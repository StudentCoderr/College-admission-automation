"""Flask application factory for the College Admission Automation System."""

import logging
import os

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user, logout_user

from app.config import Config
from app.extensions import csrf, login_manager
from app.models import User
from app.services.supabase_service import init_service

# Static admin console (HTML/CSS/JS that consumes the /api JSON endpoints).
ADMIN_CONSOLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "admin"
)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # --- Extensions ------------------------------------------------------
    login_manager.init_app(app)
    csrf.init_app(app)

    # --- Supabase service (server-side only) -----------------------------
    init_service(app)

    # --- Local document downloads (offline mode only) --------------------
    if app.config.get("USE_LOCAL_DB"):

        @app.route("/local-documents/<path:storage_path>")
        def local_document(storage_path):
            """Serve an uploaded document from the local uploads folder."""
            if not current_user.is_authenticated:
                abort(401)
            document = app.supabase.get_document_by_storage_path(storage_path)
            if not document:
                abort(404)
            is_owner = str(document.get("user_id")) == str(current_user.id)
            if not is_owner and getattr(current_user, "role", "") != "admin":
                abort(404)
            try:
                path = app.supabase.uploads_path(storage_path)
            except ValueError:
                abort(404)
            if not os.path.isfile(path):
                abort(404)
            return send_file(path, mimetype=document.get("mime_type"))

    # --- Flask-Login user loader ----------------------------------------
    @login_manager.user_loader
    def load_user(user_id):
        data = app.supabase.get_user_by_id(user_id)
        return User(data) if data else None

    # --- Where anonymous users are sent ---------------------------------
    @login_manager.unauthorized_handler
    def unauthorized():
        """Admins go to the dedicated admin login; everyone else to the
        shared student login. Both preserve where the user was heading."""
        if request.path.startswith("/admin/"):
            flash("Please log in with an administrator account to continue.", "warning")
            return redirect(url_for("admin.admin_login", next=request.path))
        flash("Please log in to continue.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    # --- Sign out accounts that were deactivated or withdrawn ------------
    @app.before_request
    def sign_out_inactive_accounts():
        """Clear a stale session for an inactive account.

        Flask-Login already treats an inactive user as anonymous (its
        ``is_authenticated`` mirrors ``is_active``); this makes the reason
        explicit, clears the cookie and keeps the user on the login page. The
        JSON API is skipped so it can keep returning structured 401/403 bodies.
        """
        if request.path.startswith("/api/") or request.endpoint == "static":
            return None
        # Accessing current_user triggers Flask-Login's lazy load; an inactive
        # account is returned as our User object but reports is_active=False.
        user = current_user
        if isinstance(user, User) and not user.is_active:
            logout_user()
            flash(
                "Your account is not active. Please contact the administrator.",
                "danger",
            )
            if request.endpoint not in ("auth.login", "admin.admin_login"):
                return redirect(url_for("auth.login"))
        return None

    # --- Blueprints ------------------------------------------------------
    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.student import student_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(admin_bp)

    # --- JSON REST API (/api) --------------------------------------------
    from app.api import init_api

    init_api(app)

    # --- Static admin console (/admin-console) ----------------------------
    register_admin_console(app)

    # --- Template helpers ------------------------------------------------
    @app.context_processor
    def inject_globals():
        from app.models import STATUS_LABELS
        from app.utils.validators import QUALIFICATION_LABELS, person_name

        return {
            "current_year": 2026,
            "STATUS_LABELS": STATUS_LABELS,
            "QUALIFICATION_LABELS": QUALIFICATION_LABELS,
            "person_name": person_name,
            "app_name": "College Admission Automation System",
        }

    # --- Error handlers --------------------------------------------------
    register_error_handlers(app)

    # --- CLI commands ----------------------------------------------------
    register_cli(app)

    return app


def register_admin_console(app):
    """Serve the static admin dashboard at /admin-console.

    Serving it from the same origin as the API means the session cookie and
    CSRF token work without any CORS configuration in development and in
    production. Authorization is still enforced server-side on every /api/admin
    route; this route only hands out static assets.
    """

    @app.route("/admin-console/")
    @app.route("/admin-console")
    def admin_console_index():
        return send_from_directory(ADMIN_CONSOLE_DIR, "index.html")

    @app.route("/admin-console/<path:filename>")
    def admin_console_file(filename):
        return send_from_directory(ADMIN_CONSOLE_DIR, filename)


def register_error_handlers(app):
    def wants_json():
        """API routes always get JSON; other routes honour the Accept header."""
        if request.path.startswith("/api/"):
            return True
        return request.accept_mimetypes.best == "application/json"

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", "Bad request.")
        if wants_json():
            return jsonify({"ok": False, "error": message}), 400
        return render_template("errors/error.html", code=400, message=message), 400

    @app.errorhandler(401)
    def unauthorized(error):
        message = getattr(error, "description", "Authentication required.")
        if wants_json():
            return jsonify({"ok": False, "error": message}), 401
        return render_template("errors/error.html", code=401, message=message), 401

    @app.errorhandler(403)
    def forbidden(error):
        message = getattr(
            error, "description", "You do not have permission to access this resource."
        )
        if wants_json():
            return jsonify({"ok": False, "error": message}), 403
        return render_template("errors/error.html", code=403, message=message), 403

    @app.errorhandler(404)
    def not_found(error):
        message = getattr(error, "description", "The resource you requested was not found.")
        if wants_json():
            return jsonify({"ok": False, "error": message}), 404
        return (
            render_template(
                "errors/error.html", code=404, message="The page you requested was not found."
            ),
            404,
        )

    @app.errorhandler(405)
    def method_not_allowed(error):
        message = "Method not allowed for this endpoint."
        if wants_json():
            return jsonify({"ok": False, "error": message}), 405
        return render_template("errors/error.html", code=405, message=message), 405

    @app.errorhandler(413)
    def too_large(error):
        message = "The uploaded file is too large. Maximum size is 5 MB."
        if wants_json():
            return jsonify({"ok": False, "error": message}), 413
        return render_template("errors/error.html", code=413, message=message), 413

    @app.errorhandler(500)
    def server_error(error):  # pragma: no cover - defensive
        app.logger.exception("Unhandled server error")
        message = "Something went wrong on our side. Please try again."
        if wants_json():
            return jsonify({"ok": False, "error": message}), 500
        return render_template("errors/error.html", code=500, message=message), 500


def register_cli(app):
    import click

    @app.cli.command("create-admin")
    @click.option("--email", default=None, help="Admin email (defaults to $ADMIN_EMAIL).")
    @click.option(
        "--full-name", default=None, help="Admin full name (defaults to $ADMIN_FULL_NAME)."
    )
    @click.option(
        "--reset-password",
        is_flag=True,
        help="Rotate the password of an existing administrator ($ADMIN_PASSWORD).",
    )
    def create_admin(email, full_name, reset_password):
        """Create (or promote) the initial administrator - idempotent.

        Reads ADMIN_EMAIL / ADMIN_FULL_NAME / ADMIN_PASSWORD from the
        environment or .env; anything missing is asked for at an interactive
        prompt. The password is never accepted from the command line, never
        echoed to the console and never written to source code - it is hashed
        (Werkzeug scrypt) before reaching the users table. Re-running on an
        existing administrator is a no-op unless --reset-password is given.
        """
        from werkzeug.security import generate_password_hash

        from app.utils.validators import (
            clean_str,
            is_valid_email,
            split_full_name,
            validate_password,
        )

        email = clean_str(email or os.environ.get("ADMIN_EMAIL") or "", 254).lower()
        if not email:
            email = clean_str(click.prompt("Administrator email"), 254).lower()
        if not is_valid_email(email):
            raise click.ClickException(
                "Invalid administrator email. Set ADMIN_EMAIL in .env or pass --email."
            )

        full_name = clean_str(full_name or os.environ.get("ADMIN_FULL_NAME") or "")

        def obtain_password():
            password = os.environ.get("ADMIN_PASSWORD", "")
            if not password:
                password = click.prompt(
                    "Administrator password", hide_input=True, confirmation_prompt=True
                )
            pw_error = validate_password(password)
            if pw_error:
                raise click.ClickException(pw_error)
            return password

        if not app.supabase.is_configured:
            raise click.ClickException(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in .env, then run this command again."
            )

        existing = app.supabase.get_user_by_email(email)
        already_admin = bool(existing) and existing.get("role") == "admin"

        # Idempotent no-op: an existing administrator is left completely
        # untouched unless the operator explicitly requests a rotation.
        if existing and already_admin and not reset_password:
            click.echo(
                f"Administrator {email} already exists - no changes made. To "
                "rotate the password, re-run with --reset-password."
            )
            return

        if existing and already_admin and reset_password:
            password_hash = generate_password_hash(obtain_password(), method="scrypt")
            if not app.supabase.update_user(
                existing["id"], {"password_hash": password_hash}
            ):
                raise click.ClickException(f"Could not rotate the password for {email}.")
            click.echo(f"Password rotated for administrator {email}.")
            return

        if existing and not already_admin:
            # Promote the existing account instead of creating a duplicate. Its
            # own password is preserved unless a rotation was explicitly asked
            # for, so provisioning never hijacks an existing user's credentials.
            if reset_password:
                password_hash = generate_password_hash(obtain_password(), method="scrypt")
            else:
                password_hash = None
            updated = app.supabase.promote_to_admin(existing["id"], password_hash)
            if not updated:
                raise click.ClickException(f"Could not promote {email} to administrator.")
            click.echo(
                f"Granted the administrator role to {email} "
                + (
                    "and rotated its password."
                    if reset_password
                    else "(its password was left unchanged)."
                )
            )
            return

        # Brand-new account (the usual first-run case).
        if not full_name:
            full_name = click.prompt("Administrator full name")
        password_hash = generate_password_hash(obtain_password(), method="scrypt")
        first_name, middle_name, last_name = split_full_name(full_name)
        created = app.supabase.create_user(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            role="admin",
        )
        if not created:
            raise click.ClickException(
                f"Could not create the administrator account for {email}. Verify "
                "the Supabase service-role key and that the users table is reachable."
            )
        click.echo(f"Created administrator account {email}.")

    @app.cli.command("reset-project")
    @click.option(
        "--yes",
        is_flag=True,
        help="Skip the typed RESET confirmation (for scripted, intentional resets).",
    )
    def reset_project(yes):
        """Delete every member, application, course and uploaded file.

        The database schema and the storage bucket are kept. The command asks
        for the new administrator's email, full name and password (hidden
        input, never echoed or logged) before deleting anything, so a typo
        cannot leave the project without an administrator. No old password is
        required.
        """
        from werkzeug.security import generate_password_hash

        from app.utils.validators import (
            clean_str,
            is_valid_email,
            split_full_name,
            validate_password,
        )

        service = app.supabase
        if not service.is_configured:
            raise click.ClickException(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in .env, then run this command again."
            )

        counts = {}
        for table in ("users", "courses", "applications", "documents"):
            try:
                counts[table] = service.count_rows(table)[0]
            except Exception:
                counts[table] = "?"

        click.echo("This will PERMANENTLY delete:")
        for table, label in (
            ("users", "members/accounts"),
            ("courses", "courses"),
            ("applications", "applications"),
            ("documents", "documents"),
        ):
            click.echo("  {:<20} {}".format(label + ":", counts[table]))
        click.echo("Uploaded files in the private storage bucket are removed too.")
        click.echo("The database schema and the storage bucket itself are kept.")

        if not yes:
            confirmation = click.prompt("Type RESET to continue")
            if confirmation.strip().upper() != "RESET":
                raise click.ClickException("Aborted. Nothing was deleted.")

        # Collect and validate the replacement administrator BEFORE deleting,
        # so an invalid email/password never leaves the project admin-less.
        email = clean_str(os.environ.get("ADMIN_EMAIL", ""), 254).lower()
        if not email:
            email = clean_str(click.prompt("New administrator email"), 254).lower()
        if not is_valid_email(email):
            raise click.ClickException(
                "Invalid administrator email. Nothing was deleted."
            )

        full_name = clean_str(os.environ.get("ADMIN_FULL_NAME", ""))
        if not full_name:
            full_name = clean_str(click.prompt("New administrator full name"))
        if not full_name:
            raise click.ClickException("A full name is required. Nothing was deleted.")

        password = os.environ.get("ADMIN_PASSWORD", "")
        if not password:
            password = click.prompt(
                "New administrator password",
                hide_input=True,
                confirmation_prompt=True,
            )
        password_error = validate_password(password)
        if password_error:
            raise click.ClickException(password_error + " Nothing was deleted.")

        deleted = service.purge_all_data()
        if deleted.get("users") is None:
            raise click.ClickException(
                "The members/accounts table could not be cleared. Check the "
                "Supabase service-role key and that sql/schema.sql has been applied."
            )
        click.echo(
            "Removed {} accounts, {} courses, {} applications, {} documents "
            "and {} uploaded files.".format(
                deleted.get("users") or 0,
                deleted.get("courses") or 0,
                deleted.get("applications") or 0,
                deleted.get("documents") or 0,
                deleted.get("storage_objects") or 0,
            )
        )

        password_hash = generate_password_hash(password, method="scrypt")
        first_name, middle_name, last_name = split_full_name(full_name)
        created = service.create_user(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            role="admin",
        )
        if not created:
            raise click.ClickException(
                "The project was emptied, but the administrator account could "
                "not be created. Run `flask create-admin` to try again."
            )
        click.echo(f"Created administrator account {email}.")
        click.echo("Sign in at /admin/login with the password you just entered.")

    @app.cli.command("seed-courses")
    def seed_courses():
        """Insert the bundled course catalogue (idempotent by course code).

        The list lives in ``app/data/courses.py``. Re-running is safe: codes
        that already exist are skipped, so real courses you have edited in the
        admin dashboard are never overwritten.
        """
        if not app.supabase.is_configured:
            raise click.ClickException(
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in .env, then run this command again."
            )

        from app.data.courses import DEFAULT_COURSES

        existing = {c.get("code") for c in app.supabase.list_courses()}
        added = 0
        for course in DEFAULT_COURSES:
            if course["code"] in existing:
                continue
            if app.supabase.create_course(dict(course)):
                added += 1
        skipped = len(DEFAULT_COURSES) - added
        click.echo(
            "Seeded courses: {} added, {} already present.".format(added, skipped)
        )
        if added == 0 and skipped == 0:
            click.echo("The bundled course list is empty.")

    @app.cli.command("db-check")
    def db_check():
        """Read-only report of the live Supabase schema and row counts.

        Prints every table's columns and how many rows it holds, then flags the
        columns the course catalogue relies on but that the live database is
        missing. Run it before debugging an empty-looking page: an empty
        ``courses`` table (or a stale schema) is the usual reason no course
        names appear anywhere.
        """
        service = app.supabase
        click.echo(
            "Supabase URL: " + (getattr(service, "url", "") or "(not configured)")
        )

        describe = getattr(service, "describe_schema", None)
        schema = describe() if callable(describe) else {}
        if not schema:
            click.echo(
                "Could not read the live schema. Check SUPABASE_URL / "
                "SUPABASE_SERVICE_ROLE_KEY and the network connection."
            )
            raise SystemExit(1)

        click.echo("\nTables and columns:")
        for table in sorted(schema):
            click.echo("  {:<28} {}".format(table, ", ".join(schema[table])))

        click.echo("\nRow counts:")
        counts = {}
        count_rows = getattr(service, "count_rows", None)
        for table in sorted(schema):
            if callable(count_rows):
                try:
                    count, truncated = count_rows(table)
                except Exception:
                    count, truncated = 0, True
            else:
                count, truncated = 0, True
            counts[table] = count
            click.echo(
                "  {:<28} {}{} rows".format(table, count, "+" if truncated else "")
            )

        expected_courses = {
            "id", "code", "name", "description", "duration_years", "seats_total",
            "program_type", "eligibility", "tuition_fee", "is_active",
            "eligible_qualifications", "created_at", "updated_at",
        }
        course_columns = set(schema.get("courses", []))
        if not course_columns:
            click.echo(
                "\nWARNING: there is no 'courses' table in this database. "
                "Run sql/schema.sql in the Supabase SQL Editor."
            )
            return
        missing = sorted(expected_courses - course_columns)
        if missing:
            click.echo("\nWARNING: courses is missing: " + ", ".join(missing))
            click.echo(
                "Run sql/schema.sql (idempotent) in the Supabase SQL Editor, or "
                "sql/upgrade_diploma.sql plus sql/upgrade_qualifications.sql."
            )
        else:
            click.echo("\ncourses schema is up to date.")
        if counts.get("courses", 0) == 0:
            click.echo(
                "NOTE: courses has no rows yet. This project starts empty; add "
                "your real courses in /admin/courses."
            )

        # Name columns: users got first/middle/last in sql/upgrade_names.sql;
        # applications got middle_name in sql/upgrade_application_names.sql.
        # Both are additive and the app degrades gracefully without them, so a
        # warning (not an error) is the right signal here.
        user_columns = set(schema.get("users", []))
        missing_user_names = sorted(
            {"first_name", "middle_name", "last_name"} - user_columns
        )
        if missing_user_names:
            click.echo(
                "\nWARNING: users is missing: " + ", ".join(missing_user_names)
                + " (run sql/upgrade_names.sql or sql/schema.sql)."
            )

        app_columns = set(schema.get("applications", []))
        if app_columns and "middle_name" not in app_columns:
            click.echo(
                "\nWARNING: applications is missing: middle_name "
                "(run sql/upgrade_application_names.sql or sql/schema.sql)."
            )
