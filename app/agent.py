import re
from pathlib import Path

from openai import OpenAI

from app.config import settings
from app.schemas import (
    DocumentSection,
    FaithfulnessVerdict,
    RFPSummary,
    SectionExtraction,
    SectionRequirement,
    SolutionSummary,
    Synthesis,
)
from app.telemetry import RunTrace, traced_completion

PROMPTS_DIR = Path(__file__).parent / "prompts"  # notes on each prompt: prompts/README.md


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


EXTRACT_PROMPT = _load_prompt("extract")
SYNTHESIZE_PROMPT = _load_prompt("synthesize")
SYSTEM_PROMPT = _load_prompt("baseline")
JUDGE_PROMPT = _load_prompt("judge")

OPENING_CHARS = 3_000  # how much of the document the synthesis sees, for title and client

client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def normalize_text(text: str) -> str:
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
    section_text = normalize_text(section.text)
    return [
        SectionRequirement(
            **req.model_dump(),
            id=f"{section.id}-R{i:02d}",
            section_id=section.id,
            quote_found=normalize_text(req.quote) in section_text,
        )
        for i, req in enumerate(extraction.requirements, start=1)
    ]


def synthesize_summary(
    sections: list[DocumentSection],
    requirements: list[SectionRequirement],
    trace: RunTrace | None,
) -> RFPSummary:
    """Writes the overview, approach and risks from the extracted requirements, then checks the cited ids.

    The model sees the requirement list, not the whole document: it plans from what was
    extracted and verified, and every phase and risk must cite requirement ids.
    """
    opening = "\n\n".join(s.text for s in sections)[:OPENING_CHARS]
    requirement_lines = "\n".join(
        f"{r.id} [{r.category}, {'mandatory' if r.mandatory else 'optional'}] {r.description}"
        for r in requirements
    )

    response = traced_completion(
        client, trace, step="synthesize",
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        messages=[
            {"role": "system", "content": SYNTHESIZE_PROMPT},
            {"role": "user", "content": (
                f"## Document opening\n\n{opening}\n\n"
                f"## Extracted requirements\n\n{requirement_lines}\n\n/no_think"
            )},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "synthesis",
                "schema": Synthesis.model_json_schema(),
                "strict": True,
            },
        },
    )
    synthesis = Synthesis.model_validate_json(response.choices[0].message.content)

    # Grounding check: drop ids the model made up, and record them so the eval can count them.
    known_ids = {r.id for r in requirements}
    unknown_ids: set[str] = set()
    for item in [*synthesis.approach, *synthesis.risks]:
        unknown_ids.update(i for i in item.requirement_ids if i not in known_ids)
        item.requirement_ids = [i for i in item.requirement_ids if i in known_ids]

    covered = {i for phase in synthesis.approach for i in phase.requirement_ids}
    uncovered_mandatory = [r.id for r in requirements if r.mandatory and r.id not in covered]

    return RFPSummary(
        **synthesis.model_dump(),
        requirements=requirements,
        unknown_ids=sorted(unknown_ids),
        uncovered_mandatory=uncovered_mandatory,
    )


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


def judge_faithfulness(requirement: SectionRequirement, trace: RunTrace | None) -> FaithfulnessVerdict:
    """Asks the judge model whether a requirement's description means the same as its quote.

    Catches what the quote check can't: a verbatim quote with a description that
    changes its meaning (e.g. "CVs are not required" -> "Do not include CVs").
    """
    response = traced_completion(
        client, trace, step="judge", section_id=requirement.section_id,
        model=settings.judge_model or settings.llm_model,
        temperature=0,  # a judge should give the same verdict every time
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": (
                f"Quote: {requirement.quote}\n"
                f"Description: {requirement.description}\n\n/no_think"
            )},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "faithfulness_verdict",
                "schema": FaithfulnessVerdict.model_json_schema(),
                "strict": True,
            },
        },
    )
    return FaithfulnessVerdict.model_validate_json(response.choices[0].message.content)
