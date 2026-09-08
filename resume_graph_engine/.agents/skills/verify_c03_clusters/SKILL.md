---
name: verify-c03-clusters
description: Procedures and verification commands for checking C0.3 graph embeddings, W4 cluster registry, and W5 retirement boundaries in apps_rg_v2.
---

# Verify C0.3 Graph Embedding Clusters

## Overview
The canonical C0.3 ledger is the sole claim authority for resume skills embedding and retrieval.
The former one-vector-per-skill lane was retired in C0.3 cluster-embedding Wave 5.

## Verification Procedure
To verify that the retirement boundary and cluster registries are intact, execute via Defender:

```powershell
python tools/apps_rg_standalone/c03_legacy_embedding_retirement_wave5.py --check
```

## Invariants
- The W4 registry contains 38 multi-node graph-evidence clusters.
- W5 generated no replacement vectors and did not create an activation manifest.
- W6 is authorized to generate one vector per active cluster; production promotion remains separately gated.
- `APPS_RG_GRAPH_SKILL_EMBEDDINGS_REQUIRED` is retired and forbidden.
