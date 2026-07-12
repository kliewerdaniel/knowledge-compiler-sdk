#!/usr/bin/env python3
"""pass-08-reasoning entrypoint (model-required).

Reads the semantic + graph IRs, drives the local inference server, and writes
the reasoning-ir: observations, hypotheses, contradictions, unanswered
questions. Runs against your server when `--local` is set.

The repair step guarantees a schema-valid artifact even when the model returns
empty arrays: it emits a MISSING_EVIDENCE diagnostic and fills a minimal valid
structure (so downstream passes are never blocked by an invalid empty object).
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

PRODUCES = "reasoning-ir"
CONSUMES = ["semantic-ir", "graph-ir"]


def _summarize(name, data):
    if not isinstance(data, dict):
        return name + ": (non-object)"
    out = {name: {"keys": list(data.keys())}}
    for key in ("documents", "entities", "concepts", "nodes", "themes",
                "observations", "pages", "components", "relationships", "edges"):
        if key in data and isinstance(data[key], list):
            sample = [str(x.get("label", x.get("id", x.get("text", ""))))[:40]
                      for x in data[key][:3]]
            out[name][key] = {"count": len(data[key]), "sample": sample}
    return out


def build_user_prompt(inputs):
    summary = {art: _summarize(art, data) for art, data in inputs.items()}
    return (
        "Input artifact summaries:\n"
        + json.dumps(summary, ensure_ascii=False)
        + "\n\nReturn ONLY a JSON object with exactly these keys, each a non-empty "
        "array unless genuinely empty is impossible:\n"
        "  observations: [{id, text, provenance:[doc-id], confidence:0..1}]\n"
        "  hypotheses:   [{id, text, basis:[observation-id], confidence:0..1}]\n"
        "  contradictions:[{id, text, a:claim-id, b:claim-id, confidence}]\n"
        "  questions:     [{id, text, theme:theme-id, why_unanswered:str}]\n"
        "Cite a source id from the inputs in every observation/hypothesis."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    """Guarantee a schema-valid, non-empty reasoning-ir.

    If the model returned empty arrays, emit MISSING_EVIDENCE and seed a single
    observation derived from the graph so downstream passes still have signal.
    """
    data.setdefault("observations", [])
    data.setdefault("hypotheses", [])
    data.setdefault("contradictions", [])
    data.setdefault("questions", [])

    if not data["observations"]:
        emitter.warning(
            "MISSING_EVIDENCE",
            "model returned zero observations; seeding from graph nodes",
        )
        gi = inputs.get("graph-ir", {})
        nodes = gi.get("nodes", [])
        if nodes:
            data["observations"] = [{
                "id": "o-seed-1",
                "text": f"The corpus centres on '{nodes[0].get('label','?')}'.",
                "provenance": [nodes[0].get("concept_ref", "graph")],
                "confidence": 0.5,
            }]
            data["questions"] = [{
                "id": "q-seed-1",
                "text": "What claim or decision does this node support?",
                "theme": nodes[0].get("id", "n1"),
                "why_unanswered": "model produced no observations to build on",
            }]

    # Normalize contradiction field names to the schema's a_claim / b_claim.
    for c in data.get("contradictions", []):
        if "a_claim" not in c and "a" in c:
            c["a_claim"] = c.pop("a")
        if "b_claim" not in c and "b" in c:
            c["b_claim"] = c.pop("b")
        c.setdefault("a_claim", c.get("a_claim", ""))
        c.setdefault("b_claim", c.get("b_claim", ""))
    return data


def main():
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
