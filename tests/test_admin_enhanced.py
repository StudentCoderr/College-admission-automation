"""Tests for the enhanced administrator area.

Covers the dedicated admin login, dashboard cards/charts, students management,
reports, admin profile and the audit trail.
"""

import io

from werkzeug.security import generate_password_hash

from tests.conftest import login, register, valid_application_payload


def make_admin(app, email="admin@college.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Admin User",
        role="admin",
    )
    return email, password


def admin_login(client, email="admin@college.edu", password="AdminPass1"):
    return client.post(
        "/admin/login", data={"email": email, "password": password},
        follow_redirects=True,
    )


def submit_application(client, app, email="candidate@example.com"):
    register(client, email=email)
    client.post("/student/apply", data=valid_application_payload(app), follow_redirects=True)
    application = app.supabase.list_applications()[-1]
    client.post(
        f"/student/application/{application['id']}/upload",
        data={"doc_type": "marks_card", "file": (io.BytesIO(b"%PDF-1.4"), "m.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    client.post(f"/student/application/{application['id']}/submit", follow_redirects=True)
    client.post("/logout")
    return app.supabase.get_application(application["id"])


# ---------------------------------------------------------------------------
# Dedicated admin login
# ---------------------------------------------------------------------------
def test_admin_login_page(client):
    resp = client.get("/admin/login")
    assert resp.status_code == 200
    assert b"Administrator sign in" in resp.data


def test_admin_login_success(client, app):
    email, password = make_admin(app)
    resp = admin_login(client, email, password)
    assert resp.status_code == 200
    assert b"Admissions dashboard" in resp.data


def test_admin_login_rejects_student(client, app):
    register(client, email="student@example.com")
    client.post("/logout")
    resp = admin_login(client, "student@example.com", "StrongPass1")
    assert b"does not have administrator access" in resp.data
    # Still not signed in to the admin area.
    assert client.get("/admin/dashboard").status_code == 302


def test_anonymous_admin_route_redirects_to_admin_login(client):
    resp = client.get("/admin/students")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_student_cannot_open_admin_pages(client, app):
    register(client, email="nope@example.com")
    for path in ("/admin/dashboard", "/admin/students", "/admin/reports", "/admin/profile"):
        assert client.get(path).status_code == 403


def test_registration_cannot_create_admin(client, app):
    client.post(
        "/register",
        data={
            "first_name": "Sneaky",
            "email": "sneaky@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
            "role": "admin",
        },
        follow_redirects=True,
    )
    row = app.supabase.get_user_by_email("sneaky@example.com")
    assert row is not None
    assert row["role"] == "student"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def test_dashboard_cards_and_charts(client, app):
    submit_application(client, app)
    email, password = make_admin(app)
    admin_login(client, email, password)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"Registered students" in resp.data
    assert b"Active Polytechnic courses" in resp.data
    assert b"Pending applications" in resp.data
    assert b"chart-status" in resp.data
    assert b"Applications by status" in resp.data


# ---------------------------------------------------------------------------
# Students management
# ---------------------------------------------------------------------------
def test_students_list_and_search(client, app):
    submit_application(client, app, email="alice@example.com")
    register(client, email="bob@example.com")
    client.post("/logout")

    email, password = make_admin(app)
    admin_login(client, email, password)

    resp = client.get("/admin/students")
    assert resp.status_code == 200
    assert b"alice@example.com" in resp.data
    assert b"bob@example.com" in resp.data

    resp = client.get("/admin/students?q=alice")
    assert b"alice@example.com" in resp.data
    assert b"bob@example.com" not in resp.data

    # Search by the application (registration) number.
    application = app.supabase.list_applications()[0]
    resp = client.get(f"/admin/students?q={application['application_number']}")
    assert b"alice@example.com" in resp.data


def test_student_detail_and_deactivate(client, app):
    application = submit_application(client, app, email="carol@example.com")
    user_id = application["user_id"]

    email, password = make_admin(app)
    admin_login(client, email, password)

    resp = client.get(f"/admin/students/{user_id}")
    assert resp.status_code == 200
    assert b"carol@example.com" in resp.data
    assert application["application_number"].encode() in resp.data

    resp = client.post(
        f"/admin/students/{user_id}/status",
        data={"status": "withdrawn", "reason": "student withdrew"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_id(user_id)
    assert row["status"] == "withdrawn"
    assert row["is_active"] is False
    actions = {e["action"] for e in app.supabase.list_audit_log()}
    assert "student_status_change" in actions


# ---------------------------------------------------------------------------
# Reports, profile, audit
# ---------------------------------------------------------------------------
def test_reports_page(client, app):
    submit_application(client, app)
    email, password = make_admin(app)
    admin_login(client, email, password)
    resp = client.get("/admin/reports")
    assert resp.status_code == 200
    assert b"Applications per month" in resp.data
    assert b"Recent administrative activity" in resp.data


def test_admin_can_change_password(client, app):
    email, password = make_admin(app)
    admin_login(client, email, password)

    # Wrong current password is rejected.
    resp = client.post(
        "/admin/profile",
        data={"current_password": "Wrong1", "new_password": "NewPass123",
              "confirm_password": "NewPass123"},
        follow_redirects=True,
    )
    assert b"current password is incorrect" in resp.data

    # Correct current password updates the hash.
    resp = client.post(
        "/admin/profile",
        data={"current_password": password, "new_password": "NewPass123",
              "confirm_password": "NewPass123"},
        follow_redirects=True,
    )
    assert b"password has been updated" in resp.data

    client.post("/logout")
    resp = admin_login(client, email, "NewPass123")
    assert b"Admissions dashboard" in resp.data


def test_course_creation_is_audited(client, app):
    email, password = make_admin(app)
    admin_login(client, email, password)
    client.post(
        "/admin/courses/create",
        data={"code": "DIP-MECH", "name": "Diploma in Mechanical Engineering",
              "program_type": "diploma", "duration_years": "3", "seats_total": "60"},
        follow_redirects=True,
    )
    actions = {e["action"] for e in app.supabase.list_audit_log()}
    assert "course_create" in actions


def test_status_change_is_audited(client, app):
    application = submit_application(client, app)
    email, password = make_admin(app)
    admin_login(client, email, password)
    client.post(
        f"/admin/application/{application['id']}/status",
        data={"status": "under_review", "note": "Checking documents."},
        follow_redirects=True,
    )
    entries = [e for e in app.supabase.list_audit_log() if e["action"] == "application_status_change"]
    assert entries and "under_review" in entries[0]["details"]


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
def test_api_stats_includes_students_and_courses(client, app):
    submit_application(client, app)
    app.supabase.create_course({
        "code": "DIP-CSE", "name": "Diploma in CSE", "program_type": "diploma",
        "duration_years": 3, "seats_total": 60,
    })
    email, password = make_admin(app)
    admin_login(client, email, password)

    body = client.get("/api/admin/stats").get_json()
    assert body["ok"] is True
    assert body["stats"]["students_total"] == 1
    assert body["stats"]["diploma_active"] >= 1


def test_api_students_listing_and_detail(client, app):
    application = submit_application(client, app, email="dave@example.com")
    user_id = application["user_id"]
    email, password = make_admin(app)
    admin_login(client, email, password)

    body = client.get("/api/admin/students").get_json()
    assert body["ok"] is True
    assert body["total"] == 1
    assert body["students"][0]["email"] == "dave@example.com"

    body = client.get(f"/api/admin/students/{user_id}").get_json()
    assert body["ok"] is True
    assert body["student"]["email"] == "dave@example.com"
    assert len(body["applications"]) == 1

    body = client.post(
        f"/api/admin/students/{user_id}/status", json={"is_active": False}
    ).get_json()
    assert body["ok"] is True
    assert body["student"]["is_active"] is False


def test_api_students_forbidden_for_student(client, app):
    register(client, email="blocked@example.com")
    assert client.get("/api/admin/students").status_code == 403


# ---------------------------------------------------------------------------
# Administrator profile API + static console sections
# ---------------------------------------------------------------------------
def test_api_admin_profile_and_password_change(client, app):
    email, password = make_admin(app)
    admin_login(client, email, password)

    body = client.get("/api/admin/profile").get_json()
    assert body["ok"] is True
    assert body["profile"]["email"] == email
    assert body["profile"]["role"] == "admin"
    # A password hash must never leave the server.
    assert "password_hash" not in body["profile"]

    # Wrong current password is rejected.
    resp = client.post(
        "/api/admin/profile/password",
        json={"current_password": "Wrong1", "new_password": "NewPass123",
              "confirm_password": "NewPass123"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["errors"]["current_password"]

    # Weak new password is rejected server-side.
    resp = client.post(
        "/api/admin/profile/password",
        json={"current_password": password, "new_password": "short",
              "confirm_password": "short"},
    )
    assert resp.status_code == 422

    # Mismatched confirmation is rejected.
    resp = client.post(
        "/api/admin/profile/password",
        json={"current_password": password, "new_password": "NewPass123",
              "confirm_password": "NewPass124"},
    )
    assert resp.status_code == 422

    # A valid change succeeds, is audited, and works on the next sign-in.
    resp = client.post(
        "/api/admin/profile/password",
        json={"current_password": password, "new_password": "NewPass123",
              "confirm_password": "NewPass123"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert "admin_password_change" in {e["action"] for e in app.supabase.list_audit_log()}

    client.post("/api/auth/logout")
    resp = client.post("/api/auth/login", json={"email": email, "password": "NewPass123"})
    assert resp.status_code == 200


def test_api_profile_password_forbidden_for_student(client):
    register(client, email="student-pw@example.com")
    resp = client.post(
        "/api/admin/profile/password",
        json={"current_password": "StrongPass1", "new_password": "NewPass123"},
    )
    assert resp.status_code == 403


def test_console_ships_all_admin_sections(client):
    """The standalone console exposes the full requested navigation."""
    text = client.get("/admin-console/").get_data(as_text=True)
    for section in ("panel-overview", "panel-students", "panel-applications",
                    "panel-courses", "panel-reports", "panel-profile"):
        assert section in text
    for script in ("overview.js", "students.js", "reports.js", "profile.js"):
        assert script in text
