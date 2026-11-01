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

## baseline.md: single-call baseline

Used by `summarize_rfp()`: the whole document (truncated to `max_document_chars`) in one
call, producing the full `SolutionSummary`. Kept as the baseline the pipeline is compared
against in the eval.
