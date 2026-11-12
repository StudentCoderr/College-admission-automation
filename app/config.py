"""Central application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

# Load variables from a local .env file if present. On Render the variables
# are provided by the platform and this call is a harmless no-op.
load_dotenv()


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Config:
    # --- Core Flask -------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-change-me")
    ENV = os.environ.get("FLASK_ENV", "development")

    # --- Supabase ---------------------------------------------------------
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    # Server-only. Gives full DB access; must never reach the browser.
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "admission-documents")

    # --- Local offline database ------------------------------------------
    # When true the app uses a persistent JSON database (instance/local_db.json)
    # instead of Supabase. This makes register/login/courses work immediately
    # without a cloud project. Set to false after configuring Supabase.
    USE_LOCAL_DB = os.environ.get("USE_LOCAL_DB", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "").strip()
    LOCAL_UPLOADS_DIR = os.environ.get("LOCAL_UPLOADS_DIR", "").strip()

    # --- Uploads ----------------------------------------------------------
    MAX_CONTENT_LENGTH = _as_int(os.environ.get("MAX_CONTENT_LENGTH"), 5 * 1024 * 1024)
    SIGNED_URL_EXPIRES_IN = _as_int(os.environ.get("SIGNED_URL_EXPIRES_IN"), 300)

    # CSRF protection is on by default; the test config disables it.
    CSRF_ENABLED = True

    # Allowed document extensions and their canonical MIME types
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }

    # --- Session cookies (security hardening) -----------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies require HTTPS; Render provides HTTPS in production.
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV", "development") == "production"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours

    # --- Pagination -------------------------------------------------------
    APPLICATIONS_PER_PAGE = 10

    # --- REST API ---------------------------------------------------------
    # Require a CSRF token (X-CSRF-Token) on state-changing /api requests.
    API_CSRF_ENABLED = os.environ.get("API_CSRF_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    # Browser origins allowed to call the API with credentials.
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,"
            "http://localhost:8081,http://127.0.0.1:8081,"
            "http://localhost:5000,http://127.0.0.1:5000",
        ).split(",")
        if origin.strip()
    ]


class TestConfig(Config):
    """Configuration used by the automated test-suite (no real network calls)."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    CSRF_ENABLED = False
    API_CSRF_ENABLED = False
    CORS_ALLOWED_ORIGINS = ["http://localhost:8080"]
    # Empty Supabase settings stop the factory from creating a real client;
    # the test fixtures attach an in-memory fake instead.
    SUPABASE_URL = ""
    SUPABASE_SERVICE_ROLE_KEY = ""
