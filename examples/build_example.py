#!/usr/bin/env python3
"""Build the example corpus through the real, deterministic part of the
Knowledge Compiler and emit a small report.

Run from the repo root:
    python examples/build_example.py

This exercises pass-01-parse end-to-end and prints a summary. The model-required
passes (02-10) are planned; see examples/README.md for how an agent fills them.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
BUILD = os.path.join(ROOT, "examples", "build")


def main() -> int:
    src = os.path.join(ROOT, "examples", "corpus")
    cmd = [
        sys.executable,
        os.path.join(ROOT, "compiler", "run.py"),
        "--source", src,
        "--build", BUILD,
    ]
    print("running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode

    import json
    from compiler.core import ArtifactStore

    store = ArtifactStore(BUILD)
    print("\n--- example build summary ---")
    print("available artifacts:", store.available())
    if store.has("markdown-ir"):
        meta = store.read("markdown-ir")["metadata"]
        print("documents:", meta["document_count"],
              "| sections:", meta["total_sections"],
              "| citations:", meta["total_citations"],
              "| cross-doc links:", meta["cross_document_links"])
        print("diagnostics:", store.diagnostics("markdown-ir")["counts"])
        ev = json.load(open(os.path.join(BUILD, "markdown-ir", "evaluation.json")))
        print("evaluation overall:", ev["overall"])
    print(f"\nopen: {os.path.join(BUILD, 'markdown-ir', 'artifact.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
