"""Administrator endpoints: review list, detail, statistics, course management.

Every route here is protected with ``@api_admin_required``, so a student (or
anonymous visitor) gets a 403 JSON response and can never reach the code below.
"""

import csv
import hashlib
import io
import math
import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, current_app, request, url_for
from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.api.decorators import api_admin_required
from app.api.responses import created, failure, success
from app.api.serializers import (
    serialize_application,
    serialize_audit,
    serialize_course,
    serialize_document,
    serialize_history,
    serialize_user,
)
from app.api.utils import json_body, query_arg
from app.models import (
    APPLICATION_STATUSES,
    STATUS_LABELS,
    STUDENT_STATUSES,
)
from app.services import application_service
from app.utils.validators import (
    clean_str,
    validate_course_fields,
    validate_password,
    validate_student_form,
)

bp = Blueprint("api_admin", __name__)

# Columns the admin list may be sorted on (whitelist, never passed raw).
SORTABLE_FIELDS = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "submitted_at": "submitted_at",
    "application_number": "application_number",
    "number": "application_number",
    "status": "status",
    "first_name": "first_name",
    "middle_name": "middle_name",
    "last_name": "last_name",
    "percentage": "percentage",
}


def _date_filter(name):
    """Return validated ``YYYY-MM-DD`` style date args as ISO strings."""
    value = query_arg(name)
    if not value:
        return None
    value = value.strip()
    return value


def _end_of_day(value):
    """Append end-of-day so a `to` filter includes the entire date."""
    value = value.strip()
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return value + "T23:59:59.999999"
    return value


def _resolve_order_by():
    field = SORTABLE_FIELDS.get(query_arg("sort") or "created_at", "created_at")
    order = (query_arg("order") or "desc").lower()
    descending = order not in ("asc", "ascending")
    return field, descending


def _history_payload(history):
    """Status history rows enriched with the changer's name and role."""
    ids = {str(h.get("changed_by")) for h in history if h.get("changed_by")}
    users = {
        str(u["id"]): u
        for u in current_app.supabase.get_users_by_ids(ids or None)
    }
    return [serialize_history(h, user_map=users) for h in history]


def _course_payload(data, partial=False):
    """Validate a course payload; return (payload, errors|None)."""
    errors = {}

    code = clean_str(data.get("code"), 20).upper()
    name = clean_str(data.get("name"), 150)
    description = clean_str(data.get("description"), 500)

    raw_duration = data.get("duration_years")
    raw_seats = data.get("seats_total")
    try:
        duration = int(raw_duration or 0)
    except (TypeError, ValueError):
        errors["duration_years"] = "Duration must be a whole number."
        duration = 0
    try:
        seats = int(raw_seats or 0)
    except (TypeError, ValueError):
        errors["seats_total"] = "Seats must be a whole number."
        seats = 0

    extras, extra_errors = validate_course_fields(data)
    errors.update(extra_errors or {})

    if not partial:
        if not code:
            errors["code"] = "Course code is required."
        if not name:
            errors["name"] = "Course name is required."
        if not 1 <= duration <= 10:
            errors["duration_years"] = "Duration must be between 1 and 10 years."
        if not 1 <= seats <= 2000:
            errors["seats_total"] = "Seats must be between 1 and 2000."
    else:
        if "code" in data and not code:
            errors["code"] = "Course code cannot be empty."
        if "name" in data and not name:
            errors["name"] = "Course name cannot be empty."
        if raw_duration is not None and not 1 <= duration <= 10:
            errors["duration_years"] = "Duration must be between 1 and 10 years."
        if raw_seats is not None and not 1 <= seats <= 2000:
            errors["seats_total"] = "Seats must be between 1 and 2000."

    if errors:
        return None, errors

    payload = {}
    if code or not partial:
        payload["code"] = code
    if name or not partial:
        payload["name"] = name
    if "description" in data or not partial:
        payload["description"] = description
    if raw_duration is not None or not partial:
        payload["duration_years"] = duration
    if raw_seats is not None or not partial:
        payload["seats_total"] = seats
    # Diploma / Polytechnic fields.
    if "program_type" in data or not partial:
        payload["program_type"] = extras["program_type"]
    if "eligibility" in data or not partial:
        payload["eligibility"] = extras["eligibility"]
    if "tuition_fee" in data or not partial:
        payload["tuition_fee"] = extras["tuition_fee"]
    if "eligible_qualifications" in data or not partial:
        payload["eligible_qualifications"] = extras["eligible_qualifications"]
    return payload, None


