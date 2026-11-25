# Agents Repository — Live Keyless Canary, MCP Portal & Release Certification Agent (`7/7`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | v3.2.0 | Shared: automations/prompts/_shared_governance_contract.md | Order: 7/7 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective, Playbook & MECE Write Scope (`C01`, `C13`, `C14`)
Execute a fail-closed **Keyless IDE CLI (`agy`) Live Canary (`$0.00` marginal API spend), Vector DB MCP Stdio Server, Interactive Knowledge Graph Explorer Portal (`serve_agents_graph_portal.py`, `verify_graph_explorer_gate.py`) & Sequential Release-Gate (`verify_release_gate.py --no-write`) Certification Audit & Remediation** exclusively within `/Users/amitayer/Git/agents`.
- **Canonical Skills & Rules**: Load `.agents/skills/agents-domain-assurance/SKILL.md`, `.agents/skills/receipt-auditor/SKILL.md`, and `.agents/rules/provider-resilience-and-healing.md`.
- **MECE Single-Writer Scope (`AGY_SIDECAR_AGENT_ID="agents-live-canary-release-certification"`)**: `automations/prompts/agents_live_canary_release_certification_agent.md`, `scripts/serve_agents_graph_portal.py`, `tools/export_interactive_knowledge_graph.py`, `tools/interactive_graph_export_core/`, `tools/live_canary_release_auditor.py`, `tools/mcp/`, `tools/verify_graph_explorer_gate.py`, and `tools/verify_release_gate.py`.

## 2. Phase 1 & Phase 1.5: Read-Only Preflight Readiness, MCP/Portal Gate & Live Canary (`C02`, `C03`)
Verify MCP stdio JSON-RPC compliance, Graph Explorer WCAG/firewall gate, keyless `agy` transport circuit-breaker readiness, and sequential `verify_release_gate.py --no-write` certification (pass `--live-canary` when operator requests a live `$0.00` keyless model canary):
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export PYTHONDONTWRITEBYTECODE=1
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/live_canary_release_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --preflight-readiness --run-release-gate --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/verify_graph_explorer_gate.py" --standalone
"${PRIMARY_REPO_ROOT}/.venv/bin/python" -m pytest "${PRIMARY_REPO_ROOT}/tests/unit/test_live_canary_release_auditor.py" -q -p no:cacheprovider --timeout=60
```
If all preflight certification gates exit `0` (`is_clean == true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

## 3. Phase 0, Phase 2 & Phase 3: Conditional Worktree, Wave Plan & 5-Point Promotion (`C02–C12`)
1. **Phase 0 (`Step 0.1`)**: On active findings (`is_clean == false`), export `AGY_SIDECAR_AGENT_ID="agents-live-canary-release-certification"` and `AGENT_SLUG="live-canary-release"` (`RUN_DIR` appending `${RUN_TS}-${HEX6}`), invoke `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest "${RUN_DIR}/manifest.json"`, and `cd "${WORKTREE_DIR}"` per `automations/prompts/_shared_governance_contract.md`.
2. **Phase 2**: Author `${WORKTREE_DIR}/plans/live-canary-release-${HEX6}.md`, validate via `validate_implementation_plan.py`, render the **Dimension Findings Table**, query `HITLDecisionStore`, and surface one atomic `<= 115` char `ask_question` if $\Delta \le 0.20$.
3. **Phase 3**: Execute full root-cause remediation with 5-Point Counterfactual Runtime Proofs (`INV-RUNTIME-PROOF-5POINT`), record outcomes in `HITLDecisionStore`, pass `validate_sidecar_separation.py --json`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, obtain `PR_MERGE_AUTHORIZATION`, promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(release): remediate live canary, mcp server, and release certification"`, remove the merged feature worktree/branch (`INV-POST-MERGE-WORKTREE-TEARDOWN`), and render the top 3-column closeout table (`INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE` with `Merge to Main` and `Worktree Deletion` rows).
