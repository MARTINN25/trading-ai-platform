"""AI-analysis domain types — provider-neutral (ADR-0007 §20-21 `llm_gateway` boundary).

`ai/gateway.py` plays the `llm_gateway` architectural role from
ADR-0007/`MODULE_BOUNDARIES.md` for this vertical slice, the same way
`market_data/gateway.py` already plays the "sources" provider-adapter
role without a literal `sources` package existing yet. The full
aspirational module set (`analysis`/`insights`/`data_quality`/
`provenance`/...) from `MODULE_BOUNDARIES.md` is deferred until a real
need for that additional layering appears — this task's own scope is
explicit about not adding layers "just for structure."

`InstrumentAnalysisInput` is the *entire* bounded snapshot the model
ever sees — assembled by `use_cases.py` from already-fetched,
already-validated application data (existing `market_data` use cases).
It never carries API keys, HTTP headers, database URLs, raw provider
payloads, stack traces, or a free-form user prompt (task scope §5-6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# Fixed, never model-generated — guarantees the exact required wording
# regardless of what the model produces (ADR-0007 §53: a doubtful
# result must be reflected explicitly; human-in-the-loop is not
# delegated to the model's own phrasing of this specific disclaimer).
DISCLAIMER_TEXT = (
    "AI-анализ носит информационный характер и не является инвестиционной рекомендацией."
)


@dataclass(frozen=True, slots=True)
class PriceContextFact:
    """Current-quote facts handed to the model as DATA, not instructions.

    `quote_available=False` is never actually constructed in this
    vertical slice — an unavailable quote makes `use_cases.py` raise
    `AIInsufficientDataError` before any input is built at all. The
    flag still exists so `prompts.py`'s renderer stays honest even if
    a future caller relaxes that rule.
    """

    ticker: str
    price: Decimal | None
    change: Decimal | None
    change_percent: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    previous_close: Decimal | None
    volume: int | None
    as_of: datetime | None
    quote_available: bool


@dataclass(frozen=True, slots=True)
class HistorySummaryFact:
    """Derived facts about a price-history window — never raw per-point
    data (keeps prompt size bounded, task scope §7)."""

    period: str
    first_close: Decimal | None
    last_close: Decimal | None
    min_close: Decimal | None
    max_close: Decimal | None
    points_count: int
    history_available: bool


@dataclass(frozen=True, slots=True)
class NewsHeadlineFact:
    """One length-capped news headline/summary.

    Untrusted external content (ADR-0007 §44) — always rendered by
    `prompts.py` as clearly labeled DATA, never concatenated in a way
    that could be read as an instruction.
    """

    headline: str
    summary: str | None
    source: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class InstrumentAnalysisInput:
    """The only thing `ai/gateway.py` ever sees for one analysis call."""

    ticker: str
    price: PriceContextFact
    history: HistorySummaryFact
    news: tuple[NewsHeadlineFact, ...]
    news_available: bool


@dataclass(frozen=True, slots=True)
class InstrumentAnalysis:
    """Provider-neutral, locally-validated structured result (ADR-0007 §28-29).

    `disclaimer` is always `DISCLAIMER_TEXT`, never model-generated.
    """

    ticker: str
    generated_at: datetime
    summary: str
    price_context: str
    news_context: str
    risks: tuple[str, ...]
    disclaimer: str
    provider: str
    model: str


class AIAnalysisError(Exception):
    """Base class for AI-analysis gateway errors.

    A subset of ADR-0007 §39's full taxonomy relevant to this narrow
    vertical slice (no tool calling, no batch, no streaming here — see
    the module docstring on deliberately not adding unused layers).
    Never an `HTTPException` — the API layer maps these to HTTP
    (ADR-0002 §17), the same way `market_data`'s errors are mapped.
    """


class AITimeoutError(AIAnalysisError):
    """The bounded provider request timeout was exceeded."""


class AIRateLimitedError(AIAnalysisError):
    """Provider signaled rate limiting (e.g. HTTP 429)."""


class AIProviderUnavailableError(AIAnalysisError):
    """Provider unreachable, rejected the request (auth/permission), or returned a server error."""


class AIInvalidOutputError(AIAnalysisError):
    """Provider responded, but the content wasn't valid JSON, failed local
    schema validation, or contained forbidden recommendation language
    (task scope §4: no BUY/SELL/HOLD/target-price wording)."""


class AIInsufficientDataError(AIAnalysisError):
    """Not enough upstream instrument data (no quote) to attempt an
    analysis at all — the LLM is never called in this case."""
