# Ontology Building — Agent Skill

**Skill id:** `ontology`
**Produces:** `ontology-ir`
**Consumes:** `entity-ir`
**Deterministic:** no (model-required)

Cluster extracted entities into canonical concepts, declare typed relationships and hierarchies, and record aliases. Produces the Ontology IR — the typed backbone of the knowledge graph.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
