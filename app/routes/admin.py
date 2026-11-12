"""Administrator area: dashboard, review workflow, course management, reports."""

import csv
import hashlib
import io
import math
import secrets
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import (
    APPLICATION_STATUSES,
    DOCUMENT_TYPES,
    STATUS_LABELS,
    STUDENT_STATUSES,
    STUDENT_STATUS_LABELS,
    User,
)
from app.utils.security import admin_required
from app.utils.validators import (
    ValidationError,
    clean_str,
    is_valid_email,
    validate_course_fields,
    validate_password,
    validate_student_form,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

REVIEW_ACTIONS = {
    "under_review": "Marked as under review.",
    "approved": "Application approved.",
    "rejected": "Application rejected.",
    "correction_requested": "Correction requested from the applicant.",
}

# Whitelisted columns for the students table sorting (never passed raw).
STUDENT_SORTABLE = {
    "created_at": "created_at",
    "name": "full_name",
    "email": "email",
    "status": "status",
}

# How long a student's one-time password-setup link stays valid.
INVITE_TTL_DAYS = 7


def _audit(action, entity_type=None, entity_id=None, details=None):
    """Record an admin action. Auditing must never break the action itself."""
    try:
        current_app.supabase.add_audit_log(
            action=action,
            actor_id=current_user.id if current_user.is_authenticated else None,
            actor_email=getattr(current_user, "email", None),
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            ip_address=request.remote_addr,
        )
    except Exception:  # pragma: no cover - defensive
        current_app.logger.exception("admin audit log failed")


def _status_chart(counts):
    """Status distribution for the dashboard/report charts (drafts excluded)."""
    order = ["submitted", "under_review", "correction_requested", "approved", "rejected"]
    return [
        {"key": key, "label": STATUS_LABELS.get(key, key), "value": counts.get(key, 0)}
        for key in order
    ]


# ---------------------------------------------------------------------------
# Administrator login (separate from the student login)
# ---------------------------------------------------------------------------
@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    """Dedicated sign-in page. Only accounts with the admin role are admitted.

    The shared student login never grants admin access; this page additionally
    refuses student accounts so the two portals stay clearly separated.
    """
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        flash("You are signed in as a student. Use the student portal.", "warning")
        return redirect(url_for("student.dashboard"))

    if request.method == "POST":
        email = clean_str(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")
        next_url = request.args.get("next") or request.form.get("next")

        if not is_valid_email(email) or not password:
            flash("Enter a valid email and password.", "danger")
            return render_template("admin/login.html", email=email)

        row = current_app.supabase.get_user_by_email(email)
        # Check the password first, then the role, and keep the message generic
        # so the page never confirms whether an email address exists.
        if not row or not check_password_hash(row.get("password_hash", ""), password):
            flash("Invalid email or password.", "danger")
            return render_template("admin/login.html", email=email)

        user = User(row)
        if not user.is_admin:
            flash("This account does not have administrator access.", "danger")
            return render_template("admin/login.html", email=email)

        if not row.get("is_active", True):
            flash("This administrator account has been deactivated.", "danger")
            return render_template("admin/login.html", email=email)

        login_user(user)
        _audit(
            "admin_login",
            entity_type="user",
            entity_id=user.id,
            details="Administrator signed in.",
        )
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html", email="")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    counts = current_app.supabase.status_counts()
    recent = current_app.supabase.list_applications()[:8]
    course_stats = _course_stats()
    course_counts = current_app.supabase.course_status_counts()
    students_total = current_app.supabase.count_students()
    course_chart = [
        {"label": c.get("code") or c.get("name"), "value": c.get("applications_count", 0)}
        for c in sorted(
            course_stats, key=lambda c: c.get("applications_count", 0), reverse=True
        )[:8]
    ]
    return render_template(
        "admin/dashboard.html",
        counts=counts,
        recent=recent,
        course_stats=course_stats,
        course_counts=course_counts,
        students_total=students_total,
        status_chart=_status_chart(counts),
        course_chart=course_chart,
        status_labels=STATUS_LABELS,
    )


def _course_stats():
    """Every course with its application count and remaining available seats."""
    counts = current_app.supabase.application_counts_by_course()
    stats = []
    for course in current_app.supabase.list_courses():
        course_id = str(course.get("id"))
        applications = counts.get(course_id, 0)
        seats_total = course.get("seats_total") or 0
        stats.append({
            **course,
            "applications_count": applications,
            "seats_available": max(0, seats_total - applications),
        })
    return stats


# ---------------------------------------------------------------------------
# Notifications (action centre)
# ---------------------------------------------------------------------------
@admin_bp.route("/notifications")
@admin_required
def notifications():
    counts = current_app.supabase.status_counts()
    pending = (
        counts.get("submitted", 0)
        + counts.get("under_review", 0)
        + counts.get("correction_requested", 0)
    )
    unverified_count = current_app.supabase.count_documents(unverified_only=True)
    unverified = current_app.supabase.list_documents_all(limit=12, unverified_only=True)
    announcements = current_app.supabase.list_announcements(limit=6)
    recent = current_app.supabase.list_audit_log(limit=12)
    recent_apps = current_app.supabase.list_applications(limit=8)
    return render_template(
        "admin/notifications.html",
        counts=counts,
        pending=pending,
        unverified_count=unverified_count,
        unverified=unverified,
        announcements=announcements,
        recent=recent,
        recent_apps=recent_apps,
        status_labels=STATUS_LABELS,
        document_types=DOCUMENT_TYPES,
    )


# ---------------------------------------------------------------------------
# Application list (search + filter)
# ---------------------------------------------------------------------------
@admin_bp.route("/applications")
@admin_required
def applications():
    status = clean_str(request.args.get("status"))
    course_id = clean_str(request.args.get("course_id"))
    search = clean_str(request.args.get("q"), 120)
    date_from = clean_str(request.args.get("date_from"), 12)
    date_to = clean_str(request.args.get("date_to"), 12)

    if status and status not in APPLICATION_STATUSES:
        status = None

    rows = current_app.supabase.list_applications(
        status=status or None,
        course_id=course_id or None,
        search=search or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    courses = current_app.supabase.list_courses()

    return render_template(
        "admin/applications.html",
        applications=rows,
        courses=courses,
        statuses=APPLICATION_STATUSES,
        status_labels=STATUS_LABELS,
        filters={
            "status": status or "",
            "course_id": course_id or "",
            "q": search or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
        },
    )


# ---------------------------------------------------------------------------
# Application detail + review actions
# ---------------------------------------------------------------------------
@admin_bp.route("/application/<application_id>")
@admin_required
def application_detail(application_id):
    application = current_app.supabase.get_application(application_id)
    if not application:
        abort(404)
    documents = current_app.supabase.list_documents(application_id)
    history = current_app.supabase.list_status_history(application_id)
    return render_template(
        "admin/application_detail.html",
        application=application,
        documents=documents,
        history=history,
        statuses=APPLICATION_STATUSES,
        status_labels=STATUS_LABELS,
    )


@admin_bp.route("/application/<application_id>/status", methods=["POST"])
@admin_required
def update_status(application_id):
    application = current_app.supabase.get_application(application_id)
    if not application:
        abort(404)

    new_status = clean_str(request.form.get("status"))
    note = clean_str(request.form.get("note"), 1000)

    if new_status not in REVIEW_ACTIONS:
        flash("Invalid status transition.", "danger")
        return redirect(url_for("admin.application_detail", application_id=application_id))

    if new_status in ("rejected", "correction_requested") and not note:
        flash("A note is required when rejecting or requesting a correction.", "danger")
        return redirect(url_for("admin.application_detail", application_id=application_id))

    current_app.supabase.update_application(
        application_id,
        {
            "status": new_status,
            "admin_note": note or application.get("admin_note"),
            "reviewed_by": current_user.id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    current_app.supabase.add_status_history(
        application_id, new_status, note or REVIEW_ACTIONS[new_status], current_user.id
    )
    _audit(
        "application_status_change",
        entity_type="application",
        entity_id=application_id,
        details="Status changed to '{}'{}".format(
            new_status, f" — {note}" if note else ""
        ),
    )
    flash(f"Application status updated to '{STATUS_LABELS.get(new_status, new_status)}'.", "success")
    return redirect(url_for("admin.application_detail", application_id=application_id))


@admin_bp.route("/document/<document_id>/verify", methods=["POST"])
@admin_required
def verify_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document:
        abort(404)
    verified = request.form.get("verified") == "true"
    current_app.supabase.set_document_verified(document_id, verified)
    _audit(
        "document_verify",
        entity_type="document",
        entity_id=document_id,
        details="Document {}.".format("verified" if verified else "marked unverified"),
    )
    flash("Document marked as verified." if verified else "Document verification removed.", "success")
    return redirect(url_for("admin.application_detail", application_id=document["application_id"]))


@admin_bp.route("/document/<document_id>")
@admin_required
def view_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document:
        abort(404)
    url = current_app.supabase.create_signed_url(
        document["storage_path"], current_app.config["SIGNED_URL_EXPIRES_IN"]
    )
    if not url:
        flash("Could not open this document.", "danger")
        return redirect(url_for("admin.application_detail", application_id=document["application_id"]))
    return redirect(url)


# ---------------------------------------------------------------------------
# Course management
# ---------------------------------------------------------------------------
@admin_bp.route("/courses")
@admin_required
def courses():
    rows = _course_stats()
    service = current_app.supabase
    missing = getattr(service, "course_schema_missing", None)
    return render_template(
        "admin/courses.html",
        courses=rows,
        course_error=getattr(service, "last_course_error", None),
        missing_course_columns=missing() if callable(missing) else [],
    )


@admin_bp.route("/courses/create", methods=["POST"])
@admin_required
def create_course():
    payload, error = _course_payload()
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.courses"))
    try:
        created_course = current_app.supabase.create_course(payload)
        _audit(
            "course_create",
            entity_type="course",
            entity_id=(created_course or {}).get("id") or payload.get("code"),
            details=f"Added course {payload.get('code')} ({payload.get('program_type')}).",
        )
        flash("Course added.", "success")
    except Exception:
        current_app.logger.exception("create_course failed")
        flash("Could not add the course. The code may already exist.", "danger")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<course_id>/update", methods=["POST"])
@admin_required
def update_course(course_id):
    if not current_app.supabase.get_course(course_id):
        abort(404)
    payload, error = _course_payload()
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.courses"))
    try:
        current_app.supabase.update_course(course_id, payload)
        _audit(
            "course_update",
            entity_type="course",
            entity_id=course_id,
            details=f"Updated course {payload.get('code')}.",
        )
        flash("Course updated.", "success")
    except Exception:
        current_app.logger.exception("update_course failed")
        flash("Could not update the course.", "danger")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<course_id>/toggle", methods=["POST"])
@admin_required
def toggle_course(course_id):
    course = current_app.supabase.get_course(course_id)
    if not course:
        abort(404)
    new_state = not course.get("is_active", True)
    current_app.supabase.set_course_active(course_id, new_state)
    _audit(
        "course_activate" if new_state else "course_deactivate",
        entity_type="course",
        entity_id=course_id,
        details=f"{course.get('code')} {'activated' if new_state else 'deactivated'}.",
    )
    flash(f"Course {'activated' if new_state else 'deactivated'}.", "success")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<course_id>/delete", methods=["POST"])
@admin_required
def delete_course(course_id):
    course = current_app.supabase.get_course(course_id)
    if not course:
        abort(404)

    # Keep submitted/draft applications meaningful. Courses that already have
    # applications should be deactivated rather than removed.
    if current_app.supabase.count_applications(course_id=course_id):
        flash(
            "This course has applications and cannot be deleted. "
            "Deactivate it instead so existing records keep their course details.",
            "warning",
        )
        return redirect(url_for("admin.courses"))

    try:
        deleted = current_app.supabase.delete_course(course_id)
        if not deleted:
            flash("Could not delete the course.", "danger")
            return redirect(url_for("admin.courses"))
        _audit(
            "course_delete",
            entity_type="course",
            entity_id=course_id,
            details=f"Deleted course {course.get('code')} ({course.get('program_type')}).",
        )
        flash(f"Course {course.get('code')} deleted.", "success")
    except Exception:
        current_app.logger.exception("delete_course failed")
        flash("Could not delete the course. Deactivate it instead.", "danger")
    return redirect(url_for("admin.courses"))


def _course_payload():
    code = clean_str(request.form.get("code"), 20).upper()
    name = clean_str(request.form.get("name"), 150)
    description = clean_str(request.form.get("description"), 500)
    try:
        duration = int(request.form.get("duration_years", 0))
        seats = int(request.form.get("seats_total", 0))
    except (TypeError, ValueError):
        return None, "Duration and seats must be whole numbers."

    if not code or not name:
        return None, "Course code and name are required."
    if not (1 <= duration <= 10):
        return None, "Duration must be between 1 and 10 years."
    if not (1 <= seats <= 2000):
        return None, "Seats must be between 1 and 2000."

    # Eligibility checkboxes arrive as a list (request.form.getlist); the base
    # form dict would collapse them to a single value.
    form_values = request.form.to_dict()
    form_values["eligible_qualifications"] = request.form.getlist(
        "eligible_qualifications"
    )
    extras, extra_errors = validate_course_fields(form_values)
    if extra_errors:
        return None, " ".join(extra_errors.values())

    return {
        "code": code,
        "name": name,
        "description": description,
        "duration_years": duration,
        "seats_total": seats,
        "program_type": extras["program_type"],
        "eligibility": extras["eligibility"],
        "tuition_fee": extras["tuition_fee"],
        "eligible_qualifications": extras["eligible_qualifications"],
    }, None


# ---------------------------------------------------------------------------
# Students management
# ---------------------------------------------------------------------------
def _attach_student_application_counts(rows):
    """Add application counts and the registration reference to student rows.

    The registration reference is the admin-assigned ``registration_number``
    when present, otherwise the ADM number from the student's application.
    """
    counts = current_app.supabase.application_counts_by_user()
    numbers = current_app.supabase.application_numbers_by_user()
    enriched = []
    for row in rows:
        item = dict(row)
        uid = str(row.get("id"))
        item["applications_count"] = counts.get(uid, 0)
        item["registration_number"] = row.get("registration_number") or numbers.get(uid)
        enriched.append(item)
    return enriched


def _invite_setup_url(token):
    """Absolute one-time password-setup URL for a student invitation."""
    return url_for("auth.setup_password", token=token, _external=True)


def _issue_invitation(user_id):
    """Create a fresh one-time setup token for a student.

    Only the SHA-256 hash is stored; the raw token is returned so it can be
    shown to the administrator exactly once. No password is ever generated,
    stored in plain text, or displayed.
    """
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
    current_app.supabase.set_invitation(user_id, token_hash, expires_at)
    return token


@admin_bp.route("/students")
@admin_required
def students():
    search = clean_str(request.args.get("q"), 120)
    status = clean_str(request.args.get("status"))
    if status not in STUDENT_STATUSES:
        status = ""
    sort = clean_str(request.args.get("sort")) or "created_at"
    order_by = STUDENT_SORTABLE.get(sort, "created_at")
    order = clean_str(request.args.get("order")) or "desc"
    descending = order != "asc"

    try:
        per_page = int(request.args.get("per_page", 10))
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(5, min(per_page, 100))
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    total = current_app.supabase.count_students(
        search=search or None, status=status or None
    )
    rows = current_app.supabase.list_students(
        search=search or None,
        status=status or None,
        order_by=order_by,
        descending=descending,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    rows = _attach_student_application_counts(rows)
    pages = max(1, math.ceil(total / per_page)) if per_page else 1

    return render_template(
        "admin/students.html",
        students=rows,
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        status_labels=STUDENT_STATUS_LABELS,
        status_options=STUDENT_STATUSES,
        filters={
            "q": search or "",
            "status": status,
            "sort": sort,
            "order": "desc" if descending else "asc",
        },
    )


def _courses_context():
    """Return (courses list, id -> course map) for course selectors/labels."""
    courses = current_app.supabase.list_courses()
    return courses, {str(c.get("id")): c for c in courses}


def _student_or_404(user_id):
    student = current_app.supabase.get_student(user_id)
    if not student:
        abort(404)
    return student


def _ensure_student_unique(values, exclude_id=None):
    """Reject duplicate email addresses and registration numbers."""
    errors = {}
    existing = current_app.supabase.get_user_by_email(values["email"])
    if existing and str(existing.get("id")) != str(exclude_id or ""):
        errors["email"] = "A user with this email address already exists."
    registration = values.get("registration_number")
    if registration and current_app.supabase.registration_number_exists(
        registration, exclude_id=exclude_id
    ):
        errors["registration_number"] = "This registration number is already in use."
    if errors:
        raise ValidationError(errors)


def _ensure_course(course_id):
    if course_id and not current_app.supabase.get_course(course_id):
        raise ValidationError({"assigned_course_id": "Select a valid course."})


@admin_bp.route("/students/<user_id>")
@admin_required
def student_detail(user_id):
    student = _student_or_404(user_id)
    applications = current_app.supabase.list_applications_for_user(user_id)
    _, course_map = _courses_context()
    return render_template(
        "admin/student_detail.html",
        student=student,
        applications=applications,
        status_labels=STATUS_LABELS,
        student_status_labels=STUDENT_STATUS_LABELS,
        student_statuses=STUDENT_STATUSES,
        assigned_course=course_map.get(str(student.get("assigned_course_id"))),
    )


@admin_bp.route("/students/new", methods=["GET", "POST"])
@admin_required
def student_new():
    courses = current_app.supabase.list_courses()
    form = {}
    errors = {}
    if request.method == "POST":
        form = request.form.to_dict(flat=True)
        try:
            values, errors = validate_student_form(form)
            if errors:
                raise ValidationError(errors)
            _ensure_student_unique(values)
            _ensure_course(values.get("assigned_course_id"))
            # The account is created with an unusable random password; the
            # student sets their own via a one-time link. No password is ever
            # generated for display or stored in plain text.
            placeholder = generate_password_hash(secrets.token_urlsafe(32), method="scrypt")
            created = current_app.supabase.create_user(
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
            if not created:
                raise ValidationError({"_form": "Could not create the student record."})
            token = _issue_invitation(created["id"]) if values["status"] == "active" else None
            _audit(
                "student_create",
                entity_type="user",
                entity_id=created.get("id"),
                details="Created student {} ({}).".format(values["email"], values["status"]),
            )
            flash("Student {} was added.".format(values["email"]), "success")
            return render_template(
                "admin/student_invite.html",
                student=created,
                setup_url=_invite_setup_url(token) if token else None,
            )
        except ValidationError as exc:
            errors = exc.errors
            flash("Please correct the highlighted fields.", "danger")

    return render_template(
        "admin/student_form.html",
        form=form,
        errors=errors,
        mode="new",
        student=None,
        courses=courses,
        student_statuses=STUDENT_STATUSES,
        student_status_labels=STUDENT_STATUS_LABELS,
    )


@admin_bp.route("/students/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def student_edit(user_id):
    student = _student_or_404(user_id)
    courses = current_app.supabase.list_courses()
    errors = {}
    if request.method == "POST":
        form = request.form.to_dict(flat=True)
        try:
            values, errors = validate_student_form(form)
            if errors:
                raise ValidationError(errors)
            _ensure_student_unique(values, exclude_id=user_id)
            _ensure_course(values.get("assigned_course_id"))
            payload = {
                "first_name": values["first_name"],
                "middle_name": values["middle_name"],
                "last_name": values["last_name"],
                "full_name": values["full_name"],
                "email": values["email"],
                "phone": values["phone"] or None,
                "registration_number": values["registration_number"],
                "assigned_course_id": values["assigned_course_id"],
            }
            current_app.supabase.set_student_status(
                user_id, values["status"], extra=payload
            )
            _audit(
                "student_update",
                entity_type="user",
                entity_id=user_id,
                details="Updated student {} ({}).".format(values["email"], values["status"]),
            )
            flash("Student details updated.", "success")
            return redirect(url_for("admin.student_detail", user_id=user_id))
        except ValidationError as exc:
            errors = exc.errors
            flash("Please correct the highlighted fields.", "danger")
    else:
        form = dict(student)

    return render_template(
        "admin/student_form.html",
        form=form,
        errors=errors,
        mode="edit",
        student=student,
        courses=courses,
        student_statuses=STUDENT_STATUSES,
        student_status_labels=STUDENT_STATUS_LABELS,
    )


@admin_bp.route("/students/<user_id>/status", methods=["POST"])
@admin_required
def set_student_status(user_id):
    student = _student_or_404(user_id)
    # Accept the status field, falling back to the legacy activate/deactivate
    # action names so older forms keep working.
    status = clean_str(request.form.get("status")).lower()
    if not status:
        action = clean_str(request.form.get("action"))
        status = {"activate": "active", "deactivate": "inactive"}.get(action, "")
    if status not in STUDENT_STATUSES:
        flash("Unknown account status.", "danger")
        return redirect(url_for("admin.student_detail", user_id=user_id))

    reason = clean_str(request.form.get("reason"), 200)
    current_app.supabase.set_student_status(user_id, status)
    _audit(
        "student_status_change",
        entity_type="user",
        entity_id=user_id,
        details="{} set to {}{}".format(
            student.get("email"),
            status,
            " (reason: {})".format(reason) if reason else "",
        ),
    )
    flash(
        "Student account marked as {}.".format(
            STUDENT_STATUS_LABELS.get(status, status)
        ),
        "success",
    )
    return redirect(url_for("admin.student_detail", user_id=user_id))


@admin_bp.route("/students/<user_id>/invite", methods=["POST"])
@admin_required
def student_invite(user_id):
    student = _student_or_404(user_id)
    token = _issue_invitation(user_id)
    _audit(
        "student_invite",
        entity_type="user",
        entity_id=user_id,
        details="Issued a password-setup link for {}.".format(student.get("email")),
    )
    return render_template(
        "admin/student_invite.html",
        student=student,
        setup_url=_invite_setup_url(token),
    )


@admin_bp.route("/students/<user_id>/delete", methods=["GET", "POST"])
@admin_required
def student_delete(user_id):
    """Permanently remove a student. Requires an explicit second confirmation."""
    student = _student_or_404(user_id)
    applications = current_app.supabase.list_applications_for_user(user_id)
    document_paths = current_app.supabase.document_paths_by_user(user_id)

    if request.method == "POST":
        confirm = clean_str(request.form.get("confirm"))
        reason = clean_str(request.form.get("reason"), 300)

        # Defence in depth: student-only endpoint, but never touch an admin or
        # the signed-in administrator's own account.
        if student.get("role") == "admin":
            flash("Administrator accounts cannot be deleted here.", "danger")
            return redirect(url_for("admin.student_detail", user_id=user_id))
        if str(user_id) == str(current_user.id):
            flash("You cannot delete your own account.", "danger")
            return redirect(url_for("admin.student_delete", user_id=user_id))
        if confirm != "DELETE":
            flash("Type DELETE to confirm permanent deletion.", "danger")
            return redirect(url_for("admin.student_delete", user_id=user_id))
        if not reason:
            flash("A reason is required for permanent deletion.", "danger")
            return redirect(url_for("admin.student_delete", user_id=user_id))

        # Remove the stored files first, then the row. Foreign keys cascade, so
        # applications, documents and status history are removed atomically.
        for path in document_paths:
            current_app.supabase.delete_object(path)
        current_app.supabase.delete_user(user_id)
        _audit(
            "student_delete",
            entity_type="user",
            entity_id=user_id,
            details="Permanently deleted student {} - reason: {}".format(
                student.get("email"), reason
            ),
        )
        flash(
            "Student {} and all associated admission records were permanently "
            "deleted.".format(student.get("email")),
            "success",
        )
        return redirect(url_for("admin.students"))

    return render_template(
        "admin/student_delete.html",
        student=student,
        applications=applications,
        document_count=len(document_paths),
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@admin_bp.route("/reports")
@admin_required
def reports():
    counts = current_app.supabase.status_counts()
    course_stats = _course_stats()
    course_counts = current_app.supabase.course_status_counts()
    monthly = current_app.supabase.applications_by_month(6)
    audit = current_app.supabase.list_audit_log(limit=15)
    return render_template(
        "admin/reports.html",
        counts=counts,
        course_stats=course_stats,
        course_counts=course_counts,
        monthly=monthly,
        audit=audit,
        status_chart=_status_chart(counts),
        status_labels=STATUS_LABELS,
    )


# ---------------------------------------------------------------------------
# Admin profile
# ---------------------------------------------------------------------------
@admin_bp.route("/profile", methods=["GET", "POST"])
@admin_required
def profile():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        row = current_app.supabase.get_user_by_id(current_user.id)
        if not row or not check_password_hash(
            row.get("password_hash", ""), current_password
        ):
            flash("Your current password is incorrect.", "danger")
        else:
            error = validate_password(new_password)
            if error:
                flash(error, "danger")
            elif new_password != confirm:
                flash("The new passwords do not match.", "danger")
            else:
                current_app.supabase.update_user(
                    current_user.id,
                    {"password_hash": generate_password_hash(new_password, method="scrypt")},
                )
                _audit(
                    "admin_password_change",
                    entity_type="user",
                    entity_id=current_user.id,
                    details="Administrator changed their password.",
                )
                flash("Your password has been updated.", "success")
        return redirect(url_for("admin.profile"))

    audit = current_app.supabase.list_audit_log(limit=15, actor_id=current_user.id)
    return render_template("admin/profile.html", audit=audit)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------
@admin_bp.route("/export/applications.csv")
@admin_required
def export_applications():
    status = clean_str(request.args.get("status"))
    course_id = clean_str(request.args.get("course_id"))
    search = clean_str(request.args.get("q"), 120)
    date_from = clean_str(request.args.get("date_from"), 12)
    date_to = clean_str(request.args.get("date_to"), 12)

    rows = current_app.supabase.list_applications(
        status=status or None,
        course_id=course_id or None,
        search=search or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Application Number", "Status", "First Name", "Last Name", "Date of Birth",
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
            app.get("first_name"), app.get("last_name"), app.get("date_of_birth"),
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

    filename = "admission_report_{}.csv".format(datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
