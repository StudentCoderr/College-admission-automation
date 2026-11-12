"""Tests for centralised student contact details (email + phone).

Covers the shared profile service: registration details are reused on the
admission form, the application keeps an intentional snapshot, the profile
stays in step, legacy rows with a missing phone do not crash, contact updates
are validated server-side, and one student can never see another's details.
"""

from app.models import User
from app.services import profile_service
from tests.conftest import login, register, valid_application_payload


# ---------------------------------------------------------------------------
# Unit: the shared profile service
# ---------------------------------------------------------------------------
def test_profile_contact_reads_names_email_and_phone():
    user = User(
        {
            "id": "u1",
            "email": "Ananya@Example.com",
            "first_name": "Ananya",
            "last_name": "Sharma",
            "phone": "9876543210",
        }
    )
    contact = profile_service.profile_contact(user)
    assert contact == {
        "first_name": "Ananya",
        "middle_name": "",
        "last_name": "Sharma",
        "email": "Ananya@Example.com",
        "phone": "9876543210",
    }


def test_profile_contact_falls_back_to_legacy_full_name():
    user = User({"id": "u2", "email": "legacy@example.com", "full_name": "Legacy Kid"})
    contact = profile_service.profile_contact(user)
    assert contact["first_name"] == "Legacy"
    assert contact["last_name"] == "Kid"
    assert contact["phone"] == ""  # missing phone never renders as None


def test_profile_contact_handles_a_totally_empty_legacy_row():
    contact = profile_service.profile_contact(User({"id": "u3"}))
    assert contact == {
        "first_name": "",
        "middle_name": "",
        "last_name": "",
        "email": "",
        "phone": "",
    }


def test_merge_contact_fills_only_blank_snapshot_fields():
    snapshot = {"first_name": "Asha", "last_name": "", "email": "", "phone": ""}
    profile = {
        "first_name": "PROFILE",
        "middle_name": "B",
        "last_name": "Rao",
        "email": "profile@example.com",
        "phone": "9000000000",
    }
    merged = profile_service.merge_contact(snapshot, profile)
    # The application's own values win; only the gaps are filled.
    assert merged["first_name"] == "Asha"
    assert merged["last_name"] == "Rao"
    assert merged["middle_name"] == "B"
    assert merged["email"] == "profile@example.com"
    assert merged["phone"] == "9000000000"


def test_validate_profile_contact_rejects_email_change_and_bad_phone():
    values, errors = profile_service.validate_profile_contact(
        {"first_name": "Asha", "phone": "abc", "email": "other@example.com"},
        "asha@example.com",
    )
    assert "phone" in errors
    assert "email" in errors
    # The email is never written back to the login identity.
    assert "email" not in values


# ---------------------------------------------------------------------------
# The application form is prefilled from registration details
# ---------------------------------------------------------------------------
def test_apply_form_prefills_email_and_phone_from_registration(client):
    register(client, email="contact.prefill@example.com")
    resp = client.get("/student/apply")
    assert resp.status_code == 200
    assert b'value="contact.prefill@example.com"' in resp.data
    assert b'value="9876543210"' in resp.data


def test_apply_saves_snapshot_and_keeps_profile_in_step(client, app):
    register(client, email="contact.sync@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(
            app, email="contact.sync@example.com", phone="9111111111"
        ),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]
    assert application["email"] == "contact.sync@example.com"
    assert application["phone"] == "9111111111"
    # The number the student used is also the number on their profile.
    user = app.supabase.get_user_by_email("contact.sync@example.com")
    assert user["phone"] == "9111111111"
    assert b"9111111111" in client.get("/student/dashboard").data


def test_edit_form_fills_a_missing_legacy_phone_from_profile(client, app):
    register(client, email="contact.legacyapp@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, email="contact.legacyapp@example.com"),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]
    # Simulate an application saved before we captured the phone.
    app.supabase.applications[application["id"]]["phone"] = None
    resp = client.get(f"/student/application/{application['id']}/edit")
    assert resp.status_code == 200
    assert b'value="9876543210"' in resp.data


def test_apply_works_when_the_profile_has_no_phone(client, app):
    register(client, email="contact.nophone@example.com")
    user = app.supabase.get_user_by_email("contact.nophone@example.com")
    app.supabase.users[user["id"]]["phone"] = None

    resp = client.get("/student/apply")
    assert resp.status_code == 200
    # Email is still prefilled even though the phone is missing.
    assert b'value="contact.nophone@example.com"' in resp.data

    resp = client.post(
        "/student/apply",
        data=valid_application_payload(
            app, email="contact.nophone@example.com", phone="9222222222"
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    user = app.supabase.get_user_by_email("contact.nophone@example.com")
    assert user["phone"] == "9222222222"


# ---------------------------------------------------------------------------
# Profile updates validate server-side
# ---------------------------------------------------------------------------
def test_profile_rejects_invalid_phone(client, app):
    register(client, email="contact.badphone@example.com")
    resp = client.post(
        "/student/profile",
        data={"first_name": "Test", "last_name": "Student", "phone": "abc"},
        follow_redirects=True,
    )
    assert b"valid phone number" in resp.data
    user = app.supabase.get_user_by_email("contact.badphone@example.com")
    assert user["phone"] == "9876543210"  # unchanged


def test_profile_cannot_change_the_login_email(client, app):
    register(client, email="contact.locked@example.com")
    resp = client.post(
        "/student/profile",
        data={
            "first_name": "Test",
            "last_name": "Student",
            "phone": "9333333333",
            "email": "changed@example.com",
        },
        follow_redirects=True,
    )
    assert b"cannot be changed" in resp.data
    row = app.supabase.get_user_by_email("contact.locked@example.com")
    assert row is not None
    assert row["phone"] == "9876543210"  # nothing was saved


def test_profile_phone_update_is_persisted_and_reflected(client, app):
    register(client, email="contact.update@example.com")
    # The session user is reloaded from the database on every request.
    client.post("/logout")
    login(client, email="contact.update@example.com")
    resp = client.post(
        "/student/profile",
        data={"first_name": "Test", "last_name": "Student", "phone": "9444444444"},
        follow_redirects=True,
    )
    assert b"has been updated" in resp.data
    assert b"9444444444" in resp.data
    row = app.supabase.get_user_by_email("contact.update@example.com")
    assert row["phone"] == "9444444444"


# ---------------------------------------------------------------------------
# Privacy: a student only ever sees their own details
# ---------------------------------------------------------------------------
def test_students_cannot_view_each_others_application(client, app):
    register(client, email="contact.owner@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, email="contact.owner@example.com"),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]

    client.post("/logout")
    register(client, email="contact.intruder@example.com")

    # The application belongs to someone else: never found, never edited.
    assert client.get(f"/student/application/{application['id']}").status_code == 404
    assert (
        client.get(f"/student/application/{application['id']}/edit").status_code == 404
    )

    dashboard = client.get("/student/dashboard").data
    assert b"contact.intruder@example.com" in dashboard
    assert b"contact.owner@example.com" not in dashboard


def test_admin_student_detail_shows_contact_details(client, app):
    from tests.test_admin_enhanced import admin_login, make_admin

    email, password = make_admin(app)
    user_id = app.supabase.create_user(
        email="contact.detail@example.com",
        password_hash="x",
        first_name="Asha",
        last_name="Rao",
        phone="9555555555",
    )["id"]
    admin_login(client, email, password)
    resp = client.get(f"/admin/students/{user_id}")
    assert resp.status_code == 200
    assert b"Email address" in resp.data
    assert b"contact.detail@example.com" in resp.data
    assert b"9555555555" in resp.data
