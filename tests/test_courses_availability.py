"""Course availability tests.

Covers the two ways the course catalogue can come back empty:

  1. The live database has no course rows -> every page shows a friendly
     "no courses available" message (public catalogue, student picker,
     admin list).
  2. The live courses table is an OLD schema (no program_type /
     eligibility / tuition_fee / is_active columns) -> the schema-aware
     service still lists the rows that exist instead of failing.
"""

from werkzeug.security import generate_password_hash

from tests.conftest import login, register, valid_application_payload


def _legacy_courses(app):
    """Drop the additive course columns on the fake, like an old deploy."""
    app.supabase.simulate_legacy_courses_schema()
    return app


def _make_admin(app, email="admin@courses.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Courses Admin",
        role="admin",
    )
    return email, password


def _no_courses(app):
    """The conftest seeds BTECH-CSE; remove it for empty-catalogue tests."""
    app.supabase.courses.clear()
    return app


def _by_code(app, code):
    return next(
        c for c in app.supabase.list_courses() if c.get("code") == code
    )


# ---------------------------------------------------------------------------
# Empty catalogue -> friendly messages
# ---------------------------------------------------------------------------
def test_public_catalogue_shows_empty_message(app, client):
    _no_courses(app)
    resp = client.get("/courses")
    assert resp.status_code == 200
    assert b"No courses available yet" in resp.data


def test_apply_page_shows_empty_message_when_no_courses(app, client):
    _no_courses(app)
    register(client, email="no-course@example.edu")
    resp = client.get("/student/apply")
    assert resp.status_code == 200
    assert b"No courses are currently available" in resp.data


# ---------------------------------------------------------------------------
# Legacy courses schema (missing additive columns) still lists rows
# ---------------------------------------------------------------------------
def test_legacy_courses_table_still_lists_courses(app, client):
    _legacy_courses(app)
    app.supabase.create_course({
        "code": "DIP-OLD", "name": "Diploma in Old Schema",
        "description": "Legacy row", "duration_years": 3, "seats_total": 60,
    })
    # No is_active / program_type columns -> everything is treated as active.
    resp = client.get("/courses")
    assert resp.status_code == 200
    assert b"DIP-OLD" in resp.data
    assert b"Apply now" in resp.data

    register(client, email="legacy-courses@example.edu")
    resp = client.get("/student/apply")
    assert resp.status_code == 200
    assert b"Diploma in Old Schema" in resp.data


def test_admin_can_add_course_on_legacy_schema(app, client):
    _legacy_courses(app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    resp = client.post(
        "/admin/courses/create",
        data={
            "code": "DIP-ADD",
            "name": "Diploma in New Course",
            "duration_years": "3",
            "seats_total": "60",
            "program_type": "diploma",
            "eligibility": "Pass in SSLC",
            "tuition_fee": "25000",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Course added" in resp.data
    assert b"DIP-ADD" in resp.data
    # The optional columns are dropped, base columns are stored.
    row = _by_code(app, "DIP-ADD")
    assert row["code"] == "DIP-ADD"
    assert "tuition_fee" not in row


# ---------------------------------------------------------------------------
# Active/inactive gating end to end
# ---------------------------------------------------------------------------
def test_inactive_course_hidden_from_students_but_visible_in_all(app, client):
    app.supabase.create_course({
        "code": "DIP-SEAT", "name": "Diploma in Seats",
        "duration_years": 3, "seats_total": 60, "program_type": "diploma",
        "eligibility": "Pass in SSLC", "tuition_fee": 20000,
    })
    course_id = _by_code(app, "DIP-SEAT")["id"]

    resp = client.get("/courses")
    assert b"DIP-SEAT" in resp.data
    resp = client.get("/courses?status=all")
    assert b"DIP-SEAT" in resp.data

    # Deactivate it through the admin flow.
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    client.post(
        "/admin/courses/{}/toggle".format(course_id),
        follow_redirects=True,
    )
    resp = client.get("/courses")
    assert b"DIP-SEAT" not in resp.data
    resp = client.get("/courses?status=all")
    assert b"DIP-SEAT" in resp.data


def test_apply_rejects_inactive_or_unknown_course(app, client):
    app.supabase.create_course({
        "code": "BTECH-X", "name": "B.Tech Experimental",
        "duration_years": 4, "seats_total": 60, "program_type": "degree",
    })
    active_id = _by_code(app, "BTECH-X")["id"]
    register(client, email="gate@example.edu")
    resp = client.post("/student/apply", data=valid_application_payload(
        app, course_id="00000000-0000-0000-0000-000000000000"
    ), follow_redirects=True)
    assert b"The selected course is not available." in resp.data
    assert app.supabase.list_applications() == []

    # Sanity: an active course IS accepted.
    resp = client.post("/student/apply", data=valid_application_payload(
        app, course_id=active_id
    ), follow_redirects=True)
    assert resp.status_code == 200
    assert len(app.supabase.list_applications()) == 1