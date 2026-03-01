"""FastAPI exception handlers producing spec-compliant ErrorResponse."""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pearl.errors.exceptions import AuthorizationError, PeaRLError
from pearl.models.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""

    @app.exception_handler(PeaRLError)
    async def pearl_error_handler(request: Request, exc: PeaRLError):
        trace_id = getattr(request.state, "trace_id", "unknown")
        if isinstance(exc, AuthorizationError):
            user = getattr(request.state, "user", {}) or {}
            logger.warning(
                "governance_access_denied",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "trace_id": trace_id,
                    "user_sub": user.get("sub", "anonymous"),
                    "user_roles": user.get("roles", []),
                    "reason": str(exc),
                },
            )
        error_response = ErrorResponse(
            schema_version="1.1",
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                trace_id=trace_id,
                timestamp=datetime.now(timezone.utc),
            ),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(mode="json", exclude_none=True),
        )
