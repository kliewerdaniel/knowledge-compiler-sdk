"""Tests for the Knowledge Compiler core: registry, parse, orchestration,
evaluation, diagnostics, and artifact I/O.

These run with only the runtime dependencies (pyyaml, and jsonschema if
installed). They exercise the real, deterministic engine end-to-end.
"""

import importlib.util
import json
import os
import shutil

import pytest


from compiler.core import (
    ArtifactStore,
    Compiler,
    DiagnosticEmitter,
    PassRegistry,
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
    # Deterministic parse runs for real.
    assert records["pass-01-parse"] == "ok"
    # Model passes without --local either fail (they now have entrypoints that
    # try the local server) or are skipped; they must never silently "ok".
    for pid in ["pass-02-extract", "pass-03-ontology", "pass-10-software"]:
        assert records[pid] != "ok", f"{pid} should not pass without a server"
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


# --------------------------------------------------------------------------- #
# Local inference (port-based) support
# --------------------------------------------------------------------------- #
def test_extract_json_strips_fences():
    from compiler.core.inference import extract_json

    fenced = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert extract_json(fenced) == {"a": 1, "b": [2, 3]}
    prose = 'Here is the result:\n{"entities": [], "terms": [], "claims": []}'
    assert extract_json(prose)["entities"] == []


def test_all_model_passes_have_entrypoints(registry):
    passes_root = os.path.join(
        os.path.dirname(__file__), "..", "compiler", "passes"
    )
    for decl in registry.all():
        entry = os.path.join(passes_root, decl.id, "run.py")
        assert os.path.isfile(entry), f"missing entrypoint for {decl.id}"


def test_run_model_pass_with_stubbed_client(tmp_path, monkeypatch):
    """Exercise the model-pass scaffold without a live server."""
    from compiler.core import llm_pass

    build = str(tmp_path)
    store = ArtifactStore(build)
    # seed an input artifact the pass will consume
    store.write("markdown-ir", {"documents": [{"id": "doc-1"}]},
                pass_id="pass-01-parse")

    class _StubClient:
        def complete_json(self, system, user, temperature=0.2, **kwargs):
            return {"entities": [{"id": "e1", "label": "X", "type": "concept",
                                  "span": {"doc": "doc-1", "section": "sec-1-1"},
                                  "confidence": 0.9}],
                    "terms": [], "claims": []}

    monkeypatch.setattr(
        llm_pass, "InferenceClient",
        lambda *a, **k: _StubClient(),
    )
    rc = llm_pass.run_model_pass(
        build_dir=build,
        produces="entity-ir",
        consumes=["markdown-ir"],
        system_prompt="sys",
        user_prompt_fn=lambda inputs: "user",
        port=8080,
    )
    assert rc == 0
    assert store.has("entity-ir")
    data = store.read("entity-ir")
    assert data["entities"][0]["label"] == "X"
    assert store.metadata("entity-ir")["producer_pass"] == "model-pass:entity-ir"


def test_model_pass_retries_on_failure(tmp_path, monkeypatch):
    """A pass retries when the model returns malformed JSON, then succeeds."""
    from compiler.core import llm_pass

    build = str(tmp_path)
    store = ArtifactStore(build)
    store.write("markdown-ir", {"documents": [{"id": "doc-1"}]}, pass_id="pass-01-parse")

    calls = {"n": 0}

    class _FlakyClient:
        def complete_json(self, system, user, temperature=0.2, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                # simulate a model that emits garbage / no JSON object
                raise ValueError("model response did not contain a JSON object")
            return {"entities": [{"id": "e1", "label": "X", "type": "concept",
                                  "span": {"doc": "doc-1", "section": "s"},
                                  "confidence": 0.9}],
                    "terms": [], "claims": []}

    monkeypatch.setattr(llm_pass, "InferenceClient", lambda *a, **k: _FlakyClient())
    rc = llm_pass.run_model_pass(
        build_dir=build,
        produces="entity-ir",
        consumes=["markdown-ir"],
        system_prompt="sys",
        user_prompt_fn=lambda inputs: "user",
        port=8080,
        max_retries=3,
    )
    assert rc == 0
    assert calls["n"] == 3  # failed twice, succeeded on 3rd
    assert store.has("entity-ir")


def test_model_pass_gives_up_after_max_retries(tmp_path, monkeypatch):
    """If the model never returns JSON, the pass fails (not silent skip)."""
    from compiler.core import llm_pass

    build = str(tmp_path)
    store = ArtifactStore(build)
    store.write("markdown-ir", {"documents": [{"id": "doc-1"}]}, pass_id="pass-01-parse")

    class _AlwaysBad:
        def complete_json(self, system, user, temperature=0.2, **kwargs):
            raise ValueError("no json")

    monkeypatch.setattr(llm_pass, "InferenceClient", lambda *a, **k: _AlwaysBad())
    rc = llm_pass.run_model_pass(
        build_dir=build,
        produces="entity-ir",
        consumes=["markdown-ir"],
        system_prompt="sys",
        user_prompt_fn=lambda inputs: "user",
        port=8080,
        max_retries=2,
    )
    assert rc == 1  # failure, not 0
    assert not store.has("entity-ir")  # nothing written


def test_evaluation_dashboard_generates(tmp_path):
    """The report module scans evaluation.json and emits self-contained HTML."""
    from compiler.reports.dashboard import collect, render_html, build_dashboard

    build = str(tmp_path)
    # write two evaluations with distinct scores
    os.makedirs(os.path.join(build, "entity-ir"), exist_ok=True)
    with open(os.path.join(build, "entity-ir", "evaluation.json"), "w") as fh:
        json.dump({"artifact_type": "entity-ir",
                   "scores": {d: 0.9 for d in
                              ["completeness", "correctness", "coverage",
                               "consistency", "hallucination", "traceability",
                               "provenance", "confidence", "reproducibility"]},
                   "overall": 0.9}, fh)
    os.makedirs(os.path.join(build, "graph-ir"), exist_ok=True)
    with open(os.path.join(build, "graph-ir", "evaluation.json"), "w") as fh:
        json.dump({"artifact_type": "graph-ir",
                   "scores": {d: 0.4 for d in
                              ["completeness", "correctness", "coverage",
                               "consistency", "hallucination", "traceability",
                               "provenance", "confidence", "reproducibility"]},
                   "overall": 0.4}, fh)

    recs = collect(build)
    assert len(recs) == 2
    # sorted ascending by overall -> graph-ir (0.4) first
    assert recs[0]["artifact"] == "graph-ir"

    html = render_html(recs, build)
    assert "<!doctype html>" in html
    assert "window.__EVAL__" in html
    # weakest artifact surfaces first in the rendered cards
    assert html.index("graph-ir") < html.index("entity-ir")
    # no external/CDN dependency
    assert "http://" not in html and "https://" not in html

    out = build_dashboard(build)
    assert out and os.path.isfile(out)
    assert out.endswith("evaluation_dashboard.html")


def test_evaluation_dashboard_handles_missing(tmp_path):
    """With no evaluations, the dashboard still renders (empty state)."""
    from compiler.reports.dashboard import collect, render_html, build_dashboard
    build = str(tmp_path)
    assert collect(build) == []
    html = render_html([], build)
    assert "No evaluations found." in html
    out = build_dashboard(build)
    assert out and os.path.isfile(out)


def test_ontology_repair_drops_dangling_refs(tmp_path):
    """repair_fn drops relationships to unknown concepts and warns."""
    from compiler.core import llm_pass
    from compiler.core.diagnostics import DiagnosticEmitter

    build = str(tmp_path)
    os.makedirs(os.path.join(build, "ontology-ir"), exist_ok=True)
    data = {
        "concepts": [{"id": "c1", "label": "A"}, {"id": "c2", "label": "B"}],
        "relationships": [
            {"id": "r1", "source": "c1", "target": "c2", "type": "depends-on"},
            {"id": "r2", "source": "c1", "target": "GHOST", "type": "depends-on"},
        ],
        "hierarchies": [],
        "aliases": [],
    }
    emitter = DiagnosticEmitter("ontology-ir", build)
    # import the actual repair from the pass
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p03", os.path.join(os.path.dirname(__file__), "..",
                            "compiler", "passes", "pass-03-ontology", "run.py"))
    p03 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p03)
    repaired = p03.repair(data, {}, emitter)
    rel_ids = [r["id"] for r in repaired["relationships"]]
    assert "r1" in rel_ids and "r2" not in rel_ids
    diag = emitter.dump()
    assert any(d["code"] == "UNREFERENCED_ENTITY" for d in diag["diagnostics"])


