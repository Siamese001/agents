# Agents Repository — SSOT & Subsystem Boundary Governance Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage II (Order 2/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **SSOT Conformance & Subsystem Boundary Governance Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`05:45 ET`, Order `2/7`). This agent enforces unidirectional layer imports (`L0–L6`), strict subsystem encapsulation across `outreach_engine/` (`apps_lic`), `resume_engine/` + `resume_graph_engine/` (`apps_rg`), `apps_research/`, and `infrastructure/`, model-neutral artifact naming, and `AGENTS.md` / `.agents/rules/conformance-map.md` synchronization.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Cross-subsystem import boundaries (`lint_architecture_boundaries.py`, `lint_layer_imports.py`), model-neutral naming (`lint_model_neutral_naming.py`), provider profile registry conformance (`config/provider_profiles.yaml`), and `AGENTS.md` / `.agents/` rule synchronization.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), E2E runtime behavior (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_ssot_boundary/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` with zero code mutations.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-ssot-boundary-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
git -C "${PRIMARY_REPO_ROOT}" worktree add "${WORKTREE_DIR}" -b "${BRANCH_NAME}" main
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Dimension Read-Only Audit & Executable Forensic Scanners

### Phase 1: 6-Dimension SSOT & Boundary Audit
1. **Dimension 1 — Cross-Subsystem Encapsulation**: Verify zero illegal direct imports between `outreach_engine/` (`apps_lic`) and `resume_engine/` / `resume_graph_engine/` (`apps_rg`), and verify shared research contracts flow strictly through `apps_research/` and `infrastructure/`.
2. **Dimension 2 — Unidirectional Layer Imports (`L0–L6`)**: Run `python3 tools/lint_layer_imports.py` and `python3 tools/lint_architecture_boundaries.py`.
3. **Dimension 3 — Model-Neutral Naming & Provider Catalog SSOT**: Run `python3 tools/lint_model_neutral_naming.py` and verify every model token resolves against `config/provider_profiles.yaml`.
4. **Dimension 4 — Constitutional AST Floor**: Scan `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, and `apps_research/` for `subprocess.run` calls missing `timeout=`, bare `except Exception:` without guardian comments, or `pytest.mark.skip` without `strict=True`.
5. **Dimension 5 — Governance Conformance Map Synchronization**: Verify every rule, hook, and validator referenced in `AGENTS.md` and `.agents/rules/conformance-map.md` exists on disk, and `AGENTS.md` remains $\le 200$ lines.
6. **Dimension 6 — Sidecar Separation Integrity**: Run `python3 tools/validate_sidecar_separation.py --json`.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the following bounded AST and linter sweep in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
python3 tools/lint_layer_imports.py
python3 tools/lint_architecture_boundaries.py
python3 tools/lint_model_neutral_naming.py
python3 tools/validate_sidecar_separation.py --json
python3 - <<'PY'
import ast, json
from pathlib import Path

root = Path("/Users/amitayer/Git/agents")
targets = ["outreach_engine", "resume_engine", "resume_graph_engine", "apps_research", "apps_lic", "apps_rg", "infrastructure"]
violations = []
for d in targets:
    base = root / d
    if not base.exists():
        continue
    for py in base.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if d in ("outreach_engine", "apps_lic") and node.module.startswith(("resume_engine", "resume_graph_engine", "apps_rg")):
                    violations.append({"file": str(py.relative_to(root)), "line": node.lineno, "illegal_import": node.module})
                elif d in ("resume_engine", "resume_graph_engine", "apps_rg") and node.module.startswith(("outreach_engine", "apps_lic")):
                    violations.append({"file": str(py.relative_to(root)), "line": node.lineno, "illegal_import": node.module})

print(json.dumps({"cross_subsystem_violations": violations, "agents_md_lines": len((root / "AGENTS.md").read_text().splitlines())}, indent=2))
PY
```

Write the structured findings to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Subsystem Boundary & Layer Import Remediation`
- `## Wave 2: Model Registry, Constitutional Floor & Conformance Map Sync`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/ssot-boundary-remediation-${HEX6}.md"
cp "plans/ssot-boundary-remediation-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 dimensions.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` linter/AST violations.
   - Apply bounded boundary/SSOT fixes.
   - Run `POST_MUTATION_RUN` linters and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`):
     `/Users/amitayer/Git/agents/.venv/bin/pytest tests/test_model_neutral_naming.py -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record outcome in `HITLDecisionStore`.
3. **Turn & Commit Gates (`C09`, `C10`)**:
   Run `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py`, then commit, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
