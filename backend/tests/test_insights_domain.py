"""Unit tests for `insights.domain` — no DB, no HTTP (task scope §19)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.ai.types import ConfidenceLevel, KeyFact
from trading_ai.insights.domain import (
    InsightNotFoundError,
    NewInsight,
    PendingAnalysisNotFoundError,
    SavedInsight,
)

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _new_insight(**overrides: object) -> NewInsight:
    fields: dict[str, object] = {
        "ticker": "ACME",
        "generated_at": _T,
        "summary": "s",
        "price_context": "p",
        "news_context": "n",
        "key_facts": (KeyFact(fact="f", source="Текущая котировка"),),
        "insight_hypothesis": "h",
        "confidence": ConfidenceLevel.HIGH,
        "confidence_reason": "cr",
        "considerations": ("c",),
        "risks": ("r",),
        "key_drivers": ("kd",),
        "data_freshness": "df",
        "source_data_as_of": _T,
        "disclaimer": "d",
        "provider": "xai",
        "model": "grok-4.5",
        "prompt_version": "instrument-analysis-v2",
        "schema_version": "insight-structure-v1",
    }
    fields.update(overrides)
    return NewInsight(**fields)  # type: ignore[arg-type]


def test_new_insight_covers_all_fr018_sections() -> None:
    """Structural check that every FR-018 section has a field on the
    persistence-bound shape, not just the ephemeral `InstrumentAnalysis`."""
    insight = _new_insight()
    assert insight.summary  # 1. Краткое резюме
    assert insight.key_facts  # 2. Ключевые факты с источниками
    assert insight.price_context and insight.news_context  # 3. Анализ
    assert insight.insight_hypothesis  # 4. Инсайт или гипотеза
    assert insight.confidence and insight.confidence_reason  # 5. Уровень уверенности
    assert insight.considerations  # 6. Что можно рассмотреть
    assert insight.risks  # 7. Основные риски
    assert insight.key_drivers  # 8. Что сильнее всего повлияло на вывод
    assert insight.data_freshness  # 9. Актуальность использованных данных
    # 10. Facts (key_facts) and interpretation (insight_hypothesis) are
    # structurally distinct fields, not one blended field — both are
    # already asserted present above; this just names the field pair.
    assert isinstance(insight.key_facts, tuple) and isinstance(insight.insight_hypothesis, str)


def test_confidence_is_a_documented_categorical_value_not_a_fabricated_number() -> None:
    insight = _new_insight(confidence=ConfidenceLevel.LOW)
    assert insight.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
    assert insight.confidence.value in ("high", "medium", "low")


def test_key_fact_carries_a_source_label() -> None:
    fact = KeyFact(fact="Цена выросла.", source="Текущая котировка")
    assert fact.source == "Текущая котировка"


def test_new_insight_records_provenance_fields() -> None:
    """ADR-0004 §23 / ADR-0007 §46 minimum: provider, model, prompt
    version, schema version, source-data timestamp."""
    insight = _new_insight()
    assert insight.provider == "xai"
    assert insight.model == "grok-4.5"
    assert insight.prompt_version == "instrument-analysis-v2"
    assert insight.schema_version == "insight-structure-v1"
    assert insight.source_data_as_of == _T
    assert insight.generated_at.tzinfo is not None


def test_saved_insight_is_frozen() -> None:
    """ADR-0004 §20 immutability — a persisted insight cannot be mutated
    once constructed."""
    saved = SavedInsight(
        id=1,
        ticker="ACME",
        generated_at=_T,
        created_at=_T,
        summary="s",
        price_context="p",
        news_context="n",
        key_facts=(KeyFact(fact="f", source="Текущая котировка"),),
        insight_hypothesis="h",
        confidence=ConfidenceLevel.HIGH,
        confidence_reason="cr",
        considerations=("c",),
        risks=("r",),
        key_drivers=("kd",),
        data_freshness="df",
        source_data_as_of=_T,
        disclaimer="d",
        provider="xai",
        model="grok-4.5",
        prompt_version="instrument-analysis-v2",
        schema_version="insight-structure-v1",
    )
    with pytest.raises((AttributeError, TypeError)):
        saved.summary = "tampered"  # type: ignore[misc]


def test_pending_analysis_not_found_error_carries_ticker() -> None:
    error = PendingAnalysisNotFoundError("ACME")
    assert error.ticker == "ACME"


def test_insight_not_found_error_carries_id() -> None:
    error = InsightNotFoundError(42)
    assert error.insight_id == 42
