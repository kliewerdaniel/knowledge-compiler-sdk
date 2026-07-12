# Semantic Clustering — Agent Skill

**Skill id:** `clustering`
**Produces:** `semantic-ir (clusters)`
**Consumes:** `semantic-ir, graph-ir`
**Deterministic:** no (model-required)

Cluster embedded nodes into labelled themes. Each labelled cluster seeds a later section, page, or component.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
