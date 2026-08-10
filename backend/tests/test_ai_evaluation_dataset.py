"""Dataset validation tests (task scope §14)."""

from __future__ import annotations

import re

from trading_ai.ai.evaluation.dataset import DATASET
from trading_ai.ai.evaluation.types import EvaluationCase

# Structural secret-shape patterns — mirrors evaluators.py's own list,
# applied here to the dataset source data itself rather than to model
# output (task scope §4: "Не хранить API keys/secrets").
_SECRET_LIKE = re.compile(r"bearer\s+[a-z0-9._-]{10,}|xai-[a-z0-9]{10,}|sk-[a-z0-9]{10,}", re.IGNORECASE)


def test_dataset_size_within_expected_range() -> None:
    assert 8 <= len(DATASET) <= 15


def test_case_ids_are_unique() -> None:
    ids = [case.case_id for case in DATASET]
    assert len(ids) == len(set(ids))


def test_all_cases_have_non_empty_description_and_id() -> None:
    for case in DATASET:
        assert case.case_id.strip() != ""
        assert case.description.strip() != ""


def test_all_cases_parse_as_evaluation_case() -> None:
    for case in DATASET:
        assert isinstance(case, EvaluationCase)
        assert case.analysis_input.ticker == case.reference_response.ticker


def test_no_secrets_in_dataset() -> None:
    for case in DATASET:
        response = case.reference_response
        haystacks = [
            case.description,
            response.summary,
            response.price_context,
            response.news_context,
            *response.risks,
        ]
        for item in case.analysis_input.news:
            haystacks.append(item.headline)
            if item.summary:
                haystacks.append(item.summary)
        for text in haystacks:
            assert not _SECRET_LIKE.search(text), f"secret-like pattern found in case {case.case_id!r}"


def test_no_live_looking_ticker_price_precision_artifacts() -> None:
    """Loose guard against accidentally pasted real quotes: every case
    uses the same synthetic ticker (task scope §3: "Не использовать
    текущие live market values")."""
    for case in DATASET:
        assert case.analysis_input.ticker == "ACME"


def test_reference_responses_pass_their_own_expectations() -> None:
    """Every hand-authored reference response is meant to be compliant
    (dataset.py's own docstring) — this is exercised end-to-end by
    test_ai_evaluation_runner.py's offline-run test; here we just check
    the structural pairing is present for every case."""
    for case in DATASET:
        assert case.reference_response.disclaimer != ""
        assert len(case.reference_response.risks) >= case.expectation.risks_min_count
