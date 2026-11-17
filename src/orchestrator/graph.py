"""The supervisor graph: plan, delegate to workers, write, self-critique, and revise within budgets.

Topology
    plan (supervisor) -> [research (worker, runs ReAct subgraph) -> supervisor routing]* -> write
    write -> critique -> write (revise, bounded) | finish

Hierarchy: the supervisor owns the plan and the routing decision. Research workers delegate tool
use to their own ReAct subgraph. Writer and critic are separate roles, so the critic never sees
its own draft as authoritative.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer

from orchestrator import prompts
from orchestrator.config import GraphConfig
from orchestrator.llm import ChatModel
from orchestrator.parsing import parse_critique, parse_plan
from orchestrator.react import build_react_graph
from orchestrator.state import OrchestratorState
from orchestrator.telemetry import step_event
from orchestrator.tools import Tool


def build_graph(
    llm: ChatModel,
    tools: Iterable[Tool],
    config: GraphConfig | None = None,
    *,
    checkpointer: Checkpointer | None = None,
    interrupt_before: Sequence[str] | None = None,
) -> Any:
    cfg = config or GraphConfig()
    tool_map = {t.name: t for t in tools}
    react_app = build_react_graph(llm, tool_map, cfg.pricing)

    def over_budget(state: OrchestratorState) -> bool:
        return (
            state.get("llm_calls", 0) >= cfg.max_llm_calls
            or state.get("cost_usd", 0.0) >= cfg.max_cost_usd
        )

    def plan(state: OrchestratorState) -> dict[str, Any]:
        started = perf_counter()
        if over_budget(state):  # the budget applies to the planner too; fall back to the raw task
            skipped = step_event(
                "plan.skipped", "supervisor", started, perf_counter(), None, cfg.pricing
            )
            return {
                "plan": [state["task"]],
                "cursor": 0,
                "status": "budget_exhausted",
                "events": [skipped],
            }
        response = llm.complete(prompts.PLANNER, f"Task: {state['task']}")
        subtasks = parse_plan(response.text, cfg.max_subtasks) or [state["task"]]
        event = step_event(
            "plan",
            "supervisor",
            started,
            perf_counter(),
            response.usage,
            cfg.pricing,
            subtasks=len(subtasks),
        )
        return {
            "plan": subtasks,
            "cursor": 0,
            "llm_calls": 1,
            "cost_usd": event["cost_usd"],
            "events": [event],
        }

    def route_supervisor(state: OrchestratorState) -> str:
        if state.get("status") == "budget_exhausted":
            return "finish"
        if state.get("cursor", 0) < len(state.get("plan", [])):
            return "research"
        return "write"

    def research(state: OrchestratorState) -> dict[str, Any]:
        started = perf_counter()
        subtask = state["plan"][state["cursor"]]
        remaining = cfg.max_llm_calls - state.get("llm_calls", 0)
        if remaining <= 0 or state.get("cost_usd", 0.0) >= cfg.max_cost_usd:
            skipped = step_event(
                "research.skipped",
                "worker",
                started,
                perf_counter(),
                None,
                cfg.pricing,
                subtask=subtask,
            )
            return {
                "status": "budget_exhausted",
                "cursor": state["cursor"] + 1,
                "events": [skipped],
            }

        result = react_app.invoke(
            {
                "subtask": subtask,
                "max_steps": min(cfg.max_react_steps, remaining),
                "steps": 0,
                "scratchpad": [],
                "sources": [],
                "llm_calls": 0,
                "cost_usd": 0.0,
                "events": [],
            }
        )
        sources = list(dict.fromkeys(result.get("sources", [])))
        suffix = f" (sources: {', '.join(sources)})" if sources else ""
        finding = f"{subtask} -> {result['answer']}{suffix}"
        marker = step_event(
            "research",
            "worker",
            started,
            perf_counter(),
            None,
            cfg.pricing,
            subtask=subtask,
            react_steps=result.get("steps", 0),
        )
        return {
            "findings": [finding],
            "cursor": state["cursor"] + 1,
            "llm_calls": result.get("llm_calls", 0),
            "cost_usd": result.get("cost_usd", 0.0),
            "events": [*result["events"], marker],
        }

    def write(state: OrchestratorState) -> dict[str, Any]:
        started = perf_counter()
        findings = state.get("findings", [])
        if over_budget(state):
            draft = "\n".join(f"- {f}" for f in findings)  # deterministic fallback, no model call
            skipped = step_event(
                "write.skipped", "worker", started, perf_counter(), None, cfg.pricing
            )
            return {"draft": draft, "status": "budget_exhausted", "events": [skipped]}

        revision = state.get("revisions", 0)
        feedback = state.get("critique", {}).get("issues", []) if revision else []
        response = llm.complete(prompts.WRITER, _writer_input(state["task"], findings, feedback))
        event = step_event(
            "write",
            "worker",
            started,
            perf_counter(),
            response.usage,
            cfg.pricing,
            revision=revision,
        )
        return {
            "draft": response.text,
            "llm_calls": 1,
            "cost_usd": event["cost_usd"],
            "events": [event],
        }

    def critique(state: OrchestratorState) -> dict[str, Any]:
        started = perf_counter()
        if over_budget(state):
            skipped = step_event(
                "critique.skipped", "worker", started, perf_counter(), None, cfg.pricing
            )
            return {
                "critique": {"score": None, "issues": ["skipped: budget exhausted"]},
                "status": "budget_exhausted",
                "events": [skipped],
            }

        findings = "\n".join(f"{i}. {f}" for i, f in enumerate(state.get("findings", []), 1))
        user = f"Task: {state['task']}\nDraft:\n{state.get('draft', '')}\nFindings:\n{findings}"
        response = llm.complete(prompts.CRITIC, user)
        review = parse_critique(response.text)
        approved = review["score"] >= cfg.approve_score
        event = step_event(
            "critique",
            "worker",
            started,
            perf_counter(),
            response.usage,
            cfg.pricing,
            score=review["score"],
            approved=approved,
        )
        return {
            "critique": {**review, "approved": approved},
            "revisions": state.get("revisions", 0) + (0 if approved else 1),
            "llm_calls": 1,
            "cost_usd": event["cost_usd"],
            "events": [event],
        }

    def route_after_critique(state: OrchestratorState) -> str:
        if state.get("status") == "budget_exhausted":
            return "finish"
        if state.get("critique", {}).get("approved"):
            return "finish"
        if state.get("revisions", 0) > cfg.max_revisions:
            return "finish"  # rewrites exhausted; finish with status revision_limit
        return "write"

    def finish(state: OrchestratorState) -> dict[str, Any]:
        started = perf_counter()
        status = state.get("status", "running")
        if status == "running":
            approved = state.get("critique", {}).get("approved", False)
            status = "completed" if approved else "revision_limit"
        answer = state.get("draft") or "\n".join(f"- {f}" for f in state.get("findings", []))
        if not answer.strip():
            answer = (
                f"No answer was produced: the run stopped with status '{status}' before any "
                "research or drafting finished. Raise the call budget and try again."
            )
        event = step_event(
            "finish", "supervisor", started, perf_counter(), None, cfg.pricing, status=status
        )
        return {"final_answer": answer, "status": status, "events": [event]}

    builder = StateGraph(OrchestratorState)
    builder.add_node("plan", plan)
    builder.add_node("research", research)
    builder.add_node("write", write)
    builder.add_node("critique", critique)
    builder.add_node("finish", finish)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges(
        "plan", route_supervisor, {"research": "research", "write": "write", "finish": "finish"}
    )
    builder.add_conditional_edges(
        "research", route_supervisor, {"research": "research", "write": "write", "finish": "finish"}
    )
    builder.add_edge("write", "critique")
    builder.add_conditional_edges(
        "critique", route_after_critique, {"write": "write", "finish": "finish"}
    )
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer, interrupt_before=list(interrupt_before or []))


def _writer_input(task: str, findings: list[str], feedback: list[str]) -> str:
    numbered = "\n".join(f"{i}. {f}" for i, f in enumerate(findings, start=1))
    text = f"Task: {task}\nFindings:\n{numbered}"
    if feedback:
        text += "\nReviewer feedback (address every point):\n" + "\n".join(
            f"- {x}" for x in feedback
        )
    return text
