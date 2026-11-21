---
trigger: model_decision
description: Production derivation integrity, anti-overfitting ban on company/JD branches, provenance truth, and post-verification immutability
---
# Production Derivation Integrity & Anti-Overfitting Rules

Governs production derivation purity (`INV-ANTI-OVERFITTING-MULTI-JD`), candidate fact provenance truth, and post-verification immutability (`INV-GROUNDING-DELIVERY-IMMUTABILITY`).

## 1. Core Invariants

1. **Derivation Integrity**: Every domain-bearing production artifact (resumes, outreach messages, research briefs, and evaluation verdicts) must be derived from runtime inputs plus verified configuration through declared prompts and domain-blind normalization. Hardcoded domain paragraphs, synthetic unverified metrics, or golden-fixture answer imports in production code fail closed.
2. **Ban on Company-Specific or Single-JD Logic (`INV-ANTI-OVERFITTING-MULTI-JD`)**: Production runtime modules (`resume_graph_engine/src/`, `outreach_engine/`, `apps_research/`, `agents/`) must never branch on specific target company names or single-JD literals (for example, `if "truist" in jd_text:` or `if company == "anthropic":`) outside declared targeting config files. Generalizable role profiles, career-band weights, and multi-JD benchmarks govern allocation and ranking.
3. **Strict Fact Provenance & Section Eligibility**: Candidate facts and quantified metrics must bind to verified candidate provenance rather than unverified synthetic entries, and allocators must strictly enforce per-item `section_eligibility` before binding any metric to a section.
4. **Post-Verification Immutability (`INV-GROUNDING-DELIVERY-IMMUTABILITY`)**: Once a section or deliverable passes deterministic X2 validation and blind LLM-as-a-Judge evaluation, silent post-hoc text mutation is strictly prohibited. Any rewrite or voice repair must re-execute the full deterministic validation suite and synchronize usage ledgers, rolling back cleanly on any failure.
5. **Plain-English Human Authenticity**: Executive prose must read like a high-caliber human executive, not an impersonal datasheet or stitched template. Inanimate-subject openers, AI transition crutches, and abstract noun soup fail deterministic and blind-judge verification.
6. **Zero Agent-Synthesized Candidate Facts (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS`)**: Agents are strictly prohibited from inventing, extrapolating, or "backfilling" candidate metrics, vendor names, or achievements (`approved_by_graph_presence` without verified base-resume or operator-confirmed provenance) into `fact_inventory/*.json` to pass a metric or coverage gate. When a candidate lacks a quantified metric for a role, surface the source-data gap to the user rather than fabricating data.
7. **Zero Post-LLM Prose Mutators (`INV-NO-POST-LLM-PROSE-MUTATORS`)**: Never add deterministic regex text-splicers, suffix-appenders, mechanical opener strippers, or stacked post-LLM rewriters to patch LLM prose quality. Fix prose quality strictly upstream (clean verified facts, concise contradiction-free prompt, or a single bounded fresh-turn judge-guided rewrite loop).
8. **Multi-JD Anti-Whiplash Gate (`INV-MULTI-JD-NO-WHIPLASH`)**: Never alter global section shapes (sentence bands, employer slot locks, or diversity rules) in response to a single JD run without verifying against the standing multi-JD benchmark (banking, AI lab, insurance, enterprise software) so fixing one JD never breaks the next.

## 2. Enforcement

- AST & Regex Linter (Tier 1): `tools/lint_no_jd_overfitting.py` and `tools/lint_production_purity.py`.
- Tier 1 Gate: `tools/verify_commit.py` (Category 3: Production Purity).
- Tier 2 Gate: `tools/verify_main_readiness.py` (Stage 3: Adversarial Purity & Derivation Integrity + Stage 8: Diff-Scoped Unmocked Domain Eval Shield).
