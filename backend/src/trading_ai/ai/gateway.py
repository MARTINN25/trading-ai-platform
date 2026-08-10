"""xAI (Grok) LLM gateway for instrument analysis.

The only place in the codebase that imports `httpx` for xAI calls or
knows xAI's URL/request/response shape — plays the `llm_gateway`
architectural boundary role defined by ADR-0007 §20-22 for this
vertical slice (application/use-case code depends only on this
module's Protocol via `use_cases.py`, never on xAI specifics).

xAI is the ADR-0007-approved initial LLM provider (§64, Product Owner
decision) — not chosen by this task. The model (`grok-4.5`, current
documented flagship text/chat model, GA — not a `-latest` rolling
alias) and integration path (xAI's officially-documented
OpenAI-compatible `/v1/chat/completions` endpoint via raw `httpx`, no
`xai-sdk`/`openai` package dependency) are this vertical slice's
implementation decisions (ADR-0007 §23, §59 steps 18-19), consistent
with this codebase's established zero-SDK-dependency gateway pattern
(`market_data/gateway.py`, `market_data/news_gateway.py`) and
explicitly sanctioned by ADR-0007 §22 ("OpenAI-совместимый режим xAI
... остаётся внутри adapter-слоя").
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trading_ai.ai.prompts import SYSTEM_INSTRUCTIONS, build_user_content
from trading_ai.ai.types import (
    DISCLAIMER_TEXT,
    AIAnalysisError,
    AIInvalidOutputError,
    AIProviderUnavailableError,
    AIRateLimitedError,
    AITimeoutError,
    InstrumentAnalysis,
    InstrumentAnalysisInput,
)

logger = logging.getLogger(__name__)

SOURCE = "xai"
_BASE_URL = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-4.5"

# Generation is slower than a quote/news lookup — bounded, single
# attempt, no retry (task scope §11, ADR-0007 §34: retry only for
# transient errors, and even then never automatically here — a
# "Повторить"/"Обновить AI-анализ" user click is the retry mechanism).
_REQUEST_TIMEOUT_SECONDS = 30.0

_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "name": "instrument_analysis",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "price_context": {"type": "string"},
            "news_context": {"type": "string"},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "price_context", "news_context", "risks"],
        "additionalProperties": False,
    },
    "strict": True,
}

# Best-effort, defense-in-depth check on top of the prompt instructions
# (task scope §4) — not a substitute for prompt design, just an honest
# extra guard: a response containing these is never trusted as valid
# output, regardless of what the model was told.
_FORBIDDEN_PHRASES = (
    "strong buy",
    "strong sell",
    "buy rating",
    "sell rating",
    "hold rating",
    "target price",
    "price target",
    "покупай",
    "продавай",
    "цель по цене",
    "целевая цена",
    "рекомендую купить",
    "рекомендую продать",
)
_FORBIDDEN_PATTERNS = [
    re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE) for phrase in _FORBIDDEN_PHRASES
]


def contains_forbidden_language(text: str) -> bool:
    """Public (not `_`-prefixed): also reused by `ai/evaluation/evaluators.py`
    so production and evaluation share one phrase list instead of two
    that could silently drift apart."""
    return any(pattern.search(text) for pattern in _FORBIDDEN_PATTERNS)


class ModelOutputSchema(BaseModel):
    """Local source of truth (ADR-0007 §28-29) — validated independently
    of whatever the provider's own "strict" structured-output mode claims
    to guarantee.

    Public (not `_`-prefixed): also reused by `ai/evaluation/evaluators.py`
    to validate raw model-shaped JSON offline, without duplicating this
    schema."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    price_context: str = Field(min_length=1, max_length=1000)
    news_context: str = Field(min_length=1, max_length=1000)
    risks: list[str] = Field(min_length=1, max_length=6)


