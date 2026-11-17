"""Tools available to ReAct workers: a safe calculator and a keyword-searchable knowledge base."""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ToolRun = Callable[[str], tuple[str, list[str]]]  # input -> (observation, source ids)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: ToolRun


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_EXPONENT = 100


def calculate(expression: str) -> float:
    """Evaluate arithmetic by walking the AST. Names, calls and attributes are rejected."""
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval(tree.body)


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        if isinstance(node.value, bool):
            raise ValueError("booleans are not allowed")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    raise ValueError("unsupported expression")


def calculator_tool() -> Tool:
    def run(expression: str) -> tuple[str, list[str]]:
        try:
            value = calculate(expression)
        except ZeroDivisionError:
            return "error: division by zero", []
        except (SyntaxError, ValueError) as exc:
            return f"error: {exc}", []
        return f"{value:g}", []

    return Tool(
        "calculator",
        "Evaluate an arithmetic expression such as '30 * 24 * 0.12'. Input: the expression.",
        run,
    )


_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are for in is it of on or our the to what how does do with".split())


def _clip(text: str, limit: int) -> str:
    """Shorten to at most `limit` characters, ending on a word boundary."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " ..."


def _body(text: str) -> str:
    """Collapse a markdown document to one line of body text, dropping its leading heading."""
    lines = text.strip().splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return " ".join(" ".join(lines).split())


class KnowledgeBase:
    def __init__(self, documents: dict[str, str]) -> None:
        self._documents = documents

    @classmethod
    def from_dir(cls, path: str | Path) -> KnowledgeBase:
        docs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(Path(path).glob("*.md"))}
        return cls(docs)

    def search(self, query: str, k: int = 1) -> list[tuple[str, str]]:
        terms = {t for t in _WORD.findall(query.lower()) if t not in _STOP}
        scored = []
        for doc_id, text in self._documents.items():
            words = set(_WORD.findall(text.lower()))
            score = len(terms & words)
            if score:
                scored.append((score, doc_id, text))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(doc_id, _body(text)) for _, doc_id, text in scored[:k]]


def knowledge_tool(kb: KnowledgeBase) -> Tool:
    def run(query: str) -> tuple[str, list[str]]:
        hits = kb.search(query, k=1)
        if not hits:
            return "no matching documents", []
        doc_id, text = hits[0]
        return f"[{doc_id}] {_clip(text, 300)}", [doc_id]

    return Tool(
        "search_kb",
        "Search the internal knowledge base. Input: a short keyword query.",
        run,
    )
