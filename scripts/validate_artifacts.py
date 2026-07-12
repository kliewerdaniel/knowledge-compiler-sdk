#!/usr/bin/env python3
"""scripts/validate_artifacts.py — validate every artifact in a build dir.

For each artifact directory containing artifact.json, validate it against its
declared schema (from metadata.json) and print PASS/FAIL. Exits non-zero if any
artifact fails. This is the check CI runs after a compile.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from compiler.core import ArtifactStore  # noqa: E402


def main(build_dir: str) -> int:
    store = ArtifactStore(build_dir)
    available = store.available()
    if not available:
        print(f"no artifacts found in {build_dir}")
        return 0
    failures = 0
    for art in available:
        errs = store.validate(art)
        if errs:
            failures += 1
            print(f"FAIL {art}:")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"PASS {art}")
    print(f"\n{len(available)-failures}/{len(available)} artifacts valid")
    return 1 if failures else 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build"
    raise SystemExit(main(os.path.abspath(target)))
