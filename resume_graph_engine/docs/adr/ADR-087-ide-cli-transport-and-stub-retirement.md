# ADR-087: Keyless Antigravity IDE CLI Transport and Retirement of Judge and Generator Stubs

**Status:** Accepted  
**Date:** 2026-11-19  
**Scope:** `resume_graph_engine` (`apps_rg`), `config/provider_profiles.yaml`, `config/model_catalog.json`

## Context

On 2026-11-17, two in-process synthetic shortcuts entered `resume_graph_engine`:
1. `apps_rg/runtime/judges/inprocess_proof_judge.py` (`evaluate_argon_x1d_judge`, commit `baa6e5de60`) intercepted proof judge calls for Argon model pins inside `executive_summary_x1d.py` and returned constant scores (`4.85` / `4.80`), static findings, and synthetic token counts while labelling outputs `MODEL_BACKED` and `proof_eligible_judge: true`.
2. `apps_rg/runtime/providers/inprocess_ide_provider.py` (`evaluate_inprocess_ide_generation` and `evaluate_inprocess_ide_selector`, commit `d90e9751fc`) intercepted `5-5-` model pins inside `external_provider.py` and `bullet_pool_claude_selector.py` and returned canned section payloads labelled `REAL_LLM` (including a 5-bullet `unify_bullets` payload that deterministically failed `x2_unify_bullet_count_6`).

Meanwhile, the `google-antigravity` Python SDK (`LocalAgentConfig`) requires an external `GEMINI_API_KEY` or Vertex ADC credential, whereas the headless Antigravity CLI (`agy -p`) authenticates via the signed-in local Antigravity OS keyring session with zero API keys, pins exact model slugs (`init.model`), supports `--json-schema`, and reports real token usage plus `conversation_id`.

## Decision

1. **Shared Keyless CLI Transport (`apps_rg/runtime/providers/agy_cli_transport.py`)**:
   - Strip `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, and `OPENAI_API_KEY` from the child process environment so calls cannot silently consume API keys.
   - Pass a temporary session-only `--settings` file with `deny: ["command(*)", "unsandboxed(*)", "read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)", "mcp(*)"]` inside an isolated empty working directory, and fail closed if any tool step or stray file appears.
   - Verify `agy --help` banner via `AGY_CLI_BIN`, require `init.model == model_requested`, require `status == "SUCCESS"`, and require both a non-empty `conversation_id` and `usage.total_tokens > 0`.

2. **Judge Stub Retirement & Dual IDE Proof Panel (`apps_rg/runtime/judges/x1d_ide_cli.py`)**:
   - Delete `evaluate_argon_x1d_judge` and `is_argon_model` from `inprocess_proof_judge.py`; retain `evaluate_argon_handoff_payload` solely for `apps_research` with explicit `"x_deterministic_screen": True, "x_model_call": False` markers.
   - Route both `gemini_pro` and `openai_chatgpt` X1D proof judge slots through `call_ide_cli_judge` when `ide_cli_judging.transport == "ide_cli"`, resolving Slot 2 (`second_judge_by_writer_maker`) to a distinct IDE model pin that never matches the lane's writer or Slot 1's Argon pin.
   - Validate CLI readiness and verify every active pinned IDE model against `agy models` during `python -m resume_graph_engine preflight`.

3. **Generator Stub Retirement & IDE Generation Adapter (`apps_rg/runtime/providers/ide_cli_generation.py`)**:
   - Delete `apps_rg/runtime/providers/inprocess_ide_provider.py` completely.
   - Route `ExternalProvider`, `bullet_pool_claude_selector.py`, and `ExecutiveVoiceRepairAgent.py` through `ide_cli_generation` (`model_map` pin-to-IDE-slug resolution), preserving the exact provider response contract with real token usage, `conversation_id`, and honest prompt-cache suppression (`capability_source: "ide_cli_transport"`).
   - Fail closed to `BLOCKED` on any transport, quota, schema, or empty-output failure; never emit canned or synthetic fallback text.

## Consequences

- **Positive:** Every section generation, pool selection, and X1D proof judgment produces verifiable model output backed by a real CLI `conversation_id` and token usage receipt with zero external API keys on IDE-routed lanes. Quota exhaustion (`RESOURCE_EXHAUSTED`) surfaces immediately as `BLOCKED` rather than masked synthetic passes.
- **Trade-offs:** Subprocess CLI invocation incurs ~15 to 40 seconds wall-clock latency per call and depends on the signed-in IDE subscription's per-family rate limits, mitigated by `ide_cli_generation.model_map`, `second_judge_by_writer_maker`, and fail-closed preflight verification against `agy models`.
