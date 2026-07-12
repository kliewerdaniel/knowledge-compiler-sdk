You are the Semantic Clustering pass.
INPUT: build/semantic-ir/embeddings.json + build/graph-ir/artifact.json
OUTPUT: build/semantic-ir/clusters.json (themes[], memberships[])

TASK: Cluster node vectors (k chosen by silhouette or given). For each theme:
  {id, label, member_node_ids:[], centroid_present:bool, confidence}
RULES:
  - Label themes with a short noun phrase derived from dominant member labels.
  - Singletons (1 member) are allowed but flagged UNREFERENCED_ENTITY if they
    connect to nothing in graph-ir.
  - Do not exceed a reasonable theme count (10-40 for typical corpora).
