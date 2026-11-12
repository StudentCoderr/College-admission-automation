"""RESTful JSON API, mounted at ``/api``.

The API is a separate presentation layer from the server-rendered HTML views
and reuses the same service layer, so authorization and validation rules stay
identical. It is assembled from focused sub-blueprints:

* ``auth``         - register / login / logout / session / CSRF token
* ``courses``      - public course catalogue and announcements
* ``applications`` - student application lifecycle and public tracking
* ``documents``    - private document upload and signed-URL access
* ``admin``        - administrator review, statistics and verification
"""

import logging

from flask import Blueprint, jsonify, request

from app.api import admin, applications, auth, courses, documents
from app.api.responses import failure
from app.services.errors import ServiceError
from app.utils.security import validate_csrf_token
from app.utils.validators import ValidationError as FormValidationError

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Wire the sub-blueprints once at import time. Registering them later (e.g. on a
# second create_app call in the tests) is not allowed once a blueprint has been
# registered.
api_bp.register_blueprint(auth.bp)
api_bp.register_blueprint(courses.bp)
api_bp.register_blueprint(applications.bp)
api_bp.register_blueprint(documents.bp)
api_bp.register_blueprint(admin.bp)

# Endpoints that may be called before a CSRF token exists.
_CSRF_EXEMPT = {"/api/auth/csrf"}


def _register_error_handlers(app):
    @app.errorhandler(FormValidationError)
    def _handle_form_validation(exc):
        # Raised by app.utils.validators.validate_application_form.
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Please correct the highlighted fields.",
                    "errors": getattr(exc, "errors", None),
                }
            ),
            422,
        )

    @app.errorhandler(ServiceError)
    def _handle_service_error(exc):
        payload = {"ok": False, "error": exc.message}
        if exc.errors:
            payload["errors"] = exc.errors
        return jsonify(payload), exc.status_code


def _register_csrf(app):
    @app.before_request
    def _api_csrf_guard():  # pragma: no cover - thin wrapper
        if not request.path.startswith("/api/"):
            return None
        if not app.config.get("API_CSRF_ENABLED", True):
            return None
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        if request.path.rstrip("/") in _CSRF_EXEMPT:
            return None

        token = request.headers.get("X-CSRF-Token")
        if not token:
            body = request.get_json(silent=True)
            if isinstance(body, dict):
                token = body.get("csrf_token")
        if not validate_csrf_token(token):
            logger.warning("Blocked API request to %s: invalid CSRF token", request.path)
            return failure("Invalid or missing CSRF token. Fetch /api/auth/csrf first.", 403)
        return None


def _register_cors(app):
    allowed = set(app.config.get("CORS_ALLOWED_ORIGINS") or [])

    @app.after_request
    def _cors_headers(response):
        if not request.path.startswith("/api/"):
            return response
        origin = request.headers.get("Origin")
        if origin and origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-CSRF-Token, Accept"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers.add("Vary", "Origin")
        return response


def init_api(app):
    """Register the API blueprint, CORS, CSRF and error handlers."""
    app.register_blueprint(api_bp)

    _register_cors(app)
    _register_csrf(app)
    _register_error_handlers(app)

    logger.info("REST API mounted at /api")
    return api_bp
