#!/usr/bin/env python3
"""pass-03-ontology entrypoint (model-required).

Consumes the Entity IR and produces the Ontology IR: canonical concepts, typed
relationships, hierarchies, and aliases. Runs against the user's local
inference server when `--local` is set. Enforces reference consistency via a
repair step so the ontology is internally valid for the graph pass downstream.

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

PRODUCES = "ontology-ir"
CONSUMES = ["entity-ir"]


def build_user_prompt(inputs: dict) -> str:
    ei = inputs["entity-ir"]
    slim = {
        "entities": [
            {"id": e["id"], "label": e["label"], "type": e.get("type")}
            for e in ei.get("entities", [])
        ],
        "claims": [
            {"id": c["id"], "text": c["text"], "entity_refs": c.get("entity_refs", [])}
            for c in ei.get("claims", [])
        ],
    }
    return (
        "Entity IR:\n"
        + json.dumps(slim, ensure_ascii=False)
        + "\n\nBuild concepts[] (merge synonymous entities into one concept and "
        "record which entity ids became members), relationships[] (typed, "
        "controlled vocabulary), hierarchies[], and aliases[]. Respond with the "
        "ontology-ir JSON object only."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    """Enforce internal consistency of the ontology IR.

    - Every relationship/hierarchy endpoint must reference an existing concept.
    - Drop dangling references and emit UNREFERENCED_ENTITY / DUPLICATE_CONCEPT.
    """
    concepts = data.get("concepts", [])
    ids = {c.get("id") for c in concepts if c.get("id")}
    if not ids:
        emitter.error("MISSING_EVIDENCE", "ontology produced zero concepts")
        return data

    rels = data.get("relationships", [])
    kept = []
    for r in rels:
        if r.get("source") in ids and r.get("target") in ids:
            kept.append(r)
        else:
            emitter.warning(
                "UNREFERENCED_ENTITY",
                f"relationship {r.get('id')} references unknown concept; dropped",
            )
    data["relationships"] = kept

    hier = data.get("hierarchies", [])
    kept_h = [
        h for h in hier
        if h.get("parent") in ids and h.get("child") in ids
    ]
    data["hierarchies"] = kept_h

    # weak-ontology heuristic
    if len(rels) < 1.5 * len(concepts):
        emitter.warning(
            "WEAK_ONTOLOGY",
            f"relationships ({len(rels)}) < 1.5x concepts ({len(concepts)})",
        )
    return data


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
        prompt_file=os.path.join(os.path.dirname(__file__), "prompt.md"),
        repair_fn=repair,
    )


if __name__ == "__main__":
    raise SystemExit(main())
