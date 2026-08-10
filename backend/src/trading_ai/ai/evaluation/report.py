"""Human-review report formatting (task scope §10).

Not a dashboard — a plain-text summary meant for a person to read in a
terminal. Never includes the full prompt, the full model response, or
any raw provider payload; `CheckResult.detail` strings are short,
hand-generated fragments (e.g. which forbidden phrase matched), never
a dump of `analysis.summary`/`price_context`/`news_context` (task
scope §10, §17, §18).
"""

from __future__ import annotations

from trading_ai.ai.evaluation.types import EvaluationResult

_SAFETY_CATEGORIES = ("safety", "injection")


def format_report(
    results: list[EvaluationResult],
    *,
    model: str | None = None,
) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"Case: {result.case_id}")
        if result.generation_error is not None:
            lines.append(f"ERROR generation_failed ({result.generation_error})")
        else:
            for check in result.checks:
                status = "PASS" if check.passed else "FAIL"
                suffix = f" ({check.detail})" if check.detail and not check.passed else ""
                lines.append(f"{status} {check.name}{suffix}")
        if result.latency_ms is not None:
            lines.append(f"latency_ms={result.latency_ms:.0f}")
        lines.append("")

    total = len(results)
    passed = sum(1 for result in results if result.passed)
    safety_violations = sum(
        1
        for result in results
        for check in result.checks
        if not check.passed and check.category in _SAFETY_CATEGORIES
    )

    lines.append("Summary:")
    if results and results[0].source == "live":
        lines.append(f"mode=live model={model or 'unknown'} cases={total}")
    else:
        lines.append("mode=offline")
    lines.append(f"{passed}/{total} cases passed")
    lines.append(f"{safety_violations} safety violations")

    token_reports = [
        result
        for result in results
        if result.input_tokens is not None or result.output_tokens is not None
    ]
    if token_reports:
        total_input = sum(r.input_tokens or 0 for r in token_reports)
        total_output = sum(r.output_tokens or 0 for r in token_reports)
        lines.append(f"total_input_tokens={total_input} total_output_tokens={total_output}")

    return "\n".join(lines)
