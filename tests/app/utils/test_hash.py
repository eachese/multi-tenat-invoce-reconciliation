"""Tests for app.utils.hash utilities."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.utils.hash import stable_hash


def is_hexadecimal_sha256(value: str) -> bool:
    """Return True if the string is a 64-character lowercase hex digest."""
    try:
        int(value, 16)
    except ValueError:
        return False
    return len(value) == 64 and value == value.lower()


@pytest.mark.parametrize(
    "data",
    [
        {"foo": "bar"},
        [1, 2, 3],
        "plain-text",
        42,
    ],
)
def test_stable_hash_returns_sha256_hex(data: object) -> None:
    result = stable_hash(data)
    assert is_hexadecimal_sha256(result)


def test_stable_hash_is_deterministic_for_same_input() -> None:
    data = {"value": [1, 2, 3], "active": True}
    first = stable_hash(data)
    second = stable_hash(data)
    assert first == second


def test_stable_hash_is_key_order_insensitive_for_dicts() -> None:
    data_one = {"a": 1, "b": 2, "c": 3}
    data_two = {"c": 3, "b": 2, "a": 1}
    assert stable_hash(data_one) == stable_hash(data_two)


def test_stable_hash_handles_non_json_serializable_values() -> None:
    data = {"generated_at": datetime(2024, 1, 1, 12, 30, 45)}
    first = stable_hash(data)
    second = stable_hash(data)
    assert first == second


def test_stable_hash_reflects_value_changes() -> None:
    base_data = {"value": "original"}
    mutated_data = {"value": "mutated"}

    assert stable_hash(base_data) != stable_hash(mutated_data)
