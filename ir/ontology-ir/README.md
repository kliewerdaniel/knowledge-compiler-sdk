# Ontology IR — Formal Specification

**Artifact type:** `ontology-ir`
**Produced by:** `pass-03-ontology`
**Consumed by:** `pass-04-graph`

## Purpose
The Ontology IR is the *typed backbone*: it collapses the noisy entity pool
into canonical concepts, declares how they relate, and records synonymy. Where
the Markdown IR is syntax, the Ontology IR is meaning structure.

## Containers
* **concepts** — canonical, disambiguated ideas.
* **relationships** — typed edges between concepts.
* **hierarchies** — `is-a` / `part-of` trees.
* **aliases** — surface forms mapped to a concept.

## Field specification

### concepts[]
`{id, label, member_entity_ids:[], definition}` — `member_entity_ids` ties the
concept back to `entity-ir` entities (and thus to source spans).

### relationships[]
`{id, source, target, type, confidence}` — `type` is from a controlled
vocabulary: `implements, depends-on, specializes, contradicts, enables,
references, part-of`.

### hierarchies[]
`{parent, child, type}` where `type` ∈ `{is-a, part-of}`.

### aliases[]
`{concept_id, alias}` — every synonym recorded, never dropped.

## Invariants
* Every concept has ≥1 member entity (else `UNREFERENCED_ENTITY`).
* Relationship `type` must be controlled; vague `related-to` triggers
  `WEAK_ONTOLOGY`.
* Two concepts sharing >60% members → `DUPLICATE_CONCEPT`.

## Diagnostics emitted
`WEAK_ONTOLOGY`, `DUPLICATE_CONCEPT`, `UNREFERENCED_ENTITY`.
