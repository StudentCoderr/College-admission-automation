"""Public catalogue endpoints: courses and announcements."""

from flask import Blueprint, current_app, request

from app.api.responses import success
from app.api.serializers import serialize_announcement, serialize_course

bp = Blueprint("api_courses", __name__)


@bp.route("/courses", methods=["GET"])
def list_courses():
    active_only = request.args.get("active", "true").lower() != "false"
    program_type = (request.args.get("program_type") or request.args.get("type") or "").lower()
    if program_type not in ("degree", "diploma"):
        program_type = None
    courses = current_app.supabase.list_courses(active_only=active_only, program_type=program_type)
    return success(courses=[serialize_course(c) for c in courses])


@bp.route("/announcements", methods=["GET"])
def list_announcements():
    rows = current_app.supabase.list_announcements()
    return success(announcements=[serialize_announcement(r) for r in rows])
