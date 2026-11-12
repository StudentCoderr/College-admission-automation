"""Supabase service layer.

All database and storage access goes through this module. The Flask views
never touch the Supabase client directly, which keeps query construction in
one auditable place and makes it easy to test with a mocked service.
"""

import logging
import os
import secrets
from collections import OrderedDict
from datetime import datetime, timezone

from app.utils.validators import (
    clean_name,
    format_display_name,
    split_full_name,
)

logger = logging.getLogger(__name__)


# Columns present in every deployment of the users table (the base schema).
# first_name / middle_name / last_name are handled below as optional columns
# added by sql/upgrade_names.sql.
_BASE_USER_COLUMNS = {
    "id", "email", "password_hash", "full_name", "phone", "role",
    "is_active", "created_at", "updated_at",
}

# Columns introduced by the student-lifecycle upgrade
# (sql/upgrade_students.sql). Databases created from an older schema may not
# have them, so the service probes for their existence and degrades
# gracefully instead of assuming they exist (which would make PostgREST
# reject INSERT/UPDATE payloads with PGRST204).
_OPTIONAL_USER_COLUMNS = {
    "status", "registration_number", "assigned_course_id",
    "invite_token_hash", "invite_expires_at", "invite_used_at",
    "first_name", "middle_name", "last_name",
}

# Columns present in every deployment of the courses table (the base schema).
_BASE_COURSE_COLUMNS = {
    "id", "code", "name", "description", "duration_years", "seats_total",
    "created_at", "updated_at",
}

# Columns added by the Diploma/Polytechnic upgrade
# (sql/upgrade_diploma.sql), the course-activation support and the
# qualification-based eligibility rules (sql/upgrade_qualifications.sql).
# Older databases may lack them, so the service probes for their existence and
# degrades gracefully instead of assuming they exist (which would make
# PostgREST reject the query with PGRST204 and hide every course).
_OPTIONAL_COURSE_COLUMNS = {
    "program_type", "eligibility", "tuition_fee", "is_active",
    "eligible_qualifications",
}

# Columns present in every deployment of the applications table (the base
# schema). PostgREST refuses INSERT/UPDATE payloads that name a column that
# does not exist (PGRST204), so new additive columns are probed for and only
# written when present.
_APPLICATION_BASE_COLUMNS = {
    "id", "application_number", "user_id", "course_id", "status",
    "first_name", "last_name", "date_of_birth", "gender", "category",
    "nationality", "email", "phone", "address_line", "city", "state",
    "postal_code", "country", "qualifying_exam", "board_university",
    "school_name", "passing_year", "marks_obtained", "marks_total",
    "percentage", "admin_note", "submitted_at", "reviewed_at", "reviewed_by",
    "created_at", "updated_at",
}

# Columns introduced by the qualification upgrade (sql/upgrade_qualifications.sql):
# institution_name / stream / trade / affiliation / roll_number are additive and
# nullable, so older databases keep working until the migration is applied.
_OPTIONAL_APPLICATION_COLUMNS = {
    "middle_name",
    "institution_name", "stream", "trade", "affiliation", "roll_number",
}

