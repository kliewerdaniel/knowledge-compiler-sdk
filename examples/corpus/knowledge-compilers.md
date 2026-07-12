# Knowledge Compilers

A knowledge compiler transforms Markdown into progressively higher-level
semantic artifacts, much like LLVM transforms C into machine code.

## 1. Intermediate Representations

Each stage consumes a well-defined artifact and produces another. The Markdown
IR, Ontology IR, and Graph IR precede the Semantic IR.

## 2. Contrast with RAG

Retrieval-augmented generation is reactive: it answers queries without building
a durable model of meaning. A compiler persists meaning as artifacts.

## 3. Diagnostics

Like compiler warnings, each pass emits diagnostics: missing evidence,
circular references, and weak ontologies are surfaced, not hidden.
