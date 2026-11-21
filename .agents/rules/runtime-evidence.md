---
trigger: glob
globs: "{resume_graph_engine/src/apps_rg/runtime/**,apps_research/**,outreach_engine/**,apps_eval/**}"
---
# Runtime Evidence & Grounded Delivery Rules

Governs claims about runtime state, retrieval evidence, evaluation receipts, and grounded product delivery across `agents` applications.

## 1. Evidence Inventory & Scoping

- **Inspect Before Claiming**: Verify runtime state, lane dispositions, and artifact files directly from the target run directory before reporting pass/fail status.
- **Explicit Scoping**: Bind every evaluation claim to its explicit run directory, commit SHA, and receipt digest.
- **Absence Claims**: Pattern search misses prove only that a string was unobserved in the searched scope, never global absence.
- **Independent Verification Over Self-Reports**: Receipts record runs; they never substitute for independently inspecting generated display text, wire request payloads, and raw judge parse results.

## 2. Grounded Delivery Invariants

- **Verified Source Grounding**: Factual claims, metrics, and technology names surfaced in resumes or outreach must bind to verified candidate/company source records, never to unverified synthetic placeholders or JD targeting text.
- **Post-Verification Immutability (`INV-GROUNDING-DELIVERY-IMMUTABILITY`)**: Prohibit modifying display text between X2/X1D verification and final aggregation/export without full re-validation and receipt re-sealing.
- **Fail-Closed Publication (`INV-GROUNDING-SAFE-FAILURE-RESPONSE`)**: Blocked or denied runs (`X3A_DENY_REROUTE` / `X3_BLOCK`) must write `status="FAIL"` and `product_authorized=false` with exact blocker diagnostics; never emit `status="PASS"` on a denied disposition.
- **Model Registry Parity**: Every active model slug in `config/model_catalog.json` and `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml` must resolve to an approved, runnable provider entry with no phantom model tokens.
