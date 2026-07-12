# Prompt — Pass Evaluation

You are the Pass Evaluation skill. INPUT: any build/<artifact>/{artifact.json,metadata.json,diagnostics.json}. OUTPUT: build/<artifact>/evaluation.json.
Compute the nine-dimension scorecard (see docs/evaluation.md). Merge structural heuristics with pass hints. Render per-dimension scores + overall. This skill is also implementable deterministically (compiler/core/evaluation.py).
