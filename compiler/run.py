#!/usr/bin/env python3
"""knowledgec — the Knowledge Compiler command line driver.

Usage:
    python -m compiler.run --source PATH [--build BUILD] [--target IR]
                            [--local --port 8080] [--incremental]
                            [--only pass-04-graph] [--resume]

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


def build_parser() -> argparse.ArgumentParser:
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
    ap.add_argument(
        "--local",
        action="store_true",
        help="Execute model-required passes against a local OpenAI-compatible "
        "inference server (llama.cpp / Ollama / vLLM) instead of skipping them.",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("KC_PORT", "8080")),
        help="Port of the local inference server (default 8080; env KC_PORT).",
    )
    ap.add_argument(
        "--model",
        default=os.environ.get("KC_MODEL"),
        help="Model name to request from the local server (env KC_MODEL).",
    )
    ap.add_argument(
        "--embed-model",
        default=os.environ.get("KC_EMBED_MODEL"),
        help="Ollama embedding model for the fallback path (env KC_EMBED_MODEL).",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("KC_TIMEOUT", "900")),
        help="Per-request timeout (seconds) for the local inference server "
             "(env KC_TIMEOUT). Raise for slow CPU inference / large corpora.",
    )
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("KC_MAX_TOKENS", "8192")),
        help="Max generation tokens per model call (env KC_MAX_TOKENS). Raise "
             "for large corpora so reasoning models have room for the JSON answer.",
    )
    ap.add_argument(
        "--incremental",
        action="store_true",
        help="Skip passes whose output already exists and whose inputs are "
        "unchanged (content-hash based caching).",
    )
    ap.add_argument(
        "--only",
        default=None,
        help="Run only the named pass id (e.g. pass-04-graph). Implies a "
        "single-step plan; inputs must already exist.",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Re-run from the first pass whose output is missing or stale; "
        "equivalent to --incremental but always executes the final target.",
    )
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

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
    summary = compiler.run(
        target=args.target,
        dry_run=args.dry,
        local=args.local,
        port=args.port,
        model=args.model,
        incremental=args.incremental or args.resume,
        only=args.only,
        embed_model=args.embed_model,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
    )

    steps = summary["plan"]["steps"]
    skipped = summary["plan"]["skipped"]
    print(f"\nplan: {len(steps)} step(s), {len(skipped)} skipped")
    flagmap = {"ok": "✓", "failed": "✗", "skipped": "·", "cached": "≡"}
    for rec in summary["records"]:
        flag = flagmap.get(rec["status"], "?")
        extra = f" ({rec['reason']})" if rec.get("reason") else ""
        print(
            f"  {flag} {rec['pass_id']:<22} -> {rec['produces']}{extra}"
        )

    print(f"\nbuild dir: {build_dir}")
    print(f"summary:   {os.path.join(build_dir, 'plan.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
