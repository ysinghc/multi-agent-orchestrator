"""Regression tests for defects found by end-to-end testing."""

import pytest

from orchestrator import cli
from orchestrator.config import GraphConfig
from orchestrator.offline import OfflineModel
from orchestrator.parsing import parse_json_object
from orchestrator.runner import run_task
from orchestrator.tools import KnowledgeBase, calculate, calculator_tool, knowledge_tool

TASK = "Compute 30 * 24 * 3 * 0.12 and summarise our autoscaling policy"


def _tools(kb=None):
    kb = kb or KnowledgeBase.from_dir(cli.DEFAULT_CORPUS)
    return [calculator_tool(), knowledge_tool(kb)]


def test_zero_budget_makes_no_model_call():
    result = run_task(TASK, OfflineModel(), _tools(), GraphConfig(max_llm_calls=0))
    assert result.trace["llm_calls"] == 0
    assert result.status == "budget_exhausted"


def test_exhausted_budget_still_returns_a_non_empty_answer():
    result = run_task(TASK, OfflineModel(), _tools(), GraphConfig(max_llm_calls=1))
    assert result.status == "budget_exhausted"
    assert result.final_answer.strip()


def test_offline_writer_labels_unsourced_findings_as_none():
    kb = KnowledgeBase({"unrelated": "Nothing here matches the question."})
    result = run_task("Summarise our autoscaling policy", OfflineModel(), _tools(kb))
    assert "calculation" not in result.final_answer
    assert "[1] none" in result.final_answer


def test_json_is_found_after_stray_braces_in_prose():
    text = 'Note {1} then {"action": "finish", "action_input": "4"}'
    assert parse_json_object(text) == {"action": "finish", "action_input": "4"}


def test_json_is_found_when_a_stray_brace_follows_it():
    assert parse_json_object('{"action": "finish"} and a closing } brace') == {"action": "finish"}


def test_calculator_rejects_results_too_large_to_be_reasonable():
    with pytest.raises(ValueError):
        calculate("(10**100)**100")  # about 33,000 bits


def test_calculator_tool_reports_float_overflow_as_an_observation():
    observation, sources = calculator_tool().run("(10.0**100)**100")
    assert observation.startswith("error:")
    assert sources == []


def test_calculator_prints_integers_exactly_and_truncates_only_huge_ones():
    # Printing must not convert to float, which overflows for integers this large.
    assert calculator_tool().run("10**20")[0] == str(10**20)
    assert calculator_tool().run("10**100")[0].endswith("(101 digits)")


def test_knowledge_base_matches_inflected_words_and_document_titles():
    kb = KnowledgeBase(
        {
            "caching": "Product pages are cached in Redis for 10 minutes.",
            "autoscaling": "Scale out when CPU utilisation is high. Policy: 3 to 12 replicas.",
        }
    )
    hits = kb.search("Summarise our caching policy", k=1)
    assert hits[0][0] == "caching"


def test_bundled_corpus_ships_inside_the_package():
    from importlib import resources

    corpus = resources.files("orchestrator") / "corpus"
    assert corpus.is_dir()
    assert len(list(corpus.iterdir())) == 3


def test_missing_corpus_directory_is_an_error_not_an_empty_knowledge_base(tmp_path):
    with pytest.raises(FileNotFoundError):
        KnowledgeBase.from_dir(tmp_path / "does-not-exist")


def test_cli_reports_a_missing_corpus_cleanly(tmp_path):
    with pytest.raises(SystemExit, match="corpus"):
        cli.main([TASK, "--corpus", str(tmp_path / "nope")])


def test_cli_reports_an_unavailable_gemini_backend_without_a_traceback(monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("Your default credentials were not found")

    monkeypatch.setattr(cli, "GeminiChat", broken)
    with pytest.raises(SystemExit, match="application-default login"):
        cli.main([TASK, "--provider", "gemini"])
