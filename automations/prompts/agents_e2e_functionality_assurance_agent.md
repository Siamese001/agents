# Agents Repository — Outreach & Resume End-to-End Functionality Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-A (Order 3/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Outreach (`outreach_engine/` / `apps_lic`), Resume (`resume_engine/` / `resume_graph_engine/` / `apps_rg`), and Research (`apps_research/`) End-to-End Critical Functionality Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:05 ET`, Order `3/7`). This agent verifies that the full pipeline from `apps_research` intelligence packets into `outreach_engine` campaign generation and `resume_graph_engine` role tailoring executes without silent drops, schema breaks, or ungrounded synthesis.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: End-to-end runtime contracts across `apps_research` -> `outreach_engine` (`apps_lic`) and `apps_research` -> `resume_engine` / `resume_graph_engine` (`apps_rg`), state transition integrity, and output schema completeness.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), retrieval ranking/chunking internals (`agents-research-retrieval-surface`), judge rubric calibration (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and unit test coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_e2e_functionality/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` with zero code mutations.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-e2e-functionality-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_e2e_functionality/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
python3 "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar E2E Audit, 8-Field Admission Proof & Executable Scanners

### Phase 1: 6-Pillar End-to-End Functionality Audit
1. **Pillar 1 — `apps_research` -> `outreach_engine` (`apps_lic`) Handoff Integrity (`AppsResearchBridge`, `GovernedResearchRun`)**: Verify research brief schemas, `AppsResearchBridge` / `GovernedResearchRun` handoff contracts, recipient context blocks, and citation fields pass cleanly into outreach campaign generators without dropped keys or silent fallback to empty strings.
2. **Pillar 2 — `apps_research` -> `resume_engine` / `resume_graph_engine` (`apps_rg`) Handoff Integrity (`ResearchRetrievalEngine`)**: Verify role requirements, `ResearchRetrievalEngine` evidence packets, competency graphs, and domain evidence flow into resume graph nodes and tailored bullet synthesis without schema mismatch.
3. **Pillar 3 — Outreach Campaign Generation & Guardrail Gates**: Verify multi-touch outreach sequences enforce personalization ground-truth, compliance constraints, and deterministic serialization.
4. **Pillar 4 — Resume Graph Traversal & Bullet Synthesis**: Verify `resume_graph_engine` DAG traversal, experience node selection, and metric preservation never fabricate ungrounded claims.
5. **Pillar 5 — Error Propagation & Fail-Closed Recovery**: Detect swallowed exceptions, silent `None` returns, or unguarded retries across `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, and `apps_research/`.
6. **Pillar 6 — Production Derivation Integrity**: Run `python3 tools/lint_production_purity.py` to confirm zero golden test fixtures substitute for runtime derivation.

### Mandatory 8-Field E2E Criticality Admission Proof
Every candidate finding MUST include all 8 fields before entering the remediation plan:
1. `subsystem_surface` (`outreach_engine` | `resume_engine` | `resume_graph_engine` | `apps_research`)
2. `e2e_flow_stage` (`research_intake` | `handoff_contract` | `graph_traversal` | `synthesis` | `output_validation`)
3. `file_and_symbol` (`path/to/file.py:line_no:function_name`)
4. `failure_mode` (concrete exception, silent drop, or schema violation)
5. `blast_radius` (downstream callers and user deliverables impacted)
6. `reproduction_command` (deterministic CLI or pytest invocation)
7. `counterfactual_fix_summary` (exact contract or state transition fix)
8. `severity_tier` (`P0_CRITICAL` | `P1_HIGH` | `P2_MEDIUM`)

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the following bounded E2E contract and AST inspection in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
python3 tools/lint_production_purity.py
python3 - <<'PY'
import ast, json
from pathlib import Path

root = Path("/Users/amitayer/Git/agents")
surfaces = ["outreach_engine", "resume_engine", "resume_graph_engine", "apps_research", "apps_lic", "apps_rg"]
summary = {}
silent_returns = []

for s in surfaces:
    base = root / s
    if not base.exists():
        continue
    py_files = list(base.rglob("*.py"))
    summary[s] = len(py_files)
    for py in py_files:
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for child in node.body:
                    if isinstance(child, ast.Return) and (child.value is None or (isinstance(child.value, ast.Constant) and child.value.value in (None, "", {}, []))):
                        silent_returns.append({"surface": s, "file": str(py.relative_to(root)), "line": node.lineno})

print(json.dumps({"surface_file_counts": summary, "silent_except_returns": silent_returns[:25]}, indent=2))
PY
python3 tools/run_resume_graph_traversal_probe.py --max-paths 200
```

Verify that `run_resume_graph_traversal_probe.py` reports `status == "PASS"`, `direct_graph_traversal == true`, and non-zero multi-hop paths across `resume_graph_engine` (`domain -> skill -> evidence` and `skill -> fact -> metric_outcome -> employment -> career_epoch`) in an ephemeral read-only sandbox. Write the structured findings and 8-field admission proofs to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/e2e-outreach-resume-assurance-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Research-to-Outreach & Research-to-Resume Handoff Contract Remediation`
- `## Wave 2: End-to-End Pipeline Synthesis & Fail-Closed Error Handling`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/e2e-outreach-resume-assurance-${HEX6}.md"
cp "plans/e2e-outreach-resume-assurance-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 E2E pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_e2e_functionality/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` failure/contract gap before edit.
   - Apply bounded E2E remediation across `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, or `apps_research/`.
   - Run `POST_MUTATION_RUN` entrypoint verification and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn & Commit Gates (`C09`, `C10`)**:
   Run `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py`, then commit, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
