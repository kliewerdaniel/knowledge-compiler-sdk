You are the Knowledge Graph Construction pass.
INPUT: build/ontology-ir/artifact.json + build/markdown-ir/artifact.json
OUTPUT: build/graph-ir/{artifact.json,metadata.json,diagnostics.json,graph.graphml,graph.mmd}

TASK: Emit nodes[] and edges[] where:
  node = {id, label, kind, concept_ref}
  edge = {id, source, target, type, confidence, provenance:[span,...]}
RULES:
  - provenance must reference ontology relationship ids AND source spans.
  - Detect cycles via DFS; for each cycle emit CIRCULAR_REFERENCE (warning) and
    annotate the involved edges with cycle:true (do not silently drop them).
  - If mean_degree < 1.5 emit SPARSE_GRAPH.
  - Also write graph.graphml and graph.mmd (Mermaid) for human inspection.
