# Architecture

> Why knowledge should be compiled like C, and how this repository is built to
> do it.

## 1. The central claim

Human knowledge authored as Markdown (notes, specs, research, docs) is **source
code**. Left as prose it is un-queryable, un-composable, and un-deployable. A
*compiler* turns source into progressively more abstract, more useful
representations — and that is exactly what we want from a body of knowledge.

This repository is **not** an AI agent framework, **not** a RAG framework, and
**not** a prompt library. It is *compiler infrastructure* for knowledge. The
analogy to LLVM/GCC is deliberate and structural, not metaphorical:

| Compiler concept      | Knowledge Compiler equivalent                         |
|-----------------------|-------------------------------------------------------|
| source `.c` file      | a folder of Markdown                                   |
| lexer / parser        | `pass-01-parse` → Markdown IR                         |
| AST                   | Ontology IR + Graph IR                                |
| SSA / optimisations   | Semantic IR (embeddings, clusters, summaries)         |
| analysis passes       | Reasoning IR (contradictions, gaps, hypotheses)       |
| code generation       | Application IR (spec → architecture → code)           |
| object file / binary  | deployable software (e.g. a Next.js app)              |
| warnings              | compiler diagnostics                                  |
| optimisation reports  | evaluation scorecards                                 |
| pass manager          | the orchestrator + declarative pass registry          |

## 2. Design principles

These are load-bearing. They are what separate a *compiler* from a *pipeline of
prompts*.

### Small deterministic passes
Each pass performs exactly one conceptual operation and is, where possible,
deterministic (no LLM). `pass-01-parse` is pure Python + regex; it never calls a
model. Determinism means reproducibility: the same source always yields the same
Markdown IR.

### Immutable artifacts
Artifacts are written once and never mutated in place. A later stage that
revises a representation writes a *new* artifact type, preserving lineage via
`metadata.json`. This is the IR-equivalent of "don't edit the object file by
hand."

### Composable stages
Passes are wired by *what they consume and produce*, declared in YAML — never by
hardcoded call order. The orchestrator discovers passes and resolves a path from
source to any target IR. Adding a pass is dropping a directory; it changes
nothing in the core.

### Transparent outputs
Every stage emits files: JSON, Markdown, YAML, GraphML, Mermaid, PlantUML, SVG,
HTML, TypeScript interfaces, JSON Schemas. Reasoning is **never** hidden inside a
conversation. If an agent reasoned about something, the result is an artifact
someone can open and audit.

### Static, version-controlled, reproducible
The entire build directory is plain static files. Commit it. Diff it. Re-run it.
No stateful conversation is required to understand or reproduce a result.

## 3. Repository layout

```
knowledge-compiler-sdk/
  compiler/
    core/            # the engine: registry, orchestrator, artifacts, diagnostics, evaluation
    passes/          # pass-01..pass-10, each a declarative YAML + entrypoint + prompt
    run.py           # the `knowledgec` CLI driver
  ir/                # formal specs for the 6 intermediate representations
  schemas/           # JSON Schemas for every artifact
  skills/            # 17 reusable agent skills (11 files each)
  docs/              # this architecture doc + phases, IRs, artifacts, evaluation, deployment
  examples/          # a runnable worked example (corpus + build artifacts)
  templates/         # starter templates for new passes/skills
  tests/             # pytest suite for the core + passes
  scripts/           # helper scripts (validate, render, diff)
  .github/           # CI that runs the test suite
```

## 4. The runtime model

The core (`compiler/core`) is **standard-library only** plus `pyyaml` and
(optionally) `jsonschema`. That is intentional: autonomous agents run inside
minimal sandboxes, and the dependency floor must be as low as the task allows.
The *intelligence* — the model-required passes — lives in the **skills**, which
agents load on demand, and executes against **your own** inference server.

**Local-first inference.** Model passes talk to an OpenAI-compatible server
(llama.cpp / Ollama / vLLM / LM Studio) on a port you control via
`--local --port 8080 --model <name>` — no cloud API, no key, no data leaving
the machine. The client (`compiler/core/inference.py`) asks for JSON and the
model only ever sees structured artifacts, never raw Markdown. Without
`--local`, model passes are planned and reported as `skipped`; with a dead
server they report `failed` — the build never fakes an LLM result.

A run looks like this:

```
source/*.md  --[pass-01-parse]--> markdown-ir
markdown-ir  --[pass-02-extract]--> entity-ir
entity-ir    --[pass-03-ontology]--> ontology-ir
ontology-ir  --[pass-04-graph]----> graph-ir
graph-ir     --[pass-05/06/07]----> semantic-ir
semantic-ir  --[pass-08-reasoning]-> reasoning-ir
...          --[pass-09/10]-------> application-ir
```

The orchestrator computes *which* of these to run to reach a target, executes
the deterministic ones directly, and (with `--local`) runs the model ones
against your server. See `docs/compiler-phases.md`.

## 5. Why not RAG?

RAG retrieves chunks to answer a query. It is *stateless with respect to
meaning*: it never builds a durable, queryable model of the knowledge, never
detects contradictions across the corpus, never generates software from it. The
Knowledge Compiler **persists** intermediate representations. The Graph IR, once
built, is a first-class artifact an agent (or a program) can traverse, visualise,
and compile further. Semantic compilation is *constructive*; RAG is *reactive*.

## 6. How autonomous agents consume compiler artifacts

An agent does not "chat with the knowledge." It:

1. Loads the relevant skill (`skills/<name>`).
2. Reads the declared input artifact (structured JSON, not prose).
3. Performs the one operation the skill describes.
4. Writes the declared output artifact + diagnostics + evaluation.

Because artifacts are structured and schema-validated, agents interoperate
without a shared prompt — they share **contracts**. This is why the repository
scales across Hermes, Claude Code, OpenCode, Codex, etc.: the artifacts are the
API.

## 7. Extending the compiler

To add a pass:

1. `mkdir compiler/passes/pass-11-<name>`.
2. Write `pass.yaml` (id, produces, consumes, entrypoint, deterministic,
   model_required).
3. Add a JSON Schema under `schemas/`.
4. Write `run.py` (deterministic) or a `prompt.md` + skill (model-required).

The orchestrator picks it up on the next discovery. No core change. This is the
build-system property the project was designed for.
