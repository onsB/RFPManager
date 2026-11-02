from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = "lm-studio"  # LM Studio ignores it, but the SDK requires one
    llm_model: str = "qwen/qwen3-8b"  # the model identifier shown in LM Studio
    llm_temperature: float = 0.2

    # LLM judge used by the eval harness. Empty = reuse llm_model: light enough for a laptop
    # demo, at the cost of self-preference bias (see DECISIONS.md).
    judge_model: str = ""
    # Judge every requirement in normal runs too (online evaluation). Runs after the summary
    # is shown, so it doesn't delay the brief; the review flags fill in a few minutes later.
    # LIVE_JUDGE=false turns it off.
    live_judge: bool = True

    # Critic agent: reviews the draft brief with tools and sends it back for revision.
    # AGENT_REVIEW=false gives the fixed pipeline (draft only), for A/B comparisons.
    agent_review: bool = True
    agent_max_steps: int = 6  # LLM turns per review: the anti-looping guard on the tool loop
    max_review_rounds: int = 2  # review -> revise rounds before keeping the latest brief
    tool_result_chars: int = 4_000  # tool results are cut to this, so they can't flood the context

    # Local models have small context windows; longer documents are truncated for now.
    max_document_chars: int = 40_000
    max_section_chars: int = 8_000  # ~2k tokens per section
    # Sections with less text are merged into the next one: a heading-only section still
    # costs a full LLM call (3-8 s) and returns nothing.
    min_section_chars: int = 200
    # Sections whose title matches one of these (case-insensitive regex) are not sent to
    # the LLM: boilerplate that never states supplier obligations.
    skip_section_patterns: list[str] = [
        r"^(table of )?contents$",  # anchored: "Proposal contents" lists requirements
        r"\bglossary\b",
        r"\b(acronyms|abbreviations)\b",
        r"^authority$",
        r"\bfreedom of information\b|\bfoia\b",
        r"\bpublic (documents|disclosure|records)\b",
        r"\bprivacy notice\b",
        r"\bdisclaimer\b",
    ]

    # Output caps. A non-thinking extraction of an 8k-char section needs ~1.3k tokens; a
    # call that hits the cap is almost always the model looping, and is logged as such.
    max_output_tokens: int = 2048  # extraction and judge calls
    max_summary_tokens: int = 4096  # synthesis writes the whole approach and risks

    # Local inference is free; cost is estimated at Alibaba's hosted price for Qwen3 8B
    # (source and date in ASSUMPTIONS.md). Change both when switching models.
    price_in_per_1m: float = 0.18   # USD per 1M prompt tokens
    price_out_per_1m: float = 0.70  # USD per 1M completion tokens


settings = Settings()
