"""Tests for the split first/middle/last name fields.

Covers registration with every combination of the optional names, server-side
validation (first name required, whitespace trimming), safe NULL storage for
empty optional fields, formatted display names, the student profile update,
admin add/edit of the three fields, legacy full_name fallbacks for the API and
CLI-style callers, and graceful behaviour on databases that predate
sql/upgrade_names.sql.
"""

import pytest

from app.models import User
from app.utils.validators import (
    clean_name,
    format_display_name,
    split_full_name,
    validate_names,
)
from tests.conftest import login, register, valid_application_payload
from tests.test_admin_enhanced import admin_login, make_admin


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------
def test_clean_name_collapses_internal_whitespace():
    assert clean_name("   Ananya    B   Sharma  ") == "Ananya B Sharma"
    assert clean_name("   ") == ""
    assert clean_name(None) == ""


def test_split_full_name_legacy_strings():
    assert split_full_name("Ananya") == ("Ananya", None, None)
    assert split_full_name("Ananya Sharma") == ("Ananya", None, "Sharma")
    assert split_full_name("Ananya B Sharma") == ("Ananya", "B", "Sharma")
    assert split_full_name("  ") == (None, None, None)


def test_format_display_name_handles_missing_parts():
    assert format_display_name("Ananya", None, "Sharma") == "Ananya Sharma"
    assert format_display_name("Ananya", None, None) == "Ananya"
    assert format_display_name("Ananya", "B", "Sharma") == "Ananya B Sharma"
    assert format_display_name(None, None, None) == ""
    assert format_display_name(None, None, None, fallback="Legacy Name") == "Legacy Name"


def test_validate_names_rules():
    (first, middle, last), errors = validate_names("  Ananya  ", "", None)
    assert first == "Ananya" and middle is None and last is None
    assert errors == {}

    _, errors = validate_names("   ", "B", "Sharma")
    assert errors["first_name"] == "First name is required."

    _, errors = validate_names(None, None, None)
    assert errors["first_name"] == "First name is required."


def test_user_model_formats_display_name_from_parts():
    user = User({"first_name": "Ananya", "middle_name": None, "last_name": "Sharma",
                 "full_name": "stale value"})
    assert user.full_name == "Ananya Sharma"
    assert user.first_name == "Ananya"
    assert user.middle_name is None
    assert user.last_name == "Sharma"


def test_user_model_falls_back_to_full_name_for_legacy_rows():
    user = User({"full_name": "Legacy Student", "email": "legacy@example.com"})
    assert user.full_name == "Legacy Student"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def test_register_with_all_three_names(client, app):
    resp = register(client, first_name="Ananya", middle_name="Priya", last_name="Sharma")
    assert resp.status_code == 200
    row = app.supabase.get_user_by_email("student@example.com")
    assert row["first_name"] == "Ananya"
    assert row["middle_name"] == "Priya"
    assert row["last_name"] == "Sharma"
    assert row["full_name"] == "Ananya Priya Sharma"
    client.post("/logout")


def test_register_first_name_only(client, app):
    register(client, email="first@example.com", first_name="Ananya")
    row = app.supabase.get_user_by_email("first@example.com")
    assert row["first_name"] == "Ananya"
    # Optional names default to SQL NULL, never empty strings.
    assert row["middle_name"] is None
    assert row["last_name"] is None
    assert row["full_name"] == "Ananya"


def test_register_first_and_last_name(client, app):
    register(client, email="fl@example.com", first_name="Ananya", last_name="Sharma")
    row = app.supabase.get_user_by_email("fl@example.com")
    assert row["first_name"] == "Ananya"
    assert row["middle_name"] is None
    assert row["last_name"] == "Sharma"
    # The example from the task: "Ananya Sharma" when the middle name is empty.
    assert row["full_name"] == "Ananya Sharma"


def test_register_trimmed_names_and_whitespace_collapse(client, app):
    register(
        client,
        email="trim@example.com",
        first_name="  Ananya   ",
        middle_name=" B ",
        last_name="  Sharma ",
    )
    row = app.supabase.get_user_by_email("trim@example.com")
    assert row["first_name"] == "Ananya"
    assert row["middle_name"] == "B"
    assert row["last_name"] == "Sharma"
    assert row["full_name"] == "Ananya B Sharma"


