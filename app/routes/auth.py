"""Authentication: student registration, login, logout, password setup."""

import hashlib
from datetime import datetime, timezone

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import User
from app.utils.validators import (
    ValidationError,
    clean_name,
    clean_str,
    is_valid_email,
    is_valid_phone,
    validate_email_password,
    validate_names,
    validate_password,
)

auth_bp = Blueprint("auth", __name__)


def _dashboard_for(user):
    return "admin.dashboard" if user.is_admin else "student.dashboard"


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(_dashboard_for(current_user)))

    form = {}
    errors = {}
    if request.method == "POST":
        first_name = clean_name(request.form.get("first_name"))
        middle_name = clean_name(request.form.get("middle_name"))
        last_name = clean_name(request.form.get("last_name"))
        form = {
            "first_name": first_name or "",
            "middle_name": middle_name or "",
            "last_name": last_name or "",
            "email": clean_str(request.form.get("email"), 254).lower(),
            "phone": clean_str(request.form.get("phone"), 20),
        }
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        try:
            email, errors = validate_email_password(form["email"], password, confirm)
            form["email"] = email
            (first_name, middle_name, last_name), name_errors = validate_names(
                first_name, middle_name, last_name
            )
            errors.update(name_errors)
            if form["phone"] and not is_valid_phone(form["phone"]):
                errors["phone"] = "Enter a valid phone number."
            if errors:
                raise ValidationError(errors)

            if current_app.supabase.get_user_by_email(form["email"]):
                raise ValidationError({"email": "An account with this email already exists."})

            user_row = current_app.supabase.create_user(
                email=form["email"],
                password_hash=generate_password_hash(password, method="scrypt"),
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                phone=form["phone"] or None,
                role="student",
            )
            if not user_row:
                raise ValidationError({"_form": "Could not create your account. Please try again."})

            login_user(User(user_row))
            flash("Welcome! Your account has been created.", "success")
            return redirect(url_for("student.dashboard"))
        except ValidationError as exc:
            errors = exc.errors
            for message in errors.values():
                flash(message, "danger")

    return render_template("auth/register.html", form=form, errors=errors)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(_dashboard_for(current_user)))

    if request.method == "POST":
        email = clean_str(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")
        next_url = request.args.get("next") or request.form.get("next")

        if not is_valid_email(email) or not password:
            flash("Enter a valid email and password.", "danger")
            return render_template("auth/login.html", email=email)

        row = current_app.supabase.get_user_by_email(email)
        if not row or not check_password_hash(row.get("password_hash", ""), password):
            # Deliberately generic message to avoid user enumeration.
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", email=email)

        if not row.get("is_active", True) or row.get("status", "active") != "active":
            flash(
                "This account is not active. Contact the administrator.",
                "danger",
            )
            return render_template("auth/login.html", email=email)

        user = User(row)
        login_user(user)

        # Only allow relative "next" targets to avoid open-redirects.
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for(_dashboard_for(user)))

    return render_template("auth/login.html", email="")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))


# ---------------------------------------------------------------------------
# One-time password setup (account invitation)
# ---------------------------------------------------------------------------
def _invite_is_valid(row) -> bool:
    """A setup link is valid only while unused and unexpired."""
    if not row or row.get("invite_used_at"):
        return False
    expires = row.get("invite_expires_at")
    if not expires:
        return False
    try:
        expires_at = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < expires_at


@auth_bp.route("/setup-password/<token>", methods=["GET", "POST"])
def setup_password(token):
    """Let an invited student choose their own password.

    Only the SHA-256 hash of the token is stored. The link is single-use and
    expires, so a leaked URL has a limited window and cannot be replayed.
    """
    token_hash = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    row = current_app.supabase.get_user_by_invite_hash(token_hash)
    if not _invite_is_valid(row):
        return (
            render_template("auth/setup_password.html", invalid=True, token=None),
            410,
        )

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        error = validate_password(password)
        if error:
            flash(error, "danger")
        elif password != confirm:
            flash("The passwords do not match.", "danger")
        else:
            current_app.supabase.consume_invitation(
                row["id"], generate_password_hash(password, method="scrypt")
            )
            current_app.supabase.add_audit_log(
                action="student_password_setup",
                actor_id=row.get("id"),
                actor_email=row.get("email"),
                entity_type="user",
                entity_id=str(row.get("id")),
                details="Student set their own password via a one-time link.",
                ip_address=request.remote_addr,
            )
            flash("Your password has been set. You can now sign in.", "success")
            return redirect(url_for("auth.login"))

    return render_template(
        "auth/setup_password.html", invalid=False, token=token, email=row.get("email")
    )

