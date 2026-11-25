---
trigger: model_decision
description: Production derivation integrity, anti-overfitting ban on company/JD branches, provenance truth, and post-verification immutability
---

# Production Derivation Integrity & Anti-Overfitting (`agents` Overrides)

Inherits runtime derivation purity, fixture/test import quarantine, and post-verification immutability from `~/.gemini/config/plugins/core-governance/rules/production-derivation-and-anti-overfitting.md`.

## `agents` Domain Purity Invariants

1. **Zero Single-JD or Company Branching (`INV-ANTI-OVERFITTING-MULTI-JD = 0`, `INV-MULTI-JD-NO-WHIPLASH = 0`)**: Production code (`resume_graph_engine/src/`, `outreach_engine/`, `apps_research/`, `agents/`) must never branch on specific target company or single-JD literals outside declared targeting configs, and global section shapes must hold across the multi-JD benchmark (`tools/lint_no_jd_overfitting.py`).
2. **Verified Candidate Fact Provenance (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS = 0`)**: Never fabricate or backfill candidate metrics (`approved_by_graph_presence` without base-resume or operator-confirmed truth) into `fact_inventory/*.json`, and enforce per-item `section_eligibility`.
3. **Zero Post-LLM Prose Mutators & Delivery Immutability (`INV-NO-POST-LLM-PROSE-MUTATORS = 0`, `INV-GROUNDING-DELIVERY-IMMUTABILITY`)**: Fix prose defects upstream via verified facts, contradiction-free prompts, or a single bounded judge-guided rewrite loop rather than regex text-splicers; any rewrite must re-run deterministic X2 validation.
4. **Enforcement**: `tools/lint_production_purity.py`, `tools/lint_no_jd_overfitting.py`, `tools/verify_commit.py`, and `tools/verify_main_readiness.py`.
