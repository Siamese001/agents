# Antigravity SDK Wiring Remediation Plan

## Implementation Status

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Hook Tool-Matcher Hardening, MCP Config Integrity & Skill Cap Alignment | COMPLETE |
| Wave 2 | Core Antigravity SDK Dependencies, Client Lifecycle & Local Runtime Adapters | COMPLETE |
| Wave 3 | Subagent Delegation, Structured Output, Custom Tools & Native Cancellation | COMPLETE |
| Wave 4 | Budget Config, Retries, Compaction, Persistence & Thought-Token Observability | COMPLETE |

## Architectural Defense & Holistic Spine Alignment

- What stays unchanged in upstream `resume_graph_engine` Stage-1/Stage-2 `resume_graph_allocation.py` and `FactAnchor` contracts, upstream `outreach_engine` `briefing_resolver.py` and `apps_research_bridge.py`, and upstream `apps_research` `search_retrieval.py` and `research_retrieval_engine.py`: domain retrieval and evidence binding remain deterministic.
- Downstream validation stages (`cross_section_x2.py`, `bullet_fact_entailment.py`, `outreach_engine/src/apps_lic/domain/validators.py`, `judges/evaluator.py`, and `apps_research/integrations/apps_rg_handoff.py` with `apps_rg_targeting_brief_contract.py`) remain enforced across all 4 waves.

## Wave 1: Hook Tool-Matcher Hardening, MCP Config Integrity & Skill Cap Alignment

### Objective & Scope
Close critical tool-matcher gaps in `.agents/hooks.json` and `tools/hook_dispatch.py`, reconcile `.mcp.json` and `.agents/rules/mcp-config-ssot.md`, export programmatic SDK hook/policy helpers, and align skill budget caps.

### Milestones & Deliverables
- [MODIFY] `.agents/hooks.json` and `tools/hook_dispatch.py` to guard `create_file` and `start_subagent` alongside existing file-write and subagent matchers, and expose programmatic `google.antigravity.hooks` and `policy` presets with `RunCommandConfig(enable_sandbox=True)`.
- [MODIFY] `.mcp.json`, `.agents/mcp_config.json`, `.agents/rules/mcp-config-ssot.md`, and `tools/ssot_boundary_auditor.py` to resolve the dangling `vector_db_server.py` entry, verify MCP script existence on disk, and provide an `McpStdioServer` / `McpStreamableHttpServer` loader.
- [MODIFY] `.agents/skills/agent-subagent-orchestration/SKILL.md`, `.agents/rules/skills_contract_hardening.md`, and `tools/validate_sidecar_separation.py` to align `edit_file`, skill count caps (`MAX_SKILLS_CAP`), `skills_paths`, and `google.antigravity.triggers` (`every`, `on_file_change`).

