#!/usr/bin/env python3
"""pass-04b-relations entrypoint (model-required).

Classifies the *type* of each candidate edge in the Knowledge Graph IR into a
controlled relationship vocabulary. The discovery of candidate edges is done
deterministically in pass-04 (corpus co-occurrence); this pass adds semantic
typing, which the 35B model will not emit when asked to discover relationships
freely but *will* produce when given a concrete pair and asked to label it.

The model is shown, for each pair, the two concepts' labels plus light
grounding text (the titles / preamble of the source documents their member
entities come from) — enough context to judge a relation without dumping whole
posts. Pairs with no meaningful typed relation are dropped (type "none").

Invocation: python run.py <build_dir> [--port 8080] [--model NAME]
                       [--embed-model MODEL] [--timeout S] [--max-tokens N]
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from core.inference import InferenceClient
from core.diagnostics import DiagnosticEmitter
from compiler.core import ArtifactStore, evaluate_artifact, write_evaluation

PRODUCES = "relations-ir"
CONSUMES = ["graph-ir", "ontology-ir", "entity-ir", "markdown-ir"]

VOCAB = [
    "depends-on", "enables", "implements", "refutes", "supports",
    "extends", "is-part-of", "compares-to", "exemplifies", "mentions",
]

SYSTEM_PROMPT = (
    "You are a knowledge-graph relationship classifier. You are given pairs of "
    "concepts and light grounding text (source-document titles/excerpts). For "
    "each pair, decide the single best typed relationship from this controlled "
    "vocabulary, or 'none' if the pair is only loosely associated:\n"
    + ", ".join(VOCAB + ["none"]) + ".\n\n"
    "Rules:\n"
    "- Use 'mentions' only for weak co-occurrence with no deeper link.\n"
    "- Prefer a specific type (depends-on, enables, implements, refutes, "
    "supports, extends, is-part-of, compares-to, exemplifies) when justified.\n"
    "- 'refutes'/'supports' require the concepts to take opposing/agreeing "
    "positions on the same claim.\n"
    "- Respond with a JSON array ONLY: "
    '[{"source": <id>, "target": <id>, "type": <vocab>, "confidence": <0..1>, '
    '"reason": <short>}]. Pairs typed "none" are omitted. No markdown, no prose.'
)


def _grounding(inputs, concept_docs, concept_labels):
    """Map each concept id -> short grounding string from its source docs."""
    md = inputs.get("markdown-ir", {}) or {}
    docs = {d.get("id"): d for d in (md.get("documents", []) or [])}
    out = {}
    for cid, doc_ids in concept_docs.items():
        bits = []
        for did in list(doc_ids)[:3]:
            d = docs.get(did)
            if not d:
                continue
            title = (d.get("title") or "").replace("**", "").strip()
            pre = (d.get("preamble") or "").strip()
            pre = pre[:160]
            bits.append(f"[{title}] {pre}" if pre else f"[{title}]")
        label = concept_labels.get(cid, cid)
        out[cid] = f"{label}: " + " | ".join(bits) if bits else label
    return out


def main(argv=None) -> int:
    from core.llm_pass import parse_port_model
    ns = parse_port_model(sys.argv[1:] if argv is None else argv)
    store = ArtifactStore(ns.build_dir)
    for c in CONSUMES:
        if not store.has(c):
            print(f"error: missing input artifact: {c}", file=sys.stderr)
            return 1

    gi = store.read("graph-ir")
    ei = store.read("entity-ir")
    oi = store.read("ontology-ir")
    md = store.read("markdown-ir")

    nodes = gi.get("nodes", [])
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    candidate_edges = [
        e for e in gi.get("edges", [])
        if e.get("source") in node_ids and e.get("target") in node_ids
    ]
    if not candidate_edges:
        print("error: graph-ir has no candidate edges", file=sys.stderr)
        return 1

    # Concept -> member entity ids -> source docs (for grounding).
    concept_entities = defaultdict(list)
    for n in nodes:
        concept_entities[n["id"]].extend(n.get("member_entity_ids", []) or [])
    ent_docs = {}
    for e in ei.get("entities", []):
        d = (e.get("span") or {}).get("doc")
        if d:
            ent_docs.setdefault(e.get("id"), set()).add(d)
    concept_docs = {}
    for cid, eids in concept_entities.items():
        docs = set()
        for eid in eids:
            docs |= ent_docs.get(eid, set())
        concept_docs[cid] = docs
    concept_labels = {n["id"]: n.get("label", n["id"]) for n in nodes}

    grounding = _grounding({"markdown-ir": md}, concept_docs, concept_labels)

    # Keep the strongest candidates (most shared docs) to bound model cost,
    # but always include at least all edges with shared >= 2.
    cand = sorted(candidate_edges, key=lambda e: e.get("confidence", 0),
                  reverse=True)
    top = cand[:400] if len(cand) > 400 else cand

    try:
        client = InferenceClient(port=ns.port, model=ns.model, timeout=ns.timeout)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    batch_size = int(os.environ.get("KC_BATCH", "24") or "24")
    typed_edges = []
    eid = 0
    pairs = [(e["source"], e["target"]) for e in top]
    for i in range(0, len(pairs), batch_size):
        chunk = pairs[i:i + batch_size]
        pair_block = "\n".join(
            f'{j+1}. ({a}) "{grounding.get(a, a)}"  --  ({b}) "{grounding.get(b, b)}"'
            for j, (a, b) in enumerate(chunk)
        )
        user = (
            f"Classify each pair (concept ids in parentheses):\n{pair_block}\n\n"
            "Return the typed relations as a JSON array."
        )
        try:
            resp = client.complete_json(SYSTEM_PROMPT, user,
                                         max_tokens=ns.max_tokens)
        except Exception as ex:  # noqa: BLE001
            print(f"warn: batch {i//batch_size+1} failed: {ex}", file=sys.stderr)
            continue
        items = resp.get("edges") or []
        if not items and isinstance(resp, list):
            items = resp
        for it in items:
            s, t = it.get("source"), it.get("target")
            typ = (it.get("type") or "none").lower()
            if typ in ("none", "") or s not in node_ids or t not in node_ids:
                continue
            if typ not in VOCAB:
                # Map vague types onto the vocabulary; drop if un-mappable.
                if typ in ("related-to", "related"):
                    typ = "mentions"
                else:
                    continue
            eid += 1
            typed_edges.append({
                "id": f"rel-{eid}",
                "source": s,
                "target": t,
                "type": typ,
                "confidence": float(it.get("confidence", 0.6)),
                "provenance": it.get("provenance", []) or [f"derived from co-occurrence of {s},{t}"],
                "label": it.get("reason", ""),
            })

    emitter = DiagnosticEmitter(PRODUCES, ns.build_dir)
    if not typed_edges:
        emitter.warning("NO_TYPED_EDGES",
                        "model returned no typed relations; graph stays co-occurrence-only")
    data = {"edges": typed_edges, "vocabulary": VOCAB}
    meta = store.write(PRODUCES, data, pass_id="pass-04b-relations",
                       source_artifacts=list(CONSUMES), schema_id=PRODUCES)
    errs = store.validate(PRODUCES, PRODUCES)
    if errs:
        for e in errs:
            emitter.error("CORRECTNESS", f"schema validation: {e}")
    from collections import Counter
    dist = Counter(e["type"] for e in typed_edges)
    emitter.info("TYPED_EDGES", f"{len(typed_edges)} typed edges: {dict(dist)}")
    ev = evaluate_artifact(PRODUCES, data, meta, hints={"reproducibility": 0.0})
    write_evaluation(ns.build_dir, PRODUCES, ev)
    emitter.write()
    print(f"wrote {PRODUCES} (overall eval {ev.overall:.3f}): "
          f"{len(typed_edges)} typed edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
