"""Scores requirement extraction against hand-written gold labels.

    uv run python -m eval.harness                 # every gold file in eval/gold/
    uv run python -m eval.harness --no-judge      # skip the LLM judge (faster)
    uv run python -m eval.harness --gold eval/gold/synthetic_volunteer_platform.json

For each gold file: split the document into sections, extract requirements section by
section (the same code the app runs), match each extracted requirement to a gold item
by quote overlap, optionally ask the LLM judge whether each description is faithful to
its quote, then write eval/results/<run_id>.json and .md. Token, latency and cost of the
run (extraction and judge calls) are traced to runs/<run_id>.json as usual.

Gold file format (see eval/gold/):
  requirements  must be extracted (recall), with the expected `mandatory` and accepted `categories`
  optional      may be extracted: neither rewarded nor penalised (e.g. "may propose an option")
  forbidden     must NOT be extracted (traps: relaxations, permissions, the client's own goals)
"""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from app.agent import PROMPTS_DIR, extract_requirements, judge_section
from app.config import settings
from app.documents import load_document
from app.quality import quote_overlap
from app.schemas import SectionRequirement
from app.sections import split_sections
from app.telemetry import RunTrace

ROOT = Path(__file__).parent.parent
GOLD_DIR = ROOT / "eval" / "gold"
RESULTS_DIR = ROOT / "eval" / "results"

MATCH_THRESHOLD = 0.6  # share of the shorter quote's words that must appear in the other


