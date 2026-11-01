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

## Evaluation

### Synthetic brief with planted traps as the gold set
- **Chose:** a synthetic ITT (`eval/briefs/`) written so every requirement is known, with
  gold labels in `eval/gold/`. Items are tagged with the failure mode they test.
- **Instead of:** hand-labelling the real RFPs.
- **Why:** labels are unambiguous by construction, and each trap targets a failure mode
  seen on real documents (should vs must, relaxations, permissions, tables). Real RFPs
  have many borderline items where two labellers would disagree.
- **Trade-off:** synthetic text is cleaner than real PDFs (no extraction noise, short
  sections). Next step: label one real RFP to check the scores carry over.
- **Three gold lists**, not one: `requirements` (recall), `optional` (an invitation like
  "may propose an SMS option": not counted either way, since reasonable labels differ) and
  `forbidden` (must not be extracted).

### Matching by quote overlap, not by description
- **Chose:** match on the quote: share of the shorter quote's content words found in the
  other (threshold 0.6), one-to-one, best first. Modal verbs and "supplier" are stopwords so
  the match depends on what the requirement is about; "not" is kept.
- **Instead of:** embedding similarity or an LLM matcher on descriptions.
- **Why:** deterministic, free, explainable in one sentence. Quotes come from the source,
  so they are far more stable than generated descriptions.
- **Check:** no two gold items overlap at 0.6 or more, so the matcher can't confuse them.

### Light LLM judge, scoring content only
- **Chose:** the generator model (`qwen/qwen3-8b`) as the judge, configurable with
  `JUDGE_MODEL`. It checks whether each description states the same content as its quote.
- **Why light:** it runs on a laptop next to the generator for the demo. In production I'd
  use a larger model from a different family (self-preference bias), and calibrate it
  against human verdicts on a sample before trusting its rate.
- **Iteration (failure mode found):** the first judge also scored obligation strength. It
  flagged correct imperative descriptions ("Deliver a web platform") as "stronger" or
  "removes the obligation": 3-4 false alarms out of 25. Giving it the mandatory label
  moved the errors instead of removing them (it flagged list items whose "must" sits in
  the lead-in, not the quote). Fix: the judge scores content only, and strength is scored
  deterministically against gold (mandatory accuracy). False alarms went to 0 of 4 flags.
- **Known limit:** verdict labels are sometimes wrong even when the flag is right
  (a dropped condition labelled "stronger" instead of "weaker").

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

### Found by the eval (synthetic brief, run 20261101-174328)
- **`mandatory` still over-set:** 71% accuracy; every "should" item and every item under
  "Each proposal should include:" was marked mandatory (0/3 on the should-vs-must trap).
- **Forbidden items extracted:** "Individual CVs are not required" (as "Do not require
  individual CVs"), "consortia are welcome", and the client's own announcement date.
- **"Desirable but not essential" turned into a requirement** ("Have ISO 27001 certification").
- **Quote stitched from two table rows:** row 1's milestone with row 2's date. The
  description had the right date; the quote check flagged it, and so did the judge.
- **Quotes stitched to list lead-ins:** "The supplier will need to provide: two online
  training sessions..." is faithful but not verbatim, so 6 of 25 quotes are "not found".
  Either the check should accept lead-in + item, or the prompt should ask for the item only.
- **Consistent across runs:** three runs (temperature 0.2) gave identical extraction metrics.

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
| Eval harness (synthetic gold set, matcher, judge) | ~3 h |
| Agentic pipeline (planner, risks, critic) | — |
| Docs and demo | — |
