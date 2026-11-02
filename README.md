# RFP Manager

Agentic application that reads an RFP brief and produces a structured solution summary
(requirements, approach, risks). It runs on a local open-source LLM, so no paid API key is needed.

## Running the app

### Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (installs Python 3.12 and the dependencies for you)
- [LM Studio](https://lmstudio.ai/) to run the model locally

### 1. Start the model in LM Studio

1. In LM Studio, download **Qwen3 8B** (`qwen/qwen3-8b`).
2. Open the **Developer** tab, load the model and click **Start Server**.
   It should listen on `http://localhost:1234`.

### 2. Install the project

```bash
git clone <repo-url>
cd RFPManager
uv sync
```

### 3. Configure

```bash
cp .env.example .env
```

`LLM_MODEL` must match the model identifier shown in LM Studio. Any model that supports
structured output works; to try another one, change this value only.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible endpoint (LM Studio) |
| `LLM_API_KEY` | `lm-studio` | Ignored by LM Studio, required by the SDK |
| `LLM_MODEL` | `qwen/qwen3-8b` | Model identifier in LM Studio |
| `JUDGE_MODEL` | *(empty)* | Model for the faithfulness judge; empty reuses `LLM_MODEL` |
| `LIVE_JUDGE` | `true` | Judge every requirement in normal runs, after the brief is shown (review flags fill in a few minutes later) |

### 4. Run

**Web demo**

```bash
uv run python -m app.api
```

Open http://127.0.0.1:8000, upload an RFP (PDF, DOCX, TXT or MD) and click
**Extract requirements**. Sections fill in as they finish; each requirement shows its
category, whether it is mandatory, and whether its quote was found in the document.
API docs are at http://127.0.0.1:8000/docs.

**Command line**

```bash
uv run python -m app.main inputs/InvitationtoTender_CommunitiesofPracticeDevelopment.pdf
```

Without an argument it uses `RFP_PATH` and `SECTION_IDS` at the top of `app/main.py`,
so it can also be started with VS Code's Run button.

### 5. Evaluate

```bash
uv run python -m eval.harness            # with the LLM judge (~2 min)
uv run python -m eval.harness --no-judge # extraction metrics only
```

Runs extraction on every brief with gold labels in `eval/gold/` and writes a report to
`eval/results/<run_id>_<brief>.md` (and `.json`). See [Evaluation](#evaluation).

### Troubleshooting

- **Connection error**: the LM Studio server is not running, or not on port 1234.
- **Model not found**: `LLM_MODEL` in `.env` does not match the identifier in LM Studio.
  `.env` overrides the defaults in `app/config.py`.
- **`No module named app`**: run `uv sync`, and in VS Code select the `.venv` interpreter.

## Evaluation

Two layers: **online** checks on every run (no gold labels needed), and an **offline**
harness that scores extraction against gold labels on a test brief.

### Online: every run

Each requirement is checked as soon as its section is extracted (`app/quality.py`):

| Check | How |
|---|---|
| Quote found | The quote appears in the section text (deterministic) |
| Faithful | The LLM judge says the description states the same content as its quote |
| Duplicate | Its quote overlaps an earlier requirement's quote (deterministic) |
| Summary grounding | No made-up requirement ids; every mandatory requirement is planned |

Flagged requirements are highlighted in the web page and CLI with the judge's reason.
The run's quality report (rates, verdict counts, ids that need review) is shown at the
end and saved in the run trace (`runs/<run_id>.json`, key `quality`).

### Offline: gold-label harness

`eval/harness.py` scores the extraction step against hand-written gold labels.

**Gold set.** `eval/briefs/synthetic_volunteer_platform.md` is a synthetic ITT where every
requirement is known by construction (`eval/gold/synthetic_volunteer_platform.json`):
21 requirements to extract, 1 optional item (neither rewarded nor penalised), and 5
forbidden items that must not be extracted. Items are tagged with the trap they test:
"should" vs "must", list items to split, a prohibition, "desirable but not essential",
a budget cap, milestones in a table, relaxations ("CVs are not required"), permissions
("consortia are welcome") and the client's own goals.

**Matching.** An extracted requirement matches a gold item when at least 60% of the shorter
quote's content words appear in the other, one-to-one, best overlap first. A second
extraction of the same item counts as a duplicate (false positive).

**Metrics.**

| Metric | What it measures |
|---|---|
| Precision / recall / F1 | Right requirements found, nothing extra |
| Mandatory accuracy | `mandatory` matches the gold label (on matched items) |
| Category accuracy | Category is one of the gold's accepted categories |
| Quotes found | Quote appears in the section text (grounding check) |
| Faithful descriptions | LLM judge: description states the same content as its quote |
| Trap scoreboard | Pass/fail per planted trap |

Each result records the git commit, a hash of the extraction prompt, the model and the
judge, so scores can be compared across prompt changes. Token usage, latency and
estimated cost are reported per step (extraction, judge).

**Latest result** (`qwen/qwen3-8b`, judge `qwen/qwen3-8b`): precision 88%, recall 100%,
mandatory accuracy 71%, faithful descriptions 84%. Full report in `eval/results/`.

