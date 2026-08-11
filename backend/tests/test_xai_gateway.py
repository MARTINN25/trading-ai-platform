"""`XAIGateway` tests — mock only the external provider boundary
(`httpx.MockTransport`, no extra dependency), never our own use cases.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import pytest

from trading_ai.ai.gateway import SOURCE, XAIGateway
from trading_ai.ai.types import (
    AIInvalidOutputError,
    AIProviderUnavailableError,
    AIRateLimitedError,
    AITimeoutError,
    ConfidenceLevel,
    HistorySummaryFact,
    InstrumentAnalysisInput,
    NewsHeadlineFact,
    PriceContextFact,
)

_FAKE_API_KEY = "test-xai-secret-should-never-leak"

# Every field FR-018 requires (see ai/gateway.py's ModelOutputSchema) —
# omitting any of the 6 new ones (key_facts/insight_hypothesis/
# confidence/confidence_reason/considerations/key_drivers) would fail
# schema validation, same as the original 4.
_FULL_VALID_FIELDS: dict[str, object] = {
    "summary": "Компания демонстрирует смешанные показатели за последний период.",
    "price_context": "Цена снизилась на 2% за последний торговый день по имеющимся данным.",
    "news_context": "Недавние заголовки упоминают понижение рейтинга аналитиками.",
    "key_facts": [
        {"fact": "Цена снизилась на 2% за последний торговый день.", "source": "Текущая котировка"},
    ],
    "insight_hypothesis": "Снижение может отражать реакцию на понижение рейтинга.",
    "confidence": "medium",
    "confidence_reason": "Данные о цене доступны, но новостной контекст ограничен.",
    "considerations": ["Стоит проверить дальнейшую динамику в последующие дни."],
    "risks": [
        "Исторические данные ограничены выбранным периодом.",
        "Часть новостных данных может быть неполной.",
    ],
    "key_drivers": ["Снижение цены на 2%.", "Понижение рейтинга аналитиками."],
}

_SUCCESS_CONTENT = json.dumps(_FULL_VALID_FIELDS)

_SUCCESS_PAYLOAD: dict[str, Any] = {
    "id": "chatcmpl-test",
    "model": "grok-4.5",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": _SUCCESS_CONTENT},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 500, "completion_tokens": 120, "total_tokens": 620},
}


def _gateway(handler: object) -> XAIGateway:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return XAIGateway(api_key=_FAKE_API_KEY, transport=transport)


def _sample_input(news: tuple[NewsHeadlineFact, ...] = ()) -> InstrumentAnalysisInput:
    return InstrumentAnalysisInput(
        ticker="AAPL",
        price=PriceContextFact(
            ticker="AAPL",
            price=Decimal("213.45"),
            change=Decimal("-2.31"),
            change_percent=Decimal("-1.09"),
            open=Decimal("215.00"),
            high=Decimal("216.00"),
            low=Decimal("212.00"),
            previous_close=Decimal("215.76"),
            volume=48_213_456,
            as_of=datetime.now(timezone.utc),
            quote_available=True,
        ),
        history=HistorySummaryFact(
            period="1M",
            first_close=Decimal("200.00"),
            last_close=Decimal("213.45"),
            min_close=Decimal("195.00"),
            max_close=Decimal("220.00"),
            points_count=22,
            history_available=True,
        ),
        news=news,
        news_available=True,
    )


@pytest.mark.anyio
async def test_generate_instrument_analysis_maps_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    analysis = await _gateway(handler).generate_instrument_analysis(_sample_input())

    assert analysis.ticker == "AAPL"
    assert analysis.provider == SOURCE
    assert analysis.model == "grok-4.5"
    assert "смешанные" in analysis.summary
    assert len(analysis.risks) == 2
    assert analysis.disclaimer == (
        "AI-анализ носит информационный характер и не является инвестиционной рекомендацией."
    )
    assert analysis.generated_at.tzinfo is not None
    # FR-018's new sections:
    assert len(analysis.key_facts) == 1
    assert analysis.key_facts[0].fact != ""
    assert analysis.key_facts[0].source == "Текущая котировка"
    assert analysis.insight_hypothesis != ""
    assert analysis.confidence == ConfidenceLevel.MEDIUM
    assert analysis.confidence_reason != ""
    assert len(analysis.considerations) == 1
    assert len(analysis.key_drivers) == 2
    # data_freshness/source_data_as_of are backend-computed, never from
    # the model's JSON content.
    assert "котировка актуальна" in analysis.data_freshness
    assert analysis.source_data_as_of is not None
    assert analysis.prompt_version == "instrument-analysis-v2"
    assert analysis.schema_version == "insight-structure-v1"


@pytest.mark.anyio
async def test_generate_instrument_analysis_sends_api_key_as_bearer_header() -> None:
    seen_auth_header = ""
    seen_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_auth_header, seen_url
        seen_auth_header = request.headers.get("Authorization", "")
        seen_url = str(request.url)
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    await _gateway(handler).generate_instrument_analysis(_sample_input())

    assert seen_auth_header == f"Bearer {_FAKE_API_KEY}"
    assert _FAKE_API_KEY not in seen_url


@pytest.mark.anyio
async def test_generate_instrument_analysis_timeout_raises_timeout_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(AITimeoutError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_rate_limited_raises_rate_limited_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    with pytest.raises(AIRateLimitedError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_auth_failure_raises_provider_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid API key"})

    with pytest.raises(AIProviderUnavailableError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_provider_5xx_raises_provider_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(AIProviderUnavailableError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_network_error_raises_provider_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(AIProviderUnavailableError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_malformed_json_raises_invalid_output() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_missing_choices_raises_invalid_output() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "x", "choices": []})

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_content_not_json_raises_invalid_output() -> None:
    payload = {
        **_SUCCESS_PAYLOAD,
        "choices": [{"message": {"content": "not a json object at all"}}],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_schema_validation_failure_raises_invalid_output() -> None:
    bad_content = json.dumps({"summary": "ok", "price_context": "ok"})  # missing required fields
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_extra_field_rejected_by_strict_schema() -> None:
    bad_content = json.dumps({**_FULL_VALID_FIELDS, "recommendation": "BUY"})
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_forbidden_language_rejected() -> None:
    bad_content = json.dumps(
        {**_FULL_VALID_FIELDS, "summary": "На основании данных, Strong Buy для этого актива."}
    )
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_target_price_language_rejected() -> None:
    bad_content = json.dumps(
        {**_FULL_VALID_FIELDS, "price_context": "Аналитики называют target price в $250."}
    )
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_forbidden_language_in_insight_hypothesis_rejected() -> None:
    """Forbidden-language scanning covers the *new* FR-018 fields too,
    not just the original summary/price_context/news_context/risks."""
    bad_content = json.dumps(
        {**_FULL_VALID_FIELDS, "insight_hypothesis": "Рекомендую купить на этой новости."}
    )
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_forbidden_language_in_considerations_rejected() -> None:
    bad_content = json.dumps(
        {**_FULL_VALID_FIELDS, "considerations": ["Целевая цена в районе $300."]}
    )
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_invalid_confidence_value_rejected() -> None:
    """`confidence` must be one of the three documented `ConfidenceLevel`
    values — not a fabricated numeric score (task scope §3)."""
    bad_content = json.dumps({**_FULL_VALID_FIELDS, "confidence": "83.7%"})
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_empty_key_facts_rejected() -> None:
    bad_content = json.dumps({**_FULL_VALID_FIELDS, "key_facts": []})
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_data_freshness_is_never_model_supplied() -> None:
    """Even if the model tried to supply `data_freshness`/`source_data_as_of`,
    the schema forbids extra properties (`additionalProperties: False`) —
    these fields are only ever backend-computed."""
    bad_content = json.dumps({**_FULL_VALID_FIELDS, "data_freshness": "fabricated by the model"})
    payload = {**_SUCCESS_PAYLOAD, "choices": [{"message": {"content": bad_content}}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(AIInvalidOutputError):
        await _gateway(handler).generate_instrument_analysis(_sample_input())


@pytest.mark.anyio
async def test_generate_instrument_analysis_no_secret_leakage_in_error_messages() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(AIProviderUnavailableError) as exc_info:
        await _gateway(handler).generate_instrument_analysis(_sample_input())

    assert _FAKE_API_KEY not in str(exc_info.value)
    assert _FAKE_API_KEY not in repr(exc_info.value)


@pytest.mark.anyio
async def test_generate_instrument_analysis_does_not_log_prompt_or_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    news = (
        NewsHeadlineFact(
            headline="A very specific and identifiable headline text",
            summary="A very specific and identifiable summary text",
            source="TestWire",
            published_at=datetime.now(timezone.utc),
        ),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SUCCESS_PAYLOAD)

    with caplog.at_level(logging.INFO):
        await _gateway(handler).generate_instrument_analysis(_sample_input(news=news))

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert _FAKE_API_KEY not in log_text
    assert "A very specific and identifiable headline text" not in log_text
    assert "A very specific and identifiable summary text" not in log_text
    assert "смешанные" not in log_text  # the model's own summary text is never logged either
    assert "operation=generate_instrument_analysis" in log_text
    assert "ticker=AAPL" in log_text
    assert "provider=xai" in log_text
