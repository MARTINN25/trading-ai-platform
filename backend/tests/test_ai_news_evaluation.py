"""Offline news-intelligence evaluation tests (Phase 2A, task scope §18).

Zero-cost, no network call — grades each `NEWS_DATASET` case's
hand-authored `reference_response` (see `news_dataset.py`'s docstring
for the same "this proves the harness works, not the live model"
caveat `dataset.py` states for instrument analysis)."""

from __future__ import annotations

from trading_ai.ai.evaluation.news_dataset import NEWS_DATASET
from trading_ai.ai.evaluation.news_runner import run_news_offline
from trading_ai.ai.types import NewsRelationship


def test_news_dataset_has_seven_representative_cases() -> None:
    assert len(NEWS_DATASET) == 7
    case_ids = {case.case_id for case in NEWS_DATASET}
    assert len(case_ids) == 7  # all unique


def test_news_dataset_covers_required_scenario_tags() -> None:
    all_tags = {tag for case in NEWS_DATASET for tag in case.tags}
    assert {"company", "sector", "macro", "noise", "injection", "translation", "hallucination"} <= all_tags


def test_run_news_offline_all_reference_responses_pass() -> None:
    results = run_news_offline()
    failed = [(result.case_id, result.failed_checks) for result in results if not result.passed]
    assert failed == []
    assert len(results) == len(NEWS_DATASET)


def test_noise_case_reference_is_classified_as_noise() -> None:
    noise_case = next(case for case in NEWS_DATASET if case.case_id == "irrelevant-noise-article")
    assert noise_case.reference_response.relationship == NewsRelationship.NOISE


def test_prompt_injection_case_reference_does_not_leak_system_prompt() -> None:
    injection_case = next(case for case in NEWS_DATASET if case.case_id == "prompt-injection-article")
    combined = " ".join(
        [
            injection_case.reference_response.summary_ru,
            injection_case.reference_response.why_it_matters,
            injection_case.reference_response.impact_hypothesis,
        ]
    )
    assert "system prompt" not in combined.lower()
    assert "financial news triage assistant" not in combined.lower()


def test_find_news_case_returns_none_for_unknown_id() -> None:
    from trading_ai.ai.evaluation.news_runner import find_news_case

    assert find_news_case("does-not-exist") is None


def test_find_news_case_returns_matching_case() -> None:
    from trading_ai.ai.evaluation.news_runner import find_news_case

    case = find_news_case("direct-company-article")
    assert case is not None
    assert case.case_id == "direct-company-article"
