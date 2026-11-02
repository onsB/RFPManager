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

### Submission deadline found by code, not by the LLM
- **Chose:** `find_deadline()` in `app/facts.py` scans the document text for dates and
  classifies each by the words just before it: it must name a submission and a deadline,
  and not be about questions, site visits, award or delivery. Shown under the summary title.
- **Instead of:** taking the deadline from the extracted requirements.
- **Why:** it is the most important fact in an RFP, and the LLM dropped it (the Key Dates
  regression). A regex can't drop it on a bad run, and it cites the section it came from.
- **Checked on all 6 sample documents:** right deadline in the 5 that have one (four
  formats: date lists, table cells, form fields, sentences); none for the EOI, which has none.
  It skips the decoys: the Beach Clubs question deadline and the Hertford delivery deadline.
- **Limit:** English month names and numeric dates only; relative dates ("four weeks after
  publication") aren't found. When nothing is found, the page says so.

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

### Online evaluation on every run
- **Chose:** the checks that need no gold labels (quote found, judge faithfulness,
  duplicates, summary grounding) run inside the pipeline on every document. Flagged
  requirements are shown with the judge's reason; the run's quality report is saved in its trace.
- **Why:** gold labels only exist for the test brief. On real uploads, these checks are
  the only signal, and they turn "review 60 requirements" into "review the 10 flagged ones".
  Saving them in the trace makes quality comparable across runs (dashboard next).
- **Trade-off:** the judge adds ~1 s per requirement with the 8B model (about +40% run time).
- **Judge after the summary, not during extraction:** the judge first ran right after each
  section, so the brief waited for every verdict. Nothing before the summary uses them (the
  synthesis plans from all requirements, flagged or not), so the judge now runs after the
  summary event: the brief appears as soon as it's written and the "flagged for review"
  count fills in section by section. Same total time, but on the synthetic brief the
  brief appeared at 55 s instead of ~78 s, and the review numbers ~23 s later.
  A background job overnight was rejected: the flagged numbers are part of the demo.
  `LIVE_JUDGE=false` turns the judge off; the deterministic checks stay on.
- **If the critic loop is added:** it needs verdicts before the summary (to re-extract
  flagged sections), so it would move the judge back before synthesis, for flagged
  sections at least. That's the cost of a loop, and it should be measured.
- **Shared code:** the harness and the pipeline use the same quote-overlap function
  (`app/quality.py`) for gold matching and duplicate detection.

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
- **Not fully consistent across runs:** three harness runs gave identical metrics, but a
  pipeline run on the same brief extracted 6 requirements from S07 instead of 8 (it dropped
  "CVs not required" and "consortia welcome"). Temperature 0.2 leaves some variation; a
  consistency metric (N runs, agreement of the matched set) is the next eval addition.

### Buyer rights as requirements, and the deadline regression the fix caused
- **Seen (v1):** on the Beach Clubs RFP, the buyer's rights were extracted as offeror
  obligations ("NPS reserves the right to negotiate with the next highest ranked Offeror",
  "reject one or all proposals", "incorporated at Lessor's discretion").
- **Fix attempt (v2):** extract only obligations on the supplier; list the buyer's rights,
  "process and timeline" and position as not requirements, with a subject test.
- **Regression:** in two full runs, S02 "Key Dates" returned no requirements and dropped
  the proposal deadline (Sept 18), the most important requirement in the document.
  The TOC filter was suspected but ruled out: the trace shows S02 was sent to the LLM
  (694 prompt tokens) with the deadline in its text, and the model answered `[]`.
- **Cause:** v2 contradicted itself. "Deadlines are requirements" and "the buyer's
  timeline is not" both apply to a list of key dates, so the section became borderline.
  It returned `[]` in 2/2 full runs, but found the deadline in 8/8 isolated reruns:
  near a decision boundary, small differences between runs tip the outcome.
- **Fix (v3):** the buyer's own dates (release, selection) are "milestones", not
  requirements; a deadline the supplier must meet is a requirement even in a list of dates.
- **Measured (2026-11-02, Beach Clubs, temperature 0.2):**

  | | v2 | v3 |
  |---|---|---|
  | S02: both deadlines found | 0/2 full runs | 5/5 |
  | S03: buyer rights extracted | 4/4 runs | 1/6 runs |
  | S03: due diligence, NPS approval of alterations found | yes | no |

- **Trade-off:** v3 is more precise on S03 but misses two real offeror obligations there
  ("It is incumbent upon the Offeror to conduct all due diligence", alterations "must be
  approved in advance by NPS"): obligations whose sentence subject is not the offeror.
- **Lesson:** v2 was judged on one run, and so was the regression. With this much run-to-run
  variation, a prompt change only counts if it holds over several runs. These three cases
  (deadline must be found, buyer rights must not, the two S03 obligations must) go into the
  harness as gold items on a real document, run N times.
- **Open question:** one failing run was served as `qwen3-8b` and the other as
  `qwen/qwen3-8b`. If LM Studio has two different downloads under these names, runs aren't
  comparable; the trace records the served model so this can be checked.

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
