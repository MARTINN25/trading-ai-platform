"""User evaluation and manual outcome of a saved insight (MODULE_BOUNDARIES.md §12 "evaluations").

**Not to be confused with `trading_ai.ai.evaluation`** (the developer AI
quality regression harness that scores the LLM's *output structure*
against a fixed dataset — no user, no database row, no HTTP surface).
This module is the opposite direction: a human, real end user, judging
one specific *already-saved* `SavedInsight` (`trading_ai.insights`) and
optionally recording what actually happened afterward (FR-035, FR-036,
FR-038; UJ-014, UJ-015).

Depends on `trading_ai.insights` only for existence-checking a
referenced insight id (MODULE_BOUNDARIES.md §12: "insights — только для
ссылки на инсайт, не для его изменения") — this module never reads or
writes insight *content*, and `insights` itself has no reverse
dependency on this module (MODULE_BOUNDARIES.md §11: insights'
allowed deps are `provenance, shared_kernel` only).

One `InsightEvaluation` record per insight (Product Owner scope
decision, task scope §7: "для MVP предпочтительно одна evaluation
record на insight" — UJ-014/UJ-015 describe a single evolving record,
not a history of many evaluations), holding both the user's rating
half and the manual-outcome half — UJ-015's "результат сохраняется
рядом с исходным выводом" plus FR-038's "хранятся неразрывно" is read
as "one evaluation row stably linked to one insight via `insight_id`
FK", not literally the same row as `insights` (that would violate
insight immutability and MODULE_BOUNDARIES.md's explicit module split).
Either half may be set independently and later updated — UJ-014
explicitly allows changing a previously given rating; the same upsert
semantics is extended to the outcome half for consistency, since no
document forbids correcting a manual outcome entry either.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class InsightRating(str, Enum):
    """Categorical, not numeric (Product Owner decision — 3-way,
    documents left the exact format open; a numeric scale was rejected
    as implying a false precision no single glance at an insight can
    support, same reasoning `ai.types.ConfidenceLevel` used for
    confidence in the previous slice)."""

    USEFUL = "useful"
    PARTIALLY_USEFUL = "partially_useful"
    NOT_USEFUL = "not_useful"


class EvaluationError(Exception):
    """Base class for evaluation/outcome domain and application errors."""


class EvaluationNotFoundError(EvaluationError):
    """Raised when a caller asks for the evaluation of an insight that
    exists but has never been rated or had an outcome recorded — distinct
    from `InsightNotFoundError` (the insight itself doesn't exist)."""

    def __init__(self, insight_id: int) -> None:
        super().__init__(f"no evaluation recorded for insight {insight_id}")
        self.insight_id = insight_id


class InvalidOutcomeError(EvaluationError):
    """Raised when a manual outcome note fails minimal validation
    (blank/whitespace-only) — FR-036 requires the user to actually
    record something, not an empty confirmation click."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class InsightEvaluation:
    """One immutable snapshot of the evaluation/outcome row for an
    insight. The underlying row is mutable (upsert semantics above);
    each read returns a fresh, frozen snapshot — the same "immutable
    value object over a mutable row" split already used elsewhere in
    this codebase is not applicable here since this row *does* change,
    but the returned Python object is still never mutated in place."""

    id: int
    insight_id: int
    rating: InsightRating | None
    rated_at: datetime | None
    outcome_note: str | None
    outcome_recorded_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
