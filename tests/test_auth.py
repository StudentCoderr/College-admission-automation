"""Authentication and access-control tests."""

from tests.conftest import login, register


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_register_creates_student_and_logs_in(client):
    resp = register(client)
    assert resp.status_code == 200
    # Redirected to the student dashboard.
    assert b"My Applications" in resp.data or b"Welcome" in resp.data


def test_register_rejects_weak_password(client):
    resp = client.post(
        "/register",
        data={
            "first_name": "Weak Person",
            "email": "weak@example.com",
            "password": "short",
            "confirm_password": "short",
        },
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data


def test_register_rejects_duplicate_email(client, app):
    register(client, email="dup@example.com")
    client.post("/logout")
    resp = client.post(
        "/register",
        data={
            "first_name": "Dup",
            "email": "dup@example.com",
            "password": "StrongPass1",
            "confirm_password": "StrongPass1",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.data


def test_login_rejects_wrong_password(client):
    register(client, email="login@example.com")
    client.post("/logout")
    resp = login(client, email="login@example.com", password="WrongPass9")
    assert b"Invalid email or password" in resp.data


def test_login_success(client):
    register(client, email="ok@example.com")
    client.post("/logout")
    resp = login(client, email="ok@example.com", password="StrongPass1")
    assert resp.status_code == 200
    assert b"Logout" in resp.data


def test_anonymous_redirected_from_dashboard(client):
    resp = client.get("/student/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
