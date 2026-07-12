# Purpose — Ontology Building

Cluster extracted entities into canonical concepts, declare typed relationships and hierarchies, and record aliases. Produces the Ontology IR — the typed backbone of the knowledge graph.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
