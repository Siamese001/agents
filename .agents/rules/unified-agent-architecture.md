---
trigger: always_on
---

# Unified Architecture: Skills, Agents, Sub-Agents, Hooks & Rules

Defines the non-negotiable structural taxonomy, delegation contracts, and execution lifecycle across the repository.

## Five Core Architectural Pillars

1. **Skills (What work gets done)**
   - Reusable, atomic or composite capabilities.
   - Model & Tool Agnostic. Stateless by default.
   - Located centrally under `.agents/skills/`.
   - Building blocks: skills never dictate high-level orchestration strategy.

2. **Agents (Who decides & orchestrates)**
   - Goal-driven orchestrators.
   - Own high-level strategy and control, maintain context and state, and decompose objectives.
   - Delegate bounded subtasks to specialized sub-agents.

3. **Sub-Agents (Specialized executors)**
   - Focused on narrow, bounded domains.
   - Lightweight autonomy within delegated scope.
   - Strictly return results upstream to parent agent. Sub-agents must never mutate shared/global architecture state directly.

4. **Hooks (When to extend)**
   - Event-based lifecycle extension points (`pre_tool_call`, `post_tool_call`, `around_action`).
   - Handle cross-cutting concerns: logging, metrics, caching, notifications, guardrails, moderation.
   - Strictly non-intrusive: hooks must never mutate core business logic or bypass governance rules.

5. **Rules (What must be true)**
   - Immutable governance constraints, pre/post-conditions, routing rules, and safety boundaries.
   - No agent, sub-agent, skill, or hook may bypass an enforced rule.

## Four Shared Foundations

1. **Memory & Transparent Scratchpads**: Visible scratchpads (telemetry, cognitive thinking deliberation, reasoning steps, tool audits) and persistent ledgers.
2. **Knowledge Bases & Data Sources**: Knowledge graphs (ADG SQLite), vector indices, schemas, and relational tables.
3. **Models & Tools**: Foundation models, native CLI tools, and MCP servers.
4. **Observability**: Distributed traces, audit events, and execution receipts.

## Sub-Agent Delegation Contract (10 Required Fields)

Before spawning any sub-agent (via `invoke_subagent` or `browser_subagent`), the orchestrator MUST construct an explicit delegation contract declaring:
1. `task_id`: Unique identifier for the delegation.
2. `parent_task_id`: Caller's task identifier.
3. `objective`: Specific, bounded goal description.
4. `scope_in`: Itemized list of allowed target files/modules.
5. `scope_out`: Itemized list of strictly forbidden files/modules.
6. `allowed_tools`: Whitelist of permissible tools for the sub-agent.
7. `deliverable`: Exact expected output artifact or schema.
8. `definition_of_done`: Objective verification condition.
9. `budget`: Concrete caps (`max_turns`, `timeout_seconds`, or `token_limit`).
10. `escalation_rule`: Immediate failure/escalation condition.

## Upstream Return Protocol
Upon task completion, the sub-agent must return a structured payload:
- `task_id`: Matching delegation task identifier.
- `status`: `SUCCESS`, `FAILED`, or `BLOCKED`.
- `deliverable`: Output artifact, diff, or report.
- `evidence_refs`: Pointers to generated receipts, test outputs, or logs.
- `metrics`: Turns used, execution duration, tools called.

## Seven-Step Execution Lifecycle
1. **Goal & Rule Verification**: Agent evaluates active rules, policies, and classifications.
2. **Planning & Skill Selection**: Agent decomposes goal into wave milestones and selects required skills.
3. **Sub-Agent Delegation**: Agent delegates bounded subtasks under explicit contracts.
4. **Skill Execution**: Skills execute tasks and produce outputs.
5. **Hook Triggers**: Pre/post/around hooks execute for telemetry, caching, and guardrails.
6. **Continuous Rule Validation**: Rules continuously validate inputs, outputs, and side effects.
7. **Upstream Synthesis**: Results flow back upstream; parent agent synthesizes verified response.
