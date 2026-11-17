from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.config import GraphConfig
from orchestrator.graph import build_graph
from orchestrator.llm import LLMResponse, Usage
from orchestrator.offline import OfflineModel
from orchestrator.runner import initial_state, run_task
from orchestrator.tools import KnowledgeBase, calculator_tool, knowledge_tool

CORPUS = Path(__file__).resolve().parents[1] / "examples" / "corpus"
TASK = "Compute 30 * 24 * 3 * 0.12 and summarise our autoscaling policy"


def _tools():
    return [calculator_tool(), knowledge_tool(KnowledgeBase.from_dir(CORPUS))]


class StubbornCritic:
    """Always rejects, so the revision limit is the only way out of the loop."""

    name = "stubborn-critic"

    def __init__(self):
        self._inner = OfflineModel()

    def complete(self, system, user):
        if "ROLE: critic" in system:
            reply = '{"score": 3, "issues": ["still weak"]}'
            return LLMResponse(reply, Usage(10, 8, 0.001))
        return self._inner.complete(system, user)


def test_full_run_plans_delegates_critiques_and_revises_once():
    result = run_task(TASK, OfflineModel(), _tools())

    assert result.status == "completed"
    assert result.revisions == 1
    assert "259.2" in result.final_answer
    assert "Sources:" in result.final_answer
    assert len(result.findings) == 2  # one finding per research subtask

    path = result.trace["path"]
    assert path[0] == "plan"
    assert path[-1] == "finish"
    assert path.count("write") == 2  # first draft rejected, second accepted
    assert path.count("critique") == 2
    assert path.count("react.act") == 2  # calculator and knowledge base


def test_llm_call_count_in_trace_matches_the_expected_control_flow():
    result = run_task(TASK, OfflineModel(), _tools())
    # plan(1) + two ReAct workers at two calls each (4) + write x2 + critique x2
    assert result.trace["llm_calls"] == 9


def test_budget_guard_stops_the_run_and_still_returns_findings():
    config = GraphConfig(max_llm_calls=3)
    result = run_task(TASK, OfflineModel(), _tools(), config)

    assert result.status == "budget_exhausted"
    assert result.trace["llm_calls"] <= 3
    assert "259.2" in result.final_answer  # deterministic fallback, no extra model call
    assert "research.skipped" in result.trace["path"]


def test_revision_limit_ends_the_loop_with_status_revision_limit():
    graph = build_graph(StubbornCritic(), _tools(), GraphConfig(max_revisions=2))
    state = graph.invoke(initial_state(TASK), {"configurable": {"thread_id": "stubborn"}})

    assert state["status"] == "revision_limit"
    assert state["revisions"] == 3  # 2 allowed rewrites, the third rejection stops the loop
    write_events = [e for e in state["events"] if e["node"] == "write"]
    assert len(write_events) == 3  # initial draft plus two revisions


def test_human_in_the_loop_pauses_before_writing_and_accepts_an_edit():
    graph = build_graph(
        OfflineModel(), _tools(), checkpointer=MemorySaver(), interrupt_before=["write"]
    )
    cfg = {"configurable": {"thread_id": "review-1"}}
    graph.invoke(initial_state(TASK), cfg)

    paused = graph.get_state(cfg)
    assert paused.next == ("write",)
    assert len(paused.values["findings"]) == 2

    # A reviewer adds a finding; it is written into state exactly as if the worker had produced it.
    graph.update_state(
        cfg, {"findings": ["Reviewer note -> the SLA is 99.9 percent"]}, as_node="research"
    )
    while graph.get_state(cfg).next:  # each draft pauses for review until the critic approves
        graph.invoke(None, cfg)

    final = graph.get_state(cfg).values
    assert final["status"] == "completed"
    assert "99.9 percent" in final["final_answer"]


def test_state_cost_equals_the_sum_of_per_step_trace_costs():
    checkpointer = MemorySaver()
    graph = build_graph(OfflineModel(), _tools(), checkpointer=checkpointer)
    cfg = {"configurable": {"thread_id": "costs"}}
    state = graph.invoke(initial_state(TASK), cfg)

    per_step = sum(e["cost_usd"] for e in state["events"])
    assert state["cost_usd"] == pytest.approx(per_step, rel=1e-9)
    assert all(
        {"node", "role", "llm", "duration_s", "prompt_tokens", "completion_tokens"} <= e.keys()
        for e in state["events"]
    )
