"""Server-side input validation helpers.

Every value that reaches the database passes through these helpers so that
malformed or malicious input is rejected before it is used in a query.
"""

import re
from datetime import date, datetime

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{7,20}$")


class ValidationError(Exception):
    """Raised when a payload fails validation."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"_form": errors}
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


def clean_str(value, max_length=None) -> str:
    """Trim a string and strip control characters. Returns '' for None."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    if max_length is not None:
        text = text[:max_length]
    return text


# ---------------------------------------------------------------------------
# Name handling
#
# Student names are stored as three separate columns -- first_name (required),
# middle_name (optional) and last_name (optional). full_name is maintained as
# a denormalised display column (never-null) so legacy screens and audit
# records keep working; it is rebuilt from the parts on every write.
# ---------------------------------------------------------------------------
def clean_name(value, max_length=120) -> str:
    """Trim a name and collapse runs of internal whitespace to one space."""
    text = clean_str(value, max_length)
    return re.sub(r"\s+", " ", text).strip()


def split_full_name(full_name):
    """Best-effort split of a legacy single "full name" string into parts.

    ``"Ananya Sharma"`` -> (Ananya, None, Sharma)
    ``"Ananya B Sharma"`` -> (Ananya, B, Sharma)
    ``"Ananya"`` -> (Ananya, None, None)
    Returns ``(None, None, None)`` for blank input.
    """
    parts = [p for p in clean_name(full_name).split(" ") if p]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def format_display_name(first_name, middle_name=None, last_name=None, fallback=""):
    """Join the present name parts into a display string.

    ``format_display_name("Ananya", None, "Sharma")`` -> ``"Ananya Sharma"``.
    When every part is empty the ``fallback`` value (e.g. a legacy
    ``full_name`` column) is returned so old rows never render blank.
    """
    parts = [p for p in (first_name, middle_name, last_name) if p]
    display = " ".join(parts).strip()
    return display or (fallback or "")


def validate_names(first_name=None, middle_name=None, last_name=None) -> tuple:
    """Validate the three name fields. Returns ``((first, middle, last), errors)``.

    Only the first name is compulsory; it must not be empty or whitespace-only.
    Optional names may be empty and are normalised to ``None`` (SQL NULL).
    """
    first = clean_name(first_name) or None
    middle = clean_name(middle_name) or None
    last = clean_name(last_name) or None

    errors = {}
    if not first:
        errors["first_name"] = "First name is required."
    return (first, middle, last), errors


def person_name(row, fallback="—") -> str:
    """Build a display name from a row/dict of name columns.

    Works for dict rows (Supabase/PostgREST) and attribute objects (models).
    Missing or SQL NULL optional parts are skipped so the name never renders
    with stray spaces, and ``fallback`` is shown when there is no name at all.
    """
    if not row:
        return fallback
    if hasattr(row, "get"):
        get = row.get
    else:
        def get(key):
            return getattr(row, key, None)
    return format_display_name(
        get("first_name"), get("middle_name"), get("last_name"),
        fallback=get("full_name") or "",
    ) or fallback


def is_valid_email(value: str) -> bool:
    return bool(value) and bool(EMAIL_RE.match(value)) and len(value) <= 254


def is_valid_phone(value: str) -> bool:
    return bool(value) and bool(PHONE_RE.match(value))


def validate_password(password: str):
    """Return an error message, or None when the password is acceptable."""
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one number."
    if len(password) > 128:
        return "Password is too long (max 128 characters)."
    return None


def validate_email_password(email, password, confirm=None):
    errors = {}
    email = clean_str(email, 254).lower()
    if not is_valid_email(email):
        errors["email"] = "Enter a valid email address."
    pw_error = validate_password(password)
    if pw_error:
        errors["password"] = pw_error
    if confirm is not None and password != confirm:
        errors["confirm_password"] = "Passwords do not match."
    return email, errors


# ---------------------------------------------------------------------------
# Application form validation
# ---------------------------------------------------------------------------
GENDERS = {"male", "female", "other", "prefer_not_to_say"}
CATEGORIES = {"general", "obc", "sc", "st", "ews", "other"}

