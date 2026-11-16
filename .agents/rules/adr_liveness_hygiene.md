---
trigger: model_decision
---

# ADR Liveness Hygiene

## ProceduralPattern:ADRLivenessHygiene

- ADR markdown is rationale/provenance only; current authority requires a live binding to a current gate, test, `.agents` rule/skill, config, runtime/code surface, or current plan.
- Use `.venv/bin/python tools/ssot_boundary_auditor.py` to audit SSOT/boundary alignment alongside ADR review (`live_bound`, `noncanonical`, `historical_stale_marker`, or `unbound_review`).
- Keep legacy ADR namespace drift reporting advisory while allowing known duplicate ADR numbers and known legacy/generated noncanonical ADR-like files.
- Do not wire the liveness inventory into default full contract gates without reassessing runtime cost; it scans repo-wide inbound references and took roughly 30-40 seconds locally on 2026-06-22.
- Discovered: 2026-06-22; validated: 2026-06-22.
