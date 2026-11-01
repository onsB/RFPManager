import re
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.schemas import DocumentSection, SectionExtraction, SectionRequirement, SolutionSummary
from app.telemetry import RunTrace, traced_completion

PROMPTS_DIR = Path(__file__).parent / "prompts"  # notes on each prompt: prompts/README.md


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


EXTRACT_PROMPT = _load_prompt("extract")
SYSTEM_PROMPT = _load_prompt("baseline")

client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def _normalize(text: str) -> str:
    """Lowercases and strips Markdown and whitespace so quotes can be matched to the source."""
    text = re.sub(r"<[^>]+>|[*_|`#]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def extract_requirements(section: DocumentSection, trace: RunTrace | None) -> list[SectionRequirement]:
    """Extracts the requirements stated in one section and checks each quote against it."""
    response = traced_completion(
        client, trace, step="extract", section_id=section.id, section_title=section.breadcrumb,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            # /no_think turns off Qwen3's reasoning: slower and not needed for extraction.
            {"role": "user", "content": f"## [{section.id}] {section.breadcrumb}\n\n{section.text}\n\n/no_think"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "section_extraction",
                "schema": SectionExtraction.model_json_schema(),
                "strict": True,
            },
        },
    )

    extraction = SectionExtraction.model_validate_json(response.choices[0].message.content)
    section_text = _normalize(section.text)
    return [
        SectionRequirement(
            **req.model_dump(),
            section_id=section.id,
            quote_found=_normalize(req.quote) in section_text,
        )
        for req in extraction.requirements
    ]


def summarize_rfp(document_text: str, trace: RunTrace | None) -> SolutionSummary:
    text = document_text[: settings.max_document_chars]

    response = traced_completion(
        client, trace, step="summarize",  # whole document, so no section_id
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"RFP document:\n\n{text}"},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "solution_summary",
                "schema": SolutionSummary.model_json_schema(),
                "strict": True,
            },
        },
    )

    return SolutionSummary.model_validate_json(response.choices[0].message.content)
