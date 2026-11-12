"""SSLC / PUC / ITI qualification support.

Covers the required-qualification dropdown, per-qualification field rules,
optional / "Not applicable" handling (stored as SQL NULL), backend field-scoped
errors, course eligibility validation (configured by admins, enforced at apply
time), legacy-schema degradation, profile/review display and the CSV export.
"""

import io

import pytest
from werkzeug.datastructures import MultiDict
from werkzeug.security import generate_password_hash

from app.services.application_service import validate_course_eligibility
from app.utils.validators import ValidationError, validate_application_form
from tests.conftest import login, register, valid_application_payload

COURSE_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _base_fields(**overrides):
    fields = {
        "first_name": "A",
        "last_name": "B",
        "date_of_birth": "2004-01-01",
        "gender": "female",
        "category": "general",
        "email": "a@b.com",
        "phone": "9876543210",
        "address_line": "Road",
        "city": "City",
        "state": "State",
        "postal_code": "560001",
        "course_id": COURSE_ID,
    }
    fields.update(overrides)
    return fields


def _valid_sslc(**overrides):
    fields = _base_fields(
        qualifying_exam="sslc",
        board_university="Karnataka SSLC Board",
        institution_name="Model High School",
        passing_year="2022",
    )
    fields.update(overrides)
    return MultiDict(fields)


def _valid_puc(**overrides):
    fields = _base_fields(
        qualifying_exam="puc",
        board_university="Karnataka PUC Board",
        institution_name="National College",
        stream="science",
        roll_number="PUC-2023-001",
        passing_year="2024",
    )
    fields.update(overrides)
    return MultiDict(fields)


def _valid_iti(**overrides):
    fields = _base_fields(
        qualifying_exam="iti",
        institution_name="Govt ITI Hubli",
        trade="Electrician",
        affiliation="ncvt",
        passing_year="2023",
    )
    fields.update(overrides)
    return MultiDict(fields)


def _make_admin(app, email="quals.admin@college.edu", password="AdminPass1"):
    app.supabase.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        full_name="Qualifications Admin",
        role="admin",
    )
    return email, password


def _submit(client, app, payload, email="candidate@example.com"):
    register(client, email=email)
    response = client.post("/student/apply", data=payload, follow_redirects=True)
    return response, app.supabase.list_applications()


# ---------------------------------------------------------------------------
# Validator: SSLC / PUC / ITI field rules
# ---------------------------------------------------------------------------
def test_sslc_requires_school_and_board():
    data = validate_application_form(_valid_sslc())
    assert data["qualifying_exam"] == "sslc"
    assert data["institution_name"] == "Model High School"
    assert data["school_name"] == "Model High School"  # legacy mirror
    assert data["board_university"] == "Karnataka SSLC Board"
    assert data["passing_year"] == 2022
    # Qualification-irrelevant fields are stored as SQL NULL.
    assert data["stream"] is None
    assert data["trade"] is None
    assert data["affiliation"] is None
    assert data["percentage"] is None  # no marks supplied


def test_sslc_stores_optional_roll_and_marks():
    data = validate_application_form(
        _valid_sslc(roll_number=" 12345 ", marks_obtained="480", marks_total="500")
    )
    assert data["roll_number"] == "12345"
    assert data["marks_obtained"] == 480.0
    assert data["percentage"] == 96.0


def test_sslc_missing_school_or_board_is_field_scoped():
    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_sslc(institution_name="", board_university=""))
    assert "institution_name" in exc.value.errors
    assert "board_university" in exc.value.errors
    # ITI-only fields are irrelevant for SSLC -> never validated.
    assert "trade" not in exc.value.errors
    assert "affiliation" not in exc.value.errors
    assert "stream" not in exc.value.errors


def test_puc_requires_stream_and_rejects_stream_na_as_null():
    data = validate_application_form(_valid_puc(stream="na"))
    assert data["stream"] is None  # never the literal string "na" / "null"
    assert data["roll_number"] == "PUC-2023-001"
    assert data["board_university"] == "Karnataka PUC Board"

    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_puc(stream=""))
    assert "stream" in exc.value.errors


def test_iti_requires_trade_but_not_board():
    data = validate_application_form(_valid_iti(affiliation="na"))
    assert data["trade"] == "Electrician"
    assert data["affiliation"] is None  # "na" == NULL
    assert data["board_university"] is None  # board is not applicable to ITI

    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_iti(trade=""))
    assert "trade" in exc.value.errors
    assert "board_university" not in exc.value.errors


def test_iti_rejects_invalid_affiliation():
    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_iti(affiliation="ivy-league"))
    assert "affiliation" in exc.value.errors


def test_switching_qualification_only_validates_new_fields():
    # Re-submitting as ITI must not re-raise the SSLC/PUC board requirement:
    # the board is stored NULL and the ITI-specific rules take over.
    data = validate_application_form(_valid_iti(board_university=""))
    assert data["qualifying_exam"] == "iti"
    assert data["board_university"] is None

    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_iti(board_university="", trade=""))
    assert "trade" in exc.value.errors
    assert "board_university" not in exc.value.errors


