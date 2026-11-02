"""Tools the critic agent can call: plain Python over the run's state, no LLM.

Each tool takes JSON arguments and returns a JSON string, cut to `tool_result_chars` so a
large result can't flood the context. `call_tool` raises on an unknown tool or bad
arguments; the agent loop turns that into an error message the model can correct.
"""

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from app.agent import normalize_text
from app.config import settings
from app.facts import find_key_facts
from app.quality import STOPWORDS
from app.schemas import DocumentSection, RFPSummary, SectionRequirement

SNIPPET_CHARS = 600


@dataclass
class ToolContext:
    """What the tools can see: the document's sections, the requirements and the current brief."""

    sections: list[DocumentSection]
    requirements: list[SectionRequirement]
    summary: RFPSummary


def _stems(text: str) -> list[str]:
    """Content words, cut to 6 letters so "commencement" matches "commence" (a crude stemmer)."""
    words = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [w[:6] if len(w) > 6 else w for w in words if w not in STOPWORDS and len(w) > 1]


def _snippet(text: str, stems: set[str]) -> str:
    """The SNIPPET_CHARS window of the text that contains the most distinct query words."""
    text = re.sub(r"\s+", " ", text)
    lowered = text.lower()
    hits = [(m.start(), s) for s in stems for m in re.finditer(rf"\b{re.escape(s)}", lowered)]
    if not hits:
        return text[:SNIPPET_CHARS]
    half = SNIPPET_CHARS // 2
    center = max(hits, key=lambda h: len({s for p, s in hits if abs(p - h[0]) <= half}))[0]
    start = max(0, center - half)
    return ("…" if start else "") + text[start:start + SNIPPET_CHARS] + ("…" if start + SNIPPET_CHARS < len(text) else "")


def search_rfp(ctx: ToolContext, query: str, k: int = 3) -> list[dict]:
    """BM25 over the sections' text, with the best-matching passage of each hit."""
    docs = [_stems(f"{s.breadcrumb} {s.text}") for s in ctx.sections]
    query_stems = set(_stems(query))
    if not query_stems:
        raise ValueError("the query has no searchable words; use content words like 'lease commencement'")
    n, avg_len = len(docs), sum(map(len, docs)) / max(len(docs), 1)
    df = Counter(s for doc in docs for s in set(doc))
    scores = []
    for section, doc in zip(ctx.sections, docs):
        tf, score = Counter(doc), 0.0
        for s in query_stems:
            if tf[s]:
                idf = math.log(1 + (n - df[s] + 0.5) / (df[s] + 0.5))
                score += idf * tf[s] * 2.2 / (tf[s] + 1.2 * (0.25 + 0.75 * len(doc) / avg_len))  # k1=1.2, b=0.75
        if score:
            scores.append((score, section))
    scores.sort(key=lambda x: -x[0])
    return [
        {"section_id": s.id, "title": s.breadcrumb, "snippet": _snippet(s.text, query_stems)}
        for _, s in scores[: int(k)]
    ]


def get_section(ctx: ToolContext, section_id: str) -> dict:
    for s in ctx.sections:
        if s.id == section_id:
            return {"section_id": s.id, "title": s.breadcrumb, "text": s.text}
    raise ValueError(f"unknown section_id {section_id!r}; ids look like S01 or S13a (see search_rfp results)")


def list_requirements(
    ctx: ToolContext, category: str | None = None, mandatory: bool | str | None = None, section_id: str | None = None,
) -> list[dict]:
    if isinstance(mandatory, str):  # 8B models sometimes send "true" as a string
        mandatory = mandatory.strip().lower() == "true"
    return [
        {"id": r.id, "category": r.category, "mandatory": r.mandatory, "description": r.description}
        for r in ctx.requirements
        if (category is None or r.category == category)
        and (mandatory is None or r.mandatory == mandatory)
        and (section_id is None or r.section_id == section_id)
        and r.duplicate_of is None
    ]