# Previous education / qualification. Stored lower-case so the catalogue and
# eligibility engine share one vocabulary. Older rows may still contain free
# text such as "Class 12" — those are preserved, never re-validated.
QUALIFICATIONS = ("sslc", "puc", "iti")
QUALIFICATION_LABELS = {"sslc": "SSLC", "puc": "PUC", "iti": "ITI"}
INSTITUTION_LABELS = {
    "sslc": "School name",
    "puc": "College name",
    "iti": "ITI institute name",
}
PUC_STREAMS = ("science", "commerce", "arts", "other")
ITI_AFFILIATIONS = ("ncvt", "scvt", "other")


def _check_date(value, field, errors, required=True):
    value = clean_str(value)
    if not value:
        if required:
            errors[field] = "Date of birth is required."
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors[field] = "Date of birth must be in YYYY-MM-DD format."
        return None
    if parsed > date.today():
        errors[field] = "Date of birth cannot be in the future."
    elif (date.today() - parsed).days < 3650:  # younger than ~10 years
        errors[field] = "Applicant must be at least 10 years old."
    return parsed.isoformat()


def _check_number(value, field, label, errors, minimum=0.0, maximum=100.0, required=True):
    value = clean_str(value)
    if not value:
        if required:
            errors[field] = f"{label} is required."
        return None
    try:
        number = float(value)
    except ValueError:
        errors[field] = f"{label} must be a number."
        return None
    if number < minimum or number > maximum:
        errors[field] = f"{label} must be between {minimum:g} and {maximum:g}."
        return None
    return number


def _normalize_qualification_option(value, allowed, field, required_msg, errors, required=True):
    """Normalise a qualification-specific dropdown value.

    The ``"na"`` / ``"Not applicable"`` (and blank, when the field is not
    required) choices map to SQL ``NULL`` so we never store the literal string
    "null" or "N/A". Returns the canonical lower-case value, or ``None``.
    """
    value = clean_str(value).lower()
    if value in ("na", "n/a", "not_applicable", "not applicable", "none", "-"):
        return None
    if value in allowed:
        return value
    if not value:
        if required and required_msg:
            errors[field] = required_msg
        return None
    errors[field] = "Select a valid option."
    return None


def parse_qualification_list(value):
    """Normalise a course's eligible-qualifications selection.

    Accepts a list, a comma/space/semicolon separated string, or a single
    value. Returns ``(unique_qualifications, invalid_values)``; the list is
    ``None`` when nothing was selected, which means "open to all
    qualifications".
    """
    if value is None:
        return None, []
    if isinstance(value, str):
        parts = [p for p in re.split(r"[\s,;]+", value) if p]
    elif isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = [value]
    quals = []
    invalid = []
    for part in parts:
        text = clean_str(part).lower()
        if text in QUALIFICATIONS:
            if text not in quals:
                quals.append(text)
        elif text:
            invalid.append(text)
    return (quals or None), invalid


