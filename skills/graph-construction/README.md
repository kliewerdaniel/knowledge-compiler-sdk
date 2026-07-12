# Knowledge Graph Construction — Agent Skill

**Skill id:** `graph-construction`
**Produces:** `graph-ir`
**Consumes:** `ontology-ir, markdown-ir`
**Deterministic:** no (model-required)

Materialise the ontology into a Knowledge Graph IR: nodes, typed edges, per-edge confidence, and full provenance. The most-consumed artifact in the pipeline.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
