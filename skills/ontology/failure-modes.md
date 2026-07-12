# Failure Modes — Ontology Building

- **Empty input** → MISSING_EVIDENCE; abort gracefully.
- **Unsourced output** → HALLUCINATION_SUSPECT; drop or cite.
- **Schema invalid** → ERROR; do not write partial artifact.
- **Weak structure** → WEAK_ONTOLOGY / SPARSE_GRAPH as relevant.
- **Model drift** → pin model; record in metadata.
