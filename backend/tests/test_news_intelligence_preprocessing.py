"""Deterministic preprocessing tests (Phase 2A, task scope §17):
headline normalization, exact/near dedup, ticker/company mention."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_ai.market_data.types import InstrumentNewsItem
from trading_ai.news_intelligence.preprocessing import (
    dedup_key,
    deduplicate_items,
    mentions_company_name,
    mentions_ticker,
    normalize_headline_for_dedup,
)

_T = datetime(2026, 8, 10, 15, 0, 0, tzinfo=timezone.utc)


def _item(
    item_id: str,
    headline: str,
    *,
    source: str = "Reuters",
    published_at: datetime = _T,
    summary: str | None = None,
) -> InstrumentNewsItem:
    return InstrumentNewsItem(
        id=item_id,
        ticker="AAPL",
        headline=headline,
        source=source,
        published_at=published_at,
        url="https://example.com/a",
        summary=summary,
    )


def test_normalize_headline_lowercases_and_strips_punctuation() -> None:
    normalized = normalize_headline_for_dedup("Apple's Q3 Earnings: Beat Estimates!")
    assert normalized == "apple s q3 earnings beat estimates"


def test_normalize_headline_collapses_whitespace() -> None:
    assert normalize_headline_for_dedup("Apple   unveils    new   product") == "apple unveils new product"


def test_normalize_headline_strips_known_syndication_prefix() -> None:
    assert normalize_headline_for_dedup("Reuters: Apple unveils new product") == "apple unveils new product"
    assert normalize_headline_for_dedup("(Reuters) Apple unveils new product") == "apple unveils new product"


def test_dedup_key_differs_by_date_even_with_same_headline_and_source() -> None:
    first = _item("1", "Apple unveils new product", published_at=_T)
    second = _item("2", "Apple unveils new product", published_at=_T + timedelta(days=7))
    assert dedup_key(first) != dedup_key(second)


def test_dedup_key_same_for_syndicated_variants_same_day() -> None:
    first = _item("1", "Apple unveils new product line")
    second = _item("2", "Reuters: Apple unveils new product line", published_at=_T + timedelta(hours=2))
    assert dedup_key(first) == dedup_key(second)


def test_deduplicate_items_collapses_near_duplicates() -> None:
    first = _item("1", "Apple unveils new product line", summary=None)
    second = _item("2", "Reuters: Apple unveils new product line", summary="Full summary text.")
    result = deduplicate_items([first, second])
    assert len(result) == 1
    # The surviving item is the one carrying a summary, not necessarily
    # the first-seen — more information is preferred over less.
    assert result[0].id == "2"
    assert result[0].summary == "Full summary text."


def test_deduplicate_items_keeps_genuinely_different_stories() -> None:
    first = _item("1", "Apple unveils new product line")
    second = _item("2", "Apple reports quarterly earnings")
    result = deduplicate_items([first, second])
    assert len(result) == 2


def test_deduplicate_items_drops_exact_id_repeat() -> None:
    item = _item("1", "Apple unveils new product line")
    result = deduplicate_items([item, item])
    assert len(result) == 1


def test_deduplicate_items_preserves_input_order_for_survivors() -> None:
    first = _item("1", "Apple reports quarterly earnings", published_at=_T)
    second = _item("2", "Apple unveils new product line", published_at=_T - timedelta(hours=1))
    result = deduplicate_items([first, second])
    assert [item.id for item in result] == ["1", "2"]


def test_deduplicate_items_empty_input_returns_empty_list() -> None:
    assert deduplicate_items([]) == []


def test_mentions_ticker_matches_word_boundary_case_insensitive() -> None:
    assert mentions_ticker("AAPL shares rose today", "aapl") is True
    assert mentions_ticker("aapl shares rose today", "AAPL") is True


def test_mentions_ticker_does_not_match_substring_inside_another_word() -> None:
    # "AAPLE" (typo/unrelated) must not count as a mention of "AAPL".
    assert mentions_ticker("AAPLE unrelated word", "AAPL") is False


def test_mentions_ticker_false_for_empty_ticker() -> None:
    assert mentions_ticker("Some headline", "") is False


def test_mentions_company_name_word_boundary_case_insensitive() -> None:
    assert mentions_company_name("Apple Inc reports strong quarter", "apple inc") is True


def test_mentions_company_name_returns_false_when_name_unavailable() -> None:
    assert mentions_company_name("Apple Inc reports strong quarter", None) is False


def test_mentions_company_name_false_when_not_present() -> None:
    assert mentions_company_name("Rocket Lab launches satellite", "Apple Inc") is False
