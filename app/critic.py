"""The critic agent: reviews the draft brief, calling tools in a capped loop.

This is the agentic step. The model decides which tools to call and when it has seen
enough; code caps the loop, runs the tools, and re-checks the verdict.
In its own module because the tools import from app.agent (which must not import them).
"""

import json
import re
import time

from pydantic import ValidationError

from app.agent import _load_prompt, client
from app.config import settings
from app.schemas import BLOCKING_KINDS, Review, ReviewIssue, RFPSummary
from app.telemetry import RunTrace, ToolCallRecord, traced_completion
from app.tools import AGENT_TOOL_SPECS, CONTEXT_TOOLS, ToolContext, call_tool

READING_TOOLS = {"search_rfp", "get_section"}  # tools that read the RFP text itself
PUSH_BACK = (
    "You haven't read the RFP text yet. Before answering, use search_rfp to confirm at least one "
    "point: a possible contradiction in the key facts, the evaluation criteria, or a risk's fact."
)

CRITIC_PROMPT = _load_prompt("critic")
# Qwen3's recommended sampling for thinking mode: greedy or low temperature makes it repeat itself.
THINKING_SAMPLING = {"temperature": 0.6, "top_p": 0.95}
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
ID_RE = re.compile(r"\bS\d+[a-z]?(?:-R\d+)?\b")  # S08, S13a, S08-R03


def _ids(text: str) -> set[str]:
    """Ids in a text, plus the section of each requirement id: seeing S08-R03 means seeing S08."""
    ids = set(ID_RE.findall(text))
    return ids | {i.split("-")[0] for i in ids}


class AgentLoopError(Exception):
    """The agent used all its steps without a final answer: the looping guard fired."""


class ReviewParseError(Exception):
    """The final answer wasn't a valid Review, even after one repair turn."""


def brief_markdown(summary: RFPSummary) -> str:
    """The draft brief as the critic reads it, with the requirement ids each item cites."""
    lines = [f"# {summary.project_title} ({summary.client})"]
    if summary.deadline:
        lines.append(f"Due: {summary.deadline.date} ({summary.deadline.label}, {summary.deadline.section_id})")
    lines += ["", summary.overview, "", "## Approach"]
    lines += [f"{n}. {p.phase}: {p.description} [{', '.join(p.requirement_ids)}]"
              for n, p in enumerate(summary.approach, start=1)]
    lines += ["", "## Risks"]
    lines += [f"{n}. ({r.severity}) {r.description} Mitigation: {r.mitigation} [{', '.join(r.requirement_ids)}]"
              for n, r in enumerate(summary.risks, start=1)]
    return "\n".join(lines)


def _strip_think(text: str | None) -> str:
    """Removes Qwen's <think> blocks; thinking is never sent back into the history."""
    text = text or ""
    if "<think>" in text and "</think>" not in text:  # cut off mid-thought: nothing usable
        return ""
    return THINK_RE.sub("", text).strip()


def _parse_review(text: str | None) -> Review:
    """The first JSON object in the answer, validated as a Review (raises ValueError or ValidationError)."""
    text = _strip_think(text)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in the answer")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return Review.model_validate(obj)


def _run_tool(ctx: ToolContext, name: str, raw_args: str, trace: RunTrace | None, agent: str) -> str:
    """Runs one tool call. Errors (bad JSON, unknown tool, bad arguments) go back to the model."""
    start, error = time.perf_counter(), None
    try:
        result = call_tool(ctx, name, json.loads(raw_args))
    except Exception as exc:  # 8B models send malformed arguments now and then
        error = f"{type(exc).__name__}: {exc}"
        result = f"ERROR: {error}. Fix the arguments and try again."
    if trace is not None:
        trace.tool_calls.append(ToolCallRecord(
            agent=agent, name=name, arguments=raw_args, result_chars=len(result),
            ms=round((time.perf_counter() - start) * 1000, 1), error=error,
        ))
    return result


def _call(messages: list[dict], trace: RunTrace | None, tools: bool = True, require_tool: bool = False):
    tool_args = {"tools": AGENT_TOOL_SPECS, "tool_choice": "required" if require_tool else "auto"} if tools else {}
    return traced_completion(
        client, trace, step="critic",
        model=settings.llm_model,
        max_tokens=settings.max_summary_tokens,
        messages=messages,
        **tool_args,
        **THINKING_SAMPLING,
    )


