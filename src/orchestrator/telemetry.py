"""Granular, per-step trace events stored in graph state, plus an aggregate summary."""

from __future__ import annotations

from typing import Any

from orchestrator.config import Pricing
from orchestrator.llm import Usage


def step_event(
    node: str,
    role: str,
    started: float,
    now: float,
    usage: Usage | None,
    pricing: Pricing,
    **detail: Any,
) -> dict[str, Any]:
    """One trace record per graph step. `llm` is True only when a model was called."""
    if usage is None:
        return {
            "node": node,
            "role": role,
            "llm": False,
            "duration_s": round(now - started, 6),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "generation_s": 0.0,
            "tokens_per_second": None,
            "cost_usd": 0.0,
            **detail,
        }
    tps = usage.completion_tokens / usage.seconds if usage.seconds > 0 else None
    return {
        "node": node,
        "role": role,
        "llm": True,
        "duration_s": round(now - started, 6),
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "generation_s": round(usage.seconds, 6),
        "tokens_per_second": round(tps, 2) if tps is not None else None,
        "cost_usd": round(pricing.cost(usage.prompt_tokens, usage.completion_tokens), 10),
        **detail,
    }


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    llm_events = [e for e in events if e["llm"]]
    completion = sum(e["completion_tokens"] for e in llm_events)
    generation_s = sum(e["generation_s"] for e in llm_events)
    return {
        "path": [e["node"] for e in events],
        "llm_calls": len(llm_events),
        "prompt_tokens": sum(e["prompt_tokens"] for e in llm_events),
        "completion_tokens": completion,
        "cost_usd": round(sum(e["cost_usd"] for e in llm_events), 8),
        "tokens_per_second": round(completion / generation_s, 2) if generation_s > 0 else None,
        "wall_clock_s": round(sum(e["duration_s"] for e in events), 6),
    }
