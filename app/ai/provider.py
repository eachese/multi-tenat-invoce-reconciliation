"""AI client abstractions and factories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(slots=True)
class ExplanationContext:
    """Data passed to AI client for explanation generation."""

    invoice_amount: float
    invoice_currency: str
    invoice_date: str | None
    invoice_description: str | None
    vendor_name: str | None
    transaction_amount: float
    transaction_currency: str
    transaction_date: str
    transaction_description: str | None
    score: float
    reasoning: str


class AIClient(Protocol):
    """Protocol for AI explanation clients."""

    def explain(self, context: ExplanationContext) -> tuple[str, str | None]:
        ...


class OpenAIClient:
    """Minimal OpenAI completions client for explanation generation."""

    def __init__(self, model: str, api_key: str, timeout: float = 8.0) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def explain(self, context: ExplanationContext) -> tuple[str, str | None]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You explain invoice and bank transaction matches succinctly.",
                },
                {
                    "role": "user",
                    "content": (
                        "Invoice amount {amount} {currency}, date {invoice_date}, vendor {vendor}. "
                        "Transaction amount {txn_amount} {txn_currency}, date {txn_date}. "
                        "Transaction memo {txn_description}. "
                        "Heuristic reasoning: {reasoning}. Overall score {score:.2f}."
                    ).format(
                        amount=context.invoice_amount,
                        currency=context.invoice_currency,
                        invoice_date=context.invoice_date or "unknown",
                        vendor=context.vendor_name or "unknown vendor",
                        txn_amount=context.transaction_amount,
                        txn_currency=context.transaction_currency,
                        txn_date=context.transaction_date,
                        txn_description=context.transaction_description or "n/a",
                        reasoning=context.reasoning,
                        score=context.score,
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 200,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        if context.score >= 0.8:
            confidence = "high"
        elif context.score >= 0.55:
            confidence = "medium"
        else:
            confidence = "low"
        return content, confidence


class DeterministicFallbackClient:
    """Fallback explanation client using heuristic-driven templates."""

    def explain(self, context: ExplanationContext) -> tuple[str, str | None]:
        if context.score >= 0.8:
            band = "high"
            template = (
                "The invoice and transaction align strongly: exact/tight amount match, "
                "date proximity, and descriptive similarity. Reasoning: {reasoning}."
            )
        elif context.score >= 0.55:
            band = "medium"
            template = (
                "The match appears plausible with reasonable amount alignment and some context overlap. "
                "Reasoning: {reasoning}."
            )
        else:
            band = "low"
            template = (
                "The evidence is weak; consider manual review before confirming. Reasoning: {reasoning}."
            )
        explanation = template.format(reasoning=context.reasoning)
        return explanation, band


def resolve_ai_client(model: str, api_key: str | None) -> AIClient | None:
    """Return an AI client instance when credentials are available."""

    if not api_key:
        return None
    return OpenAIClient(model=model, api_key=api_key)


def fallback_client() -> DeterministicFallbackClient:
    """Return deterministic fallback client instance."""

    return DeterministicFallbackClient()
