# Embedding Generation — Agent Skill

**Skill id:** `embeddings`
**Produces:** `semantic-ir (embeddings)`
**Consumes:** `graph-ir`
**Deterministic:** no (model-required)

Embed graph nodes into a vector space using a LOCAL model (no cloud APIs). Produces the embedding table that powers clustering and semantic search.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
