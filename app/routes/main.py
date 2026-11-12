"""Public pages: home and course catalogue."""

from flask import Blueprint, abort, current_app, render_template, request

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Public home page.

    Only the public course catalogue is exposed here. Admission totals
    (registered students, applications received and approved admissions) are
    administrative information and stay on the admin dashboard.
    """
    courses = current_app.supabase.list_courses(active_only=True)
    return render_template(
        "index.html",
        courses=courses[:6],
        active_course_count=len(courses),
        diploma_courses=[c for c in courses if c.get("program_type") == "diploma"],
        degree_courses=[c for c in courses if c.get("program_type") != "diploma"],
    )


@main_bp.route("/courses")
def courses():
    # Optional server-side filters: ?program_type=degree|diploma and
    # ?status=active|all. The page also filters instantly in the browser;
    # these query parameters make views shareable / bookmarkable.
    program_type = request.args.get("program_type") or request.args.get("type")
    if program_type not in ("degree", "diploma"):
        program_type = None
    status = request.args.get("status")
    if status not in ("active", "all"):
        status = "active"
    rows = current_app.supabase.list_courses(
        active_only=(status == "active"), program_type=program_type
    )
    return render_template(
        "courses.html",
        courses=rows,
        program_type=program_type or "",
        status_filter=status,
        course_error=current_app.supabase.last_course_error,
    )


@main_bp.route("/courses/<course_id>")
def course_detail(course_id):
    course = current_app.supabase.get_course(course_id)
    if not course or not course.get("is_active", True):
        abort(404)
    return render_template("course_detail.html", course=course)


@main_bp.route("/healthz")
def healthz():
    """Simple readiness probe used by Render health checks."""
    return {"status": "ok", "supabase_configured": current_app.supabase.is_configured}
