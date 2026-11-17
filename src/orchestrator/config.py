"""Limits and pricing. Budgets are enforced inside the graph, not left to the caller."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens. Replace with your model's current list price."""

    input_per_mtok: float = 0.30
    output_per_mtok: float = 2.50

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_per_mtok + completion_tokens * self.output_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class GraphConfig:
    max_subtasks: int = 4
    max_react_steps: int = 4  # model calls allowed per research subtask
    max_revisions: int = 2  # rewrites allowed after a rejected critique
    approve_score: int = 8  # critic score needed to accept a draft
    max_llm_calls: int = 20  # hard budget for the whole task
    max_cost_usd: float = 0.05  # hard budget for the whole task
    pricing: Pricing = field(default_factory=Pricing)
