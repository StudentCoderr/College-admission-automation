"""Authentication endpoints: register, login, logout, session and CSRF token."""

import logging

from flask import Blueprint, current_app
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.api.responses import created, failure, success
from app.api.serializers import serialize_user
from app.api.utils import json_body
from app.models import User
from app.utils.security import generate_csrf_token
from app.utils.validators import (
    clean_name,
    clean_str,
    is_valid_email,
    is_valid_phone,
    split_full_name,
    validate_email_password,
    validate_names,
)

logger = logging.getLogger(__name__)

bp = Blueprint("api_auth", __name__)


@bp.route("/auth/register", methods=["POST"])
@bp.route("/register", methods=["POST"])
def register():
    data = json_body()
    first_name = clean_name(data.get("first_name"))
    middle_name = clean_name(data.get("middle_name"))
    last_name = clean_name(data.get("last_name"))
    if not first_name and not middle_name and not last_name:
        # Legacy API clients send a single full_name / name value; split it.
        legacy = clean_str(data.get("full_name") or data.get("name"), 120)
        if legacy:
            first_name, middle_name, last_name = split_full_name(legacy)
    phone = clean_str(data.get("phone"), 20)
    password = data.get("password") or ""
    confirm = data.get("confirm_password") or password

    email, errors = validate_email_password(data.get("email"), password, confirm)
    (first_name, middle_name, last_name), name_errors = validate_names(
        first_name, middle_name, last_name
    )
    errors.update(name_errors)
    if phone and not is_valid_phone(phone):
        errors["phone"] = "Enter a valid phone number."
    if errors:
        return failure("Please correct the highlighted fields.", 422, errors)

    service = current_app.supabase
    if service.get_user_by_email(email):
        return failure(
            "An account with this email already exists.",
            409,
            {"email": "An account with this email already exists."},
        )

    try:
        row = service.create_user(
            email=email,
            password_hash=generate_password_hash(password, method="scrypt"),
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=phone or None,
            role="student",
        )
    except Exception:
        logger.exception("API register failed for %s", email)
        return failure("Could not create your account. Please try again.", 500)

    if not row:
        return failure("Could not create your account. Please try again.", 500)

    login_user(User(row))
    logger.info("New student registered (id=%s)", row.get("id"))
    return created(user=serialize_user(row), csrf_token=generate_csrf_token())


@bp.route("/auth/login", methods=["POST"])
@bp.route("/login", methods=["POST"])
def login():
    data = json_body()
    email = clean_str(data.get("email"), 254).lower()
    password = data.get("password") or ""

    if not is_valid_email(email) or not password:
        return failure("Enter a valid email and password.", 400)

    row = current_app.supabase.get_user_by_email(email)
    if not row or not check_password_hash(row.get("password_hash", ""), password):
        # Generic message and a warning log that records no secret material.
        logger.warning("Failed login attempt for %s", email)
        return failure("Invalid email or password.", 401)

    if not row.get("is_active", True):
        return failure("This account has been deactivated. Contact the administrator.", 403)

    login_user(User(row))
    logger.info("Login succeeded (id=%s)", row.get("id"))
    return success(user=serialize_user(row), csrf_token=generate_csrf_token())


@bp.route("/auth/logout", methods=["POST"])
@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return success(message="You have been logged out.")


@bp.route("/auth/me", methods=["GET"])
@bp.route("/me", methods=["GET"])
def me():
    if not current_user.is_authenticated:
        # Returning 200 with a null user lets a client cheaply probe the session.
        return success(user=None)
    row = current_app.supabase.get_user_by_id(current_user.id)
    return success(user=serialize_user(row or current_user.to_dict()))


@bp.route("/auth/csrf", methods=["GET"])
def csrf_token():
    """Issue (and remember) the CSRF token required on state-changing calls."""
    return success(csrf_token=generate_csrf_token())
