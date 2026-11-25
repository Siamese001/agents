---
trigger: model_decision
description: Wave-based implementation plan format, 6-field completion gates, sharded progression, and pytest Class A/B protocol.
---

# Wave Progression Rules (`agents` Overrides)

Inherits execution-evidence-gated wave progression, 4-section / 6-field gate schema, and top green-checkmark closeout tables (`INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE`) from `~/.gemini/config/plugins/core-governance/rules/wave-progression.md`.

## `agents` Plan Profile & Sharded DAG Settings

- **Unbounded Plan & Shard Profile (`INV-WAVE-PLAN-MAX-WORDS = 0`)**: Configured in `config/governance/linter_profile.json` (`allow_sharded: true`, `base_max_words: 0`) and validated via `tools/validate_implementation_plan.py` and `tools/implementation_plan_core/wave_dag.py` (`Wave 2A`/`2B`, `Depends On:`, and fenced `shard-manifest` blocks).
- **Top Closeout Table & Brevity (`INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE`)**: `/plan`, `/learn`, wave completion, and branch-promotion turns render the 3-column green-checkmark table (`**Plan**`, `**Learning**`, `**Wave 1..N**`, plus dedicated `**Merge to Main**` and `**Worktree Deletion**` `✅ Complete` rows on branch promotion, enforced via `tools/hook_dispatch.py`), while adhering to [.agents/rules/output-brevity-governance.md](output-brevity-governance.md) (target ~150-250 words, max 450 words) and omitting verbose 6-column internal wave ledgers from chat.

## `pytest` Class A & Class B Run Protocol

- **Class A (Debug & Verification)**: Permits a single test file, named test case, coupled multi-file producer+contract+consumer test slice (no file-count cap), or full subsystem/repository suites (`pytest tests/ --timeout=60`, `pytest resume_graph_engine/tests/ --timeout=60`, etc.; compute transitive impact via `.venv/bin/python tools/adg_impact_tests.py --changed-files <files>`). Always pass `--timeout=60` (or `--timeout=180` for broad E2E/integration suites) synchronously (`WaitMsBeforeAsync >= 10000`).
- **Class B (Wave Receipt)**: Runs all declared acceptance and impacted regression tests synchronously with `--timeout=60` (or `--timeout=180`), recording pass counts in the wave receipt without skipping or weakening assertions.
