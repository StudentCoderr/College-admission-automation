"""Run the application against an in-memory database.

The bundled course catalogue from ``app/data/courses.py`` is inserted so the
course list and application forms work immediately. No demo members or
applications are created. This is useful for a local walkthrough without a
Supabase project.

    python scripts/demo_server.py

Set ``SEED_DEMO_COURSES=0`` to start with an empty catalogue instead.

To create the first administrator, set these environment variables before
starting the server (the password is hashed in memory and never printed):

    PowerShell:
        $env:ADMIN_EMAIL="admin@example.com"
        $env:ADMIN_FULL_NAME="Admissions Administrator"
        $env:ADMIN_PASSWORD="A-Strong-Passw0rd"
        python scripts/demo_server.py

    macOS / Linux:
        ADMIN_EMAIL=admin@example.com \
        ADMIN_FULL_NAME="Admissions Administrator" \
        ADMIN_PASSWORD="A-Strong-Passw0rd" \
        python scripts/demo_server.py

If the variables are omitted, the server still starts with no accounts. Open
the public site or the admin console and create data through the UI.

Public site:   http://localhost:5010/
Admin console: http://localhost:5010/admin-console/
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.data.courses import DEFAULT_COURSES  # noqa: E402
from app.utils.validators import (  # noqa: E402
    is_valid_email,
    split_full_name,
    validate_password,
)
from tests.fake_supabase import FakeSupabaseService  # noqa: E402

DEMO_PORT = int(os.environ.get("DEMO_PORT", "5010"))


class DemoConfig(TestConfig):
    """TestConfig with the API CSRF guard switched on."""

    API_CSRF_ENABLED = True
    CSRF_ENABLED = False
    SECRET_KEY = "demo-secret-key"


def _seed_courses(fake):
    """Insert the bundled course list into the in-memory database."""
    if os.environ.get("SEED_DEMO_COURSES", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return 0
    added = 0
    existing = {c.get("code") for c in fake.list_courses()}
    for course in DEFAULT_COURSES:
        if course["code"] in existing:
            continue
        if fake.create_course(dict(course)):
            added += 1
    return added


def _create_admin_from_env(fake):
    """Create exactly one administrator when the environment asks for it."""
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    full_name = (os.environ.get("ADMIN_FULL_NAME") or "").strip()
    password = os.environ.get("ADMIN_PASSWORD") or ""

    if not email and not password:
        return None
    if not email or not password:
        raise SystemExit(
            "Set both ADMIN_EMAIL and ADMIN_PASSWORD (and optionally "
            "ADMIN_FULL_NAME) to create the first administrator."
        )
    if not is_valid_email(email):
        raise SystemExit("ADMIN_EMAIL is not a valid email address.")
    password_error = validate_password(password)
    if password_error:
        raise SystemExit("ADMIN_PASSWORD: " + password_error)

    if not full_name:
        full_name = "Administrator"
    first_name, middle_name, last_name = split_full_name(full_name)
    return fake.create_user(
        email=email,
        password_hash=generate_password_hash(password, method="scrypt"),
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        role="admin",
    )


def main():
    app = create_app(DemoConfig)
    fake = FakeSupabaseService()
    app.supabase = fake
    app.config["FAKE"] = fake

    courses_added = _seed_courses(fake)
    admin = _create_admin_from_env(fake)

    print("=" * 64)
    print("Local server (in-memory data, no network access)")
    print("Public site:   http://localhost:{}/".format(DEMO_PORT))
    print("Admin console: http://localhost:{}/admin-console/".format(DEMO_PORT))
    print("Courses:       {} available".format(len(fake.list_courses())))
    if courses_added:
        print("               seeded {} from app/data/courses.py".format(courses_added))
    if admin:
        print("Administrator: {}".format(admin["email"]))
        print("Use the password you supplied in ADMIN_PASSWORD.")
    else:
        print("No accounts created. Set ADMIN_EMAIL and ADMIN_PASSWORD to")
        print("create the first administrator, or add data through the UI.")
    print("=" * 64)
    app.run(host="127.0.0.1", port=DEMO_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
