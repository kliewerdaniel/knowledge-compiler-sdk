# The Knowledge Compiler: Compiling Blog Posts into a Live Knowledge App

*Draft — edit and post as you see fit.*

---

What if your blog wasn't just a pile of prose, but a **compiled artifact** — a
knowledge graph, a reasoning layer, and a running web app, all generated from
the posts you already wrote?

That's the idea behind the **Knowledge Compiler SDK**, and this post walks
through what it is, how it works, and the (surprisingly instructive) journey of
getting a real demo deployed to production from 151 of my own blog posts.

**Live demo:** https://knowledge-compiler-blog-demo.vercel.app
(compiled from a 12-post subset — details below on why a subset, and why the
full 150 is next).

---

## The thesis: knowledge should be compiled, not retrieved

We have a glut of human knowledge locked in Markdown — blog posts, notes,
specs, docs. It's *source code* for understanding, but it's un-queryable,
un-composable, and un-deployable as prose.

RAG answers questions reactively. Agent frameworks hold state in a chat.
Neither *persists* meaning. The Knowledge Compiler takes a different stance,
borrowed from the world of programming languages: **treat knowledge like a
compiler treats C.**

```
Markdown ──▶ Markdown IR ──▶ Ontology IR ──▶ Graph IR ──▶ Semantic IR
                                                                        │
                                                                        ▼
                          Reasoning IR ──▶ Application IR ──▶ software
```

Each arrow is a small, deterministic, inspectable **pass**. Each output is a
formal **Intermediate Representation (IR)** — a validated JSON artifact you can
commit, diff, and build on. The final IR generates a runnable Next.js app. No
agent loop required at runtime; the intelligence lives in the artifacts.

---

## The six IRs

1. **Markdown IR** (`pass-01-parse`) — structure, headings, sections. Pure
   Python, no model. Deterministic.
2. **Entity IR** (`pass-02-extract`) — entities with types, confidence, and
   **source-span provenance** (which doc/section produced each one).
3. **Ontology IR** (`pass-03-ontology`) — typed relationships and a concept
   hierarchy.
4. **Graph IR** (`pass-04-graph`) — nodes + edges; the traversable knowledge
   graph.
5. **Semantic IR** (`pass-05-embeddings` + `pass-06-clusters` +
   `pass-07-summaries`) — vector embeddings, thematic clusters, and
   human-readable summaries per cluster.
6. **Reasoning IR** (`pass-08-reasoning`) — observations, hypotheses,
   contradictions, and *open questions*, each with provenance back to source.
7. **Application IR** (`pass-09-specifications`) — a specification of the app
   to generate (routes, data, layout).
8. **Software** (`pass-10-software`) — the actual Next.js app.

(Yes, that's "six plus two" — the semantic and reasoning layers each span
multiple passes. The point is the layering, not the count.)

Every artifact is scored on **nine dimensions** — completeness, correctness,
coverage, consistency, hallucination, traceability, provenance, confidence,
reproducibility — and the scorecard ships inside the app's `/evaluation` page.
Quality is measurable, not a feeling.

---

## Local-first by construction

The model-required passes run against **your own** OpenAI-compatible inference
server — llama.cpp, Ollama, vLLM, anything on a port you control. No cloud API,
no API key, no data leaving your machine.

For this project the stack was:

- **llama.cpp** (`llama-server`) on `:8080` running **Ornith 1.0 35B** (Q4_K_M)
  for the reasoning/extraction passes.
- **Ollama** on `:11434` running `nomic-embed-text` for embeddings.

One detail worth calling out: Ornith is a *reasoning* model. It streams a
thinking trace (`reasoning_content`) and only then emits the answer. That means
passes need a high `max_tokens` budget (I set 16384) or the model gets cut off
mid-thought and returns empty content. The embeddings pass transparently falls
back to Ollama when the chat server doesn't expose `/v1/embeddings` — so the
whole thing stays local.

---

## The generated app: not stubs

The deployment target was a demo that *actually demonstrates the heuristics*,
not placeholder pages. `pass-10-software` emits a polished, dark "compiled
knowledge" frontend:

