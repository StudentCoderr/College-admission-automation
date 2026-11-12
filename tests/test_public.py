"""Smoke tests that render every public page."""

import pytest


@pytest.mark.parametrize("path", ["/", "/courses", "/login", "/register"])
def test_public_pages_render(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert b"College Admission Portal" in resp.data


def test_unknown_page_returns_404_page(client):
    resp = client.get("/this-does-not-exist")
    assert resp.status_code == 404
    assert b"404" in resp.data


def test_course_detail_page_renders(client, app):
    course = app.supabase.list_courses()[0]
    resp = client.get(f"/courses/{course['id']}")
    assert resp.status_code == 200
    assert course["name"].encode() in resp.data
    assert b"Eligibility" in resp.data


def test_course_detail_hides_inactive_and_unknown(client, app):
    course = app.supabase.list_courses()[0]
    app.supabase.set_course_active(course["id"], False)
    assert client.get(f"/courses/{course['id']}").status_code == 404
    assert client.get("/courses/does-not-exist").status_code == 404


def test_course_listing_filters_by_program_type(client, app):
    app.supabase.create_course({
        "code": "DIP-CSE", "name": "Diploma in Computer Science and Engineering",
        "duration_years": 3, "seats_total": 60, "program_type": "diploma",
        "eligibility": "Pass in SSLC / Class 10.", "tuition_fee": 25000.0,
    })
    resp = client.get("/courses?program_type=diploma")
    assert resp.status_code == 200
    assert b"Diploma in Computer Science and Engineering" in resp.data
    assert b"B.Tech CSE" not in resp.data
