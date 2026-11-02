"""Compares run traces side by side: cost, speed and online-eval quality.

    uv run python -m eval.compare_runs 20261101-190551 20261102-101500
    uv run python -m eval.compare_runs runs/a.json runs/b.json --labels v1 v2

Reads runs/<run_id>.json (written by every pipeline run) and prints a Markdown table,
ready to paste into DECISIONS.md. Older traces lack some fields; those show "n/a".

Critic A/B: compare a run with AGENT_REVIEW=false against one with it on. The "on" run
also holds its own before/after: round 1 reviews the draft, the last round the final brief.
"""

import argparse
import json
from pathlib import Path

RUNS_DIR = Path(__file__).parent.parent / "runs"


def _load(ref: str) -> dict:
    path = Path(ref) if ref.endswith(".json") else RUNS_DIR / f"{ref}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _row(trace: dict) -> dict[str, str]:
    t, q, calls = trace["totals"], trace.get("quality") or {}, trace["calls"]
    n = q.get("requirements")

    def pct(v):
        return "n/a" if v is None else f"{v:.0%}"

    review = q.get("needs_review")
    history = [r for r in q.get("review_history", []) if not r.get("error")]

    def issues(rnd: dict | None) -> str:
        if rnd is None:
            return "n/a"
        kinds = rnd["issues_by_kind"]
        return f"{sum(kinds.values())} " + (str(kinds) if kinds else "")

    agent_calls = [c for c in calls if c["step"] in ("critic", "revise")]
    agent_s = sum(c["latency_s"] for c in agent_calls)
    agent_on = "review_rounds" in q and q["review_rounds"] > 0
    return {
        "Document": trace["document"],
        "Sections sent to LLM": str(sum(c["step"] == "extract" for c in calls)),
        "Sections skipped (boilerplate)": str(q.get("skipped_sections", "n/a")),
        "Requirements extracted": str(n if n is not None else "n/a"),
        "LLM calls": str(t["calls"]),
        "Total tokens": f"{t['prompt_tokens'] + t['completion_tokens']:,}",
        "LLM time (s)": f"{t['latency_s']:,}",
        "Est. cost (USD)": f"{t['cost_usd']:.4f}",
        "Calls hitting max_tokens": str(len(q["truncated_calls"])) if "truncated_calls" in q else "n/a",
        "Reasoning tokens": str(q.get("reasoning_tokens", "n/a")),
        "Quotes found in source": pct(q.get("quote_found_rate")),
        "Judged faithful": pct(q.get("faithfulness_rate")),
        "Duplicates": str(q.get("duplicates", "n/a")),
        "Need review": f"{len(review)} ({len(review) / n:.0%})" if review is not None and n else "n/a",
        "Failed sections": str(q.get("failed_sections", "n/a")),
        "Made-up ids in summary": str(q.get("unknown_ids", "n/a")),
        "Mandatory reqs not planned": str(q.get("uncovered_mandatory", "n/a")),
        # Critic loop. Round 1 reviews the draft (= what AGENT_REVIEW=false outputs), the last
        # round the final brief, so one trace holds its own before/after on the same extraction.
        "Review rounds": str(q["review_rounds"]) if "review_rounds" in q else "n/a",
        "Final brief approved": str(q.get("approved")) if agent_on else "n/a",
        "Critic issues on the draft (round 1)": issues(history[0] if history else None),
        "Critic issues, last round": issues(history[-1] if len(history) > 1 else None),
        "Agent steps / tool calls": f"{q['agent_steps']} / {q['tool_calls']}" if agent_on else "n/a",
        "Agent time (s) / tokens": (
            f"{agent_s:,.1f} / {sum(c['prompt_tokens'] + c['completion_tokens'] for c in agent_calls):,}"
            if agent_on else "n/a"
        ),
        "LLM time without agent (s)": f"{t['latency_s'] - agent_s:,.1f}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", help="run ids (runs/<id>.json) or paths to trace files")
    parser.add_argument("--labels", nargs="+", help="column labels, e.g. v1 v2 (default: run ids)")
    args = parser.parse_args()

    traces = [_load(r) for r in args.runs]
    labels = args.labels or [t["run_id"] for t in traces]
    rows = [_row(t) for t in traces]
    print("| Metric | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    for key in rows[0]:
        print(f"| {key} | " + " | ".join(r[key] for r in rows) + " |")


if __name__ == "__main__":
    main()
