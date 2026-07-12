You are the Embedding Generation pass.
INPUT: build/graph-ir/artifact.json
OUTPUT: build/semantic-ir/embeddings.json (+ metadata noting the model used)

TASK: For every node id in graph-ir, produce a vector (length L). Write a JSON
map {node_id: [floats...]}. Record model name + dim in metadata.
RULES:
  - Prefer a LOCAL embedding model (sentence-transformers, all-MiniLM, etc.).
    Do not call cloud APIs.
  - Only embed nodes that carry a `label`; skip empty nodes and emit
    UNREFERENCED_ENTITY for them.
  - Vectors must be normalised or flagged; document the convention in metadata.
