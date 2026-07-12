# Missing Information Detection — Agent Skill

**Skill id:** `gap-analysis`
**Produces:** `reasoning-ir (questions)`
**Consumes:** `semantic-ir, graph-ir`
**Deterministic:** no (model-required)

Detect claims/themes that reference evidence not present in the corpus, and surface unanswered questions worth resolving.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
