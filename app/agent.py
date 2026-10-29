from openai import OpenAI

from app.config import settings
from app.schemas import SolutionSummary

SYSTEM_PROMPT = """You are a pre-sales solution architect analysing a Request for Proposal (RFP).
Read the RFP and produce a structured solution summary:
- requirements: every concrete requirement stated in the RFP. Do not invent any.
- approach: the phases of a delivery approach that satisfies those requirements.
- risks: delivery, technical, and commercial risks, each with a mitigation.
Base everything on the document. If something is not stated, say "not specified"."""

client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


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
