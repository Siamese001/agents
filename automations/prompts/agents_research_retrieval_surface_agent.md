# Agents Repository — Research & Retrieval Surface Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-C (Order 5/8) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Research, Embedding & Retrieval Surface Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `5/8`). This agent audits and remediates evidence chunking, hybrid retrieval ranking (lexical BM25 + BGE-M3 dense vector + 3-hop SQLite graph traversal), source provenance binding, and prompt/retrieval cache parity across `apps_research/`, `resume_graph_engine/`, and `agents/context/` so downstream `outreach_engine` and `resume_engine` synthesis operate on citation-grounded evidence.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: `apps_research/` query expansion, chunking boundaries, ranking/reranking pipelines, `resume_graph_engine/` graph node/edge/BGE-M3 embedding verification (`verify_graph_integrity_and_embeddings.py`), prompt/pipeline cache slot alignment (`verify_pipeline_latency_caching.py`), and retrieval cache invalidation parity.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), core agent runtime mechanics (`agents-core-runtime-orchestration`), downstream outreach/resume synthesis orchestration (`agents-domain-applications-pipeline`), judge rubrics (`agents-evals-judge-assurance`), token economics & local hardware (`agents-cost-token-budget`), and pytest suite gaps & credential security (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When `0` actionable findings exist (`is_clean: true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or authoring a synthetic plan.
  - Whenever `>= 1` findings exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 7-Pillar Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 7-Pillar Research & Retrieval Surface Audit
1. **Pillar 1 — Query Decomposition, Multi-Query Ranking & Source Recommendations (`apps_research`, `ResearchRetrievalEngine`, `GovernedResearchRun`)**: Execute live `ResearchRetrievalEngine` multi-query ranking, `recommend_sources`, and benchmark probes alongside `GovernedResearchRun` to verify deterministic ranking without dropping entity constraints.
2. **Pillar 2 — Document Chunking & Context Window Preservation (`AppsResearchBridge`, `agents/context/`)**: Audit chunk overlap, header preservation, and metadata attachment across `apps_research/`, `agents/context/`, and `AppsResearchBridge` handoff packets.
3. **Pillar 3 — Hybrid Ranking, BGE-M3 Embeddings & Graph Traversal (`resume_graph_engine`)**: Run `tools/verify_graph_integrity_and_embeddings.py` and `python3 tools/run_resume_graph_traversal_probe.py` (`direct_graph_traversal`) to verify 1024-dim L2-normalized BGE-M3 vectors, 3-hop acyclic paths, and Stage-2 metric boost fusion.
4. **Pillar 4 — Citation & Provenance Binding**: Ensure every retrieved research snippet and resume graph assertion carries a verifiable source identifier (`source_id`, `doc_hash`, or `node_id`) into `outreach_engine` and `resume_engine`.
5. **Pillar 5 — Empty-Result & Low-Confidence Fail-Closed Gates**: Verify retrieval and delegation bridges across both `resume_graph_engine` (`dispatch_resume_research_briefing`) and `outreach_engine` (`dispatch_outreach_research_briefing`) explicitly fail closed on low-confidence or zero-hit queries rather than fabricating fallback claims.
6. **Pillar 6 — Retrieval & Prompt Cache Slot Alignment**: Run `tools/verify_pipeline_latency_caching.py` to verify static prefix thresholds and compiler slot ordering (`R0`, `E0` before dynamic `C0`).
7. **Pillar 7 — 11-Root Return-Type & Cross-Subsystem Contract Alignment**: Verify `apps_research` output schemas (`apps_rg` and `apps_lic` profiles) and public return-type annotations across all 11 executable roots (`agents/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `resume_graph_engine/`, `outreach_engine/`, `resume_engine/`, `infrastructure/`, `ops_scripts/`, `scripts/`, and `tools/`) without filename-regex exclusions.

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanners
Execute the fail-closed 7-pillar behavioral retrieval auditor, BGE-M3 embedding check, multi-hop graph probe, live latency-caching verifier, and scoped unit suite in read-only mode (`timeout <= 120s`):

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/retrieval_surface_auditor.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --read-only \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/verify_graph_integrity_and_embeddings.py"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/run_resume_graph_traversal_probe.py" --max-paths 200
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/verify_pipeline_latency_caching.py" --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_e2e_and_retrieval_full_parity.py" "${PRIMARY_REPO_ROOT}/outreach_engine/tests/test_research_governance_truth.py" -q --timeout=60
```

If all preflight commands exit `0` (`"status": "PASS"`, `"is_clean": true`), fast-exit `COMPLETE` (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision an isolated worktree, write `manifest.json` via `--write-manifest`, and switch into `${WORKTREE_DIR}`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-research-retrieval-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_research_retrieval_surface/${RUN_TS}"
export PLAN_REL="plans/research-retrieval-surface-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-research-retrieval-surface" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/retrieval_surface_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --read-only \
  --output "${RUN_DIR}/audit_report.json" \
  --json || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/research-retrieval-surface-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
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
- Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

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
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, and either stage overnight via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(retrieval): remediate research and resume retrieval surface"`.
