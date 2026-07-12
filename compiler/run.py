#!/usr/bin/env python3
"""knowledgec — the Knowledge Compiler command line driver.

Usage:
    python -m compiler.run --source PATH [--build BUILD] [--target IR] [--dry]

This is intentionally thin. It wires together the registry, the orchestrator
and an ArtifactStore, then prints a machine-readable summary. The *intelligence*
lives in the pass entrypoints, not here.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

# Make the package importable whether invoked as a module or a script.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from core import Compiler, PassRegistry  # noqa: E402

PASSES_ROOT = os.path.join(_HERE, "passes")
DEFAULT_BUILD = os.path.join(os.getcwd(), "build")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="knowledgec", description=__doc__)
    ap.add_argument(
        "--source",
        required=True,
        help="Path to a Markdown file or a directory of .md files (the 'source code').",
    )
    ap.add_argument("--build", default=DEFAULT_BUILD, help="Build/output directory.")
    ap.add_argument(
        "--target",
        default=None,
        help="Target artifact type to compile to (e.g. application-ir). "
        "Omit to run every available pass.",
    )
    ap.add_argument(
        "--dry", action="store_true", help="Plan only; do not execute passes."
    )
    args = ap.parse_args(argv)

    # Stage the source into the build dir so pass-01-parse can find it.
    build_dir = os.path.abspath(args.build)
    source_dir = os.path.join(build_dir, "source")
    os.makedirs(source_dir, exist_ok=True)
    src = os.path.abspath(args.source)
    if os.path.isdir(src):
        for fn in os.listdir(src):
            if fn.endswith(".md"):
                shutil.copy(os.path.join(src, fn), os.path.join(source_dir, fn))
    elif os.path.isfile(src):
        shutil.copy(src, os.path.join(source_dir, os.path.basename(src)))
    else:
        print(f"error: source not found: {src}", file=sys.stderr)
        return 2

    registry = PassRegistry(PASSES_ROOT)
    print(
        f"discovered {len(registry.passes)} passes: "
        + ", ".join(registry.passes.keys())
    )

    compiler = Compiler(registry, build_dir)
    summary = compiler.run(target=args.target, dry_run=args.dry)

    steps = summary["plan"]["steps"]
    skipped = summary["plan"]["skipped"]
    print(f"\nplan: {len(steps)} step(s), {len(skipped)} skipped")
    for rec in summary["records"]:
        flag = {"ok": "✓", "failed": "✗", "skipped": "·"}.get(
            rec["status"], "?"
        )
        print(f"  {flag} {rec['pass_id']:<22} -> {rec['produces']}")

    print(f"\nbuild dir: {build_dir}")
    print(f"summary:   {os.path.join(build_dir, 'plan.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
