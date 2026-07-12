# Acceptance Tests — Contradiction Detection

A pass run is **accepted** when ALL hold:
1. Output artifact exists and validates.
2. `metadata.producer_pass` and `metadata.content_hash` present.
3. Every output element cites a provenance span/source id.
4. 0 ERROR diagnostics.
5. Re-run identical input -> identical hash (when model pinned).
6. Evaluation overall ≥ 0.6.
