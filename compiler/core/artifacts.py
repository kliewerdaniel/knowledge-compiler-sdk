"""Artifact storage.

An *artifact* is the unit of output produced by a compiler pass. Artifacts are
immutable: once written they are never edited in place. If a later pass needs to
revise a representation it writes a *new* artifact (typically under a new
artifact type), preserving the lineage through ``metadata.json``.

On disk an artifact lives in a directory named after its artifact type::

    <build>/
        markdown-ir/
            artifact.json      # the IR data (validated against a JSON Schema)
            metadata.json      # provenance: producer, inputs, timestamp, hash
            diagnostics.json   # compiler diagnostics emitted by the producer

This module is the only place that knows how artifacts are serialised, so the
rest of the compiler can treat them as opaque, well-typed values.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "schemas"
)


def _stable_json(obj: Any) -> str:
    """Canonical JSON serialisation for hashing and comparison."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)


def artifact_path(build_dir: str, artifact_type: str) -> str:
    return os.path.join(build_dir, artifact_type)


def artifact_exists(build_dir: str, artifact_type: str) -> bool:
    p = os.path.join(artifact_path(build_dir, artifact_type), "artifact.json")
    return os.path.isfile(p)


def read_artifact(build_dir: str, artifact_type: str) -> Dict[str, Any]:
    p = os.path.join(artifact_path(build_dir, artifact_type), "artifact.json")
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"artifact '{artifact_type}' not found in build dir '{build_dir}'"
        )
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def content_hash_of(build_dir: str, artifact_type: str) -> Optional[str]:
    """Return the stored content hash of an artifact, or None if absent."""
    meta = read_metadata(build_dir, artifact_type)
    return meta.get("content_hash")


def source_hashes_of(build_dir: str, artifacts: List[str]) -> Dict[str, str]:
    """Map each (present) artifact name to its current content hash.

    The special name ``"source"`` refers to the staged source directory
    (``<build>/source``); its hash is computed over the concatenated canonical
    JSON of every ``.md`` file so incremental caching can detect source edits.
    """
    out = {}
    for a in artifacts:
        if a == "source":
            h = _source_dir_hash(build_dir)
            if h is not None:
                out[a] = h
            continue
        h = content_hash_of(build_dir, a)
        if h is not None:
            out[a] = h
    return out


def _source_dir_hash(build_dir: str) -> Optional[str]:
    """Hash of all staged .md files under <build>/source, stable across order."""
    import hashlib

    src = os.path.join(build_dir, "source")
    if not os.path.isdir(src):
        return None
    parts = []
    for fn in sorted(os.listdir(src)):
        if fn.endswith(".md"):
            with open(os.path.join(src, fn), "r", encoding="utf-8") as fh:
                parts.append(fn + "\u0000" + fh.read())
    if not parts:
        return None
    return hashlib.sha256("\u0000".join(parts).encode("utf-8")).hexdigest()


def read_metadata(build_dir: str, artifact_type: str) -> Dict[str, Any]:
    p = os.path.join(artifact_path(build_dir, artifact_type), "metadata.json")
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_diagnostics(build_dir: str, artifact_type: str) -> Dict[str, Any]:
    p = os.path.join(artifact_path(build_dir, artifact_type), "diagnostics.json")
    if not os.path.isfile(p):
        return {"diagnostics": []}
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_against_schema(
    data: Dict[str, Any], schema_id: Optional[str], schema_dir: str = DEFAULT_SCHEMA_DIR
) -> List[str]:
    """Validate ``data`` against ``<schema_dir>/<schema_id>.json``.

    Returns a list of human-readable error strings (empty == valid). If the
    schema file is missing or ``jsonschema`` is not installed, validation is
    skipped and an info note is returned so the build never hard-fails on
    environment differences.
    """
    if not schema_id:
        return []
    schema_path = os.path.join(schema_dir, f"{schema_id}.json")
    if not os.path.isfile(schema_path):
        return [f"schema '{schema_id}' not found at {schema_path} (skipped)"]
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return ["jsonschema not installed (validation skipped)"]
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{loc}: {err.message}")
    return errors


