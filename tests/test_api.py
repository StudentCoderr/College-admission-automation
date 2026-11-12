"""Tests for the JSON REST API (``/api``).

These exercise authentication, authorization, validation, the application
lifecycle, private document uploads and CSRF protection end to end using the
in-memory fake Supabase service.
"""

import io
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from tests.conftest import valid_application_payload
from tests.fake_supabase import FakeSupabaseService

STUDENT = {"email": "api.student@example.com", "password": "StrongPass1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def api_register(client, email=STUDENT["email"], password=STUDENT["password"], name="API Student"):
    return client.post(
        "/api/auth/register",
        json={
            "full_name": name,
            "email": email,
            "phone": "9876543210",
            "password": password,
            "confirm_password": password,
        },
    )


def api_login(client, email=STUDENT["email"], password=STUDENT["password"]):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def make_admin(app, email="api.admin@example.com", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="API Admin",
        role="admin",
    )
    return email, password


def create_application(client, app, **overrides):
    return client.post("/api/applications", json=valid_application_payload(app, **overrides))


def upload_marks_card(client, application_id, filename="marks.pdf", content=b"%PDF-1.4 fake"):
    return client.post(
        f"/api/applications/{application_id}/documents",
        data={"doc_type": "marks_card", "file": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_register_returns_user_and_csrf(client):
    resp = api_register(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["ok"] is True
    assert body["user"]["email"] == STUDENT["email"]
    assert body["user"]["role"] == "student"
    assert "password_hash" not in body["user"]
    assert body["csrf_token"]


def test_register_duplicate_email_conflicts(client):
    api_register(client)
    client.post("/api/auth/logout")
    resp = api_register(client)
    assert resp.status_code == 409
    assert resp.get_json()["ok"] is False


def test_register_weak_password_is_rejected(client):
    resp = client.post(
        "/api/auth/register",
        json={"full_name": "Weak", "email": "weak@example.com", "password": "short"},
    )
    assert resp.status_code == 422
    assert "password" in resp.get_json()["errors"]


def test_register_requires_full_name(client):
    resp = client.post(
        "/api/register",
        json={"email": "noname@example.com", "password": "StrongPass1"},
    )
    assert resp.status_code == 422
    assert "first_name" in resp.get_json()["errors"]


def test_login_success_and_me(client):
    api_register(client)
    client.post("/api/auth/logout")

    resp = api_login(client)
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == STUDENT["email"]

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == STUDENT["email"]


def test_login_wrong_password_unauthorized(client):
    api_register(client)
    client.post("/api/auth/logout")
    resp = api_login(client, password="WrongPass9")
    assert resp.status_code == 401


def test_me_anonymous_returns_null_user(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.get_json()["user"] is None


def test_logout_clears_session(client):
    api_register(client)
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert client.get("/api/auth/me").get_json()["user"] is None


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------
def test_courses_are_public(client, app):
    resp = client.get("/api/courses")
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.get_json()["courses"]]
    assert "BTECH-CSE" in codes


def test_announcements_endpoint(client):
    resp = client.get("/api/announcements")
    assert resp.status_code == 200
    assert resp.get_json()["announcements"] == []


# ---------------------------------------------------------------------------
# Application lifecycle + authorization
# ---------------------------------------------------------------------------
def test_create_application_requires_login(client, app):
    resp = client.post("/api/applications", json=valid_application_payload(app))
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_create_application_as_student(client, app):
    api_register(client)
    resp = create_application(client, app)
    assert resp.status_code == 201
    application = resp.get_json()["application"]
    assert application["status"] == "draft"
    assert application["id"]
    assert application["application_number"] is None


def test_student_cannot_self_assign_approved_status(client, app):
    api_register(client)
    resp = create_application(client, app, status="approved")
    assert resp.status_code == 201
    # The protected field is ignored: a new application is always a draft.
    assert resp.get_json()["application"]["status"] == "draft"


def test_student_cannot_promote_own_application_via_update(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]

    resp = client.put(
        f"/api/applications/{application_id}",
        json=valid_application_payload(app, status="approved", city="Mysuru"),
    )
    assert resp.status_code == 200
    body = resp.get_json()["application"]
    assert body["status"] == "draft"  # unchanged
    assert body["city"] == "Mysuru"  # legitimate edit applied


def test_my_applications_lists_only_own(client, app):
    api_register(client)
    create_application(client, app)
    resp = client.get("/api/applications/my")
    assert resp.status_code == 200
    assert len(resp.get_json()["applications"]) == 1


def test_student_cannot_view_another_students_application(client, app):
    api_register(client, email="owner@example.com")
    application_id = create_application(client, app).get_json()["application"]["id"]

    client.post("/api/auth/logout")
    api_register(client, email="intruder@example.com")

    resp = client.get(f"/api/applications/{application_id}")
    assert resp.status_code == 404

    resp = client.get(f"/api/applications/{application_id}/documents")
    assert resp.status_code == 404

    resp = client.put(
        f"/api/applications/{application_id}", json=valid_application_payload(app)
    )
    assert resp.status_code == 404


def test_application_validation_errors_are_field_scoped(client, app):
    api_register(client)
    resp = create_application(client, app, marks_obtained="600", marks_total="500")
    assert resp.status_code == 422
    assert "marks_obtained" in resp.get_json()["errors"]


def test_submit_requires_marks_card(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]
    resp = client.post(f"/api/applications/{application_id}/submit")
    assert resp.status_code == 409


def test_upload_document_and_submit(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]

    resp = upload_marks_card(client, application_id)
    assert resp.status_code == 201
    document = resp.get_json()["document"]
    assert document["doc_type"] == "marks_card"
    assert document["verified"] is False

    resp = client.post(f"/api/applications/{application_id}/submit")
    assert resp.status_code == 200
    application = resp.get_json()["application"]
    assert application["status"] == "submitted"
    assert application["application_number"].startswith("ADM-")


def test_document_upload_rejects_bad_extension(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]
    resp = upload_marks_card(client, application_id, filename="virus.exe", content=b"x")
    assert resp.status_code == 422


def test_document_upload_enforces_size_limit(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]
    app.config["MAX_CONTENT_LENGTH"] = 1024
    resp = upload_marks_card(client, application_id, content=b"x" * 2048)
    assert resp.status_code == 413


def test_signed_url_access_is_owner_only(client, app):
    api_register(client)
    application_id = create_application(client, app).get_json()["application"]["id"]
    document_id = upload_marks_card(client, application_id).get_json()["document"]["id"]

    resp = client.get(f"/api/documents/{document_id}")
    assert resp.status_code == 200
    assert resp.get_json()["url"]

    client.post("/api/auth/logout")
    api_register(client, email="nosy@example.com")
    assert client.get(f"/api/documents/{document_id}").status_code == 404


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
def _submitted_application(client, app):
    application_id = create_application(client, app).get_json()["application"]["id"]
    upload_marks_card(client, application_id)
    client.post(f"/api/applications/{application_id}/submit")
    return client.get(f"/api/applications/{application_id}").get_json()["application"]


def test_track_by_number_with_email(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    resp = client.post(
        "/api/applications/track",
        json={"number": application["application_number"], "email": application["email"]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["application"]["application_number"] == application["application_number"]


def test_track_requires_matching_email(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    resp = client.post(
        "/api/applications/track",
        json={"number": application["application_number"], "email": "wrong@example.com"},
    )
    assert resp.status_code == 403

    resp = client.get(
        f"/api/applications/track/{application['application_number']}?email=wrong@example.com"
    )
    assert resp.status_code == 403


def test_track_unknown_number_returns_404(client):
    resp = client.post("/api/applications/track", json={"number": "ADM-2026-99999"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Administrator endpoints
# ---------------------------------------------------------------------------
def test_admin_list_forbidden_for_student(client, app):
    api_register(client)
    assert client.get("/api/admin/applications").status_code == 403
    assert client.get("/api/admin/stats").status_code == 403


def test_admin_list_and_stats(client, app):
    api_register(client)
    _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.get("/api/admin/applications")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["applications"][0]["status"] == "submitted"

    stats = client.get("/api/admin/stats").get_json()["stats"]
    assert stats["submitted"] == 1
    assert stats["pending"] == 1


def test_admin_can_approve(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.patch(
        f"/api/admin/applications/{application['id']}/status",
        json={"status": "approved", "note": "Documents verified."},
    )
    assert resp.status_code == 200
    assert resp.get_json()["application"]["status"] == "approved"


def test_rejection_requires_note(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.patch(
        f"/api/admin/applications/{application['id']}/status", json={"status": "rejected"}
    )
    assert resp.status_code == 422
    assert "note" in resp.get_json()["errors"]


def test_student_cannot_change_status(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    resp = client.patch(
        f"/api/admin/applications/{application['id']}/status", json={"status": "approved"}
    )
    assert resp.status_code == 403


def test_invalid_status_transition_rejected(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.patch(
        f"/api/admin/applications/{application['id']}/status", json={"status": "draft"}
    )
    assert resp.status_code == 422


def test_admin_list_sort_and_pagination(client, app):
    api_register(client)
    for name in ["Zulu", "Alpha", "Mike"]:
        create_application(client, app, last_name=name)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    # Sort by last name, ascending.
    resp = client.get("/api/admin/applications?sort=last_name&order=asc")
    body = resp.get_json()
    assert [a["last_name"] for a in body["applications"]] == ["Alpha", "Mike", "Zulu"]
    assert body["total"] == 3
    assert body["pages"] == 1

    # Pagination over the same sorted set.
    resp = client.get("/api/admin/applications?sort=last_name&order=asc&per_page=2&page=2")
    body = resp.get_json()
    assert body["page"] == 2
    assert body["per_page"] == 2
    assert body["total"] == 3
    assert body["pages"] == 2
    assert len(body["applications"]) == 1
    assert body["applications"][0]["last_name"] == "Zulu"

    # An unknown sort column falls back to created_at instead of erroring.
    resp = client.get("/api/admin/applications?sort=email")
    assert resp.status_code == 200
    assert resp.get_json()["total"] == 3


def test_admin_list_search_and_status_filter(client, app):
    api_register(client)
    create_application(client, app, last_name="Needle")
    create_application(client, app, last_name="Haystack")
    _submitted_application(client, app)  # gains the "submitted" status
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.get("/api/admin/applications?status=submitted")
    assert resp.get_json()["total"] == 1

    resp = client.get("/api/admin/applications?q=Haystack")
    assert resp.get_json()["total"] == 1
    assert resp.get_json()["applications"][0]["last_name"] == "Haystack"

    resp = client.get("/api/admin/applications?status=bogus")
    assert resp.status_code == 400


def test_admin_list_date_filter(client, app):
    api_register(client)
    create_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert client.get(f"/api/admin/applications?from={today}&to={today}").get_json()["total"] == 1
    assert client.get("/api/admin/applications?from=2000-01-01&to=2000-01-02").get_json()["total"] == 0


def test_admin_detail_has_history_with_names(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    client.patch(
        f"/api/admin/applications/{application['id']}/status",
        json={"status": "approved", "note": "Documents verified."},
    )
    body = client.get(f"/api/admin/applications/{application['id']}").get_json()
    history = body["history"]
    assert history[0]["status"] == "approved"
    assert history[0]["changed_by_name"] == "API Admin"
    assert history[0]["changed_by_role"] == "admin"
    assert history[0]["note"] == "Documents verified."


def test_admin_course_create_update_toggle(client, app):
    api_register(client)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.post(
        "/api/admin/courses",
        json={
            "code": "MCA",
            "name": "Master of Computer Applications",
            "description": "Post-graduate programme.",
            "duration_years": 2,
            "seats_total": 30,
        },
    )
    assert resp.status_code == 201
    course = resp.get_json()["course"]
    assert course["code"] == "MCA"
    # New courses start active and appear in the public catalogue.
    assert course["is_active"] is True
    assert any(c["code"] == "MCA" for c in client.get("/api/courses").get_json()["courses"])

    resp = client.patch(f"/api/admin/courses/{course['id']}", json={"seats_total": 45})
    assert resp.status_code == 200
    assert resp.get_json()["course"]["seats_total"] == 45

    resp = client.post(f"/api/admin/courses/{course['id']}/toggle")
    assert resp.status_code == 200
    assert resp.get_json()["course"]["is_active"] is False

    resp = client.patch(f"/api/admin/courses/{course['id']}", json={"name": ""})
    assert resp.status_code == 422
    assert "name" in resp.get_json()["errors"]

    resp = client.delete(f"/api/admin/courses/{course['id']}")
    assert resp.status_code == 200
    assert all(
        c["code"] != "MCA"
        for c in client.get("/api/admin/courses").get_json()["courses"]
    )


def test_student_cannot_manage_courses(client, app):
    api_register(client)
    assert client.post(
        "/api/admin/courses",
        json={"code": "X", "name": "Nope", "duration_years": 1, "seats_total": 1},
    ).status_code == 403
    assert client.get("/api/admin/courses").status_code == 403
    assert client.post("/api/admin/courses/abc/toggle").status_code == 403
    assert client.delete("/api/admin/courses/abc").status_code == 403


def test_admin_course_validation(client, app):
    api_register(client)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.post(
        "/api/admin/courses",
        json={"code": "", "name": "", "duration_years": 99, "seats_total": 5000},
    )
    assert resp.status_code == 422
    errors = resp.get_json()["errors"]
    assert "code" in errors
    assert "name" in errors
    assert "duration_years" in errors
    assert "seats_total" in errors


def test_admin_creates_diploma_course_with_new_fields(client, app):
    api_register(client)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.post(
        "/api/admin/courses",
        json={
            "code": "DIP-MECH",
            "name": "Diploma in Mechanical Engineering",
            "description": "Three year diploma (demo).",
            "program_type": "diploma",
            "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
            "tuition_fee": 25000,
            "duration_years": 3,
            "seats_total": 60,
        },
    )
    assert resp.status_code == 201
    course = resp.get_json()["course"]
    assert course["program_type"] == "diploma"
    assert course["eligibility"].startswith("Pass in SSLC")
    assert float(course["tuition_fee"]) == 25000.0

    # The public catalogue can be filtered by programme type.
    diploma_codes = [c["code"] for c in client.get("/api/courses?program_type=diploma").get_json()["courses"]]
    degree_codes = [c["code"] for c in client.get("/api/courses?program_type=degree").get_json()["courses"]]
    assert "DIP-MECH" in diploma_codes
    assert "DIP-MECH" not in degree_codes
    assert "BTECH-CSE" in degree_codes
    assert "BTECH-CSE" not in diploma_codes


def test_admin_course_api_rejects_bad_program_type_and_fee(client, app):
    api_register(client)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.post(
        "/api/admin/courses",
        json={"code": "BAD", "name": "Bad", "program_type": "doctorate",
              "tuition_fee": -5, "duration_years": 3, "seats_total": 30},
    )
    assert resp.status_code == 422
    errors = resp.get_json()["errors"]
    assert "program_type" in errors
    assert "tuition_fee" in errors


def test_admin_course_list_includes_application_counts(client, app):
    api_register(client)
    _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    body = client.get("/api/admin/courses").get_json()
    assert body["courses"]
    for course in body["courses"]:
        assert "application_count" in course
    total = sum(c["application_count"] for c in body["courses"])
    assert total == 1


def test_admin_csv_export(client, app):
    api_register(client)
    application = _submitted_application(client, app)
    client.post("/api/auth/logout")

    email, password = make_admin(app)
    api_login(client, email=email, password=password)

    resp = client.get("/api/admin/export/applications.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    text = resp.get_data(as_text=True)
    assert "Application Number" in text
    assert application["application_number"] in text
    assert "Submitted" in text  # human-readable status label

    # Students are forbidden from downloading the report.
    client.post("/api/auth/logout")
    api_register(client, email="plain@example.com")
    assert client.get("/api/admin/export/applications.csv").status_code == 403


def test_admin_console_is_served(client):
    resp = client.get("/admin-console/")
    assert resp.status_code == 200
    assert b"text/html" in resp.content_type.encode() or "html" in resp.mimetype
    text = resp.get_data(as_text=True)
    assert "College Admission" in text or "dashboard" in text.lower()


def test_admin_console_flow_with_csrf_enabled():
    """Exercise exactly what the browser console does: bootstrap the CSRF
    token, sign in, manage courses, review applications, export CSV."""

    class CSRFConfig(TestConfig):
        API_CSRF_ENABLED = True

    application = create_app(CSRFConfig)
    fake = FakeSupabaseService()
    application.supabase = fake
    fake.create_course({"code": "BTECH-CSE", "name": "B.Tech CSE",
                        "description": "Test", "duration_years": 4, "seats_total": 60})
    fake.create_user(
        email="admin@csrfdemo.edu",
        password_hash=generate_password_hash("AdminPass1", method="scrypt"),
        full_name="CSRF Admin",
        role="admin",
    )
    client = application.test_client()
    headers = {"X-CSRF-Token": client.get("/api/auth/csrf").get_json()["csrf_token"]}

    # A state-changing request without the token is rejected.
    assert client.post("/api/admin/courses", json={"code": "X", "name": "Y"}).status_code == 403

    # Sign in (with the token) and reach the dashboard data.
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@csrfdemo.edu", "password": "AdminPass1"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert client.get("/api/admin/stats", headers=headers).get_json()["stats"]["total"] == 0

    # Create + update + toggle a course.
    resp = client.post(
        "/api/admin/courses",
        json={"code": "MCA", "name": "MCA", "duration_years": 2, "seats_total": 30},
        headers=headers,
    )
    assert resp.status_code == 201
    course = resp.get_json()["course"]
    assert client.patch(
        f"/api/admin/courses/{course['id']}", json={"seats_total": 40}, headers=headers
    ).get_json()["course"]["seats_total"] == 40
    assert client.post(
        f"/api/admin/courses/{course['id']}/toggle", headers=headers
    ).get_json()["course"]["is_active"] is False

    # The consoles for the CSV export and empty states.
    assert client.get("/api/admin/export/applications.csv", headers=headers).status_code == 200


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------
def test_csrf_required_when_enabled():
    class CSRFConfig(TestConfig):
        API_CSRF_ENABLED = True

    application = create_app(CSRFConfig)
    fake = FakeSupabaseService()
    application.supabase = fake
    fake.create_course(
        {"code": "BTECH-CSE", "name": "B.Tech CSE", "description": "Test",
         "duration_years": 4, "seats_total": 60}
    )
    client = application.test_client()

    payload = {
        "full_name": "CSRF Student",
        "email": "csrf@example.com",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
    }

    # Without a token the request is rejected.
    assert client.post("/api/auth/register", json=payload).status_code == 403

    # Fetch the token, then retry with the header.
    token = client.get("/api/auth/csrf").get_json()["csrf_token"]
    resp = client.post("/api/auth/register", json=payload, headers={"X-CSRF-Token": token})
    assert resp.status_code == 201
