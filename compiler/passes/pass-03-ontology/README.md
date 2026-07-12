# pass-03-ontology — Ontology Building

**Produces:** `ontology-ir`
**Consumes:** `entity-ir`
**Deterministic:** no · **Model required:** yes

## What this pass does

Consumes the entity pool and produces a typed concept lattice:
- **concepts** — clusters of synonymous entities, each with a canonical label.
- **relationships** — typed edges between concepts (e.g. `implements`,
  `depends-on`, `contradicts`, `specializes`).
- **hierarchies** — `is-a` / `part-of` trees.
- **aliases** — surface forms mapping onto a concept.

A *weak ontology* diagnostic fires when the relationship-to-concept ratio is
low, signalling the agent should infer more structure before graph construction.

The reusable agent skill lives at `skills/ontology`.
