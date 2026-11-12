"""Application endpoints for students (create, list, read, update, submit,
track). Administrators may also read a single application through here."""

from flask import Blueprint, current_app, request
from flask_login import current_user

from app.api.access import load_visible_application
from app.api.decorators import api_login_required, api_student_required
from app.api.responses import created, failure, success
from app.api.serializers import (
    serialize_application,
    serialize_document,
    serialize_history,
)
from app.api.utils import json_body, normalize_application_payload, query_arg
from app.models import APPLICATION_STATUSES
from app.services import application_service
from app.utils.validators import clean_str

bp = Blueprint("api_applications", __name__)


def _is_admin():
    return getattr(current_user, "role", None) == "admin"


def _filter_own(rows, status, course_id, search):
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if course_id:
        rows = [r for r in rows if str(r.get("course_id")) == str(course_id)]
    if search:
        term = search.lower()
        rows = [
            r
            for r in rows
            if term in (r.get("application_number") or "").lower()
            or term in (r.get("first_name") or "").lower()
            or term in (r.get("last_name") or "").lower()
            or term in (r.get("email") or "").lower()
        ]
    return rows


@bp.route("/applications", methods=["GET"])
@api_login_required
def list_applications():
    """Students receive only their own records; admins receive the full list."""
    status = query_arg("status")
    if status and status not in APPLICATION_STATUSES:
        return failure("Unknown status filter.", 400, {"status": "Unknown status filter."})
    course_id = query_arg("course_id") or query_arg("courseId")
    search = query_arg("q") or query_arg("search")

    if _is_admin():
        rows = current_app.supabase.list_applications(
            status=status or None, course_id=course_id or None, search=search or None
        )
    else:
        rows = current_app.supabase.list_applications_for_user(current_user.id)
        rows = _filter_own(rows, status, course_id, search)

    return success(applications=[serialize_application(r) for r in rows])


@bp.route("/applications/my", methods=["GET"])
@api_student_required
def my_applications():
    rows = current_app.supabase.list_applications_for_user(current_user.id)
    return success(applications=[serialize_application(r) for r in rows])


@bp.route("/applications", methods=["POST"])
@api_student_required
def create_application():
    payload = normalize_application_payload(json_body())
    application = application_service.create_application(
        current_app.supabase, current_user, payload
    )
    return created(application=serialize_application(application))


@bp.route("/applications/<application_id>", methods=["GET"])
@api_login_required
def get_application(application_id):
    application, error = load_visible_application(application_id, admin=True)
    if error:
        return error

    documents = current_app.supabase.list_documents(application_id)
    history = current_app.supabase.list_status_history(application_id)

    payload = serialize_application(application)
    payload["documents"] = [serialize_document(d) for d in documents]
    payload["history"] = [serialize_history(h) for h in history]
    return success(
        application=payload,
        documents=payload["documents"],
        history=payload["history"],
    )


@bp.route("/applications/<application_id>", methods=["PUT", "PATCH"])
@api_student_required
def update_application(application_id):
    payload = normalize_application_payload(json_body())
    application = application_service.update_application(
        current_app.supabase, current_user, application_id, payload
    )
    return success(application=serialize_application(application))


@bp.route("/applications/<application_id>/submit", methods=["POST"])
@api_student_required
def submit_application(application_id):
    application = application_service.submit_application(
        current_app.supabase, current_user, application_id
    )
    return success(application=serialize_application(application))


@bp.route("/applications/track", methods=["POST"])
@bp.route("/applications/track/<application_number>", methods=["GET"])
def track_application(application_number=None):
    """Look up an application by its number.

    Anonymous callers must also supply the email used on the application; a
    logged-in owner or an administrator may omit it.
    """
    if request.method == "POST":
        payload = json_body()
        number = clean_str(payload.get("number") or payload.get("application_number"), 40)
        email = clean_str(payload.get("email"), 254).lower()
    else:
        number = clean_str(application_number, 40)
        email = clean_str(request.args.get("email"), 254).lower()

    if not number:
        return failure("An application number is required.", 400)

    application = current_app.supabase.get_application_by_number(number)
    if not application:
        return failure("No application found with that application number.", 404)

    is_owner = current_user.is_authenticated and str(application.get("user_id")) == str(
        current_user.id
    )
    is_admin = current_user.is_authenticated and _is_admin()
    email_matches = bool(email) and email == (application.get("email") or "").lower()

    if not (is_owner or is_admin or email_matches):
        return failure(
            "Provide the email address used on the application to track it.", 403
        )

    return success(application=serialize_application(application))
