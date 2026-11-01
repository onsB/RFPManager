import json
import time
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from app.config import settings

RUNS_DIR = Path(__file__).parent.parent / "runs"  # <project>/runs, wherever the app is started from

class CallRecord(BaseModel):
    """measure tokens, latency, price, and timestamp for a single LLM call"""
    step: str
    section_id: str | None
    section_title: str | None = None
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cost_usd: float


class RunTrace(BaseModel):
    """an LLM run trace saved to runs/{run_id}.json, for later analysis"""

    run_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S"))
    document: str
    model: str = settings.llm_model
    temperature: float = settings.llm_temperature
    max_document_chars: int = settings.max_document_chars
    max_section_chars: int = settings.max_section_chars  # changes how sections are split, so what S12 means
    calls: list[CallRecord] = []


    def totals(self) -> dict:
        prompt = sum(c.prompt_tokens for c in self.calls)
        completion = sum(c.completion_tokens for c in self.calls)
        latency = sum(c.latency_s for c in self.calls)
        tokens_per_s = round(completion / latency, 1) if latency else 0
        return {
            "calls": len(self.calls),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "latency_s": round(latency, 1),
            "tokens_per_s": tokens_per_s,
            "cost_usd": round(sum(c.cost_usd for c in self.calls), 6)
        }

    def save(self, directory: str | Path = RUNS_DIR) -> Path:
        """Writes the whole run (settings, totals, then every call) to one JSON file."""
        path = Path(directory) / f"{self.run_id}.json"
        path.parent.mkdir(exist_ok=True)
        data = {
            **self.model_dump(exclude={"calls"}),  # run_id, document, model, settings
            "totals": self.totals(),
            "calls": [c.model_dump() for c in self.calls],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path


def traced_completion(
    client,
    trace: RunTrace | None,
    step: str,
    section_id: str | None = None,
    section_title: str | None = None,
    **kwargs,
):
    """wraps the LLM run to record tokens, latency, and cost in a RunTrace"""
    start = time.perf_counter()
    result = client.chat.completions.create(**kwargs)
    latency = time.perf_counter() - start

    usage = result.usage
    prompt = usage.prompt_tokens if usage else 0
    completion = usage.completion_tokens if usage else 0
    cost_usd = (prompt * settings.price_in_per_1m + completion * settings.price_out_per_1m) / 1_000_000

    if trace is not None:
        trace.calls.append(
            CallRecord(
                step=step,
                section_id=section_id,
                section_title=section_title,
                model=result.model,
                prompt_tokens=prompt,
                completion_tokens=completion,
                latency_s=round(latency,2),
                cost_usd=cost_usd
            )
        )
    return result