def validate_application_form(form) -> dict:
    """Validate and normalise an admission application form.

    Raises ValidationError with a field -> message mapping when invalid.
    """
    errors = {}
    data = {}

    # --- Personal --------------------------------------------------------
    # Names mirror the registration / profile forms exactly: the first name is
    # the only compulsory part and optional parts are stored as SQL NULL (never
    # an empty string). Shared with those forms via validate_names().
    (first_name, middle_name, last_name), name_errors = validate_names(
        form.get("first_name"), form.get("middle_name"), form.get("last_name")
    )
    data["first_name"] = first_name
    data["middle_name"] = middle_name
    data["last_name"] = last_name
    errors.update(name_errors)

    data["date_of_birth"] = _check_date(form.get("date_of_birth"), "date_of_birth", errors)

    gender = clean_str(form.get("gender")).lower()
    if gender not in GENDERS:
        errors["gender"] = "Select a valid gender option."
    data["gender"] = gender

    category = clean_str(form.get("category")).lower()
    if category and category not in CATEGORIES:
        errors["category"] = "Select a valid category."
    data["category"] = category or None

    data["nationality"] = clean_str(form.get("nationality"), 60) or "Indian"

    # --- Contact ---------------------------------------------------------
    data["email"] = clean_str(form.get("email"), 254).lower()
    if not is_valid_email(data["email"]):
        errors["email"] = "Enter a valid contact email address."

    data["phone"] = clean_str(form.get("phone"), 20)
    if not is_valid_phone(data["phone"]):
        errors["phone"] = "Enter a valid phone number (7-20 digits)."

    data["address_line"] = clean_str(form.get("address_line"), 200)
    data["city"] = clean_str(form.get("city"), 80)
    data["state"] = clean_str(form.get("state"), 80)
    data["postal_code"] = clean_str(form.get("postal_code"), 12)
    data["country"] = clean_str(form.get("country"), 60) or "India"

    if not data["address_line"]:
        errors["address_line"] = "Address is required."
    if not data["city"]:
        errors["city"] = "City is required."
    if not data["state"]:
        errors["state"] = "State is required."
    if not data["postal_code"]:
        errors["postal_code"] = "Postal code is required."

    # --- Academic (SSLC / PUC / ITI) ------------------------------------
    qualification = clean_str(form.get("qualifying_exam"), 20).lower()
    if qualification not in QUALIFICATIONS:
        errors["qualifying_exam"] = "Select your previous education / qualification."
        qualification = None
    data["qualifying_exam"] = qualification

    # Only the fields relevant to the chosen qualification are compulsory.
    # Irrelevant fields are stored as SQL NULL (never the literal "null").
    institution_label = INSTITUTION_LABELS.get(qualification, "School / Institution")
    data["institution_name"] = clean_str(
        form.get("institution_name") or form.get("school_name"), 150
    ) or None
    # Denormalised mirror of the institution on the legacy school_name column
    # so older screens/report exports keep showing the same value.
    data["school_name"] = data["institution_name"]
    if qualification and not data["institution_name"]:
        errors["institution_name"] = f"{institution_label} is required."

    if qualification in ("sslc", "puc"):
        board = clean_str(form.get("board_university"), 120)
        if not board:
            errors["board_university"] = "Board is required for SSLC / PUC."
        data["board_university"] = board or None
    else:
        # Board is not applicable to ITI applications.
        data["board_university"] = None

    if qualification == "puc":
        data["stream"] = _normalize_qualification_option(
            form.get("stream"), PUC_STREAMS, "stream",
            "Stream is required for PUC.", errors,
        )
    else:
        data["stream"] = None

    if qualification == "iti":
        trade = clean_str(form.get("trade"), 100)
        if not trade:
            errors["trade"] = "Trade / specialization is required for ITI."
        data["trade"] = trade or None
    else:
        data["trade"] = None

    if qualification == "iti":
        data["affiliation"] = _normalize_qualification_option(
            form.get("affiliation"), ITI_AFFILIATIONS, "affiliation",
            None, errors, required=False,
        )
    else:
        data["affiliation"] = None

    # Registration / roll number: optional for every qualification.
    data["roll_number"] = clean_str(form.get("roll_number"), 40) or None

    year = clean_str(form.get("passing_year"))
    if not year or not year.isdigit() or not (1950 <= int(year) <= date.today().year + 1):
        errors["passing_year"] = "Enter a valid passing year."
        data["passing_year"] = None
    else:
        data["passing_year"] = int(year)

    data["marks_obtained"] = _check_number(
        form.get("marks_obtained"), "marks_obtained", "Marks obtained",
        errors, 0, 100000, required=False,
    )
    data["marks_total"] = _check_number(
        form.get("marks_total"), "marks_total", "Maximum marks",
        errors, 1, 100000, required=False,
    )
    if (
        data.get("marks_obtained") is not None
        and data.get("marks_total") is not None
        and data["marks_obtained"] > data["marks_total"]
    ):
        errors["marks_obtained"] = "Marks obtained cannot exceed total marks."

    percentage = _check_number(
        form.get("percentage"), "percentage", "Percentage", errors, 0, 100, required=False
    )
    if percentage is None and data.get("marks_obtained") and data.get("marks_total"):
        percentage = round(data["marks_obtained"] / data["marks_total"] * 100, 2)
    data["percentage"] = percentage

    # --- Course ----------------------------------------------------------
    data["course_id"] = clean_str(form.get("course_id")) or None
    if not data["course_id"]:
        errors["course_id"] = "Select a preferred course."

    if errors:
        raise ValidationError(errors)
    return data


