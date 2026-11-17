"""Tolerant parsing of model output. Models do not always return clean JSON."""

from __future__ import annotations

import json
from typing import Any


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Return the first top-level JSON object found in `text`, or None."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def parse_plan(text: str, limit: int) -> list[str]:
    obj = parse_json_object(text) or {}
    raw = obj.get("subtasks", [])
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    plan: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        subtask = item.strip()
        if subtask and subtask.lower() not in seen:
            seen.add(subtask.lower())
            plan.append(subtask)
    return plan[:limit]


def parse_critique(text: str) -> dict[str, Any]:
    obj = parse_json_object(text)
    if obj is None:
        return {"score": 0, "issues": ["critic output was not valid JSON"]}
    try:
        score = int(obj.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    issues = obj.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    return {
        "score": max(0, min(10, score)),
        "issues": [str(i).strip() for i in issues if str(i).strip()],
    }
