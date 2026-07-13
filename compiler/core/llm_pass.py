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

    try:
        client = InferenceClient(port=port, model=model, timeout=timeout)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    primary = consumes[0] if consumes else None
    doc_items: List[tuple] = []
    if primary and isinstance(inputs.get(primary), dict):
        # The corpus lives under the primary artifact's "documents" key, which
        # may be a {doc_id: body} dict OR a [body, ...] list depending on the
        # pass. Batch over whichever shape we find.
        docs = inputs[primary].get("documents")
        if isinstance(docs, dict):
            doc_items = list(docs.items())
        elif isinstance(docs, list):
            doc_items = list(enumerate(docs))

    batch_size = int(os.environ.get("KC_BATCH", "12") or "12")
    if batch_size < 1:
        batch_size = len(doc_items) or 1

    def _prompt_for(chunk_items: List[tuple]) -> str:
        chunk_inputs = dict(inputs)
        if primary:
            chunk_inputs[primary] = dict(inputs[primary])
            orig = inputs[primary].get("documents")
            if isinstance(orig, dict):
                chunk_inputs[primary]["documents"] = dict(chunk_items)
            else:  # list-shaped corpus
                chunk_inputs[primary]["documents"] = [body for _, body in chunk_items]
        return user_prompt_fn(chunk_inputs)

    def _name_key(item):
        """Stable de-dup key for a merged list item.

        Model-generated sequential ids (``ent-1``, ``ent-2`` …) collide across
        corpus batches, so we key on the *content* (label/name/text) when
        present and fall back to ``id``. This collapses the same entity
        extracted from different batches without dropping distinct ones.
        """
        if not isinstance(item, dict):
            return item
        raw = item.get("label") or item.get("name") or item.get("text") \
            or item.get("id") or item
        return str(raw).strip().lower()

    def _merge(a: Optional[dict], b: dict) -> dict:
        """Accumulate pass output across corpus batches.

        Lists are concatenated (de-duplicating dict items by their content key
        so a recurring entity/node isn't doubled); dicts are shallow-merged;
        scalars take the later value.
        """
        if a is None:
            return b
        if not isinstance(a, dict) or not isinstance(b, dict):
            return b
        out = dict(a)
        for k, v in b.items():
            if k in out:
                if isinstance(out[k], list) and isinstance(v, list):
                    merged = list(out[k])
                    seen = {_name_key(item) for item in merged}
                    for item in v:
                        key = _name_key(item)
                        if key in seen:
                            continue
                        seen.add(key)
                        merged.append(item)
                    out[k] = merged
                elif isinstance(out[k], dict) and isinstance(v, dict):
                    out[k] = {**out[k], **v}
                else:
                    out[k] = v
            else:
                out[k] = v
        return out

    def _call_with_retries(up: str):
        last: Optional[Exception] = None
        base = up
        for attempt in range(max_retries):
            if attempt > 0:
                up = (
                    base
                    + f"\n\n[retry {attempt}/{max_retries}] Respond with ONLY a single "
                    "valid JSON object and nothing else — no markdown fences, no "
                    "trailing commentary, no extra JSON objects."
                )
                time.sleep(min(2 ** attempt, 8))
            try:
                return client.complete_json(system_prompt, up, max_tokens=max_tokens), None
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"warn: inference attempt {attempt + 1} failed: {e}", file=sys.stderr)
        return None, last

    data: Optional[dict] = None
    last_err: Optional[Exception] = None
    if not doc_items or len(doc_items) <= batch_size:
        # Single call — unchanged behaviour for small corpora.
        up = _prompt_for(doc_items)
        data, last_err = _call_with_retries(up)
    else:
        n_batches = (len(doc_items) + batch_size - 1) // batch_size
        for bi in range(0, len(doc_items), batch_size):
            chunk = doc_items[bi:bi + batch_size]
            up = _prompt_for(chunk)
            cd, err = _call_with_retries(up)
            if cd is None:
                last_err = err
                print(f"warn: batch {bi // batch_size + 1}/{n_batches} failed: {err}",
                      file=sys.stderr)
                continue
            data = _merge(data, cd)
            print(f"info: batch {bi // batch_size + 1}/{n_batches} merged "
                  f"({len(doc_items)} docs total)")
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
