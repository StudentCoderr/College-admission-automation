"""Tests for full student lifecycle management in the admin dashboard.

Covers adding students (with a one-time password-setup invitation), editing,
status changes (active / inactive / withdrawn), permanent deletion with a
second confirmation, the JSON API equivalents, and the guards that stop
inactive students from logging in or applying.
"""

from app.models import User
from app.services import application_service
from app.services.errors import ConflictError
from tests.conftest import login, register, valid_application_payload
from tests.test_admin_enhanced import admin_login, make_admin, submit_application


def _token_from(url):
    return url.rstrip("/").rsplit("/", 1)[-1]


def _create_via_api(client, **overrides):
    payload = {
        "full_name": "API Student",
        "email": "api.student@example.com",
        "phone": "9876500000",
        "status": "active",
    }
    payload.update(overrides)
    return client.post("/api/admin/students", json=payload)


# ---------------------------------------------------------------------------
# Add student (HTML)
# ---------------------------------------------------------------------------
def test_admin_add_student_html(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    course_id = app.supabase.list_courses()[0]["id"]

    resp = client.post(
        "/admin/students/new",
        data={
            "full_name": "New Student",
            "email": "new.student@example.com",
            "phone": "9876500000",
            "registration_number": "REG-1001",
            "assigned_course_id": course_id,
            "status": "active",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"One-time password setup link" in resp.data
    assert b"setup-password" in resp.data

    row = app.supabase.get_user_by_email("new.student@example.com")
    assert row is not None
    assert row["registration_number"] == "REG-1001"
    assert row["assigned_course_id"] == course_id
    assert row["status"] == "active"
    assert row["is_active"] is True
    # A random hash is stored and an invitation issued; no plaintext password
    # is ever generated for display.
    assert row["password_hash"]
    assert row["invite_token_hash"]
    assert row["invite_expires_at"]

    actions = {e["action"] for e in app.supabase.list_audit_log()}
    assert "student_create" in actions


def test_add_student_rejects_duplicate_email_and_registration(client, app):
    email, pw = make_admin(app)
    app.supabase.create_user(
        email="dup@example.com", password_hash="x", full_name="Dup",
        registration_number="REG-2001",
    )
    admin_login(client, email, pw)

    resp = client.post(
        "/admin/students/new",
        data={"full_name": "Copy", "email": "dup@example.com",
              "registration_number": "REG-9999", "status": "active"},
    )
    assert b"already exists" in resp.data

    resp = client.post(
        "/admin/students/new",
        data={"full_name": "Copy", "email": "fresh@example.com",
              "registration_number": "REG-2001", "status": "active"},
    )
    assert b"already in use" in resp.data
    assert app.supabase.get_user_by_email("fresh@example.com") is None


def test_add_inactive_student_gets_no_setup_link(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    resp = client.post(
        "/admin/students/new",
        data={"full_name": "Dormant", "email": "dormant@example.com",
              "status": "inactive"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"setup-password" not in resp.data
    assert b"not active" in resp.data.lower()


# ---------------------------------------------------------------------------
# One-time password setup
# ---------------------------------------------------------------------------
def test_password_setup_flow(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    resp = _create_via_api(client, email="invited@example.com")
    assert resp.status_code == 201
    token = _token_from(resp.get_json()["setup_url"])

    # Only the hash of the token is stored, never the token itself.
    row = app.supabase.get_user_by_email("invited@example.com")
    assert row["invite_token_hash"]
    assert token not in row["invite_token_hash"]

    client.post("/logout")

    assert client.get(f"/setup-password/{token}").status_code == 200
    # A weak password is refused and keeps the link usable.
    resp = client.post(
        f"/setup-password/{token}",
        data={"password": "short", "confirm_password": "short"},
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data

    resp = client.post(
        f"/setup-password/{token}",
        data={"password": "BrandNew1", "confirm_password": "BrandNew1"},
        follow_redirects=True,
    )
    assert b"password has been set" in resp.data

    # Single use: a second visit is rejected.
    assert client.get(f"/setup-password/{token}").status_code == 410

    resp = login(client, email="invited@example.com", password="BrandNew1")
    assert b"Welcome" in resp.data


# ---------------------------------------------------------------------------
# Status management and enforcement
# ---------------------------------------------------------------------------
def test_status_withdrawn_blocks_login(client, app):
    application = submit_application(client, app, email="withdraw@example.com")
    user_id = application["user_id"]

    email, pw = make_admin(app)
    admin_login(client, email, pw)
    client.post(
        f"/admin/students/{user_id}/status",
        data={"status": "withdrawn", "reason": "student withdrew"},
        follow_redirects=True,
    )
    client.post("/logout")

    resp = login(client, email="withdraw@example.com", password="StrongPass1")
    assert b"not active" in resp.data


def test_deactivated_student_is_signed_out(client, app):
    register(client, email="kick@example.com")
    row = app.supabase.get_user_by_email("kick@example.com")
    app.supabase.set_student_status(row["id"], "inactive")

    resp = client.get("/student/dashboard", follow_redirects=True)
    assert b"not active" in resp.data
    assert b"Welcome" not in resp.data


def test_inactive_student_cannot_create_application(app):
    row = app.supabase.create_user(
        email="inactive@example.com", password_hash="x",
        full_name="Inactive", status="inactive",
    )
    user = User(row)
    try:
        application_service.create_application(
            app.supabase, user, valid_application_payload(app)
        )
        assert False, "an inactive student must not be able to apply"
    except ConflictError:
        pass


def test_students_filter_by_withdrawn(client, app):
    app.supabase.create_user(
        email="w@example.com", password_hash="x",
        full_name="Withdrawn One", status="withdrawn",
    )
    app.supabase.create_user(
        email="a@example.com", password_hash="x",
        full_name="Active One", status="active",
    )
    email, pw = make_admin(app)
    admin_login(client, email, pw)

    resp = client.get("/admin/students?status=withdrawn")
    assert b"Withdrawn One" in resp.data
    assert b"Active One" not in resp.data


# ---------------------------------------------------------------------------
# Edit and permanent deletion
# ---------------------------------------------------------------------------
def test_admin_edit_student(client, app):
    app.supabase.create_user(
        email="edit@example.com", password_hash="x", full_name="Old Name",
    )
    user_id = app.supabase.get_user_by_email("edit@example.com")["id"]
    email, pw = make_admin(app)
    admin_login(client, email, pw)

    resp = client.post(
        f"/admin/students/{user_id}/edit",
        data={"full_name": "New Name", "email": "edit@example.com",
              "phone": "9000000000", "status": "active"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_id(user_id)
    assert row["full_name"] == "New Name"
    assert row["phone"] == "9000000000"
    actions = {e["action"] for e in app.supabase.list_audit_log()}
    assert "student_update" in actions


def test_permanent_delete_requires_confirmation(client, app):
    application = submit_application(client, app, email="delete@example.com")
    user_id = application["user_id"]
    email, pw = make_admin(app)
    admin_login(client, email, pw)

    resp = client.get(f"/admin/students/{user_id}/delete")
    assert resp.status_code == 200
    assert b"admission application" in resp.data
    assert b"<strong>1</strong>" in resp.data

    # Wrong confirmation word: nothing is deleted.
    resp = client.post(
        f"/admin/students/{user_id}/delete",
        data={"confirm": "nope", "reason": "duplicate"},
        follow_redirects=True,
    )
    assert b"Type DELETE" in resp.data
    assert app.supabase.get_user_by_id(user_id) is not None


def test_permanent_delete_removes_records_and_audits(client, app):
    application = submit_application(client, app, email="gone@example.com")
    user_id = application["user_id"]
    email, pw = make_admin(app)
    admin_login(client, email, pw)

    resp = client.post(
        f"/admin/students/{user_id}/delete",
        data={"confirm": "DELETE", "reason": "retention period elapsed"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert app.supabase.get_user_by_id(user_id) is None
    assert app.supabase.list_applications_for_user(user_id) == []

    entry = [
        e for e in app.supabase.list_audit_log() if e["action"] == "student_delete"
    ]
    assert entry and "retention period elapsed" in entry[0]["details"]


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
def test_api_student_lifecycle(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)

    resp = _create_via_api(client, email="life@example.com",
                           registration_number="REG-3001")
    assert resp.status_code == 201
    sid = resp.get_json()["student"]["id"]

    resp = client.patch(
        f"/api/admin/students/{sid}",
        json={"full_name": "Life Updated", "email": "life@example.com",
              "registration_number": "REG-3001", "status": "active"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["student"]["full_name"] == "Life Updated"

    resp = client.post(
        f"/api/admin/students/{sid}/status", json={"status": "withdrawn"}
    )
    assert resp.get_json()["student"]["status"] == "withdrawn"
    assert resp.get_json()["student"]["is_active"] is False

    # Deleting without the confirmation word is refused.
    assert client.delete(
        f"/api/admin/students/{sid}", json={"reason": "duplicate"}
    ).status_code == 422
    assert app.supabase.get_user_by_id(sid) is not None

    resp = client.delete(
        f"/api/admin/students/{sid}",
        json={"confirm": "DELETE", "reason": "duplicate record"},
    )
    assert resp.status_code == 200
    assert app.supabase.get_user_by_id(sid) is None


def test_api_student_duplicate_email(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    assert _create_via_api(client, email="dupe@example.com").status_code == 201
    assert _create_via_api(client, email="dupe@example.com").status_code == 409


def test_student_cannot_manage_students(client, app):
    register(client)
    assert client.get("/api/admin/students").status_code == 403
    assert client.post(
        "/api/admin/students", json={"email": "x@example.com"}
    ).status_code == 403
    resp = client.get("/admin/students/new")
    assert resp.status_code == 403
