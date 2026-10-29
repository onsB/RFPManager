import re
from app.schemas import DocumentSection

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


def split_sections(markdown: str) -> list[DocumentSection]:
    """
    Splits a markdown string into sections based on headings.

    Args:
        markdown (str): The markdown string to be split.

    Returns:
        list[DocumentSection]: A list of DocumentSection objects representing the sections.
    """
    sections = []
    current_section = None
    current_level = 0

    for line in markdown.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = clean_heading(heading_match.group(2))

            if current_section is not None:
                sections.append(current_section)

            current_section = DocumentSection(id=str(len(sections) + 1), title=title, level=level, text="")
            current_level = level
        elif current_section is not None:
            current_section.text += line + "\n"

    if current_section is not None:
        sections.append(current_section)

    return merge_small_sections(sections)


def merge_small_sections(sections: list[DocumentSection], min_chars: int = 50) -> list[DocumentSection]:
    """
    Merges sections with almost no body text into the section that follows them.

    A heading followed directly by a sub-heading (e.g. "Communities of Practice aims")
    has an empty body. Its title is kept as a bold line at the top of the next section,
    so the context is not lost. Sections are renumbered S01, S02, ... afterwards.

    Args:
        sections (list[DocumentSection]): Sections in document order.
        min_chars (int): Sections with less body text than this are merged.

    Returns:
        list[DocumentSection]: The merged and renumbered sections.
    """
    merged = []
    carry = ""  # titles and text of small sections waiting for the next section

    for section in sections:
        body = section.text.strip()
        if len(body) < min_chars:
            carry += f"**{section.title}**\n\n" + (f"{body}\n\n" if body else "")
            continue

        merged.append(section.model_copy(update={"text": carry + body}))
        carry = ""

    # Small sections at the very end have no next section: attach them to the last one.
    if carry:
        if merged:
            last = merged[-1]
            merged[-1] = last.model_copy(update={"text": f"{last.text}\n\n{carry.strip()}"})
        else:
            merged.append(DocumentSection(id="", title="Document", level=0, text=carry.strip()))

    return [s.model_copy(update={"id": f"S{i:02d}"}) for i, s in enumerate(merged, start=1)]