def test_invalid_qualification_is_rejected():
    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_sslc(qualifying_exam="Class 12"))
    assert "qualifying_exam" in exc.value.errors
    assert exc.value.errors["qualifying_exam"] != ""


def test_marks_optional_and_blank_becomes_null():
    data = validate_application_form(_valid_sslc(marks_obtained="", marks_total=""))
    assert data["marks_obtained"] is None
    assert data["marks_total"] is None
    assert data["percentage"] is None

    with pytest.raises(ValidationError) as exc:
        validate_application_form(_valid_sslc(marks_obtained="600", marks_total="500"))
    assert "marks_obtained" in exc.value.errors


# ---------------------------------------------------------------------------
# Course eligibility (admin-configured, enforced at apply time)
# ---------------------------------------------------------------------------
def test_course_without_eligibility_is_open_to_all(client, app):
    register(client, email="open@example.com")
    resp = client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="iti",
                                       institution_name="Tech ITI", trade="COPA"),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert app.supabase.list_applications()
    assert b"This course requires" not in resp.data


def test_course_blocks_ineligible_qualification_on_apply(client, app):
    course = app.supabase.list_courses()[0]
    app.supabase.update_course(course["id"], {"eligible_qualifications": ["puc"]})

    register(client, email="sslc@example.com")
    resp = client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="sslc"),
        follow_redirects=True,
    )
    assert b"PUC" in resp.data and b"not eligible" in resp.data
    assert app.supabase.list_applications() == []


def test_course_accepts_eligible_qualification_on_apply(client, app):
    course = app.supabase.list_courses()[0]
    app.supabase.update_course(course["id"], {"eligible_qualifications": ["puc"]})

    register(client, email="puc@example.com")
    resp = client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="puc",
                                       institution_name="City College", stream="science"),
        follow_redirects=True,
    )
    assert app.supabase.list_applications()
    assert b"This course requires" not in resp.data


def test_eligibility_validator_unit_rules(app):
    course_restricted = {"eligible_qualifications": ["puc", "iti"]}
    validate_course_eligibility(course_restricted, "iti")   # allowed
    validate_course_eligibility(course_restricted, "puc")   # allowed
    with pytest.raises(ValidationError):
        validate_course_eligibility(course_restricted, "sslc")
    validate_course_eligibility({"eligible_qualifications": None}, "sslc")
    validate_course_eligibility({"eligible_qualifications": []}, "sslc")
    # Legacy free-text rows are never blocked.
    validate_course_eligibility(course_restricted, "Class 12")


def test_admin_can_restrict_course_eligibility(client, app):
    email, password = _make_admin(app)
    login(client, email=email, password=password)
    resp = client.post(
        "/admin/courses/create",
        data={
            "code": "DIP-CSE", "name": "Diploma in CSE",
            "description": "Demo", "program_type": "diploma",
            "eligibility": "Pass in SSLC.", "duration_years": "3",
            "seats_total": "60", "eligible_qualifications": ["sslc", "puc"],
        },
        follow_redirects=True,
    )
    assert b"Course added" in resp.data
    course = next(c for c in app.supabase.list_courses() if c["code"] == "DIP-CSE")
    assert sorted(course["eligible_qualifications"]) == ["puc", "sslc"]


def test_api_admin_course_eligibility_roundtrip(client, app):
    from tests.test_api import api_login, make_admin

    make_admin(app, email="api.quals@example.com", password="AdminPass1")
    assert api_login(client, email="api.quals@example.com", password="AdminPass1").status_code == 200
    resp = client.post(
        "/api/admin/courses",
        json={
            "code": "DIP-ECE", "name": "Diploma in ECE",
            "duration_years": 3, "seats_total": 60, "program_type": "diploma",
            "eligible_qualifications": ["sslc"],
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["course"]["eligible_qualifications"] == ["sslc"]

    course = next(c for c in app.supabase.list_courses() if c["code"] == "DIP-ECE")
    client.patch(
        f"/api/admin/courses/{course['id']}",
        json={"eligible_qualifications": ["puc", "sslc"]},
    )
    assert sorted(app.supabase.get_course(course["id"])["eligible_qualifications"]) == ["puc", "sslc"]


# ---------------------------------------------------------------------------
# N/A selections and optional blanks are stored as SQL NULL end to end
# ---------------------------------------------------------------------------
def test_na_and_blanks_saved_as_null(client, app):
    register(client, email="nu@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(
            app,
            qualifying_exam="iti",
            institution_name="District ITI",
            trade="Fitter",
            affiliation="na",
            roll_number="",
            marks_obtained="",
            marks_total="",
        ),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]
    assert application["affiliation"] is None
    assert application["roll_number"] is None
    assert application["marks_obtained"] is None
    assert application["marks_total"] is None
    assert application["percentage"] is None
    # The literal strings must never reach the database.
    assert application["affiliation"] != "na"
    assert application["affiliation"] != "null"


# ---------------------------------------------------------------------------
# Legacy schema degradation (PGRST204 avoidance)
# ---------------------------------------------------------------------------
def test_legacy_applications_schema_ignores_new_columns(client, app):
    app.supabase.simulate_legacy_applications_schema()
    register(client, email="legacy@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="puc",
                                       institution_name="Old College",
                                       stream="science"),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]
    assert application["qualifying_exam"] == "puc"
    # The migrated columns are simply not written (no PGRST204 blow-up).
    assert "institution_name" not in application
    assert application["school_name"] == "Old College"


