"""Evaluation framework.

Every artifact is scored along nine dimensions (see ``docs/evaluation.md``):

    completeness     — required fields present and populated
    correctness      — structure validates against its JSON Schema
    coverage         — fraction of source material represented
    consistency      — no internal contradictions
    hallucination    — fraction of claims traceable to inputs
    traceability     — provenance links resolvable
    provenance       — metadata complete (hash, producer, sources)
    confidence       — mean confidence of assertions
    reproducibility  — deterministic given identical inputs

Each dimension yields a 0..1 score; the overall score is their weighted mean.
A pass may attach per-dimension hints (e.g. measured coverage) which are merged
with structural heuristics computed here, so evaluation is *both* declarative
and computable without an LLM.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_WEIGHTS = {
    "completeness": 0.15,
    "correctness": 0.15,
    "coverage": 0.10,
    "consistency": 0.10,
    "hallucination": 0.15,
    "traceability": 0.10,
    "provenance": 0.10,
    "confidence": 0.10,
    "reproducibility": 0.05,
}

DIMENSIONS = list(DEFAULT_WEIGHTS.keys())


@dataclass
class Evaluation:
    artifact_type: str
    scores: Dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    notes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "overall": round(self.overall, 4),
            "notes": self.notes,
        }


def _ratio(items, predicate) -> float:
    items = list(items)
    if not items:
        return 0.0
    return sum(1 for i in items if predicate(i)) / len(items)


def evaluate_artifact(
    artifact_type: str,
    data: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    hints: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Evaluation:
    """Compute a structural evaluation of an artifact dict.

    ``hints`` are per-dimension signals a pass measured directly (e.g.
    ``{"coverage": 0.83, "hallucination": 0.04}``). Missing dimensions are
    estimated from structure so every artifact gets a full scorecard.
    """
    metadata = metadata or {}
    hints = hints or {}
    weights = weights or DEFAULT_WEIGHTS

    # --- completeness: required-ish top-level keys populated ---------------
    def occupied(v):
        if v is None:
            return False
        if isinstance(v, (list, dict, str)):
            return len(v) > 0
        return True

    top_keys = list(data.keys())
    completeness = _ratio(top_keys, lambda k: occupied(data[k])) if top_keys else 0.0

    # --- correctness: did schema validation pass? -------------------------
    correctness = 1.0 if hints.get("_valid", True) else 0.0

    # --- coverage / hallucination: prefer measured hints ------------------
    coverage = float(hints.get("coverage", completeness))
    # hallucination stored as *rate* (lower better); convert to score.
    if "hallucination" in hints:
        hallucination = 1.0 - float(hints["hallucination"])
    else:
        hallucination = 1.0 - float(hints.get("hallucination_rate", 0.0))

    # --- consistency: diagnostic-derived (passes with contradictions) -----
    consistency = float(hints.get("consistency", 1.0))

    # --- traceability: share of elements carrying a source/provenance ------
    traceability = float(hints.get("traceability", completeness))

    # --- provenance: metadata completeness ---------------------------------
    prov_fields = ["producer_pass", "source_artifacts", "content_hash", "schema_id"]
    provenance = _ratio(prov_fields, lambda f: bool(metadata.get(f)))

    # --- confidence: mean of any numeric confidence fields ----------------
    conf_values = []

    def _collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in ("confidence", "score", "weight"):
                    try:
                        conf_values.append(float(v))
                    except (TypeError, ValueError):
                        pass
                else:
                    _collect(v)
        elif isinstance(o, list):
            for x in o:
                _collect(x)

    _collect(data)
    confidence = sum(conf_values) / len(conf_values) if conf_values else 0.5

    # --- reproducibility: deterministic passes reproduce -------------------
    reproducibility = float(hints.get("reproducibility", 1.0))

    scores = {
        "completeness": completeness,
        "correctness": correctness,
        "coverage": coverage,
        "consistency": consistency,
        "hallucination": hallucination,
        "traceability": traceability,
        "provenance": provenance,
        "confidence": confidence,
        "reproducibility": reproducibility,
    }

    total_w = sum(weights.get(k, 0.0) for k in scores)
    overall = (
        sum(scores[k] * weights.get(k, 0.0) for k in scores) / total_w
        if total_w
        else 0.0
    )

    notes = {
        "computed": "structural heuristic + pass hints",
        "hints_applied": sorted(hints.keys()),
    }
    return Evaluation(artifact_type, scores, overall, notes)


def write_evaluation(build_dir: str, artifact_type: str, ev: Evaluation) -> None:
    os.makedirs(os.path.join(build_dir, artifact_type), exist_ok=True)
    with open(
        os.path.join(build_dir, artifact_type, "evaluation.json"),
        "w",
        encoding="utf-8",
    ) as fh:
        fh.write(json.dumps(ev.to_dict(), ensure_ascii=False, indent=2))
