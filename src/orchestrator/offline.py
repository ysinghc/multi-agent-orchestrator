"""Deterministic offline models for tests, CI and demos.

`OfflineModel` is a rules-based stand-in that answers each agent role (planner, ReAct worker,
writer, critic) so the whole graph can run without credentials. It is not an LLM. Its rules are
written to exercise every code path, including the self-reflection revision loop.

`ScriptedModel` replays a fixed list of replies and is used to test specific control-flow cases.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from time import perf_counter

from orchestrator.llm import LLMResponse, Usage


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) * 1.3))


def _usage(system: str, user: str, reply: str, seconds: float) -> Usage:
    return Usage(
        prompt_tokens=_estimate_tokens(system + user),
        completion_tokens=_estimate_tokens(reply),
        seconds=max(seconds, 1e-9),
    )


class ScriptedModel:
    """Replies in the order given. Raises if the graph asks for more replies than were scripted."""

    name = "scripted"

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        started = perf_counter()
        if not self._replies:
            raise AssertionError("ScriptedModel ran out of replies")
        self.calls.append((system, user))
        reply = self._replies.pop(0)
        return LLMResponse(reply, _usage(system, user, reply, perf_counter() - started))


class OfflineModel:
    name = "offline-rules"

    def complete(self, system: str, user: str) -> LLMResponse:
        started = perf_counter()
        if "ROLE: planner" in system:
            reply = self._plan(user)
        elif "ROLE: react" in system:
            reply = self._react(user)
        elif "ROLE: writer" in system:
            reply = self._write(user)
        elif "ROLE: critic" in system:
            reply = self._critique(user)
        else:
            raise ValueError("unknown role in system prompt")
        return LLMResponse(reply, _usage(system, user, reply, perf_counter() - started))

    @staticmethod
    def _plan(user: str) -> str:
        task = re.search(r"Task: (.*)", user, re.S).group(1).strip()
        parts = [p.strip() for p in re.split(r"\s+and\s+|;\s*", task, flags=re.IGNORECASE)]
        return json.dumps({"subtasks": [p for p in parts if p][:4]})

    @staticmethod
    def _react(user: str) -> str:
        subtask = re.search(r"Subtask: (.*)", user).group(1).strip()
        observations = re.findall(r"^Observation: (.*)$", user, re.M)
        if observations:
            body = re.sub(r"^\[[^\]]+\]\s*", "", observations[-1]).strip()
            return json.dumps(
                {"thought": "I have enough evidence.", "action": "finish", "action_input": body}
            )
        match = re.search(r"(\d[\d.\s+\-*/()]*\d)", subtask)
        if match:
            return json.dumps(
                {
                    "thought": "The subtask needs arithmetic.",
                    "action": "calculator",
                    "action_input": match.group(1).strip(),
                }
            )
        return json.dumps(
            {
                "thought": "Search the knowledge base.",
                "action": "search_kb",
                "action_input": subtask,
            }
        )

    @staticmethod
    def _write(user: str) -> str:
        task = re.search(r"Task: (.*)", user).group(1).strip()
        findings = re.findall(r"^\d+\. (.*)$", user, re.M)
        feedback = user.split("Reviewer feedback", 1)[1] if "Reviewer feedback" in user else ""
        lines = [f"Answer to: {task}"]
        sources: list[str] = []
        for index, finding in enumerate(findings, start=1):
            text = re.sub(r"\s*\(sources?: [^)]*\)", "", finding)
            lines.append(f"- {text} [{index}]")
            found = re.search(r"\(sources?: ([^)]*)\)", finding)
            sources.append(found.group(1) if found else "calculation")
        if "Sources" in feedback:
            lines.append("")
            lines.append("Sources:")
            lines.extend(f"[{i}] {name}" for i, name in enumerate(sources, start=1))
        return "\n".join(lines)

    @staticmethod
    def _critique(user: str) -> str:
        draft = user.split("Draft:", 1)[1].split("Findings:", 1)[0]
        if "Sources:" in draft:
            return json.dumps({"score": 9, "issues": []})
        return json.dumps(
            {"score": 6, "issues": ["Add a Sources section that lists each cited finding"]}
        )
