---
trigger: model_decision
---

# ADG Redis Hotcache Query Alignment

```json
{
  "entities": [{
    "name": "ProceduralPattern:ADGRedisHotcacheQueryAlignment",
    "entityType": "ProceduralPattern",
    "observations": [
      "Fixes ADG Redis cache misses caused by helpers reading legacy unversioned keys while adg_redis_ingest writes versioned snapshot keys.",
      "Use tools/adg/adg_impact_tests.py --check to verify the current workspace's latest adg_indexed_<ts>.sqlite has adg:v1:<ts>:_hot.",
      "Use tools/adg/adg_impact_tests.py for quick node/edge lookups; it must resolve snapshot_id/cache_version from adg:meta/adg:status and read adg:v1:<snapshot_id>:node|edge|fanin|edge_detail keys.",
      "Use tools/adg/adg_impact_tests.py --json for commit-vs-SQLite-snapshot freshness; Git queries must use --after=@<epoch> to avoid UTC/local timezone drift, and freshness must prefer adg:meta.sqlite_mtime over ingested_at so re-ingesting an old SQLite file cannot mask stale graph content.",
      "Do not rely on tools/adg_impact_tests.py, tools/adg/storage_worktree_hygiene.py, tools/adg/adg_impact_tests.py, or tools/adg/ssot_boundary_auditor.py in this checkout unless those files are restored; the canonical generator path is tools/generate/adg_impact_tests.py.",
      "discovered: 2026-06-29, validated: 2026-06-29"
    ]
  }]
}
```
