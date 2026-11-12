"""Application management service.

The lifecycle of an admission application (create, edit, submit and admin
review) lives here so the rules are enforced in exactly one place, whether the
request arrives from the HTML views or the JSON API. The functions receive the
Supabase service explicitly, which keeps them easy to unit-test.
"""

from datetime import datetime, timezone

from app.services.errors import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from app.utils.validators import (
    QUALIFICATION_LABELS,
    ValidationError as FormValidationError,
    validate_application_form,
)

# A student may only edit an application while it is in one of these states.
EDITABLE_STATUSES = ("draft", "correction_requested")

# Statuses an administrator is allowed to move an application to.
REVIEW_STATUSES = ("under_review", "approved", "rejected", "correction_requested")

# Fields a client must never be able to set directly.
PROTECTED_FIELDS = (
    "user_id",
    "status",
    "application_number",
    "reviewed_by",
    "reviewed_at",
    "submitted_at",
    "created_at",
    "updated_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _owned_application(service, application_id, user):
    """Return the application only when it belongs to ``user``.

    A missing application and someone else's application raise the same error
    so we never reveal that a record exists.
    """
    application = service.get_application(application_id)
    if not application or str(application.get("user_id")) != str(user.id):
        raise NotFoundError("Application not found.")
    return application


def validate_course_eligibility(course, qualification):
    """Raise ``ValidationError`` when the applicant's qualification is not
    allowed for the course.

    A course without ``eligible_qualifications`` (NULL / empty) is open to all
    qualifications. When a course restricts eligibility, the applicant must
    hold one of the listed qualifications. Legacy application rows whose
    ``qualifying_exam`` is free text (not an SSLC/PUC/ITI value) are never
    blocked — we cannot determine their eligibility.
    """
    allowed = course.get("eligible_qualifications") if course else None
    if not allowed:
        return
    allowed = [str(item).strip().lower() for item in allowed if str(item).strip()]
    if not allowed:
        return
    qual = (qualification or "").strip().lower()
    if qual in allowed:
        return
    if qual not in QUALIFICATION_LABELS:
        return  # legacy free-text row; cannot determine eligibility
    labels = ", ".join(QUALIFICATION_LABELS.get(item, item.upper()) for item in allowed)
    qual_label = QUALIFICATION_LABELS.get(qual, qual)
    raise FormValidationError(
        {"course_id": (
            f"This course requires {labels}. Your qualification "
            f"({qual_label}) is not eligible."
        )}
    )


def _resolve_course(service, course_id, qualification=None):
    course = service.get_course(course_id)
    if not course or not course.get("is_active", True):
        raise ValidationError(
            "The selected course is not available.",
            errors={"course_id": "The selected course is not available."},
        )
    validate_course_eligibility(course, qualification)
    return course


def _ensure_active(user):
    """Only active student accounts may create or change applications.

    Administrators are never blocked here (they do not own applications). An
    inactive or withdrawn student keeps their history but cannot start or
    submit new applications.
    """
    if getattr(user, "role", "student") == "student" and not getattr(
        user, "is_active", True
    ):
        raise ConflictError(
            "Your account is not active, so you cannot submit applications. "
            "Please contact the administrator.",
            403,
        )


def create_application(service, user, form):
    """Validate and create a new draft application for ``user``."""
    _ensure_active(user)
    data = validate_application_form(form)
    _resolve_course(service, data.get("course_id"), data.get("qualifying_exam"))

    application = service.create_application(user.id, data)
    if not application:
        raise ServiceError("Could not create the application. Please try again.", 500)
    service.add_status_history(application["id"], "draft", "Application started.", user.id)
    return application


def update_application(service, user, application_id, form):
    """Update an editable application owned by ``user``."""
    _ensure_active(user)
    application = _owned_application(service, application_id, user)
    if application.get("status") not in EDITABLE_STATUSES:
        raise ConflictError("This application can no longer be edited.", 409)

    data = validate_application_form(form)
    _resolve_course(service, data.get("course_id"), data.get("qualifying_exam"))
    for field in PROTECTED_FIELDS:
        data.pop(field, None)

    updated = service.update_application(application_id, data)
    service.add_status_history(
        application_id,
        application.get("status", "draft"),
        "Application details updated by student.",
        user.id,
    )
    return updated or service.get_application(application_id)


def submit_application(service, user, application_id):
    """Submit an editable application, generating its application number."""
    _ensure_active(user)
    application = _owned_application(service, application_id, user)
    if application.get("status") not in EDITABLE_STATUSES:
        raise ConflictError("This application has already been submitted.", 409)

    documents = service.list_documents(application_id)
    if not any(d.get("doc_type") == "marks_card" for d in documents):
        raise ConflictError("Please upload at least your marks card before submitting.", 409)

    application_number = application.get("application_number") or service.generate_application_number()
    updated = service.update_application(
        application_id,
        {
            "status": "submitted",
            "application_number": application_number,
            "submitted_at": _now(),
            "admin_note": None,
        },
    )
    service.add_status_history(
        application_id, "submitted", "Application submitted by student.", user.id
    )
    return updated or application


def change_status(service, admin, application_id, status, note):
    """Administrator review transition (approve/reject/request correction)."""
    if status not in REVIEW_STATUSES:
        raise ValidationError(
            "Invalid status transition.", errors={"status": "Invalid status transition."}
        )

    application = service.get_application(application_id)
    if not application:
        raise NotFoundError("Application not found.")

    if status in ("rejected", "correction_requested") and not note:
        raise ValidationError(
            "A note is required when rejecting or requesting a correction.",
            errors={"note": "A note is required when rejecting or requesting a correction."},
        )

    updated = service.update_application(
        application_id,
        {
            "status": status,
            "admin_note": note or application.get("admin_note"),
            "reviewed_by": admin.id,
            "reviewed_at": _now(),
        },
    )
    service.add_status_history(application_id, status, note or status, admin.id)
    return updated or application
