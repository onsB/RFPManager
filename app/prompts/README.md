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

### synthesize.md v2: written for the critic loop
- **Risks must cite an id AND name a concrete fact** (amount, date, named system, permit,
  regulation). v1 said "risks must come from the requirements" and the model still wrote
  "tight deadlines" with an id attached.
- **Approach by evaluation criteria** when the RFP has them, because bids are scored per criterion.
- **Bidder's side only**: the issuer's rights and actions aren't the bidder's phases or risks.
- **Revision mode**: with a previous draft and reviewer issues in the user message (same
  prompt, same schema), it fixes each issue and keeps the rest.

## critic.md: the reviewer agent (tools, thinking on)

Used by `review_summary()` in `app/critic.py`, in a tool loop of at most `agent_max_steps`
turns. The user message is the draft brief as Markdown, with the ids each item cites.

- **A rubric of 5 checks, each tied to a tool:** specific risks (get_key_facts,
  list_requirements), coverage (check_coverage), contradictions (get_key_facts, then
  search_rfp to read both passages), right party, structure (search_rfp
  "evaluation criteria"). A rubric gives the 8B model concrete things to check rather than
  "review this".
- **"Check each point with a tool before you raise it"**, and evidence must be ids it read in
  a tool result. Code enforces this: evidence ids it was never shown are dropped and counted
  (`unverified_evidence`).
- **check_coverage and get_key_facts first**: they are deterministic and cheap, and they
  answer two of the five checks. Search only to confirm.
- **At most 5 tool calls, at most 6 issues**: the code cap is `agent_max_steps`; the prompt
  cap keeps the model from spending all its steps on searches.
- **JSON answer in the prompt, not a strict schema**: LM Studio can't combine `tools` with
  a strict `response_format`. Code takes the first JSON object after stripping `<think>`,
  validates it with pydantic, and sends one repair turn if that fails.
- **`approved` is re-checked in code**: false while any blocking issue (generic_risk,
  uncovered_mandatory, contradiction, wrong_party) remains, whatever the model said.
- **Thinking on (`/think`), temperature 0.6, top_p 0.95**: Qwen's recommended settings for
  thinking mode; low temperature with thinking causes repetition loops. Thinking is
  stripped before the assistant turn goes back into the history.

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
