"""Service-layer exception hierarchy."""
from __future__ import annotations


class ServiceError(Exception):
    """Base service error."""


class NotFoundError(ServiceError):
    """Raised when an entity is not found."""


class ConflictError(ServiceError):
    """Raised when a domain conflict occurs."""


class ValidationError(ServiceError):
    """Raised when business validation fails."""
