from pathlib import Path

from docx import Document
from pymupdf import pymupdf4llm


def load_document(path: str | Path) -> str:
    """Extract text from a PDF (as Markdown), DOCX, or text file."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        # Markdown keeps headings and tables, so the agent can cite sections.
        return pymupdf4llm.to_markdown(str(path)).strip()

    if suffix == ".docx":
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs).strip()

    if suffix in {".txt", ".md"}:
        # utf-8-sig drops the BOM Windows editors add, which would hide a first-line heading.
        return path.read_text(encoding="utf-8-sig").strip()

    raise ValueError(f"Unsupported file type: {suffix}")
