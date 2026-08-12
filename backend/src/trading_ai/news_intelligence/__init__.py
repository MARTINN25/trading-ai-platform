"""News Intelligence — Phase 2A.

Turns the raw, per-ticker news feed (`market_data.news_gateway`) into a
curated, classified, Russian-summarized feed (FR-064, UJ-034). Not a
`MODULE_BOUNDARIES.md`-listed module (that document has no `news`
boundary — news is currently a `market_data` concern, see
`TARGET_INTELLIGENCE_CONTEXT.md` §2.5); this package follows the same
precedent as `insights`/`evaluations`/`journal`: a small, focused
package for one concern, not the full aspirational module set.

Owns: deterministic preprocessing (`preprocessing.py`), the persisted
cache of already-enriched items (`models.py`/`repository.py`), and the
orchestrating use case (`use_cases.py`). Does not own raw news fetching
(`market_data.news_gateway`) or the LLM call itself
(`ai.gateway.XAIGateway.generate_news_intelligence`) — it only
coordinates them, the same relationship `ai.use_cases.
GenerateInstrumentAnalysis` already has with `market_data`.
"""

from __future__ import annotations
