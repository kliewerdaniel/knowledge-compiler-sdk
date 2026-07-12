# New Skill Template

Copy this directory to `skills/<name>/` and create the 11 files. Each file's
purpose is fixed so skills are interchangeable across agents.

| File | Contains |
|------|----------|
| `README.md` | Skill id, produces/consumes, deterministic flag, one-paragraph purpose, file index. |
| `purpose.md` | The single conceptual operation, stated as behaviour steps. |
| `inputs.md` | Which artifact(s) are read and how (operate on the IR, not raw prose). |
| `outputs.md` | Which artifact is written, validated against `artifact-schema.json`. |
| `artifact-schema.json` | A JSON Schema describing the skill's output contract. |
| `acceptance-tests.md` | Objective pass/fail conditions (valid, sourced, 0 errors, deterministic, eval≥0.6). |
| `evaluation.md` | Which of the nine dimensions this skill targets and how. |
| `failure-modes.md` | What goes wrong and the diagnostic each raises. |
| `examples.md` | A minimal invocation + how to inspect the output. |
| `prompt.md` | The (small) prompt that consumes structured artifacts, not raw Markdown. |
| `checklist.md` | Pre-flight checklist before running the skill. |

## Golden rules

1. The purpose is to **describe behaviour**, not to contain a giant prompt.
2. Prompts consume **structured artifacts**, never raw Markdown.
3. Move intelligence into the **artifacts**, not the prompts.
4. Every output element must cite a **provenance span / source id**.
5. Emit diagnostics; never hide a quality problem.
6. Keep the prompt **small** — the IR carries the context.
