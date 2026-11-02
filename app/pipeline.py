import time
from collections.abc import Iterator

from app.agent import extract_requirements, judge_section, synthesize_summary
from app.config import settings
from app.facts import find_deadline
from app.quality import mark_duplicates, quality_report
from app.schemas import SectionRequirement
from app.sections import is_boilerplate, split_sections
from app.telemetry import RunTrace


def run_pipeline(text: str, document: str, section_ids: list[str] | None = None) -> Iterator[dict]:
    """Runs the whole analysis of one document, yielding an event after each step.

    Steps: split into sections -> extract requirements per section (and flag duplicates)
    -> synthesize the summary -> judge each section's requirements (online evaluation).
    The judge runs after the summary so the brief is on screen while the review flags
    fill in; nothing before it uses the verdicts. Events (plain dicts, JSON-ready):
      {"type": "sections"}  the sections found
      {"type": "section"}   one per section, with its requirements and LLM usage
                            ("skipped": true for boilerplate sections, not sent to the LLM)
      {"type": "summary"}   overview, approach, risks and the checks
      {"type": "judging"}   the judge is starting, with the number of sections to judge
      {"type": "verdicts"}  one per judged section: {requirement id: verdict and reason}
      {"type": "done"}      run totals, quality report and the trace file name
    The CLI prints these events and the API streams them to the browser.
    """
    sections = split_sections(text)  # also merges small and splits long sections
    trace = RunTrace(document=document)
    yield {
        "type": "sections",
        "sections": [
            {"id": s.id, "title": s.breadcrumb, "chars": s.char_count, "skipped": is_boilerplate(s)}
            for s in sections
        ],
    }

    all_requirements: list[SectionRequirement] = []
    failed_sections = skipped_sections = 0
    for section in sections:
        if section_ids and section.id not in section_ids:
            continue
        if is_boilerplate(section):
            skipped_sections += 1
            yield {
                "type": "section", "id": section.id, "title": section.breadcrumb, "seconds": 0,
                "requirements": [], "error": None, "usage": None, "skipped": True,
            }
            continue

        start = time.perf_counter()
        calls_before = len(trace.calls)
        try:
            requirements = extract_requirements(section, trace)
            error = None
        except Exception as exc:  # one failing section should not stop the run
            requirements, error = [], str(exc)
            failed_sections += 1
        mark_duplicates(requirements, all_requirements)
        all_requirements.extend(requirements)

        # A failed call may not be recorded; don't report the previous section's usage.
        extract_call = next((c for c in trace.calls[calls_before:] if c.step == "extract"), None)

        # Save before yielding: if the browser disconnects, the generator stops at the yield.
        trace.save()
        yield {
            "type": "section",
            "id": section.id,
            "title": section.breadcrumb,
            "seconds": round(time.perf_counter() - start, 1),
            "requirements": [r.model_dump() for r in requirements],
            "error": error,
            "usage": extract_call.model_dump() if extract_call else None,
            "skipped": False,
        }

    try:
        summary = synthesize_summary(sections, all_requirements, trace)
        # Found by code in the full text, so the LLM can't drop it (see DECISIONS.md, Key Dates).
        summary.deadline = find_deadline(sections)
        error = None
    except Exception as exc:
        summary, error = None, str(exc)
    trace.save()
    yield {"type": "summary", "summary": summary.model_dump() if summary else None, "error": error}

    if settings.live_judge:
        yield from _judge_sections(all_requirements, trace)

    trace.quality = quality_report(all_requirements, summary, failed_sections, skipped_sections, trace)
    path = trace.save()
    yield {
        "type": "done",
        "totals": trace.totals(),
        "quality": trace.quality,
        "run_id": trace.run_id,
        "trace_file": path.name,
    }


def _judge_sections(requirements: list[SectionRequirement], trace: RunTrace) -> Iterator[dict]:
    """Asks the judge about each section's requirements (one call per section), in place."""
    by_section: dict[str, list[SectionRequirement]] = {}
    for req in requirements:
        by_section.setdefault(req.section_id, []).append(req)
    yield {"type": "judging", "sections": len(by_section)}

    for i, (section_id, reqs) in enumerate(by_section.items(), start=1):
        try:
            verdicts, error = judge_section(reqs, trace), None
        except Exception as exc:  # a failed judgement leaves the requirements unjudged, not lost
            verdicts, error = {}, str(exc)
        for req in reqs:
            if req.id in verdicts:
                req.verdict, req.verdict_reason = verdicts[req.id].verdict, verdicts[req.id].reason
            else:
                req.verdict_reason = f"judge failed: {error}" if error else "judge returned no verdict"

        trace.save()
        yield {
            "type": "verdicts",
            "section_id": section_id,
            "done": i,
            "total": len(by_section),
            "verdicts": {r.id: {"verdict": r.verdict, "reason": r.verdict_reason} for r in reqs},
            "error": error,
        }
