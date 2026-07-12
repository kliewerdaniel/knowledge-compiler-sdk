# New Pass Template

Copy this directory to `compiler/passes/pass-NN-<name>/` and fill it in.

## pass.yaml

```yaml
id: pass-NN-name
name: Human Label
produces: <artifact-type>
consumes: [<upstream-artifact-types>]
downstream: [<downstream-artifact-types>]
entrypoint: run.py        # for deterministic passes
prompt: prompt.md        # for model-required passes (omit entrypoint)
deterministic: false
model_required: true
description: >
  One-line description of the single conceptual operation this pass performs.
```

## README.md

```
# pass-NN-name — Human Label

**Produces:** `<artifact-type>`
**Consumes:** `<upstream>`
**Deterministic:** no · **Model required:** yes

What this pass does, in prose. Reference the reusable skill under
`skills/<name>` that an agent loads to execute it.
```

## prompt.md (model-required passes only)

```
You are the <Human Label> compiler pass.
INPUT: build/<upstream>/artifact.json
OUTPUT: build/<artifact-type>/{artifact.json,metadata.json,diagnostics.json}

TASK: <precise, structured instruction>
RULES:
  - <constraint tying outputs to source spans / provenance>
  - <diagnostic to emit on failure mode>
  - Validate against schemas/<artifact-type>.json.
```

## The pass contract (every pass obeys this)

- **Purpose** — one sentence, one conceptual operation.
- **Inputs** — the artifact type(s) read.
- **Outputs** — the artifact type written.
- **Algorithm** — explicit steps so the procedure is identical every run.
- **Expected reasoning** — what inference is allowed vs. forbidden.
- **Artifacts produced** — JSON/Markdown/YAML/GraphML/Mermaid/etc.
- **Failure cases** — what breaks and the diagnostic raised.
- **Evaluation criteria** — the nine dimensions scored.
- **Acceptance tests** — objective pass/fail.
- **Example execution** — a concrete run.
