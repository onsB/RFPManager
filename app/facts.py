"""Facts found by code, not by the LLM: deterministic, so they can't be dropped or invented."""

import re

from app.schemas import Deadline, DocumentSection

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
          r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_DATE = (rf"(?:{_DAY}\s+{_MONTH},?\s+\d{{4}}"       # 18 September 2026, 01 Sep 2026
         rf"|{_MONTH}\s+{_DAY},?\s+\d{{4}}"          # September 18, 2026
         r"|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})")  # 18/09/2026, 2026-09-18
_TIME = (r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2}|noon|midday)"
         r"(?:\s*(?:[ECMP][SD]T|ET|GMT|BST|UTC))?")
# Optional time before ("12pm 18 September 2026", "5pm on 15 January 2027") or after ("at 5:00 PM EDT").
DATE_RE = re.compile(rf"(?:{_TIME},?\s+(?:on\s+(?:the\s+)?)?)?{_DATE}(?:,?\s*(?:at\s+)?{_TIME})?", re.IGNORECASE)

# The words just before a date decide what it is the date of.
SUBMISSION_RE = re.compile(r"tender|proposal|bid|offer|quot|response|application|submi|expression of interest", re.I)
DEADLINE_RE = re.compile(r"deadline|due|clos|no later than|submitted|received|\bby\b|before", re.I)
STRONG_RE = re.compile(r"deadline|due|clos", re.I)
NOT_SUBMISSION_RE = re.compile(
    r"question|clarification|enquir|quer(y|ies)|site (visit|tour)|tours?\b|award|selection|announce"
    r"|commence|start|effective|release|deliver", re.I)

CONTEXT_CHARS = 120  # how far before a date to look for its label


def _plain(text: str) -> str:
    """Markdown tables and line breaks to plain text, so a table row reads like a sentence."""
    text = re.sub(r"<br>|\|", " ", text)
    text = re.sub(r"<[^>]+>|[*_]", "", text)
    return re.sub(r"\s+", " ", text)


def find_deadline(sections: list[DocumentSection]) -> Deadline | None:
    """Finds the proposal submission deadline in the document text, or None.

    Every date is classified by the text between it and the previous date (at most
    CONTEXT_CHARS): it must name a submission and a deadline, and not be about questions,
    site visits, award or delivery. Best score wins ("deadline" / "due" / "closing" beat
    "by"); ties go to the earliest in the document, usually the cover page.
    """
    best: tuple[int, Deadline] | None = None
    for section in sections:
        text = _plain(section.text)
        previous_end = 0
        for match in DATE_RE.finditer(text):
            context = text[max(previous_end, match.start() - CONTEXT_CHARS):match.start()]
            previous_end = match.end()
            # Only the clause right before the date: "...are needed.) Initial Proposal Deadline:"
            label = re.split(r"[.;)]\s", context)[-1].strip(" :-–,")
            if not (SUBMISSION_RE.search(label) and DEADLINE_RE.search(label)):
                continue
            if NOT_SUBMISSION_RE.search(label):
                continue
            score = 2 if STRONG_RE.search(label) else 1
            if best is None or score > best[0]:
                best = (score, Deadline(date=match.group(0).strip(), label=label, section_id=section.id))
    return best[1] if best else None
