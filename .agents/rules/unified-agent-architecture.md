---
trigger: model_decision
description: Five-pillar taxonomy, 10-field delegation contract, upstream return protocol, and in-process A2A guardrails.
---

# Unified Agent Architecture Rules (`agents` Overrides)

Inherits the Five Pillars (Skills, Agents, Sub-Agents, Hooks, Rules), 7-step lifecycle, and 10-field delegation contract from `~/.gemini/config/plugins/core-governance/rules/unified-agent-architecture.md`.

## `agents` Delegation & In-Process A2A Guardrails

1. **Opt-In Contract Enforcement (`tools/unified_agent_architecture.py`)**: Interactive `/boost` and `/swarm` workers execute without artificial write-lock barriers (`INV-ZERO-BUGFIX-BLAST-RADIUS-CAP`); when an explicit `delegation_contract` is supplied, `tools/unified_agent_architecture.py` validates all 10 fields and `{task_id, status, deliverable, evidence_refs, metrics}` returns.
2. **In-Process Domain A2A Guardrails**:
   - **Cross-Family Orthogonality**: Drafter vs. Auditor/Skeptic loops resolve orthogonal provider families from `config/provider_profiles.yaml` with compact auditor/selector turns locked to `reasoning_effort: low`.
   - **Structured Disposition & Non-Orphan Directives**: Auditor/Skeptic turns validate deterministic JSON (`disposition`, `violated_facts`, `repair_hint`) and bind repair directives (`O1`, `O4`, `REGEN_DELTA`) directly into `execute_patch_run` / `execute_phase1_lanes`, preserving W9 `apps_research` judge boundaries and C0.3 `resume_graph_allocation.py` ID invariants.
