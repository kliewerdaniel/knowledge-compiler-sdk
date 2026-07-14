# Knowledge Compiler SDK

> Compile collections of human knowledge into progressively higher-level
> semantic artifacts — until they generate deployable software.

[![Live Demo](https://img.shields.io/badge/live%20demo-knowledge--compiler--blog--demo.vercel.app-blue?style=flat)](https://knowledge-compiler-blog-demo.vercel.app)

**▶ Live demo (compiled from 151 real blog posts):**
https://knowledge-compiler-blog-demo.vercel.app

**Links**
- Live demo: https://knowledge-compiler-blog-demo.vercel.app/
- Blog post: https://www.danielkliewer.com/blog/2026-07-14-recursive-research-compiler-knowledge-compiler-sdk
- NotebookLM: https://notebooklm.google.com/notebook/57b09d32-2e14-4dd3-83a6-204cbc461d4b

The deployed demo compiles the full 151-post corpus: **293 entities**, 209
graph nodes, **263 typed edges** across a 10-type relationship vocabulary
(depends-on, enables, implements, refutes, supports, extends, is-part-of,
compares-to, exemplifies, mentions — classified by the model from
corpus co-occurrence), 8 thematic clusters, and a reasoning layer
(observations, hypotheses, contradictions, open questions) — all served from
the generated app's `/api/*` routes.

This is **not** an AI agent framework. **Not** a RAG framework. **Not** a prompt
collection. It is **compiler infrastructure for knowledge**, in the spirit of
LLVM and GCC — except it compiles Markdown into knowledge instead of C into
machine code.

```
Markdown ──▶ Markdown IR ──▶ Ontology IR ──▶ Graph IR ──▶ Semantic IR
                                                                        │
                                                                        ▼
                                          Reasoning IR ──▶ Application IR ──▶ software
```

## Why

Human knowledge authored as Markdown is source code: un-queryable, un-composable,
and un-deployable as prose. A compiler turns source into progressively more
abstract, more useful representations. The Knowledge Compiler does that for
knowledge — through six formal **Intermediate Representations (IRs)**, each a
validated, inspectable artifact.

Unlike RAG (reactive retrieval) or agent frameworks (stateful conversation), the
Knowledge Compiler **persists** meaning: a Knowledge Graph built once is a
first-class artifact any agent or program can traverse, visualise, and compile
further. Reasoning is never hidden in a chat — it is emitted as files.

## Principles

- **Small deterministic passes** — one conceptual operation each; `pass-01-parse`
  is pure Python, no model.
- **Immutable artifacts** — written once, never mutated; lineage via `metadata.json`.
- **Composable stages** — passes wired by *what they consume/produce* (YAML),
  not hardcoded call order.
- **Transparent outputs** — JSON, Markdown, YAML, GraphML, Mermaid, PlantUML,
  SVG, HTML, TypeScript, JSON Schemas. Always inspectable.
- **Static, version-controlled, reproducible** — the whole build dir is plain
  files you can commit and diff.

## What's in the box

| Path | What |
|------|------|
| `compiler/core/` | The engine: pass registry, orchestrator, artifact store, diagnostics, evaluation. Stdlib + `pyyaml` only. |
| `compiler/passes/` | 10 declarative passes (`pass-01-parse` … `pass-10-software`), each `pass.yaml` + entrypoint/prompt. |
| `compiler/run.py` | The `knowledgec` CLI driver. |
| `ir/` | Formal specs for the 6 IRs. |
| `schemas/` | JSON Schemas for every artifact. |
| `skills/` | 17 reusable agent skills (11 files each) for Hermes, Claude Code, OpenCode, Codex, … |
| `docs/` | Architecture, phases, IRs, artifacts, evaluation, deployment. |
| `examples/` | A runnable worked example. |
| `tests/` | Pytest suite for the core + passes. |

## Quick start

```bash
# 1. install the only runtime deps of the core
pip install pyyaml jsonschema

# 2. compile a folder of Markdown into the Markdown IR (deterministic, no model)
python -m compiler.run --source path/to/notes --build build

# 3. plan the full pipeline to a deployable Application IR
python -m compiler.run --source path/to/notes --build build --target application-ir

# 4. inspect what was produced
cat build/markdown-ir/artifact.json
cat build/markdown-ir/diagnostics.json
cat build/markdown-ir/evaluation.json
cat build/plan.json
```

`pass-01-parse` runs for real. The model-required passes (02–10) are
*planned* and recorded as `skipped` with a reason — the build is honest about
what was and wasn't computed. An autonomous agent loads the matching
`skills/<name>` to fill each one in.

## Local inference (bring your own model)

The model-required passes run against **your own** OpenAI-compatible inference
server — llama.cpp, Ollama, vLLM, LM Studio, text-generation-webui — on a port
you control. No cloud API, no API key, no data leaving your machine.

```bash
# llama.cpp (default port 8080), Ollama (port 11434), or any /v1 server
python -m compiler.run --source notes --build build --local --port 8080 --model llama3.1
```

Flags:

| Flag            | Default (env)        | Meaning                                                   |
|-----------------|----------------------|-----------------------------------------------------------|
| `--local`       | —                    | Execute model passes via local inference.                 |
| `--port`        | `8080` (`KC_PORT`)   | Port of the `/v1` inference server.                        |
| `--model`       | `KC_MODEL`           | Model name to request from the server.                    |
| `--embed-model` | `KC_EMBED_MODEL`     | Ollama embedding model for the fallback path.            |
| `--incremental` | —                    | Skip passes whose inputs are unchanged (hash caching).   |
| `--only`        | —                    | Run a single pass by id (e.g. `pass-04-graph`).          |
| `--resume`      | —                    | Like `--incremental`, but always rebuilds the target.     |

**Embeddings & the Ollama fallback.** The embedding pass (`pass-05`) needs
vector embeddings. Many chat servers — including a llama.cpp instance started
*without* `--embeddings` — do not expose `/v1/embeddings`. In that case the
compiler transparently falls back to **Ollama** via its native
`/api/embeddings` endpoint (e.g. `nomic-embed-text`). Everything stays local:
no cloud, no key. Point it at your setup with
`--embed-model nomic-embed-text:latest`.

The client (`compiler/core/inference.py`) speaks the OpenAI Chat Completions
protocol and asks for JSON; the model only ever sees **structured artifacts**,
never raw Markdown, so intelligence stays in the artifacts. If the server is
down, model passes report `failed` (not silently `skipped`) — the build stays
truthful. CI installs `openai` only when the `--local` path is exercised.

### End-to-end local run

With a server listening (e.g. `llama.cpp` on :8080), the whole pipeline runs:

```bash
# start your server, then:
python -m compiler.run --source notes --build build --local --port 8080 --model llama3.1
```

Model passes are **resilient**: if the local model returns malformed or
non-JSON output (common with local models), the scaffold retries up to 3 times
with exponential backoff and an explicit "respond with only valid JSON" reminder
before giving up. A pass that never produces valid JSON *fails loudly* (exit 1,
no artifact written) rather than silently skipping — the build stays truthful.
If the server is down, model passes report `failed` (not silently `skipped`).

The deterministic parse runs first; each model pass calls your server, validates
the JSON against its schema, enforces internal reference consistency (dropping
dangling graph edges, flagging weak ontologies, annotating cycles), and writes
the artifact. The final pass (`pass-10-software`) turns the `application-ir`
into a **runnable Next.js application** under `build/knowledge-app/`:

- `data/*.json` — the compiled IRs, copied in so the app is self-contained
- `knowledge-app/app/api/*/route.ts` — real route handlers that read `data/` and return
  the artifacts as JSON (no external services needed)
- `knowledge-app/components/` — a polished, heuristic-driven UI: `Sidebar`,
  `EntityExplorer` (entities + source-span provenance + linked claims),
  `GraphCanvas` (interactive SVG knowledge graph), `ReasoningPanel`
  (observations / hypotheses / contradictions / open questions with provenance),
  `ThemeClusters` (semantic clusters + summaries), `EvaluationDashboard`
  (9-dimension scorecard), `StatCard`. Styled with Tailwind + shadcn-style
  primitives + `framer-motion` transitions, dark "compiled knowledge" theme.
- `knowledge-app/app/{overview,entities,graph,reasoning,themes,evaluation}/page.tsx`
  — six routes, each a real view of the compiled IRs (no stub pages)
- `package.json`, `next.config.mjs`, `tsconfig.json`, `tailwind.config.ts`,
  `postcss.config.js`, `globals.css`, `vercel.json`, `README.md`

The generated app uses **relative imports only** (Vercel's Next build does not
honor `@/` tsconfig aliases) and ships `typescript`/`@types/*`/`tailwindcss` in
`dependencies` so a production `npm install` includes them — both are required
for a clean `vercel --prod` build.

Run it locally with `cd build/knowledge-app && npm install && npm run dev`
(open http://localhost:3000; the evaluation dashboard is at `/evaluation`).
Incremental mode reuses any artifact whose inputs are unchanged, so re-runs
are cheap.

### Deploy to Vercel

The generated app is a standard Next.js project, so it deploys to Vercel as-is:

```bash
cd build/knowledge-app
vercel              # preview
vercel --prod       # production
```

A running example compiled from the full 151-post corpus is live at
**https://knowledge-compiler-blog-demo.vercel.app** (all six routes return 200
and serve the compiled IRs via `/api/*` — 293 entities, 209 graph nodes with
263 typed edges, 8 themes, and a reasoning layer).

`vercel.json` is emitted alongside the app (framework `nextjs`, build
`npm install && npm run build`, output `.next`). The `/api/*` routes become
serverless functions and read the compiled IRs from `data/` — no database, no
external services. The whole thing is static-data + serverless, fully
local-first in spirit.

## The pass registry (the extensibility model)

Passes are **declared declaratively** in YAML — not hardcoded. The orchestrator
*discovers* them, resolves dependencies between artifact types, plans a path
from source to any target IR, and executes only the passes whose inputs are
satisfied. Adding a pass is dropping a directory; it changes nothing in the
core. This is the build-system property that makes the compiler extensible.

```yaml
# compiler/passes/pass-01-parse/pass.yaml
id: pass-01-parse
name: Markdown Parsing
produces: markdown-ir
consumes: []
entrypoint: run.py
deterministic: true
model_required: false
description: Parse raw Markdown into a Markdown IR.
```

## Agent skills

Seventeen reusable skills live under `skills/`. Each has the same 11-file shape
(`README.md`, `purpose.md`, `inputs.md`, `outputs.md`, `artifact-schema.json`,
`acceptance-tests.md`, `evaluation.md`, `failure-modes.md`, `examples.md`,
`prompt.md`, `checklist.md`) and describes **how the pass behaves** — not just a
prompt. An agent loads a skill, reads the declared input artifact (structured
JSON), performs the one operation, and writes the declared output artifact.

## Evaluation

Every artifact is scored on nine dimensions — completeness, correctness,
coverage, consistency, hallucination, traceability, provenance, confidence,
reproducibility — and the scorecard is committed as `evaluation.json`. Quality
becomes measurable and trendable, not a feeling.

After every build, the compiler emits a **self-contained evaluation dashboard**
(`evaluation_dashboard.html`) that visualizes those 9-dimension scores for every
artifact. It is a single static file with the data embedded inline and
hand-rolled SVG/CSS — no CDN, no build step, no runtime services — so it opens
straight from disk (`file://…/evaluation_dashboard.html`). Artifacts are sorted
weakest-first so the lowest-scoring IR surfaces at the top, and each card shows
a per-dimension bar (green ≥ 75, amber ≥ 50, red < 50) plus the overall score.
This is the *observability is the OS* payoff: the loop inspects itself.

## Documentation

- `docs/architecture.md` — why knowledge should be compiled like C.
- `docs/compiler-phases.md` — the ten passes + diagnostics.
- `docs/intermediate-representations.md` — the six IRs.
- `docs/artifact-specifications.md` — the on-disk artifact contract.
- `docs/evaluation.md` — the nine-dimension scorecard.
- `docs/deployment.md` — how artifacts become software.

## License

MIT — build the future of autonomous knowledge compilation in the open.
