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
      "When Redis ADG hotcache helpers are active, resolve snapshot_id/cache_version from adg:meta/adg:status and read adg:v1:<snapshot_id>:node|edge|fanin|edge_detail keys against the latest adg_indexed_<ts>.sqlite.",
      "For commit-vs-SQLite-snapshot freshness, Git queries must use --after=@<epoch> to avoid UTC/local timezone drift, and freshness must prefer adg:meta.sqlite_mtime over ingested_at so re-ingesting an old SQLite file cannot mask stale graph content.",
      "Legacy tools/adg/* Redis CLI wrappers are retired in this checkout; use tools/adg_impact_tests.py for test-impact selection and AST/grep inspection directly when adg_sqlite is offline.",
      "discovered: 2026-06-29, validated: 2026-06-29"
    ]
  }]
}
```
