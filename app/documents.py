from pathlib import Path

from docx import Document
from pypdf import PdfReader


def load_document(path: str | Path) -> str:
    """Extract plain text from a PDF, DOCX, or text file."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(path)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()

    if suffix == ".docx":
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs).strip()

    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8").strip()

    raise ValueError(f"Unsupported file type: {suffix}")
