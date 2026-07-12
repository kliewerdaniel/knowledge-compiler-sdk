# Graph IR — Formal Specification

**Artifact type:** `graph-ir`
**Produced by:** `pass-04-graph`
**Consumed by:** `pass-05-embeddings`, `pass-06-clusters`, `pass-07-summaries`,
`pass-08-reasoning`, `pass-09-specifications`, `pass-10-software`

## Purpose
The Knowledge Graph IR materialises the ontology into an inspectable graph:
nodes, typed edges, per-edge confidence, and full provenance. It is the most
frequently consumed artifact in the pipeline.

## Containers
* **nodes** — graph vertices.
* **edges** — typed, weighted, provenance-bearing links.
* **confidence** — per-edge belief score in `[0,1]`.
* **provenance** — source spans justifying each edge.

## Field specification

### nodes[]
`{id, label, kind, concept_ref}` — `concept_ref` links to an `ontology-ir`
concept id.

### edges[]
`{id, source, target, type, confidence, provenance:[span], cycle?:bool}`

## Views (derived, also written for humans)
* `graph.graphml` — GraphML for yEd/Gephi.
* `graph.mmd` — Mermaid for inline rendering.

## Invariants
* Every edge `source`/`target` must reference an existing node.
* Mean degree < 1.5 → `SPARSE_GRAPH`.
* Any cycle detected via DFS is annotated `cycle:true` and reported as
  `CIRCULAR_REFERENCE` (warning, not error).

## Diagnostics emitted
`CIRCULAR_REFERENCE`, `SPARSE_GRAPH`, `UNREFERENCED_ENTITY`.
