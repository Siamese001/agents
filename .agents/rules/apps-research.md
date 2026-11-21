---
trigger: glob
globs: "apps_research/**"
---

# Apps Research Governance

Applies to all work inside `apps_research/`.

## Core Runtime Invariants

- **Autonomous Subsystem Encapsulation**: `apps_research/` is an independent domain subsystem; cross-subsystem imports must respect directional boundaries enforced by `tools/ssot_boundary_auditor.py` and `tools/lint_architecture_boundaries.py`.
- **Fail-Closed Targeting Brief & Handoff Envelope**: Missing, malformed, or schema-invalid research targeting briefs and handoff envelopes must fail closed rather than silently falling back to fabricated or ungrounded summaries.
- **Ingress-Only Judge & Evidence Grounding**: Preserve deterministic evidence provenance and real unmocked retrieval verification (`tools/retrieval_surface_auditor.py`, `tests/unit/apps_research/`).
- **Hardware Acceleration Policy**: Limit local MPS/GPU usage to embedding/transformer inference resolved via `infrastructure/device/device_manager.py`; keep control-plane orchestration and SQLite/FTS operations on CPU.
