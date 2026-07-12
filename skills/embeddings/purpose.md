# Purpose — Embedding Generation

Embed graph nodes into a vector space using a LOCAL model (no cloud APIs). Produces the embedding table that powers clustering and semantic search.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
