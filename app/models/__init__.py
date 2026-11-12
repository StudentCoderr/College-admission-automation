"""Lightweight model wrappers around Supabase rows.

Supabase stores data in PostgreSQL; these classes give the rest of the app a
typed, convenient view over rows without an ORM.
"""

from flask_login import UserMixin

from app.utils.validators import format_display_name


class User(UserMixin):
    """A row from the `users` table."""

    def __init__(self, data: dict):
        self._data = data or {}
        self.id = str(self._data.get("id", ""))
        self.email = self._data.get("email", "")
        self.first_name = self._data.get("first_name")
        self.middle_name = self._data.get("middle_name")
        self.last_name = self._data.get("last_name")
        # Display name: built from the individual parts so optional names are
        # formatted correctly (e.g. "Ananya Sharma"), falling back to the
        # legacy full_name column for rows that predate the split.
        self.full_name = format_display_name(
            self.first_name,
            self.middle_name,
            self.last_name,
            fallback=self._data.get("full_name", ""),
        )
        self.phone = self._data.get("phone")
        self.role = self._data.get("role", "student")
        self.status = self._data.get("status") or (
            "active" if self._data.get("is_active", True) else "inactive"
        )
        self.registration_number = self._data.get("registration_number")
        self.assigned_course_id = self._data.get("assigned_course_id")
        self._is_active = self._data.get("is_active", True)
        self.created_at = self._data.get("created_at")

    # Flask-Login requires is_active to be a bool attribute/property. An account
    # is login-eligible only while its status is "active".
    @property
    def is_active(self):  # noqa: D401 - Flask-Login contract
        return bool(self._is_active) and self.status == "active"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_student(self) -> bool:
        return self.role == "student"

    @property
    def password_hash(self) -> str:
        return self._data.get("password_hash", "")

    def get_id(self) -> str:
        return self.id

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "phone": self.phone,
            "role": self.role,
            "status": self.status,
            "registration_number": self.registration_number,
            "assigned_course_id": self.assigned_course_id,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }


# Student account statuses and the labels shown in the UI.
STUDENT_STATUSES = ["active", "inactive", "withdrawn"]

STUDENT_STATUS_LABELS = {
    "active": "Active",
    "inactive": "Inactive",
    "withdrawn": "Withdrawn",
}



# Application statuses and the labels shown in the UI
APPLICATION_STATUSES = [
    "draft",
    "submitted",
    "under_review",
    "correction_requested",
    "approved",
    "rejected",
]

STATUS_LABELS = {
    "draft": "Draft",
    "submitted": "Submitted",
    "under_review": "Under Review",
    "correction_requested": "Correction Requested",
    "approved": "Approved",
    "rejected": "Rejected",
}

# Document types accepted with an application
DOCUMENT_TYPES = {
    "marks_card": "Marks Card / Transcript",
    "id_proof": "Government ID Proof",
    "photo": "Passport-size Photograph",
    "signature": "Signature",
    "transfer_certificate": "Transfer / Migration Certificate",
    "other": "Other Supporting Document",
}
