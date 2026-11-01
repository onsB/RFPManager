# Prompts

Each prompt is a plain Markdown file loaded by `app/agent.py`, so prompts can be read,
diffed and changed without touching code. The notes below are not sent to the model.

## extract.md: per-section requirement extractor

Used by `extract_requirements()`, once per document section, with a strict JSON schema
(`SectionExtraction`). The user message is the section's breadcrumb and text.

- **Defines a requirement** (supplier obligation or bid constraint) and what is not one
  (background, the client's own goals), because the model otherwise extracts everything.
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

## baseline.md: single-call baseline

Used by `summarize_rfp()`: the whole document (truncated to `max_document_chars`) in one
call, producing the full `SolutionSummary`. Kept as the baseline the pipeline is compared
against in the eval.
