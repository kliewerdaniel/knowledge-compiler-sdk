#!/usr/bin/env python3
"""scripts/render_report.py — render a Markdown report from built artifacts.

Reads markdown-ir + (if present) semantic-ir/reasoning-ir and writes
build/report.md. Demonstrates the artifact-driven, transparent-output principle:
reasoning is emitted as a file, never hidden in a chat.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from compiler.core import ArtifactStore  # noqa: E402


def main(build_dir: str) -> int:
    store = ArtifactStore(build_dir)
    out = ["# Knowledge Compiler Report\n"]
    if store.has("markdown-ir"):
        ir = store.read("markdown-ir")
        m = ir["metadata"]
        out.append(f"## Corpus\n- documents: {m['document_count']}")
        out.append(f"- sections: {m['total_sections']}")
        out.append(f"- citations: {m['total_citations']}")
        out.append(f"- cross-doc links: {m['cross_document_links']}\n")
        out.append("### Documents")
        for d in ir["documents"]:
            out.append(f"- **{d['title']}** (`{d['path']}`) — "
                       f"{d['section_count']} sections, {d['word_count']} words")
    diag = store.diagnostics("markdown-ir")["counts"] if store.has("markdown-ir") else {}
    if diag:
        out.append(f"\n## Diagnostics\n- warnings: {diag.get('warning',0)} "
                   f"| errors: {diag.get('error',0)} | info: {diag.get('info',0)}")
    report = os.path.join(build_dir, "report.md")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {report}")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build"
    raise SystemExit(main(os.path.abspath(target)))
