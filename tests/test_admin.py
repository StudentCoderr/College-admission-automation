"""Administrator workflow tests: dashboard, review, courses, CSV export."""

import io

from werkzeug.security import generate_password_hash

from tests.conftest import login, register, valid_application_payload


def _make_admin(app, email="admin@college.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Admin User",
        role="admin",
    )
    return email, password


def _submitted_application(client, app):
    register(client, email="candidate@example.com")
    client.post("/student/apply", data=valid_application_payload(app), follow_redirects=True)
    application = app.supabase.list_applications()[0]
    client.post(
        f"/student/application/{application['id']}/upload",
        data={"doc_type": "marks_card", "file": (io.BytesIO(b"%PDF-1.4"), "m.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    client.post(f"/student/application/{application['id']}/submit", follow_redirects=True)
    client.post("/logout")
    return app.supabase.get_application(application["id"])


def test_admin_dashboard_shows_counts(client, app):
    _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"Admissions dashboard" in resp.data
    assert b"Total applications" in resp.data


def test_admin_can_approve_application(client, app):
    application = _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        f"/admin/application/{application['id']}/status",
        data={"status": "approved", "note": "Verified documents."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert app.supabase.get_application(application["id"])["status"] == "approved"


def test_rejection_requires_note(client, app):
    application = _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        f"/admin/application/{application['id']}/status",
        data={"status": "rejected", "note": ""},
        follow_redirects=True,
    )
    assert b"note is required" in resp.data
    assert app.supabase.get_application(application["id"])["status"] == "submitted"


def test_admin_search_and_filter(client, app):
    _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.get("/admin/applications?status=submitted&q=applicant")
    assert resp.status_code == 200
    assert b"ADM-" in resp.data

    resp = client.get("/admin/applications?status=approved")
    assert b"No applications match" in resp.data


def test_csv_export(client, app):
    _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.get("/admin/export/applications.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"Application Number" in resp.data
    assert b"ADM-" in resp.data


def test_course_management(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        "/admin/courses/create",
        data={"code": "MBA", "name": "Master of Business Administration",
              "duration_years": "2", "seats_total": "40"},
        follow_redirects=True,
    )
    assert b"Course added" in resp.data
    codes = {c["code"] for c in app.supabase.list_courses()}
    assert "MBA" in codes

    target = next(c for c in app.supabase.list_courses() if c["code"] == "MBA")
    client.post(f"/admin/courses/{target['id']}/toggle", follow_redirects=True)
    assert app.supabase.get_course(target["id"])["is_active"] is False

    resp = client.post(
        f"/admin/courses/{target['id']}/delete", follow_redirects=True
    )
    assert b"Course MBA deleted" in resp.data
    assert app.supabase.get_course(target["id"]) is None


def test_course_with_applications_cannot_be_deleted(client, app):
    application = _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    course_id = application["course_id"]
    resp = client.post(
        f"/admin/courses/{course_id}/delete", follow_redirects=True
    )
    assert b"cannot be deleted" in resp.data
    assert app.supabase.get_course(course_id) is not None


def test_student_cannot_manage_courses(client, app):
    register(client, email="noperm@example.com")
    resp = client.post(
        "/admin/courses/create",
        data={"code": "X", "name": "Nope", "duration_years": "2", "seats_total": "10"},
    )
    assert resp.status_code == 403


def test_admin_can_create_diploma_course(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        "/admin/courses/create",
        data={
            "code": "DIP-CSE",
            "name": "Diploma in Computer Science and Engineering",
            "description": "Three year diploma (demo).",
            "program_type": "diploma",
            "eligibility": "Pass in SSLC / Class 10 with Mathematics and Science.",
            "tuition_fee": "25000",
            "duration_years": "3",
            "seats_total": "60",
        },
        follow_redirects=True,
    )
    assert b"Course added" in resp.data

    course = next(c for c in app.supabase.list_courses() if c["code"] == "DIP-CSE")
    assert course["program_type"] == "diploma"
    assert course["eligibility"].startswith("Pass in SSLC")
    assert float(course["tuition_fee"]) == 25000.0
    assert course["duration_years"] == 3


def test_admin_course_rejects_bad_program_type(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        "/admin/courses/create",
        data={"code": "BAD", "name": "Bad type", "program_type": "doctorate",
              "duration_years": "3", "seats_total": "10"},
        follow_redirects=True,
    )
    assert b"Programme type must be Degree or Diploma" in resp.data
    assert all(c["code"] != "BAD" for c in app.supabase.list_courses())


def test_admin_course_rejects_negative_fee(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)

    resp = client.post(
        "/admin/courses/create",
        data={"code": "NEGFEE", "name": "Negative fee", "program_type": "diploma",
              "tuition_fee": "-100", "duration_years": "3", "seats_total": "10"},
        follow_redirects=True,
    )
    assert b"cannot be negative" in resp.data
    assert all(c["code"] != "NEGFEE" for c in app.supabase.list_courses())


def test_admin_dashboard_groups_applications_by_course(client, app):
    _submitted_application(client, app)
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"Applications by course" in resp.data
    assert b"Available seats" in resp.data
