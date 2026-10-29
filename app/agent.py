import re

from openai import OpenAI

from app.config import settings
from app.schemas import DocumentSection, SectionExtraction, SectionRequirement, SolutionSummary

EXTRACT_PROMPT = """You extract requirements from ONE section of a Request for Proposal (RFP).

A requirement is something the supplier must do, deliver, provide or comply with,
or a constraint on the bid itself (deadline, budget, format, eligibility).
NOT requirements: background on the client, the client's own goals or history,
unless the text turns them into something the supplier must do.

Rules:
- One requirement per obligation. Split lists into separate requirements.
- description: one self-contained sentence starting with a verb ("Deliver...", "Submit...").
  Do not write "this", "the above" or "as described"; name the thing.
- mandatory: true only for must / shall / required / mandatory / will need to.
  false for should / may / desirable / would like / ideally.
- quote: copy the shortest span of the section text (max 30 words) that states the
  requirement, character for character. Never paraphrase or combine sentences.
- category:
  functional = what the supplier delivers or does
  non-functional = quality, accessibility, timing or performance of the delivery
  compliance = legal, policy, insurance, data protection, certifications
  commercial = budget, pricing, payment, contract terms, submission logistics
  other = anything else
- Use only this section. If it contains no requirements, return an empty list;
  that is a correct answer, not a failure."""

SYSTEM_PROMPT = """You are a pre-sales solution architect analysing a Request for Proposal (RFP).
Read the RFP and produce a structured solution summary:
- requirements: every concrete requirement stated in the RFP. Do not invent any.
- approach: the phases of a delivery approach that satisfies those requirements.
- risks: delivery, technical, and commercial risks, each with a mitigation.
Base everything on the document. If something is not stated, say "not specified"."""

client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


def _normalize(text: str) -> str:
    """Lowercases and strips Markdown and whitespace so quotes can be matched to the source."""
    text = re.sub(r"<[^>]+>|[*_|`#]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def extract_requirements(section: DocumentSection) -> list[SectionRequirement]:
    """Extracts the requirements stated in one section and checks each quote against it."""
    response = client.chat.completions.create(
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


def summarize_rfp(document_text: str) -> SolutionSummary:
    text = document_text[: settings.max_document_chars]

    response = client.chat.completions.create(
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
