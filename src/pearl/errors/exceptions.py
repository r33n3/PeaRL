"""Custom exception classes for PeaRL API."""


class PeaRLError(Exception):
    """Base exception for PeaRL."""

    def __init__(self, code: str, message: str, details=None, status_code: int = 500):
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code
        super().__init__(message)


class ValidationError(PeaRLError):
    """Schema or request validation failure."""

    def __init__(self, message: str, details=None):
        super().__init__("VALIDATION_ERROR", message, details, status_code=400)


class NotFoundError(PeaRLError):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            "NOT_FOUND",
            f"{resource} '{resource_id}' not found",
            status_code=404,
        )


class AuthenticationError(PeaRLError):
    """Authentication required or token invalid."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__("AUTHENTICATION_ERROR", message, status_code=401)


class AuthorizationError(PeaRLError):
    """Insufficient permissions."""

    def __init__(self, message: str = "Insufficient scope"):
        super().__init__("AUTHORIZATION_ERROR", message, status_code=403)


class ConflictError(PeaRLError):
    """Resource state conflict."""

    def __init__(self, message: str):
        super().__init__("CONFLICT", message, status_code=409)
