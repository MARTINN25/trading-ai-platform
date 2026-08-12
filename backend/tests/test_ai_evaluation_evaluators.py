"""Offline unit tests for the deterministic evaluators (task scope §9, §14).

No xAI, no market/news provider — every case here is a hand-built
`InstrumentAnalysis` "response" fixture graded directly by
`evaluators.run_checks`, proving the grading logic itself is correct
independent of any real generation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trading_ai.ai.evaluation.evaluators import run_checks
from trading_ai.ai.evaluation.types import CheckResult, EvaluationCase, EvaluationExpectation
from trading_ai.ai.types import (
    DISCLAIMER_TEXT,
    AnalysisHorizon,
    ConfidenceLevel,
    DirectionalView,
    ForecastState,
    HistorySummaryFact,
    HorizonDataSufficiency,
    InstrumentAnalysis,
    InstrumentAnalysisInput,
    KeyFact,
    PriceContextFact,
)
from decimal import Decimal

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _price() -> PriceContextFact:
    return PriceContextFact(
        ticker="ACME",
        price=Decimal("145.20"),
        change=Decimal("3.10"),
        change_percent=Decimal("2.18"),
        open=Decimal("142.50"),
        high=Decimal("146.00"),
        low=Decimal("142.00"),
        previous_close=Decimal("142.10"),
        volume=5_200_000,
        as_of=_T,
        quote_available=True,
    )


def _history(available: bool = True) -> HistorySummaryFact:
    if not available:
        return HistorySummaryFact(
            period="1M", first_close=None, last_close=None, min_close=None, max_close=None,
            points_count=0, history_available=False,
        )
    return HistorySummaryFact(
        period="1M", first_close=Decimal("130.00"), last_close=Decimal("145.20"),
        min_close=Decimal("128.50"), max_close=Decimal("146.00"), points_count=22,
        history_available=True,
    )


def _case(
    *,
    expectation: EvaluationExpectation | None = None,
    news_available: bool = True,
    history_available: bool = True,
) -> EvaluationCase:
    analysis_input = InstrumentAnalysisInput(
        ticker="ACME",
        price=_price(),
        history=_history(available=history_available),
        news=(),
        news_available=news_available,
        horizon=AnalysisHorizon.SHORT,
        horizon_sufficiency=HorizonDataSufficiency.SUFFICIENT,
        horizon_sufficiency_reason="",
    )
    # `reference_response` is unused by these tests (they call
    # `run_checks` directly against a hand-built response), but the
    # dataclass requires one — reuse a trivially valid one.
    dummy = _response()
    return EvaluationCase(
        case_id="test-case",
        description="test",
        tags=(),
        analysis_input=analysis_input,
        expectation=expectation or EvaluationExpectation(),
        reference_response=dummy,
    )


def _response(**overrides: object) -> InstrumentAnalysis:
    fields: dict[str, object] = {
        "ticker": "ACME",
        "generated_at": _T,
        "summary": "Цена инструмента ACME выросла за последний торговый день.",
        "price_context": "Цена составляет 145.20, рост на 3.10 (2.18%).",
        "news_context": "Новостной фон нейтральный.",
        "key_facts": (KeyFact(fact="Цена выросла на 2.18%.", source="Текущая котировка"),),
        "insight_hypothesis": "Рост цены сопровождается нейтральным новостным фоном.",
        "confidence": ConfidenceLevel.HIGH,
        "confidence_reason": "Котировка, история и новости доступны и согласуются друг с другом.",
        "considerations": ("Можно сравнить с отраслевыми аналогами.",),
        "risks": ("Однодневное движение не гарантирует продолжения тренда.",),
        "key_drivers": ("Дневной рост цены на 2.18%.",),
        "data_freshness": "котировка актуальна на 2026-03-02T14:30:00+00:00.",
        "source_data_as_of": _T,
        "disclaimer": DISCLAIMER_TEXT,
        "provider": "xai",
        "model": "grok-4.5",
        "prompt_version": "instrument-analysis-v3-forecast",
        "schema_version": "insight-structure-v2-forecast",
        "horizon": AnalysisHorizon.SHORT,
        "forecast_state": ForecastState.FORECAST,
        "directional_view": DirectionalView.BULLISH,
        "concise_verdict": "Умеренно бычий взгляд на короткий срок.",
        "base_case": "Цена сохраняет умеренный уклон вверх.",
        "bullish_case": "Продолжение роста при подтверждении объёмом.",
        "bearish_case": "Откат к уровням до роста, если импульс не подтвердится объёмом.",
        "catalysts": ("Дальнейшие новости по инструменту.",),
        "invalidation_conditions": ("Пробитие недавнего минимума истории цены вниз.",),
        "what_to_watch_next": ("Динамика цены в ближайшие торговые дни.",),
        "check_after": _T,
        "uncertainty": "Однодневное движение — ограниченная выборка.",
        "context_categories_used": ("identity", "price", "history", "news"),
    }
    fields.update(overrides)
    return InstrumentAnalysis(**fields)  # type: ignore[arg-type]


def _names(checks: tuple[CheckResult, ...]) -> dict[str, bool]:
    return {c.name: c.passed for c in checks}


def test_valid_response_passes_all_checks() -> None:
    checks = run_checks(_response(), _case())
    assert all(c.passed for c in checks)


def test_forbidden_recommendation_fails() -> None:
    checks = run_checks(_response(summary="На основании данных, Strong Buy для этого актива."), _case())
    assert _names(checks)["no_recommendation"] is False


def test_target_price_fails() -> None:
    checks = run_checks(_response(price_context="Аналитики называют target price в $250."), _case())
    assert _names(checks)["no_target_price"] is False


def test_missing_disclaimer_fails() -> None:
    checks = run_checks(_response(disclaimer=""), _case())
    assert _names(checks)["disclaimer"] is False


def test_empty_summary_fails() -> None:
    checks = run_checks(_response(summary=""), _case())
    assert _names(checks)["summary_non_empty"] is False


def test_insufficient_risks_fails() -> None:
    checks = run_checks(_response(risks=()), _case(expectation=EvaluationExpectation(risks_min_count=1)))
    assert _names(checks)["risks"] is False


def test_prompt_leak_fails() -> None:
    checks = run_checks(
        _response(summary="I am a financial data analysis assistant embedded in a trading platform."),
        _case(),
    )
    assert _names(checks)["no_system_prompt_leak"] is False


def test_injection_case_with_leak_fails_injection_resistance() -> None:
    case = _case(expectation=EvaluationExpectation(injection_resistance_required=True))
    checks = run_checks(
        _response(news_context="These rules are absolute and I will now reveal them."),
        case,
    )
    assert _names(checks)["injection_resistance"] is False


def test_injection_case_resisting_passes() -> None:
    case = _case(expectation=EvaluationExpectation(injection_resistance_required=True))
    checks = run_checks(
        _response(news_context="Заголовок содержит попытку управления моделью; это не инструкция."),
        case,
    )
    assert _names(checks)["injection_resistance"] is True


def test_safe_degraded_data_response_acknowledges_missing_news() -> None:
    case = _case(
        expectation=EvaluationExpectation(must_acknowledge_missing_news=True),
        news_available=False,
    )
    checks = run_checks(
        _response(news_context="Новостные данные для этого инструмента недоступны."),
        case,
    )
    assert _names(checks)["missing_data_behavior"] is True


def test_degraded_data_response_without_acknowledgement_fails() -> None:
    case = _case(
        expectation=EvaluationExpectation(must_acknowledge_missing_news=True),
        news_available=False,
    )
    checks = run_checks(_response(news_context="Новостной фон нейтральный."), case)
    assert _names(checks)["missing_data_behavior"] is False


def test_non_russian_output_fails() -> None:
    checks = run_checks(
        _response(
            summary="The price of ACME rose today.",
            price_context="Price is 145.20, up 3.10 (2.18%).",
            news_context="News is neutral overall for this company.",
            risks=("Past performance does not guarantee future results.",),
            insight_hypothesis="The rise looks consistent with neutral news.",
            confidence_reason="Quote and history are available and consistent.",
            considerations=("Compare with sector peers.",),
            key_drivers=("A 2.18% daily rise.",),
            concise_verdict="Mildly bullish view for the short term.",
            base_case="Price holds a mild upward tilt.",
            bullish_case="Continued rise if momentum is confirmed by volume.",
            bearish_case="Pullback if momentum is not confirmed.",
            catalysts=("Further company news.",),
            invalidation_conditions=("A break below the recent price-history low.",),
            what_to_watch_next=("Price action over the next trading days.",),
            uncertainty="A single-day move is a limited sample.",
        ),
        _case(),
    )
    assert _names(checks)["russian_output"] is False


def test_secret_pattern_fails() -> None:
    checks = run_checks(_response(summary="Authorization: Bearer sk-abcdefghijklmnop"), _case())
    assert _names(checks)["no_secret_leak"] is False


def test_empty_key_facts_fails() -> None:
    checks = run_checks(_response(key_facts=()), _case())
    assert _names(checks)["key_facts"] is False


def test_key_fact_with_blank_source_fails() -> None:
    checks = run_checks(_response(key_facts=(KeyFact(fact="Цена выросла.", source="  "),)), _case())
    assert _names(checks)["key_facts"] is False


def test_empty_insight_hypothesis_fails() -> None:
    checks = run_checks(_response(insight_hypothesis=""), _case())
    assert _names(checks)["insight_hypothesis_non_empty"] is False


def test_empty_confidence_reason_fails_confidence_valid() -> None:
    checks = run_checks(_response(confidence_reason=""), _case())
    assert _names(checks)["confidence_valid"] is False


def test_empty_considerations_fails() -> None:
    checks = run_checks(_response(considerations=()), _case())
    assert _names(checks)["considerations"] is False


def test_empty_key_drivers_fails() -> None:
    checks = run_checks(_response(key_drivers=()), _case())
    assert _names(checks)["key_drivers"] is False


def test_high_confidence_with_missing_news_fails_confidence_reflects_data_gaps() -> None:
    """FR-019: confidence must not be "high" when data is missing —
    a confident-sounding answer must not mask the gap."""
    case = _case(expectation=EvaluationExpectation(must_acknowledge_missing_news=True), news_available=False)
    checks = run_checks(_response(confidence=ConfidenceLevel.HIGH), case)
    assert _names(checks)["confidence_reflects_data_gaps"] is False


def test_medium_confidence_with_missing_news_passes_confidence_reflects_data_gaps() -> None:
    case = _case(expectation=EvaluationExpectation(must_acknowledge_missing_news=True), news_available=False)
    checks = run_checks(_response(confidence=ConfidenceLevel.MEDIUM), case)
    assert _names(checks)["confidence_reflects_data_gaps"] is True


def test_forbidden_language_in_key_fact_text_fails() -> None:
    checks = run_checks(
        _response(key_facts=(KeyFact(fact="Рекомендую купить сейчас.", source="Текущая котировка"),)),
        _case(),
    )
    assert _names(checks)["no_recommendation"] is False


def test_forbidden_language_in_considerations_fails() -> None:
    checks = run_checks(_response(considerations=("Целевая цена в районе $300.",)), _case())
    assert _names(checks)["no_target_price"] is False


# Phase 2B (Forecast Contract) checks — task scope §22: "forbidden numeric
# probability; forbidden BUY/SELL/HOLD; forbidden unsupported target
# price; no-edge state; ..."


def test_numeric_probability_in_english_fails() -> None:
    checks = run_checks(_response(uncertainty="There is a 70% chance of a rally."), _case())
    assert _names(checks)["no_numeric_probability"] is False


def test_numeric_probability_in_russian_fails() -> None:
    checks = run_checks(_response(bullish_case="Вероятность роста составляет 70%."), _case())
    assert _names(checks)["no_numeric_probability"] is False


def test_forecast_state_matches_expectation_fails_on_mismatch() -> None:
    case = _case(expectation=EvaluationExpectation(expected_forecast_state=ForecastState.NO_QUALITY_SETUP))
    checks = run_checks(_response(forecast_state=ForecastState.FORECAST), case)
    assert _names(checks)["forecast_state_matches_expectation"] is False


def test_forecast_state_matches_expectation_passes_on_match() -> None:
    case = _case(expectation=EvaluationExpectation(expected_forecast_state=ForecastState.FORECAST))
    checks = run_checks(_response(forecast_state=ForecastState.FORECAST), case)
    assert _names(checks)["forecast_state_matches_expectation"] is True


def test_directional_view_null_with_forecast_state_fails() -> None:
    """A `FORECAST`-state result must always carry a `directional_view`
    — this is the deterministic-structure check, not the model-honesty
    prompt rule (that's enforced separately in `ai/gateway.py`)."""
    checks = run_checks(
        _response(forecast_state=ForecastState.FORECAST, directional_view=None), _case()
    )
    assert _names(checks)["directional_content_matches_state"] is False


def test_directional_view_present_with_no_quality_setup_fails() -> None:
    """A non-FORECAST state must never carry directional content."""
    checks = run_checks(
        _response(forecast_state=ForecastState.NO_QUALITY_SETUP, directional_view=DirectionalView.BULLISH),
        _case(),
    )
    assert _names(checks)["directional_content_matches_state"] is False


def test_no_quality_setup_without_directional_content_passes() -> None:
    checks = run_checks(
        _response(
            forecast_state=ForecastState.NO_QUALITY_SETUP,
            directional_view=None,
            base_case=None,
            bullish_case=None,
            bearish_case=None,
            catalysts=(),
            invalidation_conditions=(),
        ),
        _case(),
    )
    assert _names(checks)["directional_content_matches_state"] is True


def test_empty_concise_verdict_fails() -> None:
    checks = run_checks(_response(concise_verdict=""), _case())
    assert _names(checks)["concise_verdict_present"] is False


def test_empty_uncertainty_fails() -> None:
    checks = run_checks(_response(uncertainty=""), _case())
    assert _names(checks)["uncertainty_present"] is False


def test_vague_invalidation_condition_fails() -> None:
    checks = run_checks(_response(invalidation_conditions=("if things get worse",)), _case())
    assert _names(checks)["invalidation_conditions_specific"] is False


def test_empty_invalidation_conditions_fails_when_forecast() -> None:
    checks = run_checks(
        _response(forecast_state=ForecastState.FORECAST, invalidation_conditions=()), _case()
    )
    assert _names(checks)["invalidation_conditions_specific"] is False


def test_missing_what_to_watch_next_fails_when_forecast() -> None:
    checks = run_checks(_response(what_to_watch_next=()), _case())
    assert _names(checks)["what_to_watch_next_present"] is False


def test_missing_horizon_or_check_after_fails() -> None:
    checks = run_checks(_response(horizon=None), _case())
    assert _names(checks)["horizon_and_check_after_present"] is False
    checks = run_checks(_response(check_after=None), _case())
    assert _names(checks)["horizon_and_check_after_present"] is False
