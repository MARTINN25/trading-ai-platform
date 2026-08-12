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
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from trading_ai.ai.horizon import compute_check_after
from trading_ai.ai.news_prompts import NEWS_SYSTEM_INSTRUCTIONS, build_news_user_content
from trading_ai.ai.prompts import PROMPT_VERSION, SYSTEM_INSTRUCTIONS, build_user_content
from trading_ai.ai.types import (
    DISCLAIMER_TEXT,
    INSIGHT_SCHEMA_VERSION,
    AIAnalysisError,
    AIInvalidOutputError,
    AINewsEnrichmentError,
    AINewsInvalidOutputError,
    AINewsProviderUnavailableError,
    AINewsRateLimitedError,
    AINewsTimeoutError,
    AIProviderUnavailableError,
    AIRateLimitedError,
    AITimeoutError,
    ConfidenceLevel,
    DirectionalView,
    ForecastState,
    HorizonDataSufficiency,
    InstrumentAnalysis,
    InstrumentAnalysisInput,
    KeyFact,
    NewsCandidateFact,
    NewsEnrichmentResult,
    NewsRelationship,
    NewsRelevance,
)

logger = logging.getLogger(__name__)

SOURCE = "xai"
_BASE_URL = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-4.5"

# Generation is slower than a quote/news lookup — bounded, single
# attempt, no retry (task scope §11, ADR-0007 §34: retry only for
# transient errors, and even then never automatically here — a
# "Повторить"/"Обновить AI-анализ" user click is the retry mechanism).
# Raised from 30s (Instrument AI Analysis) to 60s here (Insight
# Persistence & Structure Completion): FR-018's structured output went
# from 4 required fields to 10, which measurably increases generation
# time — a real 504 was observed live against a v1-era 30s bound during
# this task's own browser verification, not a hypothetical concern.
_REQUEST_TIMEOUT_SECONDS = 60.0

# FR-018's 10 mandatory sections, minus `disclaimer` (never model-
# generated, DISCLAIMER_TEXT is injected after parsing) and minus
# "Актуальность использованных данных" (`data_freshness`/
# `source_data_as_of` — always backend-computed from
# `InstrumentAnalysisInput`, never asked of the model — see
# `ai/types.py`'s `InstrumentAnalysis` docstring for the full 10-section
# mapping, including why "Анализ" isn't its own field).
_KEY_FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fact": {"type": "string"},
        "source": {"type": "string"},
    },
    "required": ["fact", "source"],
    "additionalProperties": False,
}

_DIRECTIONAL_VIEW_ENUM = [
    "strongly_bullish",
    "bullish",
    "neutral",
    "bearish",
    "strongly_bearish",
]
_FORECAST_STATE_ENUM = ["forecast", "no_quality_setup", "insufficient_edge", "insufficient_data"]

_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "name": "instrument_analysis",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "price_context": {"type": "string"},
            "news_context": {"type": "string"},
            "key_facts": {"type": "array", "items": _KEY_FACT_SCHEMA},
            "insight_hypothesis": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "confidence_reason": {"type": "string"},
            "considerations": {"type": "array", "items": {"type": "string"}},
            "risks": {"type": "array", "items": {"type": "string"}},
            "key_drivers": {"type": "array", "items": {"type": "string"}},
            # Phase 2B (Forecast Contract) — see `ai/prompts.py` rules
            # 13-22 and `ai/types.py`'s `InstrumentAnalysis` docstring.
            "forecast_state": {"type": "string", "enum": _FORECAST_STATE_ENUM},
            "directional_view": {"type": ["string", "null"], "enum": [*_DIRECTIONAL_VIEW_ENUM, None]},
            "concise_verdict": {"type": "string"},
            "base_case": {"type": ["string", "null"]},
            "bullish_case": {"type": ["string", "null"]},
            "bearish_case": {"type": ["string", "null"]},
            "catalysts": {"type": "array", "items": {"type": "string"}},
            "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
            "what_to_watch_next": {"type": "array", "items": {"type": "string"}},
            "uncertainty": {"type": "string"},
        },
        "required": [
            "summary",
            "price_context",
            "news_context",
            "key_facts",
            "insight_hypothesis",
            "confidence",
            "confidence_reason",
            "considerations",
            "risks",
            "key_drivers",
            "forecast_state",
            "directional_view",
            "concise_verdict",
            "base_case",
            "bullish_case",
            "bearish_case",
            "catalysts",
            "invalidation_conditions",
            "what_to_watch_next",
            "uncertainty",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}

