"""Offline and live evaluation runners (ADR-0007 §52, task scope §8-9).

`run_offline` never makes a network call — it grades each case's
hand-authored `reference_response` (see `dataset.py`). `run_live` makes
exactly one real xAI call per case passed to it; callers control cost
by controlling how many cases they pass in (see `__main__.py`'s
default of 3 representative cases for `--live`).

Neither function is called at import time — evaluation only happens
when a caller (CLI, or a test explicitly marked `live_provider`)
invokes one of these (task scope §16: "не делать live calls на
import").
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Protocol

from trading_ai.ai.evaluation.dataset import DATASET
from trading_ai.ai.evaluation.evaluators import run_checks
from trading_ai.ai.evaluation.types import EvaluationCase, EvaluationResult
from trading_ai.ai.gateway import SOURCE
from trading_ai.ai.types import AIAnalysisError, InstrumentAnalysis, InstrumentAnalysisInput

logger = logging.getLogger(__name__)


class _AIGatewayLike(Protocol):
    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis: ...


def run_offline(cases: Sequence[EvaluationCase] = DATASET) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        checks = run_checks(case.reference_response, case)
        results.append(EvaluationResult(case_id=case.case_id, source="offline", checks=checks))
    return results


async def run_live(
    cases: Sequence[EvaluationCase], gateway: _AIGatewayLike, *, model: str | None = None
) -> list[EvaluationResult]:
    """One real call per case in `cases` — callers decide how many
    cases that is (task scope §8: bounded by the caller, not this
    function).

    `input_tokens`/`output_tokens` on the result are always `None`:
    `XAIGateway.generate_instrument_analysis` doesn't return usage to
    its caller today (it only logs it internally, ADR-0007 §48). Not
    threading that through is an honest limitation of this first
    slice, not a silent omission — see the final report. `model` is
    accepted purely for the observability log line below (task scope
    §18) — it isn't used to configure the call itself, that's the
    caller's `gateway` construction.
    """
    results: list[EvaluationResult] = []
    for case in cases:
        started = time.monotonic()
        try:
            analysis = await gateway.generate_instrument_analysis(case.analysis_input)
        except AIAnalysisError as exc:
            latency_ms = (time.monotonic() - started) * 1000
            logger.info(
                "ai_evaluation operation=ai_evaluation case_id=%s provider=%s status=%s latency_ms=%.1f",
                case.case_id,
                SOURCE,
                type(exc).__name__,
                latency_ms,
            )
            results.append(
                EvaluationResult(
                    case_id=case.case_id,
                    source="live",
                    checks=(),
                    latency_ms=latency_ms,
                    generation_error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        latency_ms = (time.monotonic() - started) * 1000
        checks = run_checks(analysis, case)
        # Never the full prompt/response — only fixed, safe fields
        # (task scope §18, same rule as XAIGateway._log).
        logger.info(
            "ai_evaluation operation=ai_evaluation case_id=%s provider=%s model=%s status=%s "
            "latency_ms=%.1f",
            case.case_id,
            SOURCE,
            model or "unknown",
            "ok" if all(check.passed for check in checks) else "checks_failed",
            latency_ms,
        )
        results.append(
            EvaluationResult(
                case_id=case.case_id,
                source="live",
                checks=checks,
                latency_ms=latency_ms,
            )
        )
    return results


def find_case(case_id: str, cases: Sequence[EvaluationCase] = DATASET) -> EvaluationCase | None:
    return next((case for case in cases if case.case_id == case_id), None)
