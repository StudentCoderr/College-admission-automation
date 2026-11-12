"""Domain-level exceptions shared by the service layer and the JSON API.

Services raise these instead of calling ``abort`` so they stay independent of
Flask. The API blueprint registers error handlers that translate them into
consistent JSON responses, and the HTML routes catch them where useful.
"""


class ServiceError(Exception):
    """A recoverable business-rule error with an HTTP status code."""

    status_code = 400

    def __init__(self, message, status_code=None, errors=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.errors = errors  # optional {field: message} mapping


class ValidationError(ServiceError):
    status_code = 422


class UnauthorizedError(ServiceError):
    status_code = 401


class ForbiddenError(ServiceError):
    status_code = 403


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409
