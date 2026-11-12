"""Private document uploads.

Handles validation (extension, size, content type), the private-storage upload
and the metadata row. Storage paths are namespaced by application id so one
student can never read another student's files. Access is always granted via a
short-lived signed URL rather than a public URL.
"""

import os
import uuid

from app.models import DOCUMENT_TYPES
from app.services.application_service import EDITABLE_STATUSES
from app.services.errors import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from app.utils.validators import allowed_file, clean_str

# Canonical MIME type per allowed extension. Used when the browser sends a
# generic content type such as application/octet-stream.
_EXTENSION_MIME = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def _read_and_validate(file, config):
    """Return (bytes, safe_name, mime_type) or raise ValidationError."""
    if file is None or not getattr(file, "filename", ""):
        raise ValidationError(
            "Choose a file to upload.", errors={"file": "Choose a file to upload."}
        )

    filename = os.path.basename(file.filename)
    if not allowed_file(filename, config["ALLOWED_EXTENSIONS"]):
        raise ValidationError(
            "Only PDF, JPG and PNG files are allowed.",
            errors={"file": "Only PDF, JPG and PNG files are allowed."},
        )

    file_bytes = file.read()
    if not file_bytes:
        raise ValidationError(
            "The uploaded file is empty.", errors={"file": "The uploaded file is empty."}
        )
    if len(file_bytes) > config["MAX_CONTENT_LENGTH"]:
        raise ServiceError("File too large. Maximum size is 5 MB.", 413)

    mime_type = getattr(file, "mimetype", None) or "application/octet-stream"
    if mime_type not in config["ALLOWED_MIME_TYPES"]:
        ext = filename.rsplit(".", 1)[1].lower()
        mime_type = _EXTENSION_MIME.get(ext, "application/octet-stream")

    safe_name = filename.replace(" ", "_")
    return file_bytes, safe_name, mime_type


def upload_document(service, user, application, doc_type, file, config):
    """Upload a validated file and record its metadata."""
    if application.get("status") not in EDITABLE_STATUSES:
        raise ConflictError(
            "Documents can only be changed while the application is editable.", 409
        )

    doc_type = clean_str(doc_type)
    if doc_type not in DOCUMENT_TYPES:
        raise ValidationError(
            "Select a valid document type.",
            errors={"doc_type": "Select a valid document type."},
        )

    file_bytes, safe_name, mime_type = _read_and_validate(file, config)

    storage_path = "applications/{}/{}".format(
        application["id"], uuid.uuid4().hex + "_" + safe_name
    )
    service.upload_document(storage_path, file_bytes, mime_type)
    document = service.create_document(
        application_id=application["id"],
        user_id=user.id,
        doc_type=doc_type,
        file_name=safe_name,
        storage_path=storage_path,
        mime_type=mime_type,
        size_bytes=len(file_bytes),
    )
    service.add_status_history(
        application["id"],
        application.get("status", "draft"),
        "Document uploaded: {}.".format(DOCUMENT_TYPES[doc_type]),
        user.id,
    )
    return document


def delete_document(service, user, document):
    """Delete a document owned by ``user`` while the application is editable."""
    application = service.get_application(document.get("application_id"))
    if not application or str(application.get("user_id")) != str(user.id):
        raise NotFoundError("Document not found.")
    if application.get("status") not in EDITABLE_STATUSES:
        raise ConflictError(
            "Documents can only be changed while the application is editable.", 409
        )
    service.delete_object(document.get("storage_path"))
    service.delete_document(document.get("id"))
    return True


def signed_url(service, document, expires_in):
    """Return a short-lived signed URL for a private document."""
    url = service.create_signed_url(document.get("storage_path"), expires_in)
    if not url:
        raise ServiceError("Could not generate a secure link for this document.", 502)
    return url
