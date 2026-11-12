"""Course catalogue resilience tests.

The courses *table* being empty and the courses *query* failing look the same
to a naive template (an empty list). These tests pin the distinction the admin
and student pages now make: an empty catalogue is a normal state with an
"add courses" message, while a failed query is reported as a database error.
They also cover the legacy-schema warning that tells an administrator to run
the SQL upgrade before programme type / fees / eligibility can be stored.
"""

from werkzeug.security import generate_password_hash

from tests.conftest import login, register


def _make_admin(app, email="admin@college.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Admin User",
        role="admin",
    )
    return email, password


def test_course_schema_missing_reports_legacy_columns(app):
    # A fully-upgraded fake reports nothing missing.
    assert app.supabase.course_schema_missing() == []

    app.supabase.simulate_legacy_courses_schema()
    missing = app.supabase.course_schema_missing()
    assert "program_type" in missing
    assert "eligibility" in missing
    assert "tuition_fee" in missing
    assert "eligible_qualifications" in missing
    # is_active is part of the same optional set.
    assert "is_active" in missing


def test_admin_courses_warns_when_schema_is_stale(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    app.supabase.simulate_legacy_courses_schema()

    resp = client.get("/admin/courses")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "is missing" in body
    assert "program_type" in body
    assert "upgrade_diploma.sql" in body


def test_admin_courses_shows_no_schema_warning_when_upgraded(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.get("/admin/courses")
    body = resp.get_data(as_text=True)
    assert "table is missing" not in body


def test_catalogue_reports_database_error_not_empty(client, app):
    app.supabase.simulate_course_query_error()

    resp = client.get("/courses")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "temporarily unavailable" in body
    # It must not masquerade as an empty-but-healthy catalogue.
    assert "No courses available yet" not in body


def test_catalogue_shows_empty_message_when_truly_empty(client, app):
    app.supabase.courses.clear()

    resp = client.get("/courses")
    body = resp.get_data(as_text=True)
    assert "No courses available yet" in body
    assert "temporarily unavailable" not in body


def test_apply_reports_database_error_not_empty(client, app):
    register(client)
    app.supabase.simulate_course_query_error()

    resp = client.get("/student/apply")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "temporarily unavailable" in body
    assert "No courses are currently available" not in body
