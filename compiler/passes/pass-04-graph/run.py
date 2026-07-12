#!/usr/bin/env python3
"""pass-04-graph entrypoint (model-required).

Materialises the Ontology IR into a Knowledge Graph IR: nodes, typed edges,
per-edge confidence, and provenance. Also writes GraphML + Mermaid views for
human inspection. Runs against the user's local inference server when
`--local` is set. A repair step drops edges that reference unknown nodes and
detects cycles (annotated, not dropped).

Invocation: python run.py <build_dir> [--port 8080] [--model NAME]
"""

from __future__ import annotations

import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.llm_pass import parse_port_model, run_model_pass
from core.diagnostics import DiagnosticEmitter

PRODUCES = "graph-ir"
CONSUMES = ["ontology-ir", "markdown-ir"]


def build_user_prompt(inputs: dict) -> str:
    oi = inputs["ontology-ir"]
    slim = {
        "concepts": [
            {"id": c["id"], "label": c["label"]}
            for c in oi.get("concepts", [])
        ],
        "relationships": oi.get("relationships", []),
        "hierarchies": oi.get("hierarchies", []),
    }
    return (
        "Ontology IR:\n"
        + json.dumps(slim, ensure_ascii=False)
        + "\n\nProduce graph-ir: nodes[] (one per concept, concept_ref=concept id) "
        "and edges[] (one per relationship/hierarchy, source/target = concept "
        "ids, with confidence and provenance). Respond with the graph-ir JSON "
        "object only."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    nodes = data.get("nodes", [])
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    if not node_ids:
        # The model returned an empty graph. Backfill with the most fundamental
        # units we have - one node per source document - so downstream passes
        # (embeddings, reasoning, app generation) still have a workable graph.
        # This is honest degradation, not silent success: we flag it.
        md = inputs.get("markdown-ir", {}) or {}
        docs = md.get("documents", []) or []
        if docs:
            emitter.warning(
                "EMPTY_GRAPH_BACKFILL",
                f"model returned 0 nodes; backfilling {len(docs)} document nodes",
            )
            nodes = [
                {"id": d.get("id", f"doc-{i+1}"),
                 "label": d.get("title") or d.get("id", f"doc-{i+1}"),
                 "kind": "document",
                 "concept_ref": None}
                for i, d in enumerate(docs)
            ]
            data["nodes"] = nodes
            node_ids = {n["id"] for n in nodes}
        else:
            emitter.error("MISSING_EVIDENCE", "graph produced zero nodes")
            return data

    edges = data.get("edges", [])
    kept = []
    for e in edges:
        if e.get("source") in node_ids and e.get("target") in node_ids:
            kept.append(e)
        else:
            emitter.warning(
                "UNREFERENCED_ENTITY",
                f"edge {e.get('id')} references unknown node; dropped",
            )
    data["edges"] = kept

    # cycle detection (DFS) -> annotate, keep, warn
    adj = {}
    for e in kept:
        adj.setdefault(e["source"], []).append(e["target"])
    seen, in_stack, cyclic = set(), set(), set()

    def visit(u):
        seen.add(u)
        in_stack.add(u)
        for v in adj.get(u, []):
            if v in in_stack:
                cyclic.add((u, v))
            elif v not in seen:
                visit(v)
        in_stack.discard(u)

    for n in list(node_ids):
        if n not in seen:
            visit(n)
    if cyclic:
        emitter.warning(
            "CIRCULAR_REFERENCE",
            f"{len(cyclic)} cycle edge(s) detected; annotated cycle:true",
        )
        cyc_pairs = {(a, b) for a, b in cyclic}
        for e in kept:
            if (e["source"], e["target"]) in cyc_pairs:
                e["cycle"] = True

    if kept:
        deg = sum(len(adj.get(n, [])) for n in node_ids) / max(1, len(node_ids))
        if deg < 1.5:
            emitter.warning("SPARSE_GRAPH", f"mean degree {deg:.2f} < 1.5")

    # Write derived GraphML + Mermaid views for humans.
    build_dir = emitter.build_dir
    _write_graphml(build_dir, nodes, kept)
    _write_mermaid(build_dir, nodes, kept)
    return data


def _write_graphml(build_dir, nodes, edges) -> None:
    import xml.sax.saxutils as su

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
             '  <graph id="knowledge" edgedefault="directed">']
    for n in nodes:
        lines.append(
            f'    <node id="{su.escape(str(n.get("id")))}">'
            f'<data key="label">{su.escape(str(n.get("label","")))}</data></node>'
        )
    for e in edges:
        lines.append(
            f'    <edge source="{su.escape(str(e.get("source")))}" '
            f'target="{su.escape(str(e.get("target")))}">'
            f'<data key="type">{su.escape(str(e.get("type","")))}</data></edge>'
        )
    lines.append("  </graph>")
    lines.append("</graphml>")
    gdir = os.path.join(build_dir, "graph-ir")
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "graph.graphml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_mermaid(build_dir, nodes, edges) -> None:
    lines = ["graph TD"]
    labels = {n.get("id"): n.get("label", n.get("id")) for n in nodes}
    for n in nodes:
        lines.append(f'  {n.get("id")}["{labels.get(n.get("id"), n.get("id"))}"]')
    for e in edges:
        t = e.get("type", "->")
        lines.append(f'  {e.get("source")} -- {t} --> {e.get("target")}')
    gdir = os.path.join(build_dir, "graph-ir")
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "graph.mmd"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    ns = parse_port_model(sys.argv[1:])
    return run_model_pass(
        build_dir=ns.build_dir,
        produces=PRODUCES,
        consumes=CONSUMES,
        system_prompt=SYSTEM_PROMPT,
        user_prompt_fn=build_user_prompt,
        port=ns.port,
        model=ns.model,
        timeout=ns.timeout,
        max_tokens=ns.max_tokens,
        prompt_file=os.path.join(os.path.dirname(__file__), "prompt.md"),
        repair_fn=repair,
    )


if __name__ == "__main__":
    raise SystemExit(main())
