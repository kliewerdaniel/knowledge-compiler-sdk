# Example

A worked, runnable example of the Knowledge Compiler.

## Corpus

`examples/corpus/` contains two short Markdown documents about the Sovereign
Intelligence Stack and knowledge compilers. They cross-reference each other so
the document graph is non-empty.

## Build

```bash
python examples/build_example.py
```

This runs `pass-01-parse` for real and produces:

```
examples/build/
  source/                       # staged Markdown
  markdown-ir/                  # artifact.json, metadata.json, diagnostics.json, evaluation.json
  plan.json                    # the orchestrator's plan (10 steps, 9 model passes planned)
```

The Markdown IR is fully computed and schema-validated. The model-required
passes (02–10) are present in `plan.json` as `skipped` with reasons — fill them
by loading the matching `skills/<name>` in an agent.

## Inspecting

```bash
cat examples/build/markdown-ir/artifact.json | python -m json.tool | head -40
cat examples/build/markdown-ir/diagnostics.json
cat examples/build/plan.json
```
