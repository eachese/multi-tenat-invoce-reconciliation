"""Tests for API error mapping helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from app.api.errors import map_service_error
from app.services.exceptions import ConflictError, NotFoundError, ServiceError, ValidationError


@pytest.mark.parametrize(
    ("exc_cls", "message", "expected_status"),
    [
        (NotFoundError, "resource missing", status.HTTP_404_NOT_FOUND),
        (ConflictError, "already exists", status.HTTP_409_CONFLICT),
        (ValidationError, "invalid payload", status.HTTP_400_BAD_REQUEST),
    ],
)
def test_map_service_error_known_types(exc_cls, message, expected_status) -> None:
    error = exc_cls(message)

    http_exc = map_service_error(error)

    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == expected_status
    assert http_exc.detail == message


def test_map_service_error_fallback_to_internal_error() -> None:
    error = ServiceError("do not leak this message")

    http_exc = map_service_error(error)

    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert http_exc.detail == "Internal service error"