# One batch call per ticker-news-fetch (task scope §5, §10: LLM only
# for semantic ambiguity, called once per already-deduplicated batch,
# never once per item) — bounded independently of whatever cap the
# caller applies, as a defensive ceiling on prompt size.
_MAX_NEWS_ITEMS_PER_BATCH = 10

# Enrichment is lighter-weight than full instrument analysis, but still
# bounded and single-attempt (same reasoning as
# `_REQUEST_TIMEOUT_SECONDS` above — a "Повторить" user click is the
# retry mechanism, not automatic retry here).
_NEWS_REQUEST_TIMEOUT_SECONDS = 45.0

_NEWS_RESULT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "relationship": {
            "type": "string",
            "enum": ["company", "sector", "market", "macro", "indirect", "noise"],
        },
        "relevance": {"type": "string", "enum": ["high", "medium", "low"]},
        "summary_ru": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "impact_hypothesis": {"type": "string"},
    },
    "required": [
        "id",
        "relationship",
        "relevance",
        "summary_ru",
        "why_it_matters",
        "impact_hypothesis",
    ],
    "additionalProperties": False,
}

_NEWS_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "name": "news_intelligence",
    "schema": {
        "type": "object",
        "properties": {
            "results": {"type": "array", "items": _NEWS_RESULT_ITEM_SCHEMA},
        },
        "required": ["results"],
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
    "buy now",
    "sell now",
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


# Phase 2B (Forecast Contract, task scope §6, §15): a numeric
# probability/odds statement is forbidden in every field, independent
# of the existing recommendation/target-price guard above (task scope
# §9: "категориальная уверенность, численные вероятности не
# вводятся"). Best-effort pattern match, same honest limitation as
# `_FORBIDDEN_PATTERNS` — not a claim of catching every phrasing.
_PROBABILITY_PATTERNS = [
    re.compile(r"\d{1,3}\s?%\s*(chance|probability|likelihood|odds)", re.IGNORECASE),
    re.compile(r"(chance|probability|likelihood|odds)\s+of\s+\d{1,3}\s?%", re.IGNORECASE),
    re.compile(r"\d{1,3}\s?%\s*вероятност\w*", re.IGNORECASE | re.UNICODE),
    re.compile(r"вероятност\w*[^.\n]{0,25}\d{1,3}\s?%", re.IGNORECASE | re.UNICODE),
]


def contains_numeric_probability_language(text: str) -> bool:
    """Public for the same reuse-in-evaluation reason as
    `contains_forbidden_language`."""
    return any(pattern.search(text) for pattern in _PROBABILITY_PATTERNS)


class KeyFactSchema(BaseModel):
    """Local source of truth for one `key_facts` entry — see `ai/types.py`'s
    `KeyFact` docstring for why `source` is a plain, model-copied label
    rather than a full provenance record."""

    model_config = ConfigDict(extra="forbid")

    fact: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=200)


