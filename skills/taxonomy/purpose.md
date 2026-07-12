# Purpose — Taxonomy Construction

Refine the ontology into a navigable taxonomy: layered is-a/part-of trees and canonical alias resolution. Makes the concept space browsable and disambiguated.

## Behaviour
1. Read the declared input artifact(s) from the build directory.
2. Perform exactly one conceptual operation.
3. Write the declared output artifact, validated against its schema.
4. Emit diagnostics for quality issues.
5. Emit an evaluation scorecard.
