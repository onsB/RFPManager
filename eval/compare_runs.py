"""Compares run traces side by side: cost, speed and online-eval quality.

    uv run python -m eval.compare_runs 20261101-190551 20261102-101500
    uv run python -m eval.compare_runs runs/a.json runs/b.json --labels v1 v2

Reads runs/<run_id>.json (written by every pipeline run) and prints a Markdown table,
ready to paste into DECISIONS.md. Older traces lack some fields; those show "n/a".
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
