# Reasoning IR — Formal Specification

**Artifact type:** `reasoning-ir`
**Produced by:** `pass-08-reasoning`
**Consumed by:** `pass-09-specifications`, `pass-10-software`

## Purpose
The Reasoning IR is the analytical layer: it states what the knowledge *means*,
where it *conflicts*, what it *lacks*, and what may be *inferred*. This is the
pass that turns a graph into judgments.

## Containers
* **observations** — evidenced statements about the corpus.
* **hypotheses** — plausible inferences, each tied to observations.
* **contradictions** — pairs of conflicting claims.
* **unanswered questions** — gaps the knowledge does not resolve.
* **confidence** — per-item belief in `[0,1]`.

## Field specification
* `observations[]` — `{id, text, provenance:[span], confidence}`
* `hypotheses[]` — `{id, text, basis:[observation_id], confidence}`
* `contradictions[]` — `{id, a_claim, b_claim, explanation, confidence}`
* `questions[]` — `{id, text, theme, why_unanswered}`

## Invariants
* A contradiction requires TWO evidenced claims.
* A question with no supporting claim is a GAP → `MISSING_EVIDENCE`.
* Hypotheses are never asserted as fact (tagged `confidence` + `basis`).

## Diagnostics emitted
`CONTRADICTORY_STATEMENT`, `MISSING_EVIDENCE`, `HALLUCINATION_SUSPECT`.
