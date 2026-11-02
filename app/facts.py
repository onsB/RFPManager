"""Facts found by code, not by the LLM: deterministic, so they can't be dropped or invented."""

import re

from app.schemas import Deadline, DocumentSection

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
          r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_DATE = (rf"(?:{_DAY}\s+{_MONTH},?\s+\d{{4}}"       # 18 September 2026, 01 Sep 2026
         rf"|{_MONTH}\s+{_DAY},?\s+\d{{4}}"          # September 18, 2026
         r"|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})")  # 18/09/2026, 2026-09-18
_TIME = (r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2}|(?:12\s+)?(?:noon|midday))"
         r"(?:\s*(?:[ECMP][SD]T|ET|GMT|BST|UTC))?")
_WEEKDAY = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+"
# Optional time before ("12pm 18 September 2026", "3:00 PM PST on Friday, December 11, 2026")
# or after ("at 5:00 PM EDT").
DATE_RE = re.compile(
    rf"(?:{_TIME},?\s+(?:on\s+(?:the\s+)?)?)?(?:{_WEEKDAY})?{_DATE}(?:,?\s*(?:at\s+)?{_TIME})?", re.IGNORECASE)

# The words just before a date decide what it is the date of.
SUBMISSION_RE = re.compile(r"tender|proposal|bid|offer|quot|response|application|submi|expression of interest", re.I)
DEADLINE_RE = re.compile(r"deadline|due|clos|no later than|submitted|received|\bby\b|before", re.I)
STRONG_RE = re.compile(r"deadline|due|clos", re.I)
NOT_SUBMISSION_RE = re.compile(
    r"question|clarification|enquir|quer(y|ies)|site (visit|tour)|tours?\b|award|selection|announce"
    r"|commence|start|effective|release|deliver", re.I)

CONTEXT_CHARS = 120  # how far before a date to look for its label

# Key facts for the critic: every amount of money, and every date including month-year
# ("January 2026"), which find_deadline doesn't need but contradictions often hide in.
MONEY_RE = re.compile(
    r"(?:[$£€]|\b(?:USD|GBP|EUR)\s?)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|bn|[mk])\b)?"
    r"(?:\s?(?:per|/|a)\s?(?:year|annum|yr|month|hour|day))?", re.IGNORECASE)
KEY_DATE_RE = re.compile(rf"{DATE_RE.pattern}|\b{_MONTH}\s+\d{{4}}\b", re.IGNORECASE)
LABEL_CHARS = 70  # keep labels short: the critic reads dozens of them


def _plain(text: str) -> str:
    """Markdown tables and line breaks to plain text, so a table row reads like a sentence."""
    text = re.sub(r"<br>|\|", " ", text)
    text = re.sub(r"<[^>]+>|[*_]", "", text)
    return re.sub(r"\s+", " ", text)


def _labelled_matches(pattern: re.Pattern, text: str) -> list[tuple[re.Match, str]]:
    """Each match with its label: the clause right before it, back to the previous match.

    "...are needed.) Initial Proposal Deadline: September 18" -> "Initial Proposal Deadline"
    """
    result = []
    previous_end = 0
    for match in pattern.finditer(text):
        context = text[max(previous_end, match.start() - CONTEXT_CHARS):match.start()]
        previous_end = match.end()
        result.append((match, re.split(r"[.;)]\s", context)[-1].strip(" :-–,")))
    return result


def find_deadline(sections: list[DocumentSection]) -> Deadline | None:
    """Finds the proposal submission deadline in the document text, or None.

    Every date is classified by the text between it and the previous date (at most
    CONTEXT_CHARS): it must name a submission and a deadline, and not be about questions,
    site visits, award or delivery. Best score wins ("deadline" / "due" / "closing" beat
    "by"); ties go to the earliest in the document, usually the cover page.
    """
    best: tuple[int, Deadline] | None = None
    for section in sections:
        for match, label in _labelled_matches(DATE_RE, _plain(section.text)):
            if not (SUBMISSION_RE.search(label) and DEADLINE_RE.search(label)):
                continue
            if NOT_SUBMISSION_RE.search(label):
                continue
            score = 2 if STRONG_RE.search(label) else 1
            if best is None or score > best[0]:
                best = (score, Deadline(date=match.group(0).strip(), label=label, section_id=section.id))
    return best[1] if best else None


def find_key_facts(sections: list[DocumentSection]) -> dict:
    """The deadline, every amount of money and every date, each with its label and section.

    Used by the critic's get_key_facts tool: comparing dates and amounts across sections
    is how it finds contradictions (e.g. a lease start in 2027 on the cover, 2026 later).
    Identical (value, label) pairs are listed once, with the first section they appear in.
    """
    facts: dict[str, list[dict]] = {"amounts": [], "dates": []}
    seen: set[tuple[str, str, str]] = set()
    for section in sections:
        text = _plain(section.text)
        for kind, pattern in (("amounts", MONEY_RE), ("dates", KEY_DATE_RE)):
            for match, label in _labelled_matches(pattern, text):
                value = match.group(0).strip()
                if len(label) > LABEL_CHARS:  # keep the end, cut at a word boundary
                    label = label[-LABEL_CHARS:].split(" ", 1)[-1]
                if (kind, value, label) in seen:
                    continue
                seen.add((kind, value, label))
                facts[kind].append({"value": value, "label": label, "section_id": section.id})
    deadline = find_deadline(sections)
    return {"deadline": deadline.model_dump() if deadline else None, **facts}
