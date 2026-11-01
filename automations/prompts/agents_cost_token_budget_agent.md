# Agents Repository — Cost, Token Budget & Provider Routing Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-A (Order 6/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Cost, Token Budget, Prompt Caching, and Provider Routing Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:45 ET`, Order `6/7`). This agent audits token consumption, prompt prefix caching, retry amplification, context compaction, and model tier routing across `outreach_engine/` (`apps_lic`), `resume_engine/` + `resume_graph_engine/` (`apps_rg`), `apps_research/`, `infrastructure/`, and `config/provider_profiles.yaml`.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Token budgets, prompt prefix cache ordering, retry backoff caps, context compaction thresholds, model tier routing (`config/provider_profiles.yaml`), and $\text{ROI} \ge 2.5\times$ economic efficiency gates.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), E2E functional handoffs (`agents-outreach-resume-functionality`), retrieval recall (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Mandatory $\text{ROI} \ge 2.5\times$ Admission Gate**: Every candidate tokenomics remediation must prove:
  $$\text{ROI} = \frac{\text{Expected Token Savings} \times \text{Quality Preservation Factor}}{\text{Implementation Complexity Cost}} \ge 2.5$$
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_cost_token_budget/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` with zero code mutations.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-cost-token-budget-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
python3 "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar Tokenomics Audit & Executable Forensic Scanners

### Phase 1: 6-Pillar Cost & Token Budget Audit
1. **Pillar 1 — Provider Profile & Model Pin Conformance**: Verify all LLM invocations across `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, and `infrastructure/` resolve to canonical profiles in `config/provider_profiles.yaml` with zero hardcoded model literals.
2. **Pillar 2 — Prompt Prefix Cache Ordering**: Verify static system instructions and schema definitions precede dynamic recipient or resume payloads so provider prefix caching achieves maximum hit rates.
3. **Pillar 3 — `apps_research` Context Compaction & Payload Caps**: Audit `apps_research` dossier payloads passed into `outreach_engine` and `resume_engine` for unbounded raw HTML/text dumps missing `max_tokens` or snippet truncation caps.
4. **Pillar 4 — Retry Amplification & Timeout Bounds**: Detect LLM call loops or retry decorators with `max_retries > 3` or missing per-call timeouts.
5. **Pillar 5 — Duplicate Research & Embedding Deduplication**: Identify redundant LLM or embedding calls on identical company/role inputs within a single run.
6. **Pillar 6 — Output Token Ceiling & Schema Compactness**: Ensure structured generation calls declare explicit `max_output_tokens` / `max_tokens` caps.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the following bounded tokenomics and provider registry scanner in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
python3 tools/lint_model_neutral_naming.py
python3 - <<'PY'
import ast, json
from pathlib import Path

root = Path("/Users/amitayer/Git/agents")
surfaces = ["outreach_engine", "resume_engine", "resume_graph_engine", "apps_research", "infrastructure"]
unbounded_calls = []

for s in surfaces:
    base = root / s
    if not base.exists():
        continue
    for py in base.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                if func_name in ("generate", "complete", "chat", "create"):
                    kw_names = {kw.arg for kw in node.keywords if kw.arg}
                    if not kw_names.intersection({"max_tokens", "max_output_tokens", "timeout"}):
                        unbounded_calls.append({"file": str(py.relative_to(root)), "line": node.lineno, "call": func_name})

print(json.dumps({"provider_profiles_exists": (root / "config/provider_profiles.yaml").exists(), "unbounded_llm_call_candidates": unbounded_calls[:25]}, indent=2))
PY
```

Write the structured findings and $\text{ROI} \ge 2.5\times$ calculations to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Provider Profile Conformance & Explicit Token Budget Caps`
- `## Wave 2: Research Payload Compaction & Prompt Prefix Cache Optimization`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/cost-token-budget-${HEX6}.md"
cp "plans/cost-token-budget-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 tokenomics pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` token budget / model registry metric before edit.
   - Apply bounded tokenomics remediation with $\text{ROI} \ge 2.5\times$.
   - Run `POST_MUTATION_RUN` `python3 tools/lint_model_neutral_naming.py` and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn & Commit Gates (`C09`, `C10`)**:
   Run `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py`, then commit, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
