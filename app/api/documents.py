"""Document endpoints: list, upload, fetch a signed link and delete.

Bytes live in a *private* Supabase Storage bucket. Read access is only ever
granted through a short-lived signed URL, and only to the owning student or an
administrator.
"""

from flask import Blueprint, current_app, request
from flask_login import current_user

from app.api.access import load_visible_application
from app.api.decorators import api_login_required, api_student_required
from app.api.responses import created, failure, success
from app.api.serializers import serialize_document
from app.services import document_service

bp = Blueprint("api_documents", __name__)


def _signed_url(document):
    return document_service.signed_url(
        current_app.supabase, document, current_app.config["SIGNED_URL_EXPIRES_IN"]
    )


@bp.route("/applications/<application_id>/documents", methods=["GET"])
@api_login_required
def list_documents(application_id):
    application, error = load_visible_application(application_id, admin=True)
    if error:
        return error

    include_urls = request.args.get("urls", "").lower() in ("1", "true", "yes")
    documents = current_app.supabase.list_documents(application_id)

    result = []
    for document in documents:
        url = None
        if include_urls:
            try:
                url = _signed_url(document)
            except Exception:
                url = None
        result.append(serialize_document(document, url))
    return success(documents=result)


@bp.route("/applications/<application_id>/documents", methods=["POST"])
@api_student_required
def upload_document(application_id):
    # load_visible_application(admin=False) ensures the caller owns the record.
    application, error = load_visible_application(application_id)
    if error:
        return error

    doc_type = request.form.get("doc_type") or (request.get_json(silent=True) or {}).get(
        "doc_type"
    )
    file = request.files.get("file") or request.files.get("document")

    document = document_service.upload_document(
        current_app.supabase, current_user, application, doc_type, file, current_app.config
    )
    return created(document=serialize_document(document))


@bp.route("/documents/<document_id>", methods=["GET"])
@api_login_required
def get_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document:
        return failure("Document not found.", 404)

    is_owner = str(document.get("user_id")) == str(current_user.id)
    if getattr(current_user, "role", None) != "admin" and not is_owner:
        return failure("Document not found.", 404)

    url = _signed_url(document)
    return success(
        document=serialize_document(document, url),
        url=url,
        expires_in=current_app.config["SIGNED_URL_EXPIRES_IN"],
    )


@bp.route("/documents/<document_id>", methods=["DELETE"])
@api_student_required
def delete_document(document_id):
    document = current_app.supabase.get_document(document_id)
    if not document or str(document.get("user_id")) != str(current_user.id):
        return failure("Document not found.", 404)

    document_service.delete_document(current_app.supabase, current_user, document)
    return success(message="Document removed.")
