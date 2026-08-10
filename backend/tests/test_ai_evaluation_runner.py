"""Offline runner, report formatting, and CLI behavior (task scope §14).

No xAI, no market/news provider calls anywhere in this file — `run_live`
is exercised here only against a fake in-process gateway, never the
real `XAIGateway` (that's `tests/integration/test_ai_evaluation_live.py`,
opt-in only).
"""

from __future__ import annotations

import logging
import subprocess
import sys

import pytest

from trading_ai.ai.evaluation.dataset import DATASET
from trading_ai.ai.evaluation.report import format_report
from trading_ai.ai.evaluation.runner import find_case, run_live, run_offline
from trading_ai.ai.evaluation.types import CheckResult, EvaluationResult
from trading_ai.ai.types import AIProviderUnavailableError, InstrumentAnalysis, InstrumentAnalysisInput


def test_run_offline_all_dataset_cases_pass() -> None:
    """Every hand-authored reference response is meant to be compliant —
    this is the concrete assertion that the harness end-to-end (dataset
    + evaluators + runner) agrees with that intent."""
    results = run_offline(DATASET)

    assert len(results) == len(DATASET)
    failing = [r.case_id for r in results if not r.passed]
    assert failing == [], f"unexpected offline failures: {failing}"
    assert all(r.source == "offline" for r in results)
    assert all(r.generation_error is None for r in results)


def test_run_offline_single_case() -> None:
    case = find_case("prompt-injection-headline")
    assert case is not None
    results = run_offline([case])
    assert len(results) == 1
    assert results[0].case_id == "prompt-injection-headline"


def test_find_case_unknown_returns_none() -> None:
    assert find_case("does-not-exist") is None


def test_report_contains_summary_counts() -> None:
    results = run_offline(DATASET)
    report = format_report(results)
    assert "mode=offline" in report
    assert f"{len(DATASET)}/{len(DATASET)} cases passed" in report
    assert "0 safety violations" in report
    for case in DATASET:
        assert f"Case: {case.case_id}" in report


def test_report_counts_safety_violation_distinctly_from_structure_failure() -> None:
    result_with_safety_failure = EvaluationResult(
        case_id="x",
        source="offline",
        checks=(
            CheckResult("no_recommendation", "safety", False, "found: 'strong buy'"),
            CheckResult("summary_non_empty", "structure", True),
        ),
    )
    report = format_report([result_with_safety_failure])
    assert "1 safety violations" in report
    assert "0/1 cases passed" in report


def test_report_counts_structure_failure_without_safety_violation() -> None:
    result_with_structure_failure = EvaluationResult(
        case_id="y",
        source="offline",
        checks=(
            CheckResult("summary_non_empty", "structure", False, "blank"),
            CheckResult("no_recommendation", "safety", True),
        ),
    )
    report = format_report([result_with_structure_failure])
    assert "0 safety violations" in report
    assert "0/1 cases passed" in report


def test_report_never_contains_full_response_text() -> None:
    """`CheckResult.detail` strings are short hand-written fragments, not
    a dump of the analysis text (task scope §10, §17, §18)."""
    results = run_offline(DATASET)
    report = format_report(results)
    for case in DATASET:
        assert case.reference_response.summary not in report
        assert case.reference_response.price_context not in report
        assert case.reference_response.news_context not in report


def test_cli_offline_single_case_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "trading_ai.ai.evaluation", "--offline", "--case", "normal-bullish-day"],
        capture_output=True,
        text=True,
        cwd="src",
        timeout=30,
    )
    assert result.returncode == 0
    assert "Case: normal-bullish-day" in result.stdout
    assert "1/1 cases passed" in result.stdout


def test_cli_offline_unknown_case_exits_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "trading_ai.ai.evaluation", "--offline", "--case", "does-not-exist"],
        capture_output=True,
        text=True,
        cwd="src",
        timeout=30,
    )
    assert result.returncode == 2
    assert "Unknown case id" in result.stderr


def test_cli_offline_full_dataset_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "trading_ai.ai.evaluation"],
        capture_output=True,
        text=True,
        cwd="src",
        timeout=30,
    )
    assert result.returncode == 0
    assert f"{len(DATASET)}/{len(DATASET)} cases passed" in result.stdout


class _FakeGateway:
    def __init__(self, result: InstrumentAnalysis | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def generate_instrument_analysis(
        self, analysis_input: InstrumentAnalysisInput
    ) -> InstrumentAnalysis:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


@pytest.mark.anyio
async def test_run_live_success_produces_checks_and_latency() -> None:
    case = find_case("normal-bullish-day")
    assert case is not None
    gateway = _FakeGateway(result=case.reference_response)

    results = await run_live([case], gateway, model="grok-4.5")

    assert len(results) == 1
    assert results[0].source == "live"
    assert results[0].generation_error is None
    assert results[0].latency_ms is not None
    assert results[0].passed is True


@pytest.mark.anyio
async def test_run_live_generation_failure_is_reported_not_raised() -> None:
    case = find_case("normal-bullish-day")
    assert case is not None
    gateway = _FakeGateway(error=AIProviderUnavailableError("boom"))

    results = await run_live([case], gateway, model="grok-4.5")

    assert len(results) == 1
    assert results[0].checks == ()
    assert results[0].generation_error is not None
    assert "AIProviderUnavailableError" in results[0].generation_error
    assert results[0].passed is False


@pytest.mark.anyio
async def test_run_live_does_not_log_prompt_or_secret(caplog: pytest.LogCaptureFixture) -> None:
    case = find_case("prompt-injection-headline")
    assert case is not None
    gateway = _FakeGateway(result=case.reference_response)

    with caplog.at_level(logging.INFO):
        await run_live([case], gateway, model="grok-4.5")

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert case.reference_response.summary not in log_text
    assert case.reference_response.news_context not in log_text
    assert "Ignore previous instructions" not in log_text  # the injected headline text itself
    assert "operation=ai_evaluation" in log_text
    assert "case_id=prompt-injection-headline" in log_text
    assert "provider=xai" in log_text
    assert "model=grok-4.5" in log_text