class ModelOutputSchema(BaseModel):
    """Local source of truth (ADR-0007 §28-29) — validated independently
    of whatever the provider's own "strict" structured-output mode claims
    to guarantee.

    Public (not `_`-prefixed): also reused by `ai/evaluation/evaluators.py`
    to validate raw model-shaped JSON offline, without duplicating this
    schema. Covers 8 of FR-018's 10 sections — `disclaimer` and
    `data_freshness`/`source_data_as_of` are never model output (see
    `ai/types.py`'s `InstrumentAnalysis` docstring).

    Phase 2B: the forecast fields below are validated with a
    `model_validator` (not just per-field types) — `forecast_state`
    other than `"forecast"` must carry `directional_view`/`base_case`/
    `bullish_case`/`bearish_case` all `None` (task scope §12, §7: a
    no-quality-setup result never carries directional content), and
    `forecast_state == "forecast"` must carry a non-null
    `directional_view`. This is enforced locally regardless of what the
    provider's own strict-schema claim guarantees."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    price_context: str = Field(min_length=1, max_length=1000)
    news_context: str = Field(min_length=1, max_length=1000)
    key_facts: list[KeyFactSchema] = Field(min_length=1, max_length=10)
    insight_hypothesis: str = Field(min_length=1, max_length=1000)
    confidence: ConfidenceLevel
    confidence_reason: str = Field(min_length=1, max_length=500)
    considerations: list[str] = Field(min_length=1, max_length=6)
    risks: list[str] = Field(min_length=1, max_length=6)
    key_drivers: list[str] = Field(min_length=1, max_length=5)
    forecast_state: ForecastState
    directional_view: DirectionalView | None
    concise_verdict: str = Field(min_length=1, max_length=600)
    base_case: str | None = Field(default=None, max_length=1000)
    bullish_case: str | None = Field(default=None, max_length=1000)
    bearish_case: str | None = Field(default=None, max_length=1000)
    catalysts: list[str] = Field(max_length=6)
    invalidation_conditions: list[str] = Field(max_length=6)
    what_to_watch_next: list[str] = Field(max_length=6)
    uncertainty: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _forecast_content_matches_state(self) -> "ModelOutputSchema":
        if self.forecast_state == ForecastState.FORECAST:
            if self.directional_view is None:
                raise ValueError("directional_view is required when forecast_state is 'forecast'")
        else:
            if self.directional_view is not None:
                raise ValueError("directional_view must be null when forecast_state is not 'forecast'")
            if self.base_case is not None or self.bullish_case is not None or self.bearish_case is not None:
                raise ValueError(
                    "base_case/bullish_case/bearish_case must be null when forecast_state is not 'forecast'"
                )
        return self


class NewsEnrichmentItemSchema(BaseModel):
    """Local source of truth for one `results[]` entry (mirrors
    `ModelOutputSchema`'s role for instrument analysis) — validated
    independently of the provider's own "strict" structured-output
    claim."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    relationship: NewsRelationship
    relevance: NewsRelevance
    summary_ru: str = Field(min_length=1, max_length=600)
    why_it_matters: str = Field(min_length=1, max_length=400)
    impact_hypothesis: str = Field(min_length=1, max_length=400)


class NewsEnrichmentBatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[NewsEnrichmentItemSchema] = Field(max_length=_MAX_NEWS_ITEMS_PER_BATCH)


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

    @property
    def model(self) -> str:
        """Public read accessor — `news_intelligence.use_cases` records
        this in the persisted enrichment row's provenance fields
        without needing its own copy of the configured model name."""
        return self._model

    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis:
        started = time.monotonic()
        try:
            response = await self._fetch_raw(analysis_input)
            analysis, usage = self._parse_response(analysis_input, response)
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
        self, analysis_input: InstrumentAnalysisInput, response: httpx.Response
    ) -> tuple[InstrumentAnalysis, tuple[int | None, int | None]]:
        ticker = analysis_input.ticker
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
            [
                validated.summary,
                validated.price_context,
                validated.news_context,
                validated.insight_hypothesis,
                validated.confidence_reason,
                validated.concise_verdict,
                validated.base_case or "",
                validated.bullish_case or "",
                validated.bearish_case or "",
                validated.uncertainty,
                *validated.considerations,
                *validated.risks,
                *validated.key_drivers,
                *validated.catalysts,
                *validated.invalidation_conditions,
                *validated.what_to_watch_next,
                *(fact.fact for fact in validated.key_facts),
            ]
        )
        if contains_forbidden_language(combined_text):
            raise AIInvalidOutputError("model output contained forbidden recommendation language")
        if contains_numeric_probability_language(combined_text):
            raise AIInvalidOutputError("model output contained a numeric probability statement")

        # Deterministic override (task scope §12): the sufficiency gate
        # computed *before* this call (`ai/horizon.py`,
        # `analysis_input.horizon_sufficiency`) is the final authority
        # on the INSUFFICIENT direction — a model that ignored rule 13
        # and returned a directional forecast anyway is corrected here,
        # never trusted over the deterministic signal.
        forecast_state = validated.forecast_state
        directional_view = validated.directional_view
        base_case = validated.base_case
        bullish_case = validated.bullish_case
        bearish_case = validated.bearish_case
        catalysts = tuple(validated.catalysts)
        invalidation_conditions = tuple(validated.invalidation_conditions)
        if (
            analysis_input.horizon_sufficiency is HorizonDataSufficiency.INSUFFICIENT
            and forecast_state is not ForecastState.INSUFFICIENT_DATA
        ):
            logger.info(
                "ai_analysis operation=generate_instrument_analysis ticker=%s "
                "status=sufficiency_override model_state=%s",
                ticker,
                forecast_state.value,
            )
            forecast_state = ForecastState.INSUFFICIENT_DATA
            directional_view = None
            base_case = None
            bullish_case = None
            bearish_case = None
            catalysts = ()
            invalidation_conditions = ()

        data_freshness, source_data_as_of = compute_data_freshness(analysis_input)
        generated_at = datetime.now(timezone.utc)

        analysis = InstrumentAnalysis(
            ticker=ticker,
            generated_at=generated_at,
            summary=validated.summary,
            price_context=validated.price_context,
            news_context=validated.news_context,
            key_facts=tuple(
                KeyFact(fact=item.fact, source=item.source) for item in validated.key_facts
            ),
            insight_hypothesis=validated.insight_hypothesis,
            confidence=validated.confidence,
            confidence_reason=validated.confidence_reason,
            considerations=tuple(validated.considerations),
            risks=tuple(validated.risks),
            key_drivers=tuple(validated.key_drivers),
            data_freshness=data_freshness,
            source_data_as_of=source_data_as_of,
            disclaimer=DISCLAIMER_TEXT,
            provider=SOURCE,
            model=self._model,
            prompt_version=PROMPT_VERSION,
            schema_version=INSIGHT_SCHEMA_VERSION,
            horizon=analysis_input.horizon,
            forecast_state=forecast_state,
            directional_view=directional_view,
            concise_verdict=validated.concise_verdict,
            base_case=base_case,
            bullish_case=bullish_case,
            bearish_case=bearish_case,
            catalysts=catalysts,
            invalidation_conditions=invalidation_conditions,
            what_to_watch_next=tuple(validated.what_to_watch_next),
            check_after=compute_check_after(generated_at, analysis_input.horizon),
            uncertainty=validated.uncertainty,
            context_categories_used=_context_categories_used(analysis_input),
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


    async def generate_news_intelligence(
        self, ticker: str, candidates: tuple[NewsCandidateFact, ...]
    ) -> list[NewsEnrichmentResult]:
        """One batch call for up to `_MAX_NEWS_ITEMS_PER_BATCH` already-
        deduplicated candidates. Never raises for a single bad item —
        only for whole-call failures (network/timeout/rate-limit/
        provider-down/malformed-response). A result missing from the
        model's response, or one that fails local per-item validation,
        is silently dropped from the returned list — the caller
        (`news_intelligence.use_cases`) treats a missing id as "not
        enriched" for that one item, never as a batch failure (task
        scope §11, §16)."""
        if not candidates:
            return []
        bounded = candidates[:_MAX_NEWS_ITEMS_PER_BATCH]

        started = time.monotonic()
        try:
            response = await self._fetch_news_raw(ticker, bounded)
            results, usage = self._parse_news_response(bounded, response)
        except AINewsEnrichmentError as exc:
            self._log_news(ticker, started, status=type(exc).__name__, items_count=len(bounded))
            raise
        self._log_news(
            ticker,
            started,
            status="ok",
            items_count=len(bounded),
            enriched_count=len(results),
            input_tokens=usage[0],
            output_tokens=usage[1],
        )
        return results

    async def _fetch_news_raw(
        self, ticker: str, candidates: tuple[NewsCandidateFact, ...]
    ) -> httpx.Response:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": NEWS_SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": build_news_user_content(ticker, candidates)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": _NEWS_RESPONSE_JSON_SCHEMA,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=_NEWS_REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as exc:
            raise AINewsTimeoutError("timeout generating news intelligence") from exc
        except httpx.HTTPError as exc:
            raise AINewsProviderUnavailableError(
                "network error generating news intelligence"
            ) from exc
        return response

    def _parse_news_response(
        self, candidates: tuple[NewsCandidateFact, ...], response: httpx.Response
    ) -> tuple[list[NewsEnrichmentResult], tuple[int | None, int | None]]:
        if response.status_code == 429:
            raise AINewsRateLimitedError("provider rate limit exceeded")
        if response.status_code in (401, 403):
            raise AINewsProviderUnavailableError("provider rejected the request")
        if response.status_code >= 500:
            raise AINewsProviderUnavailableError(f"provider returned {response.status_code}")
        if not response.is_success:
            raise AINewsProviderUnavailableError(f"provider returned {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AINewsInvalidOutputError("provider response was not valid JSON") from exc

        if not isinstance(payload, dict):
            raise AINewsInvalidOutputError("provider response was not a JSON object")

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AINewsInvalidOutputError("provider response missing expected content") from exc

        if not isinstance(content, str):
            raise AINewsInvalidOutputError("provider response content was not a string")

        try:
            structured = json.loads(content)
        except ValueError as exc:
            raise AINewsInvalidOutputError("model output was not valid JSON") from exc

        try:
            validated = NewsEnrichmentBatchSchema.model_validate(structured)
        except ValidationError as exc:
            raise AINewsInvalidOutputError("model output failed schema validation") from exc

        known_ids = {candidate.id for candidate in candidates}
        results: list[NewsEnrichmentResult] = []
        seen_ids: set[str] = set()
        for item in validated.results:
            # Defensive per-item drop, not a whole-batch failure (task
            # scope §11): an id the model invented, a duplicate id, or
            # forbidden-recommendation language in one item's text must
            # never take down the rest of an otherwise-good batch.
            if item.id not in known_ids or item.id in seen_ids:
                continue
            combined_text = " ".join([item.summary_ru, item.why_it_matters, item.impact_hypothesis])
            if contains_forbidden_language(combined_text):
                continue
            seen_ids.add(item.id)
            results.append(
                NewsEnrichmentResult(
                    id=item.id,
                    relevance=item.relevance,
                    relationship=item.relationship,
                    summary_ru=item.summary_ru,
                    why_it_matters=item.why_it_matters,
                    impact_hypothesis=item.impact_hypothesis,
                )
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
        return results, (input_tokens, output_tokens)

    def _log_news(
        self,
        ticker: str,
        started: float,
        *,
        status: str,
        items_count: int,
        enriched_count: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """Minimal observability per call (ADR-0009 §22, ADR-0007 §48) —
        never the API key, prompt, model response, or article content."""
        latency_ms = (time.monotonic() - started) * 1000
        logger.info(
            "news_intelligence operation=generate_news_intelligence ticker=%s provider=%s "
            "model=%s status=%s latency_ms=%.1f items_count=%d enriched_count=%s "
            "input_tokens=%s output_tokens=%s",
            ticker,
            SOURCE,
            self._model,
            status,
            latency_ms,
            items_count,
            enriched_count if enriched_count is not None else "n/a",
            input_tokens if input_tokens is not None else "n/a",
            output_tokens if output_tokens is not None else "n/a",
        )


def compute_data_freshness(analysis_input: InstrumentAnalysisInput) -> tuple[str, datetime | None]:
    """FR-018 §9 ("Актуальность использованных данных") — a fact about
    the request, already known with certainty, so it is computed here
    rather than asked of the model (see `InstrumentAnalysis`'s
    docstring). Returns the Russian prose plus the underlying quote
    timestamp, so the persisted row can keep both the human-readable
    statement and a structured, queryable value (task scope §6:
    "source-data timestamps").

    Public (not `_`-prefixed): also reused by `ai/evaluation/dataset.py`
    so hand-authored reference responses compute this the same way a
    real generation would.
    """
    price = analysis_input.price
    parts: list[str] = []
    if price.quote_available and price.as_of is not None:
        parts.append(f"котировка актуальна на {price.as_of.isoformat()}")
    else:
        parts.append("котировка недоступна")

    if analysis_input.history.history_available:
        parts.append(f"история цены доступна за период {analysis_input.history.period}")
    else:
        parts.append("история цены недоступна")

    if analysis_input.news_available:
        count = len(analysis_input.news)
        parts.append(f"новости доступны ({count} заголовков)" if count else "новости доступны, но не найдены")
    else:
        parts.append("новости недоступны")

    freshness_text = "; ".join(parts) + "."
    source_data_as_of = price.as_of if price.quote_available else None
    return freshness_text, source_data_as_of


def _context_categories_used(analysis_input: InstrumentAnalysisInput) -> tuple[str, ...]:
    """Phase 2B provenance (`FORECAST_CONTRACT.md` §10: "ссылка на
    конкретные категории контекста, реально вошедшие в анализ") —
    deterministic, from what was actually available on this call, never
    asked of the model. Only names categories from
    `TARGET_INTELLIGENCE_CONTEXT.md` §2 that this codebase actually
    implements today (`identity`/`price`/`history`/`news`) — task scope
    §10 forbids fabricating macro/indices/rates/sector categories that
    don't exist yet."""
    categories = ["identity"]
    if analysis_input.price.quote_available:
        categories.append("price")
    if analysis_input.history.history_available:
        categories.append("history")
    if analysis_input.news_available and analysis_input.news:
        categories.append("news")
    return tuple(categories)
