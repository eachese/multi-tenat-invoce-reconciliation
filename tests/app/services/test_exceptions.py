"""Unit tests for service-layer exception hierarchy."""
from __future__ import annotations

from app.services.exceptions import ConflictError, NotFoundError, ServiceError, ValidationError


def test_service_error_inherits_from_exception() -> None:
    assert issubclass(ServiceError, Exception)


def test_not_found_error_inherits_service_error() -> None:
    assert issubclass(NotFoundError, ServiceError)


def test_conflict_error_inherits_service_error() -> None:
    assert issubclass(ConflictError, ServiceError)


def test_validation_error_inherits_service_error() -> None:
    assert issubclass(ValidationError, ServiceError)


def test_exception_instantiation_preserves_message() -> None:
    message = "entity not found"
    error = NotFoundError(message)
    assert str(error) == message
