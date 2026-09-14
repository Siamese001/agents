#!/usr/bin/env python3
"""Run Comprehensive Live LLM & Mock Elimination Audit on gpt-5.6-luna (high) using env_agents."""

import os
import sys
import time
from pathlib import Path

# 1. Load env_agents credentials into os.environ
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents file not found in repo root")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

audit_prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect reviewing this entire repository: /Users/amitayer/Git/agents.

OBJECTIVE:
The operator requires ALL mock/stub/fake LLM API calls across the entire codebase to be identified and disabled, ensuring real API keys (from `env_agents` / `.env`: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY / GEMINI_API_KEY) are used for live calls throughout all execution paths.

DETAILED CODEBASE TOPOLOGY & ACTIVE RUNTIME ARCHITECTURE:

1. Unified CLI Entrypoint (`agents/cli.py`):
   - Commands: `python -m agents resume [run|eval|show]`, `outreach [run|eval|show]`, `e2e [--company ... --role ...]`.
   - In `run_e2e`, 3 lifecycle stages are orchestrated:
     * Stage 1: Upstream Company Research (`apps_research.__main__.main`)
     * Stage 2: Resume Tailoring (`apps_rg.__main__.main`)
     * Stage 3: Grounded Executive Outreach (`apps_lic.__main__.main`)
   - Needs to ensure that running `python -m agents e2e` or any individual engine executes real live model calls via the configured API keys.

2. Resume Graph Engine (`resume_graph_engine/src/apps_rg/`):
   A. Generation Provider Layer:
      - `apps_rg/runtime/providers/provider_run_mode.py`:
        * `classify_provider_run_mode()`: classifies context into `LIVE_REQUIRED`, `EXPLICIT_STUB`, `TEST_STUB`.
        * Detects `_pytest_active()` via `PYTEST_CURRENT_TEST` or `pytest in sys.modules` and forces `TEST_STUB`.
        * Detects `cli_explicit_stub` or `APPS_RG_L2_PROVIDER_MODE in ("stub_only", "stub", "off", "0", "false", "no")` or `APPS_RG_L2_FORCE_STUB=1`.
        * `assert_provider_authentic_for_full_resume()`: enforces authenticity when `LIVE_REQUIRED`.
      - `apps_rg/runtime/local_provider.py`:
        * `ProviderGateway.invoke()`: when `profile.provider_kind == ProviderKind.STUB`, short-circuits and returns synthetic JSON `{"stub_receipt": true}` without any network request.
      - `apps_rg/runtime/bindings/l2_envelope_adapter.py`:
        * `_provider_profile_for_cpa()`: maps CPA target providers; if `ProviderMode.STUB_ONLY` or unmapped, returns `apps_rg_envelope_stub` with `ProviderKind.STUB`.
      - `apps_rg/l2_recipe/r4_generation_mode.py`:
        * `resolve_apps_rg_modular_lane_provider()` defaults to `"external_claude"`.
        * `resolve_apps_rg_modular_lane_provider_override()` allows forcing provider.
      - `apps_rg/config/provider_profiles.yaml`:
        * SSOT for model routing. Pins generation models (`claude-sonnet-5`, `gpt-5.6-luna`), judge models (`gemini-3.8-flash`, `gpt-5.6-luna`), selector models (`claude-sonnet-5`).
        * Defines stub profiles: `llm_judge_stub`, `executive_positioning_judge_stub`.
      - `apps_rg/l2_recipe/artifact_assembler.py`:
        * `minimal_l2_blob()` and `write_synthetic_lane_bundle()`: emit synthetic phase 0 blobs with `runtime_generation_status = "MOCKED"`.
      - `apps_rg/runtime/providers/external_provider.py`:
        * Real HTTP transport (`_anthropic_messages_transport` and `_openai_responses_transport`) via `urllib.request`.
        * Injected `transport: ExternalTransport` can intercept and stub requests.
   B. X1D Proof Judge & Selector Layer:
      - `apps_rg/runtime/judges/executive_summary_x1d.py`:
        * `run_llm_judges()`: accepts `mode: str = "blocked_if_unavailable"`. If `mode == "mocked"`, invokes `_mocked_output()` returning hardcoded fake scores (0.80) and `evaluator_mode="MOCKED"`.
      - `apps_rg/runtime/judges/competencies_x1d.py`:
        * `_mocked()`: returns fake judge outputs with `evaluator_mode="MOCKED"`.
      - `apps_rg/runtime/judges/bullet_pool_claude_selector.py`:
        * Lines 2097 & 2132: if `mode == "mocked"` or `APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS=1`, bypasses the Claude selector call and calls `_fallback_first_complete_path()`.
      - `apps_rg/runtime/sections/role_episode_lane.py`:
        * Line 2188: sets `judge_mode="mocked" if bool(getattr(args, "mock_judges", False)) else "blocked_if_unavailable"`.
      - `apps_rg/runtime/live_judge_only_guard.py`:
        * Guards product CLI against `--mock-judges` flags, but `resolve_cli_mock_judges()` permits mocks if `APPS_RG_TEST_HARNESS=1` and `APPS_RG_MOCK_JUDGES=1`.
      - `apps_rg/runtime/section_proof/mock_runtime_proof_policy.py`:
        * Checks `args.mock_judges` and `args.allow_test_mock_judges`.
      - `apps_rg/runtime/assembly/full_resume_llm_coherence.py`:
        * Emits `evaluator_mode="MOCKED"` if mock coherence evaluation is active.

