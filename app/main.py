import sys
import time
from pathlib import Path

from app.agent import extract_requirements
from app.documents import load_document
from app.sections import split_sections

# Edit these to test from VS Code: press Run (or F5), no terminal arguments needed.
RFP_PATH = Path(__file__).parent.parent / "inputs" / "InvitationtoTender_CommunitiesofPracticeDevelopment.pdf"
SECTION_IDS: list[str] = ["S12"]  # empty list = run every section


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else RFP_PATH

    text = load_document(path)
    sections = split_sections(text)  # also merges small and splits long sections
    print(f"{len(sections)} sections: {', '.join(s.id for s in sections)}\n")

    for section in sections:
        if SECTION_IDS and section.id not in SECTION_IDS:
            continue

        start = time.perf_counter()
        requirements = extract_requirements(section)
        elapsed = time.perf_counter() - start

        print(f"## [{section.id}] {section.breadcrumb}  ({len(requirements)} reqs, {elapsed:.1f}s)")
        for req in requirements:
            found = "ok " if req.quote_found else "NOT FOUND"
            must = "must" if req.mandatory else "    "
            print(f"  [{found}] {must} {req.category:<14} {req.description}")
            print(f"           quote: \"{req.quote}\"")
        print()


if __name__ == "__main__":
    main()
