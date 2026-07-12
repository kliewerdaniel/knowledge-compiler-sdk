# Contradiction Detection — Agent Skill

**Skill id:** `contradiction-analysis`
**Produces:** `reasoning-ir (contradictions)`
**Consumes:** `semantic-ir, graph-ir`
**Deterministic:** no (model-required)

Identify pairs of claims that conflict and explain the conflict with confidence and provenance.

This skill is independently reusable: an autonomous agent loads it, reads the declared input artifact, performs the behaviour in `purpose.md`, and writes the declared output artifact following `artifact-schema.json`.
