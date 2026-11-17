---
trigger: model_decision
---

# ADG Post-Run Output Bundle — stub

> On-demand during ADG work (plan `always-on-rule-surface-cut-c7f3a1`). A `generate_full_adg` / `run_full_adg_audit` run is not PASS unless the SAME response renders exactly one sealed `## ADG Executive Brief` after every generator/wrapper gate finishes. That brief must contain the decision-gate/FIX view and P0-P3 impact inventory; the standalone burndown markdown remains a digest-inventoried artifact and is never replayed as a second terminal report. Source of truth: timestamped `artifacts/adg/adg_run_output_bundle_<run_id>.json`; latest/docs mirrors are not handoff authority. Detail: [`scope-containment`](../skills/scope-containment/SKILL.md). Enforced: `ssot_boundary_auditor.py`. Bypass: `ADG_BURNDOWN_INLINE_BYPASS=1`.
