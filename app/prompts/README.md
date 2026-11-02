# Prompts

Each prompt is a plain Markdown file loaded by `app/agent.py`, so prompts can be read,
diffed and changed without touching code. The notes below are not sent to the model.

## extract.md: per-section requirement extractor

Used by `extract_requirements()`, once per document section, with a strict JSON schema
(`SectionExtraction`). The user message is the section's breadcrumb and text.

- **Defines a requirement** (supplier obligation or bid constraint) and what is not one
  (background, the client's own goals), because the model otherwise extracts everything.
- **Offeror-only (v2).** On the Beach Clubs RFP, v1 extracted the buyer's rights as
  offeror obligations ("NPS reserves the right to negotiate with the next Offeror",
  "elements may be incorporated at Lessor's discretion"). The prompt now lists the
  supplier's other names (offeror, lessee...) and the buyer-side patterns to skip, with
  a subject test: if the subject is the buyer, it's almost never a requirement.
- **Deadline exception (v3).** v2 listed the buyer's "process and timeline" as not a
  requirement, which contradicts "deadlines are requirements": on the Beach Clubs "Key
  Dates" section the model sometimes returned nothing, dropping the proposal deadline.
  v3 calls them the buyer's "milestones" (release date, selection date) and says supplier
  deadlines are requirements even in a list of dates. Measured on 2026-11-02: Key Dates 5/5
  runs found both deadlines; on S03 the buyer rights were extracted in 4/4 runs with v2 and
  1/6 with v3, but v3 also missed two real obligations there (due diligence, NPS approval
  of alterations).
- **One obligation per item**, so lists in RFPs become countable requirements.
- **Verbatim quote (max 30 words)** so code can check each requirement against the source
  (`quote_found`). This is the main hallucination guard.
- **Category definitions** are explicit; without them the model labels almost everything
  `functional`. Submission logistics are `commercial` on purpose.
- **Empty list is a correct answer**, so sections without requirements don't get filler.
- `/no_think` is appended to the user message (not here) to turn off Qwen3 reasoning.

Known issues (see DECISIONS.md):
- "starting with a verb" forces relaxations into commands: "individual CVs are not
  required" became "Do not include individual CVs".
- `mandatory` is set to true too often.
- Permissions ("consortia are welcome") are extracted as requirements.

## synthesize.md: overview, approach and risks from the requirements

Used by `synthesize_summary()`, once per run, after extraction, with a strict JSON schema
(`Synthesis`). The user message is the first ~3,000 chars of the document (for title and
client) and the extracted requirements as `id [category, mandatory] description` lines.

- **Plans from the extracted requirements, not the raw document**, so the summary reuses
  verified requirements instead of re-extracting them in one long call.
- **Every phase and risk cites requirement ids.** The ids come first in the schema so the
  model picks its evidence before writing. Code then drops ids that don't exist
  (`unknown_ids`) and lists mandatory requirements no phase covers (`uncovered_mandatory`).
- **"Risks must come from the requirements"**, because otherwise the model writes generic
  project risks ("scope creep", "communication issues").

## judge.md: faithfulness judge (eval only)

Used by `judge_section()`, in the live pipeline (online evaluation) and the eval harness,
once per section, with a strict JSON schema (`SectionVerdicts`). The user message lists the
section's requirements as `[id]`, quote and description.

- **Catches what the quote check can't**: a verbatim quote with a description that changes
  its meaning ("desirable but not essential" -> "Have ISO 27001 certification").
- **Content only, not obligation strength.** Strength is scored against gold labels
  (mandatory accuracy). The first two versions judged strength too, and the 8B judge flagged
  every imperative description ("Deliver...") as "stronger": 3-4 false alarms per run.
- **`reason` before `verdict`** in the schema, so the model names the difference before labelling it.
- `temperature=0`: a judge should give the same verdict every time.
- **One call per section, not per requirement.** Per-requirement calls re-sent the
  instructions every time: on a 50-section RFP the judge used more prompt tokens than
  extraction. Batching cuts judge prompt tokens ~75% (cost on a hosted API) but **not local
  latency**: measured back to back on the same 14 requirements, batched took 73 s vs 61 s
  per-item, because local time follows output tokens and batching adds ids and list
  structure. Each verdict carries the requirement id; code drops ids that weren't asked
  about and reports requirements left without a verdict.

## baseline.md: single-call baseline

Used by `summarize_rfp()`: the whole document (truncated to `max_document_chars`) in one
call, producing the full `SolutionSummary`. Kept as the baseline the pipeline is compared
against in the eval.
