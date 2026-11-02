# Agents Repository — Research & Retrieval Surface Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-B (Order 4/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Research & Retrieval Surface Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:15 ET`, Order `4/7`). This agent audits and remediates evidence chunking, hybrid retrieval ranking (lexical + vector/graph), source provenance binding, and cache parity across `apps_research/` and `resume_graph_engine/` so downstream outreach (`outreach_engine`) and resume (`resume_engine`) synthesis operate on high-recall, citation-grounded evidence.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: `apps_research/` query expansion, chunking boundaries, ranking/reranking pipelines, `resume_graph_engine/` graph node/edge evidence retrieval, citation provenance tags, and retrieval cache invalidation parity.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), downstream outreach/resume synthesis orchestration (`agents-outreach-resume-functionality`), judge rubrics (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and pytest suite gaps (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_research_retrieval_surface/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` with zero code mutations.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-research-retrieval-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
python3 "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 7-Pillar Retrieval Audit & Executable Forensic Scanners

### Phase 1: 7-Pillar Research & Retrieval Surface Audit
1. **Pillar 1 — Query Decomposition & Intent Routing (`apps_research`, `ResearchRetrievalEngine`, `GovernedResearchRun`)**: Verify prospect/company research queries and role-target queries executed through `ResearchRetrievalEngine` and `GovernedResearchRun` decompose deterministically without dropping entity constraints.
2. **Pillar 2 — Document Chunking & Context Window Preservation (`AppsResearchBridge`)**: Audit chunk overlap, header preservation, and metadata attachment across `apps_research/` ingestion modules and `AppsResearchBridge` handoff packets.
3. **Pillar 3 — Hybrid Ranking & Graph Traversal (`resume_graph_engine`)**: Verify candidate experience nodes, skill edges, and impact metrics rank deterministically without score NaN or tie-break instability.
4. **Pillar 4 — Citation & Provenance Binding**: Ensure every retrieved research snippet and resume graph assertion carries a verifiable source identifier (`source_id`, `doc_hash`, or `node_id`) into `outreach_engine` and `resume_engine`.
5. **Pillar 5 — Empty-Result & Low-Confidence Fail-Closed Gates**: Verify retrieval modules explicitly flag low-confidence or zero-hit queries rather than fabricating fallback claims.
6. **Pillar 6 — Retrieval Cache & Schema Parity**: Verify cached research packets invalidate cleanly when schema versions or query parameters change.
7. **Pillar 7 — Cross-Subsystem Contract Alignment**: Verify `apps_research` output schemas match consumer expectations in `outreach_engine/` (`apps_lic`) and `resume_engine/` (`apps_rg`).

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the following bounded retrieval surface scanner in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
python3 - <<'PY'
import ast, json
from pathlib import Path

root = Path("/Users/amitayer/Git/agents")
targets = ["apps_research", "resume_graph_engine", "outreach_engine", "resume_engine"]
retrieval_modules = []
untyped_returns = []

for t in targets:
    base = root / t
    if not base.exists():
        continue
    for py in base.rglob("*.py"):
        rel = str(py.relative_to(root))
        if any(k in rel.lower() for k in ("retriev", "search", "graph", "rank", "chunk", "research", "provenance")):
            retrieval_modules.append(rel)
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and node.returns is None:
                    untyped_returns.append({"file": rel, "line": node.lineno, "function": node.name})

print(json.dumps({"retrieval_module_count": len(retrieval_modules), "sample_modules": retrieval_modules[:25], "public_functions_missing_return_annotations": untyped_returns[:25]}, indent=2))
PY
python3 tools/run_resume_graph_traversal_probe.py --max-paths 200
```

Verify that `run_resume_graph_traversal_probe.py` reports `status == "PASS"`, `direct_graph_traversal == true`, and non-zero multi-hop paths (`two_hop_path_count > 0` and `domain_skill_evidence_path_count > 0`) across `resume_graph_engine` and `apps_research` without mutating repository files. Write the combined structured findings to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Research Retrieval Ranking, Provenance & Chunking Remediation`
- `## Wave 2: Resume Graph Traversal & Cache Invalidation Parity`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/research-retrieval-surface-${HEX6}.md"
cp "plans/research-retrieval-surface-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 7 retrieval pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` retrieval/provenance metric before edit.
   - Apply bounded fixes in `apps_research/` or `resume_graph_engine/`.
   - Run `POST_MUTATION_RUN` entrypoint verification and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn & Commit Gates (`C09`, `C10`)**:
   Run `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py`, then commit, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
