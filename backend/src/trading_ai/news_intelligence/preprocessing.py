"""Deterministic preprocessing — runs before any LLM call (`ENGINEERING_PRINCIPLES.md`,
points 54-55: filter/dedup before the model, never after).

Every function here is pure and network-free. `deduplicate_items` is the
only stateful-looking one (it decides an order among duplicates), and
even that is a pure function of its input list.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from trading_ai.market_data.types import InstrumentNewsItem

# Collapses whitespace and strips a small set of common wire-service
# syndication prefixes/suffixes so two outlets running the same story
# with slightly different framing still normalize to the same key
# (task scope §9: "near-duplicate syndicated versions"). Not an attempt
# at full semantic dedup — that would need the LLM, which §9 says to
# avoid for this step; this is intentionally a cheap, deterministic
# approximation.
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SYNDICATION_PREFIXES = (
    "reuters:",
    "reuters -",
    "(reuters)",
    "bloomberg:",
    "update:",
    "update 1-",
    "update 2-",
    "breaking:",
    "exclusive:",
)


def normalize_headline_for_dedup(headline: str) -> str:
    """Lowercased, punctuation-stripped, whitespace-collapsed headline —
    used only as a dedup key, never displayed to the user."""
    text = headline.strip().lower()
    for prefix in _SYNDICATION_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    text = _PUNCTUATION_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def dedup_key(item: InstrumentNewsItem) -> str:
    """A near-duplicate key: normalized headline + source + calendar
    date (not full timestamp — two syndicated copies of the same story
    published minutes apart on the same day are still the same story;
    two genuinely different stories a week apart from the same source
    with a coincidentally similar headline are not treated as the same
    key because the date differs)."""
    return f"{item.source.strip().lower()}|{item.published_at.date().isoformat()}|{normalize_headline_for_dedup(item.headline)}"


def deduplicate_items(items: Sequence[InstrumentNewsItem]) -> list[InstrumentNewsItem]:
    """Collapses near-duplicates, keeping the first-seen item per key
    that has a `summary` when one with a summary exists, otherwise the
    first-seen item — never silently drops a story with more
    information in favor of one with less. Input order (newest-first,
    per `FinnhubNewsGateway`) is preserved for the surviving items."""
    best_by_key: dict[str, InstrumentNewsItem] = {}
    order: list[str] = []
    seen_ids: set[str] = set()
    for item in items:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        key = dedup_key(item)
        if key not in best_by_key:
            best_by_key[key] = item
            order.append(key)
        elif best_by_key[key].summary is None and item.summary is not None:
            best_by_key[key] = item
    return [best_by_key[key] for key in order]


_WORD_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _word_boundary_pattern(term: str) -> re.Pattern[str]:
    pattern = _WORD_BOUNDARY_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[term] = pattern
    return pattern


def mentions_ticker(text: str, ticker: str) -> bool:
    """Word-boundary, case-insensitive match — a bonus deterministic
    signal, not a hard filter (Finnhub's `company-news` endpoint is
    already ticker-scoped, so most items already have some association
    even without this matching literally, task scope §5)."""
    if not ticker:
        return False
    return bool(_word_boundary_pattern(ticker).search(text))


def mentions_company_name(text: str, company_name: str | None) -> bool:
    """Best-effort ("where reliable", task scope §5) — `company_name`
    is optional (see `use_cases.py`'s company-name resolver) and this
    returns `False`, never a guess, when it isn't available."""
    if not company_name:
        return False
    return bool(_word_boundary_pattern(company_name).search(text))