def test_graph_repair_detects_cycles(tmp_path):
    """repair_fn annotates cycle edges and writes GraphML/Mermaid."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p04", os.path.join(os.path.dirname(__file__), "..",
                            "compiler", "passes", "pass-04-graph", "run.py"))
    p04 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p04)
    from compiler.core.diagnostics import DiagnosticEmitter

    build = str(tmp_path)
    data = {
        "nodes": [{"id": "n1", "label": "A", "concept_ref": "c1"},
                  {"id": "n2", "label": "B", "concept_ref": "c2"}],
        "edges": [{"id": "e1", "source": "n1", "target": "n2", "type": "x"},
                  {"id": "e2", "source": "n2", "target": "n1", "type": "y"}],
    }
    emitter = DiagnosticEmitter("graph-ir", build)
    p04.repair(data, {}, emitter)
    cyc = [e for e in data["edges"] if e.get("cycle")]
    assert len(cyc) >= 1
    assert os.path.isfile(os.path.join(build, "graph-ir", "graph.graphml"))
    assert os.path.isfile(os.path.join(build, "graph-ir", "graph.mmd"))


def test_embeddings_fallback_to_ollama(tmp_path, monkeypatch):
    """When /v1/embeddings is unsupported, fall back to Ollama native API."""
    import http.server, socketserver, threading

    # A chat server stub that rejects embeddings with 501.
    class Chat(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(501)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"code":501,"message":"no embeddings"}}')

        def log_message(self, *a):
            pass

    # An Ollama stub returning a fixed embedding vector.
    class Ollama(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"embedding":[0.1,0.2,0.3]}')

        def log_message(self, *a):
            pass

    chat = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Chat)
    oll = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Ollama)
    chat.allow_reuse_address = True
    oll.allow_reuse_address = True
    cport = chat.server_address[1]
    oport = oll.server_address[1]
    t1 = threading.Thread(target=chat.serve_forever, daemon=True)
    t2 = threading.Thread(target=oll.serve_forever, daemon=True)
    t1.start(); t2.start()

    from compiler.core.inference import InferenceClient
    client = InferenceClient(port=cport, host="127.0.0.1",
                              ollama_host="127.0.0.1", ollama_port=oport,
                              embedding_model="nomic-embed-text:latest")
    vecs = client.embeddings(["a", "b"])
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.2, 0.3]
    chat.shutdown(); oll.shutdown()


def test_incremental_cache_skips_unchanged(tmp_path, sample_corpus):
    build = str(tmp_path / "build")
    compiler = Compiler(PassRegistry(_passes_root()), build)
    os.makedirs(os.path.join(build, "source"), exist_ok=True)
    for fn in os.listdir(sample_corpus):
        import shutil
        shutil.copy(os.path.join(sample_corpus, fn),
                    os.path.join(build, "source", fn))
    # first run: parse executes
    r1 = compiler.run(dry_run=False)
    parsed = [x for x in r1["records"] if x["pass_id"] == "pass-01-parse"][0]
    assert parsed["status"] == "ok"
    # second run with incremental: parse is cached (inputs unchanged)
    r2 = compiler.run(dry_run=False, incremental=True)
    parsed2 = [x for x in r2["records"] if x["pass_id"] == "pass-01-parse"][0]
    assert parsed2["status"] == "cached"


def test_only_flag_runs_single_pass(tmp_path, sample_corpus):
    build = str(tmp_path / "build")
    # seed markdown-ir so pass-02 has its input
    store = ArtifactStore(build)
    store.write("markdown-ir", {"documents": [{"id": "d1"}]}, pass_id="pass-01-parse")
    compiler = Compiler(PassRegistry(_passes_root()), build)
    r = compiler.run(only="pass-02-extract", local=False)
    assert [s["pass_id"] for s in r["plan"]["steps"]] == ["pass-02-extract"]
    # without --local a model pass is skipped (no server)
    assert r["records"][0]["status"] == "skipped"


def test_pass10_generates_nextjs_app(tmp_path):
    """pass-10 writes a runnable Next.js scaffold (data + viewer + api routes)."""
    import importlib.util

    build = str(tmp_path)
    store = ArtifactStore(build)
    store.write("graph-ir", {"nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
                             "edges": [{"source": "n1", "target": "n2", "type": "part-of"}]},
                pass_id="t", schema_id="graph-ir")
    store.write("semantic-ir", {"themes": [{"id": "t1", "label": "T"}]}, pass_id="t", schema_id="semantic-ir")
    store.write("reasoning-ir", {"observations": [{"id": "o1", "text": "x", "provenance": ["n1"], "confidence": 0.5}],
                                "hypotheses": [], "contradictions": [], "questions": []},
                pass_id="t", schema_id="reasoning-ir")
    store.write("application-ir", {
        "architecture": {"layers": ["ui"], "rationale": "single page"},
        "pages": [{"id": "p1", "title": "Home", "route": "/", "components": ["KnowledgeGraphVisualizer"]}],
        "components": [{"id": "cmp1", "name": "graph view", "responsibility": "show graph"}],
        "routes": [{"path": "/", "page_id": "p1", "method": "GET"}],
        "apis": [{"path": "/api/graph", "method": "GET", "purpose": "serve"}],
        "deployment_plan": {"target": "static", "steps": ["build"], "prerequisites": ["node"]},
    }, pass_id="pass-09-specifications", schema_id="application-ir")

    spec = importlib.util.spec_from_file_location(
        "p10", os.path.join(_passes_root(), "pass-10-software", "run.py"))
    p10 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p10)
    from compiler.core.diagnostics import DiagnosticEmitter
    app_root = p10.generate(build, store.read("application-ir"),
                            DiagnosticEmitter("application-ir", build))
    # runnable contract
    assert os.path.isfile(os.path.join(app_root, "package.json"))
    assert os.path.isfile(os.path.join(app_root, "app", "page.tsx"))
    assert os.path.isfile(os.path.join(app_root, "components", "KnowledgeGraphVisualizer.tsx"))
    assert os.path.isfile(os.path.join(app_root, "data", "graph-ir.json"))
    assert os.path.isfile(os.path.join(app_root, "app", "api", "graph", "route.ts"))
    assert os.path.isfile(os.path.join(app_root, "README.md"))


def _passes_root():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "compiler", "passes")


def test_ontology_normalizes_vocab(tmp_path):
    """repair_fn normalizes PART_OF -> part-of and drops unknown types."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p03b", os.path.join(_passes_root(), "pass-03-ontology", "run.py"))
    p03 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p03)
    from compiler.core.diagnostics import DiagnosticEmitter

    build = str(tmp_path)
    os.makedirs(os.path.join(build, "ontology-ir"), exist_ok=True)
    data = {
        "concepts": [{"id": "c1", "label": "A"}, {"id": "c2", "label": "B"}],
        "relationships": [
            {"id": "r1", "source": "c1", "target": "c2", "type": "PART_OF"},
            {"id": "r2", "source": "c1", "target": "c2", "type": "WAT"},
        ],
        "hierarchies": [], "aliases": [],
    }
    emitter = DiagnosticEmitter("ontology-ir", build)
    out = p03.repair(data, {}, emitter)
    types = [r["type"] for r in out["relationships"]]
    assert "part-of" in types
    assert "WAT" not in types
    diag = emitter.dump()
    assert any(d["code"] == "VOCAB" for d in diag["diagnostics"])


