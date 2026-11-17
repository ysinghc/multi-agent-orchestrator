"""Typed graph state. Reducers (operator.add) make parallel-safe accumulation explicit."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ReActState(TypedDict, total=False):
    """State of the ReAct worker subgraph used for one research subtask."""

    subtask: str
    max_steps: int
    steps: Annotated[int, operator.add]
    scratchpad: Annotated[list[str], operator.add]
    sources: Annotated[list[str], operator.add]
    action: str
    action_input: str
    answer: str
    llm_calls: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]


class OrchestratorState(TypedDict, total=False):
    """Shared state of the supervisor graph. Every node reads from and writes to this."""

    task: str
    plan: list[str]
    cursor: int
    findings: Annotated[list[str], operator.add]
    draft: str
    critique: dict[str, Any]
    revisions: int
    final_answer: str
    status: str  # running | completed | revision_limit | budget_exhausted
    llm_calls: Annotated[int, operator.add]
    cost_usd: Annotated[float, operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
