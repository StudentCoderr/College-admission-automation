"""Cross-cutting security helpers: CSRF protection and role decorators."""

import secrets
from functools import wraps

from flask import abort, current_app, request, session
from flask_login import current_user, login_required

CSRF_SESSION_KEY = "_csrf_token"


def generate_csrf_token() -> str:
    """Return a per-session token, creating one on first use."""
    if CSRF_SESSION_KEY not in session:
        session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    return session[CSRF_SESSION_KEY]


def validate_csrf_token(token: str) -> bool:
    """Constant-time comparison of the submitted token with the session token."""
    real = session.get(CSRF_SESSION_KEY)
    if not real or not token:
        return False
    return secrets.compare_digest(real, token)


class CSRFProtect:
    """Minimal, dependency-free CSRF protection for state-changing requests."""

    def init_app(self, app):
        app.jinja_env.globals["csrf_token"] = generate_csrf_token

        @app.before_request
        def _csrf_before_request():  # pragma: no cover - thin wrapper
            if not app.config.get("CSRF_ENABLED", True):
                return None
            if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
                return None
            # The JSON API performs its own token check (see app/api/__init__.py)
            # because it can bootstrap the token via GET /api/auth/csrf.
            if request.path.startswith("/api/"):
                return None
            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not validate_csrf_token(token):
                current_app.logger.warning(
                    "Blocked request to %s: missing/invalid CSRF token", request.path
                )
                abort(400, "Invalid or missing CSRF token. Please refresh and try again.")
            return None


def role_required(role: str):
    """Decorator: require login AND a specific role (used for RBAC)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if getattr(current_user, "role", None) != role:
                abort(403, "You do not have permission to access this page.")
            return view(*args, **kwargs)

        return wrapper

    return decorator


# Convenience decorators
admin_required = role_required("admin")
student_required = role_required("student")