def test_reasoning_seeds_when_empty(tmp_path):
    import importlib.util
    from compiler.core.diagnostics import DiagnosticEmitter

    spec = importlib.util.spec_from_file_location(
        "p08b", os.path.join(_passes_root(), "pass-08-reasoning", "run.py"))
    p08 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p08)
    build = str(tmp_path)
    data = {"observations": [], "hypotheses": [], "contradictions": [], "questions": []}
    emitter = DiagnosticEmitter("reasoning-ir", build)
    out = p08.repair(data, {"graph-ir": {"nodes": [{"id": "n1", "label": "X", "concept_ref": "c1"}]}}, emitter)
    assert len(out["observations"]) >= 1
    assert any(d["code"] == "MISSING_EVIDENCE" for d in emitter.dump()["diagnostics"])


def test_generated_app_is_runnable(tmp_path):
    """pass-10 copies IRs to data/, emits data-serving API routes + viewer."""
    import importlib.util
    from compiler.core import ArtifactStore

    d = str(tmp_path)
    store = ArtifactStore(d)
    # seed the inputs pass-10 reads back
    store.write("graph-ir", {"nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
                             "edges": [{"source": "n1", "target": "n2", "type": "part-of"}]},
                pass_id="t", schema_id="graph-ir")
    store.write("semantic-ir", {"themes": [{"id": "t1", "label": "T"}]}, pass_id="t", schema_id="semantic-ir")
    store.write("reasoning-ir", {"observations": [{"id": "o1", "text": "x", "provenance": ["n1"], "confidence": 0.5}],
                                "hypotheses": [], "contradictions": [], "questions": []},
                pass_id="t", schema_id="reasoning-ir")
    store.write("application-ir", {
        "architecture": {"layers": ["ui"], "rationale": "x"},
        "pages": [{"id": "p1", "title": "Home", "route": "/", "components": ["KnowledgeGraphVisualizer"]}],
        "components": [{"id": "cmp1", "name": "graph view", "responsibility": "show graph"}],
        "routes": [{"path": "/", "page_id": "p1", "method": "GET"}],
        "apis": [{"path": "/api/graph", "method": "GET", "purpose": "serve graph"}],
        "deployment_plan": {"target": "static", "steps": ["build"], "prerequisites": ["node"]}},
        pass_id="pass-09-specifications", schema_id="application-ir")

    # seed 9-dimension evaluations so the app's /evaluation route has data
    for art in ("graph-ir", "semantic-ir", "reasoning-ir", "application-ir"):
        os.makedirs(os.path.join(d, art), exist_ok=True)
        with open(os.path.join(d, art, "evaluation.json"), "w") as fh:
            json.dump({"artifact_type": art,
                       "scores": {k: 0.8 for k in
                                  ["completeness", "correctness", "coverage",
                                   "consistency", "hallucination", "traceability",
                                   "provenance", "confidence", "reproducibility"]},
                       "overall": 0.8}, fh)

    spec = importlib.util.spec_from_file_location(
        "p10c", os.path.join(_passes_root(), "pass-10-software", "run.py"))
    p10 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p10)

    from compiler.core.diagnostics import DiagnosticEmitter
    app_root = p10.generate(d, store.read("application-ir"), DiagnosticEmitter("application-ir", d))

    # data copied
    assert os.path.isfile(os.path.join(app_root, "data", "graph-ir.json"))
    assert os.path.isfile(os.path.join(app_root, "data", "application-ir.json"))
    # evaluations folded into one file for the /evaluation route
    assert os.path.isfile(os.path.join(app_root, "data", "evaluations.json"))
    ev = json.load(open(os.path.join(app_root, "data", "evaluations.json")))
    assert isinstance(ev, list) and len(ev) == 4
    # evaluation API route + page + component exist
    assert os.path.isfile(os.path.join(app_root, "app", "api", "evaluation", "route.ts"))
    assert os.path.isfile(os.path.join(app_root, "app", "evaluation", "page.tsx"))
    assert os.path.isfile(os.path.join(app_root, "components", "EvaluationDashboard.tsx"))
    # api route serves the copied artifact (reads data/ at runtime)
    route = os.path.join(app_root, "app", "api", "graph", "route.ts")
    assert os.path.isfile(route)
    assert 'data", FILE' in open(route).read() or 'process.cwd(), "data"' in open(route).read()
    # graph viewer component exists
    assert os.path.isfile(os.path.join(app_root, "components", "KnowledgeGraphVisualizer.tsx"))
    # package.json present and valid json
    pkg = json.load(open(os.path.join(app_root, "package.json")))
    assert "next" in pkg["dependencies"]
    # vercel.json present for one-command deploy
    assert os.path.isfile(os.path.join(app_root, "vercel.json"))
    vj = json.load(open(os.path.join(app_root, "vercel.json")))
    assert vj.get("framework") == "nextjs"


