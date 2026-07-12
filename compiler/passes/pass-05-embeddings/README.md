# pass-05-embeddings — Embedding Generation

**Produces:** `semantic-ir` (embedding table portion) · **Consumes:** `graph-ir`
**Deterministic:** no (depends on model) · **Model required:** yes

Generates dense vectors for each graph node (and optionally each edge) and
stores them in the Semantic IR. This pass is intentionally backend-agnostic:
the agent selects a *local* embedding model (no cloud APIs, per project
principles) and records which one in `metadata.model`. Skill: `skills/embeddings`.
