---
trigger: model_decision
---

# ADG Scheduled Retention Contract

```json
{
  "entities": [{
    "name": "ProceduralPattern:ADGScheduledRetentionContract",
    "entityType": "ProceduralPattern",
    "observations": [
      "Fixes recurring artifacts/adg accumulation where scheduled automation runs tools/adg/adg_impact_tests.py, but generate_full_ADG only archives late in tools/generate/adg_impact_tests.py after manifests and zip creation.",
      "Scheduled ADG retention must call tools.generate.archiving._archive_old_artifacts from tools/adg/adg_impact_tests.py using the derived generation manifest run id, recovered output run id, or newest same-run adg_indexed_<ts>.sqlite.",
      "Retention grouping must include markdown, YAML, SQLite attestation sidecars, graphdb workdirs, run zips, reports, and year-leading UTC helper JSON that points back to the canonical adg_indexed_<ts>.sqlite metadata.",
      "Guard tests: python -m pytest tests/unit/tools/generate/test_archive_retention_graphdb (retired) tests/unit/tools/generate/test_archive_session_scratch (retired) tests/unit/tools_adg/test_run_full_adg_audit (retired) -q.",
      "Do not rely on the scheduled TOML command to invoke generate_full_ADG's late cleanup path; keep the wrapper cleanup fail-soft so audit receipts still write when retention itself fails.",
      "discovered: 2026-07-01, validated: 2026-07-01"
    ]
  }]
}
```
