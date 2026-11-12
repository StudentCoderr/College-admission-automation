"""Secure, idempotent provisioning of the initial administrator (create-admin).

Covers: environment-variable driven creation, scrypt hashing (never plain
text), no password echo, idempotent re-runs (no duplicates, no accidental
password overwrite), explicit password rotation (--reset-password), promoting
an existing student without hijacking its credentials, validation failures,
interactive fallback prompts, and a clear error when Supabase is unconfigured.
"""

import pytest
from werkzeug.security import check_password_hash

ADMIN_EMAIL = "admin34@edu.in"
PASSWORD_A = "Admin$123"
PASSWORD_B = "Rotated$456"


def _count_admins_with_email(app, email=ADMIN_EMAIL):
    users = app.config["FAKE"].users
    return sum(1 for row in users.values() if row.get("email") == email)


def _invoke(app, monkeypatch, *args, env=None, input=None):
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    return app.test_cli_runner().invoke(
        args=["create-admin", *args], input=input
    )


def _create_via_cli(app, monkeypatch, password=PASSWORD_A, extra_args=()):
    return _invoke(
        app,
        monkeypatch,
        *extra_args,
        env={
            "ADMIN_EMAIL": ADMIN_EMAIL,
            "ADMIN_FULL_NAME": "System Administrator",
            "ADMIN_PASSWORD": password,
        },
    )


# ---------------------------------------------------------------------------
# Fresh creation
# ---------------------------------------------------------------------------
def test_create_admin_creates_account_and_never_prints_password(app, monkeypatch):
    result = _create_via_cli(app, monkeypatch)

    assert result.exit_code == 0, result.output
    assert f"Created administrator account {ADMIN_EMAIL}" in result.output
    assert PASSWORD_A not in result.output

    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    assert row is not None
    assert row["role"] == "admin"
    assert row["password_hash"] != PASSWORD_A  # never stored in plain text
    assert check_password_hash(row["password_hash"], PASSWORD_A)
    assert row["is_active"] is True


def test_create_admin_uses_configured_email_and_full_name(app, monkeypatch):
    result = _create_via_cli(app, monkeypatch)

    assert result.exit_code == 0, result.output
    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    assert row["full_name"] == "System Administrator"
    assert row["first_name"] == "System"
    assert row["last_name"] == "Administrator"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_create_admin_rerun_is_a_noop_that_keeps_original_password(app, monkeypatch):
    first = _create_via_cli(app, monkeypatch, password=PASSWORD_A)
    assert first.exit_code == 0

    second = _invoke(
        app,
        monkeypatch,
        env={"ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASSWORD": PASSWORD_B},
    )
    assert second.exit_code == 0, second.output
    assert "already exists" in second.output
    assert "no changes made" in second.output

    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    # The original password still works; the new one was NOT applied.
    assert check_password_hash(row["password_hash"], PASSWORD_A)
    assert not check_password_hash(row["password_hash"], PASSWORD_B)
    assert row["role"] == "admin"
    # No duplicate account was created across all invocations.
    assert _count_admins_with_email(app) == 1


def test_create_admin_reset_password_rotates_hash(app, monkeypatch):
    first = _create_via_cli(app, monkeypatch, password=PASSWORD_A)
    assert first.exit_code == 0

    result = _invoke(
        app,
        monkeypatch,
        "--reset-password",
        env={"ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASSWORD": PASSWORD_B},
    )
    assert result.exit_code == 0, result.output
    assert "Password rotated" in result.output
    assert PASSWORD_B not in result.output

    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    assert check_password_hash(row["password_hash"], PASSWORD_B)
    assert not check_password_hash(row["password_hash"], PASSWORD_A)
    assert row["role"] == "admin"
    assert _count_admins_with_email(app) == 1


# ---------------------------------------------------------------------------
# Promoting an existing (non-admin) user
# ---------------------------------------------------------------------------
def test_create_admin_promotes_student_without_changing_its_password(app, monkeypatch):
    from werkzeug.security import generate_password_hash

    app.supabase.create_user(
        email=ADMIN_EMAIL,
        password_hash=generate_password_hash("StudentPass1", method="scrypt"),
        full_name="Existing Student",
        role="student",
    )

    result = _invoke(
        app,
        monkeypatch,
        env={"ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASSWORD": PASSWORD_A},
    )
    assert result.exit_code == 0, result.output
    assert "Granted the administrator role" in result.output
    assert "password was left unchanged" in result.output

    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    assert row["role"] == "admin"
    # The student's own password still works; the CLI password was NOT applied.
    assert check_password_hash(row["password_hash"], "StudentPass1")
    assert not check_password_hash(row["password_hash"], PASSWORD_A)
    assert _count_admins_with_email(app) == 1


