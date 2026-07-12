"""Local inference client (OpenAI-compatible, with Ollama embedding fallback).

This module lets the Knowledge Compiler drive its model-required passes through
**your own** inference server instead of a cloud API — exactly the local-first
principle the project stands for. Any OpenAI-compatible server works:

* **llama.cpp** server (default port 8080)
* **Ollama** (``ollama serve``, port 11434)
* **vLLM**, **LM Studio**, **text-generation-webui**, ...

These servers expose ``/v1/chat/completions`` and accept any dummy API key, so
no secret is required. Point the compiler at the port and the model name:

    client = InferenceClient(port=8080, model="local-model")
    data = client.complete_json(system_prompt, user_prompt)

The compiler passes operate on **structured artifacts**, not chat, so the client
asks the model for JSON and parses it defensively (strips code fences, extracts
the outermost object). This keeps intelligence in the artifacts, not the prompts.

Embeddings
----------
Many chat servers (e.g. a llama.cpp instance started *without* ``--embeddings``)
do **not** expose ``/v1/embeddings``. For the embedding pass we therefore try the
primary server first and, on ``501``/``not_supported``, transparently fall back
to an **Ollama** embedding model via its native ``/api/embeddings`` endpoint
(``nomic-embed-text`` and friends). This is fully local — no cloud, no key.
"""

from __future__ import annotations

import json
import os
import urllib.request
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
        timeout: float = 120.0,
        connect_timeout: float = 2.0,
        ollama_host: str = "localhost",
        ollama_port: int = 11434,
        embedding_model: Optional[str] = None,
    ):
        if OpenAI is None:
            raise RuntimeError(
                "The 'openai' package is required for local inference. "
                "Install it with: pip install openai"
            )
        self.base_url = f"http://{host}:{port}/v1"
        self.host = host
        self.port = port
        self.model = model or os.environ.get("KC_MODEL") or "local-model"
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.ollama_base = f"http://{ollama_host}:{ollama_port}"
        self.embedding_model = (
            embedding_model
            or os.environ.get("KC_EMBED_MODEL")
            or "nomic-embed-text:latest"
        )
        # Probe the chat server up front so a dead port fails fast (seconds, not
        # the full request timeout). Local-first means the user's server is up.
        self._probe(host, port, connect_timeout)
        # llama.cpp / Ollama accept any non-empty key.
        self._client = OpenAI(base_url=self.base_url, api_key=api_key)

    @staticmethod
    def _probe(host: str, port: int, timeout: float) -> None:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
        except OSError as e:
            raise RuntimeError(
                f"no inference server reachable at {host}:{port} "
                f"(start llama.cpp/Ollama/vLLM, or drop --local). {e}"
            ) from e
        finally:
            s.close()

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send chat ``messages`` and return the assistant text.

        Reasoning models (e.g. Ornith, DeepSeek-R) return their verbal trace in
        ``reasoning_content`` and the final answer in ``content``; we return the
        content but the trace is available via :meth:`chat_with_reasoning`.
        """
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

    def chat_with_reasoning(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        """Like :meth:`chat` but also returns the model's reasoning trace."""
        kwargs: Dict = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.timeout,
        )
        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:  # pragma: no cover
            pass
        resp = self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        return msg.content or "", getattr(msg, "reasoning_content", None) or ""

    def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        """Conversation wrapper that returns parsed JSON from the model."""
        text = self.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return extract_json(text)

    # -- embeddings --------------------------------------------------------
    def embeddings(
        self,
        texts: List[str],
        prefer_primary: bool = True,
    ) -> List[List[float]]:
        """Return an embedding per input text.

        Tries the primary chat server's ``/v1/embeddings`` first; if it is
        unavailable (``501 not_supported``) or unreachable, falls back to Ollama
        native ``/api/embeddings`` (e.g. ``nomic-embed-text``). Returns a list
        parallel to ``texts``.
        """
        if prefer_primary:
            try:
                return self._embed_primary(texts)
            except _EmbedUnsupported:
                # expected case: chat server has no embedding endpoint
                pass
            except Exception as e:  # pragma: no cover - network edge cases
                print(
                    f"warning: primary embeddings failed ({e}); "
                    f"falling back to Ollama",
                    file=os.sys.stderr,
                )
        return self._embed_ollama(texts)

    def _embed_primary(self, texts: List[str]) -> List[List[float]]:
        try:
            resp = self._client.embeddings.create(model=self.model, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            msg = str(e)
            if "not_supported" in msg or "501" in msg or "embeddings" in msg.lower():
                raise _EmbedUnsupported(msg)
            raise

    def _embed_ollama(self, texts: List[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for t in texts:
            payload = json.dumps(
                {"model": self.embedding_model, "prompt": t}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self.ollama_base}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            last_err: Optional[Exception] = None
            emb = None
            for attempt in range(3):  # tolerate transient connection resets
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as r:
                        body = json.loads(r.read().decode("utf-8"))
                    emb = body.get("embedding")
                    if emb:
                        break
                except Exception as e:  # transient network error
                    last_err = e
                    continue
            if not emb:
                raise RuntimeError(
                    f"Ollama embedding failed for model "
                    f"'{self.embedding_model}' at {self.ollama_base}: {last_err}"
                )
            out.append(emb)
        return out


class _EmbedUnsupported(Exception):
    """Internal signal: the primary server has no embeddings endpoint."""


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
