# Evaluation

The Knowledge Compiler is only as trustworthy as its artifacts. Every artifact
is scored along **nine dimensions**, producing a scorecard that is itself a
committed artifact (`evaluation.json`). This document defines the framework.

## The nine dimensions

| Dimension        | 0 means…                          | 1 means…                         |
|------------------|-----------------------------------|----------------------------------|
| `completeness`   | required fields missing           | all required fields populated    |
| `correctness`    | fails schema validation           | validates against its JSON Schema|
| `coverage`       | source barely represented         | entire corpus represented        |
| `consistency`    | internal contradictions present   | no internal contradictions       |
| `hallucination`  | many unsourced claims             | every claim traceable to inputs  |
| `traceability`   | no provenance links               | all elements carry provenance    |
| `provenance`     | metadata incomplete               | full metadata (hash, sources)    |
| `confidence`     | low mean confidence               | high mean confidence             |
| `reproducibility`| non-deterministic / unpinned      | identical input → identical hash |

Each score is in `[0,1]`. The **overall** score is the weighted mean:

```
weights = completeness .15, correctness .15, coverage .10, consistency .10,
          hallucination .15, traceability .10, provenance .10,
          confidence .10, reproducibility .05
overall = Σ(score_k * w_k) / Σ(w_k)
```

## How scores are computed

Two sources feed a score:

1. **Structural heuristics** (always available, no model). The core computes
   `completeness` from populated top-level keys, `correctness` from schema
   validation, `provenance` from metadata fields, `confidence` from any numeric
   `confidence`/`score`/`weight` fields found in the data, and `reproducibility`
   from the producing pass's `deterministic` flag.
2. **Pass hints** (measured by the pass). A model-required pass may attach
   measured values — e.g. `{"coverage": 0.83, "hallucination": 0.04}` — which
   override the heuristic for that dimension. Every artifact gets a full
   scorecard even when hints are absent.

The implementation lives at `compiler/core/evaluation.py` and is itself
deterministic and tested.

## Acceptance thresholds

A pass run is **accepted** when, for its output artifact:

- `correctness == 1.0` (must validate),
- diagnostic `error` count == 0,
- `overall >= 0.6`.

A pass that emits `HALLUCINATION_SUSPECT` or `CONTRADICTORY_STATEMENT` should see
its `hallucination`/`consistency` scores drop accordingly, surfacing the problem
in the scorecard rather than letting it silently propagate to the Application IR.

## Using evaluation in the loop

Because evaluation artifacts are committed, you can *trend* quality across
compiles: compare `evaluation.json` before and after changing a prompt or a
model. This turns "the agent feels better" into a measurable delta — the same
role optimisation reports play in a traditional compiler.

## Scorecard example (Markdown IR from the example corpus)

```json
{
  "artifact_type": "markdown-ir",
  "scores": {"completeness": 1.0, "correctness": 1.0, "coverage": 1.0,
             "consistency": 1.0, "hallucination": 1.0, "traceability": 1.0,
             "provenance": 1.0, "confidence": 0.5, "reproducibility": 1.0},
  "overall": 0.94
}
```

(The `confidence` of 0.5 reflects that the deterministic parse carries no
per-claim confidence — a reasonable default for a syntactic pass.)