def test_create_admin_promote_with_reset_also_rotates_password(app, monkeypatch):
    from werkzeug.security import generate_password_hash

    user = app.supabase.create_user(
        email=ADMIN_EMAIL,
        password_hash=generate_password_hash("StudentPass1", method="scrypt"),
        full_name="Existing Student",
        role="student",
    )
    result = _invoke(
        app,
        monkeypatch,
        "--reset-password",
        env={"ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASSWORD": PASSWORD_A},
    )
    assert result.exit_code == 0, result.output
    assert "and rotated its password" in result.output

    row = app.supabase.get_user_by_id(user["id"])
    assert row["role"] == "admin"
    assert check_password_hash(row["password_hash"], PASSWORD_A)
    assert not check_password_hash(row["password_hash"], "StudentPass1")


# ---------------------------------------------------------------------------
# Validation and safe failure
# ---------------------------------------------------------------------------
def test_create_admin_rejects_invalid_email(app, monkeypatch):
    result = _invoke(
        app,
        monkeypatch,
        env={"ADMIN_EMAIL": "not-an-email", "ADMIN_PASSWORD": PASSWORD_A},
    )
    assert result.exit_code != 0
    assert "Invalid administrator email" in result.output
    assert app.supabase.get_user_by_email("not-an-email") is None


def test_create_admin_rejects_weak_password(app, monkeypatch):
    result = _invoke(
        app,
        monkeypatch,
        env={
            "ADMIN_EMAIL": ADMIN_EMAIL,
            "ADMIN_FULL_NAME": "System Administrator",
            "ADMIN_PASSWORD": "short",
        },
    )
    assert result.exit_code != 0
    assert "at least 8 characters" in result.output
    assert app.supabase.get_user_by_email(ADMIN_EMAIL) is None


def test_create_admin_fails_cleanly_when_supabase_unconfigured(app, monkeypatch):
    from tests.fake_supabase import FakeSupabaseService

    monkeypatch.setattr(FakeSupabaseService, "is_configured", property(lambda self: False))
    result = _invoke(
        app,
        monkeypatch,
        env={"ADMIN_EMAIL": ADMIN_EMAIL, "ADMIN_PASSWORD": PASSWORD_A},
    )
    assert result.exit_code != 0
    assert "Supabase is not configured" in result.output
    assert PASSWORD_A not in result.output


# ---------------------------------------------------------------------------
# Interactive fallback prompts (password via hidden input, never echoed)
# ---------------------------------------------------------------------------
def test_create_admin_prompts_when_env_variables_missing(app, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ADMIN_FULL_NAME", "System Administrator")
    # No ADMIN_PASSWORD -> hidden confirmation prompt consumes two lines.
    result = _invoke(
        app,
        monkeypatch,
        input=f"{PASSWORD_A}\n{PASSWORD_A}\n",
    )
    assert result.exit_code == 0, result.output
    assert f"Created administrator account {ADMIN_EMAIL}" in result.output
    assert PASSWORD_A not in result.output

    row = app.supabase.get_user_by_email(ADMIN_EMAIL)
    assert row["role"] == "admin"
    assert check_password_hash(row["password_hash"], PASSWORD_A)


# ---------------------------------------------------------------------------
# End-to-end: the provisioned account logs in, students stay locked out
# ---------------------------------------------------------------------------
def test_created_admin_signs_in_via_admin_login_and_reaches_dashboard(
    app, client, monkeypatch
):
    result = _create_via_cli(app, monkeypatch)
    assert result.exit_code == 0, result.output

    resp = client.post(
        "/admin/login",
        data={"email": ADMIN_EMAIL, "password": PASSWORD_A},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"does not have administrator access" not in resp.data
    assert b"Dashboard" in resp.data

    # The wrong password is refused with the generic message.
    client.post("/logout")
    resp = client.post(
        "/admin/login",
        data={"email": ADMIN_EMAIL, "password": "wrong-password"},
        follow_redirects=True,
    )
    assert b"Invalid email or password" in resp.data


def test_provisioned_admin_portal_is_closed_to_students(app, client, monkeypatch):
    from tests.conftest import register

    result = _create_via_cli(app, monkeypatch)
    assert result.exit_code == 0, result.output

    # An ordinary student (created through public registration, role=student)
    # cannot open admin pages even when already signed in.
    register(client, email="student-blocked@example.com", password="StrongPass1")
    assert client.get("/admin/dashboard").status_code == 403

    # And the dedicated admin login refuses student accounts outright.
    client.post("/logout")
    resp = client.post(
        "/admin/login",
        data={"email": "student-blocked@example.com", "password": "StrongPass1"},
        follow_redirects=True,
    )
    assert b"does not have administrator access" in resp.data