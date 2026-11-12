"""Convert database rows into the JSON shapes returned by the API.

The API returns the full snake_case database columns *plus* a small set of
camelCase aliases so the bundled static frontend can consume the responses
unchanged. ``password_hash`` is never exposed.
"""

from app.utils.validators import format_display_name

APPLICATION_FIELDS = (
    "application_number",
    "status",
    "first_name",
    "middle_name",
    "last_name",
    "date_of_birth",
    "gender",
    "category",
    "nationality",
    "email",
    "phone",
    "address_line",
    "city",
    "state",
    "postal_code",
    "country",
    "qualifying_exam",
    "board_university",
    "school_name",
    "institution_name",
    "stream",
    "trade",
    "affiliation",
    "roll_number",
    "passing_year",
    "marks_obtained",
    "marks_total",
    "percentage",
    "admin_note",
    "submitted_at",
    "reviewed_at",
    "reviewed_by",
    "created_at",
    "updated_at",
)


def serialize_user(row):
    if not row:
        return None
    full_name = format_display_name(
        row.get("first_name"),
        row.get("middle_name"),
        row.get("last_name"),
        fallback=row.get("full_name") or "",
    )
    return {
        "id": str(row.get("id", "")),
        "first_name": row.get("first_name"),
        "middle_name": row.get("middle_name"),
        "last_name": row.get("last_name"),
        "full_name": full_name,
        "name": full_name,  # alias used by the static frontend
        "email": row.get("email"),
        "phone": row.get("phone"),
        "role": row.get("role", "student"),
        "status": row.get("status")
        or ("active" if row.get("is_active", True) else "inactive"),
        "registration_number": row.get("registration_number"),
        "assigned_course_id": row.get("assigned_course_id"),
        "is_active": bool(row.get("is_active", True)),
        "created_at": row.get("created_at"),
    }


def serialize_course(row, application_counts=None):
    if not row:
        return None
    course_id = str(row.get("id", ""))
    data = {
        "id": course_id,
        "code": row.get("code"),
        "name": row.get("name"),
        "description": row.get("description"),
        "program_type": row.get("program_type", "degree"),
        "eligibility": row.get("eligibility"),
        "eligible_qualifications": row.get("eligible_qualifications"),
        "tuition_fee": row.get("tuition_fee"),
        "duration_years": row.get("duration_years"),
        "seats_total": row.get("seats_total"),
        "is_active": bool(row.get("is_active", True)),
    }
    if application_counts:
        data["application_count"] = int(application_counts.get(course_id, 0))
    else:
        data["application_count"] = row.get("application_count")
    return data


def serialize_application(row):
    if not row:
        return None

    course = row.get("courses") or row.get("course") or {}
    first = row.get("first_name")
    middle = row.get("middle_name")
    last = row.get("last_name")
    applicant_name = format_display_name(first, middle, last)

    data = {field: row.get(field) for field in APPLICATION_FIELDS}
    data["id"] = str(row.get("id", ""))
    data["user_id"] = str(row["user_id"]) if row.get("user_id") else None
    data["course_id"] = str(row["course_id"]) if row.get("course_id") else None
    data["course"] = serialize_course(course) if course else None
    data["courses"] = data["course"]  # alias used by the service joins

    # camelCase aliases for the bundled static frontend.
    data.update(
        {
            "number": row.get("application_number"),
            "applicantName": applicant_name,
            "middleName": middle,
            "courseName": course.get("name") if course else None,
            "courseCode": course.get("code") if course else None,
            "dateOfBirth": row.get("date_of_birth"),
            "address": row.get("address_line"),
            "postalCode": row.get("postal_code"),
            "qualifyingExam": row.get("qualifying_exam"),
            "board": row.get("board_university"),
            "school": row.get("school_name"),
            "institutionName": (
                row.get("institution_name") or row.get("school_name")
            ),
            "stream": row.get("stream"),
            "trade": row.get("trade"),
            "affiliation": row.get("affiliation"),
            "rollNumber": row.get("roll_number"),
            "passingYear": row.get("passing_year"),
            "marksObtained": row.get("marks_obtained"),
            "marksTotal": row.get("marks_total"),
            "adminNote": row.get("admin_note"),
            "submittedAt": row.get("submitted_at"),
            "updatedAt": row.get("updated_at"),
        }
    )
    return data


def serialize_document(row, url=None):
    if not row:
        return None
    verified = bool(row.get("is_verified", False))
    size = row.get("size_bytes")
    data = {
        "id": str(row.get("id", "")),
        "application_id": str(row["application_id"]) if row.get("application_id") else None,
        "user_id": str(row["user_id"]) if row.get("user_id") else None,
        "doc_type": row.get("doc_type"),
        "file_name": row.get("file_name"),
        "mime_type": row.get("mime_type"),
        "size_bytes": size,
        "is_verified": verified,
        "uploaded_at": row.get("uploaded_at"),
        # camelCase aliases for the static frontend
        "type": row.get("doc_type"),
        "name": row.get("file_name"),
        "size": size,
        "verified": verified,
    }
    if url:
        data["url"] = url
    return data


def serialize_history(row, user_map=None):
    if not row:
        return None
    changed_by = str(row["changed_by"]) if row.get("changed_by") else None
    user = (user_map or {}).get(changed_by) if changed_by else None
    return {
        "id": str(row.get("id", "")) if row.get("id") else None,
        "status": row.get("status"),
        "note": row.get("note"),
        "changed_by": changed_by,
        "changed_by_name": (user or {}).get("full_name"),
        "changed_by_role": (user or {}).get("role"),
        "created_at": row.get("created_at"),
        "at": row.get("created_at"),  # alias for the static frontend
    }


def serialize_audit(row):
    if not row:
        return None
    return {
        "id": str(row.get("id", "")) if row.get("id") else None,
        "actor_id": str(row["actor_id"]) if row.get("actor_id") else None,
        "actor_email": row.get("actor_email"),
        "action": row.get("action"),
        "entity_type": row.get("entity_type"),
        "entity_id": row.get("entity_id"),
        "details": row.get("details"),
        "created_at": row.get("created_at"),
    }


def serialize_announcement(row):
    if not row:
        return None
    return {
        "id": str(row.get("id", "")) if row.get("id") else None,
        "title": row.get("title"),
        "body": row.get("body"),
        "tag": row.get("tag"),
        "date": row.get("published_at") or row.get("created_at"),
        "published_at": row.get("published_at"),
    }