### Acceptance Criteria
- `tools/hook_dispatch.py` intercepts `create_file` and `start_subagent` in pre-tool guards.
- `tools/ssot_boundary_auditor.py` verifies all `.mcp.json` stdio script paths exist on disk and exits 0.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_hook_dispatch.py tests/unit/test_sidecar_separation_governance.py -v --timeout=60`
- Input: Synthetic `PreToolUse` payloads for `create_file` and `start_subagent` plus `.mcp.json` server entries.
- Expected: 100% test pass rate and exit code 0 with `create_file` and `start_subagent` blocked when unaligned.
- Verify independently: Run `.venv/bin/python tools/ssot_boundary_auditor.py` and confirm 0 MCP or hook violations.
- Fail if: `create_file` or `start_subagent` bypasses pre-tool hooks or any `.mcp.json` script path is missing.
- Record: `artifacts/governance/receipts/wave1_hooks_mcp_sdk_receipt.json`

## Wave 2: Core Antigravity SDK Dependencies, Client Lifecycle & Local Runtime Adapters

### Objective & Scope
Declare `google-antigravity` and `litert-lm` in `pyproject.toml`, wire `infrastructure/sdks_mcps/` and `agents/gateway/model_gateway.py` to `Agent` / `LocalAgentConfig`, fix `GEMINI_API_KEY` precedence and Vertex/Priority tier options, and enable keyless `LiteRTAgentConfig` and `LocalOpenAIAgentConfig`.

### Milestones & Deliverables
- [MODIFY] `pyproject.toml` to add `google-antigravity` to `[project].dependencies` and `litert-lm` to `[project.optional-dependencies].infra`.
- [MODIFY] `infrastructure/sdks_mcps/client_wrappers.py`, `infrastructure/sdks_mcps/gemini_client.py`, `infrastructure/live_execution.py`, and `agents/gateway/model_gateway.py` to build `LocalAgentConfig`, `LiteRTAgentConfig`, and `LocalOpenAIAgentConfig(...).lightweight()`, prioritize `GEMINI_API_KEY`, support Vertex Standard/Express and `ServiceTier.PRIORITY`, and stream `response` tokens and `response.thoughts`.
- [MODIFY] `config/provider_profiles.yaml`, `infrastructure/device/device_manager.py`, and `scripts/local_llm/test_client_call.py` to map profiles to `LocalAgentConfig` and allow keyless local execution.

### Acceptance Criteria
- `infrastructure/live_execution.py` resolves `GEMINI_API_KEY` first and permits keyless local configs (`LiteRTAgentConfig`, `LocalOpenAIAgentConfig`).
- `client_wrappers.py` and `model_gateway.py` execute through async `Agent(config)` context managers with zero placeholder `"Simulated execution..."` strings.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/unit/test_client_wrappers_sdk.py -v --timeout=60`
- Input: Hosted `gemini-3.8-flash` profile, Vertex Express config, and keyless `LiteRTAgentConfig` / `LocalOpenAIAgentConfig` fixtures.
- Expected: Exit code 0 with verified `LocalAgentConfig`, `LiteRTAgentConfig`, and `LocalOpenAIAgentConfig` instantiation.
- Verify independently: Inspect `infrastructure/live_execution.py` and `infrastructure/sdks_mcps/client_wrappers.py` via AST check for zero mandatory `LOCAL_OPENAI_API_KEY` errors on local configs.
- Fail if: Local configs raise `LiveExecutionError` without an API key or `GEMINI_API_KEY` is marked deprecated.
- Record: `artifacts/governance/receipts/wave2_core_sdk_adapters_receipt.json`

## Wave 3: Subagent Delegation, Structured Output, Custom Tools & Native Cancellation

### Objective & Scope
Wire `SubAgentDefinition` and domain orchestrators to `types.SubagentConfig` and `BuiltinTools.START_SUBAGENT`, replace manual JSON fence stripping with `response_schema` and `await response.structured_output()`, bind `ToolContext` and `TemplatedSystemInstructions`, add `types.Document.from_file`, and replace daemon thread timeouts with `await response.cancel()`.

### Milestones & Deliverables
- [MODIFY] `tools/unified_agent_architecture.py`, `agents/orchestration/services/swarm_challenger.py`, `outreach_engine/src/apps_lic/runtime/outreach_swarm_challenger.py`, `resume_graph_engine/src/apps_rg/runtime/resume_swarm_challenger.py`, and `apps_research/reasoning/research_multi_agent.py` to map 10-field contracts to `types.SubagentConfig` and `CapabilitiesConfig(enable_subagents=True, max_subagent_depth=..., allowed_subagents=[...])`.
- [MODIFY] `resume_graph_engine/src/apps_rg/l2_recipe/raw_text_json_unwrap.py`, `apps_research/engines/company_brief/synthesis.py`, `apps_research/integrations/apps_rg_handoff.py`, `outreach_engine/src/apps_lic/pipeline/compiler.py`, `resume_graph_engine/src/apps_rg/runtime/providers/external_provider.py`, and `apps_research/integrations/pdf_ingest.py` to support `LocalAgentConfig(response_schema=...)`, `TemplatedSystemInstructions`, and `types.Document.from_file`.
- [MODIFY] `agents/orchestration/primitives.py`, `agents/orchestration/engine.py`, `resume_graph_engine/src/apps_rg/runtime/providers/wallclock_http_guard.py`, and `resume_graph_engine/src/apps_rg/runtime/orchestration/managed_section_lane_dispatcher.py` to inject `ToolContext` and use `await response.cancel()` with `except AntigravityCancelledError:`.