# The migration that adds each probed application column, used only to make the
# "column missing" log message point at the right SQL file.
_APPLICATION_COLUMN_UPGRADES = {
    "middle_name": "sql/upgrade_application_names.sql",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseService:
    """Thin, defensive wrapper around supabase-py."""

    def __init__(self, url: str, service_role_key: str, bucket: str):
        self.url = url
        self.service_role_key = service_role_key
        self.bucket = bucket
        self.client = None
        self._init_error = None
        self._user_columns_cache = None
        self._course_columns_cache = None
        self._application_columns_cache = None
        # Set by list_courses() so pages can tell "no courses configured yet"
        # apart from "the course query failed". None means the last query
        # succeeded; a short, non-sensitive message means it did not.
        self.last_course_error = None

        if not url or not service_role_key:
            self._init_error = (
                "Supabase is not configured. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY in your environment."
            )
            logger.warning(self._init_error)
            return

        try:
            from supabase import create_client

            self.client = create_client(url, service_role_key)
        except Exception as exc:  # pragma: no cover - depends on environment
            self._init_error = f"Failed to initialise Supabase client: {exc}"
            logger.exception(self._init_error)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @property
    def is_configured(self) -> bool:
        return self.client is not None

    def _client(self):
        if self.client is None:
            raise RuntimeError(self._init_error or "Supabase client unavailable.")
        return self.client

    def _table(self, name):
        return self._client().table(name)

    def describe_schema(self):
        """Return ``{table: [columns]}`` for the live database (read-only).

        Uses the PostgREST OpenAPI document so it works even when a table is
        empty (a normal ``select * limit 0`` cannot reveal the columns of an
        empty table). Used by the ``db-check`` CLI and diagnostics.
        """
        if not self.is_configured:
            return {}
        import json
        import urllib.request

        try:
            request = urllib.request.Request(
                self.url.rstrip("/") + "/rest/v1/",
                headers={
                    "apikey": self.service_role_key,
                    "Authorization": "Bearer " + self.service_role_key,
                    "Accept": "application/openapi+json",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                spec = json.loads(response.read().decode("utf-8", "replace"))
        except Exception:
            logger.exception("describe_schema failed")
            return {}

        definitions = spec.get("definitions") or {}
        return {
            table: sorted((definition.get("properties") or {}).keys())
            for table, definition in definitions.items()
        }

    def count_rows(self, table, cap=1000):
        """Approximate row count for a table (reads at most ``cap`` ids).

        Returns ``(count, truncated)`` where ``truncated`` is True when the
        table holds ``cap`` or more rows.
        """
        if not self.is_configured:
            return 0, False
        try:
            rows = self._table(table).select("id").limit(cap).execute().data or []
        except Exception:
            logger.exception("count_rows(%s) failed", table)
            return 0, True
        return len(rows), len(rows) >= cap

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def _user_columns(self):
        """Columns that actually exist on the live ``users`` table (cached).

        PostgREST validates every column named in an INSERT/UPDATE against its
        schema cache and refuses unknown ones (PGRST204). Older databases
        created without the student-lifecycle upgrade have no ``status`` or
        invite columns, so we probe each optional column once and remember
        which ones exist.
        """
        if self._user_columns_cache is not None:
            return self._user_columns_cache
        known = set(_BASE_USER_COLUMNS)
        if self.is_configured:
            for col in sorted(_OPTIONAL_USER_COLUMNS):
                try:
                    self._table("users").select(col).limit(1).execute()
                    known.add(col)
                except Exception:
                    logger.warning(
                        "users.%s is not present on this database; the "
                        "student-lifecycle feature is degraded until "
                        "sql/upgrade_students.sql has been applied.",
                        col,
                    )
        self._user_columns_cache = known
        return known

    def get_user_by_email(self, email: str):
        if not self.is_configured:
            return None
        try:
            res = (
                self._table("users")
                .select("*")
                .eq("email", email.lower().strip())
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_user_by_email failed")
            return None

    def get_user_by_id(self, user_id: str):
        if not self.is_configured:
            return None
        try:
            res = self._table("users").select("*").eq("id", user_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_user_by_id failed")
            return None

    def get_users_by_ids(self, user_ids):
        """Fetch several users in one query (used for status-history names)."""
        ids = [str(uid) for uid in (user_ids or []) if uid]
        if not ids or not self.is_configured:
            return []
        try:
            res = (
                self._table("users")
                .select("id, full_name, role")
                .in_("id", ids)
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("get_users_by_ids failed")
            return []

    def create_user(
        self,
        email,
        password_hash,
        full_name=None,
        first_name=None,
        middle_name=None,
        last_name=None,
        phone=None,
        role="student",
        registration_number=None,
        status="active",
        assigned_course_id=None,
    ):
        # Normalise the name into its three parts. New callers pass the parts
        # directly; legacy callers (CLI, early API clients, tests) pass a
        # single full_name which is split best-effort.
        first = clean_name(first_name) or None
        middle = clean_name(middle_name) or None
        last = clean_name(last_name) or None
        if not first and not middle and not last and full_name:
            first, middle, last = split_full_name(full_name)
        display_name = format_display_name(first, middle, last)

        columns = self._user_columns()
        payload = {
            "email": email.lower().strip(),
            "password_hash": password_hash,
            "full_name": display_name,
            "phone": phone,
            "role": role,
            "is_active": status == "active",
        }
        # Name parts are sent as explicit NULL when empty. On a legacy schema
        # that predates sql/upgrade_names.sql they are simply omitted; the
        # display column keeps the app working in the meantime.
        for key, value in (
            ("first_name", first),
            ("middle_name", middle),
            ("last_name", last),
        ):
            if key in columns:
                payload[key] = value
        # Only send columns that exist on THIS database. On a legacy schema
        # (no student-lifecycle migration) `status` is omitted and the account
        # is still created with the correct is_active value.
        if "status" in columns:
            payload["status"] = status
        if registration_number and "registration_number" in columns:
            payload["registration_number"] = registration_number
        if assigned_course_id and "assigned_course_id" in columns:
            payload["assigned_course_id"] = assigned_course_id
        try:
            res = self._table("users").insert(payload).execute()
            return res.data[0] if res.data else None
        except Exception:
            # Surface genuine database errors (network issues, unique-constraint
            # races) as a None return; the caller converts that into a
            # user-friendly message instead of a raw traceback.
            logger.exception("create_user failed")
            return None

    def update_user(self, user_id: str, payload: dict):
        columns = self._user_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        payload["updated_at"] = _now_iso()
        res = self._table("users").update(payload).eq("id", user_id).execute()
        return res.data[0] if res.data else None

    def promote_to_admin(self, user_id: str, password_hash: str = None):
        """Grant the admin role, optionally refreshing the password hash.

        ``password_hash`` is optional: when omitted, the account keeps its
        existing password. Idempotent provisioning (the ``create-admin`` CLI)
        relies on this so promoting a user never silently hijacks the
        credentials of an existing account.
        """
        payload = {
            "role": "admin",
            "is_active": True,
            "status": "active",
        }
        if password_hash:
            payload["password_hash"] = password_hash
        return self.update_user(user_id, payload)

    def set_user_active(self, user_id: str, is_active: bool):
        return self.set_student_status(user_id, "active" if is_active else "inactive")

    def set_student_status(self, user_id: str, status: str, extra: dict = None):
        """Set a student's lifecycle status and keep ``is_active`` in step.

        ``status`` is one of active / inactive / withdrawn. Any login-eligible
        status keeps ``is_active`` true; the others disable sign-in while
        preserving the account and its admission history.
        """
        columns = self._user_columns()
        payload = {
            "status": status,
            "is_active": status == "active",
            "updated_at": _now_iso(),
        }
        if "status" not in columns:
            # Legacy schema without users.status: keep the boolean gate only.
            payload.pop("status", None)
        if extra:
            payload.update({k: v for k, v in extra.items() if k in columns})
        res = self._table("users").update(payload).eq("id", user_id).execute()
        return res.data[0] if res.data else None

    def count_active_admins(self) -> int:
        """Number of active administrator accounts (used to protect the last one)."""
        if not self.is_configured:
            return 0
        try:
            res = (
                self._table("users")
                .select("id", count="exact")
                .eq("role", "admin")
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            count = getattr(res, "count", None)
            if count is None:
                return len(res.data or [])
            return count
        except Exception:
            logger.exception("count_active_admins failed")
            return 0

    def delete_user(self, user_id: str):
        """Permanently delete a user row.

        Foreign keys cascade, so the student's applications, documents and
        status history are removed in the same atomic statement. Callers must
        remove Storage objects first (see ``document_paths_by_user``).
        """
        res = self._table("users").delete().eq("id", user_id).execute()
        return res.data[0] if res.data else None

    def registration_number_exists(self, registration_number: str, exclude_id=None):
        if not registration_number or not self.is_configured:
            return False
        try:
            query = (
                self._table("users")
                .select("id")
                .ilike("registration_number", registration_number.strip())
            )
            if exclude_id:
                query = query.neq("id", exclude_id)
            res = query.limit(1).execute()
            return bool(res.data)
        except Exception:
            logger.exception("registration_number_exists failed")
            return False

    def set_invitation(self, user_id: str, token_hash: str, expires_at: str):
        return self.update_user(
            user_id,
            {
                "invite_token_hash": token_hash,
                "invite_expires_at": expires_at,
                "invite_used_at": None,
            },
        )

    def get_user_by_invite_hash(self, token_hash: str):
        if not token_hash or not self.is_configured:
            return None
        try:
            res = (
                self._table("users")
                .select("*")
                .eq("invite_token_hash", token_hash)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_user_by_invite_hash failed")
            return None

    def consume_invitation(self, user_id: str, password_hash: str):
        """Set the student's chosen password, activate the account, clear the token."""
        return self.update_user(
            user_id,
            {
                "password_hash": password_hash,
                "status": "active",
                "is_active": True,
                "invite_token_hash": None,
                "invite_expires_at": None,
                "invite_used_at": _now_iso(),
            },
        )

    def document_paths_by_user(self, user_id: str):
        """Storage paths of every document belonging to a user (for deletion)."""
        if not self.is_configured:
            return []
        try:
            res = self._table("documents").select("storage_path").eq("user_id", user_id).execute()
            return [r.get("storage_path") for r in (res.data or []) if r.get("storage_path")]
        except Exception:
            logger.exception("document_paths_by_user failed")
            return []


    # ------------------------------------------------------------------
    # Students (administrator views)
    # ------------------------------------------------------------------
    def _student_search_ids(self, term):
        """User ids whose application number matches ``term``.

        Admins can search students by the registration reference, which is
        either the college-assigned ``registration_number`` or the number a
        student receives when an application is submitted (ADM-YYYY-NNNNN).
        """
        if not term or not self.is_configured:
            return []
        try:
            res = (
                self._table("applications")
                .select("user_id")
                .ilike("application_number", f"%{term}%")
                .execute()
            )
            return sorted(
                {str(r.get("user_id")) for r in (res.data or []) if r.get("user_id")}
            )
        except Exception:
            logger.exception("_student_search_ids failed")
            return []

    def _apply_student_filters(self, query, search=None, status=None):
        columns = self._user_columns()
        if status in ("active", "inactive", "withdrawn") and "status" in columns:
            query = query.eq("status", status)
        if search:
            term = search.replace(",", " ").strip()
            filters = [
                "full_name.ilike.%{0}%".format(term),
                "email.ilike.%{0}%".format(term),
                "phone.ilike.%{0}%".format(term),
            ]
            if "registration_number" in columns:
                filters.append("registration_number.ilike.%{0}%".format(term))
            ids = self._student_search_ids(term)
            if ids:
                filters.append("id.in.({0})".format(",".join(ids)))
            query = query.or_(",".join(filters))
        return query

    def list_students(
        self,
        search=None,
        status=None,
        order_by="created_at",
        descending=True,
        limit=None,
        offset=None,
    ):
        if not self.is_configured:
            return []
        try:
            query = self._table("users").select("*").eq("role", "student")
            query = self._apply_student_filters(query, search, status)
            # Never ORDER BY a column that does not exist on this database.
            if order_by not in self._user_columns():
                order_by = "created_at"
                descending = True
            query = query.order(order_by, desc=descending)
            if limit is not None:
                start = offset or 0
                query = query.range(start, start + limit - 1)
            return query.execute().data or []
        except Exception:
            logger.exception("list_students failed")
            return []

    def count_students(self, search=None, status=None):
        if not self.is_configured:
            return 0
        try:
            query = (
                self._table("users").select("id", count="exact").eq("role", "student")
            )
            query = self._apply_student_filters(query, search, status)
            res = query.limit(1).execute()
            count = getattr(res, "count", None)
            if count is None:
                return len(res.data or [])
            return count
        except Exception:
            logger.exception("count_students failed")
            return 0

    def get_student(self, user_id: str):
        """Return the user row only when it is a student account."""
        row = self.get_user_by_id(user_id)
        if row and row.get("role") == "student":
            return row
        return None

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------
    def _course_columns(self):
        """Columns that actually exist on the live ``courses`` table (cached).

        Older databases created before the Diploma/Polytechnic upgrade have no
        ``program_type`` / ``eligibility`` / ``tuition_fee`` / ``is_active``
        columns. PostgREST refuses queries that name an unknown column, which
        used to make ``list_courses`` throw and (because the error was
        swallowed) return an empty list even though courses existed. We probe
        once and only ever filter on columns that exist.
        """
        if self._course_columns_cache is not None:
            return self._course_columns_cache
        known = set(_BASE_COURSE_COLUMNS)
        if self.is_configured:
            for col in sorted(_OPTIONAL_COURSE_COLUMNS):
                try:
                    self._table("courses").select(col).limit(1).execute()
                    known.add(col)
                except Exception:
                    upgrade = (
                        "sql/upgrade_qualifications.sql"
                        if col == "eligible_qualifications"
                        else "sql/upgrade_diploma.sql"
                    )
                    logger.warning(
                        "courses.%s is not present on this database; that course "
                        "field stays hidden until %s has been applied.",
                        col,
                        upgrade,
                    )
        self._course_columns_cache = known
        return known

    def course_schema_missing(self):
        """Optional course columns that this database is still missing.

        Returns a sorted list of column names the course features rely on but
        the live ``courses`` table does not have yet (empty list when the
        schema is up to date). The admin area uses this to explain why
        programme type, fees or eligibility cannot be stored until the SQL
        upgrade in ``sql/upgrade_diploma.sql`` / ``sql/upgrade_qualifications.sql``
        has been applied.
        """
        return sorted(_OPTIONAL_COURSE_COLUMNS - self._course_columns())

    def _application_columns(self):
        """Columns that actually exist on the live ``applications`` table (cached).

        The qualification upgrade (sql/upgrade_qualifications.sql) adds
        institution_name / stream / trade / affiliation / roll_number. Older
        databases created before that migration lack them, and PostgREST
        rejects an INSERT/UPDATE that names an unknown column (PGRST204), which
        would break saving applications. We probe once and only ever write
        columns that exist.
        """
        if self._application_columns_cache is not None:
            return self._application_columns_cache
        known = set(_APPLICATION_BASE_COLUMNS)
        if self.is_configured:
            for col in sorted(_OPTIONAL_APPLICATION_COLUMNS):
                try:
                    self._table("applications").select(col).limit(1).execute()
                    known.add(col)
                except Exception:
                    upgrade = _APPLICATION_COLUMN_UPGRADES.get(
                        col, "sql/upgrade_qualifications.sql"
                    )
                    logger.warning(
                        "applications.%s is not present on this database; that "
                        "field will be ignored until %s has been applied.",
                        col,
                        upgrade,
                    )
        self._application_columns_cache = known
        return known

    def list_courses(self, active_only=False, program_type=None):
        if not self.is_configured:
            self.last_course_error = "Supabase is not configured."
            return []
        columns = self._course_columns()
        try:
            query = self._table("courses").select("*").order("name")
            # These filters reference columns that may not exist on an old
            # schema — applying them blindly would 404 every course.
            if active_only and "is_active" in columns:
                query = query.eq("is_active", True)
            if program_type in ("degree", "diploma") and "program_type" in columns:
                query = query.eq("program_type", program_type)
            rows = query.execute().data or []
            self.last_course_error = None
            return rows
        except Exception:
            logger.exception("list_courses failed")
            # Never leak the raw PostgREST/Supabase error to the UI; keep a
            # short, non-sensitive message the caller can show instead of a
            # misleading "no courses yet".
            self.last_course_error = (
                "The course catalogue could not be loaded from the database."
            )
            return []

    def get_course(self, course_id: str):
        if not course_id or not self.is_configured:
            return None
        try:
            res = self._table("courses").select("*").eq("id", course_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_course failed")
            return None

    def create_course(self, payload):
        # Never INSERT a column that is missing from this database (PGRST204).
        columns = self._course_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        try:
            res = self._table("courses").insert(payload).execute()
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("create_course failed")
            return None

    def update_course(self, course_id, payload):
        columns = self._course_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        payload["updated_at"] = _now_iso()
        res = self._table("courses").update(payload).eq("id", course_id).execute()
        return res.data[0] if res.data else None

    def set_course_active(self, course_id, is_active):
        if "is_active" not in self._course_columns():
            logger.warning(
                "courses.is_active is missing; activate/deactivate is disabled."
            )
            return self.get_course(course_id)
        res = (
            self._table("courses")
            .update({"is_active": bool(is_active), "updated_at": _now_iso()})
            .eq("id", course_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def delete_course(self, course_id: str):
        """Permanently delete a course row.

        The schema declares ``on delete set null`` for applications.course_id
        and users.assigned_course_id, so historical records survive without a
        dangling reference.
        """
        if not course_id or not self.is_configured:
            return None
        res = self._table("courses").delete().eq("id", course_id).execute()
        return res.data[0] if res.data else None

    def application_counts_by_course(self):
        """Return {course_id: number of non-draft applications}.

        Used by the admin dashboard to track how many students applied to each
        course (available seats = seats_total - applications_count).
        """
        counts = {}
        if not self.is_configured:
            return counts
        try:
            res = self._table("applications").select("course_id, status").execute()
            for row in res.data or []:
                if row.get("status") == "draft":
                    continue
                course_id = row.get("course_id")
                if course_id:
                    counts[str(course_id)] = counts.get(str(course_id), 0) + 1
        except Exception:
            logger.exception("application_counts_by_course failed")
        return counts

    def application_counts_by_user(self):
        """Return {user_id: number of applications} for the students table."""
        counts = {}
        if not self.is_configured:
            return counts
        try:
            res = self._table("applications").select("user_id").execute()
            for row in res.data or []:
                user_id = row.get("user_id")
                if user_id:
                    counts[str(user_id)] = counts.get(str(user_id), 0) + 1
        except Exception:
            logger.exception("application_counts_by_user failed")
        return counts

    def application_numbers_by_user(self):
        """Map user_id -> most recent application number (registration no.)."""
        numbers = {}
        if not self.is_configured:
            return numbers
        try:
            res = (
                self._table("applications")
                .select("user_id, application_number, created_at")
                .order("created_at", desc=True)
                .execute()
            )
            for row in res.data or []:
                user_id = row.get("user_id")
                number = row.get("application_number")
                if user_id and number and str(user_id) not in numbers:
                    numbers[str(user_id)] = number
        except Exception:
            logger.exception("application_numbers_by_user failed")
        return numbers

    def course_status_counts(self):
        """Aggregate course totals used by the dashboard cards and reports."""
        counts = {
            "total": 0,
            "active": 0,
            "inactive": 0,
            "diploma": 0,
            "diploma_active": 0,
            "degree": 0,
        }
        for course in self.list_courses():
            counts["total"] += 1
            active = bool(course.get("is_active", True))
            if active:
                counts["active"] += 1
            else:
                counts["inactive"] += 1
            if course.get("program_type", "degree") == "diploma":
                counts["diploma"] += 1
                if active:
                    counts["diploma_active"] += 1
            else:
                counts["degree"] += 1
        return counts

    # ------------------------------------------------------------------
    # Application numbers
    # ------------------------------------------------------------------
    def generate_application_number(self) -> str:
        """Ask PostgreSQL for the next sequence value; fall back locally."""
        try:
            res = self._client().rpc("generate_application_number", {}).execute()
            data = res.data
            if isinstance(data, list) and data:
                return str(data[0])
            if data:
                return str(data)
        except Exception:
            logger.warning("generate_application_number RPC failed, using fallback", exc_info=True)
        year = datetime.now(timezone.utc).year
        return f"ADM-{year}-{secrets.randbelow(900000) + 100000}"

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------
    def create_application(self, user_id: str, data: dict):
        payload = dict(data)
        payload["user_id"] = user_id
        payload.setdefault("status", "draft")
        # Never INSERT a column that is missing from this database (PGRST204).
        columns = self._application_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        res = self._table("applications").insert(payload).execute()
        return res.data[0] if res.data else None

    def get_application(self, application_id: str):
        if not self.is_configured:
            return None
        try:
            res = (
                self._table("applications")
                .select("*, courses(id, code, name)")
                .eq("id", application_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_application failed")
            return None

    def get_application_by_number(self, application_number: str):
        if not self.is_configured or not application_number:
            return None
        try:
            res = (
                self._table("applications")
                .select("*, courses(id, code, name)")
                .eq("application_number", application_number)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_application_by_number failed")
            return None

    def update_application(self, application_id: str, data: dict):
        payload = dict(data)
        payload["updated_at"] = _now_iso()
        # Never UPDATE a column that is missing from this database (PGRST204).
        columns = self._application_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        res = self._table("applications").update(payload).eq("id", application_id).execute()
        return res.data[0] if res.data else None

    def list_applications_for_user(self, user_id: str):
        if not self.is_configured:
            return []
        try:
            res = (
                self._table("applications")
                .select("*, courses(id, code, name)")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("list_applications_for_user failed")
            return []

    def _apply_application_filters(
        self, query, status=None, course_id=None, search=None, date_from=None, date_to=None
    ):
        """Apply the shared admin/student filters to a PostgREST query builder."""
        if status:
            query = query.eq("status", status)
        if course_id:
            query = query.eq("course_id", course_id)
        if date_from:
            query = query.gte("created_at", date_from)
        if date_to:
            query = query.lte("created_at", date_to)
        if search:
            term = search.replace(",", " ").strip()
            query = query.or_(
                "application_number.ilike.%{0}%,"
                "first_name.ilike.%{0}%,"
                "last_name.ilike.%{0}%,"
                "email.ilike.%{0}%".format(term)
            )
        return query

    def list_applications(
        self,
        status=None,
        course_id=None,
        search=None,
        date_from=None,
        date_to=None,
        order_by="created_at",
        descending=True,
        limit=None,
        offset=None,
    ):
        if not self.is_configured:
            return []
        try:
            query = self._table("applications").select("*, courses(id, code, name)")
            query = self._apply_application_filters(
                query, status, course_id, search, date_from, date_to
            )
            query = query.order(order_by, desc=descending)
            if limit is not None:
                start = offset or 0
                query = query.range(start, start + limit - 1)
            res = query.execute()
            return res.data or []
        except Exception:
            logger.exception("list_applications failed")
            return []

    def count_applications(
        self, status=None, course_id=None, search=None, date_from=None, date_to=None
    ):
        """Return the number of applications matching the same filters."""
        if not self.is_configured:
            return 0
        try:
            query = self._table("applications").select("id", count="exact")
            query = self._apply_application_filters(
                query, status, course_id, search, date_from, date_to
            )
            res = query.limit(1).execute()
            count = getattr(res, "count", None)
            if count is None:
                return len(res.data or [])
            return count
        except Exception:
            logger.exception("count_applications failed")
            return 0

    def status_counts(self) -> dict:
        counts = {
            "total": 0,
            "draft": 0,
            "submitted": 0,
            "under_review": 0,
            "correction_requested": 0,
            "approved": 0,
            "rejected": 0,
        }
        if not self.is_configured:
            return counts
        try:
            res = self._table("applications").select("status").execute()
            rows = res.data or []
            counts["total"] = len(rows)
            for row in rows:
                key = row.get("status")
                if key in counts:
                    counts[key] += 1
        except Exception:
            logger.exception("status_counts failed")
        return counts

    def applications_by_month(self, months: int = 6):
        """Return monthly application totals, oldest month first.

        Each item is ``{"month": "YYYY-MM", "label": "Mon YYYY", "count": n}``
        and is derived from ``applications.created_at`` so the reports page can
        plot a real trend without a bespoke SQL aggregate.
        """
        if not self.is_configured:
            return []
        try:
            res = self._table("applications").select("created_at").execute()
            rows = res.data or []
        except Exception:
            logger.exception("applications_by_month failed")
            return []

        now = datetime.now(timezone.utc)
        year, month = now.year, now.month
        keys = []
        for _ in range(max(1, int(months))):
            keys.append((year, month))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        keys.reverse()

        buckets = OrderedDict((f"{y:04d}-{m:02d}", 0) for y, m in keys)
        for row in rows:
            key = (row.get("created_at") or "")[:7]
            if key in buckets:
                buckets[key] += 1

        result = []
        for key, count in buckets.items():
            try:
                label = datetime.strptime(key, "%Y-%m").strftime("%b %Y")
            except ValueError:  # pragma: no cover - defensive
                label = key
            result.append({"month": key, "label": label, "count": count})
        return result

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------
    def add_audit_log(
        self,
        action,
        actor_id=None,
        actor_email=None,
        entity_type=None,
        entity_id=None,
        details=None,
        ip_address=None,
    ):
        """Record an administrative action. Never raises to the caller."""
        try:
            self._table("admin_audit_log").insert(
                {
                    "actor_id": actor_id,
                    "actor_email": actor_email,
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": str(entity_id) if entity_id is not None else None,
                    "details": details,
                    "ip_address": ip_address,
                }
            ).execute()
        except Exception:
            logger.exception("add_audit_log failed")

    def list_audit_log(self, limit: int = 20, actor_id=None):
        if not self.is_configured:
            return []
        try:
            query = self._table("admin_audit_log").select("*")
            if actor_id:
                query = query.eq("actor_id", actor_id)
            res = query.order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception:
            logger.exception("list_audit_log failed")
            return []

    # ------------------------------------------------------------------
    # Announcements
    # ------------------------------------------------------------------
    def list_announcements(self, limit: int = 20):
        if not self.is_configured:
            return []
        try:
            res = (
                self._table("announcements")
                .select("*")
                .eq("is_published", True)
                .order("published_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("list_announcements failed")
            return []

    # ------------------------------------------------------------------
    # Status history
    # ------------------------------------------------------------------
    def add_status_history(self, application_id, status, note=None, changed_by=None):
        try:
            self._table("application_status_history").insert(
                {
                    "application_id": application_id,
                    "status": status,
                    "note": note,
                    "changed_by": changed_by,
                }
            ).execute()
        except Exception:
            logger.exception("add_status_history failed")

    def list_status_history(self, application_id):
        if not self.is_configured:
            return []
        try:
            res = (
                self._table("application_status_history")
                .select("*")
                .eq("application_id", application_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("list_status_history failed")
            return []

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def create_document(self, application_id, user_id, doc_type, file_name, storage_path,
                        mime_type, size_bytes):
        payload = {
            "application_id": application_id,
            "user_id": user_id,
            "doc_type": doc_type,
            "file_name": file_name,
            "storage_path": storage_path,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "is_verified": False,
        }
        res = self._table("documents").insert(payload).execute()
        return res.data[0] if res.data else None

    def get_document(self, document_id: str):
        if not self.is_configured:
            return None
        try:
            res = self._table("documents").select("*").eq("id", document_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            logger.exception("get_document failed")
            return None

    def list_documents(self, application_id: str):
        if not self.is_configured:
            return []
        try:
            res = (
                self._table("documents")
                .select("*")
                .eq("application_id", application_id)
                .order("uploaded_at")
                .execute()
            )
            return res.data or []
        except Exception:
            logger.exception("list_documents failed")
            return []

    def list_documents_all(self, limit: int = 20, unverified_only: bool = False):
        """Recent documents across every application (admin notifications).

        Each row carries the related application (number + status) so the
        notifications page can link straight to the review screen.
        """
        if not self.is_configured:
            return []
        try:
            query = self._table("documents").select(
                "*, applications(application_number, status)"
            )
            if unverified_only:
                query = query.eq("is_verified", False)
            res = query.order("uploaded_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception:
            logger.exception("list_documents_all failed")
            return []

    def count_documents(self, unverified_only: bool = False) -> int:
        if not self.is_configured:
            return 0
        try:
            query = self._table("documents").select("id", count="exact")
            if unverified_only:
                query = query.eq("is_verified", False)
            res = query.limit(1).execute()
            count = getattr(res, "count", None)
            if count is None:
                return len(res.data or [])
            return count
        except Exception:
            logger.exception("count_documents failed")
            return 0

    def set_document_verified(self, document_id: str, verified: bool):
        res = (
            self._table("documents")
            .update({"is_verified": bool(verified)})
            .eq("id", document_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def delete_document(self, document_id: str):
        try:
            self._table("documents").delete().eq("id", document_id).execute()
        except Exception:
            logger.exception("delete_document failed")

    # ------------------------------------------------------------------
    # Storage (private bucket)
    # ------------------------------------------------------------------
    def upload_document(self, storage_path: str, file_bytes: bytes, content_type: str):
        options = {"content-type": content_type or "application/octet-stream", "upsert": "true"}
        self._client().storage.from_(self.bucket).upload(storage_path, file_bytes, options)
        return storage_path

    def create_signed_url(self, storage_path: str, expires_in: int = 300) -> str:
        if not self.is_configured:
            return ""
        try:
            res = self._client().storage.from_(self.bucket).create_signed_url(
                storage_path, expires_in
            )
            if isinstance(res, dict):
                return res.get("signedURL") or res.get("signedUrl") or res.get("signed_url") or ""
            return getattr(res, "signed_url", "") or ""
        except Exception:
            logger.exception("create_signed_url failed")
            return ""

    def delete_object(self, storage_path: str):
        try:
            self._client().storage.from_(self.bucket).remove([storage_path])
        except Exception:
            logger.exception("delete_object failed")

    def _list_storage_paths(self, prefix: str = ""):
        """Recursively list every object path in the private bucket."""
        paths = []
        offset = 0
        while True:
            try:
                items = self._client().storage.from_(self.bucket).list(
                    prefix, {"limit": 1000, "offset": offset}
                ) or []
            except Exception:
                logger.exception("storage list failed for %s", prefix or "/")
                break
            if not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                path = "{}/{}".format(prefix, name).strip("/")
                # Folders come back without an id and without metadata.
                if item.get("id") is None and item.get("metadata") is None:
                    paths.extend(self._list_storage_paths(path))
                else:
                    paths.append(path)
            if len(items) < 1000:
                break
            offset += len(items)
        return paths

    def purge_all_data(self):
        """Permanently delete every row and every uploaded file.

        Used by the destructive ``flask reset-project`` command. The schema,
        database functions, RLS policies and the storage bucket itself are
        kept; only application data is removed. Returns a dict with the number
        of rows removed per table (``None`` means that table could not be
        cleared) plus the number of storage objects removed.
        """
        if not self.is_configured:
            return {}

        deleted = {}

        # Storage first: the document rows that point at these paths are about
        # to be deleted, so collect the paths while they still exist.
        paths = self._list_storage_paths()
        for start in range(0, len(paths), 100):
            chunk = paths[start:start + 100]
            try:
                self._client().storage.from_(self.bucket).remove(chunk)
            except Exception:
                logger.exception("purge_all_data: removing storage objects failed")
        deleted["storage_objects"] = len(paths)

        # Child tables first, then users/courses. ``neq`` with an impossible
        # uuid is PostgREST's way of saying "every row" without a raw SQL call.
        impossible_id = "00000000-0000-0000-0000-000000000000"
        for table in (
            "admin_audit_log",
            "documents",
            "application_status_history",
            "applications",
            "announcements",
            "users",
            "courses",
        ):
            try:
                res = (
                    self._table(table)
                    .delete()
                    .neq("id", impossible_id)
                    .execute()
                )
                deleted[table] = len(res.data or [])
            except Exception:
                logger.exception("purge_all_data: deleting %s failed", table)
                deleted[table] = None
        return deleted


# Module-level placeholder replaced by the application factory.
service: "SupabaseService | None" = None


def init_service(app):
    """Create the singleton service and attach it to the Flask app.

    With ``USE_LOCAL_DB=true`` the app uses a persistent local JSON database
    instead of Supabase, so it works without a cloud project. Otherwise the
    real Supabase client is created.
    """
    global service

    if app.config.get("USE_LOCAL_DB"):
        import atexit

        from app.services.local_service import LocalSupabaseService

        data_file = app.config.get("LOCAL_DB_PATH") or os.path.join(
            app.instance_path, "local_db.json"
        )
        uploads_dir = app.config.get("LOCAL_UPLOADS_DIR") or os.path.join(
            app.instance_path, "uploads"
        )
        service = LocalSupabaseService(
            data_file=data_file,
            uploads_dir=uploads_dir,
        )
        app.supabase = service
        app.config["FAKE"] = service
        app.extensions["local_db"] = service

        @app.after_request
        def persist_local_database(response):
            try:
                service.save()
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("Could not save the local database")
            return response

        atexit.register(service.save)
        logger.info("Using local database at %s", data_file)
        return service

    service = SupabaseService(
        app.config["SUPABASE_URL"],
        app.config["SUPABASE_SERVICE_ROLE_KEY"],
        app.config["SUPABASE_STORAGE_BUCKET"],
    )
    app.supabase = service
    return service
