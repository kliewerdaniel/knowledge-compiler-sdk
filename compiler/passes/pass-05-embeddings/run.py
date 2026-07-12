#!/usr/bin/env python3
"""pass-05-embeddings entrypoint (model-required, embedding-specific).

Computes a vector embedding for every node in the Graph IR and writes them into
the ``semantic-ir`` artifact (``embeddings`` key: node_id -> vector). Uses the
shared local inference client, which tries the primary chat server's
``/v1/embeddings`` first and **falls back to Ollama** (native ``/api/embeddings``,
e.g. ``nomic-embed-text``) when the chat server has no embedding endpoint — the
exact situation when llama.cpp is started without ``--embeddings``.

Invocation: python run.py <build_dir> [--port 8080] [--model NAME]
                       [--embed-model nomic-embed-text:latest]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.inference import InferenceClient

PRODUCES = "semantic-ir"
CONSUMES = ["graph-ir"]


def parse_args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir", nargs="?", default=os.getcwd())
    ap.add_argument("--port", type=int, default=int(os.environ.get("KC_PORT", "8080")))
    ap.add_argument("--model", default=os.environ.get("KC_MODEL"))
    ap.add_argument("--embed-model", default=os.environ.get("KC_EMBED_MODEL"))
    return ap.parse_args(argv)


def main(argv=None) -> int:
    ns = parse_args(sys.argv[1:] if argv is None else argv)
    from compiler.core import ArtifactStore, DiagnosticEmitter, evaluate_artifact, write_evaluation

    store = ArtifactStore(ns.build_dir)
    if not store.has("graph-ir"):
        print("error: missing input artifact: graph-ir", file=sys.stderr)
        return 1
    gi = store.read("graph-ir")
    nodes = gi.get("nodes", [])
    if not nodes:
        print("error: graph-ir has no nodes to embed", file=sys.stderr)
        return 1

    try:
        client = InferenceClient(
            port=ns.port, model=ns.model, embedding_model=ns.embed_model
        )
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    labels = [n.get("label", n.get("id", "")) for n in nodes]
    try:
        vecs = client.embeddings(labels)
    except Exception as e:  # noqa: BLE001
        print(f"error: embedding failed: {e}", file=sys.stderr)
        return 1

    embeddings = {n["id"]: vecs[i] for i, n in enumerate(nodes)}
    data = {
        "embeddings": embeddings,
        "node_count": len(nodes),
        "embedding_model": client.embedding_model,
    }

    emitter = DiagnosticEmitter(PRODUCES, ns.build_dir)
    if len(vecs) != len(nodes):
        emitter.error("CORRECTNESS", "embedding count mismatch")
    meta = store.write(
        PRODUCES, data, pass_id="pass-05-embeddings",
        source_artifacts=["graph-ir"], schema_id=PRODUCES,
    )
    ev = evaluate_artifact(PRODUCES, data, meta, hints={"reproducibility": 0.0})
    write_evaluation(ns.build_dir, PRODUCES, ev)
    emitter.write()
    print(
        f"wrote {PRODUCES} with {len(embeddings)} embeddings "
        f"(model {client.embedding_model}, eval {ev.overall:.3f})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
