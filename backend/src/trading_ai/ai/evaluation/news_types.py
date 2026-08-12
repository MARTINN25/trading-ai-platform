"""Provider-neutral evaluation types for news intelligence (Phase 2A).

A sibling of `types.py`, not an extension of it: `EvaluationCase` there
is tightly typed to `InstrumentAnalysisInput`/`InstrumentAnalysis` (the
instrument-analysis output contract) — generalizing it to also cover
news enrichment would require parameterizing the whole existing harness
generically, a larger structural change than this slice's scope
justifies (see the Phase 2A final report for why this was deferred
rather than done here). `CheckResult`/`CheckCategory` *are* reused
as-is from `types.py` — those are already generic (a named, categorized
pass/fail), not instrument-analysis-specific.

`NewsEvaluationCase.reference_response` is a hand-authored stand-in for
a compliant model answer, same caveat as `types.py`'s docstring: this
demonstrates the harness/grading logic works end-to-end at zero cost,
it is not a claim about what the live model actually produces. Only
`news_runner.run_news_live` answers that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trading_ai.ai.evaluation.types import CheckResult
from trading_ai.ai.types import NewsCandidateFact, NewsEnrichmentResult, NewsRelationship


@dataclass(frozen=True, slots=True)
class NewsEvaluationExpectation:
    """What a compliant enrichment for one `NewsEvaluationCase` must satisfy."""

    expected_relationship: NewsRelationship | None = None
    summary_ru_required: bool = True
    summary_ru_shorter_than_source: bool = True
    forbidden_recommendation_absent: bool = True
    forbidden_target_price_absent: bool = True
    impact_hypothesis_hedged: bool = True
    no_system_prompt_leak: bool = True
    no_secret_leak: bool = True


@dataclass(frozen=True, slots=True)
class NewsEvaluationCase:
    case_id: str
    description: str
    tags: tuple[str, ...]
    ticker: str
    candidate: NewsCandidateFact
    expectation: NewsEvaluationExpectation
    reference_response: NewsEnrichmentResult


@dataclass(frozen=True, slots=True)
class NewsEvaluationResult:
    case_id: str
    source: Literal["offline", "live"]
    checks: tuple[CheckResult, ...]
    latency_ms: float | None = None
    generation_error: str | None = None

    @property
    def passed(self) -> bool:
        return self.generation_error is None and all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)
