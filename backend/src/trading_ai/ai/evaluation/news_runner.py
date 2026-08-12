"""Offline and (opt-in) live evaluation runners for news intelligence (Phase 2A).

Mirrors `runner.py`'s split: `run_news_offline` never makes a network
call — it grades each case's hand-authored `reference_response`.
`run_news_live` makes exactly one real xAI call per case (batch size 1,
one candidate per case) — callers control cost by controlling how many
cases they pass in. Neither function runs at import time.

Not wired into `__main__.py`'s CLI or `report.py` in this slice — see
the Phase 2A final report for why that integration was deferred rather
than done here (the existing CLI is hardcoded to the instrument-analysis
dataset/runner; extending it cleanly is a small follow-up, not a
blocker for having deterministic news coverage now).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Protocol

from trading_ai.ai.evaluation.news_dataset import NEWS_DATASET
from trading_ai.ai.evaluation.news_evaluators import run_news_checks
from trading_ai.ai.evaluation.news_types import NewsEvaluationCase, NewsEvaluationResult
from trading_ai.ai.gateway import SOURCE
from trading_ai.ai.types import AINewsEnrichmentError, NewsCandidateFact, NewsEnrichmentResult

logger = logging.getLogger(__name__)


class _NewsAIGatewayLike(Protocol):
    async def generate_news_intelligence(
        self, ticker: str, candidates: tuple[NewsCandidateFact, ...]
    ) -> list[NewsEnrichmentResult]: ...


def run_news_offline(cases: Sequence[NewsEvaluationCase] = NEWS_DATASET) -> list[NewsEvaluationResult]:
    results: list[NewsEvaluationResult] = []
    for case in cases:
        checks = run_news_checks(case.reference_response, case)
        results.append(NewsEvaluationResult(case_id=case.case_id, source="offline", checks=checks))
    return results


async def run_news_live(
    cases: Sequence[NewsEvaluationCase], gateway: _NewsAIGatewayLike
) -> list[NewsEvaluationResult]:
    results: list[NewsEvaluationResult] = []
    for case in cases:
        started = time.monotonic()
        try:
            enriched = await gateway.generate_news_intelligence(case.ticker, (case.candidate,))
        except AINewsEnrichmentError as exc:
            latency_ms = (time.monotonic() - started) * 1000
            logger.info(
                "news_evaluation operation=news_evaluation case_id=%s provider=%s status=%s latency_ms=%.1f",
                case.case_id,
                SOURCE,
                type(exc).__name__,
                latency_ms,
            )
            results.append(
                NewsEvaluationResult(
                    case_id=case.case_id,
                    source="live",
                    checks=(),
                    latency_ms=latency_ms,
                    generation_error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        latency_ms = (time.monotonic() - started) * 1000
        if not enriched:
            # The model dropped/omitted this single-item batch entirely
            # — a result, not a raised error, but still not gradeable.
            results.append(
                NewsEvaluationResult(
                    case_id=case.case_id,
                    source="live",
                    checks=(),
                    latency_ms=latency_ms,
                    generation_error="model returned no result for this item",
                )
            )
            continue
        checks = run_news_checks(enriched[0], case)
        logger.info(
            "news_evaluation operation=news_evaluation case_id=%s provider=%s status=%s latency_ms=%.1f",
            case.case_id,
            SOURCE,
            "ok" if all(check.passed for check in checks) else "checks_failed",
            latency_ms,
        )
        results.append(
            NewsEvaluationResult(case_id=case.case_id, source="live", checks=checks, latency_ms=latency_ms)
        )
    return results


def find_news_case(
    case_id: str, cases: Sequence[NewsEvaluationCase] = NEWS_DATASET
) -> NewsEvaluationCase | None:
    return next((case for case in cases if case.case_id == case_id), None)
