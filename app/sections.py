import re
from string import ascii_lowercase

from app.config import settings
from app.schemas import DocumentSection

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
# A table of contents rendered as a table: its first row is "Contents" / "Table of Contents".
TOC_TABLE_RE = re.compile(r"^\|\s*(table of )?contents\s*\|", re.IGNORECASE)
# A TOC line with dot leaders and a page number: "Key Dates ........ 3"
DOT_LEADER_RE = re.compile(r"^.{2,}?(\.{4,}|…{2,}|(\s\.){3,})\s*\d{1,4}\s*$")
PAGE_FOOTER_RE = re.compile(r"^\s*page \d+( of \d+)?\s*$", re.IGNORECASE)


def clean_heading(raw: str) -> str:
    """
    Cleans a raw heading string by removing unwanted characters and formatting it.

    Args:
        raw (str): The raw heading string to be cleaned.

    Returns:
        str: The cleaned heading string.
    """
    raw = re.sub(r"<[^>]+>", "", raw)  # HTML tags: <u>, <mark>, ...
    raw = re.sub(r"[*_]+", "", raw)  # Markdown bold/italic markers
    raw = re.sub(r"\s+", " ", raw)  # collapse runs of whitespace
    return raw.strip().rstrip(":").strip()


def _is_toc_table(rows: list[str]) -> bool:
    """A table of contents: first row "Contents", or 3+ rows that all end in a page number."""
    plain = [re.sub(r"[*_]", "", r).strip() for r in rows]
    if TOC_TABLE_RE.match(plain[0]):
        return True
    cells = [[c.strip() for c in r.strip("|").split("|")] for r in plain if not re.fullmatch(r"[|\-\s:]+", r)]
    last = [next((c for c in reversed(row) if c), "") for row in cells]
    return len(cells) >= 3 and all(c.isdigit() for c in last)


def strip_toc(markdown: str) -> str:
    """Removes tables of contents and page footers, which would otherwise be sent to the LLM.

    The parser attaches a TOC to whatever section precedes it (in the Beach Clubs RFP, a
    600-char "Key Dates" section grew to 3,700 chars), and its lines look like headings
    and requirements. Removes: tables of contents (see _is_toc_table, which also catches
    a TOC continued on the next page without its header), dot-leader lines ending in a
    page number, and "Page N" footer lines.
    """
    kept: list[str] = []
    table: list[str] = []

    def flush_table() -> None:
        if table and not _is_toc_table(table):
            kept.extend(table)
        table.clear()

    for line in markdown.splitlines():
        plain = re.sub(r"[*_]", "", line).strip()
        if plain.startswith("|"):
            table.append(line)
            continue
        flush_table()
        if DOT_LEADER_RE.match(plain) or PAGE_FOOTER_RE.match(plain):
            continue
        kept.append(line)
    flush_table()
    return "\n".join(kept)


def is_boilerplate(section: DocumentSection) -> bool:
    """True if the section's title matches `skip_section_patterns`: not sent to the LLM."""
    return any(re.search(p, section.title, re.IGNORECASE) for p in settings.skip_section_patterns)


def split_sections(markdown: str) -> list[DocumentSection]:
    """
    Splits a markdown string into sections based on headings.

    Each section keeps the titles of its parent headings in `path`, so a sub-section
    like "1. Early Design" still knows it sits under "Scope".

    Args:
        markdown (str): The markdown string to be split.

    Returns:
        list[DocumentSection]: A list of DocumentSection objects representing the sections.
    """
    markdown = strip_toc(markdown)
    sections = []
    # Text before the first heading; dropped by the merge step if it is empty.
    current_section = DocumentSection(id="", title="Preamble", level=0, text="")
    stack: list[tuple[int, str]] = []  # (level, title) of the open headings

    for line in markdown.splitlines():
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            title = clean_heading(heading_match.group(2))

            # Close siblings and deeper headings; what is left are the ancestors.
            # Works even when levels skip (e.g. #### followed by ######).
            while stack and stack[-1][0] >= level:
                stack.pop()
            path = [t for _, t in stack]
            stack.append((level, title))

            sections.append(current_section)
            current_section = DocumentSection(id="", title=title, level=level, text="", path=path)
        else:
            current_section.text += line + "\n"

    sections.append(current_section)

    sections = merge_small_sections(sections, settings.min_section_chars)
    return split_long_sections(sections, settings.max_section_chars)


