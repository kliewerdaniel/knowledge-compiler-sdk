# Inputs — Markdown Parsing

Consumes: `(raw Markdown)`.

Read the artifact JSON from `build/<artifact-type>/artifact.json`. Operate on the structured IR — never re-read raw Markdown. Use `metadata.json` (provenance) and `diagnostics.json`.
