import sys
from pathlib import Path

from app.documents import load_document
from app.pipeline import run_pipeline

# Edit these to test from VS Code: press Run (or F5), no terminal arguments needed.
RFP_PATH = Path(__file__).parent.parent / "inputs" / "public" / "InvitationtoTender_CommunitiesofPracticeDevelopment.pdf"
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
        if req["duplicate_of"]:
            print(f"           duplicate of {req['duplicate_of']}")
    print()


def print_summary(event: dict) -> None:
    if event["error"]:
        what = f"Revision {event['revision']} failed, previous brief kept" if event["revision"] else "Summary failed"
        print(f"{what}: {event['error']}\n")
        return
    s = event["summary"]
    if event["revision"]:
        print(f"=== Revised brief (after review round {event['revision']}) ===")
    print(f"# {s['project_title']} ({s['client']})")
    d = s["deadline"]
    print(f"Due: {d['date']}  ({d['label']}, {d['section_id']})" if d else "Due: no submission deadline found")
    print(f"\n{s['overview']}\n")
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
    print(f"Review: {q['review_rounds']} rounds · approved {q['approved']} · {q['agent_steps']} agent steps · "
          f"{q['tool_calls']} tool calls {q['tools_used'] or ''} · {q['tool_errors']} tool errors")


def print_review(event: dict) -> None:
    if event["error"]:
        print(f"Review round {event['round']}: reviewer failed, brief kept ({event['error']})\n")
        return
    verdict = "approved" if event["approved"] else f"{len(event['issues'])} issues, sent back for revision"
    print(f"Review round {event['round']}: {verdict}")
    for i in event["issues"]:
        print(f"  [{i['kind']}] {i['detail']}\n      fix: {i['fix']}  (checked {', '.join(i['evidence']) or 'nothing'})")
    if event["unverified_evidence"]:
        print(f"  dropped evidence the reviewer never saw: {', '.join(event['unverified_evidence'])}")
    print()


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RFP_PATH

    for event in run_pipeline(load_document(path), path.name, SECTION_IDS):
        if event["type"] == "sections":
            print(f"{len(event['sections'])} sections: {', '.join(s['id'] for s in event['sections'])}\n")
        elif event["type"] == "section":
            print_section(event)
        elif event["type"] == "summary":
            print_summary(event)
        elif event["type"] == "reviewing":
            print(f"Reviewer checking the brief (round {event['round']})...")
        elif event["type"] == "review":
            print_review(event)
        elif event["type"] == "judging":
            print(f"Judging {event['sections']} sections...")
        elif event["type"] == "verdicts":
            flagged = {i: v for i, v in event["verdicts"].items() if v["verdict"] != "same"}
            print(f"  [{event['done']}/{event['total']}] {event['section_id']}: {len(flagged)} flagged")
            for req_id, v in flagged.items():
                print(f"      {req_id} {v['verdict'] or 'no verdict'}: {v['reason']}")
        elif event["type"] == "done":
            print(f"Totals: {event['totals']}")
            print_quality(event["quality"])
            print(f"Trace saved to runs/{event['trace_file']}")


if __name__ == "__main__":
    main()
