"""Tests for the Knowledge Compiler core: registry, parse, orchestration,
evaluation, diagnostics, and artifact I/O.

These run with only the runtime dependencies (pyyaml, and jsonschema if
installed). They exercise the real, deterministic engine end-to-end.
"""

import importlib.util
import os

import pytest

from compiler.core import (
    ArtifactStore,
    Compiler,
    DiagnosticEmitter,
    evaluate_artifact,
)


def _load_parse_run():
    spec = importlib.util.spec_from_file_location(
        "pass_01_parse_run",
        os.path.join(os.path.dirname(__file__), "..",
                     "compiler", "passes", "pass-01-parse", "run.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parse_run = _load_parse_run()


# --------------------------------------------------------------------------- #
# Pass registry
# --------------------------------------------------------------------------- #
def test_registry_discovers_all_passes(registry):
    assert len(registry.passes) == 10
    assert registry.pass_producing("markdown-ir").id == "pass-01-parse"
    assert registry.pass_producing("application-ir").id == "pass-10-software"


def test_registry_resolves_dependencies(registry):
    decl = registry.pass_producing("graph-ir")
    assert "ontology-ir" in decl.consumes
    assert "markdown-ir" in decl.consumes


def test_registry_declares_determinism(registry):
    assert registry.get("pass-01-parse").deterministic is True
    assert registry.get("pass-02-extract").model_required is True


# --------------------------------------------------------------------------- #
# Artifact store + I/O
# --------------------------------------------------------------------------- #
def test_write_and_read_artifact(tmp_path):
    store = ArtifactStore(str(tmp_path))
    meta = store.write(
        "markdown-ir",
        {"documents": [{"id": "doc-1"}]},
        pass_id="pass-01-parse",
        source_artifacts=["a.md"],
        schema_id="markdown-ir",
    )
    assert store.has("markdown-ir")
    assert store.read("markdown-ir")["documents"][0]["id"] == "doc-1"
    assert meta["producer_pass"] == "pass-01-parse"
    assert "content_hash" in meta
    assert "a.md" in meta["source_artifacts"]


def test_immutability_via_lineage(tmp_path):
    store = ArtifactStore(str(tmp_path))
    m1 = store.write("markdown-ir", {"v": 1}, "pass-01-parse")
    m2 = store.write("markdown-ir", {"v": 2}, "pass-01-parse")
    assert store.read("markdown-ir")["v"] == 2
    assert m1["content_hash"] != m2["content_hash"]


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def test_diagnostic_emitter_counts_and_writes(tmp_path):
    em = DiagnosticEmitter("markdown-ir", str(tmp_path))
    em.warning("SPARSE_GRAPH", "low degree")
    em.error("MISSING_EVIDENCE", "no docs")
    em.info("NOTE", "ok")
    dump = em.dump()
    assert dump["counts"] == {"error": 1, "warning": 1, "info": 1}
    em.write()
    assert os.path.isfile(os.path.join(str(tmp_path), "markdown-ir", "diagnostics.json"))


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def test_evaluation_computes_scorecard():
    data = {"documents": [{"id": "d1"}], "citations": [{"doc": "d1"}]}
    meta = {"producer_pass": "pass-01-parse", "source_artifacts": ["a.md"],
            "content_hash": "x", "schema_id": "markdown-ir"}
    ev = evaluate_artifact(
        "markdown-ir", data, meta,
        hints={"coverage": 1.0, "traceability": 1.0, "reproducibility": 1.0},
    )
    assert 0.0 <= ev.overall <= 1.0
    assert ev.scores["completeness"] == 1.0
    assert ev.scores["provenance"] == 1.0
    assert ev.scores["hallucination"] == 1.0


def test_evaluation_flags_hallucination():
    ev = evaluate_artifact("x", {}, {}, hints={"hallucination": 0.5})
    assert ev.scores["hallucination"] == 0.5  # 1 - rate


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def test_orchestrator_plans_full_pipeline(registry, tmp_path):
    compiler = Compiler(registry, str(tmp_path))
    plan = compiler.plan_to("application-ir")
    produced = {s.produces for s in plan.steps}
    for t in ["markdown-ir", "entity-ir", "ontology-ir", "graph-ir",
              "semantic-ir", "reasoning-ir", "application-ir"]:
        assert t in produced


def test_orchestrator_runs_parse_and_plans_rest(registry, sample_corpus, tmp_path):
    build = str(tmp_path / "build")
    compiler = Compiler(registry, build)
    os.makedirs(os.path.join(build, "source"), exist_ok=True)
    for fn in os.listdir(sample_corpus):
        if fn.endswith(".md"):
            with open(os.path.join(sample_corpus, fn)) as fh:
                data = fh.read()
            with open(os.path.join(build, "source", fn), "w") as out:
                out.write(data)
    summary = compiler.run(target=None, dry_run=False)
    records = {r["pass_id"]: r["status"] for r in summary["records"]}
    assert records["pass-01-parse"] == "ok"
    assert records["pass-02-extract"] == "skipped"
    store = ArtifactStore(build)
    assert store.has("markdown-ir")
    assert store.read("markdown-ir")["metadata"]["document_count"] == 2
    assert store.read("markdown-ir")["metadata"]["cross_document_links"] == 1


def test_orchestrator_dry_run_skips_everything(registry, sample_corpus, tmp_path):
    build = str(tmp_path / "build")
    os.makedirs(os.path.join(build, "source"), exist_ok=True)
    for fn in os.listdir(sample_corpus):
        if fn.endswith(".md"):
            with open(os.path.join(sample_corpus, fn)) as fh:
                data = fh.read()
            with open(os.path.join(build, "source", fn), "w") as out:
                out.write(data)
    compiler = Compiler(registry, build)
    summary = compiler.run(target=None, dry_run=True)
    assert all(r["status"] == "skipped" for r in summary["records"])
    assert not ArtifactStore(build).has("markdown-ir")


def test_orchestrator_unknown_target_raises(registry, tmp_path):
    compiler = Compiler(registry, str(tmp_path))
    with pytest.raises(ValueError):
        compiler.plan_to("nonexistent-ir")


# --------------------------------------------------------------------------- #
# parse-01 entrypoint directly
# --------------------------------------------------------------------------- #
def test_pass01_parse_entrypoint(sample_corpus, tmp_path):
    build = str(tmp_path / "build")
    os.makedirs(os.path.join(build, "source"), exist_ok=True)
    for fn in os.listdir(sample_corpus):
        if fn.endswith(".md"):
            with open(os.path.join(sample_corpus, fn)) as fh:
                data = fh.read()
            with open(os.path.join(build, "source", fn), "w") as out:
                out.write(data)
    rc = parse_run.main([build])
    assert rc == 0
    store = ArtifactStore(build)
    assert store.has("markdown-ir")
    ir = store.read("markdown-ir")
    assert ir["documents"][0]["title"] == "Title One"
    assert ir["document_graph"]["edges"][0]["to"] == "doc-2"
