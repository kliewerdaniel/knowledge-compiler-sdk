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
CONSUMES = ["ontology-ir", "entity-ir", "markdown-ir"]


def build_user_prompt(inputs: dict) -> str:
    oi = inputs["ontology-ir"]
    concepts = oi.get("concepts") or oi.get("items") or []
    slim = {
        "concepts": [
            {"id": c.get("id"), "label": c.get("label")}
            for c in concepts
        ],
        "relationships": oi.get("relationships", []),
        "hierarchies": oi.get("hierarchies", []),
    }
    return (
        "Ontology IR:\n"
        + json.dumps(slim, ensure_ascii=False)
        + "\n\nProduce graph-ir: nodes[] (one per concept, concept_ref=concept id) "
        "and edges[] (one per relationship/hierarchy, source/target = concept "
        "ids, with confidence and provenance). If the ontology omits "
        "relationships, infer them from co-occurrence: two concepts whose member "
        "entities appear in the same source document are related. Respond with "
        "the graph-ir JSON object only."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    from collections import defaultdict

    # The model may return concepts under either "concepts" or "items".
    oi = inputs.get("ontology-ir", {}) or {}
    model_concepts = data.get("nodes") or data.get("concepts") or oi.get("concepts") or oi.get("items") or []
    # Normalise concept shapes (model sometimes emits "items" with
    # id/label/member_entity_ids instead of "nodes").
    nodes = []
    for c in model_concepts:
        cid = c.get("id") or c.get("concept_ref")
        if not cid:
            continue
        nodes.append({
            "id": cid,
            "label": c.get("label", cid),
            "kind": c.get("kind", "concept"),
            "concept_ref": c.get("concept_ref", cid),
            "member_entity_ids": c.get("member_entity_ids", []),
        })
    node_ids = {n["id"] for n in nodes}

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
                 "concept_ref": None,
                 "member_entity_ids": []}
                for i, d in enumerate(docs)
            ]
            node_ids = {n["id"] for n in nodes}
        else:
            emitter.error("MISSING_EVIDENCE", "graph produced zero nodes")
            return data

    # ---- Edge construction ------------------------------------------------
    edges = []

    # (a) Edges declared by the ontology (relationships + hierarchies).
    for r in oi.get("relationships", []) or []:
        s, t = r.get("source"), r.get("target")
        if s in node_ids and t in node_ids:
            edges.append({
                "id": r.get("id", f"rel-{len(edges)}"),
                "source": s, "target": t,
                "type": r.get("type", "related-to"),
                "confidence": float(r.get("confidence", 0.7)),
                "provenance": r.get("provenance", []),
            })
    for h in oi.get("hierarchies", []) or []:
        s, t = h.get("parent"), h.get("child")
        if s in node_ids and t in node_ids:
            edges.append({
                "id": f"hier-{len(edges)}",
                "source": s, "target": t,
                "type": h.get("type", "is-a"),
                "confidence": 0.8,
                "provenance": h.get("provenance", []),
            })

    # (b) Co-occurrence edges derived from the corpus. Two concepts are related
    # if their member entities appear in the same source document. This is
    # evidence-grounded relationship extraction: it does not invent links, it
    # surfaces structure already present in the writing.
    ei = inputs.get("entity-ir", {}) or {}
    ent_docs = {}
    for e in ei.get("entities", []) or []:
        d = (e.get("span") or {}).get("doc")
        if d:
            ent_docs.setdefault(e.get("id"), set()).add(d)

    concept_docs: dict = {}
    for n in nodes:
        docs = set()
        for eid in n.get("member_entity_ids", []) or []:
            docs |= ent_docs.get(eid, set())
        concept_docs[n["id"]] = docs

    doc_to_concepts = defaultdict(set)
    for cid, docs in concept_docs.items():
        for d in docs:
            doc_to_concepts[d].add(cid)

    co_pair = {}  # (a,b) -> shared doc count
    for d, cids in doc_to_concepts.items():
        cids = list(cids)
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                a, b = cids[i], cids[j]
                key = (a, b) if a < b else (b, a)
                co_pair[key] = co_pair.get(key, 0) + 1

    # Cap edges per concept to keep the graph readable (top-K by shared docs).
    MAX_PER_NODE = 10
    per_node = defaultdict(list)
    for (a, b), shared in co_pair.items():
        per_node[a].append((b, shared))
        per_node[b].append((a, shared))
    seen_pairs = set()
    for cid, neigh in per_node.items():
        neigh.sort(key=lambda x: x[1], reverse=True)
        for other, shared in neigh[:MAX_PER_NODE]:
            key = (cid, other) if cid < other else (other, cid)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            denom = max(len(concept_docs[cid]), len(concept_docs[other]), 1)
            conf = min(1.0, 0.4 + 0.6 * (shared / denom))
            edges.append({
                "id": f"co-{len(edges)}",
                "source": cid, "target": other,
                "type": "co-occurs-in",
                "confidence": round(conf, 3),
                "provenance": [f"shared {shared} doc(s)"],
            })

    # Drop edges that reference unknown nodes (defensive).
    kept = [e for e in edges
            if e["source"] in node_ids and e["target"] in node_ids]
    if len(kept) < len(edges):
        emitter.warning("UNREFERENCED_ENTITY",
                        f"{len(edges) - len(kept)} edge(s) dropped (unknown node)")

    data["nodes"] = nodes
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
    else:
        emitter.warning("NO_EDGES", "graph has nodes but no edges")

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
