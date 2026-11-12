"""JSON-friendly authentication and authorization decorators.

Flask-Login's own ``login_required`` redirects anonymous users to the HTML
login page, which is wrong for an API. These decorators return a 401/403 JSON
body instead.
"""

from functools import wraps

from flask_login import current_user

from app.api.responses import failure


def api_login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return failure("Authentication required. Please log in.", 401)
        if not getattr(current_user, "is_active", True):
            return failure("This account has been deactivated.", 403)
        return view(*args, **kwargs)

    return wrapper


def api_role_required(*roles):
    """Require an authenticated user whose role is one of ``roles``."""

    def decorator(view):
        @wraps(view)
        @api_login_required
        def wrapper(*args, **kwargs):
            if getattr(current_user, "role", None) not in roles:
                return failure("You do not have permission to perform this action.", 403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


api_admin_required = api_role_required("admin")
api_student_required = api_role_required("student")
