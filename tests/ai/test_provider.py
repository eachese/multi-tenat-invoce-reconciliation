"""Unit tests for app.ai provider utilities."""
from __future__ import annotations

import importlib
from typing import Any, Dict, List

import pytest

from app.ai.provider import (
    DeterministicFallbackClient,
    ExplanationContext,
    OpenAIClient,
    fallback_client,
    resolve_ai_client,
)


def make_context(**overrides: Any) -> ExplanationContext:
    data: Dict[str, Any] = {
        "invoice_amount": 200.0,
        "invoice_currency": "USD",
        "invoice_date": "2023-01-01",
        "invoice_description": "Consulting services",
        "vendor_name": "Acme Corp",
        "transaction_amount": 200.0,
        "transaction_currency": "USD",
        "transaction_date": "2023-01-02",
        "transaction_description": "Consulting payment",
        "score": 0.75,
        "reasoning": "Amounts closely aligned",
    }
    data.update(overrides)
    return ExplanationContext(**data)


def test_ai_module_docstring_present() -> None:
    module = importlib.import_module("app.ai")
    assert module.__doc__ is not None
    assert module.__doc__.strip() == "AI client abstractions for explanation generation."


def test_resolve_ai_client_without_key_returns_none() -> None:
    assert resolve_ai_client("gpt-4o", None) is None


def test_resolve_ai_client_with_key_returns_openai_client() -> None:
    client = resolve_ai_client("gpt-4o-mini", "secret-token")
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-4o-mini"
    assert client.api_key == "secret-token"
    assert client.timeout == pytest.approx(8.0)


def test_fallback_client_returns_new_instances() -> None:
    first = fallback_client()
    second = fallback_client()
    assert isinstance(first, DeterministicFallbackClient)
    assert isinstance(second, DeterministicFallbackClient)
    assert first is not second


@pytest.mark.parametrize(
    ("score", "expected_band", "template"),
    [
        (
            0.85,
            "high",
            (
                "The invoice and transaction align strongly: exact/tight amount match, "
                "date proximity, and descriptive similarity. Reasoning: {reasoning}."
            ),
        ),
        (
            0.70,
            "medium",
            (
                "The match appears plausible with reasonable amount alignment and some context overlap. "
                "Reasoning: {reasoning}."
            ),
        ),
        (
            0.40,
            "low",
            (
                "The evidence is weak; consider manual review before confirming. Reasoning: {reasoning}."
            ),
        ),
    ],
)
def test_deterministic_fallback_client_confidence_bands(
    score: float, expected_band: str, template: str
) -> None:
    context = make_context(score=score, reasoning="Reasoning text")
    client = DeterministicFallbackClient()
    explanation, band = client.explain(context)
    assert band == expected_band
    assert explanation == template.format(reasoning="Reasoning text")


def test_openai_client_explain_posts_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    init_kwargs: List[Dict[str, Any]] = []
    post_calls: List[Dict[str, Any]] = []

    class DummyResponse:
        def raise_for_status(self) -> None:  # pragma: no cover - trivial
            return None

        def json(self) -> Dict[str, Any]:
            return {"choices": [{"message": {"content": "AI explanation"}}]}

    class DummyClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            init_kwargs.append(kwargs)

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str]) -> DummyResponse:
            post_calls.append({"url": url, "json": json, "headers": headers})
            return DummyResponse()

    monkeypatch.setattr("app.ai.provider.httpx.Client", DummyClient)

    client = OpenAIClient(model="gpt-4o-mini", api_key="secret-token", timeout=3.5)
    context = make_context(score=0.9, reasoning="Strong alignment")

    explanation, confidence = client.explain(context)

    assert explanation == "AI explanation"
    assert confidence == "high"
    assert init_kwargs == [{"timeout": 3.5}]

    assert len(post_calls) == 1
    call = post_calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer secret-token"
    assert call["headers"]["Content-Type"] == "application/json"

    payload = call["json"]
    assert payload["model"] == "gpt-4o-mini"
    assert payload["temperature"] == pytest.approx(0.2)
    assert payload["max_tokens"] == 200
    assert payload["messages"][0]["role"] == "system"
    assert "Strong alignment" in payload["messages"][1]["content"]


@pytest.mark.parametrize(
    ("score", "expected_band"),
    [
        (0.85, "high"),
        (0.60, "medium"),
        (0.30, "low"),
    ],
)
def test_openai_client_confidence_levels(
    monkeypatch: pytest.MonkeyPatch, score: float, expected_band: str
) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:  # pragma: no cover - trivial
            return None

        def json(self) -> Dict[str, Any]:
            return {"choices": [{"message": {"content": "Result"}}]}

    class DummyClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def __enter__(self) -> "DummyClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def post(self, url: str, json: Dict[str, Any], headers: Dict[str, str]) -> DummyResponse:
            return DummyResponse()

    monkeypatch.setattr("app.ai.provider.httpx.Client", DummyClient)

    client = OpenAIClient(model="gpt-4o", api_key="token")
    _, confidence = client.explain(make_context(score=score))

    assert confidence == expected_band
