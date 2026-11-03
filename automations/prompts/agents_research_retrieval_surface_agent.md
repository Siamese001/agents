# Agents Repository — Research & Retrieval Surface Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-B (Order 4/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Research, Embedding & Retrieval Surface Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:15 ET`, Order `4/7`). This agent audits and remediates evidence chunking, hybrid retrieval ranking (lexical BM25 + BGE-M3 dense vector + 3-hop SQLite graph traversal), source provenance binding, and prompt/retrieval cache parity across `apps_research/`, `resume_graph_engine/`, and `agents/context/` so downstream `outreach_engine` and `resume_engine` synthesis operate on citation-grounded evidence.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: `apps_research/` query expansion, chunking boundaries, ranking/reranking pipelines, `resume_graph_engine/` graph node/edge/BGE-M3 embedding verification (`verify_graph_integrity_and_embeddings.py`), prompt/pipeline cache slot alignment (`verify_pipeline_latency_caching.py`), and retrieval cache invalidation parity.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), downstream outreach/resume synthesis orchestration (`agents-outreach-resume-functionality`), judge rubrics (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and pytest suite gaps (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Zero-Defect Fast-Exit & Wave-Based Plan Mandate (`C03`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports `0` actionable findings, fast-exit cleanly per `C03`: copy `${RUN_DIR}` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}`, tear down the ephemeral worktree via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only`, and exit `COMPLETE` without authoring a synthetic plan.
  - Whenever `>= 1` findings exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` (`exit code 0`).
  - In `MODE: scheduled`, stage validated fixes on `${BRANCH_NAME}` via `pr_governance.py submit "${BRANCH_NAME}" --stage-only` without mutating `local main` directly.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-research-retrieval-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 7-Pillar Retrieval Audit & Executable Forensic Scanners

### Phase 1: 7-Pillar Research & Retrieval Surface Audit
1. **Pillar 1 — Query Decomposition & Intent Routing (`apps_research`, `ResearchRetrievalEngine`, `GovernedResearchRun`)**: Verify prospect/company research queries and role-target queries executed through `ResearchRetrievalEngine` and `GovernedResearchRun` decompose deterministically without dropping entity constraints.
2. **Pillar 2 — Document Chunking & Context Window Preservation (`AppsResearchBridge`, `agents/context/`)**: Audit chunk overlap, header preservation, and metadata attachment across `apps_research/`, `agents/context/`, and `AppsResearchBridge` handoff packets.
3. **Pillar 3 — Hybrid Ranking, BGE-M3 Embeddings & Graph Traversal (`resume_graph_engine`)**: Run `tools/verify_graph_integrity_and_embeddings.py` and `tools/run_resume_graph_traversal_probe.py` to verify 1024-dim L2-normalized BGE-M3 vectors, 3-hop acyclic paths, and Stage-2 metric boost fusion.
4. **Pillar 4 — Citation & Provenance Binding**: Ensure every retrieved research snippet and resume graph assertion carries a verifiable source identifier (`source_id`, `doc_hash`, or `node_id`) into `outreach_engine` and `resume_engine`.
5. **Pillar 5 — Empty-Result & Low-Confidence Fail-Closed Gates**: Verify retrieval and delegation bridges across both `resume_graph_engine` (`dispatch_resume_research_briefing`) and `outreach_engine` (`dispatch_outreach_research_briefing`) explicitly fail closed on low-confidence or zero-hit queries rather than fabricating fallback claims.
6. **Pillar 6 — Retrieval & Prompt Cache Slot Alignment**: Run `tools/verify_pipeline_latency_caching.py` to verify static prefix thresholds and compiler slot ordering (`R0`, `E0` before dynamic `C0`).
7. **Pillar 7 — Cross-Subsystem Contract Alignment**: Verify `apps_research` output schemas (`apps_rg` and `apps_lic` profiles) and public return-type annotations across `agents/`, `apps_research/`, `resume_graph_engine/`, `outreach_engine/`, `resume_engine/`, and `infrastructure/` without filename-regex exclusions.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the fail-closed 7-pillar behavioral retrieval auditor, BGE-M3 embedding check, multi-hop graph probe (`python3 tools/run_resume_graph_traversal_probe.py` verifying `direct_graph_traversal`), and live latency-caching verifier in `${WORKTREE_DIR}` (`timeout <= 120s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/retrieval_surface_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --read-only \
  --output "${RUN_DIR}/audit_report.json" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_graph_integrity_and_embeddings.py"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/run_resume_graph_traversal_probe.py" --max-paths 200
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_pipeline_latency_caching.py" --repo-root "${WORKTREE_DIR}"
```

Write the combined structured findings to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist, author `${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Research Retrieval Ranking, Provenance & Chunking Remediation`
- `## Wave 2: Resume Graph Traversal & Cache Invalidation Parity`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 7 retrieval pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}`, then stage verified fixes (or prune 0-commit runs) via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` retrieval/provenance metric before edit.
   - Apply bounded fixes in `apps_research/`, `agents/context/`, or `resume_graph_engine/`.
   - Run `POST_MUTATION_RUN` entrypoint verification and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or promote after interactive `ask_question` `PR_MERGE_AUTHORIZATION` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(retrieval): remediate research and resume retrieval surface"`.
