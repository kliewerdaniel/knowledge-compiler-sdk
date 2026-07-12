# Failure Modes — Embedding Generation

- **Empty input** → MISSING_EVIDENCE.
- **Unsourced output** → HALLUCINATION_SUSPECT.
- **Schema invalid** → ERROR.
- **Weak structure** → WEAK_ONTOLOGY / SPARSE_GRAPH.
- **Model drift** → pin model.