def get_key_facts(ctx: ToolContext) -> dict:
    return find_key_facts(ctx.sections)


def check_coverage(ctx: ToolContext) -> dict:
    """Deterministic checks of the current brief: what the critic would otherwise guess at."""
    s = ctx.summary
    known = {r.id for r in ctx.requirements}
    covered = {i for phase in s.approach for i in phase.requirement_ids}
    return {
        "uncovered_mandatory": [
            {"id": r.id, "description": r.description}
            for r in ctx.requirements if r.mandatory and r.duplicate_of is None and r.id not in covered
        ],
        "made_up_ids_dropped_from_draft": s.unknown_ids,
        "cited_ids_not_found": sorted(
            {i for item in [*s.approach, *s.risks] for i in item.requirement_ids} - known
        ),
        "risks_citing_no_requirement": [
            {"risk_index": i, "description": r.description} for i, r in enumerate(s.risks) if not r.requirement_ids
        ],
    }


TOOLS = {
    "search_rfp": search_rfp,
    "get_section": get_section,
    "list_requirements": list_requirements,
    "get_key_facts": get_key_facts,
    "check_coverage": check_coverage,
}


def call_tool(ctx: ToolContext, name: str, args: dict) -> str:
    """Runs one tool and returns its result as JSON, truncated to `tool_result_chars`."""
    if name not in TOOLS:
        raise ValueError(f"unknown tool {name!r}; available: {', '.join(TOOLS)}")
    text = json.dumps(TOOLS[name](ctx, **args), ensure_ascii=False)
    limit = settings.tool_result_chars
    if len(text) > limit:
        text = text[:limit] + f" …[truncated {len(text) - limit} chars: narrow the query or filters]"
    return text


def _spec(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


TOOL_SPECS = [  # all tools; the critic gets AGENT_TOOL_SPECS (see below)
    _spec(
        "check_coverage",
        "Deterministic checks of the draft brief: mandatory requirements no approach phase cites, "
        "requirement ids that don't exist, and risks that cite no requirement. Call this first.",
    ),
    _spec(
        "get_key_facts",
        "Every deadline, amount of money and date found in the RFP text by regex, each with the words "
        "before it and its section id. Use it to check that risks name real facts and to spot "
        "contradictions (the same date or amount stated differently in two sections).",
    ),
    _spec(
        "search_rfp",
        "Keyword search over the full RFP text. Returns the best-matching sections with a passage "
        "around the match. Use it to confirm a suspected issue in the source, e.g. "
        "'lease commencement', 'evaluation criteria', 'insurance'.",
        {
            "query": {"type": "string", "description": "A few content words, not a question"},
            "k": {"type": "integer", "description": "Number of sections to return (default 3)"},
        },
        ["query"],
    ),
    _spec(
        "get_section",
        "The full text of one section, when a search_rfp passage isn't enough.",
        {"section_id": {"type": "string", "description": "A section id from search_rfp, e.g. S08"}},
        ["section_id"],
    ),
    _spec(
        "list_requirements",
        "The extracted requirements, optionally filtered. Use it to check that a risk or phase "
        "matches what the RFP actually requires.",
        {
            "category": {"type": "string", "enum": ["functional", "non-functional", "compliance", "commercial", "other"]},
            "mandatory": {"type": "boolean", "description": "true for must-haves only"},
            "section_id": {"type": "string", "description": "Only requirements from this section"},
        },
    ),
]

# check_coverage and get_key_facts are deterministic and always needed, so code runs them and
# puts their results in the critic's first message. The 8B critic called one tool and then
# stopped; it gets only the tools that need judgement about what to look for.
CONTEXT_TOOLS = ("check_coverage", "get_key_facts")
AGENT_TOOL_SPECS = [s for s in TOOL_SPECS if s["function"]["name"] not in CONTEXT_TOOLS]