3. Research Engine (`apps_research/`):
   - `apps_research/integrations/llm_client.py`:
     * `create_openai_client()` and `create_openai_sync_client()` consume `OPENAI_API_KEY`.
   - `apps_research/integrations/provider_gateway.py`:
     * Real calls to OpenAI SDK and Gemini HTTP endpoint.
   - `apps_research/engines/research_retrieval_engine.py`:
     * Lines 79, 98, 163: `_mock_embed(text)` creates pseudo-embeddings (SHA-256) when `chromadb_path=None` instead of calling an embedding API.
   - `apps_research/reasoning/enterprise_research_orchestrator.py`:
     * Lines 355-392: `_generate_mock_research_content()` and `_generate_mock_source_register()`.
   - `apps_research/services/source_discovery_service.py`:
     * Line 112: mock discovery search fallback.
   - `apps_lic/integrations/apps_research_bridge.py` & `apps_rg/integrations/apps_research_bridge.py`:
     * `MockAppsResearchBridge` provides canned research briefs, evidence, and strategic priorities.

4. Executive Outreach Engine (`outreach_engine/src/apps_lic/`):
   - `apps_lic/pipeline/compiler.py`:
     * `render_draft_message()`: uses regex formatting (`_format_strategic_hook`) and string template injection rather than invoking a live LLM generation call.
   - `apps_lic/judges/evaluator.py`:
     * `RubricJudgeEvaluator`: uses static heuristic keyword checks (e.g. checking for 'you must', 'hire me') instead of calling an LLM judge.

5. Shared Infrastructure & Wrappers (`infrastructure/sdks_mcps/client_wrappers.py`):
   - `create_local_openai_client()` / `create_local_openai_sync_client()`: fallback to local dummy `http://localhost:8000/v1` with `sk-local-dev-key`.
   - Stub classes `OpenAIClient`, `AnthropicClient`, `VertexClient` with `pass`.

---

YOUR AUDIT & IMPLEMENTATION REPORT REQUIREMENTS:

Please produce an exhaustive, highly structured architectural audit and operational implementation blueprint addressing the following 6 sections:

### 1. Comprehensive Inventory of All Mock/Stub/Fake LLM Mechanisms
Trace every file, class, method, flag, and environment variable in the codebase where:
- LLM generation calls are stubbed, mocked, or bypassed.
- LLM evaluation/judge calls are mocked (`evaluator_mode="MOCKED"`).
- Embeddings or retrieval calls fall back to mock hashes.
- External bridges use mock implementations (`MockAppsResearchBridge`).
- String templating / regex heuristics substitute for generative reasoning.
Provide an exact table:
| Subsystem | File | Symbol / Method | Mock Mechanism / Bypass | Trigger Condition / Flag | Severity / Risk |

### 2. Forensic Classification: Harmful Silent Mocks vs Safe Test Doubles
- Differentiate between:
  A. Dangerous Silent Degradation (runtime or CLI execution silently passing with fake scores, mock content, or bypassed validation).
  B. Intentional Plumbing Test Doubles (unit tests verifying contract serialization without spending API tokens).
- Identify everywhere a mock might accidentally trigger during CLI or E2E execution.

### 3. Recommended Actions: Where & How Mocks Must Be Disabled
For each subsystem (`apps_rg`, `apps_lic`, `apps_research`, `agents` CLI):
- Specify exactly which mocks must be disabled, eliminated, or guarded with fail-closed errors.
- Specify how to enforce that API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`) from `env_agents` / `.env` are strictly required and utilized for live calls.
- Detail the exact default settings, configuration files (`provider_profiles.yaml`), and environment variable defaults needed.

### 4. Code Implementation Specifications
Provide exact, concrete Python code snippets and diffs demonstrating how to:
- Ensure `apps_rg` runs strictly `ProviderRunMode.LIVE_REQUIRED` and live X1D judges.
- Ensure `apps_research` uses live OpenAI / Gemini completions and embeddings rather than `_mock_embed`.
- Upgrade `apps_lic` from regex templating to an authenticated LLM generation pipeline using `infrastructure/sdks_mcps` or native provider calls.
- Ensure `agents/cli.py` enforces fail-closed live API key verification before starting any stage.

### 5. API Key & Token Governor Protection
When running live calls across the full multi-agent pipeline:
- How to prevent token runaway, infinite retry loops, and excessive spend while ensuring full live fidelity.
- Bounded retry limits, token budgets, and cost governance.

### 6. End-to-End Verification Plan
- Specific terminal commands to verify live API key usage across:
  * `python -m agents e2e --company Anthropic --role ...`
  * `python -m apps_rg run`
  * `python -m apps_research run`
  * `python -m apps_lic run`
- How to inspect output receipts (`external_model_usage.jsonl`, `provider_response.json`, judge receipts) to prove 100% live API key authenticity.
"""

out_path = Path("artifacts/live_llm_calls_audit_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching Live LLM & Mock Elimination Audit to gpt-5.6-luna (high)...")
start_time = time.time()

response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": (
                "You are the world-class Principal AI Systems Architect and Sovereign Agentic Platform Auditor. "
                "Deliver a rigorous, exhaustive, code-grounded forensic architectural audit and operational implementation "
                "blueprint to eliminate mock LLM calls and enforce live API key execution across this platform."
            ),
        },
        {"role": "user", "content": audit_prompt},
    ],
    reasoning_effort="high",
    max_completion_tokens=40000,
)

elapsed = time.time() - start_time
review_text = response.choices[0].message.content
out_path.write_text(review_text, encoding="utf-8")

print(f"Audit completed in {elapsed:.1f}s!")
print(f"Report written to {out_path} ({len(review_text)} chars)")
print("Usage:", response.usage)
