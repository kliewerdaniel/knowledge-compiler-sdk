# pass-07-summaries — Summary & Theme Generation

**Produces:** `semantic-ir` (summaries portion) · **Consumes:** `semantic-ir`, `graph-ir`, `markdown-ir`
**Deterministic:** no · **Model required:** yes

Writes one grounded summary per theme plus a corpus-level executive summary.
Each summary sentence is linked to the source spans it was drawn from, so the
report pass can render citations. Skill: `skills/report-generation` (shared
summarisation behaviour).
