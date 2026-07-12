# Markdown IR — Formal Specification

**Artifact type:** `markdown-ir`
**Produced by:** `pass-01-parse` (deterministic)
**Consumed by:** `pass-02-extract`, `pass-04-graph`, `pass-07-summaries`

## Purpose
The Markdown IR is the *lowest* intermediate representation: a lossless,
structured parse of the human-authored source. It deliberately carries no
inference — only syntax, structure, and explicit references. Every later pass
anchors its provenance here.

## Containers
* **documents** — one record per source Markdown file.
* **metadata** — corpus-level aggregates.
* **citations** — every explicit link/reference found inline.
* **document graph** — which documents reference which others.

## Field specification

### documents[]
| field          | type     | meaning                                            |
|----------------|----------|----------------------------------------------------|
| `id`           | string   | stable `doc-N` identifier                          |
| `title`        | string   | H1 or first heading / filename fallback            |
| `path`         | string   | source filename                                    |
| `preamble`     | string   | text before the first heading                      |
| `sections[]`   | object   | `{id, level, number, title, blocks[]}`             |
| `section_count`| integer  | count of sections                                  |
| `word_count`   | integer  | total words                                        |

### citations[]
`{doc, text, target}` — `target` is the raw link destination (URL or doc path).

### document_graph
`{nodes:[{id,label,path}], edges:[{from,to,kind}]}` — `kind` is usually
`references`.

## Provenance rule
The `id` of every section is `sec-<docIdx>-<secIdx>` so any downstream span can
name it exactly. A span is `{doc, section, start, end}` in character offsets.

## Diagnostics emitted
`MISSING_EVIDENCE` (no documents), `INSUFFICIENT_CITATIONS` (no links),
`SPARSE_GRAPH` (no cross-document edges when >1 doc).

## Serialisation
Always emitted as `artifact.json` (pretty JSON) plus `metadata.json` and
`diagnostics.json`. The canonical schema is `schemas/markdown-ir.json`.
