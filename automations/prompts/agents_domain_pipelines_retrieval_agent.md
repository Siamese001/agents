# Agents Repository — Domain Business Pipelines & Hybrid Retrieval Agent (`3/4`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Order: 3/4 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective, Playbook & MECE Write Scope (`C01`, `C13`)
Execute a holistic Stages 1–4 **Domain Business Pipelines (`outreach_engine`, `resume_engine`, `resume_graph_engine`) & 4-Channel Hybrid Retrieval (`apps_research`) Audit & Remediation** exclusively within `/Users/amitayer/Git/agents`.
- **Canonical Skill**: Load `.agents/skills/agents-domain-assurance/SKILL.md` for full dual-engine and 4-channel hybrid retrieval invariants.
- **MECE Single-Writer Scope (`AGY_SIDECAR_AGENT_ID="agents-domain-pipelines-retrieval"`)**: `apps_research/`, `outreach_engine/src/`, `outreach_engine/tests/`, `resume_engine/`, `resume_graph_engine/src/apps_rg/chunking/`, `resume_graph_engine/src/apps_rg/fact_inventory/`, `resume_graph_engine/src/apps_rg/runtime/`, `resume_graph_engine/src/apps_rg/engines/`, `resume_graph_engine/src/apps_rg/resume/`, `resume_graph_engine/src/apps_rg/prompt_assembly/`, `resume_graph_engine/src/apps_rg/l2_recipe/`, `resume_graph_engine/src/apps_rg/integrations/`, `resume_graph_engine/src/apps_rg/bare_pipeline.py`, `resume_graph_engine/tests/`, `agents/context/precedent_bridge.py`, `agents/context/provenance.py`, `ops_scripts/`, `tools/e2e_functionality_auditor.py`, `tools/retrieval_surface_auditor.py`, `tools/verify_graph_integrity_and_embeddings.py`, `tools/run_resume_graph_traversal_probe.py`, `tools/verify_pipeline_latency_caching.py`, `tests/test_sidecar_resume_graph_traversal.py`, and `tests/unit/test_e2e_and_retrieval_full_parity.py`.

## 2. Phase 1 & Phase 1.5: Read-Only Preflight Audit & Fast-Exit Gate (`C02`, `C03`)
Audit cross-subsystem research handoffs (`AppsResearchBridge`, `GovernedResearchRun`), 4-channel graph hybrid retrieval (`direct_graph_traversal`), BGE-M3 1024-d vectors, graph promotion completeness (`INV-GRAPH-PROMOTION-HYGIENE`), archetype JD-fit bundle alignment (`archetype_jd_fit_alignment_pass`), authoritative smoke, and ECMA-376 `.docx` export in read-only mode first:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export PYTHONDONTWRITEBYTECODE=1
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/e2e_functionality_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --read-only --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/retrieval_surface_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --read-only --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/verify_graph_integrity_and_embeddings.py" --read-only
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/run_resume_graph_traversal_probe.py" --max-paths 200
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/verify_pipeline_latency_caching.py" --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_e2e_and_retrieval_full_parity.py" "${PRIMARY_REPO_ROOT}/tests/test_sidecar_resume_graph_traversal.py" -q -p no:cacheprovider --timeout=60
```
If all preflight gates exit `0` (`is_clean == true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

## 3. Phase 0, Phase 2 & Phase 3: Conditional Worktree, Wave Plan & 5-Point Promotion (`C02–C12`)
1. **Phase 0 (`Step 0.1`)**: On active findings (`is_clean == false`), export `AGY_SIDECAR_AGENT_ID="agents-domain-pipelines-retrieval"` and `AGENT_SLUG="domain-pipelines-retrieval"` (`RUN_DIR` appending `${RUN_TS}-${HEX6}`), invoke `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest "${RUN_DIR}/manifest.json"`, and `cd "${WORKTREE_DIR}"` per `automations/prompts/_shared_governance_contract.md`.
2. **Phase 2**: Author `${WORKTREE_DIR}/plans/domain-pipelines-retrieval-${HEX6}.md` tracing holistic Stages 1–4 spine alignment (`INV-HOLISTIC-PIPELINE-PLANNING`), validate via `validate_implementation_plan.py`, render the **Dimension Findings Table**, query `HITLDecisionStore`, and surface one atomic `<= 115` char `ask_question` if $\Delta \le 0.20$.
3. **Phase 3**: Execute sequential waves with 5-Point Counterfactual Runtime Proofs (`INV-RUNTIME-PROOF-5POINT`), record outcomes in `HITLDecisionStore`, pass `validate_sidecar_separation.py --json`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, obtain `PR_MERGE_AUTHORIZATION`, and promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(pipelines): remediate domain synthesis and hybrid retrieval spine"`.
