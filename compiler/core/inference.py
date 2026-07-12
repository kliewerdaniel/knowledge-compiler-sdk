"""Local inference client (OpenAI-compatible).

This module lets the Knowledge Compiler drive its model-required passes through
**your own** inference server instead of a cloud API — exactly the local-first
principle the project stands for. Any OpenAI-compatible server works:

* **llama.cpp** server (default port 8080)
* **Ollama** (`ollama serve`, port 11434)
* **vLLM**, **LM Studio**, **text-generation-webui**, …

These servers expose ``/v1/chat/completions`` and accept any dummy API key, so
no secret is required. Point the compiler at the port and the model name:

    from core.inference import InferenceClient
    client = InferenceClient(port=8080, model="llama3")
    data = client.complete_json(system_prompt, user_prompt)

The compiler passes operate on **structured artifacts**, not chat, so the client
asks the model for JSON and parses it defensively (strips code fences, extracts
the outermost object). This keeps intelligence in the artifacts, not the prompts.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - import guard
    OpenAI = None


class InferenceClient:
    """Minimal OpenAI-compatible chat client for local inference."""

    def __init__(
        self,
        port: int = 8080,
        host: str = "localhost",
        model: Optional[str] = None,
        api_key: str = "not-needed",
        timeout: float = 600.0,
    ):
        if OpenAI is None:
            raise RuntimeError(
                "The 'openai' package is required for local inference. "
                "Install it with: pip install openai"
            )
        self.base_url = f"http://{host}:{port}/v1"
        self.model = model or os.environ.get("KC_MODEL") or "local-model"
        self.timeout = timeout
        # llama.cpp / Ollama accept any non-empty key.
        self._client = OpenAI(base_url=self.base_url, api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send chat ``messages`` and return the assistant text."""
        kwargs: Dict = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
        )
        # Many local servers honour response_format json_object; ignore if not.
        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:  # pragma: no cover
            pass
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    def complete_json(
        self, system: str, user: str, temperature: float = 0.2
    ) -> dict:
        """Conversation wrapper that returns parsed JSON from the model."""
        text = self.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return extract_json(text)


def extract_json(text: str) -> dict:
    """Defensively parse JSON out of a model response.

    Strips ```json fenced blocks and extracts the outermost ``{...}`` object so
    that models which prepend prose or wrap output in fences still parse.
    """
    text = text.strip()
    if text.startswith("```"):
        # drop the opening fence and optional language tag
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model response did not contain a JSON object")
    return json.loads(text[start : end + 1])
