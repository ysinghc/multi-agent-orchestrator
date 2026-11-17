import pytest

from orchestrator.parsing import parse_critique, parse_json_object, parse_plan
from orchestrator.tools import KnowledgeBase, calculate, calculator_tool, knowledge_tool


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 + 3 * 4", 14), ("(1 + 2) ** 3", 27), ("-7 // 2", -4), ("10 % 4", 2), ("2 ** -1", 0.5)],
)
def test_calculator_matches_python_for_plain_arithmetic(expression, expected):
    assert calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    ["__import__('os').system('id')", "open('x')", "abs(-1)", "x + 1", "True + 1", "2 ** 1000"],
)
def test_calculator_rejects_names_calls_booleans_and_huge_powers(expression):
    with pytest.raises(ValueError):
        calculate(expression)


def test_calculator_tool_reports_errors_as_observations():
    run = calculator_tool().run
    assert run("30 * 24 * 3 * 0.12") == ("259.2", [])
    assert run("1 / 0") == ("error: division by zero", [])
    assert run("import os")[0].startswith("error:")


def test_knowledge_base_returns_best_document_body_without_heading():
    kb = KnowledgeBase(
        {
            "caching": "# Caching\n\nProduct pages are cached in Redis for 10 minutes.",
            "autoscaling": "# Autoscaling\n\nScale out at 70 percent CPU.",
        }
    )
    hits = kb.search("how long are product pages cached", k=1)
    assert hits == [("caching", "Product pages are cached in Redis for 10 minutes.")]


def test_knowledge_tool_reports_no_match_and_records_sources():
    tool = knowledge_tool(KnowledgeBase({"oncall": "Pages escalate after 15 minutes."}))
    assert tool.run("zebra stripes") == ("no matching documents", [])
    observation, sources = tool.run("escalate pages")
    assert observation.startswith("[oncall] ")
    assert sources == ["oncall"]


def test_parse_json_object_finds_json_inside_prose_and_fences():
    text = 'Sure! ```json\n{"action": "finish", "action_input": "4"}\n``` thanks'
    assert parse_json_object(text) == {"action": "finish", "action_input": "4"}


@pytest.mark.parametrize("text", ["no braces here", "{not json}", "[1, 2, 3]"])
def test_parse_json_object_returns_none_when_no_object_present(text):
    assert parse_json_object(text) is None


def test_parse_plan_dedupes_trims_and_limits():
    text = '{"subtasks": ["Find refunds", "find refunds", "  ", "Check SLA", "Third", "Fourth"]}'
    assert parse_plan(text, limit=3) == ["Find refunds", "Check SLA", "Third"]


def test_parse_plan_tolerates_wrong_types():
    assert parse_plan('{"subtasks": "not a list"}', limit=4) == []
    assert parse_plan("garbage", limit=4) == []


def test_parse_critique_clamps_score_and_keeps_string_issues():
    review = parse_critique('{"score": 42, "issues": ["add sources", 7, ""]}')
    assert review == {"score": 10, "issues": ["add sources", "7"]}


def test_parse_critique_treats_invalid_output_as_zero():
    assert parse_critique("I think it is good")["score"] == 0
    assert parse_critique('{"score": "high"}')["score"] == 0
