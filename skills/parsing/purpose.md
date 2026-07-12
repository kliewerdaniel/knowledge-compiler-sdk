# Purpose — Markdown Parsing

Deterministically transform raw Markdown source into a Markdown IR: documents, section hierarchy, inline citations, and a document graph. No inference; pure syntax + structure.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
