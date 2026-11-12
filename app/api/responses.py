"""Consistent JSON response helpers for the REST API.

Every API response carries an ``ok`` boolean. Successful responses include the
resource keys the caller asked for; failures always include an ``error`` string
and, for field-level problems, an ``errors`` object.
"""

from flask import jsonify


def success(**fields):
    """200 OK with ``ok: true`` plus the supplied resource fields."""
    payload = {"ok": True}
    payload.update(fields)
    return jsonify(payload)


def created(**fields):
    """201 Created with ``ok: true`` plus the supplied resource fields."""
    payload = {"ok": True}
    payload.update(fields)
    return jsonify(payload), 201


def failure(message, status=400, errors=None, **extra):
    """An error response with ``ok: false`` and an ``error`` message."""
    payload = {"ok": False, "error": message}
    if errors:
        payload["errors"] = errors
    payload.update(extra)
    return jsonify(payload), status
