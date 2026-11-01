from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = "lm-studio"  # LM Studio ignores it, but the SDK requires one
    llm_model: str = "qwen/qwen3-8b"  # the model identifier shown in LM Studio
    llm_temperature: float = 0.2

    # Local models have small context windows; longer documents are truncated for now.
    max_document_chars: int = 40_000
    max_section_chars: int = 8_000  # ~2k tokens per section

    # Local inference is free; cost is estimated at a hosted provider's price for the same model.
    price_in_per_1m: float = 0.0   # USD per 1M prompt tokens
    price_out_per_1m: float = 0.0  # USD per 1M completion tokens


settings = Settings()