def merge_small_sections(sections: list[DocumentSection], min_chars: int = 50) -> list[DocumentSection]:
    """
    Merges sections with almost no body text into the section that follows them.

    A heading followed directly by a sub-heading (e.g. "Communities of Practice aims")
    has an empty body. Its title already appears in the next section's `path`, so it is
    only carried as a bold line when it is not an ancestor of that section.
    Sections are renumbered S01, S02, ... afterwards.

    Args:
        sections (list[DocumentSection]): Sections in document order.
        min_chars (int): Sections with less body text than this are merged.

    Returns:
        list[DocumentSection]: The merged and renumbered sections.
    """
    merged = []
    pending: list[DocumentSection] = []  # small sections waiting for the next section

    def carried_text(target: DocumentSection) -> str:
        parts = []
        for small in pending:
            body = small.text.strip()
            if small.title not in target.path or body:
                parts.append(f"**{small.title}**")
            if body:
                parts.append(body)
        return "\n\n".join(parts)

    for section in sections:
        if len(section.text.strip()) < min_chars:
            pending.append(section)
            continue

        carry = carried_text(section)
        text = f"{carry}\n\n{section.text.strip()}" if carry else section.text.strip()
        merged.append(section.model_copy(update={"text": text}))
        pending = []

    # Small sections at the very end have no next section: attach them to the last one.
    if pending:
        if merged:
            last = merged[-1]
            carry = carried_text(last)
            if carry:
                merged[-1] = last.model_copy(update={"text": f"{last.text}\n\n{carry}"})
        else:
            text = "\n\n".join(s.text.strip() for s in pending if s.text.strip())
            merged.append(DocumentSection(id="", title="Document", level=0, text=text))

    return [s.model_copy(update={"id": f"S{i:02d}"}) for i, s in enumerate(merged, start=1)]


def _is_table(block: str) -> bool:
    return all(line.lstrip().startswith("|") for line in block.splitlines() if line.strip())


def _blocks(text: str) -> list[str]:
    """Splits text on blank lines, keeping consecutive table blocks together."""
    blocks: list[str] = []
    for block in (b.strip() for b in text.split("\n\n")):
        if not block:
            continue
        if blocks and _is_table(block) and _is_table(blocks[-1]):
            blocks[-1] += "\n" + block
        else:
            blocks.append(block)
    return blocks


def split_long_sections(sections: list[DocumentSection], max_chars: int) -> list[DocumentSection]:
    """
    Splits sections that are too long into parts on paragraph boundaries.

    Tables are never split: a table longer than max_chars becomes a part of its own.
    Parts keep the section's path and get ids like S13a, S13b and titles like
    "<title> (part 1/2)".

    Args:
        sections (list[DocumentSection]): Sections in document order.
        max_chars (int): Sections with more body text than this are split.

    Returns:
        list[DocumentSection]: The sections, with long ones replaced by their parts.
    """
    result = []

    for section in sections:
        if section.char_count <= max_chars:
            result.append(section)
            continue

        chunks: list[str] = []
        current = ""
        for block in _blocks(section.text):
            if current and len(current) + len(block) + 2 > max_chars:
                chunks.append(current)
                current = ""
            current = f"{current}\n\n{block}" if current else block
        if current:
            chunks.append(current)

        for i, chunk in enumerate(chunks):
            result.append(
                section.model_copy(
                    update={
                        "id": f"{section.id}{ascii_lowercase[i]}",
                        "title": f"{section.title} (part {i + 1}/{len(chunks)})",
                        "text": chunk,
                    }
                )
            )

    return result
