#!/usr/bin/env python3
"""pass-10-software entrypoint (model-required).

Reads the declared input IR(s) (as compact summaries), drives the local
inference server, and writes the application-ir artifact. Runs against your
server when `--local` is set.

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

PRODUCES = "application-ir"
CONSUMES = ["application-ir", "reasoning-ir", "semantic-ir"]


def _summarize(name, data):
    """Compact, token-friendly summary of an input artifact."""
    if not isinstance(data, dict):
        return name + ": (non-object)"
    out = {name: {"keys": list(data.keys())}}
    # include counts + a couple of sample labels so the model has context
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
        + "\n\nReturn the JSON object required by the application-ir schema. "
        "Every output element MUST cite a provenance span or source id from "
        "the inputs above."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


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
        prompt_file=os.path.join(os.path.dirname(__file__), "prompt.md"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
