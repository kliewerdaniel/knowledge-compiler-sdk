# pass-08-reasoning — Reasoning & Analysis

**Produces:** `reasoning-ir` · **Consumes:** `semantic-ir`, `graph-ir`
**Deterministic:** no · **Model required:** yes

The analytical heart of the compiler. Combines three sub-analyses (each also a
standalone reusable skill):
- **contradiction-analysis** — pairs of claims that conflict (`skills/contradiction-analysis`)
- **gap-analysis** — claims/themes that reference missing evidence (`skills/gap-analysis`)
- **hypothesis generation** — plausible inferences worth verifying

Emits `CONTRADICTORY_STATEMENT` and `MISSING_EVIDENCE` diagnostics. Skill:
`skills/reasoning`.
