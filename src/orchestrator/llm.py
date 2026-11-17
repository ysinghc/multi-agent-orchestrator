"""Chat-model interface, plus a Gemini (Vertex AI) implementation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    seconds: float


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: Usage


class ChatModel(Protocol):
    name: str

    def complete(self, system: str, user: str) -> LLMResponse: ...


class GeminiChat:
    """Gemini on Vertex AI. Token counts come from the provider's usage metadata."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        project: str | None = None,
        location: str = "us-central1",
        client: Any | None = None,
    ) -> None:
        self.name = model
        if client is None:
            from google import genai

            client = genai.Client(vertexai=True, project=project, location=location)
        self._client = client

    def complete(self, system: str, user: str) -> LLMResponse:
        from google.genai import types

        started = time.perf_counter()
        response = self._client.models.generate_content(
            model=self.name,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.2, max_output_tokens=2048
            ),
        )
        elapsed = time.perf_counter() - started
        meta = response.usage_metadata
        usage = Usage(
            prompt_tokens=int(getattr(meta, "prompt_token_count", 0) or 0),
            completion_tokens=int(getattr(meta, "candidates_token_count", 0) or 0),
            seconds=elapsed,
        )
        return LLMResponse(text=(response.text or "").strip(), usage=usage)
