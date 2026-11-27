---
name: loophole-redteam-assurance
description: Orchestrate four read-only adversarial red-team subagents and counterfactual mutation scanning to detect reachable production mocks, tautological tests, fake scanners, and agent governance bypasses.
---

# Loophole & Anti-BS Red-Team Assurance

Run an independent, read-only 4-agent adversarial audit across the `agents` repository's 7 on-demand assurance agents, core runtime agents, deterministic scanners, and 6 test roots without interfering with MECE single-writer leases (`INV-PARALLEL-AGENT-MECE-ISOLATION`).

## 1. Four Specialized Read-Only Red-Team Roles

1. **`redteam-r1-mock-hunter` (Mock, Stub & Canned-Fallback Hunter)**: Scans all 11 production roots for simulated default adapters (`simulated_default`, `simulated-v1`), `hasattr(..., "mock_calls")` production escape hatches, unguarded `mode == "mocked"` branches, and canned `SUCCESS` fallbacks.
2. **`redteam-r2-fake-test-hunter` (Fake-Test, Tautology & Fake-Coverage Hunter)**: Scans all 6 test roots and `tools/testing_gaps_auditor.py` for `assert True`, self-comparisons (`assert x == x`), pass-or-fail exit assertions (`returncode in (0, 1)`), mocked `*_e2e*` / `*live_llm*` masquerades, and flat AST name-collision coverage inflation.
3. **`redteam-r3-fake-scan-hunter` (Fake-Scan, Dead-Flag & Guard-Theater Hunter)**: Audits `tools/` linters and `apps_eval/construct_validity.py` for unwired AST flags, dead reverse-importer expansion, `except SyntaxError: return []` swallows, comment-bypassable fixture checks, and unregistered `# guardian:` tags against `config/governance/guardian_exemption_registry.yaml`.
4. **`redteam-r4-agent-bypass-hunter` (Agent-Prompt, Sandbox & Gate-Bypass Hunter)**: Audits `automations/prompts/agents_*_agent.md`, `tools/run_eval_flywheel_cycle.py`, `tools/verify_main_readiness.py`, and `agents/orchestration/services/` for `--sandbox` cooldown/drift skips, `chore/` branch test-pinning bypasses, deleted-stage `"Optional suite not present" -> PASS` fallbacks, fail-open ambiguity fallbacks, and post-LLM regex prose mutators.

## 2. Canonical 10-Field Read-Only Delegation Contracts

Each red-team worker executes under strict read-only tools (`read_file`, `run_command`) and returns `{"task_id", "status", "deliverable", "evidence_refs", "metrics"}`:

```json
{
  "task_id": "redteam-r1-mock-hunter",
  "parent_task_id": "loophole-redteam-coordinator",
  "objective": "Audit all 11 production roots for reachable simulated adapters, mock escape hatches, and canned SUCCESS fallbacks.",
  "scope_in": [
    "agents/",
    "apps_eval/",
    "apps_research/",
    "infrastructure/",
    "outreach_engine/",
    "resume_engine/",
    "resume_graph_engine/"
  ],
  "scope_out": [
    "No tracked file edits",
    "No external repository access"
  ],
  "allowed_tools": [
    "read_file",
    "run_command"
  ],
  "deliverable": {
    "format": "JSON",
    "target_path": "artifacts/governance/redteam_r1_mock_findings.json"
  },
  "definition_of_done": "Every R1 finding includes file, line, loophole_id, and counterfactual reproduction proof.",
  "budget": {
    "max_turns": 8,
    "max_tool_calls": 20,
    "timeout_seconds": 180
  },
  "escalation_rule": "Escalate to coordinator if confidence margin between real loophole and legitimate test seam is <= 20%."
}
```

```json
{
  "task_id": "redteam-r2-fake-test-hunter",
  "parent_task_id": "loophole-redteam-coordinator",
  "objective": "Audit all 6 test roots and testing-gap coverage logic for tautologies, pass-or-fail checks, mocked E2E masquerades, and name-collision coverage.",
  "scope_in": [
    "tests/",
    "resume_graph_engine/tests/",
    "outreach_engine/tests/",
    "apps_eval/tests/",
    "tools/testing_gaps_auditor.py"
  ],
  "scope_out": [
    "No tracked file edits",
    "No external repository access"
  ],
  "allowed_tools": [
    "read_file",
    "run_command"
  ],
  "deliverable": {
    "format": "JSON",
    "target_path": "artifacts/governance/redteam_r2_fake_test_findings.json"
  },
  "definition_of_done": "All tautological assertions, mocked high-assurance suites, and fake-coverage paths are cataloged with exact line references.",
  "budget": {
    "max_turns": 8,
    "max_tool_calls": 20,
    "timeout_seconds": 180
  },
  "escalation_rule": "Escalate to coordinator when a mock-guard unit test requires reclassification rather than deletion."
}
```

```json
{
  "task_id": "redteam-r3-fake-scan-hunter",
  "parent_task_id": "loophole-redteam-coordinator",
  "objective": "Audit deterministic linters, construct-validity scanners, and guardian exemptions using counterfactual fault injection.",
  "scope_in": [
    "tools/",
    "apps_eval/construct_validity.py",
    "config/governance/guardian_exemption_registry.yaml"
  ],
  "scope_out": [
    "No tracked file edits",
    "No external repository access"
  ],
  "allowed_tools": [
    "read_file",
    "run_command"
  ],
  "deliverable": {
    "format": "JSON",
    "target_path": "artifacts/governance/redteam_r3_fake_scan_findings.json"
  },
  "definition_of_done": "Counterfactual self-test proves 12/12 planted defects fail closed and clean controls yield 0 false positives.",
  "budget": {
    "max_turns": 8,
    "max_tool_calls": 20,
    "timeout_seconds": 180
  },
  "escalation_rule": "Escalate to coordinator if any scanner exemption ceiling requires policy registry sign-off."
}
```

```json
{
  "task_id": "redteam-r4-agent-bypass-hunter",
  "parent_task_id": "loophole-redteam-coordinator",
  "objective": "Audit the 7 on-demand assurance agents, flywheel sandbox preflights, readiness gates, and runtime prose/precedent guards for bypass loopholes.",
  "scope_in": [
    "automations/prompts/",
    "agents/orchestration/services/",
    "agents/context/precedent_bridge.py",
    "tools/verify_main_readiness.py",
    "tools/run_eval_flywheel_cycle.py"
  ],
  "scope_out": [
    "No tracked file edits",
    "No external repository access"
  ],
  "allowed_tools": [
    "read_file",
    "run_command"
  ],
  "deliverable": {
    "format": "JSON",
    "target_path": "artifacts/governance/redteam_r4_agent_bypass_findings.json"
  },
  "definition_of_done": "All prompt, sandbox, branch-prefix, and readiness-receipt bypass vectors are documented with remediation wave targets.",
  "budget": {
    "max_turns": 8,
    "max_tool_calls": 20,
    "timeout_seconds": 180
  },
  "escalation_rule": "Escalate to coordinator if closing a gate bypass conflicts with an active readiness lane definition."
}
```

## 3. Deterministic Execution & Counterfactual Verification

```bash
.venv/bin/python tools/loophole_redteam_auditor.py --counterfactual-self-test --json
.venv/bin/python tools/loophole_redteam_auditor.py --audit-repo --json
.venv/bin/python tools/validate_sidecar_separation.py --json
.venv/bin/python tools/audit_skills_budget.py --json
```
