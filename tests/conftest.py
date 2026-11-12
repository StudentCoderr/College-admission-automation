"""Pytest fixtures: a Flask test client wired to an in-memory fake Supabase."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from tests.fake_supabase import FakeSupabaseService  # noqa: E402


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    fake = FakeSupabaseService()
    application.supabase = fake
    # Seed a course used across tests.
    fake.create_course({"code": "BTECH-CSE", "name": "B.Tech CSE",
                        "description": "Test", "duration_years": 4, "seats_total": 60})
    application.config["FAKE"] = fake
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------
# Helper functions used by tests
# --------------------------------------------------------------------------
def register(client, email="student@example.com", password="StrongPass1",
             name="Test Student", first_name=None, middle_name=None, last_name=None):
    # Callers may pass a single legacy name string (split for the form) or the
    # individual parts.
    if first_name is None:
        parts = (name or "").split(None, 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""
    return client.post(
        "/register",
        data={
            "first_name": first_name,
            "middle_name": middle_name or "",
            "last_name": last_name or "",
            "email": email,
            "phone": "9876543210",
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=True,
    )


def login(client, email="student@example.com", password="StrongPass1"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def valid_application_payload(app, **overrides):
    course_id = app.supabase.list_courses()[0]["id"]
    payload = {
        "first_name": "Test",
        "last_name": "Applicant",
        "date_of_birth": "2004-05-15",
        "gender": "male",
        "category": "general",
        "nationality": "Indian",
        "email": "applicant@example.com",
        "phone": "9876543210",
        "address_line": "1 College Road",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560001",
        "country": "India",
        "qualifying_exam": "sslc",
        "board_university": "CBSE",
        "institution_name": "Sample School",
        "passing_year": "2023",
        "marks_obtained": "480",
        "marks_total": "500",
        "percentage": "",
        "course_id": course_id,
    }
    payload.update(overrides)
    return payload
