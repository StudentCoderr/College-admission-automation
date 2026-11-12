"""Shared authorization helpers for record-level access control."""

from flask import current_app
from flask_login import current_user

from app.api.responses import failure


def load_visible_application(application_id, admin=False):
    """Return ``(application, error_response)``.

    ``error_response`` is not ``None`` when access is denied. A student can only
    load their own application; an administrator (when ``admin`` is true) can
    load any. Missing and not-owned records return the same 404 so existence is
    never leaked.
    """
    application = current_app.supabase.get_application(application_id)
    if not application:
        return None, failure("Application not found.", 404)
    if admin and getattr(current_user, "role", None) == "admin":
        return application, None
    if str(application.get("user_id")) != str(current_user.id):
        return None, failure("Application not found.", 404)
    return application, None
