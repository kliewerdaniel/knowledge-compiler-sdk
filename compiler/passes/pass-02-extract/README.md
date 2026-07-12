# pass-02-extract — Entity Extraction

**Produces:** `entity-ir`
**Consumes:** `markdown-ir`
**Deterministic:** no · **Model required:** yes

## What this pass does

Walks the `documents` of the Markdown IR and extracts:
- **entities** — named things (people, systems, concepts, libraries) with a
  proposed `type` and the `span` (document id + section id + character range)
  they were drawn from.
- **terms** — domain vocabulary that may not be named entities but is
  conceptually load-bearing.
- **claims** — atomic assertions made in the text, each linked to the span that
  supports it.

The output is the *raw material* for the ontology pass. This pass intentionally
does **not** decide how entities relate — it only surfaces them and their
provenance. Relationship inference belongs to `pass-03-ontology`.

## Execution model

This is a model-required pass. The orchestrator does not ship a hardcoded
implementation; instead an autonomous agent loads `skills/entity-extraction`
and `skills/entity-extraction/prompt.md`, reads `markdown-ir/artifact.json`,
and writes `entity-ir/artifact.json` plus diagnostics. The skill defines *how*
the extraction behaves; the prompt is small and consumes the structured IR.

See `skills/entity-extraction/` for the reusable agent skill.