class XAIGateway:
    """Concrete gateway for xAI. One provider, one class — no generic framework."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        base_url: str = _BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        # Injectable only for tests (`httpx.MockTransport`) — `None`
        # means httpx's real network transport, unchanged in production.
        self._transport = transport

    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis:
        started = time.monotonic()
        try:
            response = await self._fetch_raw(analysis_input)
            analysis, usage = self._parse_response(analysis_input.ticker, response)
        except AIAnalysisError as exc:
            self._log(analysis_input.ticker, started, status=type(exc).__name__)
            raise
        self._log(
            analysis_input.ticker,
            started,
            status="ok",
            input_tokens=usage[0],
            output_tokens=usage[1],
        )
        return analysis

    async def _fetch_raw(self, analysis_input: InstrumentAnalysisInput) -> httpx.Response:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": build_user_content(analysis_input)},
            ],
            "response_format": {"type": "json_schema", "json_schema": _RESPONSE_JSON_SCHEMA},
        }
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    # Header, not a query param — same reasoning as the
                    # market-data gateways: keeps the key out of any URL
                    # that might be logged by a layer other than our own.
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise AITimeoutError("timeout generating instrument analysis") from exc
        except httpx.HTTPError as exc:
            raise AIProviderUnavailableError(
                "network error generating instrument analysis"
            ) from exc
        return response

    def _parse_response(
        self, ticker: str, response: httpx.Response
    ) -> tuple[InstrumentAnalysis, tuple[int | None, int | None]]:
        if response.status_code == 429:
            raise AIRateLimitedError("provider rate limit exceeded")
        if response.status_code in (401, 403):
            # Auth/permission/billing problem — never surfaced with
            # provider wording; treated as provider-side unavailability.
            raise AIProviderUnavailableError("provider rejected the request")
        if response.status_code >= 500:
            raise AIProviderUnavailableError(f"provider returned {response.status_code}")
        if not response.is_success:
            raise AIProviderUnavailableError(f"provider returned {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AIInvalidOutputError("provider response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise AIInvalidOutputError("provider response was not a JSON object")

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIInvalidOutputError("provider response missing expected content") from exc

        if not isinstance(content, str):
            raise AIInvalidOutputError("provider response content was not a string")

        try:
            structured = json.loads(content)
        except ValueError as exc:
            raise AIInvalidOutputError("model output was not valid JSON") from exc

        try:
            validated = ModelOutputSchema.model_validate(structured)
        except ValidationError as exc:
            raise AIInvalidOutputError("model output failed schema validation") from exc

        combined_text = " ".join(
            [validated.summary, validated.price_context, validated.news_context, *validated.risks]
        )
        if contains_forbidden_language(combined_text):
            raise AIInvalidOutputError("model output contained forbidden recommendation language")

        analysis = InstrumentAnalysis(
            ticker=ticker,
            generated_at=datetime.now(timezone.utc),
            summary=validated.summary,
            price_context=validated.price_context,
            news_context=validated.news_context,
            risks=tuple(validated.risks),
            disclaimer=DISCLAIMER_TEXT,
            provider=SOURCE,
            model=self._model,
        )

        usage_obj = payload.get("usage")
        input_tokens = (
            usage_obj.get("prompt_tokens")
            if isinstance(usage_obj, dict) and isinstance(usage_obj.get("prompt_tokens"), int)
            else None
        )
        output_tokens = (
            usage_obj.get("completion_tokens")
            if isinstance(usage_obj, dict) and isinstance(usage_obj.get("completion_tokens"), int)
            else None
        )
        return analysis, (input_tokens, output_tokens)

    def _log(
        self,
        ticker: str,
        started: float,
        *,
        status: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """Minimal observability per call (ADR-0009 §22, ADR-0007 §48).

        Never includes the API key, the Authorization header, the full
        prompt, the full model response, or news bodies — only the
        safe, fixed fields below plus optional numeric token counts.
        """
        latency_ms = (time.monotonic() - started) * 1000
        if input_tokens is not None and output_tokens is not None:
            logger.info(
                "ai_analysis operation=generate_instrument_analysis ticker=%s provider=%s "
                "model=%s status=%s latency_ms=%.1f input_tokens=%d output_tokens=%d",
                ticker,
                SOURCE,
                self._model,
                status,
                latency_ms,
                input_tokens,
                output_tokens,
            )
        else:
            logger.info(
                "ai_analysis operation=generate_instrument_analysis ticker=%s provider=%s "
                "model=%s status=%s latency_ms=%.1f",
                ticker,
                SOURCE,
                self._model,
                status,
                latency_ms,
            )
