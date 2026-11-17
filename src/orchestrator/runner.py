"""Run a task end to end and return a structured result with its trace."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from orchestrator.config import GraphConfig
from orchestrator.graph import build_graph
from orchestrator.llm import ChatModel
from orchestrator.telemetry import summarize
from orchestrator.tools import Tool


@dataclass(frozen=True)
class RunResult:
    thread_id: str
    status: str
    final_answer: str
    findings: list[str]
    revisions: int
    critique: dict[str, Any]
    trace: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)


def initial_state(task: str) -> dict[str, Any]:
    return {
        "task": task,
        "status": "running",
        "findings": [],
        "revisions": 0,
        "llm_calls": 0,
        "cost_usd": 0.0,
        "events": [],
    }


def result_from_state(thread_id: str, state: dict[str, Any]) -> RunResult:
    events = list(state.get("events", []))
    return RunResult(
        thread_id=thread_id,
        status=state.get("status", "unknown"),
        final_answer=state.get("final_answer", ""),
        findings=list(state.get("findings", [])),
        revisions=state.get("revisions", 0),
        critique=state.get("critique", {}),
        trace=summarize(events),
        events=events,
    )


def run_task(
    task: str,
    llm: ChatModel,
    tools: Iterable[Tool],
    config: GraphConfig | None = None,
    thread_id: str | None = None,
) -> RunResult:
    graph = build_graph(llm, tools, config, checkpointer=MemorySaver())
    thread = thread_id or uuid4().hex[:12]
    state = graph.invoke(initial_state(task), {"configurable": {"thread_id": thread}})
    return result_from_state(thread, state)
