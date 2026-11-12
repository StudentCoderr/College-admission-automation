"""Student application flow and ownership tests."""

import io

import pytest

from tests.conftest import login, register, valid_application_payload


def _start_draft(client, app):
    register(client, email="stu@example.com")
    resp = client.post("/student/apply", data=valid_application_payload(app), follow_redirects=True)
    assert resp.status_code == 200
    return app.supabase.list_applications()[0]


def test_student_cannot_open_admin_dashboard(client, app):
    register(client, email="stu2@example.com")
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 403


def test_create_draft_application(client, app):
    application = _start_draft(client, app)
    assert application["status"] == "draft"
    assert application["application_number"] is None
    # Percentage was auto-calculated server-side (480 / 500 = 96.0).
    assert float(application["percentage"]) == 96.0


def test_application_validation_blocks_bad_marks(client, app):
    register(client, email="badmarks@example.com")
    payload = valid_application_payload(app, marks_obtained="600", marks_total="500")
    resp = client.post("/student/apply", data=payload, follow_redirects=True)
    assert b"cannot exceed total marks" in resp.data
    assert app.supabase.list_applications() == []


def test_cannot_apply_for_inactive_course(client, app):
    course = app.supabase.list_courses()[0]
    app.supabase.set_course_active(course["id"], False)
    register(client, email="inactive@example.com")
    payload = valid_application_payload(app)  # points at the (now inactive) course
    resp = client.post("/student/apply", data=payload, follow_redirects=True)
    assert b"The selected course is not available." in resp.data
    assert app.supabase.list_applications() == []


def test_cannot_apply_for_nonexistent_course(client, app):
    register(client, email="nocourse@example.com")
    payload = valid_application_payload(app)
    payload["course_id"] = "11111111-1111-1111-1111-111111111111"
    resp = client.post("/student/apply", data=payload, follow_redirects=True)
    assert b"The selected course is not available." in resp.data
    assert app.supabase.list_applications() == []


def test_apply_form_lists_diploma_courses(client, app):
    app.supabase.create_course({
        "code": "DIP-CIVIL", "name": "Diploma in Civil Engineering",
        "duration_years": 3, "seats_total": 60, "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10.", "tuition_fee": 25000.0,
    })
    register(client, email="picker@example.com")
    resp = client.get("/student/apply")
    assert resp.status_code == 200
    assert b"Diploma in Civil Engineering" in resp.data
    assert b"data-course-search" in resp.data


def test_submit_requires_marks_card(client, app):
    application = _start_draft(client, app)
    resp = client.post(
        f"/student/application/{application['id']}/submit", follow_redirects=True
    )
    assert b"upload at least your marks card" in resp.data
    assert app.supabase.get_application(application["id"])["status"] == "draft"


def test_upload_and_submit_generates_application_number(client, app):
    application = _start_draft(client, app)
    resp = client.post(
        f"/student/application/{application['id']}/upload",
        data={
            "doc_type": "marks_card",
            "file": (io.BytesIO(b"%PDF-1.4 fake"), "marks.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Document uploaded successfully" in resp.data

    resp = client.post(
        f"/student/application/{application['id']}/submit", follow_redirects=True
    )
    submitted = app.supabase.get_application(application["id"])
    assert submitted["status"] == "submitted"
    assert submitted["application_number"].startswith("ADM-")
    assert b"Application submitted successfully" in resp.data


def test_upload_rejects_disallowed_extension(client, app):
    application = _start_draft(client, app)
    resp = client.post(
        f"/student/application/{application['id']}/upload",
        data={"doc_type": "marks_card", "file": (io.BytesIO(b"x"), "virus.exe")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Only PDF, JPG and PNG" in resp.data


def test_students_cannot_access_each_others_applications(client, app):
    application = _start_draft(client, app)
    application_id = application["id"]

    # Register and log in as a different student.
    client.post("/logout")
    register(client, email="other@example.com")

    resp = client.get(f"/student/application/{application_id}")
    assert resp.status_code == 404
