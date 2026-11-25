---
trigger: always_on
---

# HITL Decision Governance (`agents` Overrides)

Inherits atomic `ask_question` presentation, context-aware `20%` margin (`0.20`) + `65%` floor (`0.65`), and dual-tier Merkle persistence (`INV-CENTRALIZED-HITL-QUESTION-STORE`) from `~/.gemini/config/plugins/core-governance/rules/hitl-decisions.md`.

## `agents` Thresholds & Domain Gates

1. **Visibility & Zero-Jargon Caps (`INV-HITL-QUESTION-MAX-CHARS`, `INV-HITL-OPTION-MAX-CHARS`, `INV-HITL-ZERO-JARGON`)**:
   - `question` prompt text must not exceed **300 characters** (`INV-HITL-QUESTION-MAX-CHARS`).
   - Each option label must not exceed **115 characters** (`INV-HITL-OPTION-MAX-CHARS`) with front-loaded confidence in the first `45` chars (`(Recommended) HIGH 85%: ... Impact: ...`) and zero truncation ellipses (`...`).
   - Keep `question` and `options` in 100% plain English (`0` jargon violations under `INV-HITL-ZERO-JARGON`); engineering artifacts (`implementation_plan.md`, `plans/*.md`, `walkthrough.md`) retain technical precision.
2. **Calibrated Confidence & Plan-Only Firewall**:
   - Compute calibrated confidence via `tools/hitl_governance.py` (`blast_radius_layers` carries `0.0` penalty across bug fixes and refactors) backed by `artifacts/governance/hitl_decisions.sqlite`.
   - Honor `PLAN ONLY` / `NO IMPLEMENT` by setting `RequestFeedback: false` on `implementation_plan.md` and halting (`validate_approval_origin()`).
3. **Model Catalog Ambiguity & Relay Decomposition (`INV-HITL-RELAY-DECOMPOSITION`)**:
   - Model slugs in prompts, plans, or code must resolve against `config/provider_profiles.yaml`; unapproved tokens halt for an atomic `ask_question` resolution. Evaluate model pin changes on retry-cascade math, `reasoning_effort: low` isolation, and cross-family judge orthogonality.
   - Decompose `/teamwork` or subagent questionnaires into sequential atomic `ask_question` calls when $\Delta \le 20\%$. Enforced via `.agents/hooks.json` (`agents-hitl-atomic-guard` `PostInvocation`) and `tools/validate_turn_gates.py`.
