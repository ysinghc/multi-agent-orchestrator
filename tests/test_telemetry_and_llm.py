from types import SimpleNamespace

import pytest

from orchestrator.config import Pricing
from orchestrator.llm import Usage
from orchestrator.telemetry import step_event, summarize


def test_step_event_for_a_model_call_computes_throughput_and_cost():
    event = step_event(
        "write",
        "worker",
        started=0.0,
        now=0.5,
        usage=Usage(prompt_tokens=1_000_000, completion_tokens=100, seconds=0.25),
        pricing=Pricing(input_per_mtok=0.30, output_per_mtok=2.50),
    )
    assert event["llm"] is True
    assert event["tokens_per_second"] == 400.0
    assert event["cost_usd"] == pytest.approx(0.30 + 100 * 2.50 / 1_000_000)


def test_step_event_without_a_model_call_has_no_throughput():
    event = step_event("finish", "supervisor", 0.0, 0.1, None, Pricing())
    assert event["llm"] is False
    assert event["tokens_per_second"] is None
    assert event["cost_usd"] == 0.0


def test_summarize_aggregates_only_model_steps():
    pricing = Pricing(input_per_mtok=1.0, output_per_mtok=1.0)
    events = [
        step_event("plan", "supervisor", 0, 1, Usage(100, 10, 0.1), pricing),
        step_event("react.act", "tool", 1, 2, None, pricing),
        step_event("write", "worker", 2, 3, Usage(200, 30, 0.3), pricing),
    ]
    summary = summarize(events)
    assert summary["llm_calls"] == 2
    assert summary["prompt_tokens"] == 300
    assert summary["completion_tokens"] == 40
    assert summary["tokens_per_second"] == pytest.approx(40 / 0.4, rel=1e-3)
    assert summary["path"] == ["plan", "react.act", "write"]


def test_gemini_chat_maps_provider_usage_metadata():
    pytest.importorskip("google.genai")
    from orchestrator.llm import GeminiChat

    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen.update(model=model, system=config.system_instruction)
            return SimpleNamespace(
                text="  Answer [1].  ",
                usage_metadata=SimpleNamespace(prompt_token_count=512, candidates_token_count=21),
            )

    chat = GeminiChat(model="gemini-test", client=SimpleNamespace(models=FakeModels()))
    response = chat.complete("ROLE: writer", "Task: x")
    assert response.text == "Answer [1]."
    assert (response.usage.prompt_tokens, response.usage.completion_tokens) == (512, 21)
    assert seen == {"model": "gemini-test", "system": "ROLE: writer"}
