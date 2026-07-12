# pass-04-graph — Knowledge Graph Construction

**Produces:** `graph-ir` · **Consumes:** `ontology-ir`, `markdown-ir`
**Deterministic:** no · **Model required:** yes

Builds the Knowledge Graph IR from the ontology. Each ontology concept becomes a
**node**; each relationship/hierarchy becomes an **edge** with a `confidence`
and `provenance` (the source spans that justify it). Detects circular
references and a sparse graph (low average degree). Emits GraphML/Mermaid for
visual inspection. Skill: `skills/graph-construction`.
