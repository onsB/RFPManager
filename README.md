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
| `LLM_MODEL` | `qwen3-8b` | Model identifier in LM Studio |

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

### Troubleshooting

- **Connection error**: the LM Studio server is not running, or not on port 1234.
- **Model not found**: `LLM_MODEL` in `.env` does not match the identifier in LM Studio.
  `.env` overrides the defaults in `app/config.py`.
- **`No module named app`**: run `uv sync`, and in VS Code select the `.venv` interpreter.
