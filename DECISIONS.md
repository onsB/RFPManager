# Decisions

Each entry: what I chose, what I considered instead, and why.

## Architecture

### Local open-source LLM (LM Studio, Qwen3 8B)
- **Chose:** Qwen3 8B served by LM Studio through its OpenAI-compatible API.
- **Instead of:** a hosted API (OpenAI, Anthropic).
- **Why:** anyone can run the demo without an API key or paid account. The `openai` SDK
  only needs a `base_url`, so switching to a hosted model is a `.env` change.
- **Trade-off:** an 8B model makes more extraction mistakes and is slower than a frontier
  model. The pipeline is designed around that (small inputs, verification in code).

### Plain Python orchestration, no agent framework
- **Chose:** each step is a Python function; the pipeline is ordinary code.
- **Instead of:** LangGraph / CrewAI.
- **Why:** every step, prompt and loop is visible and easy to explain. The workflow is a
  fixed sequence with one possible review loop, which doesn't need a graph framework.

### Structured output with a strict JSON schema
- **Chose:** `response_format` with a JSON schema generated from Pydantic models, `strict: true`.
- **Instead of:** asking for JSON in the prompt and parsing it.
- **Why:** output is always valid against the schema, so no parsing or retry logic.
  The Pydantic models are the single source of truth for the data shape.

## Document processing

### PDF to Markdown with pymupdf4llm
- **Chose:** pymupdf4llm.
- **Instead of:** pypdf (first version).
- **Why:** pypdf gives flat text; pymupdf4llm keeps headings and tables as Markdown,
  which the section splitter relies on.
- **Known gap:** PDF form fields aren't extracted (the US Navy RFQ keeps its page-1 data
  in form fields).

### Per-section extraction instead of one call for the whole document
- **Chose:** split the Markdown by headings and extract requirements section by section.
  Each section keeps its parent headings (breadcrumb, e.g. "Scope > 1. Early Design").
  Sections under 50 chars are merged into the next; sections over `max_section_chars`
  (8,000) are split on paragraph boundaries, never inside a table.
- **Instead of:** sending the whole document in one call (kept as the baseline, `summarize_rfp`).
- **Why:** a local model has a small context and loses detail on long inputs. Small inputs
  give better recall, each requirement is traceable to a section, and a failing section
  doesn't fail the run.
- **Trade-off:** more calls (one per section), so more total latency; requirements that
  span two sections can be missed or duplicated.

## Hallucination control

### Verbatim quote + check in code (`quote_found`)
- **Chose:** every requirement carries a verbatim quote; code checks it appears in the
  section text after normalising case, whitespace and Markdown.
- **Why:** a cheap, deterministic grounding check. It catches invented requirements and
  gives an eval metric (share of quotes found).
- **Limit:** it checks the wording, not the meaning. See the failure mode below.

## Observability

### Own telemetry wrapper instead of Phoenix / Langfuse
- **Chose:** `traced_completion()` in `app/telemetry.py` wraps every LLM call and records
  step, section, model, prompt/completion tokens, latency and estimated cost. One run =
  one JSON file in `runs/`, saved after every section so interrupted runs are kept.
- **Instead of:** Arize Phoenix or Langfuse.
- **Why:** no extra server or account; the data is plain files I can show and the eval can
  read. All LLM calls go through this one function, so adding OpenTelemetry later is a
  change in one place.
- **Cost:** local inference is free, so cost is estimated at a reference hosted price
  (see ASSUMPTIONS.md).

## Failure modes found

### Negation flip ("CVs are not required" → "Do not include individual CVs")
- **Seen:** S12 of the Nature Towns ITT. The quote was verbatim (`quote_found = true`), but
  the description reversed its meaning: a relaxation became a prohibition.
- **Cause:** the prompt asks for a description "starting with a verb", which forces every
  item into a command. "Not required" has no command form, so the model invented one.
  It also isn't a requirement at all.
- **Fix (planned):** prompt rule and example separating prohibitions ("must not") from
  relaxations ("not required" → skip); a critic step that checks each description
  against its quote (same / weaker / stronger / contradicts).

### `mandatory` set too often
- **Seen:** 8 of 10 requirements in S12 marked mandatory, including "should" items.
- **Fix (planned):** obligation level `must / should / may`, with the evidence phrase
  generated before the label; measure against hand labels.

### Permissions extracted as requirements
- **Seen:** "applications from consortia are welcome" extracted as a requirement.
- **Fix (planned):** same as the negation flip: define permissions as not requirements.

### Quotes not found
- **Seen:** 2 of 10 quotes in S12 not found in the section text.
- **Fix (planned):** inspect whether these are paraphrases or normalisation gaps
  (e.g. table cells, line breaks), then tighten the prompt or the normaliser.

## Time log

Approximate, from commit timestamps; to be corrected.

| Part | Time |
|---|---|
| Setup, project skeleton, config | ~1 h |
| Finding and assessing RFP documents, data exploration | ~2 h |
| Document loading and section splitting | ~2 h |
| Requirement extraction with quote check | ~1 h |
| FastAPI demo page | ~0.5 h |
| Observability (telemetry, run traces) | ~2 h |
| Eval harness | — |
| Agentic pipeline (planner, risks, critic) | — |
| Docs and demo | — |
