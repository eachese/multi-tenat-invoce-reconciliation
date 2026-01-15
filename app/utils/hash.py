"""Hashing utilities for deterministic idempotency."""
from __future__ import annotations

import json
import hashlib
from typing import Any


def stable_hash(data: Any) -> str:
    """Return a SHA-256 hash for the provided data structure."""

    serialized = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
