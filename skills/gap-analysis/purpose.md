# Purpose — Missing Information Detection

Detect claims/themes that reference evidence not present in the corpus, and surface unanswered questions worth resolving.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
