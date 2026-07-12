# Purpose — Entity Extraction

Surface entities, domain terms, and atomic claims from the Markdown IR. Every extraction carries a source span so all downstream artifacts stay traceable.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