# ---------------------------------------------------------------------------
# Application list (search / filter / sort / paginate)
# ---------------------------------------------------------------------------
@bp.route("/admin/applications", methods=["GET"])
@api_admin_required
def list_applications():
    status = query_arg("status")
    if status and status not in APPLICATION_STATUSES:
        return failure("Unknown status filter.", 400, {"status": "Unknown status filter."})

    course_id = query_arg("course_id") or query_arg("courseId")
    search = query_arg("q") or query_arg("search")
    date_from = _date_filter("from") or _date_filter("date_from")
    date_to = _date_filter("to") or _date_filter("date_to")
    if date_to:
        date_to = _end_of_day(date_to)
    order_by, descending = _resolve_order_by()

    try:
        per_page = int(query_arg("per_page", 10) or 10)
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(1, min(per_page, 100))
    try:
        page = int(query_arg("page", 1) or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    total = current_app.supabase.count_applications(
        status=status or None,
        course_id=course_id or None,
        search=search or None,
        date_from=date_from,
        date_to=date_to,
    )
    rows = current_app.supabase.list_applications(
        status=status or None,
        course_id=course_id or None,
        search=search or None,
        date_from=date_from,
        date_to=date_to,
        order_by=order_by,
        descending=descending,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return success(
        applications=[serialize_application(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


# ---------------------------------------------------------------------------
# Application detail + review actions
# ---------------------------------------------------------------------------
@bp.route("/admin/applications/<application_id>", methods=["GET"])
@api_admin_required
def application_detail(application_id):
    application = current_app.supabase.get_application(application_id)
    if not application:
        return failure("Application not found.", 404)

    documents = current_app.supabase.list_documents(application_id)
    history = _history_payload(current_app.supabase.list_status_history(application_id))

    # Short-lived signed URLs so the admin can open each document; these expire
    # automatically and grant no storage-level permissions.
    expires = current_app.config.get("SIGNED_URL_EXPIRES_IN", 300)
    doc_payload = [
        serialize_document(
            d,
            url=current_app.supabase.create_signed_url(d.get("storage_path"), expires),
        )
        for d in documents
    ]

    payload = serialize_application(application)
    payload["documents"] = doc_payload
    payload["history"] = history
    return success(
        application=payload,
        documents=payload["documents"],
        history=payload["history"],
    )


@bp.route("/admin/applications/<application_id>/status", methods=["PATCH", "POST"])
@api_admin_required
def update_status(application_id):
    payload = json_body()
    status = clean_str(payload.get("status"))
    note = clean_str(payload.get("note"), 1000)

    application = application_service.change_status(
        current_app.supabase, current_user, application_id, status, note
    )
    return success(application=serialize_application(application))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@bp.route("/admin/stats", methods=["GET"])
@api_admin_required
def stats():
    counts = current_app.supabase.status_counts()
    counts["pending"] = (
        counts.get("submitted", 0)
        + counts.get("under_review", 0)
        + counts.get("correction_requested", 0)
    )
    course_counts = current_app.supabase.course_status_counts()
    counts["students_total"] = current_app.supabase.count_students()
    counts["courses_active"] = course_counts.get("active", 0)
    counts["diploma_active"] = course_counts.get("diploma_active", 0)
    return success(stats=counts)


# ---------------------------------------------------------------------------
# Students management
# ---------------------------------------------------------------------------
STUDENT_SORTABLE = {
    "created_at": "created_at",
    "name": "full_name",
    "email": "email",
    "status": "status",
}

# How long a student's one-time password-setup link stays valid.
INVITE_TTL_DAYS = 7


def _issue_invite(user_id):
    """Create a one-time setup token; only its SHA-256 hash is stored."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
    current_app.supabase.set_invitation(user_id, token_hash, expires_at)
    return token


def _audit_student(action, entity_id, details):
    current_app.supabase.add_audit_log(
        action=action,
        actor_id=current_user.id,
        actor_email=getattr(current_user, "email", None),
        entity_type="user",
        entity_id=entity_id,
        details=details,
    )


def _validate_student_payload(payload, exclude_id=None):
    """Validate a create/update payload. Returns (values, error_response)."""
    values, errors = validate_student_form(payload)
    if errors:
        return None, failure("Please correct the highlighted fields.", 422, errors)

    existing = current_app.supabase.get_user_by_email(values["email"])
    if existing and str(existing.get("id")) != str(exclude_id or ""):
        return None, failure(
            "A user with this email address already exists.",
            409,
            {"email": "This email address is already in use."},
        )
    if values.get("registration_number") and current_app.supabase.registration_number_exists(
        values["registration_number"], exclude_id=exclude_id
    ):
        return None, failure(
            "This registration number is already in use.",
            409,
            {"registration_number": "This registration number is already in use."},
        )
    if values.get("assigned_course_id") and not current_app.supabase.get_course(
        values["assigned_course_id"]
    ):
        return None, failure(
            "Select a valid course.",
            422,
            {"assigned_course_id": "Select a valid course."},
        )
    return values, None


@bp.route("/admin/students", methods=["GET"])
@api_admin_required
def list_students():
    search = query_arg("q") or query_arg("search")
    status = (query_arg("status") or "").lower()
    if status not in STUDENT_STATUSES:
        status = None
    order_by = STUDENT_SORTABLE.get(query_arg("sort") or "created_at", "created_at")
    descending = (query_arg("order") or "desc").lower() not in ("asc", "ascending")

    try:
        per_page = int(query_arg("per_page", 10) or 10)
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(1, min(per_page, 100))
    try:
        page = int(query_arg("page", 1) or 1)
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    total = current_app.supabase.count_students(search=search, status=status)
    rows = current_app.supabase.list_students(
        search=search,
        status=status,
        order_by=order_by,
        descending=descending,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    counts = current_app.supabase.application_counts_by_user()
    numbers = current_app.supabase.application_numbers_by_user()
    students = []
    for row in rows:
        payload = serialize_user(row)
        uid = str(row.get("id"))
        payload["applications_count"] = counts.get(uid, 0)
        payload["registration_number"] = row.get("registration_number") or numbers.get(uid)
        students.append(payload)
    return success(
        students=students,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if per_page else 0,
    )


@bp.route("/admin/students", methods=["POST"])
@api_admin_required
def create_student():
    """Create a student without ever handling or revealing a password."""
    payload = json_body()
    values, error = _validate_student_payload(payload)
    if error:
        return error

    placeholder = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")
    row = current_app.supabase.create_user(
        email=values["email"],
        password_hash=placeholder,
        first_name=values["first_name"],
        middle_name=values["middle_name"],
        last_name=values["last_name"],
        phone=values["phone"] or None,
        role="student",
        registration_number=values["registration_number"],
        status=values["status"],
        assigned_course_id=values["assigned_course_id"],
    )
    if not row:
        return failure("Could not create the student.", 500)

    setup_url = None
    if values["status"] == "active":
        setup_url = url_for(
            "auth.setup_password", token=_issue_invite(row["id"]), _external=True
        )
    _audit_student(
        "student_create",
        row.get("id"),
        "Created student {} ({}).".format(values["email"], values["status"]),
    )
    return created(student=serialize_user(row), setup_url=setup_url)


@bp.route("/admin/students/<user_id>", methods=["GET"])
@api_admin_required
def student_detail(user_id):
    student = current_app.supabase.get_student(user_id)
    if not student:
        return failure("Student not found.", 404)
    applications = current_app.supabase.list_applications_for_user(user_id)
    payload = serialize_user(student)
    payload["applications_count"] = len(applications)
    return success(
        student=payload,
        applications=[serialize_application(a) for a in applications],
    )


@bp.route("/admin/students/<user_id>", methods=["PATCH", "PUT"])
@api_admin_required
def update_student(user_id):
    student = current_app.supabase.get_student(user_id)
    if not student:
        return failure("Student not found.", 404)

    values, error = _validate_student_payload(json_body(), exclude_id=user_id)
    if error:
        return error

    updated = current_app.supabase.set_student_status(
        user_id,
        values["status"],
        extra={
            "first_name": values["first_name"],
            "middle_name": values["middle_name"],
            "last_name": values["last_name"],
            "full_name": values["full_name"],
            "email": values["email"],
            "phone": values["phone"] or None,
            "registration_number": values["registration_number"],
            "assigned_course_id": values["assigned_course_id"],
        },
    )
    _audit_student(
        "student_update",
        user_id,
        "Updated student {} ({}).".format(values["email"], values["status"]),
    )
    return success(student=serialize_user(updated or student))


@bp.route("/admin/students/<user_id>/status", methods=["POST", "PATCH"])
@api_admin_required
def set_student_status(user_id):
    student = current_app.supabase.get_student(user_id)
    if not student:
        return failure("Student not found.", 404)

    payload = json_body()
    status = clean_str(payload.get("status")).lower()
    if not status:
        # Backwards-compatible boolean form.
        raw = payload.get("is_active", payload.get("active"))
        if isinstance(raw, str):
            raw = raw.strip().lower() in ("1", "true", "yes", "active")
        if raw is None:
            return failure(
                "Provide status (active/inactive/withdrawn).",
                422,
                {"status": "Required."},
            )
        status = "active" if raw else "inactive"
    if status not in STUDENT_STATUSES:
        return failure("Invalid status.", 422, {"status": "Invalid status."})

    reason = clean_str(payload.get("reason"), 200)
    updated = current_app.supabase.set_student_status(user_id, status)
    _audit_student(
        "student_status_change",
        user_id,
        "{} set to {}{}".format(
            student.get("email"),
            status,
            " (reason: {})".format(reason) if reason else "",
        ),
    )
    return success(student=serialize_user(updated or student))


@bp.route("/admin/students/<user_id>/invite", methods=["POST"])
@api_admin_required
def invite_student(user_id):
    student = current_app.supabase.get_student(user_id)
    if not student:
        return failure("Student not found.", 404)
    setup_url = url_for(
        "auth.setup_password", token=_issue_invite(user_id), _external=True
    )
    _audit_student(
        "student_invite",
        user_id,
        "Issued a password-setup link for {}.".format(student.get("email")),
    )
    return success(setup_url=setup_url)


@bp.route("/admin/students/<user_id>", methods=["DELETE"])
@api_admin_required
def delete_student(user_id):
    """Permanently delete a student. Requires confirm=DELETE and a reason."""
    student = current_app.supabase.get_student(user_id)
    if not student:
        return failure("Student not found.", 404)
    if str(user_id) == str(current_user.id):
        return failure("You cannot delete your own account.", 403)
    if student.get("role") == "admin":
        return failure("Administrator accounts cannot be deleted here.", 403)

    payload = json_body()
    if clean_str(payload.get("confirm")) != "DELETE":
        return failure(
            "Provide confirm=DELETE to permanently delete.",
            422,
            {"confirm": "Type DELETE to confirm."},
        )
    reason = clean_str(payload.get("reason"), 300)
    if not reason:
        return failure(
            "A reason is required for permanent deletion.",
            422,
            {"reason": "A reason is required."},
        )

    for path in current_app.supabase.document_paths_by_user(user_id):
        current_app.supabase.delete_object(path)
    current_app.supabase.delete_user(user_id)
    _audit_student(
        "student_delete",
        user_id,
        "Permanently deleted student {} - reason: {}".format(student.get("email"), reason),
    )
    return success(deleted=True, id=str(user_id))


@bp.route("/admin/audit", methods=["GET"])
@api_admin_required
def audit_log():
    try:
        limit = int(query_arg("limit", 20) or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    rows = current_app.supabase.list_audit_log(limit=limit)
    return success(entries=[serialize_audit(r) for r in rows])



# ---------------------------------------------------------------------------
# Administrator profile
# ---------------------------------------------------------------------------
@bp.route("/admin/profile", methods=["GET"])
@api_admin_required
def admin_profile():
    """The signed-in administrator's own account details (never a hash)."""
    row = current_app.supabase.get_user_by_id(current_user.id) or current_user.to_dict()
    return success(profile=serialize_user(row))


@bp.route("/admin/profile/password", methods=["POST", "PATCH"])
@api_admin_required
def change_password():
    """Change the signed-in administrator's password.

    The current password is always re-verified against the stored hash and the
    new password is validated server-side; the role supplied by the browser is
    never trusted because the account is taken from the server-side session.
    """
    payload = json_body()
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    confirm = payload.get("confirm_password")

    row = current_app.supabase.get_user_by_id(current_user.id)
    if not row or not check_password_hash(row.get("password_hash", ""), current_password):
        return failure(
            "Your current password is incorrect.",
            422,
            {"current_password": "Your current password is incorrect."},
        )

    password_error = validate_password(new_password)
    if password_error:
        return failure(password_error, 422, {"new_password": password_error})
    if confirm is not None and new_password != confirm:
        return failure(
            "The new passwords do not match.",
            422,
            {"confirm_password": "The new passwords do not match."},
        )

    updated = current_app.supabase.update_user(
        current_user.id,
        {"password_hash": generate_password_hash(new_password, method="scrypt")},
    )
    if not updated:
        return failure("Could not update your password. Please try again.", 500)

    current_app.supabase.add_audit_log(
        action="admin_password_change",
        actor_id=current_user.id,
        actor_email=getattr(current_user, "email", None),
        entity_type="user",
        entity_id=current_user.id,
        details="Administrator changed their password via the admin console.",
    )
    return success(message="Your password has been updated.")


# ---------------------------------------------------------------------------
# Document verification
# ---------------------------------------------------------------------------
@bp.route("/admin/documents/<document_id>/verify", methods=["POST", "PATCH"])
@api_admin_required
def verify_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document:
        return failure("Document not found.", 404)

    payload = json_body()
    verified = payload.get("verified", True)
    if isinstance(verified, str):
        verified = verified.strip().lower() in ("1", "true", "yes")
    updated = current_app.supabase.set_document_verified(document_id, bool(verified))
    return success(document=serialize_document(updated or document))


# ---------------------------------------------------------------------------
# Course management
# ---------------------------------------------------------------------------
@bp.route("/admin/courses", methods=["GET"])
@api_admin_required
def list_courses():
    rows = current_app.supabase.list_courses(active_only=False)
    counts = current_app.supabase.application_counts_by_course()
    return success(courses=[serialize_course(c, application_counts=counts) for c in rows])


@bp.route("/admin/courses", methods=["POST"])
@api_admin_required
def create_course():
    payload, errors = _course_payload(json_body())
    if errors:
        return failure("Please correct the highlighted fields.", 422, errors)
    try:
        course = current_app.supabase.create_course(payload)
    except Exception:
        current_app.logger.exception("API create_course failed")
        return failure("Could not add the course. The code may already exist.", 409)
    if not course:
        return failure("Could not add the course. Please try again.", 500)
    return created(course=serialize_course(course))


@bp.route("/admin/courses/<course_id>", methods=["PATCH", "PUT"])
@api_admin_required
def update_course(course_id):
    if not current_app.supabase.get_course(course_id):
        return failure("Course not found.", 404)
    payload, errors = _course_payload(json_body(), partial=True)
    if errors:
        return failure("Please correct the highlighted fields.", 422, errors)
    try:
        course = current_app.supabase.update_course(course_id, payload)
    except Exception:
        current_app.logger.exception("API update_course failed")
        return failure("Could not update the course. Please try again.", 500)
    return success(course=serialize_course(course))


@bp.route("/admin/courses/<course_id>", methods=["DELETE"])
@api_admin_required
def delete_course(course_id):
    course = current_app.supabase.get_course(course_id)
    if not course:
        return failure("Course not found.", 404)
    if current_app.supabase.count_applications(course_id=course_id):
        return failure(
            "This course has applications and cannot be deleted. "
            "Deactivate it instead so existing records keep their course details.",
            409,
        )
    try:
        deleted = current_app.supabase.delete_course(course_id)
    except Exception:
        current_app.logger.exception("API delete_course failed")
        return failure("Could not delete the course. Deactivate it instead.", 500)
    if not deleted:
        return failure("Could not delete the course.", 500)
    return success(deleted=serialize_course(deleted))


@bp.route("/admin/courses/<course_id>/toggle", methods=["POST"])
@api_admin_required
def toggle_course(course_id):
    course = current_app.supabase.get_course(course_id)
    if not course:
        return failure("Course not found.", 404)
    new_state = not course.get("is_active", True)
    updated = current_app.supabase.set_course_active(course_id, new_state)
    return success(course=serialize_course(updated or course))


# ---------------------------------------------------------------------------
# CSV report export (same filters as the admin list)
# ---------------------------------------------------------------------------
@bp.route("/admin/export/applications.csv", methods=["GET"])
@api_admin_required
def export_applications():
    status = query_arg("status")
    if status and status not in APPLICATION_STATUSES:
        status = None
    course_id = query_arg("course_id") or query_arg("courseId")
    search = query_arg("q") or query_arg("search")
    date_from = _date_filter("from") or _date_filter("date_from")
    date_to = _date_filter("to") or _date_filter("date_to")
    if date_to:
        date_to = _end_of_day(date_to)

    rows = current_app.supabase.list_applications(
        status=status or None,
        course_id=course_id or None,
        search=search or None,
        date_from=date_from,
        date_to=date_to,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Application Number", "Status", "First Name", "Middle Name", "Last Name",
        "Date of Birth",
        "Gender", "Category", "Email", "Phone", "City", "State", "Postal Code",
        "Course Code", "Course Name", "Qualifying Exam", "Institution",
        "Board/University", "Stream", "Trade", "Affiliation", "Roll Number",
        "Passing Year", "Marks Obtained", "Total Marks", "Percentage",
        "Submitted At", "Reviewed At", "Admin Note",
    ])
    for app in rows:
        course = app.get("courses") or {}
        writer.writerow([
            app.get("application_number") or "(draft)",
            STATUS_LABELS.get(app.get("status"), app.get("status")),
            app.get("first_name"), app.get("middle_name"), app.get("last_name"),
            app.get("date_of_birth"),
            app.get("gender"), app.get("category"), app.get("email"), app.get("phone"),
            app.get("city"), app.get("state"), app.get("postal_code"),
            course.get("code"), course.get("name"),
            app.get("qualifying_exam"),
            app.get("institution_name") or app.get("school_name"),
            app.get("board_university"), app.get("stream"), app.get("trade"),
            app.get("affiliation"), app.get("roll_number"),
            app.get("passing_year"), app.get("marks_obtained"), app.get("marks_total"),
            app.get("percentage"), app.get("submitted_at"), app.get("reviewed_at"),
            app.get("admin_note"),
        ])

    filename = "admission_report_{}.csv".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )