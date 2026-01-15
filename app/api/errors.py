"""HTTP exception helpers for service-layer errors."""
from __future__ import annotations

from fastapi import HTTPException, status

from app.services.exceptions import ConflictError, NotFoundError, ServiceError, ValidationError


def map_service_error(exc: ServiceError) -> HTTPException:
    """Translate service-layer errors into HTTP exceptions."""

    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal service error")