### Acceptance Criteria
- `unified_agent_architecture.py` exports validated `types.SubagentConfig` objects while preserving upstream `resume_graph_allocation.py`, `briefing_resolver.py`, and `search_retrieval.py` contracts and downstream `cross_section_x2.py`, `outreach_engine/src/apps_lic/domain/validators.py`, and `apps_rg_handoff.py` validators.
- Cancellation paths invoke `await response.cancel()` and catch `AntigravityCancelledError` before `Exception`.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_unified_agent_architecture.py -v --timeout=60`
- Input: 10-field delegation contracts, Pydantic `response_schema` models, `ToolContext` state mutations, and stream cancellation triggers.
- Expected: Exit code 0 with verified `SubagentConfig` projection, typed `structured_output()` parsing, and clean `AntigravityCancelledError` handling.
- Verify independently: Run `.venv/bin/python tools/unified_agent_architecture.py` and verify `SubagentConfig` serialization.
- Fail if: `AntigravityCancelledError` is swallowed by `except Exception:` or `SubagentConfig` omits tool/subagent whitelists.
- Record: `artifacts/governance/receipts/wave3_domain_sdk_wiring_receipt.json`

## Wave 4: Budget Config, Retries, Compaction, Persistence & Thought-Token Observability

### Objective & Scope
Bridge token/call governors to `types.BudgetConfig` and `types.StopReason`, wire `RetryConfig`, `CompactionConfig`, `save_dir`, and `app_data_dir` from `.antigravity/runtime-boundary.json`, and export `UsageMetadata` (`thoughts_token_count`) and `google.antigravity` logger telemetry.

### Milestones & Deliverables
- [MODIFY] `infrastructure/live_governor.py`, `agents/context/budgeting.py`, `apps_model_telemetry/token_budget_governor.py`, and `resume_graph_engine/src/apps_rg/runtime/model_token_governor.py` to project budgets into `types.BudgetConfig` (`LIFETIME` and `FORWARD_LOOKING`) and inspect `response.stop_reason` (`types.StopReason`).
- [MODIFY] `tools/agent_runtime_auditor.py`, `tools/cost_token_budget_governor_probes.py`, `infrastructure/utils/distributed_state_manager.py`, and `.antigravity/runtime-boundary.json` to wire `types.RetryConfig`, `types.CompactionConfig`, `save_dir`, `conversation_id`, `app_data_dir`, `workspaces`, and `hooks.OnToolErrorHook`.
- [MODIFY] `agents/observability/prompt_cache.py`, `apps_model_telemetry/telemetry_facade.py`, and `agents/observability/events.py` to read `agent.conversation.total_usage`, emit `gen_ai.usage.thought_tokens` (`thoughts_token_count`), and attach handlers to `logging.getLogger("google.antigravity")`.

### Acceptance Criteria
- `telemetry_facade.py` records `gen_ai.usage.thought_tokens` alongside input, output, cached, and total tokens from `UsageMetadata`.
- `live_governor.py` produces valid `types.BudgetConfig` instances and maps `types.StopReason` outcomes.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/unit/test_cost_token_budget_auditor.py -v --timeout=60`
- Input: Simulated `UsageMetadata` with `thoughts_token_count`, `BudgetConfig` limits, `RetryConfig`, and `CompactionConfig` thresholds.
- Expected: Exit code 0 with `gen_ai.usage.thought_tokens` exported and `StopReason` budget halts verified.
- Verify independently: Run `.venv/bin/python tools/cost_token_budget_auditor.py` and confirm 100% pass across all 8 tokenomics pillars.
- Fail if: `thoughts_token_count` is dropped from telemetry spans or `BudgetConfig` fails to enforce token/call caps.
- Record: `artifacts/governance/receipts/wave4_budgets_observability_receipt.json`