# ---------------------------------------------------------------------------
# Profile + admin review display
# ---------------------------------------------------------------------------
def test_student_profile_shows_saved_qualification_details(client, app):
    register(client, email="view@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="puc",
                                       institution_name="City College",
                                       stream="science", roll_number="R-77"),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]
    resp = client.get(f"/student/application/{application['id']}")
    assert resp.status_code == 200
    assert b"PUC" in resp.data
    assert b"College name" in resp.data
    assert b"City College" in resp.data
    assert b"Science" in resp.data
    assert b"R-77" in resp.data
    # ITI-only rows must not appear for a PUC application.
    assert b"Trade / specialization" not in resp.data


def test_admin_review_and_list_show_qualification_details(client, app):
    register(client, email="review@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="iti",
                                       institution_name="Govt ITI",
                                       trade="Electrician", affiliation="ncvt"),
        follow_redirects=True,
    )
    application = app.supabase.list_applications()[0]

    email, password = _make_admin(app)
    client.post("/logout")
    login(client, email=email, password=password)

    detail = client.get(f"/admin/application/{application['id']}")
    assert detail.status_code == 200
    assert b"ITI" in detail.data
    assert b"ITI institute name" in detail.data
    assert b"Govt ITI" in detail.data
    assert b"Electrician" in detail.data
    assert b"NCVT" in detail.data
    # Board is not applicable to ITI -> hidden on the review page too.
    assert b"Karnataka PUC Board" not in detail.data

    listing = client.get("/admin/applications")
    assert listing.status_code == 200
    assert b"ITI" in listing.data


def test_csv_export_contains_qualification_columns(client, app):
    register(client, email="csv@example.com")
    client.post(
        "/student/apply",
        data=valid_application_payload(app, qualifying_exam="puc",
                                       institution_name="Commerce College",
                                       stream="commerce", roll_number="R-9"),
        follow_redirects=True,
    )
    client.post("/logout")

    email, password = _make_admin(app)
    login(client, email=email, password=password)
    resp = client.get("/admin/export/applications.csv")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    for header in ("Institution", "Stream", "Trade", "Affiliation", "Roll Number"):
        assert header in text
    assert "Commerce College" in text
    assert "commerce" in text
    assert "R-9" in text


# ---------------------------------------------------------------------------
# API serialization of the new fields
# ---------------------------------------------------------------------------
def test_api_serializes_qualification_fields(client, app):
    resp = client.post("/api/auth/register", json={
        "full_name": "API Qual Student",
        "email": "api.qual@example.com",
        "phone": "9876543210",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
    })
    assert resp.status_code == 201
    course_id = app.supabase.list_courses()[0]["id"]

    created = client.post("/api/applications", json=valid_application_payload(
        app, qualifying_exam="iti", institution_name="Model ITI",
        trade="Mechanic", affiliation="scvt", roll_number="ITI-9",
    ))
    assert created.status_code == 201
    created_body = created.get_json()["application"]
    assert created_body["qualifyingExam"] == "iti"
    assert created_body["institutionName"] == "Model ITI"
    assert created_body["trade"] == "Mechanic"
    assert created_body["affiliation"] == "scvt"
    assert created_body["rollNumber"] == "ITI-9"
    assert course_id  # payload course_id is used


# ---------------------------------------------------------------------------
# Course catalogue pages advertise eligibility
# ---------------------------------------------------------------------------
def test_course_pages_advertise_eligible_qualifications(client, app):
    course = app.supabase.list_courses()[0]
    app.supabase.update_course(course["id"], {"eligible_qualifications": ["puc"]})

    listing = client.get("/courses")
    assert b"Eligible for:" in listing.data
    assert b"PUC" in listing.data

    detail = client.get(f"/courses/{course['id']}")
    assert b"Eligible for" in detail.data
    assert b"PUC" in detail.data

    # A course with no restriction advertises "open to all".
    open_course = app.supabase.create_course({
        "code": "DIP-OPEN", "name": "Open Diploma", "duration_years": 3,
        "seats_total": 30, "program_type": "diploma",
    })
    open_page = client.get(f"/courses/{open_course['id']}")
    assert b"All qualifications" in open_page.data