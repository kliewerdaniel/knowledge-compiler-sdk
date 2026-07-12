#!/usr/bin/env python3
"""pass-09-specifications entrypoint (model-required).

Reads the reasoning + graph IRs and writes the application-ir: architecture,
pages, components, routes, APIs, deployment plan. Runs against your server
when `--local` is set.

The repair step guarantees a schema-valid application-ir even if the model
omits required sections: it backfills a minimal valid scaffold (pages from
themes/nodes, a component per page, a route per page, a deployment plan) so the
final code-generation pass always has a complete target. Missing sections are
flagged with MISSING_EVIDENCE diagnostics — the build stays honest, never
invalid.
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

PRODUCES = "application-ir"
CONSUMES = ["reasoning-ir", "semantic-ir", "graph-ir"]


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
        + "\n\nReturn ONLY a JSON object with exactly these keys:\n"
        "  architecture:    {layers:[str], rationale:str}\n"
        "  pages:           [{id, title, route, components:[id], theme_ref?}]\n"
        "  components:      [{id, name, props:[], responsibility:str}]\n"
        "  routes:          [{path, page_id, method}]\n"
        "  apis:            [{path, method, purpose, request:{}, response:{}}]\n"
        "  deployment_plan: {target:str, steps:[str], prerequisites:[str]}\n"
        "Every page.route must start with '/'. Create at least one page."
    )


SYSTEM_PROMPT = open(os.path.join(os.path.dirname(__file__), "prompt.md"),
                    encoding="utf-8").read()


def repair(data, inputs, emitter: DiagnosticEmitter) -> dict:
    """Backfill a schema-valid application-ir from available inputs."""
    gi = inputs.get("graph-ir", {})
    si = inputs.get("semantic-ir", {})
    ri = inputs.get("reasoning-ir", {})
    nodes = gi.get("nodes", [])
    themes = si.get("themes", [])

    if not data.get("architecture"):
        emitter.warning("MISSING_EVIDENCE", "no architecture; using default layers")
        data["architecture"] = {
            "layers": ["presentation", "application", "data"],
            "rationale": "default three-tier from available IRs",
        }
    if not data.get("pages"):
        emitter.warning("MISSING_EVIDENCE", "no pages; deriving one per theme/node")
        src = themes or nodes
        pages = []
        for i, t in enumerate(src[:5] or [{"id": "n1", "label": "Home"}]):
            label = t.get("label", f"Page {i+1}")
            pid = f"page-{i+1}"
            pages.append({
                "id": pid,
                "title": label,
                "route": "/" if i == 0 else f"/{t.get('id', f'p{i+1}')}",
                "components": [f"cmp-{i+1}"],
                "theme_ref": t.get("id"),
            })
        data["pages"] = pages
    if not data.get("components"):
        emitter.warning("MISSING_EVIDENCE", "no components; deriving from pages")
        comps = []
        for p in data["pages"]:
            cid = (p.get("components") or [f"cmp-{p['id']}"])[0]
            comps.append({
                "id": cid,
                "name": p["title"].replace(" ", "") or "Component",
                "props": [],
                "responsibility": f"Renders {p['title']}",
            })
        data["components"] = comps
    if not data.get("routes"):
        data["routes"] = [
            {"path": p["route"], "page_id": p["id"], "method": "GET"}
            for p in data["pages"]
        ]
    if not data.get("apis"):
        data["apis"] = [{
            "path": "/api/knowledge",
            "method": "GET",
            "purpose": "serve the compiled knowledge graph",
            "request": {}, "response": {},
        }]
    if not data.get("deployment_plan"):
        emitter.warning("MISSING_EVIDENCE", "no deployment plan; using default")
        data["deployment_plan"] = {
            "target": "static",
            "steps": ["build", "deploy"],
            "prerequisites": ["node"],
        }
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
