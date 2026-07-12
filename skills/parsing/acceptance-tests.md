# Acceptance Tests — Markdown Parsing

A pass run is **accepted** when ALL hold:
1. Output artifact exists and validates against `artifact-schema.json`.
2. `metadata.producer_pass` and `metadata.content_hash` present.
3. Every output element cites a provenance span or source id.
4. Diagnostic counts: 0 ERROR; WARNINGs documented.
5. Re-run identical input -> identical `content_hash` (always).
6. Evaluation overall ≥ 0.6.
