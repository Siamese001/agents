# Centralize Tier-1 Governance Linters, Rules, Skills & Hooks (Wave 4 Cutover)

## Implementation Status Table

| Wave | Description | Status | Deliverables / Receipts |
| :--- | :--- | :--- | :--- |
| Wave 1 | Sync standalone Tier-1 fallback bundles and configure repository linter profile | COMPLETED | `config/governance/linter_profile.json`, `tools/_standalone_*.py` |
| Wave 2 | Delegate Tier-1 security, purity, naming, layer, commit, and wave-plan validators to `core-governance` with standalone CI fallback | COMPLETED | `tools/lint_secrets.py`, `tools/lint_production_purity.py`, `tools/lint_model_neutral_naming.py`, `tools/lint_layer_imports.py`, `tools/lint_commit_message.py`, `tools/validate_implementation_plan.py` |
| Wave 3 | Retire duplicate workspace skills, deduplicate HITL tool hooks, and compact shared `.agents/rules/*.md` overrides | COMPLETED | `.agents/hooks.json`, `.agents/rules/*.md`, `tools/audit_governance_harmonization.py` |

## Wave 1: Standalone Fallback Bundles & Repository Linter Profile
### Objective & Scope
Verify SHA-256 synchronized Tier-1 standalone fallback modules in `tools/` and register `agents` wave-plan validator settings in `config/governance/linter_profile.json`.

### Milestones & Deliverables
- [NEW] `tools/_standalone_security_purity.py`
- [NEW] `tools/_standalone_boundary_naming.py`
- [NEW] `tools/_standalone_plan_validator.py`
- [NEW] `config/governance/linter_profile.json`
- [MODIFY] `tools/ssot_boundary_auditor.py`

### Acceptance Criteria
- Standalone linter and wave-plan validator bundles verify cleanly against `core-governance` SHA-256 digests with zero manual edits.
- `config/governance/linter_profile.json` declares `allow_sharded: true`, `base_max_words: 0`, and canonical `legacy_exemptions`.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python ~/.gemini/config/plugins/core-governance/mcp/policy_ssot_parity_engine.py --repo-root .`
- Input: `tools/_standalone_*.py` and `config/governance/linter_profile.json`
- Expected: `tier1_standalone_bundle_drift` reports 0 findings and exit code 0
- Verify independently: `.venv/bin/python tools/lint_contract_schemas.py --files config/governance/linter_profile.json`
- Fail if: standalone SHA-256 digest mismatches or `linter_profile.json` fails JSON schema/syntax validation
- Record: `plans/centralize-tier1-governance-c1a4e9.md`

## Wave 2: Tier-1 Linter & Wave-Plan Validator Delegation with Dual-Mode Fallback
### Objective & Scope
Refactor the six Tier-1 linters and validators in `tools/` to delegate core scanning to `core-governance/mcp` when available while falling back seamlessly to `tools._standalone_*` when `CORE_GOVERNANCE_FORCE_STANDALONE=1` or the plugin directory is absent, preserving 100% of public symbols, CLI flags, and return shapes.

### Milestones & Deliverables
- [MODIFY] `tools/lint_secrets.py`
- [MODIFY] `tools/lint_production_purity.py`
- [MODIFY] `tools/lint_model_neutral_naming.py`
- [MODIFY] `tools/lint_layer_imports.py`
- [MODIFY] `tools/lint_commit_message.py`
- [MODIFY] `tools/validate_implementation_plan.py`

### Acceptance Criteria
- All six CLI tools and Python module APIs pass in both normal `core-governance` mode and `CORE_GOVERNANCE_FORCE_STANDALONE=1` mode.
- `tools/verify_commit.py --all` and all unit tests importing Tier-1 linter symbols pass with zero regressions.

### Runtime Receipt & Completion Gate
- Run: `CORE_GOVERNANCE_FORCE_STANDALONE=1 .venv/bin/python tools/verify_commit.py --all`
- Input: full `agents` worktree Python, config, and markdown files
- Expected: all 5 Tier-1 pre-commit categories pass with exit code 0 in both normal and standalone modes
- Verify independently: `.venv/bin/python -m pytest tests/test_implementation_plan_governance.py tests/test_model_neutral_naming.py --timeout=60`
- Fail if: any symbol import breaks or normal vs standalone outputs diverge
- Record: `plans/centralize-tier1-governance-c1a4e9.md`

## Wave 3: Skill Deduplication, Hook Deduplication & Thin Rule Compaction
### Objective & Scope
Delete the three workspace skills now centralized in `core-governance/skills/`, remove duplicate `ask_question` `PreToolUse`/`PostToolUse` entries from `.agents/hooks.json`, and compact the 13 shared `.agents/rules/*.md` files into thin `agents`-specific overrides inheriting `core-governance/rules/<name>.md`.

### Milestones & Deliverables
- [DELETE] `.agents/skills/agent-runtime-engineering/SKILL.md`
- [DELETE] `.agents/skills/agent-subagent-orchestration/SKILL.md`
- [DELETE] `.agents/skills/governance-harmonizer/SKILL.md`
- [MODIFY] `.agents/hooks.json`
- [MODIFY] `config/governance/policy_registry.yaml`
- [MODIFY] `tools/audit_governance_harmonization.py`
- [MODIFY] `tests/unit/test_prompt_collision_safeguards.py`
- [MODIFY] `.agents/rules/conformance-map.md`
- [MODIFY] `.agents/rules/contract-enforcement.md`
- [MODIFY] `.agents/rules/e2e-and-edge-case-coverage.md`
- [MODIFY] `.agents/rules/git-worktree-governance.md`
- [MODIFY] `.agents/rules/hitl-decisions.md`
- [MODIFY] `.agents/rules/plan-first-enforcement.md`
- [MODIFY] `.agents/rules/pr-governance.md`
- [MODIFY] `.agents/rules/production-derivation-and-anti-overfitting.md`
- [MODIFY] `.agents/rules/provider-resilience-and-healing.md`
- [MODIFY] `.agents/rules/risk-tiered-change-lanes.md`
- [MODIFY] `.agents/rules/runtime-evidence.md`
- [MODIFY] `.agents/rules/unified-agent-architecture.md`
- [MODIFY] `.agents/rules/wave-progression.md`

### Acceptance Criteria
- `audit_governance_harmonization.py --strict`, `validate_turn_gates.py --mode pre-turn`, `audit_skills_budget.py`, and `policy_ssot_parity_engine.py` all pass with 0 critical findings.
- `.agents/rules/sidecar-automation-routing.md` and all peer-worktree-owned files remain 100% untouched.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python tools/audit_governance_harmonization.py --repo-root . --strict`
- Input: compacted `.agents/rules/*.md`, `.agents/hooks.json`, `.agents/skills/`, and `config/governance/policy_registry.yaml`
- Expected: `status=PASS` with `critical=0` and reduced always-on context bytes and skill token utilization
- Verify independently: `.venv/bin/python ~/.gemini/config/plugins/core-governance/mcp/policy_ssot_parity_engine.py --repo-root .`
- Fail if: any policy threshold, script reference, hook handler, or turn gate fails closed
- Record: `plans/centralize-tier1-governance-c1a4e9.md`
