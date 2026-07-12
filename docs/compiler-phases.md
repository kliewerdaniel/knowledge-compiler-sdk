# Compiler Phases

This document specifies the ten compiler passes, their inputs/outputs, and the
diagnostics each may emit. Each pass is declared in `compiler/passes/<id>/pass.yaml`.
The orchestrator reads those declarations; nothing here is hardcoded.

## Pass overview

| #  | Pass                  | Produces       | Consumes                          | Deterministic | Model |
|----|-----------------------|----------------|-----------------------------------|---------------|-------|
| 01 | Parse                 | `markdown-ir`  | (raw Markdown)                    | yes           | no    |
| 02 | Extract               | `entity-ir`    | `markdown-ir`                     | no            | yes   |
| 03 | Ontology              | `ontology-ir`  | `entity-ir`                       | no            | yes   |
| 04 | Graph                 | `graph-ir`     | `ontology-ir`, `markdown-ir`      | no            | yes   |
| 05 | Embeddings            | `semantic-ir`* | `graph-ir`                        | no            | yes   |
| 06 | Clusters              | `semantic-ir`* | `semantic-ir`, `graph-ir`         | no            | yes   |
| 07 | Summaries             | `semantic-ir`* | `semantic-ir`, `graph-ir`, `markdown-ir` | no       | yes   |
| 08 | Reasoning             | `reasoning-ir` | `semantic-ir`, `graph-ir`         | no            | yes   |
| 09 | Specifications        | `application-ir`* | `reasoning-ir`, `semantic-ir`, `graph-ir` | no    | yes   |
| 10 | Software              | `application-ir` | `application-ir`, `reasoning-ir`, `semantic-ir` | no   | yes   |

\* Passes 05/06/07 all extend `semantic-ir` (embedding table, clusters,
summaries respectively) — they are siblings that enrich the same IR. Passes
09/10 both extend `application-ir` (specification, then full design).

## The pass contract

Every pass — regardless of determinism — obeys the same contract:

**Purpose** — one sentence stating the single conceptual operation.
**Inputs** — the artifact type(s) it reads.
**Outputs** — the artifact type it writes.
**Algorithm** — the steps, stated explicitly so an agent executes the *same*
procedure every time.
**Expected reasoning** — what inference is allowed vs. forbidden.
**Artifacts produced** — JSON/Markdown/YAML/GraphML/Mermaid/etc.
**Failure cases** — what goes wrong and the diagnostic raised.
**Evaluation criteria** — the nine dimensions scored.
**Acceptance tests** — objective pass/fail.
**Example execution** — a concrete run.

The full template lives at `templates/pass-template.md`.

## Diagnostics emitted per phase

| Phase | Diagnostics |
|-------|-------------|
| 01 Parse | `MISSING_EVIDENCE`, `INSUFFICIENT_CITATIONS`, `SPARSE_GRAPH` |
| 02 Extract | low-confidence / unsourced extractions (`HALLUCINATION_SUSPECT`) |
| 03 Ontology | `WEAK_ONTOLOGY`, `DUPLICATE_CONCEPT`, `UNREFERENCED_ENTITY` |
| 04 Graph | `CIRCULAR_REFERENCE`, `SPARSE_GRAPH`, `UNREFERENCED_ENTITY` |
| 05–07 Semantic | `UNREFERENCED_ENTITY`, `HALLUCINATION_SUSPECT` |
| 08 Reasoning | `CONTRADICTORY_STATEMENT`, `MISSING_EVIDENCE`, `HALLUCINATION_SUSPECT` |
| 09–10 Application | `UNREFERENCED_ENTITY`, `HALLUCINATION_SUSPECT` |

### Diagnostic code table

| Code | Meaning | Severity |
|------|---------|----------|
| `MISSING_EVIDENCE` | No citations / no source backs a claim | warning |
| `CIRCULAR_REFERENCE` | Entity/relationship forms a cycle (kept, annotated) | warning |
| `WEAK_ONTOLOGY` | Low relationship-to-concept ratio | warning |
| `DUPLICATE_CONCEPT` | Two concepts denote the same thing | warning |
| `SPARSE_GRAPH` | Average node degree below threshold | warning |
| `UNREFERENCED_ENTITY` | Entity present but never used downstream | warning |
| `CONTRADICTORY_STATEMENT` | Two assertions conflict | warning |
| `INSUFFICIENT_CITATIONS` | Source density below threshold | warning |
| `HALLUCINATION_SUSPECT` | Content not traceable to inputs | warning/error |
| `LOW_CONFIDENCE` | Mean confidence below threshold | info |

Diagnostics are written to `diagnostics.json` alongside each artifact and are
themselves inspectable — exactly like `clang -Weverything` output.

## Planning & execution

Given a target IR, the orchestrator:

1. Finds the pass that produces it.
2. Walks its `consumes` backwards, recursively, collecting the passes needed.
3. Topologically orders them by their `consumes → produces` edges.
4. Executes each: deterministic passes run their `entrypoint` script directly;
   model-required passes are *planned* (the orchestrator records them as
   `skipped` with a reason and leaves them for an agent to fill, so the build
   is honest about what was and wasn't computed).

Running with `--target application-ir` from a fresh source will plan all ten
passes; only `pass-01-parse` executes with no model. That is the correct,
auditable behaviour — the core never fakes an LLM result.
