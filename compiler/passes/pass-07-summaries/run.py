#!/usr/bin/env python3
"""pass-07-summaries entrypoint (model-required).

Reads the declared input IR(s), drives the local inference server, and writes
the semantic-ir artifact. Run by the orchestrator when `--local` is set.

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

PRODUCES = "semantic-ir"
CONSUMES = ["semantic-ir", "graph-ir", "markdown-ir"]


def build_user_prompt(inputs):
    parts = []
    for art, data in inputs.items():
        if isinstance(data, dict):
            parts.append(art + ": keys=" + str(list(data.keys())))
    brief = "\n".join(parts)
    full = json.dumps(inputs, ensure_ascii=False)[:12000]
    return (
        "Available input artifacts:\n" + brief + "\n\n"
        "Full artifacts (truncated):\n" + full + "\n\n"
        "Return the JSON object required by the semantic-ir schema. "
        "Every output element MUST cite a provenance span or source id."
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
