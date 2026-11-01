import time
from collections.abc import Iterator

from app.agent import extract_requirements, synthesize_summary
from app.sections import split_sections
from app.telemetry import RunTrace


def run_pipeline(text: str, document: str, section_ids: list[str] | None = None) -> Iterator[dict]:
    """Runs the whole analysis of one document, yielding an event after each step.

    Steps: split into sections -> extract requirements per section -> synthesize the
    summary from all requirements. Events (plain dicts, JSON-ready):
      {"type": "sections"}  the sections found
      {"type": "section"}   one per section, with its requirements and LLM usage
      {"type": "summary"}   overview, approach, risks and the checks
      {"type": "done"}      run totals and the trace file name
    The CLI prints these events and the API streams them to the browser.
    """
    sections = split_sections(text)  # also merges small and splits long sections
    trace = RunTrace(document=document)
    yield {
        "type": "sections",
        "sections": [{"id": s.id, "title": s.breadcrumb, "chars": s.char_count} for s in sections],
    }

    all_requirements = []
    for section in sections:
        if section_ids and section.id not in section_ids:
            continue

        start = time.perf_counter()
        calls_before = len(trace.calls)
        try:
            requirements = extract_requirements(section, trace)
            error = None
        except Exception as exc:  # one failing section should not stop the run
            requirements, error = [], str(exc)
        all_requirements.extend(requirements)

        # Save before yielding: if the browser disconnects, the generator stops at the yield.
        trace.save()
        yield {
            "type": "section",
            "id": section.id,
            "title": section.breadcrumb,
            "seconds": round(time.perf_counter() - start, 1),
            "requirements": [r.model_dump() for r in requirements],
            "error": error,
            # A failed call may not be recorded; don't report the previous section's usage.
            "usage": trace.calls[-1].model_dump() if len(trace.calls) > calls_before else None,
        }

    try:
        summary = synthesize_summary(sections, all_requirements, trace).model_dump()
        error = None
    except Exception as exc:
        summary, error = None, str(exc)
    trace.save()
    yield {"type": "summary", "summary": summary, "error": error}

    path = trace.save()
    yield {"type": "done", "totals": trace.totals(), "run_id": trace.run_id, "trace_file": path.name}