def _coverage_issue(coverage: dict) -> ReviewIssue | None:
    """The deterministic coverage check as one issue for the writer, instead of one per id."""
    uncovered = coverage["uncovered_mandatory"]
    if not uncovered:
        return None
    return ReviewIssue(
        kind="uncovered_mandatory",
        detail=f"{len(uncovered)} mandatory requirements are cited by no approach phase: "
               + "; ".join(f"{u['id']} ({u['description']})" for u in uncovered),
        evidence=[u["id"] for u in uncovered],
        fix="Cite each one in the phase that delivers it. If one is an action or right of the issuer, "
            "not the bidder (e.g. 'deliver the premises as-is'), leave it out: don't invent a phase or a risk for it.",
        source="code",
    )


def review_summary(ctx: ToolContext, trace: RunTrace | None) -> Review:
    """Runs the critic on ctx.summary until it answers, or raises after `agent_max_steps` turns.

    LM Studio can't combine tools with a strict response_format, so the final answer is
    free text: parsed as JSON, with one repair turn if that fails.
    """
    brief = brief_markdown(ctx.summary)
    # Deterministic checks run by code, not left to the model's choice (see CONTEXT_TOOLS).
    context = {name: _run_tool(ctx, name, "{}", trace, agent="code") for name in CONTEXT_TOOLS}
    messages = [
        {"role": "system", "content": CRITIC_PROMPT},
        {"role": "user", "content": (
            f"{brief}\n\n## Coverage check (run by code)\n\n{context['check_coverage']}\n\n"
            f"## Key facts (run by code)\n\n{context['get_key_facts']}\n\n"
            "/think"  # thinking on: this is where reasoning pays off
        )},
    ]
    seen_ids = _ids(messages[1]["content"])  # ids the critic has actually been shown
    read_rfp = pushed_back = False

    for step in range(settings.agent_max_steps):
        # The first turn must call a tool (the model picks which, and what to search): without
        # this, the 8B critic answered from the checks alone and never read the RFP.
        message = _call(messages, trace, require_tool=step == 0).choices[0].message
        if not message.tool_calls:
            if not read_rfp and not pushed_back:  # fallback if the server ignores tool_choice: send it back once
                pushed_back = True
                messages += [{"role": "assistant", "content": _strip_think(message.content)},
                             {"role": "user", "content": PUSH_BACK}]
                continue
            review = _finish(message.content, messages, seen_ids, trace)
            break
        messages.append({
            "role": "assistant",
            "content": _strip_think(message.content),
            "tool_calls": [tc.model_dump() for tc in message.tool_calls],
        })
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            result = _run_tool(ctx, name, tool_call.function.arguments or "{}", trace, agent="critic")
            read_rfp = read_rfp or (name in READING_TOOLS and not result.startswith("ERROR"))
            seen_ids.update(_ids(result))
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    else:
        raise AgentLoopError(f"critic gave no final answer within {settings.agent_max_steps} steps")

    # Coverage is reported by code, once, so the critic's issues are its own judgement.
    review.issues = [i for i in review.issues if i.kind != "uncovered_mandatory"]
    coverage = _coverage_issue(json.loads(context["check_coverage"]))
    if coverage:
        review.issues.insert(0, coverage)
    # The model sometimes approves while listing a blocking issue: code has the last word.
    review.approved = review.approved and not any(i.kind in BLOCKING_KINDS for i in review.issues)
    return review


def _finish(content: str | None, messages: list[dict], seen_ids: set[str], trace: RunTrace | None) -> Review:
    """Parses the final answer (one repair turn on failure), then re-checks it in code."""
    try:
        review = _parse_review(content)
    except (ValueError, ValidationError):
        messages += [
            {"role": "assistant", "content": _strip_think(content)},
            {"role": "user", "content": "Return only the JSON object described in the instructions, nothing else. /no_think"},
        ]
        try:
            review = _parse_review(_call(messages, trace, tools=False).choices[0].message.content)
        except (ValueError, ValidationError) as exc:
            raise ReviewParseError(f"critic answer isn't a valid review after a repair turn: {exc}") from exc

    # Hallucination guard: drop evidence ids the critic was never shown, and count them.
    unverified: set[str] = set()
    for issue in review.issues:
        unverified.update(e for e in issue.evidence if ID_RE.fullmatch(e) and e not in seen_ids)
        issue.evidence = [e for e in issue.evidence if e not in unverified]
    review.unverified_evidence = sorted(unverified)
    return review
