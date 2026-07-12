# Intermediate Representations

The Knowledge Compiler transforms knowledge through six progressively more
abstract intermediate representations (IRs). Each IR is a **formal contract**:
a JSON Schema in `schemas/`, a narrative spec in `ir/<name>/README.md`, and a
set of invariants every producer must honour. This document is the index.

The progression is cumulative — higher IRs embed and reference lower ones via
provenance, never by re-deriving from raw text.

```
Markdown IR ──▶ Ontology IR ──▶ Graph IR ──▶ Semantic IR ──▶ Reasoning IR ──▶ Application IR
   (parse)       (typed)         (linked)     (vectors)       (judgments)      (software)
```

## 1. Markdown IR — `ir/markdown-ir`

The lossless structural parse. No inference.

- **documents** — one record per source file (`id`, `title`, `path`, `preamble`,
  `sections[]`, `section_count`, `word_count`).
- **metadata** — corpus aggregates (document count, total words, sections,
  citations, cross-document links).
- **citations** — every inline link/reference, with `doc`, `text`, `target`.
- **document graph** — `nodes[]` + `edges[]` of cross-file references.

Provenance anchor: every later span names `doc` + `section` + character range.
Schema: `schemas/markdown-ir.json`.

## 2. Ontology IR — `ir/ontology-ir`

The typed backbone: meaning structure.

- **concepts** — canonical ideas; each lists `member_entity_ids` tying back to
  the entity pool (and thus to source spans).
- **relationships** — typed edges (`implements`, `depends-on`, `specializes`,
  `contradicts`, `enables`, `references`, `part-of`) with `confidence`.
- **hierarchies** — `is-a` / `part-of` trees.
- **aliases** — surface forms mapped to a concept (never dropped).

Invariants: every concept has ≥1 member; vague `related-to` → `WEAK_ONTOLOGY`;
>60% member overlap → `DUPLICATE_CONCEPT`. Schema: `schemas/ontology-ir.json`.

## 3. Graph IR — `ir/graph-ir`

The knowledge graph: the most-consumed artifact.

- **nodes** — `{id, label, kind, concept_ref}`; `concept_ref` links to an
  Ontology IR concept.
- **edges** — `{id, source, target, type, confidence, provenance, cycle?}`.
- **confidence** — per-edge belief in `[0,1]`.
- **provenance** — source spans justifying each edge.

Derived views written for humans: `graph.graphml` (Gephi/yEd) and `graph.mmd`
(Mermaid). Invariants: edge endpoints reference existing nodes; mean degree
<1.5 → `SPARSE_GRAPH`; cycles annotated `cycle:true` + `CIRCULAR_REFERENCE`.
Schema: `schemas/graph-ir.json`.

## 4. Semantic IR — `ir/semantic-ir`

Vectors + themes on top of the graph.

- **themes** — clusters of semantically related nodes.
- **embeddings** — `{node_id: [float,...]}`, with `metadata.model` + `dim`
  (local model only, per project principles).
- **clusters** — `{themes:[{id,label,member_node_ids,confidence}],
  memberships:[]}`.
- **summaries** — per-theme and executive prose, each sentence linked to a
  provenance span.

Invariants: embedding table covers every labelled node; themes labelled from
dominant members; singleton-with-no-edges → `UNREFERENCED_ENTITY`. Schemas:
`semantic-ir.json` (structural) + `embeddings.json`/`clusters.json` as
sub-artifacts.

## 5. Reasoning IR — `ir/reasoning-ir`

The analytical layer: judgments about the knowledge.

- **observations** — evidenced statements (`id, text, provenance, confidence`).
- **hypotheses** — plausible inferences, each tied to `basis:[observation_id]`.
- **contradictions** — `{id, a_claim, b_claim, explanation, confidence}`.
- **unanswered questions** — `{id, text, theme, why_unanswered}`.
- **confidence** — per-item belief.

Invariants: a contradiction needs two evidenced claims; a question with no
claim → `MISSING_EVIDENCE`; hypotheses never asserted as fact. Schema:
`schemas/reasoning-ir.json`.

## 6. Application IR — `ir/application-ir`

The highest IR: a deployable software design compiled from knowledge.

- **architecture** — `{layers:[], rationale}` (presentation/domain/data/infra).
- **pages** — `{id, title, route, components:[], theme_ref}`.
- **components** — `{id, name, props:[], responsibility}`.
- **routes** — `{path, page_id, method}`.
- **apis** — `{path, method, purpose, request, response}`.
- **deployment plan** — `{target, steps:[], prerequisites:[]}`.

Invariants: each page → a theme; each component → a requirement; `data_model`
stays consistent with `graph-ir`; compiler *plans* deployment, never executes
it. Schema: `schemas/application-ir.json`.

## Why IRs enable better reasoning

1. **Bounded context.** An agent operating on the Graph IR sees the whole
   corpus's structure in one file, not 200 pages of prose.
2. **Compositional.** Each IR is a stable API; a new pass consumes the IR, not
   the prompt that produced it.
3. **Auditable.** Every claim in a high IR is traceable down the chain to a
   source span — hallucination becomes detectable, not hidden.
4. **Cacheable.** Re-running pass 08 doesn't require re-parsing; the Graph IR is
   a durable input.
5. **Replaceable.** Swap the embedding model? Only `pass-05` changes; the Graph
   IR contract is unchanged. This is the LLVM "mid-level IR" advantage applied to
   knowledge.
