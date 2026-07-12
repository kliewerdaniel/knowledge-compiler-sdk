# Prompt — Embedding Generation

You are the Embedding Generation skill. INPUT: build/graph-ir/artifact.json. OUTPUT: build/semantic-ir/embeddings.json + metadata.
For every node with a label, produce a vector. Record model name + dim in metadata. Prefer a local model (all-MiniLM etc.). Skip empty nodes -> UNREFERENCED_ENTITY. Document normalisation convention.
