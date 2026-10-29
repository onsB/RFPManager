import sys

from app.agent import summarize_rfp
from app.config import settings
from app.documents import load_document


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: uv run python -m app.main <path-to-rfp>")

    text = load_document(sys.argv[1])
    if len(text) > settings.max_document_chars:
        print(
            f"Warning: document is {len(text):,} chars, truncated to {settings.max_document_chars:,}",
            file=sys.stderr,
        )

    summary = summarize_rfp(text)
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
