"""Compiler diagnostics.

Every pass emits diagnostics about the *quality* of the artifact it produced,
mirroring the warning/error model of LLVM and GCC. Diagnostics are written to
``diagnostics.json`` alongside the artifact and are themselves inspectable.

Severity levels:
    ERROR    — the artifact is structurally invalid or the pass failed.
    WARNING  — the artifact is usable but suspicious (e.g. weak ontology).
    INFO     — informational notes (e.g. "5 circular references normalised").

Each diagnostic carries a stable ``code`` (see ``docs/compiler-phases.md`` for
the canonical diagnostic code table) so agents and dashboards can filter and
trend them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# Canonical diagnostic codes (subset; extend as passes are added).
KNOWN_CODES = {
    "MISSING_EVIDENCE": "No citations back a claimed assertion.",
    "CIRCULAR_REFERENCE": "Entity/relationship forms a cycle.",
    "WEAK_ONTOLOGY": "Low ratio of relationships to concepts.",
    "DUPLICATE_CONCEPT": "Two concepts appear to denote the same thing.",
    "SPARSE_GRAPH": "Average node degree below threshold.",
    "UNREFERENCED_ENTITY": "Entity present in IR but never used downstream.",
    "CONTRADICTORY_STATEMENT": "Two assertions conflict.",
    "INSUFFICIENT_CITATIONS": "Source density below required threshold.",
    "LOW_CONFIDENCE": "Mean confidence below threshold.",
    "HALLUCINATION_SUSPECT": "Artifact content not traceable to inputs.",
}


@dataclass
class Diagnostic:
    code: str
    severity: Severity
    message: str
    loc: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "loc": self.loc,
            "metadata": self.metadata,
        }


class DiagnosticEmitter:
    """Accumulates diagnostics during a pass and writes them to disk."""

    def __init__(self, artifact_type: str, build_dir: str):
        self.artifact_type = artifact_type
        self.build_dir = build_dir
        self.items: List[Diagnostic] = []

    def emit(
        self,
        code: str,
        message: str,
        severity: Severity = Severity.WARNING,
        loc: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        if code not in KNOWN_CODES and severity != Severity.INFO:
            # Still emit; we don't hard-fail on unknown codes so new passes
            # can introduce codes without editing this module.
            pass
        self.items.append(
            Diagnostic(code, severity, message, loc, metadata or {})
        )

    def warning(self, code: str, message: str, **kw):
        self.emit(code, message, Severity.WARNING, **kw)

    def error(self, code: str, message: str, **kw):
        self.emit(code, message, Severity.ERROR, **kw)

    def info(self, code: str, message: str, **kw):
        self.emit(code, message, Severity.INFO, **kw)

    def counts(self) -> Dict[str, int]:
        out = {"error": 0, "warning": 0, "info": 0}
        for d in self.items:
            out[d.severity.value] += 1
        return out

    def dump(self) -> Dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "counts": self.counts(),
            "diagnostics": [d.to_dict() for d in self.items],
        }

    def write(self) -> Dict[str, Any]:
        os.makedirs(
            os.path.join(self.build_dir, self.artifact_type), exist_ok=True
        )
        payload = self.dump()
        with open(
            os.path.join(self.build_dir, self.artifact_type, "diagnostics.json"),
            "w",
            encoding="utf-8",
        ) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2))
        return payload
