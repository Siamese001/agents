---
trigger: glob
globs: "{resume_graph_engine/src/apps_rg/runtime/**,apps_research/**,outreach_engine/**,apps_eval/**}"
---

# Runtime Evidence & Grounded Delivery Rules (`agents` Overrides)

Inherits runtime inventory inspection, scoped negative claims, and provenance binding from `~/.gemini/config/plugins/core-governance/rules/runtime-evidence.md`.

## `agents` Delivery & Disposition Invariants

- **Independent Run Inspection**: Verify generated display text, wire request payloads, and raw judge parse results directly from the run directory rather than relying solely on self-reported summary fields.
- **Post-Verification Immutability (`INV-GROUNDING-DELIVERY-IMMUTABILITY`)**: Never mutate display text between X2/X1D verification and final export without full re-validation and receipt re-sealing.
- **Fail-Closed Publication (`INV-GROUNDING-SAFE-FAILURE-RESPONSE`)**: Denied dispositions (`X3A_DENY_REROUTE` / `X3_BLOCK`) must write `status="FAIL"` and `product_authorized=false` with exact blocker diagnostics.
- **Model Catalog Parity**: Every active slug in `config/model_catalog.json` and `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml` must resolve to an approved runnable provider entry.
