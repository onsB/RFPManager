import time
from collections.abc import Iterator

from app.agent import extract_requirements, judge_section, synthesize_summary
from app.config import settings
from app.quality import mark_duplicates, quality_report
from app.schemas import SectionRequirement
from app.sections import is_boilerplate, split_sections
from app.telemetry import RunTrace


def run_pipeline(text: str, document: str, section_ids: list[str] | None = None) -> Iterator[dict]:
    """Runs the whole analysis of one document, yielding an event after each step.

    Steps: split into sections -> extract requirements per section (then judge each one
    and flag duplicates: online evaluation) -> synthesize the summary from all
    requirements. Events (plain dicts, JSON-ready):
      {"type": "sections"}  the sections found
      {"type": "section"}   one per section, with its requirements and LLM usage
                            ("skipped": true for boilerplate sections, not sent to the LLM)
      {"type": "summary"}   overview, approach, risks and the checks
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
        _evaluate_online(requirements, all_requirements, trace)
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
        error = None
    except Exception as exc:
        summary, error = None, str(exc)
    trace.save()
    yield {"type": "summary", "summary": summary.model_dump() if summary else None, "error": error}

    trace.quality = quality_report(all_requirements, summary, failed_sections, skipped_sections, trace)
    path = trace.save()
    yield {
        "type": "done",
        "totals": trace.totals(),
        "quality": trace.quality,
        "run_id": trace.run_id,
        "trace_file": path.name,
    }


def _evaluate_online(
    requirements: list[SectionRequirement],
    earlier: list[SectionRequirement],
    trace: RunTrace,
) -> None:
    """Flags duplicates and asks the judge about the section's new requirements, in place."""
    mark_duplicates(requirements, earlier)
    if not settings.live_judge or not requirements:
        return
    try:
        verdicts = judge_section(requirements, trace)
    except Exception as exc:  # a failed judgement leaves the requirements unjudged, not lost
        for req in requirements:
            req.verdict_reason = f"judge failed: {exc}"
        return
    for req in requirements:
        if req.id in verdicts:
            req.verdict, req.verdict_reason = verdicts[req.id].verdict, verdicts[req.id].reason
        else:
            req.verdict_reason = "judge returned no verdict"