def write_artifact(
    build_dir: str,
    artifact_type: str,
    data: Dict[str, Any],
    pass_id: str,
    source_artifacts: Optional[List[str]] = None,
    schema_id: Optional[str] = None,
    schema_dir: str = DEFAULT_SCHEMA_DIR,
    diagnostics: Optional[Dict[str, Any]] = None,
    source_hashes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Persist an artifact immutably.

    Returns the metadata dict that was written (useful for callers/tests).
    """
    source_artifacts = source_artifacts or []
    if source_hashes is None:
        source_hashes = source_hashes_of(build_dir, source_artifacts)
    os.makedirs(artifact_path(build_dir, artifact_type), exist_ok=True)

    data_doc = _stable_json(data)
    content_hash = hashlib.sha256(data_doc.encode("utf-8")).hexdigest()

    artifact_file = os.path.join(
        artifact_path(build_dir, artifact_type), "artifact.json"
    )
    with open(artifact_file, "w", encoding="utf-8") as fh:
        fh.write(data_doc)

    metadata = {
        "artifact_type": artifact_type,
        "producer_pass": pass_id,
        "schema_id": schema_id,
        "source_artifacts": source_artifacts,
        "source_hashes": source_hashes or {},
        "content_hash": content_hash,
        "tool_version": "knowledge-compiler-sdk/0.1.0",
    }
    with open(
        os.path.join(artifact_path(build_dir, artifact_type), "metadata.json"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write(_stable_json(metadata))

    # Diagnostics are written by the pass via DiagnosticEmitter; if provided
    # here we persist them too (idempotent with what the emitter writes).
    if diagnostics is not None:
        with open(
            os.path.join(
                artifact_path(build_dir, artifact_type), "diagnostics.json"
            ),
            "w",
            encoding="utf-8",
        ) as fh:
            fh.write(_stable_json(diagnostics))

    return metadata


class ArtifactStore:
    """Convenience wrapper around a build directory."""

    def __init__(self, build_dir: str, schema_dir: str = DEFAULT_SCHEMA_DIR):
        self.build_dir = build_dir
        self.schema_dir = schema_dir
        os.makedirs(build_dir, exist_ok=True)

    def has(self, artifact_type: str) -> bool:
        return artifact_exists(self.build_dir, artifact_type)

    def read(self, artifact_type: str) -> Dict[str, Any]:
        return read_artifact(self.build_dir, artifact_type)

    def metadata(self, artifact_type: str) -> Dict[str, Any]:
        return read_metadata(self.build_dir, artifact_type)

    def diagnostics(self, artifact_type: str) -> Dict[str, Any]:
        return read_diagnostics(self.build_dir, artifact_type)

    def available(self) -> List[str]:
        if not os.path.isdir(self.build_dir):
            return []
        return sorted(
            d
            for d in os.listdir(self.build_dir)
            if os.path.isfile(os.path.join(self.build_dir, d, "artifact.json"))
        )

    def write(
        self,
        artifact_type: str,
        data: Dict[str, Any],
        pass_id: str,
        source_artifacts: Optional[List[str]] = None,
        schema_id: Optional[str] = None,
        diagnostics: Optional[Dict[str, Any]] = None,
        source_hashes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return write_artifact(
            self.build_dir,
            artifact_type,
            data,
            pass_id,
            source_artifacts=source_artifacts,
            schema_id=schema_id,
            schema_dir=self.schema_dir,
            diagnostics=diagnostics,
            source_hashes=source_hashes,
        )

    def validate(self, artifact_type: str, schema_id: Optional[str] = None):
        schema_id = schema_id or self.metadata(artifact_type).get("schema_id")
        return validate_against_schema(
            self.read(artifact_type), schema_id, self.schema_dir
        )
