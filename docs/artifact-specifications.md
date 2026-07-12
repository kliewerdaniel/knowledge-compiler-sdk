# Artifact Specifications

Every artifact in the Knowledge Compiler is a **directory** under the build
root, containing a fixed set of files. This document defines the on-disk
contract so any tool — agent or program — can read or write artifacts
interchangeably.

## The artifact directory layout

```
build/
  <artifact-type>/
    artifact.json      # the IR data (validated against schemas/<id>.json)
    metadata.json      # provenance: producer, inputs, timestamp, content hash
    diagnostics.json   # compiler diagnostics (warnings/errors/notes)
    evaluation.json    # nine-dimension scorecard (written by deterministic passes)
    <derived views>    # graph.graphml, graph.mmd, architecture.mmd, deployment.md, ...
  plan.json            # the orchestrator's plan + per-pass run records
  source/              # the staged Markdown inputs
```

### artifact.json
The primary payload. Must validate against its JSON Schema. It is written with
**canonical JSON** (keys sorted, UTF-8, 2-space indent) so the `content_hash` is
stable across runs — this is what makes determinism *checkable*.

### metadata.json
```json
{
  "artifact_type": "markdown-ir",
  "producer_pass": "pass-01-parse",
  "schema_id": "markdown-ir",
  "source_artifacts": ["a.md", "b.md"],
  "content_hash": "sha256:...",
  "tool_version": "knowledge-compiler-sdk/0.1.0"
}
```
`source_artifacts` records lineage so provenance is resolvable across passes.

### diagnostics.json
```json
{
  "artifact_type": "markdown-ir",
  "counts": {"error": 0, "warning": 1, "info": 0},
  "diagnostics": [
    {"code": "INSUFFICIENT_CITATIONS", "severity": "warning",
     "message": "...", "loc": "", "metadata": {}}
  ]
}
```

### evaluation.json
```json
{
  "artifact_type": "markdown-ir",
  "scores": {"completeness": 1.0, "correctness": 1.0, "...": 0.83},
  "overall": 0.94,
  "notes": {"computed": "structural heuristic + pass hints"}
}
```

## Artifact types and their schemas

| Artifact type   | Schema                  | Producer           |
|-----------------|-------------------------|--------------------|
| `markdown-ir`   | `schemas/markdown-ir.json`   | `pass-01-parse`    |
| `entity-ir`     | `schemas/entity-ir.json`     | `pass-02-extract`  |
| `ontology-ir`   | `schemas/ontology-ir.json`   | `pass-03-ontology` |
| `graph-ir`      | `schemas/graph-ir.json`      | `pass-04-graph`    |
| `semantic-ir`   | `schemas/semantic-ir.json`   | `pass-05/06/07`    |
| `reasoning-ir`  | `schemas/reasoning-ir.json`  | `pass-08-reasoning`|
| `application-ir`| `schemas/application-ir.json`| `pass-09/10`       |

## Output format policy

The project mandates **inspectable artifacts**. A pass must emit, where
applicable:

- **JSON** — machine-readable IR data.
- **Markdown** — human-readable narrative (reports, specs).
- **YAML** — pass declarations and config.
- **GraphML** — graph interchange for Gephi/yEd.
- **Mermaid** — inline-renderable diagrams.
- **PlantUML** — alternative diagram source.
- **SVG** — rendered visualisations.
- **HTML** — standalone browsable views.
- **TypeScript interfaces** — typed bindings for generated code.
- **JSON Schemas** — the contracts themselves.

Nothing is hidden inside a conversation. If an agent reasoned about something,
the artifact is the record.

## Immutability & lineage

Artifacts are never edited in place. A revision is a *new* artifact (usually a
higher IR), and `metadata.source_artifacts` + `content_hash` preserve the chain.
This is what makes a build reproducible and diffable: `git diff build/` shows
exactly how knowledge compiled differently.