def match(predictions: list[SectionRequirement], gold: dict) -> dict[str, tuple[str, str] | None]:
    """Pairs each prediction with at most one gold item, best overlap first.

    Returns {prediction id: (kind, gold id)} where kind is "requirement", "optional" or
    "forbidden", or None when the prediction matched nothing. One-to-one: a second
    prediction of the same gold item is left unmatched (counted as a duplicate later).
    """
    pairs = []
    for kind in ("requirements", "optional", "forbidden"):
        for item in gold.get(kind, []):
            for pred in predictions:
                score = quote_overlap(pred.quote, item["quote"])
                if score >= MATCH_THRESHOLD:
                    pairs.append((score, pred.id, kind, item["id"]))

    result: dict[str, tuple[str, str] | None] = {p.id: None for p in predictions}
    used_gold = set()
    for _, pred_id, kind, gold_id in sorted(pairs, reverse=True):
        if result[pred_id] is None and gold_id not in used_gold:
            result[pred_id] = (kind, gold_id)
            used_gold.add(gold_id)
    return result


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _run_info() -> dict:
    """What produced this result, so scores can be compared across prompt and code changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
        ).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT).stdout)
    except OSError:
        commit, dirty = "unknown", False
    prompt = (PROMPTS_DIR / "extract.md").read_bytes()
    return {
        "git_commit": commit + ("-dirty" if dirty else ""),
        "extract_prompt_sha": hashlib.sha256(prompt).hexdigest()[:8],
        "model": settings.llm_model,
        "judge_model": settings.judge_model or settings.llm_model,
        "temperature": settings.llm_temperature,
    }


def evaluate(gold_path: Path, use_judge: bool) -> dict:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    sections = split_sections(load_document(ROOT / gold["document"]))
    trace = RunTrace(document=Path(gold["document"]).name)

    predictions: list[SectionRequirement] = []
    errors = {}
    for section in sections:
        try:
            predictions.extend(extract_requirements(section, trace))
        except Exception as exc:  # report it; one failing section shouldn't stop the eval
            errors[section.id] = str(exc)
        trace.save()

    verdicts = {}
    if use_judge:  # same call as the live pipeline: one per section
        by_section: dict[str, list[SectionRequirement]] = {}
        for pred in predictions:
            by_section.setdefault(pred.section_id, []).append(pred)
        for section_id, preds in by_section.items():
            try:
                verdicts.update(judge_section(preds, trace))
            except Exception as exc:
                errors[f"judge {section_id}"] = str(exc)
        missing = [p.id for p in predictions if p.id not in verdicts]
        if missing:
            errors["judge returned no verdict"] = ", ".join(missing)
        trace.save()

    matches = match(predictions, gold)
    gold_by_id = {g["id"]: g for kind in ("requirements", "optional", "forbidden") for g in gold.get(kind, [])}
    matched_gold = {m[1] for m in matches.values() if m}

    rows = []
    for pred in predictions:
        m = matches[pred.id]
        if m:
            kind = {"requirements": "tp", "optional": "optional", "forbidden": "forbidden"}[m[0]]
        else:
            # Unmatched: a duplicate if it overlaps a gold item another prediction already took.
            dup = any(quote_overlap(pred.quote, gold_by_id[g]["quote"]) >= MATCH_THRESHOLD for g in matched_gold)
            kind = "duplicate" if dup else "unexpected"
        verdict = verdicts.get(pred.id)
        rows.append({
            **pred.model_dump(),
            "gold_id": m[1] if m else None,
            "match": kind,
            "verdict": verdict.verdict if verdict else None,
            "verdict_reason": verdict.reason if verdict else None,
        })

    tp_rows = [r for r in rows if r["match"] == "tp"]
    fp = sum(r["match"] in ("forbidden", "duplicate", "unexpected") for r in rows)
    required = gold["requirements"]
    precision = _ratio(len(tp_rows), len(tp_rows) + fp)
    recall = _ratio(len(tp_rows), len(required))
    f1 = round(2 * precision * recall / (precision + recall), 3) if precision and recall else 0.0

    mandatory_ok = sum(r["mandatory"] == gold_by_id[r["gold_id"]]["mandatory"] for r in tp_rows)
    category_ok = sum(r["category"] in gold_by_id[r["gold_id"]]["categories"] for r in tp_rows)
    judged = [r for r in rows if r["verdict"]]

    metrics = {
        "gold_requirements": len(required),
        "predicted": len(rows),
        "true_positives": len(tp_rows),
        "false_positives": fp,
        "missed": len(required) - len(tp_rows),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mandatory_accuracy": _ratio(mandatory_ok, len(tp_rows)),
        "category_accuracy": _ratio(category_ok, len(tp_rows)),
        "quote_found_rate": _ratio(sum(r["quote_found"] for r in rows), len(rows)),
        "faithfulness_rate": _ratio(sum(r["verdict"] == "same" for r in judged), len(judged)),
        "verdicts": dict(Counter(r["verdict"] for r in judged)),
        "match_kinds": dict(Counter(r["match"] for r in rows)),
    }

    # Trap scoreboard: a required trap passes when it is extracted with the right
    # `mandatory` and (if judged) a faithful description; a forbidden one when it isn't extracted.
    row_by_gold = {r["gold_id"]: r for r in rows if r["gold_id"]}
    traps = []
    for item in required:
        if not item.get("trap"):
            continue
        r = row_by_gold.get(item["id"])
        if r is None:
            ok, why = False, "not extracted"
        elif r["mandatory"] != item["mandatory"]:
            ok, why = False, f"mandatory={r['mandatory']}, expected {item['mandatory']}"
        elif r["verdict"] and r["verdict"] != "same":
            ok, why = False, f"description {r['verdict']}: {r['verdict_reason']}"
        else:
            ok, why = True, ""
        traps.append({"gold_id": item["id"], "trap": item["trap"], "quote": item["quote"], "passed": ok, "why": why})
    for item in gold.get("forbidden", []):
        r = row_by_gold.get(item["id"])
        traps.append({
            "gold_id": item["id"], "trap": item["trap"], "quote": item["quote"], "passed": r is None,
            "why": f"extracted as {r['id']}: {r['description']}" if r else "",
        })

    usage_by_step = {}
    for call in trace.calls:
        step = usage_by_step.setdefault(call.step, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0})
        step["calls"] += 1
        step["prompt_tokens"] += call.prompt_tokens
        step["completion_tokens"] += call.completion_tokens
        step["latency_s"] = round(step["latency_s"] + call.latency_s, 1)
        step["cost_usd"] = round(step["cost_usd"] + call.cost_usd, 6)

    trace.save()
    return {
        "run_id": trace.run_id,
        "gold_file": str(gold_path.relative_to(ROOT)),
        "document": gold["document"],
        **_run_info(),
        "judge_used": use_judge,
        "sections": len(sections),
        "metrics": metrics,
        "traps": traps,
        "missed": [g for g in required if g["id"] not in matched_gold],
        "predictions": rows,
        "errors": errors,
        "usage": {"total": trace.totals(), "by_step": usage_by_step},
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def to_markdown(result: dict) -> str:
    m = result["metrics"]
    lines = [
        f"# Eval: {Path(result['document']).name}",
        "",
        f"Run `{result['run_id']}` · commit `{result['git_commit']}` · extract prompt `{result['extract_prompt_sha']}` · "
        f"model `{result['model']}` · judge `{result['judge_model'] if result['judge_used'] else 'off'}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision | {_pct(m['precision'])} ({m['true_positives']} of {m['predicted']} predictions; {m['false_positives']} false positives) |",
        f"| Recall | {_pct(m['recall'])} ({m['true_positives']} of {m['gold_requirements']} gold requirements) |",
        f"| F1 | {m['f1']:.2f} |",
        f"| Mandatory accuracy (on matches) | {_pct(m['mandatory_accuracy'])} |",
        f"| Category accuracy (on matches) | {_pct(m['category_accuracy'])} |",
        f"| Quotes found in source | {_pct(m['quote_found_rate'])} |",
        f"| Faithful descriptions (judge) | {_pct(m['faithfulness_rate'])} {m['verdicts'] or ''} |",
        "",
        "## Traps",
        "",
        "| Gold | Trap | Result | Why |",
        "|---|---|---|---|",
    ]
    for t in result["traps"]:
        lines.append(f"| {t['gold_id']} | {t['trap']} | {'pass' if t['passed'] else '**FAIL**'} | {t['why']} |")

    by_trap = Counter()
    passed = Counter()
    for t in result["traps"]:
        by_trap[t["trap"]] += 1
        passed[t["trap"]] += t["passed"]
    lines += ["", "Passed by trap type: " + ", ".join(f"{k} {passed[k]}/{n}" for k, n in sorted(by_trap.items())), ""]

    if result["missed"]:
        lines += ["## Missed requirements", ""]
        lines += [f"- {g['id']}: \"{g['quote']}\"" for g in result["missed"]]
        lines.append("")

    wrong = [r for r in result["predictions"] if r["match"] in ("forbidden", "duplicate", "unexpected")]
    if wrong:
        lines += ["## False positives", ""]
        lines += [f"- {r['id']} ({r['match']}{', ' + r['gold_id'] if r['gold_id'] else ''}): {r['description']}" for r in wrong]
        lines.append("")

    if result["errors"]:
        lines += ["## Errors", ""] + [f"- {k}: {v}" for k, v in result["errors"].items()] + [""]

    u = result["usage"]["total"]
    lines += [
        "## Usage",
        "",
        "| Step | Calls | Prompt tokens | Completion tokens | Latency (s) | Est. cost (USD) |",
        "|---|---|---|---|---|---|",
    ]
    for step, s in result["usage"]["by_step"].items():
        lines.append(f"| {step} | {s['calls']} | {s['prompt_tokens']:,} | {s['completion_tokens']:,} | {s['latency_s']} | {s['cost_usd']:.4f} |")
    lines.append(f"| **total** | {u['calls']} | {u['prompt_tokens']:,} | {u['completion_tokens']:,} | {u['latency_s']} | {u['cost_usd']:.4f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gold", type=Path, action="append", help="gold file(s); default: all in eval/gold/")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM faithfulness judge")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    for gold_path in args.gold or sorted(GOLD_DIR.glob("*.json")):
        result = evaluate(gold_path.resolve(), use_judge=not args.no_judge)
        name = f"{result['run_id']}_{gold_path.stem}"
        (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        report = to_markdown(result)
        (RESULTS_DIR / f"{name}.md").write_text(report, encoding="utf-8")
        print(report)
        print(f"Saved eval/results/{name}.json and .md; trace in runs/{result['run_id']}.json")


if __name__ == "__main__":
    main()
