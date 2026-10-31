import time
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from app.config import settings

class CallRecord(BaseModel):
    """measure tokens, latency, price, and timestamp for a single LLM call"""
    step: str
    section_id: str | None 
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cost_usd: float


class RunTrace(BaseModel):
    """an LLM run trace saved to runs/{run_id}.json, for later analysis"""

    run_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d-%H%M%S"))
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
            "latency_s": latency,
            "tokens_per_s": tokens_per_s,
            "cost_usd": round(sum(c.cost_usd for c in self.calls), 6)
        }

    def save(self, directory: str | Path) -> Path:
        path = Path(directory) / f"{self.run_id}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text("".join(c.model_dump_json() + "\n" for c in self.calls), encoding="utf-8")
        return path


def traced_completion(client, trace: RunTrace | None, step: str, section_id: str | None = None, **kwargs):
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
                model=result.model,
                prompt_tokens=prompt,
                completion_tokens=completion,
                latency_s=round(latency,2),
                cost_usd=cost_usd
            )
        )
    return result