def test_register_rejects_blank_first_name(client, app):
    resp = client.post(
        "/register",
        data={
            "first_name": "   ",
            "middle_name": "B",
            "last_name": "Sharma",
            "email": "nofirst@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
        },
        follow_redirects=True,
    )
    assert b"First name is required." in resp.data
    # Nothing is created when the only required name field is blank.
    assert app.supabase.get_user_by_email("nofirst@example.com") is None


def test_register_page_renders_three_fields(client):
    resp = client.get("/register")
    assert resp.status_code == 200
    assert b'name="first_name"' in resp.data
    assert b'name="middle_name"' in resp.data
    assert b'name="last_name"' in resp.data
    assert b'name="full_name"' not in resp.data


# ---------------------------------------------------------------------------
# Session + profile
# ---------------------------------------------------------------------------
def test_dashboard_greeting_uses_formatted_name(client):
    register(client, email="dash@example.com", first_name="Ananya", last_name="Sharma")
    resp = client.get("/student/dashboard")
    assert resp.status_code == 200
    assert "Ananya Sharma".encode() in resp.data


def test_profile_update_with_optional_middle_name(client, app):
    register(client, email="upd@example.com", first_name="Ananya", last_name="Sharma")
    client.post("/logout")
    login(client, email="upd@example.com")
    resp = client.post(
        "/student/profile",
        data={
            "first_name": "Ananya",
            "middle_name": "Priya",
            "last_name": "",
            "phone": "9876543210",
            "email": "upd@example.com",
        },
        follow_redirects=True,
    )
    assert b"has been updated" in resp.data
    row = app.supabase.get_user_by_email("upd@example.com")
    assert row["middle_name"] == "Priya"
    assert row["last_name"] is None
    assert row["full_name"] == "Ananya Priya"
    assert b"Ananya Priya" in client.get("/student/dashboard").data


def test_profile_form_prefills_current_name_parts(client):
    register(client, email="pre@example.com", first_name="Ananya", middle_name="Priya",
             last_name="Sharma")
    resp = client.get("/student/profile")
    assert 'value="Ananya"' in resp.get_data(as_text=True)
    assert 'value="Priya"' in resp.get_data(as_text=True)
    assert 'value="Sharma"' in resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Admin student management (HTML)
