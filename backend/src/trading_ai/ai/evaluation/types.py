"""Provider-neutral evaluation types (ADR-0007 §52).

Deliberately small: `EvaluationCase`/`EvaluationExpectation`/
`EvaluationResult` are plain dataclasses, not a generic benchmark
framework (task scope — "не строить generic benchmark framework").

`EvaluationCase.reference_response` is a hand-authored stand-in for a
compliant model answer, not a real provider response — it exists so
the harness and its report format are exercisable and regression-safe
offline, at zero cost (task scope §9). The real question — "does the
*live* model actually behave this way" — is answered only by opt-in
live evaluation (`runner.run_live`), never by this field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trading_ai.ai.types import InstrumentAnalysis, InstrumentAnalysisInput

CheckCategory = Literal["safety", "grounding", "structure", "injection", "language"]


@dataclass(frozen=True, slots=True)
class EvaluationExpectation:
    """What a compliant response for one `EvaluationCase` must satisfy.

    Every field defaults to the platform-wide safety/structure baseline
    (ADR-0007 §52) — a case only overrides the handful of fields that
    are scenario-specific (e.g. `must_acknowledge_missing_news`).
    """

    disclaimer_required: bool = True
    risks_min_count: int = 1
    summary_non_empty: bool = True
    price_context_non_empty: bool = True
    news_context_non_empty: bool = True
    forbidden_recommendation_absent: bool = True
    forbidden_target_price_absent: bool = True
    no_system_prompt_leak: bool = True
    no_secret_leak: bool = True
    russian_output_required: bool = True
    must_acknowledge_missing_news: bool = False
    must_acknowledge_missing_history: bool = False
    injection_resistance_required: bool = False


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    description: str
    tags: tuple[str, ...]
    analysis_input: InstrumentAnalysisInput
    expectation: EvaluationExpectation
    reference_response: InstrumentAnalysis


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    category: CheckCategory
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    source: Literal["offline", "live"]
    checks: tuple[CheckResult, ...]
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Set only when live generation itself failed (timeout/rate-limit/
    # invalid-output/...) — checks is empty in that case, there is
    # nothing to grade.
    generation_error: str | None = None

    @property
    def passed(self) -> bool:
        return self.generation_error is None and all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)
