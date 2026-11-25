# Agents Repository — Enterprise Research Intelligence, Airlocks & Cross-Engine Handoffs Agent (`6/7`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | v3.2.0 | Shared: automations/prompts/_shared_governance_contract.md | Order: 6/7 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective, Playbook & MECE Write Scope (`C01`, `C13`, `C14`)
Execute a fail-closed **Enterprise Research Intelligence (`apps_research/`), Query Decomposition, Search Fail-Closed Guards, Prompt-Injection Briefing Airlock (`briefing_injection_airlock`), Targeting Brief Provenance/Citation Stripping, and Cross-Subsystem Handoff Contracts (`apps_rg` & `apps_lic`) Audit & Remediation** exclusively within `/Users/amitayer/Git/agents`.
- **Canonical Skills & Rules**: Load `.agents/skills/agents-domain-assurance/SKILL.md`, `.agents/rules/apps-research.md`, and `.agents/rules/production-derivation-and-anti-overfitting.md`.
- **MECE Single-Writer Scope (`AGY_SIDECAR_AGENT_ID="agents-research-intelligence-handoff"`)**: `apps_research/`, `automations/prompts/agents_research_intelligence_handoff_agent.md`, `tools/apps_research_auditor.py`, `tests/test_governed_research_lineage.py`, `tests/test_research_boundary_policy.py`, and `tests/test_research_retrieval_engine.py`.

## 2. Phase 1 & Phase 1.5: Read-Only Preflight Audit & Fast-Exit Gate (`C02`, `C03`)
Audit all 6 `apps_research` intelligence pillars (upstream `query_decomposer` & `jd_intent_coverage`, `search_retrieval`/`tavily_retrieval` fail-closed guards, `briefing_injection_airlock` sanitization, `apps_rg_targeting_brief_contract` URL/citation/placeholder stripping, `model_pins` & `domain_contract/*.yaml` integrity, and dual `apps_rg`/`apps_lic` handoff delegation + AST exception hygiene) in read-only mode first:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export PYTHONDONTWRITEBYTECODE=1
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/apps_research_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --read-only --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" -m pytest "${PRIMARY_REPO_ROOT}/tests/test_research_retrieval_engine.py" "${PRIMARY_REPO_ROOT}/tests/test_governed_research_lineage.py" "${PRIMARY_REPO_ROOT}/tests/test_research_boundary_policy.py" -q -p no:cacheprovider --timeout=60
```
If all preflight gates exit `0` (`is_clean == true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

## 3. Phase 0, Phase 2 & Phase 3: Conditional Worktree, Wave Plan & 5-Point Promotion (`C02–C12`)
1. **Phase 0 (`Step 0.1`)**: On active findings (`is_clean == false`), export `AGY_SIDECAR_AGENT_ID="agents-research-intelligence-handoff"` and `AGENT_SLUG="research-intelligence-handoff"` (`RUN_DIR` appending `${RUN_TS}-${HEX6}`), invoke `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest "${RUN_DIR}/manifest.json"`, and `cd "${WORKTREE_DIR}"` per `automations/prompts/_shared_governance_contract.md`.
2. **Phase 2**: Author `${WORKTREE_DIR}/plans/research-intelligence-handoff-${HEX6}.md` aligning upstream retrieval, intermediate `company_brief_engine` assembly, and downstream `apps_rg`/`apps_lic` handoff validators, validate via `validate_implementation_plan.py`, render the **Dimension Findings Table**, query `HITLDecisionStore`, and surface one atomic `<= 115` char `ask_question` if $\Delta \le 0.20$.
3. **Phase 3**: Execute full root-cause remediation across all owned findings with 5-Point Counterfactual Runtime Proofs (`INV-RUNTIME-PROOF-5POINT`), record outcomes in `HITLDecisionStore`, pass `validate_sidecar_separation.py --json`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, obtain `PR_MERGE_AUTHORIZATION`, promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(research): remediate research airlocks and cross-engine handoffs"`, remove the merged feature worktree/branch (`INV-POST-MERGE-WORKTREE-TEARDOWN`), and render the top 3-column closeout table (`INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE` with `Merge to Main` and `Worktree Deletion` rows).