def test_coerce_json_handles_extra_data_and_array():
    from compiler.core.inference import _coerce_json_object, extract_json
    # "Extra data": two JSON objects concatenated
    assert _coerce_json_object('{"a":1}{"b":2}') == {"a": 1}
    # prose prefix + trailing
    assert _coerce_json_object('ok here is the json:\n{"x": 3}\nthanks') == {"x": 3}
    # fenced block
    assert extract_json('```json\n{"y": 4}\n```') == {"y": 4}
    # array returned instead of object -> first contained object is extracted
    assert _coerce_json_object('[{"id": 1}]') == {"id": 1}


def test_api_route_serves_copied_artifact(tmp_path):
    """Simulate the generated route's read logic against copied data."""
    import importlib.util
    from compiler.core import ArtifactStore

    d = str(tmp_path)
    store = ArtifactStore(d)
    store.write("graph-ir", {"nodes": [{"id": "n1", "label": "A"}], "edges": []},
                pass_id="t", schema_id="graph-ir")
    spec = importlib.util.spec_from_file_location(
        "p10d", os.path.join(_passes_root(), "pass-10-software", "run.py"))
    p10 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p10)
    from compiler.core.diagnostics import DiagnosticEmitter
    app_root = p10.generate(d, store.read("application-ir") if store.has("application-ir") else {},
                           DiagnosticEmitter("application-ir", d))
    # emulate the route: read data/graph-ir.json from cwd
    data_file = os.path.join(app_root, "data", "graph-ir.json")
    served = json.load(open(data_file))
    assert served["nodes"][0]["label"] == "A"


def test_spec_backfills_when_empty(tmp_path):
    import importlib.util
    from compiler.core.diagnostics import DiagnosticEmitter

    spec = importlib.util.spec_from_file_location(
        "p09b", os.path.join(_passes_root(), "pass-09-specifications", "run.py"))
    p09 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p09)
    build = str(tmp_path)
    data = {}
    emitter = DiagnosticEmitter("application-ir", build)
    out = p09.repair(data, {"graph-ir": {"nodes": [{"id": "n1", "label": "Home", "concept_ref": "c1"}]},
                              "semantic-ir": {"themes": [{"id": "t1", "label": "T"}]}}, emitter)
    for key in ("architecture", "pages", "components", "routes", "apis", "deployment_plan"):
        assert key in out and out[key], key
    # should be schema-valid via the validation helper
    from compiler.core import ArtifactStore
    store = ArtifactStore(build)
    store.write("application-ir", out, pass_id="test", schema_id="application-ir")
    assert store.validate("application-ir", "application-ir") == []



