import json

from orchestrator.config import Pricing
from orchestrator.offline import ScriptedModel
from orchestrator.react import build_react_graph
from orchestrator.tools import KnowledgeBase, calculator_tool, knowledge_tool


def _step(action: str, action_input: str, thought: str = "t") -> str:
    return json.dumps({"thought": thought, "action": action, "action_input": action_input})


def _run(replies, tools, subtask="subtask", max_steps=4):
    llm = ScriptedModel(replies)
    app = build_react_graph(llm, {t.name: t for t in tools}, Pricing())
    state = app.invoke(
        {
            "subtask": subtask,
            "max_steps": max_steps,
            "steps": 0,
            "scratchpad": [],
            "sources": [],
            "llm_calls": 0,
            "cost_usd": 0.0,
            "events": [],
        }
    )
    return state, llm


def test_think_act_think_finish_loop_uses_the_tool_result():
    state, llm = _run(
        [_step("calculator", "2 + 2"), _step("finish", "The answer is 4.")],
        [calculator_tool()],
    )
    assert state["answer"] == "The answer is 4."
    assert state["steps"] == 2
    assert state["llm_calls"] == 2
    assert [e["node"] for e in state["events"]] == ["react.think", "react.act", "react.think"]
    assert any("Observation: 4" in line for line in state["scratchpad"])
    assert len(llm.calls) == 2


def test_step_limit_forces_a_finalised_answer():
    state, llm = _run(
        [_step("search_kb", "x"), _step("search_kb", "y")],
        [calculator_tool()],  # search_kb is not registered, so every step is an error observation
        max_steps=2,
    )
    assert state["answer"].startswith("Step limit reached")
    assert len(llm.calls) == 2  # never more model calls than the budget allows
    assert state["events"][-1]["node"] == "react.finalize"


def test_malformed_reply_is_reported_back_and_the_agent_recovers():
    state, _ = _run(["this is not json", _step("finish", "done")], [calculator_tool()])
    assert state["answer"] == "done"
    assert any("must be one JSON object" in line for line in state["scratchpad"])


def test_tool_exceptions_become_observations_not_crashes():
    state, _ = _run(
        [_step("calculator", "1 / 0"), _step("finish", "handled")],
        [calculator_tool()],
    )
    assert state["answer"] == "handled"
    assert any("division by zero" in line for line in state["scratchpad"])


def test_knowledge_base_citations_flow_into_sources():
    kb = KnowledgeBase({"autoscaling": "The service scales out at 70 percent CPU."})
    state, _ = _run(
        [_step("search_kb", "scale out cpu"), _step("finish", "It scales out at 70 percent.")],
        [knowledge_tool(kb)],
    )
    assert state["sources"] == ["autoscaling"]
    assert state["answer"] == "It scales out at 70 percent."
