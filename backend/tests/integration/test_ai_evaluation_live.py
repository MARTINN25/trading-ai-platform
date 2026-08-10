"""Opt-in smoke test running the evaluation harness against the real xAI API.

Deliberately its own file with only `@pytest.mark.live_provider` on the
one test — same reasoning as `test_market_data_live.py`: a plain
`pytest -m integration` run must never fire a real external call.

Reuses `TRADING_AI_LIVE_LLM_API_KEY`, the same env var already used by
`test_market_data_live.py::test_live_instrument_analysis_smoke` for the
raw gateway smoke test. This test is narrower in scope: it exercises
the *evaluation harness* (dataset + evaluators + runner) against real
generations, not just the raw gateway contract.

Run explicitly:

    TRADING_AI_LIVE_LLM_API_KEY=... \\
        python -m pytest -m live_provider tests/integration/test_ai_evaluation_live.py -v

Exactly 3 representative cases (task scope §15) — never the full
dataset from an automated test.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from trading_ai.ai.evaluation.dataset import DATASET
from trading_ai.ai.evaluation.report import format_report
from trading_ai.ai.evaluation.runner import run_live
from trading_ai.ai.gateway import XAIGateway

_LIVE_LLM_API_KEY = os.environ.get("TRADING_AI_LIVE_LLM_API_KEY")
_SMOKE_CASE_IDS = ("normal-bullish-day", "quote-only-degraded", "prompt-injection-headline")


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_LLM_API_KEY,
    reason=(
        "TRADING_AI_LIVE_LLM_API_KEY is not set - skipping live AI "
        "evaluation smoke test (opt-in only)."
    ),
)
def test_live_evaluation_smoke_three_representative_cases() -> None:
    assert _LIVE_LLM_API_KEY is not None
    cases = [case for case in DATASET if case.case_id in _SMOKE_CASE_IDS]
    assert len(cases) == 3

    model = "grok-4.5"
    gateway = XAIGateway(api_key=_LIVE_LLM_API_KEY, model=model)
    results = asyncio.run(run_live(cases, gateway, model=model))

    # Print the honest human-review report so `-v -s` shows real model
    # behavior — never the raw prompt/response (report.py's own rule).
    print(format_report(results, model=model))

    assert len(results) == 3
    for result in results:
        # A generation error (timeout/rate-limit/provider issue) is a
        # legitimate, honestly-reported outcome, not a test bug — this
        # smoke test does not retry (task scope §15: "не делать
        # automatic retry"). Only assert structure when generation
        # actually succeeded.
        if result.generation_error is not None:
            continue
        assert len(result.checks) > 0
        failed = [c.name for c in result.failed_checks]
        assert failed == [], f"case {result.case_id!r} failed checks: {failed}"
