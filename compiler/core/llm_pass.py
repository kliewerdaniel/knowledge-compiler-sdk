"""Shared scaffold for model-required (LLM) compiler passes.

A model pass is a normal ``run.py`` entrypoint that:

1. Loads its declared input artifact(s) from the build dir.
2. Builds a prompt from the structured IR (small, artifact-driven).
3. Calls the user's local inference server via :class:`InferenceClient`.
4. Parses the JSON the model returns.
5. Validates it against the pass's schema and writes the output artifact +
   diagnostics + evaluation.

This module factors the boilerplate so each pass stays small and focused on its
*behaviour* (in its prompt/skill), not on plumbing. Passes opt in by calling
:meth:`run_model_pass`.

The local server is discovered from ``--port`` / ``KC_PORT`` (default 8080) and
``--model`` / ``KC_MODEL``. The model only ever sees structured artifacts — never
raw Markdown — keeping the intelligence in the artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Callable, Dict, List, Optional

# Relative imports keep this module importable whether the package is reached
# as `core` (compiler/ on path) or `compiler.core` (repo root on path).
from .artifacts import ArtifactStore
from .diagnostics import DiagnosticEmitter
from .evaluation import evaluate_artifact, write_evaluation
from .inference import InferenceClient


def load_inputs(build_dir: str, consumes: List[str]) -> Dict[str, dict]:
    store = ArtifactStore(build_dir)
    out: Dict[str, dict] = {}
    for art in consumes:
        if store.has(art):
            out[art] = store.read(art)
    return out


def run_model_pass(
    build_dir: str,
    produces: str,
    consumes: List[str],
    system_prompt: str,
    user_prompt_fn: Callable[[Dict[str, dict]], str],
    port: int = 8080,
    model: Optional[str] = None,
    prompt_file: Optional[str] = None,
    repair_fn: Optional[Callable[[dict, Dict[str, dict], DiagnosticEmitter], dict]] = None,
    augment: bool = False,
    max_retries: int = 3,
    timeout: float = 900.0,
    max_tokens: int = 8192,
) -> int:
    """Execute a model-required pass against the local inference server.

    Returns a process exit code (0 ok, 2 usage/config error, 1 failure).

    ``repair_fn(data, inputs, emitter)`` is an optional hook a pass supplies to
    enforce *internal reference consistency* — e.g. drop graph edges that point
    at non-existent node ids, or flag ontology relationships with unknown
    concept ids. This keeps a multi-stage chain coherent even when the model
    drifts, and turns dangling references into diagnostics instead of silent
    corruption.

    ``augment=True`` makes the pass *extend* an existing ``produces`` artifact
    rather than overwrite it (the model output is merged at the top level). This
    is how the three semantic passes cooperate on a single ``semantic-ir``
    without clobbering each other's output.

    ``max_retries`` controls how many times a pass will re-attempt the model
    call when it returns malformed/non-JSON output (common with local models).
    Each retry appends an explicit "respond with only valid JSON" reminder and
    backs off briefly, so a transiently garbled response does not abort the
    whole pipeline.
    """
    store = ArtifactStore(build_dir)
    inputs = load_inputs(build_dir, consumes)
    missing = [c for c in consumes if c not in inputs]
    if missing:
        print(f"error: missing input artifacts: {missing}", file=sys.stderr)
        return 1

    # Allow a prompt.md to override the system prompt for easy editing.
    if prompt_file and os.path.isfile(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as fh:
            system_prompt = fh.read()

    user_prompt = user_prompt_fn(inputs)

    try:
        client = InferenceClient(port=port, model=model, timeout=timeout)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    data = None
    last_err: Optional[Exception] = None
    base_prompt = user_prompt
    for attempt in range(max_retries):
        # On retries, remind the model to return strict JSON (local models
        # frequently emit prose or trailing garbage after the object).
        if attempt > 0:
            user_prompt = (
                base_prompt
                + f"\n\n[retry {attempt}/{max_retries}] Respond with ONLY a single "
                "valid JSON object and nothing else — no markdown fences, no "
                "trailing commentary, no extra JSON objects."
            )
            time.sleep(min(2 ** attempt, 8))  # exponential backoff (capped)
        try:
            data = client.complete_json(system_prompt, user_prompt, max_tokens=max_tokens)
            last_err = None
            break
        except Exception as e:  # noqa: BLE001 - surface model/parse failures clearly
            last_err = e
            print(f"warn: inference attempt {attempt + 1} failed: {e}", file=sys.stderr)
    if data is None:
        print(f"error: inference failed after {max_retries} attempts: {last_err}",
              file=sys.stderr)
        return 1

    emitter = DiagnosticEmitter(produces, build_dir)
    if repair_fn is not None:
        data = repair_fn(data, inputs, emitter)

    if augment and store.has(produces):
        existing = store.read(produces)
        merged = dict(existing)
        merged.update(data)
        data = merged
        emitter.info("AUGMENT", f"merged onto existing {produces}")

    schema_id = produces
    meta = store.write(
        produces,
        data,
        pass_id=f"model-pass:{produces}",
        source_artifacts=list(inputs.keys()),
        schema_id=schema_id,
    )
    # Validate *after* writing so we can read the artifact back.
    errs = store.validate(produces, schema_id)
    if errs:
        for e in errs:
            emitter.error("CORRECTNESS", f"schema validation: {e}")
    ev = evaluate_artifact(
        produces,
        data,
        meta,
        hints={"reproducibility": 0.0},  # model output not deterministic
    )
    write_evaluation(build_dir, produces, ev)
    emitter.write()

    print(f"wrote {produces} (overall eval {ev.overall:.3f})")
    return 0


def parse_port_model(argv) -> argparse.Namespace:
    """Common CLI flags for model passes: --port (default 8080), --model,
    --embed-model. Uses ``parse_known_args`` so a pass can ignore flags the
    orchestrator forwards on its behalf (e.g. --embed-model for passes that
    don't need it)."""
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("build_dir", nargs="?", default=os.getcwd())
    ap.add_argument("--port", type=int, default=int(os.environ.get("KC_PORT", "8080")))
    ap.add_argument("--model", default=os.environ.get("KC_MODEL"))
    ap.add_argument("--embed-model", default=os.environ.get("KC_EMBED_MODEL"))
    ap.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("KC_TIMEOUT", "900")),
        help="Per-request timeout (seconds) for the local inference server "
             "(env KC_TIMEOUT). Raise for slow CPU inference / large corpora.",
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("KC_MAX_TOKENS", "8192")),
        help="Max generation tokens per model call (env KC_MAX_TOKENS). Raise "
             "for large corpora so reasoning models have room for the JSON answer.",
    )
    return ap.parse_known_args(argv)[0]
