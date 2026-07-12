#!/usr/bin/env python3
"""pass-02-extract entrypoint (model-required).

Reads the Markdown IR and extracts entities / terms / claims from each document,
each carrying a source span, then writes the Entity IR via the local inference
server. Run by the orchestrator when `--local` is set.

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

PRODUCES = "entity-ir"
CONSUMES = ["markdown-ir"]


def build_user_prompt(inputs):
    md = inputs["markdown-ir"]
    slim = {
        "documents": [
            {
                "id": d["id"],
                "title": d["title"],
                "sections": [
                    {"id": s["id"], "title": s["title"], "level": s["level"]}
                    for s in d["sections"]
                ],
            }
            for d in md["documents"]
        ]
    }
    return (
        "Markdown IR:\n"
        + json.dumps(slim, ensure_ascii=False)
        + "\n\nReturn JSON with entities[], terms[], claims[] per the schema. "
        "Every entity/claim MUST include a 'span' = {doc, section} referencing "
        "the ids above. Do not invent items without a span."
    )


SYSTEM_PROMPT = """You are the Entity Extraction compiler pass.
OUTPUT a JSON object: {"entities":[], "terms":[], "claims":[]}.
entities: {id,label,type,span:{doc,section,start,end},confidence}
  type in {person,system,concept,library,method,metric,event,organization}
terms: {id,label,doc,confidence}
claims: {id,text,doc,section,confidence,entity_refs:[]}
RULES:
  - Every entity/claim MUST carry a span tying it to the source IR.
  - Use concise labels (1-5 words).
  - Do not invent entities not evidenced in the IR.
  - Respond with JSON only."""


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
