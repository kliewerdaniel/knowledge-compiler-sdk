# Entity Extraction — Agent Skill

**Skill id:** `entity-extraction`
**Produces:** `entity-ir`
**Consumes:** `markdown-ir`
**Deterministic:** no (model-required)

Surface entities, domain terms, and atomic claims from the Markdown IR. Every extraction carries a source span so all downstream artifacts stay traceable.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
