---
name: governance-harmonizer
description: Reconciles rules, skills, hooks, policy registries, and AI-SDLC gates for threshold drift and broken cross-references.
---

# Governance Harmonizer

Automated cross-surface reconciliation across `AGENTS.md`, `.agents/rules/*.md`, `.agents/skills/*/SKILL.md`, `.agents/hooks.json`, `config/governance/policy_registry.yaml`, and `config/governance/risk_lanes_policy.json`.

## When to Use

- After editing `AGENTS.md`, `.agents/rules/*.md`, `.agents/skills/*/SKILL.md`, `.agents/hooks.json`, or `config/governance/*`.
- Before PR promotion (`tools/verify_main_readiness.py` Stage 9 runs this automatically).

## What It Checks

1. **Threshold & Policy Parity**: Verifies `AGENTS.md <= 200` lines, skills description budget `< 4,000` tokens, HITL margin (`0.20`), fail-closed `default_unrecognized_lane == 2`, and `executive_summary` blind `4.7/5.0` judge thresholds match across registries and Python enforcers.
2. **Broken Script Cross-References**: Ensures every `tools/*.py` path cited in `.agents/rules/*.md` and `.agents/skills/*/SKILL.md` exists on disk.
3. **Hook Handler Parity**: Ensures every `--hook <name>` referenced in `.agents/hooks.json` maps to an active handler in `tools/hook_dispatch.py`.
4. **Domain Purity**: Ensures AI-SDLC governance rules contain zero foreign-repo domain bleed.

## Execution

```bash
.venv/bin/python tools/audit_governance_harmonization.py --strict
.venv/bin/python tools/audit_governance_harmonization.py --strict --json-only
```
