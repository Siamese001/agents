---
name: agent-subagent-orchestration
description: Unified Architecture orchestration patterns across Skills, Agents, Sub-Agents, Hooks, and Rules. Covers goal decomposition, contract delegation, state memory, and 7-step lifecycle validation.
---

# Agent & Sub-Agent Orchestration Architecture

This skill provides practical guidance and operational patterns for coordinating
workflows under the **Unified Architecture for Skills, Agents, Sub-Agents, Hooks,
and Rules** (`AGENTS.md` and `.agents/rules/unified-agent-architecture.md`).

## 1. When to Use This Skill

- Orchestrating complex, multi-stage workflows across specialized capabilities.
- Decomposing an open-ended goal into bounded subtasks with isolated contexts.
- Formulating binding delegation contracts when spawning or assigning sub-agents.
- Registering non-intrusive event hooks for logging, metrics, caching, or moderation.
- Enforcing governance rules, pre-conditions, and post-conditions before and after execution.

---

## 2. Architecture & Lifecycle SSOT

The conceptual foundation and execution lifecycle are canonically defined in:
- [`.agents/rules/unified-agent-architecture.md`](file:///Users/amitayer/Git/agents/.agents/rules/unified-agent-architecture.md) (The Five Pillars, Shared Foundations, 10-field Delegation Protocol, 7-Step Lifecycle, and Sub-Agent Teardown Contract)
- [`AGENTS.md`](file:///Users/amitayer/Git/agents/AGENTS.md)
- [`tools/unified_agent_architecture.py`](file:///Users/amitayer/Git/agents/tools/unified_agent_architecture.py) (Mandatory Delegation & Structured Return Validators)

This skill provides practical delegation templates, return schemas, and hook interception code patterns.

---

## 4. Sub-Agent Delegation Contract Template

When delegating work to a sub-agent, use this canonical JSON structure:

```json
{
  "task_id": "task_sub_extract_001",
  "parent_task_id": "task_root_orchestrator_001",
  "objective": "Extract and normalize entities from meeting transcript section 04:00 - 12:00",
  "scope_in": [
    "output/project_nexus/09-10-2026/01_hitl_resolved_transcript.md"
  ],
  "scope_out": [
    "No external network calls",
    "No direct graph mutations"
  ],
  "allowed_tools": [
    "view_file",
    "edit_file",
    "run_command"
  ],
  "deliverable": {
    "schema": "urn:nee:dual-pipeline:evidence-envelope-intake:1.0.0",
    "format": "JSON",
    "target_path": "output/project_nexus/09-10-2026/03_canonical_signal_projection.json"
  },
  "definition_of_done": "All candidate entities validate against W2 Semantic Spine allowlist without schema errors.",
  "budget": {
    "max_turns": 5,
    "max_tool_calls": 12,
    "timeout_seconds": 180
  },
  "escalation_rule": "Escalate to parent if confidence margin between top two entity merge candidates satisfies needs_operator_decision (<= 20% inclusive)."
}
```

### Upstream Return Template

Sub-agents must report back to the parent agent using this structure:

```json
{
  "task_id": "task_sub_extract_001",
  "status": "SUCCESS",
  "deliverable": {
    "extracted_entities_count": 8,
    "normalized_nodes": ["person:marcus_balk", "org:slalom"]
  },
  "evidence_refs": [
    "01_hitl_resolved_transcript.md#L45-L68"
  ],
  "metrics": {
    "tool_calls_used": 4,
    "elapsed_seconds": 18.2,
    "remaining_turns": 4
  }
}
```

---

## 5. Non-Intrusive Hook Extension Protocol

Hooks intercept execution around actions without altering core logic:

```python
# Conceptual Pre/Post/Around Hook Interception
def execute_with_hooks(action, context):
    # 1. Trigger PRE Hooks (guardrails, cache checks, authentication)
    trigger_hooks(timing="PRE", context=context)
    
    # 2. Execute Core Logic
    result = action(context)
    
    # 3. Trigger POST Hooks (metrics, logging, notifications, audit events)
    trigger_hooks(timing="POST", context=context, result=result)
    
    return result
```

- **Pre-Hooks**: Abort or block execution if preconditions or safety checks fail.
- **Post-Hooks**: Capture telemetry, update caches, and log audit receipts.
- **Around-Hooks**: Measure end-to-end latency, enforce timeouts, and record resource consumption.

---

## 6. A2A Rationalization Boundaries & Canonical Dispatch Invariants

1. **Authoritative Sub-Agent Delegation & Protocol Enforcement**:
   - All internal multi-agent fan-out and sub-agent task dispatch must adhere strictly to the 10-field contract validated by [`tools/unified_agent_architecture.py`](file:///Users/amitayer/Git/agents/tools/unified_agent_architecture.py) and persist state transitions (`SUBMITTED -> ACCEPTED -> WORKING -> COMPLETED/FAILED`).
   - Post-hoc `executor_fn=None` telemetry stubs are prohibited when a coordinator broker is bound.
2. **Where A2A Multi-Angle Reasoning is Required**:
   - Pre-verdict dialectical decision deliberation (`RedTeamRiskAgent`, `StrategicFeasibilityAgent`, `CounterfactualDevilAdvocateAgent`, and all 18 roles from `CANONICAL_18_ROLES` in Round 1 with focused dissenting-role Round 2 rebuttal).
   - Multi-angle constraint-mutation negotiation when all human-proposed options fail hard constraints (`option_synthesizer.py`).
   - Multi-perspective query decomposition and starved-perspective graph re-query (`RetrievalCoordinator` + `RetrievalPerspectiveHealerAgent` + `MultiHopQueryNavigatorAgent`).
   - Compute-forked extraction (`CLIENT_SAFE` vs. default `INTERNAL_ADVISORY` in `ExtractionCoordinator`).
3. **Where A2A is Strictly Prohibited**:
   - Sub-millisecond (`< 1.0ms`) warm query routing and `FastPathSyncAgent` (`concurrency-and-storage-safety.md` §3).
   - Deterministic `U0/L1/L0/C0` normalization, `UniversalWriteGateway` / `GovernedGraphWriter.apply`, and the 5 physical SQLite checks (`trust_scope="packet_integrity_only"`).
   - Pre-egress sanitization (`LocalPreEgressSanitizer`) and `ComputePosture` barrier enforcement.

---

## 7. Multi-Agent Sharded Wave & Merge-Train Playbook

When executing broad multi-file refactors across `/swarm`, `/teamwork`, or `run_workflow`:

1. **Fork-Join Wave Plan & `shard-manifest` Annex**:
   - Define shared contracts in `## Wave 1`, then fan out into parallel `/boost` or `/swarm` shards (`## Wave 2A`, `## Wave 2B` with `Depends On: Wave 1`) and attach an optional fenced `shard-manifest` block (`minItems: 1`, `scope_in`, `verify_independently`).
2. **Optional Scope Lease Registration**:
   - Register worker contracts via `register_and_check_subagent_scope(...)` with automatic `owner_pid` tracking; parallel `/boost` and `/swarm` workers are never blocked from fixing cross-file root causes unless `exclusive_lock: true` is explicitly requested.
3. **Impacted Test Selection & Fast Shard Qualification**:
   - Select all impacted test files across all 6 test roots via `.venv/bin/python tools/adg_impact_tests.py --changed-files <files>` (zero batch-size cap).
   - Qualify each worker branch via `.venv/bin/python tools/pr_governance.py shard-ready <shard_branch>` (`verify_commit.py --shard-fast` + SHA-bound `reports/pr_shard_<slug>_receipt.json`).
4. **Coordinator Wave Merge Train & Promotion**:
   - Assemble verified shards (including shards sharing non-conflicting facade, contract, or test edits) into a wave train via `.venv/bin/python tools/pr_governance.py train --wave <N> --shards <b1> ...` (`feat/wave-<N>-train`), then promote to `main` via `.venv/bin/python tools/pr_governance.py promote feat/wave-<N>-train`.
