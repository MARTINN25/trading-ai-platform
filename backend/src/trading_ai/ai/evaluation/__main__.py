"""CLI entry point for the AI quality evaluation harness (task scope §11).

    python -m trading_ai.ai.evaluation                    # offline, all cases (default)
    python -m trading_ai.ai.evaluation --offline
    python -m trading_ai.ai.evaluation --offline --case normal-bullish-day
    python -m trading_ai.ai.evaluation --live              # live smoke: 3 representative cases
    python -m trading_ai.ai.evaluation --live --case normal-bullish-day
    python -m trading_ai.ai.evaluation --live --all-cases  # full dataset, live — explicit, costs credits

`argparse` (stdlib) — no Typer/Click dependency for three flags (task
scope §11: "не добавлять Typer/Click dependency только ради этого").

Nothing in this module runs at import time; `main()` only executes
under `if __name__ == "__main__"` below, and the live path is only
reached when the caller explicitly passed `--live` (task scope §16).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from trading_ai.ai.evaluation.dataset import DATASET
from trading_ai.ai.evaluation.report import format_report
from trading_ai.ai.evaluation.runner import find_case, run_live, run_offline
from trading_ai.ai.evaluation.types import EvaluationCase
from trading_ai.ai.gateway import XAIGateway
from trading_ai.config import get_settings

# Representative default for a bare `--live` (task scope §8, §15): one
# normal case, one degraded/missing-data case, one prompt-injection
# case — not the full dataset.
_LIVE_SMOKE_CASE_IDS = ("normal-bullish-day", "quote-only-degraded", "prompt-injection-headline")


def _select_cases(
    case_id: str | None, default_ids: tuple[str, ...] | None
) -> list[EvaluationCase]:
    if case_id is not None:
        case = find_case(case_id)
        if case is None:
            known = ", ".join(c.case_id for c in DATASET)
            print(f"Unknown case id {case_id!r}. Known ids: {known}", file=sys.stderr)
            sys.exit(2)
        return [case]
    if default_ids is not None:
        return [c for c in DATASET if c.case_id in default_ids]
    return list(DATASET)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m trading_ai.ai.evaluation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="run offline (default, no network calls)")
    mode.add_argument("--live", action="store_true", help="run against the real xAI provider (opt-in, costs credits)")
    parser.add_argument("--case", metavar="CASE_ID", help="run only this one case")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        help="with --live, run the FULL dataset instead of the 3-case smoke subset",
    )
    args = parser.parse_args()

    if not args.live:
        cases = _select_cases(args.case, None)
        results = run_offline(cases)
        print(format_report(results))
        return 0 if all(result.passed for result in results) else 1

    # --live from here on.
    settings = get_settings()
    if settings.llm_api_key is None:
        print(
            "TRADING_AI_LLM_API_KEY is not set — live evaluation requires a "
            "real xAI key in backend/.env. Aborting before making any call.",
            file=sys.stderr,
        )
        return 2

    if args.case is not None:
        cases = _select_cases(args.case, None)
    elif args.all_cases:
        cases = list(DATASET)
    else:
        cases = _select_cases(None, _LIVE_SMOKE_CASE_IDS)

    print(
        f"About to make {len(cases)} real xAI call(s) using model={settings.llm_model!r}. "
        "This spends xAI credits.",
        file=sys.stderr,
    )

    gateway = XAIGateway(api_key=settings.llm_api_key, model=settings.llm_model)
    results = asyncio.run(run_live(cases, gateway, model=settings.llm_model))
    print(format_report(results, model=settings.llm_model))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
