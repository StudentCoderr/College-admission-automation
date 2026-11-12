"""Registration and authentication against a legacy users schema.

The live Supabase project predates ``sql/upgrade_students.sql``, so
``public.users`` has no ``status`` / ``registration_number`` /
``assigned_course_id`` / ``invite_*`` columns. Sending ``status`` in an
INSERT used to make PostgREST reject registration with PGRST204.

These tests verify that registration, login, logout, profile updates and the
admin student views all still work against that schema, and that the
schema-aware service never sends or queries an unknown column.
"""

from werkzeug.security import check_password_hash, generate_password_hash

from tests.conftest import login, register


def _legacy(app, client):
    app.supabase.simulate_legacy_users_schema()
    return client


def _make_admin(app, email="admin@legacy.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Legacy Admin",
        role="admin",
    )
    return email, password


def test_register_works_without_status_column(app, client):
    client = _legacy(app, client)
    resp = register(client, email="legacy1@example.edu", name="Legacy Student")
    assert resp.status_code == 200
    # Newly registered student lands on the student dashboard.
    assert b"Logout" in resp.data

    # The row exists, the password is hashed and `status` was NOT sent: the
    # schema-aware service omitted the missing column instead of failing.
    row = app.supabase.get_user_by_email("legacy1@example.edu")
    assert row["role"] == "student"
    assert row["is_active"] is True
    assert "status" not in row
    assert check_password_hash(row["password_hash"], "StrongPass1")


def test_duplicate_email_still_rejected(app, client):
    client = _legacy(app, client)
    register(client, email="dup@legacy.edu")
    client.post("/logout")
    resp = register(client, email="dup@legacy.edu")
    assert b"already exists" in resp.data


def test_login_logout_work_after_legacy_registration(app, client):
    client = _legacy(app, client)
    register(client, email="lifecycle@legacy.edu")
    client.post("/logout")
    resp = login(client, email="lifecycle@legacy.edu")
    assert resp.status_code == 200
    assert b"Logout" in resp.data

    resp = client.post("/logout", follow_redirects=True)
    assert resp.status_code == 200
    # Logout redirects to the public landing page.
    assert b"Your Future Starts" in resp.data


def test_student_profile_update_works_on_legacy_schema(app, client):
    client = _legacy(app, client)
    register(client, email="profile@legacy.edu")
    resp = client.post(
        "/student/profile",
        data={"first_name": "Renamed", "last_name": "Student", "phone": "9123456780"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_email("profile@legacy.edu")
    # On a legacy schema the name parts are dropped but the display column is
    # still rebuilt from the supplied parts.
    assert row["full_name"] == "Renamed Student"
    assert row["phone"] == "9123456780"


def test_admin_student_list_works_without_status_column(app, client):
    client = _legacy(app, client)
    email, password = _make_admin(app)
    register(client, email="kid@legacy.edu")
    client.post("/logout")

    resp = client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp = client.get("/admin/students")
    assert resp.status_code == 200
    assert b"kid@legacy.edu" in resp.data

    # A status filter or sort by status is silently ignored (no such column)
    # instead of raising PGRST204 / 500-ing.
    resp = client.get("/admin/students?status=inactive")
    assert resp.status_code == 200
    resp = client.get("/admin/students?sort=status")
    assert resp.status_code == 200


def test_legacy_deactivation_still_blocks_login(app, client):
    client = _legacy(app, client)
    email, password = _make_admin(app)
    register(client, email="kid2@legacy.edu")
    student_id = app.supabase.get_user_by_email("kid2@legacy.edu")["id"]
    client.post("/logout")

    client.post(
        "/admin/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )
    # With no `status` column the admin toggle still flips the boolean gate.
    resp = client.post(
        "/admin/students/{}/status".format(student_id),
        data={"status": "inactive"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_email("kid2@legacy.edu")
    assert row["is_active"] is False
    assert "status" not in row

    resp = client.post("/logout", follow_redirects=True)
    resp = login(client, email="kid2@legacy.edu")
    # The boolean is_active gate still blocks sign-in on a legacy schema.
    assert b"This account is not active." in resp.data