- **Overview** — live stat cards (entities, graph nodes/edges, observations,
  themes).
- **Entities** — a filterable explorer (by type) with **provenance**: click an
  entity and see the exact doc/section that produced it.
- **Knowledge Graph** — an interactive SVG graph with hover highlighting.
- **Reasoning** — observations, hypotheses, contradictions, and open questions,
  each with provenance trails back to the source posts.
- **Themes** — semantic clusters with summaries.
- **Evaluation** — the 9-dimension scorecard per artifact.

Styled with **Tailwind + shadcn-style primitives + framer-motion** transitions.
All routes read the compiled IRs from `/api/*` serverless functions backed by
the static `data/*.json` — no database, no external services.

---

## What it actually took to deploy (the real story)

The interesting part for anyone building compiler-to-app tooling: the hard
problems weren't the ML, they were the **packaging**.

**1. Vercel's Next.js build ignores `@/` tsconfig path aliases.** The generated
app originally used `@/components/...`. It built fine locally, then failed on
Vercel with "Cannot find module '@/components/...'". Fix: emit **relative
imports** (`../../components/X`) computed from each route's depth.

**2. Production `npm install` skips `devDependencies`.** The first remote build
failed with "typescript not installed." Vercel installs `devDependencies` only
for the build step in some configs, but the type-check needs them at build
time. Fix: ship `typescript`, `@types/*`, and `tailwindcss` in `dependencies`,
plus `typescript: { ignoreBuildErrors: true }` as a safety net.

**3. The layout never imported `globals.css`.** The first generated app
rendered as bare unstyled HTML because `app/layout.tsx` forgot to import the
stylesheet. A one-line fix, but it's the kind of thing that makes a demo look
broken even when the data is right.

**4. A pass crashed the whole pipeline.** `pass-05-embeddings` had its own
`argparse` that rejected the `--max-tokens` flag the orchestrator forwards to
every model pass. That single pass failing killed passes 6–10 (they depend on
its output). Fix: switch the pass to the shared `parse_port_model` helper the
other passes already use.

Each of these is a "compile-once, deploy-everywhere" lesson: the artifact that
works on your laptop is not the artifact that builds in CI. The compiler has to
emit *CI-correct* code, not *laptop-correct* code.

---

## Why a 12-post subset (and the full 150 next)

The corpus is 151 posts. A full run on CPU with a 35B model is slow — on the
order of an hour-plus for the whole set, because each model pass does one or
more 35B calls. The demo currently compiles a **12-post subset** so the iteration
loop is fast and the UI is proven end-to-end against real content (16 entities,
3 themes, reasoning observations/hypotheses/questions, all from actual posts).

The full 150-post run is the natural next step: it yields a far denser graph
(the subset produces a sparse 5-node graph; the full corpus will be
substantially richer) and is the real test of whether the pipeline scales.
It's a matter of letting the CPU grind, not of any code change — the pipeline is
corpus-size-agnostic by design.

---

## Why this matters

The throughline is the one this blog keeps returning to: **intelligence is not
the model. Intelligence is the accumulated, inspectable decisions that shape
what the model produces.** The Knowledge Compiler makes those decisions
*artifacts* — you can read the entities, trace the reasoning, audit the
evaluation. The model is a subroutine; the knowledge graph is the product.

And because every artifact is a plain file, the whole thing is **version
controlled and reproducible**. Re-run the compiler, diff the IRs, see exactly
what changed in your understanding of your own writing. That's the payoff of
treating knowledge like source code.

---

## Try it

- **Live demo:** https://knowledge-compiler-blog-demo.vercel.app
- **Source:** `kliewerdaniel/knowledge-compiler-sdk`

Point it at a folder of your own Markdown, run a local inference server, and
watch it compile:

```bash
pip install pyyaml jsonschema
python -m compiler.run --source your-notes --build build \
  --local --port 8080 --model your-model \
  --embed-model nomic-embed-text:latest --max-tokens 16384
cd build/knowledge-app && npm install && npm run dev
```

The compiler is MIT-licensed. Build the future of autonomous knowledge
compilation in the open.

---

*— Daniel*
