---
trigger: model_decision
---

# ProceduralPattern:ADGTransportNonBlockingFallback

```json
{
  "entities": [{
    "name": "ProceduralPattern:ADGTransportNonBlockingFallback",
    "entityType": "ProceduralPattern",
    "observations": [
      "INVARIANT: Prefer adg_sqlite MCP and artifacts/adg/*.sqlite when healthy, and fall back immediately to AST and code search without blocking root-cause bug fixes, /boost, or /swarm execution.",
      "scope: .mcp.json, tools/adg_impact_tests.py, tools/ssot_boundary_auditor.py",
      "enforcement: Non-blocking inspection fallback; closed or unavailable MCP transports never stall multi-file bug remediation or cohesive refactoring.",
      "canonical_pattern: Query adg_sqlite when available for fast fan-in/fan-out views, and combine freely with direct AST and grep inspection across all 11 repository roots.",
      "doctrine_ref: .agents/rules/constitutional.md §13 and §28",
      "updated: 2026-11-16"
    ]
  }]
}
```
