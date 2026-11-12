"""Destructive `reset-project` command.

The command must require an explicit confirmation, remove every member and all
related data (including uploaded files), and then create a fresh administrator
whose password is never printed or stored in plain text.
"""

from werkzeug.security import check_password_hash

NEW_EMAIL = "fresh.admin@example.com"
NEW_PASSWORD = "FreshAdmin1"


def _seed_old_data(app):
    fake = app.config["FAKE"]
    admin = fake.create_user(
        email="old.admin@example.com",
        password_hash="old-hash",
        full_name="Old Administrator",
        role="admin",
    )
    student = fake.create_user(
        email="old.student@example.com",
        password_hash="old-hash",
        full_name="Old Student",
        role="student",
    )
    application = fake.create_application(
        student["id"],
        {
            "first_name": "Old",
            "last_name": "Student",
            "email": "old.student@example.com",
            "course_id": fake.list_courses()[0]["id"],
            "date_of_birth": "2004-05-15",
            "gender": "male",
            "category": "general",
            "nationality": "Indian",
            "phone": "9876543210",
            "address_line": "1 Old Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "qualifying_exam": "puc",
            "board_university": "CBSE",
            "school_name": "Old School",
            "passing_year": "2023",
            "marks_obtained": "480",
            "marks_total": "500",
            "percentage": "96",
        },
    )
    fake.add_status_history(application["id"], "draft", "Started", student["id"])
    fake.upload_document("applications/old/marks.pdf", b"old", "application/pdf")
    fake.create_document(
        application["id"],
        student["id"],
        "marks_card",
        file_name="marks.pdf",
        storage_path="applications/old/marks.pdf",
        mime_type="application/pdf",
        size_bytes=3,
    )
    fake.add_audit_log(
        action="admin_login",
        actor_id=admin["id"],
        actor_email=admin["email"],
    )
    return fake


def _invoke(app, *args, input=None, env=None, monkeypatch=None):
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    return app.test_cli_runner().invoke(args=["reset-project", *args], input=input)


def test_reset_project_aborts_without_typed_confirmation(app, monkeypatch):
    fake = _seed_old_data(app)

    result = _invoke(app, input="no\n", monkeypatch=monkeypatch)

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert len(fake.users) == 2
    assert len(fake.courses) == 1
    assert len(fake.applications) == 1
    assert len(fake.storage) == 1


def test_invalid_new_admin_does_not_delete_existing_data(app, monkeypatch):
    fake = _seed_old_data(app)

    result = _invoke(
        app,
        input="RESET\nnot-an-email\n",
        monkeypatch=monkeypatch,
    )

    assert result.exit_code != 0
    assert "Nothing was deleted" in result.output
    assert len(fake.users) == 2
    assert len(fake.courses) == 1
    assert len(fake.applications) == 1


def test_reset_project_clears_everything_and_creates_admin(app, monkeypatch):
    fake = _seed_old_data(app)

    result = _invoke(
        app,
        "--yes",
        env={
            "ADMIN_EMAIL": NEW_EMAIL,
            "ADMIN_FULL_NAME": "Fresh Administrator",
            "ADMIN_PASSWORD": NEW_PASSWORD,
        },
        monkeypatch=monkeypatch,
    )

    assert result.exit_code == 0, result.output
    assert "Removed" in result.output
    assert f"Created administrator account {NEW_EMAIL}" in result.output
    assert NEW_PASSWORD not in result.output

    # Every old member and all related data is gone.
    assert len(fake.users) == 1
    assert fake.get_user_by_email("old.admin@example.com") is None
    assert fake.get_user_by_email("old.student@example.com") is None
    assert fake.courses == {}
    assert fake.applications == {}
    assert fake.documents == {}
    assert fake.history == {}
    assert fake.audit == []
    assert fake.storage == {}

    admin = fake.get_user_by_email(NEW_EMAIL)
    assert admin["role"] == "admin"
    assert admin["full_name"] == "Fresh Administrator"
    assert admin["password_hash"] != NEW_PASSWORD
    assert check_password_hash(admin["password_hash"], NEW_PASSWORD)


def test_reset_project_asks_for_new_admin_interactively(app, monkeypatch):
    _seed_old_data(app)

    result = app.test_cli_runner().invoke(
        args=["reset-project"],
        input=(
            "RESET\n"
            f"{NEW_EMAIL}\n"
            "Fresh Administrator\n"
            f"{NEW_PASSWORD}\n"
            f"{NEW_PASSWORD}\n"
        ),
    )

    assert result.exit_code == 0, result.output
    assert f"Created administrator account {NEW_EMAIL}" in result.output
    assert NEW_PASSWORD not in result.output
    assert app.supabase.get_user_by_email(NEW_EMAIL)["role"] == "admin"


def test_reset_project_fails_cleanly_when_supabase_unconfigured(app, monkeypatch):
    from tests.fake_supabase import FakeSupabaseService

    monkeypatch.setattr(
        FakeSupabaseService, "is_configured", property(lambda self: False)
    )
    result = _invoke(app, "--yes", monkeypatch=monkeypatch)

    assert result.exit_code != 0
    assert "Supabase is not configured" in result.output


def test_new_admin_can_sign_in_after_reset(app, client, monkeypatch):
    _seed_old_data(app)

    _invoke(
        app,
        "--yes",
        env={
            "ADMIN_EMAIL": NEW_EMAIL,
            "ADMIN_FULL_NAME": "Fresh Administrator",
            "ADMIN_PASSWORD": NEW_PASSWORD,
        },
        monkeypatch=monkeypatch,
    )

    resp = client.post(
        "/admin/login",
        data={"email": NEW_EMAIL, "password": NEW_PASSWORD},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data
