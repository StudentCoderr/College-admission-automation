"""Unit tests for the server-side validators."""

from werkzeug.datastructures import MultiDict

from app.utils.validators import (
    ValidationError,
    is_valid_email,
    is_valid_phone,
    validate_application_form,
    validate_password,
)


def test_email_validation():
    assert is_valid_email("a@b.com")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("")


def test_phone_validation():
    assert is_valid_phone("9876543210")
    assert is_valid_phone("+91 98765-43210")
    assert not is_valid_phone("abc")


def test_password_rules():
    assert validate_password("StrongPass1") is None
    assert validate_password("short") is not None
    assert validate_password("allletters") is not None
    assert validate_password("12345678") is not None


def test_application_form_calculates_percentage():
    form = MultiDict(
        {
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
            "qualifying_exam": "sslc",
            "board_university": "CBSE",
            "institution_name": "Sample School",
            "passing_year": "2023",
            "marks_obtained": "450",
            "marks_total": "500",
            "course_id": "11111111-1111-1111-1111-111111111111",
        }
    )
    data = validate_application_form(form)
    assert data["percentage"] == 90.0
    assert data["course_id"] == "11111111-1111-1111-1111-111111111111"


def test_application_form_reports_errors():
    form = MultiDict(
        {
            "first_name": "",
            "last_name": "",
            "date_of_birth": "2999-01-01",
            "gender": "invalid",
            "email": "bad",
            "phone": "abc",
            "address_line": "",
            "city": "",
            "state": "",
            "postal_code": "",
            "qualifying_exam": "",
            "board_university": "",
            "passing_year": "1800",
            "marks_obtained": "10",
            "marks_total": "5",
            "course_id": "",
        }
    )
    try:
        validate_application_form(form)
        assert False, "Expected ValidationError"
    except ValidationError as exc:
        assert "first_name" in exc.errors
        assert "email" in exc.errors
        assert "course_id" in exc.errors
        assert "date_of_birth" in exc.errors
        # Qualification is compulsory; board only matters once a valid
        # qualification has been chosen (field-scoped errors).
        assert "qualifying_exam" in exc.errors
        assert "board_university" not in exc.errors


def _valid_application_form(**overrides):
    """A complete, valid SSLC application form with optional overrides."""
    data = {
        "first_name": "Ananya",
        "middle_name": "",
        "last_name": "Sharma",
        "date_of_birth": "2004-05-15",
        "gender": "female",
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
        "marks_obtained": "450",
        "marks_total": "500",
        "course_id": "11111111-1111-1111-1111-111111111111",
    }
    data.update(overrides)
    return MultiDict(data)


def test_application_form_normalises_names_and_nulls_optionals():
    data = validate_application_form(
        _valid_application_form(first_name="  Ananya  ", middle_name="  Priya ", last_name="")
    )
    assert data["first_name"] == "Ananya"
    assert data["middle_name"] == "Priya"
    # An empty optional name is stored as SQL NULL, never an empty string.
    assert data["last_name"] is None


def test_application_form_requires_only_first_name():
    data = validate_application_form(
        _valid_application_form(first_name="Ananya", middle_name="", last_name="")
    )
    assert data["first_name"] == "Ananya"
    assert data["middle_name"] is None
    assert data["last_name"] is None


def test_application_form_rejects_missing_first_name_but_allows_no_last():
    form = _valid_application_form(first_name="   ", middle_name="Priya", last_name="")
    try:
        validate_application_form(form)
        assert False, "Expected ValidationError"
    except ValidationError as exc:
        assert exc.errors["first_name"] == "First name is required."
        # Last name is optional and must never be flagged.
        assert "last_name" not in exc.errors
