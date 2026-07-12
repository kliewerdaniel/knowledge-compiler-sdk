#!/usr/bin/env python3
"""pass-01-parse entrypoint.

Reads ``<build>/source/*.md`` and emits a Markdown IR under
``<build>/markdown-ir/``. This pass is fully deterministic and requires no LLM;
it performs pure syntactic transformation so downstream passes receive a
stable, well-typed structure to reason over.

Invocation: python run.py <build_dir>
"""

from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_HERE)))

from core import (  # noqa: E402
    DiagnosticEmitter,
    write_artifact,
    write_evaluation,
    evaluate_artifact,
)

# A section heading, e.g. "## 2. Methods"  -> level 2, title "Methods", num "2"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# A markdown link: [text](target)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
# A reference-style definition: [id]: target
REFDEF_RE = re.compile(r"^\[([^\]]+)\]:\s+(\S+)", re.MULTILINE)
# A footnote-style citation: [^1] or (Author Year)
CITE_RE = re.compile(r"\[\^(\w+)\]|\(([A-Z][\w]+?\s+\d{4})\)")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def parse_document(path: str, idx: int) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    lines = text.splitlines()
    title = ""
    sections = []
    current = None
    citations = []
    in_code = False
    body_lines: list[str] = []

    for ln in lines:
        if ln.strip().startswith("```"):
            in_code = not in_code
        m = HEADING_RE.match(ln)
        if m and not in_code:
            level = len(m.group(1))
            raw = m.group(2).strip()
            # split leading numbering "2. Methods" -> num, title
            num_match = re.match(r"^(\d+(?:\.\d+)*\.?)\s+(.*)$", raw)
            num = num_match.group(1).rstrip(".") if num_match else ""
            heading_title = num_match.group(2) if num_match else raw
            if level == 1 and not title:
                title = heading_title
            if current is not None:
                sections.append(current)
            current = {
                "id": f"sec-{idx}-{len(sections)+1}",
                "level": level,
                "number": num,
                "title": heading_title,
                "blocks": [],
            }
        else:
            if current is not None:
                current["blocks"].append(ln)
            else:
                body_lines.append(ln)
            # collect inline citations from this line
            for lm in LINK_RE.finditer(ln):
                citations.append(
                    {
                        "text": lm.group(1),
                        "target": lm.group(2),
                        "inline": True,
                    }
                )
            for cm in CITE_RE.finditer(ln):
                ref = cm.group(1) or cm.group(2)
                citations.append({"text": ref, "target": ref, "inline": True})

    if current is not None:
        sections.append(current)

    if not title:
        # fall back to first non-empty line / filename
        title = (
            next((l.strip("# ").strip() for l in lines if l.strip()), "")
            or os.path.basename(path)
        )

    return {
        "id": f"doc-{idx+1}",
        "title": title,
        "path": os.path.basename(path),
        "preamble": "\n".join(body_lines).strip(),
        "sections": sections,
        "section_count": len(sections),
        "word_count": len(text.split()),
    }


def build_document_graph(docs: list[dict], source_dir: str) -> dict:
    nodes = [{"id": d["id"], "label": d["title"], "path": d["path"]} for d in docs]
    edges = []
    seen = set()
    for d in docs:
        for c in []:
            pass
    # cross-document links discovered via filename references in link targets
    names = {os.path.splitext(d["path"])[0]: d["id"] for d in docs}
    for d in docs:
        # re-scan for links pointing at other docs
        with open(os.path.join(source_dir, d["path"]), "r", encoding="utf-8") as fh:
            txt = fh.read()
        for lm in LINK_RE.finditer(txt):
            tgt = lm.group(2)
            base = os.path.splitext(os.path.basename(tgt))[0]
            if base in names and names[base] != d["id"]:
                key = (d["id"], names[base])
                if key not in seen:
                    seen.add(key)
                    edges.append(
                        {"from": d["id"], "to": names[base], "kind": "references"}
                    )
    return {"nodes": nodes, "edges": edges}


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) < 1:
        print("usage: run.py <build_dir>", file=sys.stderr)
        return 2
    build_dir = argv[0]
    source_dir = os.path.join(build_dir, "source")
    if not os.path.isdir(source_dir):
        print(f"no source dir at {source_dir}", file=sys.stderr)
        return 1

    md_files = sorted(f for f in os.listdir(source_dir) if f.endswith(".md"))
    documents = [parse_document(os.path.join(source_dir, f), i) for i, f in enumerate(md_files)]
    graph = build_document_graph(documents, source_dir)

    # gather citations across docs
    citations = []
    for d in documents:
        pass  # citations were captured per-line during parse; re-scan below
    for i, f in enumerate(md_files):
        with open(os.path.join(source_dir, f), "r", encoding="utf-8") as fh:
            txt = fh.read()
        for lm in LINK_RE.finditer(txt):
            citations.append(
                {
                    "doc": documents[i]["id"],
                    "text": lm.group(1),
                    "target": lm.group(2),
                }
            )

    ir = {
        "schema_version": "1.0",
        "documents": documents,
        "citations": citations,
        "document_graph": graph,
        "metadata": {
            "document_count": len(documents),
            "total_words": sum(d["word_count"] for d in documents),
            "total_sections": sum(d["section_count"] for d in documents),
            "total_citations": len(citations),
            "cross_document_links": len(graph["edges"]),
        },
    }

    emitter = DiagnosticEmitter("markdown-ir", build_dir)
    if not documents:
        emitter.error("MISSING_EVIDENCE", "no Markdown documents found in source")
    if ir["metadata"]["total_citations"] == 0:
        emitter.warning(
            "INSUFFICIENT_CITATIONS",
            "no links/citations detected; downstream provenance will be weak",
        )
    if ir["metadata"]["cross_document_links"] == 0 and len(documents) > 1:
        emitter.info(
            "SPARSE_GRAPH",
            "documents do not cross-reference each other (no document graph edges)",
        )
    emitter.write()

    meta = write_artifact(
        build_dir,
        "markdown-ir",
        ir,
        pass_id="pass-01-parse",
        source_artifacts=[f for f in md_files],
        schema_id="markdown-ir",
    )

    ev = evaluate_artifact(
        "markdown-ir",
        ir,
        meta,
        hints={
            "coverage": 1.0,
            "traceability": 1.0 if ir["metadata"]["total_citations"] else 0.3,
            "reproducibility": 1.0,
        },
    )
    write_evaluation(build_dir, "markdown-ir", ev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
