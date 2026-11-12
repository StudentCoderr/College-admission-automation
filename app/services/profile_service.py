"""Central student-profile (contact) service.

One place to read and write the contact details a student shares with the
admissions office: the name parts, the contact phone and the account email.
The student profile page, the admission application form and the application
snapshot all flow through here, so they cannot drift apart.

The functions take the *authenticated* user object (Flask-Login's
``current_user``) and always write to ``user.id``. A user id is never accepted
from the request, so one student can never read or modify another student's
contact details.

Snapshot rule: an admission application keeps its own copy of the contact
email and phone because the college needs the details *as submitted*. That
snapshot is intentional. The account email is the immutable login identity and
is therefore never changed from an application.
"""

from app.utils.validators import (
    clean_str,
    format_display_name,
    is_valid_phone,
    split_full_name,
    validate_names,
)

NAME_FIELDS = ("first_name", "middle_name", "last_name")
CONTACT_FIELDS = NAME_FIELDS + ("email", "phone")


def profile_contact(user):
    """Return the signed-in user's contact details shaped for a form.

    Null-safe: a legacy row that has no split name parts falls back to
    splitting ``full_name``, and missing optional values become ``""`` so the
    templates never render ``None``.
    """
    first = getattr(user, "first_name", None)
    middle = getattr(user, "middle_name", None)
    last = getattr(user, "last_name", None)
    if not first and not middle and not last:
        first, middle, last = split_full_name(getattr(user, "full_name", None))
    return {
        "first_name": first or "",
        "middle_name": middle or "",
        "last_name": last or "",
        "email": clean_str(getattr(user, "email", None), 254),
        "phone": clean_str(getattr(user, "phone", None), 20),
    }


def merge_contact(snapshot, profile):
    """Overlay ``profile`` defaults on a saved ``snapshot``, filling blanks only.

    An existing application is authoritative: the profile is used only for
    fields the snapshot is missing entirely, so legacy applications with no
    phone (or no middle name) still show everything the student has on file.
    """
    merged = dict(snapshot or {})
    for key in CONTACT_FIELDS:
        if not merged.get(key) and profile.get(key):
            merged[key] = profile[key]
    return merged


def validate_profile_contact(form, current_email):
    """Validate an edit-profile submission.

    Returns ``(values, errors)``. ``values`` is the persistence payload (the
    immutable email is deliberately excluded). Phone rules match the
    registration and application forms. A changed email is rejected rather
    than silently ignored because the email is the login identity.
    """
    (first, middle, last), errors = validate_names(
        form.get("first_name"), form.get("middle_name"), form.get("last_name")
    )

    phone = clean_str(form.get("phone"), 20).strip()
    if phone and not is_valid_phone(phone):
        errors["phone"] = "Enter a valid phone number (7-20 digits)."

    email = clean_str(form.get("email"), 254).lower()
    if email and email != (current_email or "").lower():
        errors["email"] = (
            "The email address is your login identity and cannot be changed."
        )

    values = {
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "full_name": format_display_name(first, middle, last),
        "phone": phone or None,
    }
    return values, errors


def save_profile_contact(service, user, values):
    """Persist the student's own profile contact details.

    Writes to ``user.id`` (never an id from the request) and updates the live
    Flask-Login object so the page reflects the change without a re-login.
    """
    updated = service.update_user(user.id, values)
    _apply_to_user(user, values)
    return updated or values


def sync_profile_contact(service, user, data):
    """Copy non-empty application contact details back to the student profile.

    Only non-empty submitted values are written, so blanking an optional field
    on the application never erases a value already saved on the profile. The
    account email is intentionally left untouched (the application holds a
    historical snapshot; the account email is the login identity). Returns the
    updated row, or ``None`` when nothing changed.
    """
    changes = {}
    for key in NAME_FIELDS:
        submitted = data.get(key)
        if submitted and submitted != getattr(user, key, None):
            changes[key] = submitted

    phone = clean_str(data.get("phone"), 20).strip()
    if phone and phone != (getattr(user, "phone", None) or ""):
        changes["phone"] = phone

    if not changes:
        return None

    changes["full_name"] = format_display_name(
        changes.get("first_name", getattr(user, "first_name", None)),
        changes.get("middle_name", getattr(user, "middle_name", None)),
        changes.get("last_name", getattr(user, "last_name", None)),
    )
    updated = service.update_user(user.id, changes)
    _apply_to_user(user, changes)
    return updated


def _apply_to_user(user, values):
    """Reflect saved values on the in-memory user object."""
    for key in NAME_FIELDS:
        if key in values:
            setattr(user, key, values[key])
    if "phone" in values:
        user.phone = values["phone"]
    if "full_name" in values:
        user.full_name = values["full_name"]
    elif any(key in values for key in NAME_FIELDS):
        user.full_name = format_display_name(
            getattr(user, "first_name", None),
            getattr(user, "middle_name", None),
            getattr(user, "last_name", None),
        )
