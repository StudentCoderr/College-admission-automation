"""Tests for the UI/UX enhancement pass.

Covers the public course-status filter, the student profile page, the admin
notifications action centre and the application date filters (list + CSV).
"""

from tests.conftest import register
from tests.test_admin_enhanced import admin_login, make_admin, submit_application


# ---------------------------------------------------------------------------
# Public landing page — admission totals stay private
# ---------------------------------------------------------------------------
def test_public_home_does_not_expose_admission_totals(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Registered students" not in resp.data
    assert b"Applications received" not in resp.data
    assert b"Admissions approved" not in resp.data
    # Public, non-sensitive information is still shown.
    assert b"active course" in resp.data
    assert b"Accepting applications now" in resp.data


def test_public_home_uses_swipe_carousels_and_quick_nav(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"home-jump" in resp.data
    assert b"data-carousel-track" in resp.data
    assert b"popular-track" in resp.data
    assert b"faq-track" in resp.data
    assert b"home.js" in resp.data


def test_student_login_and_register_use_split_auth_layout(client):
    for path, heading in (
        ("/login", b"Sign in to your account"),
        ("/register", b"Create your student account"),
    ):
        resp = client.get(path)
        assert resp.status_code == 200
        assert b"auth-page" in resp.data
        assert heading in resp.data


# ---------------------------------------------------------------------------
# Public course catalogue — status filter
# ---------------------------------------------------------------------------
def _add_closed_diploma_course(app):
    app.supabase.create_course(
        {
            "code": "DIP-MECH",
            "name": "Mechanical Engineering",
            "program_type": "diploma",
            "duration_years": 3,
            "seats_total": 60,
        }
    )
    diploma = app.supabase.list_courses(program_type="diploma")[0]
    app.supabase.set_course_active(diploma["id"], False)
    return diploma


def test_courses_hide_closed_courses_by_default(client, app):
    _add_closed_diploma_course(app)
    resp = client.get("/courses")
    assert resp.status_code == 200
    assert b"Mechanical Engineering" not in resp.data
    # The seeded active degree course is still shown.
    assert b"B.Tech CSE" in resp.data


def test_courses_status_all_includes_closed(client, app):
    _add_closed_diploma_course(app)
    resp = client.get("/courses?status=all")
    assert resp.status_code == 200
    assert b"Mechanical Engineering" in resp.data
    assert b"data-status=\"inactive\"" in resp.data
    # Closed courses must not advertise an apply action.
    assert b"Not accepting applications" in resp.data


def test_courses_status_filter_select_remembers_choice(client, app):
    _add_closed_diploma_course(app)
    resp = client.get("/courses?status=all")
    assert resp.status_code == 200
    assert b'id="course-status"' in resp.data
    assert b'value="all" selected' in resp.data


# ---------------------------------------------------------------------------
# Student profile page
# ---------------------------------------------------------------------------
def test_student_profile_page_renders(client, app):
    register(client, email="profile@example.com")
    resp = client.get("/student/profile")
    assert resp.status_code == 200
    assert b"My profile" in resp.data
    assert b"profile@example.com" in resp.data
    assert b"readonly-input" in resp.data


def test_student_profile_updates_name_and_phone(client, app):
    register(client, email="profile@example.com")
    resp = client.post(
        "/student/profile",
        data={
            "first_name": "  Ananya  ",
            "middle_name": "",
            "last_name": "Updated",
            "phone": "9911223344",
            "email": "profile@example.com",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"has been updated" in resp.data
    user = app.supabase.get_user_by_email("profile@example.com")
    assert user["first_name"] == "Ananya"
    assert user["middle_name"] is None
    assert user["last_name"] == "Updated"
    # Display name is rebuilt correctly when the middle name is empty.
    assert user["full_name"] == "Ananya Updated"
    assert user["phone"] == "9911223344"


def test_student_profile_cannot_change_email(client, app):
    register(client, email="profile@example.com")
    resp = client.post(
        "/student/profile",
        data={
            "first_name": "Ananya",
            "last_name": "Updated",
            "phone": "",
            "email": "hijacked@example.com",
        },
        follow_redirects=True,
    )
    assert b"cannot be changed" in resp.data
    assert app.supabase.get_user_by_email("profile@example.com") is not None
    assert app.supabase.get_user_by_email("hijacked@example.com") is None


def test_student_profile_rejects_blank_first_name(client, app):
    register(client, email="profile@example.com")
    resp = client.post(
        "/student/profile",
        data={"first_name": "   ", "last_name": "X", "phone": "", "email": "profile@example.com"},
        follow_redirects=True,
    )
    assert b"First name is required" in resp.data
    user = app.supabase.get_user_by_email("profile@example.com")
    assert user["full_name"] == "Test Student"


# ---------------------------------------------------------------------------
# Admin notifications action centre
# ---------------------------------------------------------------------------
def test_notifications_requires_admin(client, app):
    register(client, email="student@example.com")
    assert client.get("/admin/notifications").status_code == 403


def test_admin_notifications_lists_unverified_documents(client, app):
    make_admin(app)
    submit_application(client, app)
    admin_login(client)

    resp = client.get("/admin/notifications")
    assert resp.status_code == 200
    assert b"Notifications" in resp.data
    assert b"Documents awaiting verification" in resp.data
    assert b"Marks Card / Transcript" in resp.data
    # Pending stat counts the submitted application.
    assert b"In review / pending" in resp.data


def test_admin_notifications_drop_when_document_verified(client, app):
    make_admin(app)
    submit_application(client, app)
    admin_login(client)

    first = client.get("/admin/notifications")
    assert b"Unverified documents" in first.data

    app.supabase.set_document_verified(
        list(app.supabase.list_documents_all())[0]["id"], True
    )
    second = client.get("/admin/notifications")
    assert b"No documents awaiting verification" in second.data


def test_notifications_nav_item_present_in_admin_shell(client, app):
    make_admin(app)
    admin_login(client)
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 200
    assert b"Notifications" in resp.data
    assert b"/admin/notifications" in resp.data


# ---------------------------------------------------------------------------
# Application list + CSV export — date filters
# ---------------------------------------------------------------------------
def test_admin_applications_date_filters(client, app):
    make_admin(app)
    submit_application(client, app)
    admin_login(client)

    resp = client.get(
        "/admin/applications?status=submitted&date_from=2000-01-01&date_to=2099-12-31"
    )
    assert resp.status_code == 200
    assert b"application(s) found" in resp.data
    # The date inputs render with the submitted values preserved.
    assert b'id="date_from"' in resp.data
    assert b'id="date_to"' in resp.data


def test_admin_export_csv_with_date_filters(client, app):
    make_admin(app)
    submit_application(client, app)
    admin_login(client)

    resp = client.get(
        "/admin/export/applications.csv?status=submitted"
        "&date_from=2000-01-01&date_to=2099-12-31"
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    assert b"Application Number" in resp.data
    assert b"B.Tech CSE" in resp.data