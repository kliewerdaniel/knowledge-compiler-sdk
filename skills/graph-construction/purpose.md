# Purpose — Knowledge Graph Construction

Materialise the ontology into a Knowledge Graph IR: nodes, typed edges, per-edge confidence, and full provenance. The most-consumed artifact in the pipeline.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
