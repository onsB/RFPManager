"""Quality checks that need no gold labels, so they run on every real run (online evaluation).

The offline harness (eval/harness.py) scores extraction against gold labels on a test
brief; these checks score every document a user uploads, where no gold exists:
  - quote grounding: the quote appears in the section text (set in agent.extract_requirements)
  - faithfulness: the LLM judge says the description states the same content as its quote
  - duplicates: two requirements quote the same text (often from overlapping sections)
  - synthesis grounding: no made-up requirement ids, every mandatory requirement planned
"""

import re
from collections import Counter

from app.agent import normalize_text
from app.schemas import RFPSummary, SectionRequirement
from app.telemetry import RunTrace

DUPLICATE_THRESHOLD = 0.6  # same threshold the harness uses to match a prediction to a gold item

# Function words, plus words every requirement shares (modal verbs, "supplier"), so the
# overlap depends on what the requirement is about. "not" is kept: it changes the meaning.
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "by", "be", "is", "are", "with", "all", "any",
    "must", "shall", "should", "may", "will", "need", "supplier",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9£]+", normalize_text(text)) if w not in STOPWORDS}


def quote_overlap(a: str, b: str) -> float:
    """Share of the shorter quote's content words that appear in the other quote.

    Dividing by the shorter quote lets a short quote ("two references from similar
    projects") match the longer sentence it comes from, and vice versa.
    """
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def mark_duplicates(new: list[SectionRequirement], earlier: list[SectionRequirement]) -> None:
    """Sets `duplicate_of` on each new requirement whose quote overlaps an earlier one."""
    for req in new:
        for other in earlier:
            if quote_overlap(req.quote, other.quote) >= DUPLICATE_THRESHOLD:
                req.duplicate_of = other.id
                break
        earlier = [*earlier, req]  # later requirements in the same section are checked too


def needs_review(req: SectionRequirement) -> bool:
    return not req.quote_found or req.duplicate_of is not None or req.verdict not in (None, "same")


def quality_report(
    requirements: list[SectionRequirement],
    summary: RFPSummary | None,
    failed_sections: int,
    skipped_sections: int,
    trace: RunTrace,
    review_log: list[dict] | None = None,
) -> dict:
    """Run-level quality numbers, shown at the end of a run and saved in its trace.

    `truncated_calls` counts calls that hit max_tokens (treated as looping);
    `reasoning_tokens` should stay ~0 while thinking is off (the critic thinks, so not for it).
    Review fields: `review_history` has each round's issues by kind, so round 1 (the draft)
    against the last round shows what the critic loop changed. `approved` is None when
    the review is off or failed.
    """
    review_log = review_log or []
    last_ok = next((r for r in reversed(review_log) if not r.get("error")), None)
    review = {
        "review_rounds": len(review_log),
        "approved": last_ok["approved"] if last_ok else None,
        "review_history": review_log,
        "agent_steps": sum(1 for c in trace.calls if c.step == "critic"),
        # Tools the critic chose to call; code also runs check_coverage and get_key_facts for it.
        "tool_calls": sum(1 for t in trace.tool_calls if t.agent == "critic"),
        "tool_errors": sum(1 for t in trace.tool_calls if t.error),
        "tools_used": dict(Counter(t.name for t in trace.tool_calls if t.agent == "critic")),
    }
    judged = [r for r in requirements if r.verdict]
    n = len(requirements)
    return {
        "requirements": n,
        "quote_found_rate": round(sum(r.quote_found for r in requirements) / n, 3) if n else None,
        "judged": len(judged),
        "faithfulness_rate": round(sum(r.verdict == "same" for r in judged) / len(judged), 3) if judged else None,
        "verdicts": dict(Counter(r.verdict for r in judged)),
        "duplicates": sum(r.duplicate_of is not None for r in requirements),
        "needs_review": [r.id for r in requirements if needs_review(r)],
        "failed_sections": failed_sections,
        "skipped_sections": skipped_sections,
        "sections_sent": sum(1 for c in trace.calls if c.step == "extract"),
        "truncated_calls": [f"{c.step} {c.section_id or ''}".strip() for c in trace.calls if c.finish_reason == "length"],
        "reasoning_tokens": sum(c.reasoning_tokens for c in trace.calls),
        "unknown_ids": len(summary.unknown_ids) if summary else None,
        "uncovered_mandatory": len(summary.uncovered_mandatory) if summary else None,
        **review,
    }
