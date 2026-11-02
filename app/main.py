import sys
from pathlib import Path

from app.documents import load_document
from app.pipeline import run_pipeline

# Edit these to test from VS Code: press Run (or F5), no terminal arguments needed.
RFP_PATH = Path(__file__).parent.parent / "inputs" / "InvitationtoTender_CommunitiesofPracticeDevelopment.pdf"
SECTION_IDS: list[str] = ["S12"]  # empty list = run every section


def print_section(event: dict) -> None:
    if event.get("skipped"):
        print(f"## [{event['id']}] {event['title']}  (skipped: boilerplate)\n")
        return
    print(f"## [{event['id']}] {event['title']}  ({len(event['requirements'])} reqs, {event['seconds']}s)")
    if event["error"]:
        print(f"  ERROR: {event['error']}")
    for req in event["requirements"]:
        found = "ok " if req["quote_found"] else "NOT FOUND"
        must = "must" if req["mandatory"] else "    "
        print(f"  {req['id']} [{found}] {must} {req['category']:<14} {req['description']}")
        print(f"           quote: \"{req['quote']}\"")
        if req["verdict"] not in (None, "same"):
            print(f"           judge: {req['verdict']}: {req['verdict_reason']}")
        if req["duplicate_of"]:
            print(f"           duplicate of {req['duplicate_of']}")
    print()


def print_summary(event: dict) -> None:
    if event["error"]:
        print(f"Summary failed: {event['error']}\n")
        return
    s = event["summary"]
    print(f"# {s['project_title']} ({s['client']})\n\n{s['overview']}\n")
    print("Approach:")
    for phase in s["approach"]:
        print(f"  - {phase['phase']}: {phase['description']}  {phase['requirement_ids']}")
    print("Risks:")
    for risk in s["risks"]:
        print(f"  - [{risk['severity']}] {risk['description']} -> {risk['mitigation']}  {risk['requirement_ids']}")
    print(f"\nUnknown ids cited: {s['unknown_ids'] or 'none'}")
    print(f"Mandatory requirements not covered: {s['uncovered_mandatory'] or 'none'}\n")


def print_quality(q: dict) -> None:
    def pct(v):
        return "n/a" if v is None else f"{v:.0%}"

    print(f"Quality: {q['requirements']} requirements · quotes found {pct(q['quote_found_rate'])} · "
          f"faithful {pct(q['faithfulness_rate'])} of {q['judged']} judged {q['verdicts'] or ''} · "
          f"{q['duplicates']} duplicates · {q['failed_sections']} failed sections")
    print(f"Needs review: {', '.join(q['needs_review']) or 'none'}")
    print(f"Sections sent {q['sections_sent']} · skipped {q['skipped_sections']} · "
          f"hit max_tokens (looping): {', '.join(q['truncated_calls']) or 'none'} · "
          f"reasoning tokens {q['reasoning_tokens']}")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RFP_PATH

    for event in run_pipeline(load_document(path), path.name, SECTION_IDS):
        if event["type"] == "sections":
            print(f"{len(event['sections'])} sections: {', '.join(s['id'] for s in event['sections'])}\n")
        elif event["type"] == "section":
            print_section(event)
        elif event["type"] == "summary":
            print_summary(event)
        elif event["type"] == "done":
            print(f"Totals: {event['totals']}")
            print_quality(event["quality"])
            print(f"Trace saved to runs/{event['trace_file']}")


if __name__ == "__main__":
    main()
