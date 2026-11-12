"""Small request-parsing helpers shared by the API blueprints."""

from flask import current_app, request

# Camel-case keys the bundled static frontend sends, mapped to the snake_case
# names the database and validators expect. Accepting both keeps the API
# pleasant for external clients without weakening validation.
_APPLICATION_ALIASES = {
    "firstName": "first_name",
    "middleName": "middle_name",
    "lastName": "last_name",
    "dateOfBirth": "date_of_birth",
    "address": "address_line",
    "postalCode": "postal_code",
    "qualifyingExam": "qualifying_exam",
    "board": "board_university",
    "school": "school_name",
    "institutionName": "institution_name",
    "institution": "institution_name",
    "stream": "stream",
    "trade": "trade",
    "affiliation": "affiliation",
    "rollNumber": "roll_number",
    "passingYear": "passing_year",
    "marksObtained": "marks_obtained",
    "marksTotal": "marks_total",
    "courseId": "course_id",
    "fullName": "full_name",
}


def json_body():
    """Return the request body as a dict, accepting JSON or form data."""
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    if request.form:
        return request.form.to_dict(flat=True)
    return {}


def normalize_application_payload(data):
    """Add snake_case equivalents for camelCase application fields."""
    normalized = dict(data or {})
    for camel, snake in _APPLICATION_ALIASES.items():
        if camel in normalized and snake not in normalized:
            normalized[snake] = normalized[camel]
    return normalized


def query_arg(name, default=None, max_length=200):
    value = request.args.get(name)
    if value is None:
        return default
    value = value.strip()
    if max_length:
        value = value[:max_length]
    return value or default


def paginate(rows):
    """Slice ``rows`` using ?page= and ?per_page= and return the metadata."""
    default_per_page = current_app.config.get("APPLICATIONS_PER_PAGE", 10)
    try:
        per_page = int(query_arg("per_page", default_per_page) or default_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    per_page = max(1, min(per_page, 100))

    try:
        page = int(query_arg("page", 1) or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    total = len(rows)
    start = (page - 1) * per_page
    return page, per_page, total, rows[start:start + per_page]