def allowed_file(filename: str, allowed_extensions) -> bool:
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in allowed_extensions
    )


# ---------------------------------------------------------------------------
# Course catalogue validation (Degree / Diploma)
# Shared by the server-rendered admin views and the JSON API.
# ---------------------------------------------------------------------------
COURSE_PROGRAM_TYPES = ("degree", "diploma")


def validate_course_fields(data) -> tuple:
    """Validate the Diploma/Degree course fields.

    Returns ``(values, errors)``. ``values`` contains ``program_type``,
    ``eligibility``, ``tuition_fee`` and ``eligible_qualifications``; ``errors``
    is an empty dict when the input is valid. ``tuition_fee`` is ``None`` when
    the field is left blank (means "contact the admissions office" in the UI)
    and ``eligible_qualifications`` is ``None`` when nothing was selected
    (means the course is open to all qualifications).
    """
    errors = {}
    program_type = clean_str(data.get("program_type")).lower()
    if program_type not in COURSE_PROGRAM_TYPES + ("",):
        errors["program_type"] = "Programme type must be Degree or Diploma."
    elif not program_type:
        program_type = "degree"

    eligibility = clean_str(data.get("eligibility"), 600)

    tuition_fee = None
    raw_fee = data.get("tuition_fee")
    if raw_fee is not None and str(raw_fee).strip() != "":
        try:
            tuition_fee = float(str(raw_fee).strip())
        except (TypeError, ValueError):
            errors["tuition_fee"] = "Annual tuition fee must be a number."
        else:
            if tuition_fee < 0:
                errors["tuition_fee"] = "Annual tuition fee cannot be negative."

    eligible, invalid_quals = parse_qualification_list(
        data.get("eligible_qualifications")
    )
    if invalid_quals:
        errors["eligible_qualifications"] = (
            "Eligible qualifications must be SSLC, PUC or ITI."
        )

    return {
        "program_type": program_type,
        "eligibility": eligibility,
        "tuition_fee": tuition_fee,
        "eligible_qualifications": eligible,
    }, errors


# ---------------------------------------------------------------------------
# Student account validation (admin add / edit)
# ---------------------------------------------------------------------------
REGISTRATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_\-]{1,39}$")


def validate_student_form(data) -> tuple:
    """Validate an administrator's add/edit student payload.

    Returns ``(values, errors)``; ``errors`` is empty when the input is valid.
    Password handling is deliberately *not* part of this form - administrators
    never set or see a student's password (a one-time setup link is used).
    """
    from app.models import STUDENT_STATUSES  # local import avoids import cycles

    errors = {}
    values = {}

    # Names: the admin form sends first/middle/last separately. Older API
    # clients may still send a single full_name; split it as a fallback.
    first = clean_name(data.get("first_name"))
    middle = clean_name(data.get("middle_name"))
    last = clean_name(data.get("last_name"))
    if not first and not middle and not last:
        legacy = clean_str(data.get("full_name"), 120)
        if legacy:
            first, middle, last = split_full_name(legacy)
    if not first:
        errors["first_name"] = "First name is required."
    values["first_name"] = first or None
    values["middle_name"] = middle or None
    values["last_name"] = last or None
    values["full_name"] = format_display_name(first, middle, last)

    values["email"] = clean_str(data.get("email"), 254).lower()
    if not is_valid_email(values["email"]):
        errors["email"] = "Enter a valid email address."

    values["phone"] = clean_str(data.get("phone"), 20)
    if values["phone"] and not is_valid_phone(values["phone"]):
        errors["phone"] = "Enter a valid phone number (7-20 digits)."

    registration = clean_str(data.get("registration_number"), 40)
    if registration and not REGISTRATION_RE.match(registration):
        errors["registration_number"] = (
            "Use 2-40 letters, digits, spaces, '-', '_' or '/'."
        )
    values["registration_number"] = registration or None

    values["assigned_course_id"] = clean_str(data.get("assigned_course_id")) or None

    status = clean_str(data.get("status")).lower() or "active"
    if status not in STUDENT_STATUSES:
        errors["status"] = "Select a valid account status."
    values["status"] = status

    return values, errors

