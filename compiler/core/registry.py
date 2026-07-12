"""Pass registry.

A pass is *declared* declaratively in YAML, not hardcoded in Python. The
registry discovers every ``pass-*/pass.yaml`` under ``compiler/passes`` and
builds a dependency graph over artifact types. This is what makes the knowledge
compiler extensible like a build system: adding a new pass is a matter of
dropping a new directory + YAML, never touching the orchestrator.

Declared fields (``pass.yaml``):

    id:            stable identifier (e.g. ``pass-01-parse``)
    name:          human label
    produces:      artifact type this pass emits (e.g. ``markdown-ir``)
    consumes:      list of artifact types this pass requires as input
    downstream:    artifact type(s) this pass enables / prepares (optional hint)
    entrypoint:    executable invoked by the orchestrator (default: run.py)
    prompt:        optional path to a prompt file the pass consumes
    description:   one-line description
    deterministic: bool — does the pass produce identical output for identical
                   input? (Deterministic passes need no LLM and are preferred.)
    model_required: bool — does the pass need an LLM call?

Example:

    id: pass-01-parse
    name: Markdown Parsing
    produces: markdown-ir
    consumes: []
    entrypoint: run.py
    deterministic: true
    model_required: false
    description: Parse raw Markdown into a Markdown IR.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml  # PyYAML — the only runtime dependency of the core.


@dataclass
class PassDeclaration:
    id: str
    name: str
    produces: str
    consumes: List[str] = field(default_factory=list)
    downstream: List[str] = field(default_factory=list)
    entrypoint: str = "run.py"
    prompt: Optional[str] = None
    description: str = ""
    deterministic: bool = True
    model_required: bool = False
    path: str = ""  # absolute path to the pass directory

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "produces": self.produces,
            "consumes": self.consumes,
            "downstream": self.downstream,
            "entrypoint": self.entrypoint,
            "prompt": self.prompt,
            "description": self.description,
            "deterministic": self.deterministic,
            "model_required": self.model_required,
            "path": self.path,
        }


class PassRegistry:
    """Discovers and indexes compiler pass declarations."""

    def __init__(self, passes_root: str):
        self.passes_root = passes_root
        self.passes: Dict[str, PassDeclaration] = {}
        self.by_produces: Dict[str, PassDeclaration] = {}
        self.discover()

    def discover(self) -> None:
        self.passes.clear()
        self.by_produces.clear()
        pattern = os.path.join(self.passes_root, "pass-*", "pass.yaml")
        for path in sorted(glob.glob(pattern)):
            with open(path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
            decl = PassDeclaration(
                id=doc["id"],
                name=doc.get("name", doc["id"]),
                produces=doc["produces"],
                consumes=doc.get("consumes", []) or [],
                downstream=doc.get("downstream", []) or [],
                entrypoint=doc.get("entrypoint", "run.py"),
                prompt=doc.get("prompt"),
                description=doc.get("description", ""),
                deterministic=bool(doc.get("deterministic", True)),
                model_required=bool(doc.get("model_required", False)),
                path=os.path.dirname(path),
            )
            self.passes[decl.id] = decl
            self.by_produces[decl.produces] = decl

    def get(self, pass_id: str) -> PassDeclaration:
        return self.passes[pass_id]

    def pass_producing(self, artifact_type: str) -> Optional[PassDeclaration]:
        return self.by_produces.get(artifact_type)

    def all(self) -> List[PassDeclaration]:
        return list(self.passes.values())