# ---------------------------------------------------------------------------
def test_admin_add_student_with_three_names(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    course_id = app.supabase.list_courses()[0]["id"]
    resp = client.post(
        "/admin/students/new",
        data={
            "first_name": "Ravi",
            "middle_name": "Kumar",
            "last_name": "Reddy",
            "email": "ravi@example.com",
            "phone": "9876500000",
            "assigned_course_id": course_id,
            "status": "active",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_email("ravi@example.com")
    assert row["first_name"] == "Ravi"
    assert row["middle_name"] == "Kumar"
    assert row["last_name"] == "Reddy"
    assert row["full_name"] == "Ravi Kumar Reddy"


def test_admin_edit_student_name_parts(client, app):
    email, pw = make_admin(app)
    user_id = app.supabase.create_user(
        email="edit@example.com",
        password_hash="x",
        first_name="Old",
        last_name="Name",
    )["id"]
    admin_login(client, email, pw)
    resp = client.post(
        f"/admin/students/{user_id}/edit",
        data={
            "first_name": "New",
            "middle_name": "First",
            "last_name": "Name",
            "email": "edit@example.com",
            "phone": "",
            "status": "active",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = app.supabase.get_user_by_email("edit@example.com")
    assert row["first_name"] == "New"
    assert row["middle_name"] == "First"
    assert row["last_name"] == "Name"
    assert row["full_name"] == "New First Name"


def test_admin_student_detail_shows_name_parts(client, app):
    email, pw = make_admin(app)
    user_id = app.supabase.create_user(
        email="detail@example.com",
        password_hash="x",
        first_name="Ananya",
        middle_name="B",
        last_name="Sharma",
    )["id"]
    admin_login(client, email, pw)
    resp = client.get(f"/admin/students/{user_id}")
    assert resp.status_code == 200
    assert b"First name" in resp.data and b"<dd>Ananya</dd>" in resp.data
    assert b"Middle name" in resp.data and b"<dd>B</dd>" in resp.data
    assert b"Last name" in resp.data and b"<dd>Sharma</dd>" in resp.data


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
def test_api_create_student_with_three_names(client, app):
    email, pw = make_admin(app)
    admin_login(client, email, pw)
    resp = client.post(
        "/api/admin/students",
        json={
            "first_name": "Kiran",
            "middle_name": "",
            "last_name": "Joshi",
            "email": "kiran@example.com",
            "phone": "9876500001",
            "status": "active",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["student"]["first_name"] == "Kiran"
    assert body["student"]["middle_name"] is None
    assert body["student"]["last_name"] == "Joshi"
    assert body["student"]["full_name"] == "Kiran Joshi"


def test_api_register_legacy_full_name_split(client, app):
    resp = client.post(
        "/api/auth/register",
        json={
            "full_name": "API Student",
            "email": "legacy.api@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    # The serialized display name is preserved for old clients ...
    assert body["user"]["full_name"] == "API Student"
    # ... while the stored row is split into parts.
    row = app.supabase.get_user_by_email("legacy.api@example.com")
    assert row["first_name"] == "API"
    assert row["last_name"] == "Student"
    assert row["full_name"] == "API Student"


def test_api_register_first_name_only(client, app):
    resp = client.post(
        "/api/auth/register",
        json={
            "first_name": "Solo",
            "email": "solo@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
        },
    )
    assert resp.status_code == 201
    row = app.supabase.get_user_by_email("solo@example.com")
    assert row["first_name"] == "Solo"
    assert row["middle_name"] is None
    assert row["last_name"] is None
    assert row["full_name"] == "Solo"


def test_api_register_rejects_missing_first_name(client):
    resp = client.post(
        "/api/register",
        json={"email": "noname2@example.com", "password": "StrongPass1"},
    )
    assert resp.status_code == 422
    assert "first_name" in resp.get_json()["errors"]


# ---------------------------------------------------------------------------
# Legacy schema (no first/middle/last columns)
# ---------------------------------------------------------------------------
@pytest.fixture()
def legacy_schema(app):
    app.supabase.simulate_legacy_users_schema()
    return app


def test_register_works_on_legacy_schema(legacy_schema, client):
    register(client, email="legacy@legacy.edu", first_name="Ananya", last_name="Sharma")
    row = legacy_schema.supabase.get_user_by_email("legacy@legacy.edu")
    # The parts are dropped on an old database, but the account and display
    # name still work.
    assert "first_name" not in row
    assert row["full_name"] == "Ananya Sharma"
    client.post("/logout")
    resp = login(client, email="legacy@legacy.edu")
    assert resp.status_code == 200
    assert b"Logout" in resp.data


def test_admin_add_and_edit_work_on_legacy_schema(legacy_schema, client):
    email, pw = make_admin(legacy_schema)
    admin_login(client, email, pw)
    resp = client.post(
        "/admin/students/new",
        data={
            "first_name": "Legacy",
            "last_name": "Kid",
            "email": "lk@legacy.edu",
            "status": "active",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    row = legacy_schema.supabase.get_user_by_email("lk@legacy.edu")
    assert "first_name" not in row
    assert row["full_name"] == "Legacy Kid"


# ---------------------------------------------------------------------------
# Admission application form (First / Middle / Last)
# ---------------------------------------------------------------------------
def _apply(client, app, **overrides):
    return client.post(
        "/student/apply",
        data=valid_application_payload(app, **overrides),
        follow_redirects=True,
    )


def test_apply_form_renders_three_name_fields(client):
    register(client, email="apply.fields@example.com")
    resp = client.get("/student/apply")
    assert resp.status_code == 200
    assert b'name="first_name"' in resp.data
    assert b'name="middle_name"' in resp.data
    assert b'name="last_name"' in resp.data
    # Only the first name is mandatory at the HTML level.
    assert b'name="first_name" maxlength="120" required' in resp.data
    assert b'name="middle_name" maxlength="120" required' not in resp.data
    assert b'name="last_name" maxlength="120" required' not in resp.data


def test_apply_form_prefills_names_from_registration(client):
    register(
        client,
        email="apply.prefill@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    resp = client.get("/student/apply")
    assert b'value="Ananya"' in resp.data
    assert b'value="Priya"' in resp.data
    assert b'value="Sharma"' in resp.data


def test_apply_first_name_only_stores_null_optionals(client, app):
    register(client, email="apply.solo@example.com", first_name="Ananya")
    resp = _apply(client, app, first_name="Solo", middle_name="", last_name="")
    assert resp.status_code == 200
    row = app.supabase.list_applications()[0]
    assert row["first_name"] == "Solo"
    assert row["middle_name"] is None
    assert row["last_name"] is None


def test_apply_first_and_last_name(client, app):
    register(client, email="apply.fl@example.com", first_name="Ananya")
    _apply(client, app, first_name="Ananya", middle_name="", last_name="Sharma")
    row = app.supabase.list_applications()[0]
    assert row["first_name"] == "Ananya"
    assert row["middle_name"] is None
    assert row["last_name"] == "Sharma"


def test_apply_all_three_names_and_detail_shows_them(client, app):
    register(
        client,
        email="apply.three@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    _apply(
        client, app, first_name="Ananya", middle_name="Priya", last_name="Sharma"
    )
    row = app.supabase.list_applications()[0]
    assert row["first_name"] == "Ananya"
    assert row["middle_name"] == "Priya"
    assert row["last_name"] == "Sharma"
    resp = client.get(f"/student/application/{row['id']}")
    assert b"Ananya Priya Sharma" in resp.data


def test_application_detail_handles_missing_optionals(client, app):
    register(client, email="apply.blank@example.com", first_name="Ananya")
    _apply(client, app, first_name="Ananya", middle_name="", last_name="")
    row = app.supabase.list_applications()[0]
    resp = client.get(f"/student/application/{row['id']}")
    assert resp.status_code == 200
    assert b"Ananya" in resp.data


def test_apply_first_name_only_is_enough(client, app):
    register(client, email="apply.nolast@example.com", first_name="Ananya")
    resp = _apply(client, app, first_name="Ananya", middle_name="", last_name="")
    # No "Last name is required." validation error is shown.
    assert b"Last name is required." not in resp.data
    assert b"draft" in resp.data.lower() or b"application" in resp.data.lower()


def test_apply_missing_profile_parts_can_be_filled_and_sync(client, app):
    register(client, email="apply.fill@example.com", first_name="Ananya")
    _apply(client, app, first_name="Ananya", middle_name="Priya", last_name="Sharma")
    row = app.supabase.list_applications()[0]
    assert row["middle_name"] == "Priya"
    assert row["last_name"] == "Sharma"
    user = app.supabase.get_user_by_email("apply.fill@example.com")
    # The profile is completed too, so it is consistent everywhere.
    assert user["middle_name"] == "Priya"
    assert user["last_name"] == "Sharma"
    assert user["full_name"] == "Ananya Priya Sharma"


def test_apply_blank_optionals_do_not_overwrite_profile(client, app):
    register(
        client,
        email="apply.keep@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    _apply(client, app, first_name="Ananya", middle_name="   ", last_name="")
    user = app.supabase.get_user_by_email("apply.keep@example.com")
    # A blank optional field never erases a name already saved on the profile.
    assert user["middle_name"] == "Priya"
    assert user["last_name"] == "Sharma"
    assert user["full_name"] == "Ananya Priya Sharma"


def test_application_update_saves_new_name_consistently(client, app):
    register(
        client,
        email="apply.update@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    _apply(client, app, first_name="Ananya", middle_name="Priya", last_name="Sharma")
    application = app.supabase.list_applications()[0]
    resp = client.post(
        f"/student/application/{application['id']}/edit",
        data=valid_application_payload(
            app, first_name="Ananya", middle_name="Kumari", last_name="Sharma"
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    application = app.supabase.get_application(application["id"])
    assert application["middle_name"] == "Kumari"
    user = app.supabase.get_user_by_email("apply.update@example.com")
    assert user["middle_name"] == "Kumari"
    assert user["full_name"] == "Ananya Kumari Sharma"


def test_apply_works_on_legacy_application_schema(client, app):
    app.supabase.simulate_legacy_applications_schema()
    register(
        client,
        email="apply.legacy@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    resp = _apply(
        client, app, first_name="Ananya", middle_name="Priya", last_name="Sharma"
    )
    assert resp.status_code == 200
    row = app.supabase.list_applications()[0]
    # The middle_name column is dropped gracefully on an old database ...
    assert "middle_name" not in row
    # ... while the required name parts are still saved.
    assert row["first_name"] == "Ananya"
    assert row["last_name"] == "Sharma"


def test_api_application_serializes_middle_name(client, app):
    register(
        client,
        email="apply.api@example.com",
        first_name="Ananya",
        middle_name="Priya",
        last_name="Sharma",
    )
    resp = client.post(
        "/api/applications",
        json=valid_application_payload(
            app, first_name="Ananya", middle_name="Priya", last_name="Sharma"
        ),
    )
    assert resp.status_code == 201
    body = resp.get_json()["application"]
    assert body["first_name"] == "Ananya"
    assert body["middle_name"] == "Priya"
    assert body["last_name"] == "Sharma"
    assert body["applicantName"] == "Ananya Priya Sharma"