"""ReAct worker: a LangGraph subgraph that alternates reasoning and tool use until it can finish."""

from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph

from orchestrator import prompts
from orchestrator.config import Pricing
from orchestrator.llm import ChatModel
from orchestrator.parsing import parse_json_object
from orchestrator.state import ReActState
from orchestrator.telemetry import step_event
from orchestrator.tools import Tool


def build_react_graph(llm: ChatModel, tools: Mapping[str, Tool], pricing: Pricing) -> Any:
    def think(state: ReActState) -> dict[str, Any]:
        started = perf_counter()
        history = "\n".join(state.get("scratchpad", [])) or "(none yet)"
        user = f"Subtask: {state['subtask']}\nSteps so far:\n{history}"
        response = llm.complete(prompts.react_system(tools.values()), user)
        parsed = parse_json_object(response.text)

        update: dict[str, Any] = {"steps": 1, "llm_calls": 1}
        if parsed is None or "action" not in parsed:
            action = "invalid"
            update["scratchpad"] = [
                "Observation: reply must be one JSON object with 'action' and 'action_input'."
            ]
        else:
            action = str(parsed["action"]).strip()
            action_input = str(parsed.get("action_input", "")).strip()
            thought = str(parsed.get("thought", "")).strip()
            update["action_input"] = action_input
            if action == "finish":
                update["answer"] = action_input
                update["scratchpad"] = [f"Thought: {thought}"]
            else:
                update["scratchpad"] = [f"Thought: {thought}\nAction: {action}[{action_input}]"]
        update["action"] = action

        event = step_event(
            "react.think",
            "worker",
            started,
            perf_counter(),
            response.usage,
            pricing,
            action=action,
        )
        update["cost_usd"] = event["cost_usd"]
        update["events"] = [event]
        return update

    def act(state: ReActState) -> dict[str, Any]:
        started = perf_counter()
        name = state["action"]
        tool = tools.get(name)
        if tool is None:
            observation = f"unknown tool '{name}'. Choose one of {sorted(tools)} or finish."
            sources: list[str] = []
        else:
            try:
                observation, sources = tool.run(state.get("action_input", ""))
            except Exception as exc:  # a failing tool is an observation the agent can react to
                observation, sources = f"tool error: {exc}", []
        event = step_event("react.act", "tool", started, perf_counter(), None, pricing, tool=name)
        return {
            "scratchpad": [f"Observation: {observation}"],
            "sources": sources,
            "events": [event],
        }

    def finalize(state: ReActState) -> dict[str, Any]:
        started = perf_counter()
        observations = [s for s in state.get("scratchpad", []) if s.startswith("Observation: ")]
        best = observations[-1].removeprefix("Observation: ") if observations else "none"
        event = step_event("react.finalize", "worker", started, perf_counter(), None, pricing)
        return {
            "answer": f"Step limit reached. Best evidence so far: {best}",
            "events": [event],
        }

    def route_after_think(state: ReActState) -> str:
        if state.get("action") == "finish":
            return END
        if state.get("steps", 0) >= state.get("max_steps", 1):
            return "finalize"
        if state.get("action") == "invalid":
            return "think"  # recoverable: the agent sees the format error and tries again
        return "act"

    builder = StateGraph(ReActState)
    builder.add_node("think", think)
    builder.add_node("act", act)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "think")
    builder.add_conditional_edges(
        "think",
        route_after_think,
        {"act": "act", "think": "think", "finalize": "finalize", END: END},
    )
    builder.add_edge("act", "think")
    builder.add_edge("finalize", END)
    return builder.compile()
