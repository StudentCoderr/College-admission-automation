"""Student area: dashboard, application form, documents, status tracking."""

import os
import uuid
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from app.models import DOCUMENT_TYPES, STATUS_LABELS, STUDENT_STATUSES
from app.services import application_service, profile_service
from app.utils.security import student_required
from app.utils.validators import (
    ValidationError,
    allowed_file,
    clean_name,
    clean_str,
    validate_application_form,
)

student_bp = Blueprint("student", __name__, url_prefix="/student")



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_owned_application(application_id):
    """Fetch an application and ensure it belongs to the current student."""
    application = current_app.supabase.get_application(application_id)
    if not application:
        abort(404)
    if str(application.get("user_id")) != str(current_user.id):
        # Do not reveal that the application exists.
        abort(404)
    return application


def _editable(status) -> bool:
    return status in ("draft", "correction_requested")


def _sync_profile_contact(data):
    """Keep the student's profile contact details in step with the application.

    Only non-empty submitted values are written, so a blank optional field on
    the application never erases a value already saved on the profile. The
    application itself is already saved, so a profile-sync hiccup must never
    turn that into an error page.
    """
    try:
        profile_service.sync_profile_contact(current_app.supabase, current_user, data)
    except Exception:
        current_app.logger.exception(
            "Could not sync profile contact after application save"
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@student_bp.route("/dashboard")
@student_required
def dashboard():
    applications = current_app.supabase.list_applications_for_user(current_user.id)
    counts = {}
    notices = []
    for app in applications:
        status = app.get("status")
        counts[status] = counts.get(status, 0) + 1
        # Attach the doc list so the dashboard can render a checklist.
        docs = current_app.supabase.list_documents(app.get("id"))
        app["documents"] = docs
        has_marks = any(d.get("doc_type") == "marks_card" for d in docs)
        if status in ("draft", "correction_requested") and not has_marks:
            notices.append({
                "kind": "warning",
                "text": "Add your marks card before submitting — it is mandatory.",
            })
        if status == "draft":
            notices.append({
                "kind": "info",
                "text": "You have an unfinished draft. Complete and submit it to begin review.",
            })
        if status == "correction_requested" and app.get("admin_note"):
            notices.append({
                "kind": "warning",
                "text": f"Correction requested: {app['admin_note']}",
            })
    if applications:
        # Most recently created application (list is newest-first by default).
        latest = applications[0]
        selected_course = latest.get("courses") if latest.get("courses") else None
        latest_id = latest.get("id")
    else:
        latest = None
        selected_course = None
        latest_id = None
    if not notices:
        notices.append({
            "kind": "success",
            "text": "All your applications are in order. Check back here for status updates.",
        })
    return render_template(
        "student/dashboard.html",
        applications=applications,
        counts=counts,
        status_labels=STATUS_LABELS,
        document_types=DOCUMENT_TYPES,
        latest=latest,
        latest_id=latest_id,
        selected_course=selected_course,
        notices=notices,
        student_statuses=STUDENT_STATUSES,
    )


# ---------------------------------------------------------------------------
# Student profile (name / phone visible to the admissions office)
# ---------------------------------------------------------------------------
@student_bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    errors = {}
    form = profile_service.profile_contact(current_user)
    if request.method == "POST":
        values, errors = profile_service.validate_profile_contact(
            request.form, current_user.email
        )
        if errors:
            for message in errors.values():
                flash(message, "danger")
            # Keep what the student typed so nothing is lost on the re-render.
            form.update(
                {
                    "first_name": clean_name(request.form.get("first_name")),
                    "middle_name": clean_name(request.form.get("middle_name")),
                    "last_name": clean_name(request.form.get("last_name")),
                    "phone": clean_str(request.form.get("phone"), 20).strip(),
                }
            )
        else:
            profile_service.save_profile_contact(
                current_app.supabase, current_user, values
            )
            flash("Your profile has been updated.", "success")
            return redirect(url_for("student.profile"))

    return render_template("student/profile.html", errors=errors, form=form)


# ---------------------------------------------------------------------------
# Create / edit application
# ---------------------------------------------------------------------------
@student_bp.route("/apply", methods=["GET", "POST"])
@student_required
def apply():
    courses = current_app.supabase.list_courses(active_only=True)
    # Prefill the whole contact section (names, email and phone) from the
    # student's saved profile so they never retype details we already hold.
    form = profile_service.profile_contact(current_user)
    errors = {}

    if request.method == "POST":
        try:
            data = validate_application_form(request.form)
            # Ensure the selected course really exists, is active and accepts
            # the applicant's qualification.
            course = current_app.supabase.get_course(data["course_id"])
            if not course or not course.get("is_active", True):
                raise ValidationError({"course_id": "The selected course is not available."})
            application_service.validate_course_eligibility(
                course, data.get("qualifying_exam")
            )

            application = current_app.supabase.create_application(current_user.id, data)
            if not application:
                raise ValidationError({"_form": "Could not create the application."})

            _sync_profile_contact(data)
            current_app.supabase.add_status_history(
                application["id"], "draft", "Application started.", current_user.id
            )
            flash("Application saved as draft. Upload your documents and submit.", "success")
            return redirect(url_for("student.application_detail", application_id=application["id"]))
        except ValidationError as exc:
            errors = exc.errors
            form = dict(request.form)
            for message in errors.values():
                flash(message, "danger")

    return render_template(
        "student/apply.html",
        courses=courses,
        form=form,
        errors=errors,
        application=None,
        document_types=DOCUMENT_TYPES,
        course_error=current_app.supabase.last_course_error,
    )


@student_bp.route("/application/<application_id>/edit", methods=["GET", "POST"])
@student_required
def edit_application(application_id):
    application = _get_owned_application(application_id)
    if not _editable(application.get("status")):
        flash("This application can no longer be edited.", "warning")
        return redirect(url_for("student.application_detail", application_id=application_id))

    courses = current_app.supabase.list_courses(active_only=True)
    errors = {}
    # The saved application is authoritative; only fields it is missing
    # (e.g. a legacy row with no phone) are filled from the profile.
    form = profile_service.merge_contact(
        application, profile_service.profile_contact(current_user)
    )

    if request.method == "POST":
        try:
            data = validate_application_form(request.form)
            course = current_app.supabase.get_course(data["course_id"])
            if not course or not course.get("is_active", True):
                raise ValidationError({"course_id": "The selected course is not available."})
            application_service.validate_course_eligibility(
                course, data.get("qualifying_exam")
            )

            # Never allow the client to set ownership, number, or status.
            data.pop("user_id", None)
            current_app.supabase.update_application(application_id, data)
            _sync_profile_contact(data)
            current_app.supabase.add_status_history(
                application_id, application.get("status", "draft"),
                "Application details updated by student.",
                current_user.id,
            )
            flash("Application updated.", "success")
            return redirect(url_for("student.application_detail", application_id=application_id))
        except ValidationError as exc:
            errors = exc.errors
            form = dict(request.form)
            for message in errors.values():
                flash(message, "danger")

    return render_template(
        "student/apply.html",
        courses=courses,
        form=form,
        errors=errors,
        application=application,
        document_types=DOCUMENT_TYPES,
        course_error=current_app.supabase.last_course_error,
    )


# ---------------------------------------------------------------------------
# Detail, submit, documents
# ---------------------------------------------------------------------------
@student_bp.route("/application/<application_id>")
@student_required
def application_detail(application_id):
    application = _get_owned_application(application_id)
    documents = current_app.supabase.list_documents(application_id)
    history = current_app.supabase.list_status_history(application_id)
    return render_template(
        "student/application_detail.html",
        application=application,
        documents=documents,
        history=history,
        document_types=DOCUMENT_TYPES,
        status_labels=STATUS_LABELS,
        editable=_editable(application.get("status")),
    )


@student_bp.route("/application/<application_id>/submit", methods=["POST"])
@student_required
def submit_application(application_id):
    application = _get_owned_application(application_id)
    if not _editable(application.get("status")):
        flash("This application has already been submitted.", "warning")
        return redirect(url_for("student.application_detail", application_id=application_id))

    documents = current_app.supabase.list_documents(application_id)
    if not any(d.get("doc_type") == "marks_card" for d in documents):
        flash("Please upload at least your marks card before submitting.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))

    application_number = application.get("application_number") or \
        current_app.supabase.generate_application_number()

    current_app.supabase.update_application(
        application_id,
        {
            "status": "submitted",
            "application_number": application_number,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "admin_note": None,
        },
    )
    current_app.supabase.add_status_history(
        application_id, "submitted", "Application submitted by student.", current_user.id
    )
    flash(f"Application submitted successfully. Your application number is {application_number}.",
          "success")
    return redirect(url_for("student.application_detail", application_id=application_id))


@student_bp.route("/application/<application_id>/upload", methods=["POST"])
@student_required
def upload_document(application_id):
    application = _get_owned_application(application_id)
    if not _editable(application.get("status")):
        flash("Documents can only be changed while the application is editable.", "warning")
        return redirect(url_for("student.application_detail", application_id=application_id))

    doc_type = clean_str(request.form.get("doc_type"))
    if doc_type not in DOCUMENT_TYPES:
        flash("Select a valid document type.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file to upload.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))

    filename = file.filename
    if not allowed_file(filename, current_app.config["ALLOWED_EXTENSIONS"]):
        flash("Only PDF, JPG and PNG files are allowed.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))

    # Read once so we can validate the size and detect the real MIME type.
    file_bytes = file.read()
    if len(file_bytes) == 0:
        flash("The uploaded file is empty.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))
    if len(file_bytes) > current_app.config["MAX_CONTENT_LENGTH"]:
        flash("File too large. Maximum size is 5 MB.", "danger")
        return redirect(url_for("student.application_detail", application_id=application_id))

    mime_type = file.mimetype or "application/octet-stream"
    if mime_type not in current_app.config["ALLOWED_MIME_TYPES"]:
        # Some browsers send a generic type; fall back to extension mapping.
        ext = filename.rsplit(".", 1)[1].lower()
        mime_type = {
            "pdf": "application/pdf",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }.get(ext, "application/octet-stream")

    safe_name = os.path.basename(filename).replace(" ", "_")
    # Path is namespaced by application id so students can never read others' files.
    storage_path = f"applications/{application_id}/{uuid.uuid4().hex}_{safe_name}"

    try:
        current_app.supabase.upload_document(storage_path, file_bytes, mime_type)
        current_app.supabase.create_document(
            application_id=application_id,
            user_id=current_user.id,
            doc_type=doc_type,
            file_name=safe_name,
            storage_path=storage_path,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
        )
        current_app.supabase.add_status_history(
            application_id, application.get("status", "draft"),
            f"Document uploaded: {DOCUMENT_TYPES[doc_type]}.", current_user.id,
        )
        flash("Document uploaded successfully.", "success")
    except Exception:
        current_app.logger.exception("Document upload failed")
        flash("There was a problem uploading your document. Please try again.", "danger")

    return redirect(url_for("student.application_detail", application_id=application_id))


@student_bp.route("/document/<document_id>/delete", methods=["POST"])
@student_required
def delete_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document or str(document.get("user_id")) != str(current_user.id):
        abort(404)
    application_id = document.get("application_id")
    application = _get_owned_application(application_id)
    if not _editable(application.get("status")):
        flash("Documents can only be changed while the application is editable.", "warning")
        return redirect(url_for("student.application_detail", application_id=application_id))

    current_app.supabase.delete_object(document.get("storage_path"))
    current_app.supabase.delete_document(document_id)
    flash("Document removed.", "success")
    return redirect(url_for("student.application_detail", application_id=application_id))


@student_bp.route("/document/<document_id>")
@student_required
def view_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document or str(document.get("user_id")) != str(current_user.id):
        abort(404)
    url = current_app.supabase.create_signed_url(
        document["storage_path"], current_app.config["SIGNED_URL_EXPIRES_IN"]
    )
    if not url:
        flash("Could not open this document.", "danger")
        return redirect(url_for("student.application_detail", application_id=document["application_id"]))
    return redirect(url)
