"""A local, file-backed stand-in for ``SupabaseService``.

This lets the whole application run without a Supabase project. It implements
the same service API in memory and can persist its state to a JSON file (plus
uploaded documents on disk) so register/login/course operations survive a
restart.

The automated tests use the same class with ``data_file=None`` and
``uploads_dir=None``, which keeps everything in memory.
"""

import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import quote

from app.utils.validators import (
    clean_name,
    format_display_name,
    split_full_name,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


# Mirrors app/services/supabase_service.py: the base users columns exist in
# every deployment; the optional ones come from sql/upgrade_students.sql and
# sql/upgrade_names.sql and may be absent on databases created from an older
# schema.
USER_BASE_COLUMNS = {
    "id", "email", "password_hash", "full_name", "phone", "role",
    "is_active", "created_at", "updated_at",
}
USER_OPTIONAL_COLUMNS = {
    "status", "registration_number", "assigned_course_id",
    "invite_token_hash", "invite_expires_at", "invite_used_at",
    "first_name", "middle_name", "last_name",
}

# Mirrors app/services/supabase_service.py for the courses table: base columns
# exist in every deployment; optional ones come from sql/upgrade_diploma.sql.
COURSE_BASE_COLUMNS = {
    "id", "code", "name", "description", "duration_years", "seats_total",
    "created_at", "updated_at",
}
COURSE_OPTIONAL_COLUMNS = {
    "program_type", "eligibility", "tuition_fee", "is_active",
    "eligible_qualifications",
}

# Mirrors app/services/supabase_service.py: the new SSLC/PUC/ITI application
# columns (sql/upgrade_qualifications.sql) may be absent on databases created
# from an older schema; writes of unknown columns become no-ops there.
APPLICATION_BASE_COLUMNS = {
    "id", "application_number", "user_id", "course_id", "status",
    "first_name", "last_name", "date_of_birth", "gender", "category",
    "nationality", "email", "phone", "address_line", "city", "state",
    "postal_code", "country", "qualifying_exam", "board_university",
    "school_name", "passing_year", "marks_obtained", "marks_total",
    "percentage", "admin_note", "submitted_at", "reviewed_at", "reviewed_by",
    "created_at", "updated_at",
}
APPLICATION_OPTIONAL_COLUMNS = {
    "middle_name",
    "institution_name", "stream", "trade", "affiliation", "roll_number",
}


class LocalSupabaseService:
    def __init__(self, data_file=None, uploads_dir=None):
        self.url = "local://database"
        self.users = {}
        self.courses = {}
        self.applications = {}
        self.documents = {}
        self.history = {}
        self.storage = {}
        self.audit = []
        self._email_index = {}
        self._seq = 0
        self.user_columns = set(USER_BASE_COLUMNS) | set(USER_OPTIONAL_COLUMNS)
        self.course_columns = set(COURSE_BASE_COLUMNS) | set(COURSE_OPTIONAL_COLUMNS)
        self.application_columns = (
            set(APPLICATION_BASE_COLUMNS) | set(APPLICATION_OPTIONAL_COLUMNS)
        )
        self.data_file = os.path.abspath(data_file) if data_file else None
        self.uploads_dir = os.path.abspath(uploads_dir) if uploads_dir else None
        self._lock = threading.RLock()
        if self.uploads_dir:
            os.makedirs(self.uploads_dir, exist_ok=True)
        if self.data_file:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            self._load()
        # Mirrors the real service: None on success, a message when the last
        # course query failed. Tests can force a failure with
        # simulate_course_query_error().
        self.last_course_error = None
        self._course_query_fails = False

    @property
    def is_configured(self):
        return True

    # -- persistence ---------------------------------------------------
    def _load(self):
        if not self.data_file or not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.users = {str(k): v for k, v in (data.get("users") or {}).items()}
        self.courses = {str(k): v for k, v in (data.get("courses") or {}).items()}
        self.applications = {
            str(k): v for k, v in (data.get("applications") or {}).items()
        }
        self.documents = {
            str(k): v for k, v in (data.get("documents") or {}).items()
        }
        self.history = {str(k): v for k, v in (data.get("history") or {}).items()}
        self.audit = list(data.get("audit") or [])
        self._seq = int(data.get("seq") or 0)
        if data.get("user_columns"):
            self.user_columns = set(data["user_columns"])
        if data.get("course_columns"):
            self.course_columns = set(data["course_columns"])
        if data.get("application_columns"):
            self.application_columns = set(data["application_columns"])
        self._email_index = {}
        for user_id, user in self.users.items():
            email = (user.get("email") or "").lower().strip()
            if email:
                self._email_index[email] = user_id

    def save(self):
        """Persist the in-memory state atomically (no-op for test instances)."""
        if not self.data_file:
            return
        with self._lock:
            payload = {
                "version": 1,
                "seq": self._seq,
                "users": self.users,
                "courses": self.courses,
                "applications": self.applications,
                "documents": self.documents,
                "history": self.history,
                "audit": self.audit,
                "user_columns": sorted(self.user_columns),
                "course_columns": sorted(self.course_columns),
                "application_columns": sorted(self.application_columns),
            }
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            # Use a unique temporary file so two processes (or two threads) can
            # never collide on the same ".tmp" path. On Windows, replacing a
            # file that another process is briefly reading can fail with
            # PermissionError, so retry for a short while before giving up.
            temporary = "{}.{}.{}.tmp".format(
                self.data_file, os.getpid(), threading.get_ident()
            )
            try:
                with open(temporary, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                for attempt in range(20):
                    try:
                        os.replace(temporary, self.data_file)
                        break
                    except PermissionError:
                        if attempt == 19:
                            raise
                        time.sleep(0.05 * min(attempt + 1, 10))
            finally:
                try:
                    if os.path.exists(temporary):
                        os.remove(temporary)
                except OSError:
                    pass

    def _safe_upload_path(self, storage_path):
        if not self.uploads_dir:
            raise ValueError("Local uploads directory is not configured.")
        root = os.path.abspath(self.uploads_dir)
        target = os.path.abspath(os.path.join(root, storage_path))
        if os.path.commonpath([root, target]) != root:
            raise ValueError("Invalid storage path.")
        return target

    def uploads_path(self, storage_path):
        return self._safe_upload_path(storage_path)

    def get_document_by_storage_path(self, storage_path):
        for document in self.documents.values():
            if document.get("storage_path") == storage_path:
                return dict(document)
        return None

    # -- users ---------------------------------------------------------
    def _user_columns(self):
        return self.user_columns

    def simulate_legacy_users_schema(self):
        """Simulate a database created before the student-lifecycle migration.

        ``users`` has no status / registration_number / assigned_course_id /
        invite_* columns, which is what makes PostgREST return PGRST204 for an
        INSERT that names ``status``. Writes of unknown columns become no-ops
        and unknown query filters are ignored, matching the schema-aware
        service.
        """
        self.user_columns = set(USER_BASE_COLUMNS)

    def create_user(self, email, password_hash, full_name=None, first_name=None,
                    middle_name=None, last_name=None, phone=None, role="student",
                    registration_number=None, status="active",
                    assigned_course_id=None):
        first = clean_name(first_name) or None
        middle = clean_name(middle_name) or None
        last = clean_name(last_name) or None
        if not first and not middle and not last and full_name:
            first, middle, last = split_full_name(full_name)
        columns = self._user_columns()
        payload = {
            "id": str(uuid.uuid4()),
            "email": email.lower().strip(),
            "password_hash": password_hash,
            "full_name": format_display_name(first, middle, last),
            "phone": phone,
            "role": role,
            "is_active": status == "active",
            "created_at": _now(),
            "updated_at": _now(),
        }
        for key, value in (("first_name", first), ("middle_name", middle), ("last_name", last)):
            if key in columns:
                payload[key] = value
        if "status" in columns:
            payload["status"] = status
        if registration_number is not None and "registration_number" in columns:
            payload["registration_number"] = registration_number
        if assigned_course_id is not None and "assigned_course_id" in columns:
            payload["assigned_course_id"] = assigned_course_id
        for col in ("invite_token_hash", "invite_expires_at", "invite_used_at"):
            if col in columns:
                payload[col] = None
        uid = payload["id"]
        self.users[uid] = payload
        self._email_index[payload["email"]] = uid
        return dict(payload)

    def get_user_by_email(self, email):
        uid = self._email_index.get((email or "").lower().strip())
        return dict(self.users[uid]) if uid else None

    def get_user_by_id(self, user_id):
        row = self.users.get(str(user_id))
        return dict(row) if row else None

    def get_users_by_ids(self, user_ids):
        result = []
        for uid in (user_ids or []):
            row = self.users.get(str(uid))
            if row:
                result.append({
                    "id": row["id"],
                    "full_name": row.get("full_name"),
                    "role": row.get("role"),
                })
        return result

    def update_user(self, user_id, payload):
        row = self.users.get(str(user_id))
        if not row:
            return None
        columns = self._user_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        row.update(payload)
        return dict(row)

    def promote_to_admin(self, user_id, password_hash=None):
        """Mirror of the real service: grant admin (optional password refresh)."""
        payload = {"role": "admin", "is_active": True, "status": "active"}
        if password_hash:
            payload["password_hash"] = password_hash
        return self.update_user(user_id, payload)

    def set_user_active(self, user_id, is_active):
        return self.set_student_status(
            user_id, "active" if is_active else "inactive"
        )

    def set_student_status(self, user_id, status, extra=None):
        columns = self._user_columns()
        payload = {"is_active": status == "active"}
        if "status" in columns:
            payload["status"] = status
        if extra:
            payload.update({k: v for k, v in extra.items() if k in columns})
        return self.update_user(user_id, payload)

    def count_active_admins(self):
        return len([
            r for r in self.users.values()
            if r.get("role") == "admin" and r.get("is_active", True)
        ])

    def delete_user(self, user_id):
        uid = str(user_id)
        row = self.users.pop(uid, None)
        if row:
            self._email_index.pop(row.get("email"), None)
        # Simulate the database's ON DELETE CASCADE.
        app_ids = [
            aid for aid, a in self.applications.items()
            if str(a.get("user_id")) == uid
        ]
        for aid in app_ids:
            self.applications.pop(aid, None)
            self.history.pop(aid, None)
        for did in [
            d for d, r in self.documents.items() if str(r.get("user_id")) == uid
        ]:
            self.documents.pop(did, None)
        return dict(row) if row else None

    def registration_number_exists(self, registration_number, exclude_id=None):
        target = (registration_number or "").strip().lower()
        if not target:
            return False
        for row in self.users.values():
            if str(row.get("id")) == str(exclude_id):
                continue
            if (row.get("registration_number") or "").strip().lower() == target:
                return True
        return False

    def set_invitation(self, user_id, token_hash, expires_at):
        return self.update_user(user_id, {
            "invite_token_hash": token_hash,
            "invite_expires_at": expires_at,
            "invite_used_at": None,
        })

    def get_user_by_invite_hash(self, token_hash):
        for row in self.users.values():
            if row.get("invite_token_hash") and row.get("invite_token_hash") == token_hash:
                return dict(row)
        return None

    def consume_invitation(self, user_id, password_hash):
        return self.update_user(user_id, {
            "password_hash": password_hash,
            "status": "active",
            "is_active": True,
            "invite_token_hash": None,
            "invite_expires_at": None,
            "invite_used_at": _now(),
        })

    def document_paths_by_user(self, user_id):
        return [
            r["storage_path"] for r in self.documents.values()
            if str(r.get("user_id")) == str(user_id) and r.get("storage_path")
        ]

    # -- students (admin views) ---------------------------------------
    def _student_match(self, row, search=None, status=None):
        state = row.get("status") or ("active" if row.get("is_active", True) else "inactive")
        if status in ("active", "inactive", "withdrawn") and state != status:
            return False
        if search:
            term = search.lower()
            hay = [
                (row.get("full_name") or "").lower(),
                (row.get("email") or "").lower(),
                (row.get("phone") or "").lower(),
                (row.get("registration_number") or "").lower(),
            ]
            for app in self.applications.values():
                if str(app.get("user_id")) == str(row.get("id")):
                    hay.append((app.get("application_number") or "").lower())
            if not any(term in value for value in hay):
                return False
        return True

    def list_students(self, search=None, status=None, order_by="created_at",
                      descending=True, limit=None, offset=None):
        if "status" not in self._user_columns():
            status = None
            if order_by not in self._user_columns():
                order_by = "created_at"
                descending = True
        rows = [r for r in self.users.values() if r.get("role") == "student"]
        rows = [r for r in rows if self._student_match(r, search, status)]

        def _key(row):
            value = row.get(order_by)
            if isinstance(value, bool):
                return (1, int(value))
            if isinstance(value, (int, float)):
                return (1, value)
            return (0, str(value or "").lower())

        rows.sort(key=_key, reverse=bool(descending))
        if limit is not None:
            start = offset or 0
            rows = rows[start:start + limit]
        return [dict(r) for r in rows]

    def count_students(self, search=None, status=None):
        if "status" not in self._user_columns():
            status = None
        return len([
            r for r in self.users.values()
            if r.get("role") == "student" and self._student_match(r, search, status)
        ])

    def get_student(self, user_id):
        row = self.users.get(str(user_id))
        if row and row.get("role") == "student":
            return dict(row)
        return None

    # -- audit log -----------------------------------------------------
    def add_audit_log(self, action, actor_id=None, actor_email=None,
                      entity_type=None, entity_id=None, details=None,
                      ip_address=None):
        self.audit.append({
            "id": str(uuid.uuid4()),
            "actor_id": str(actor_id) if actor_id else None,
            "actor_email": actor_email,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
            "details": details,
            "ip_address": ip_address,
            "created_at": _now(),
        })

    def list_audit_log(self, limit=20, actor_id=None):
        rows = [
            r for r in self.audit
            if not actor_id or str(r.get("actor_id")) == str(actor_id)
        ]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return [dict(r) for r in rows[:limit]]

    # -- courses -------------------------------------------------------
    def describe_schema(self):
        """Mirror of the real service: table -> sorted column names."""
        return {
            "users": sorted(self.user_columns),
            "courses": sorted(self.course_columns),
            "applications": sorted(self.application_columns),
        }

    def count_rows(self, table, cap=1000):
        """Mirror of the real service: (row_count, truncated)."""
        rows = {
            "users": self.users,
            "courses": self.courses,
            "applications": self.applications,
            "documents": self.documents,
        }.get(table)
        if rows is None:
            return 0, False
        return len(rows), len(rows) >= cap

    def _course_columns(self):
        return self.course_columns

    def simulate_legacy_courses_schema(self):
        """Simulate a database created before the Diploma/Polytechnic upgrade.

        ``courses`` has no program_type / eligibility / tuition_fee /
        is_active columns. Writes of unknown columns become no-ops and
        unknown query filters are ignored, matching the schema-aware service.
        """
        self.course_columns = set(COURSE_BASE_COLUMNS)

    def simulate_course_query_error(self):
        """Force list_courses() to behave like a failed database query.

        Used to prove a page distinguishes "course query failed" from
        "no courses configured yet".
        """
        self._course_query_fails = True

    def course_schema_missing(self):
        """Mirror of the real service: optional course columns still absent."""
        return sorted(COURSE_OPTIONAL_COLUMNS - self._course_columns())

    def simulate_legacy_applications_schema(self):
        """Simulate a database created before the qualifications upgrade.

        ``applications`` has no institution_name / stream / trade /
        affiliation / roll_number columns. Writes of those columns become
        no-ops, matching the schema-aware service (PGRST204 avoidance).
        """
        self.application_columns = set(APPLICATION_BASE_COLUMNS)

    def list_courses(self, active_only=False, program_type=None):
        if self._course_query_fails:
            self.last_course_error = (
                "The course catalogue could not be loaded from the database."
            )
            return []
        columns = self._course_columns()
        rows = list(self.courses.values())
        if active_only and "is_active" in columns:
            rows = [r for r in rows if r.get("is_active", True)]
        if program_type in ("degree", "diploma") and "program_type" in columns:
            rows = [r for r in rows if r.get("program_type", "degree") == program_type]
        self.last_course_error = None
        return [dict(r) for r in sorted(rows, key=lambda r: r["name"])]

    def get_course(self, course_id):
        row = self.courses.get(str(course_id))
        return dict(row) if row else None

    def create_course(self, payload):
        columns = self._course_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        cid = str(uuid.uuid4())
        row = {
            "id": cid,
            "code": payload["code"],
            "name": payload["name"],
            "description": payload.get("description"),
            "duration_years": payload.get("duration_years", 4),
            "seats_total": payload.get("seats_total", 60),
            "created_at": _now(),
            "updated_at": _now(),
        }
        for col in sorted(COURSE_OPTIONAL_COLUMNS):
            if col in columns:
                # Mirror the DB column defaults (not null default 'degree',
                # is_active default true) when the payload omits them.
                if col == "is_active":
                    row[col] = payload.get(col, True)
                elif col == "program_type":
                    row[col] = payload.get(col, "degree")
                else:
                    row[col] = payload.get(col)
        self.courses[cid] = row
        return dict(row)

    def update_course(self, course_id, payload):
        row = self.courses.get(str(course_id))
        if not row:
            return None
        columns = self._course_columns()
        payload = {k: v for k, v in payload.items() if k in columns}
        row.update(payload)
        row["updated_at"] = _now()
        return dict(row)

    def set_course_active(self, course_id, is_active):
        if "is_active" not in self._course_columns():
            return self.get_course(course_id)
        return self.update_course(course_id, {"is_active": bool(is_active)})

    def delete_course(self, course_id):
        """Permanently remove a course.

        Mirrors the database's ``on delete set null`` foreign keys for
        applications and assigned students, so existing records keep their
        other data instead of becoming unreadable.
        """
        cid = str(course_id)
        row = self.courses.pop(cid, None)
        if not row:
            return None
        for application in self.applications.values():
            if str(application.get("course_id")) == cid:
                application["course_id"] = None
        for user in self.users.values():
            if str(user.get("assigned_course_id")) == cid:
                user["assigned_course_id"] = None
        return dict(row)

    def application_counts_by_course(self):
        counts = {}
        for row in self.applications.values():
            if row.get("status") == "draft":
                continue
            course_id = row.get("course_id")
            if course_id:
                counts[str(course_id)] = counts.get(str(course_id), 0) + 1
        return counts

    def application_counts_by_user(self):
        counts = {}
        for row in self.applications.values():
            user_id = row.get("user_id")
            if user_id:
                counts[str(user_id)] = counts.get(str(user_id), 0) + 1
        return counts

    def application_numbers_by_user(self):
        numbers = {}
        rows = sorted(
            self.applications.values(),
            key=lambda r: r.get("created_at") or "",
            reverse=True,
        )
        for row in rows:
            user_id = row.get("user_id")
            number = row.get("application_number")
            if user_id and number and str(user_id) not in numbers:
                numbers[str(user_id)] = number
        return numbers

    def course_status_counts(self):
        counts = {
            "total": 0, "active": 0, "inactive": 0,
            "diploma": 0, "diploma_active": 0, "degree": 0,
        }
        for course in self.courses.values():
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

    def applications_by_month(self, months=6):
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
        for row in self.applications.values():
            key = (row.get("created_at") or "")[:7]
            if key in buckets:
                buckets[key] += 1
        result = []
        for key, count in buckets.items():
            try:
                label = datetime.strptime(key, "%Y-%m").strftime("%b %Y")
            except ValueError:
                label = key
            result.append({"month": key, "label": label, "count": count})
        return result

    # -- application numbers ------------------------------------------
    def generate_application_number(self):
        self._seq += 1
        return "ADM-2026-{:05d}".format(self._seq)

    # -- applications --------------------------------------------------
    def _with_course(self, app):
        row = dict(app)
        course = self.courses.get(str(app.get("course_id")))
        row["courses"] = (
            {"id": course["id"], "code": course["code"], "name": course["name"]}
            if course
            else None
        )
        return row

    def create_application(self, user_id, data):
        aid = str(uuid.uuid4())
        # Mirror the real service: never write a column missing from this
        # database (PGRST204 would reject the write).
        data = {k: v for k, v in data.items() if k in self.application_columns}
        row = {
            "id": aid,
            "application_number": None,
            "user_id": str(user_id),
            "status": "draft",
            "admin_note": None,
            "submitted_at": None,
            "reviewed_at": None,
            "reviewed_by": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        row.update(data)
        self.applications[aid] = row
        return self._with_course(row)

    def get_application(self, application_id):
        row = self.applications.get(str(application_id))
        return self._with_course(row) if row else None

    def get_application_by_number(self, application_number):
        for row in self.applications.values():
            if row.get("application_number") == application_number:
                return self._with_course(row)
        return None

    def update_application(self, application_id, data):
        row = self.applications.get(str(application_id))
        if not row:
            return None
        data = {k: v for k, v in data.items() if k in self.application_columns}
        row.update(data)
        row["updated_at"] = _now()
        return self._with_course(row)

    def list_applications_for_user(self, user_id):
        rows = [r for r in self.applications.values() if r["user_id"] == str(user_id)]
        return [self._with_course(r) for r in rows]

    def _match_filters(self, status=None, course_id=None, search=None,
                       date_from=None, date_to=None):
        rows = list(self.applications.values())
        if status:
            rows = [r for r in rows if r["status"] == status]
        if course_id:
            rows = [r for r in rows if str(r.get("course_id")) == str(course_id)]
        if date_from:
            rows = [r for r in rows if (r.get("created_at") or "") >= date_from]
        if date_to:
            rows = [r for r in rows if (r.get("created_at") or "") <= date_to]
        if search:
            term = search.lower()
            rows = [
                r
                for r in rows
                if term in (r.get("application_number") or "").lower()
                or term in (r.get("first_name") or "").lower()
                or term in (r.get("last_name") or "").lower()
                or term in (r.get("email") or "").lower()
            ]
        return rows

    def list_applications(self, status=None, course_id=None, search=None,
                          date_from=None, date_to=None, order_by="created_at",
                          descending=True, limit=None, offset=None):
        def _key(row):
            value = row.get(order_by)
            if isinstance(value, (int, float)):
                return (1, value)
            return (0, str(value or ""))
        rows = self._match_filters(status, course_id, search, date_from, date_to)
        rows.sort(key=_key, reverse=bool(descending))
        if limit is not None:
            start = offset or 0
            rows = rows[start:start + limit]
        return [self._with_course(r) for r in rows]

    def count_applications(self, status=None, course_id=None, search=None,
                            date_from=None, date_to=None):
        return len(self._match_filters(status, course_id, search, date_from, date_to))

    def status_counts(self):
        counts = {
            "total": 0,
            "draft": 0,
            "submitted": 0,
            "under_review": 0,
            "correction_requested": 0,
            "approved": 0,
            "rejected": 0,
        }
        for row in self.applications.values():
            counts["total"] += 1
            if row["status"] in counts:
                counts[row["status"]] += 1
        return counts

    # -- announcements -------------------------------------------------
    def list_announcements(self, limit=20):
        return []

    # -- history -------------------------------------------------------
    def add_status_history(self, application_id, status, note=None, changed_by=None):
        self.history.setdefault(str(application_id), []).append(
            {
                "id": str(uuid.uuid4()),
                "application_id": str(application_id),
                "status": status,
                "note": note,
                "changed_by": changed_by,
                "created_at": _now(),
            }
        )

    def list_status_history(self, application_id):
        return list(reversed(self.history.get(str(application_id), [])))

    # -- documents -----------------------------------------------------
    def create_document(self, application_id, user_id, doc_type, file_name,
                        storage_path, mime_type, size_bytes):
        did = str(uuid.uuid4())
        row = {
            "id": did,
            "application_id": str(application_id),
            "user_id": str(user_id),
            "doc_type": doc_type,
            "file_name": file_name,
            "storage_path": storage_path,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "is_verified": False,
            "uploaded_at": _now(),
        }
        self.documents[did] = row
        return dict(row)

    def get_document(self, document_id):
        row = self.documents.get(str(document_id))
        return dict(row) if row else None

    def list_documents(self, application_id):
        return [dict(r) for r in self.documents.values() if r["application_id"] == str(application_id)]

    def list_documents_all(self, limit=20, unverified_only=False):
        rows = [
            {
                **dict(r),
                "applications": {
                    "application_number": self.applications.get(r["application_id"], {}).get("application_number"),
                    "status": self.applications.get(r["application_id"], {}).get("status"),
                },
            }
            for r in self.documents.values()
            if not unverified_only or not r["is_verified"]
        ]
        rows.sort(key=lambda r: r.get("uploaded_at") or "", reverse=True)
        return rows[:limit]

    def count_documents(self, unverified_only=False):
        matches = [r for r in self.documents.values() if not unverified_only or not r["is_verified"]]
        return len(matches)

    def set_document_verified(self, document_id, verified):
        row = self.documents.get(str(document_id))
        if not row:
            return None
        row["is_verified"] = bool(verified)
        return dict(row)

    def delete_document(self, document_id):
        self.documents.pop(str(document_id), None)

    # -- storage -------------------------------------------------------
    def upload_document(self, storage_path, file_bytes, content_type):
        if self.uploads_dir:
            target = self._safe_upload_path(storage_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(file_bytes)
            # Keep the content type (not the bytes) so the JSON file stays small.
            self.storage[storage_path] = content_type
            return storage_path
        self.storage[storage_path] = file_bytes
        return storage_path

    def create_signed_url(self, storage_path, expires_in=300):
        if self.uploads_dir:
            return "/local-documents/{}".format(quote(storage_path, safe="/"))
        return "https://fake.supabase.co/storage/v1/object/sign/{}".format(storage_path)

    def delete_object(self, storage_path):
        if self.uploads_dir:
            try:
                os.remove(self._safe_upload_path(storage_path))
            except FileNotFoundError:
                pass
            self.storage.pop(storage_path, None)
            return
        self.storage.pop(storage_path, None)

    def purge_all_data(self):
        """Mirror of the destructive reset used by the CLI command."""
        deleted = {
            "users": len(self.users),
            "courses": len(self.courses),
            "applications": len(self.applications),
            "documents": len(self.documents),
            "storage_objects": len(self.storage),
            "application_status_history": sum(
                len(rows) for rows in self.history.values()
            ),
            "admin_audit_log": len(self.audit),
            "announcements": 0,
        }
        self.users.clear()
        self._email_index.clear()
        self.courses.clear()
        self.applications.clear()
        self.documents.clear()
        self.history.clear()
        self.audit.clear()
        self.storage.clear()
        if self.uploads_dir and os.path.isdir(self.uploads_dir):
            for root, directories, files in os.walk(
                self.uploads_dir, topdown=False
            ):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except OSError:
                        pass
                for name in directories:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except OSError:
                        pass
        self.save()
        return deleted
