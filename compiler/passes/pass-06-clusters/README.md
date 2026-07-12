# pass-06-clusters — Semantic Clustering

**Produces:** `semantic-ir` (clusters portion) · **Consumes:** `semantic-ir`, `graph-ir`
**Deterministic:** no · **Model required:** yes

Clusters the embedding space into **themes**, labels each cluster, and records
which nodes belong to it. A labelled cluster is the seed of a section, page, or
component later in the pipeline. Skill: `skills/clustering`.
