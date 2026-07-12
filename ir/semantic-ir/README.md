# Semantic IR — Formal Specification

**Artifact type:** `semantic-ir`
**Produced by:** `pass-05-embeddings`, `pass-06-clusters`, `pass-07-summaries`
**Consumed by:** `pass-08-reasoning`, `pass-09-specifications`, `pass-10-software`

## Purpose
The Semantic IR adds *向量* and *thematic* structure on top of the graph: dense
embeddings per node, clusters/themes over those embeddings, and grounded
natural-language summaries. It is where the compiler moves from symbolic
structure to statistical neighbourhoods.

## Containers
* **themes** — clusters of semantically related nodes.
* **embeddings** — vector table keyed by node id.
* **clusters** — cluster membership + labels.
* **summaries** — per-theme and executive prose.

## Field specification
* `embeddings.json` — `{node_id: [float,...]}`, with `metadata.model` and
  `metadata.dim`. Vectors documented as normalised or not.
* `clusters.json` — `{themes:[{id,label,member_node_ids:[],confidence}],
  memberships:[{node_id, theme_id}]}`.
* `summaries.json` — `{theme_summaries:[{theme_id,text,provenance:[]}],
  executive_summary}`.

## Invariants
* Embedding table covers every graph node that has a `label`.
* Each theme has a human-readable label derived from dominant members.
* Theme count bounded 10–40 for typical corpora.

## Diagnostics emitted
`UNREFERENCED_ENTITY` (singleton with no graph edges),
`HALLUCINATION_SUSPECT` (ungrounded summary sentence).
