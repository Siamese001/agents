#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate Wave 6 Plan."""

import os
import sys
from pathlib import Path

# Load credentials from env_agents
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents not found")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect.
Repository: /Users/amitayer/Git/agents on branch `refactor/antipattern-remediation-waves`.
Protocol: docs/refactoring-wave-protocol.md (Maximum 6 waves; this is Wave 6: Final Convergence).
Task: Complete the 6-wave Live LLM Enforcement refactoring protocol.

PROGRESS TO DATE:
- Wave 1: Unified live credential preflight, fail-closed placeholder rejection, and CLI preflight integration (`infrastructure/live_execution.py`, `env_bootstrap.py`, `agents/cli.py`).
- Wave 2: Strict provider mode classification (`ProviderRunMode.LIVE_REQUIRED`), fail-closed CLI stub rejections, and executive judge mock guards (`provider_run_mode.py`, `executive_summary_x1d.py`).
- Wave 3: Proof judges sealed against mock mode in production (`competencies_x1d.py`, `x1d_panel_bridge.py`), and bullet selector single-path bypass sealed (`bullet_pool_claude_selector.py`).
- Wave 4: ProviderGateway strict live mode enforcement against `ProviderKind.STUB`, fail-closed L2 CPA provider resolution (`l2_envelope_adapter.py`), synthetic minimal L2 blob block in production (`artifact_assembler.py`), and research/outreach mock bridge blocks (`InMemoryResearchStore`, `MockAppsResearchBridge`).
- Wave 5: Hardened AST mock reachability auditor (`tools/audit_mock_reachability.py` checking MR001-MR005), sealed latent coherence judge mock branch (`full_resume_llm_coherence.py`), and added dedicated integration suite (`tests/integration/test_live_llm_e2e_verification.py`).

WAVE 6 OBJECTIVE:
Wave 6 is the final wave of this initiative. Its goals are:
1. Token Governor Hardening & Cost Tracking:
   - Ensure live LLM calls track authentic prompt/completion tokens and cost metrics rather than 0/dummy telemetry in production runtime.
   - Guard against unbounded live token expenditure (Token Governor limit enforcement).
2. Model Telemetry Lock:
   - Ensure telemetry receipts record authentic provider, model, and key fingerprint hashes without leaking raw credentials.
3. Final Comprehensive Verification & Close-out:
   - Run full test suites, pre-commit quality gate (all 5 tiers), mock reachability audit, and secrets linter.
   - Confirm complete convergence of the 6-wave protocol.

YOUR TASK:
Provide an authoritative architectural specification and implementation plan for Wave 6:
1. Exact components and files to verify, harden, or test.
2. Token governor and telemetry lock requirements and code patterns.
3. Acceptance criteria and verification commands.
4. Output format: A complete plan document suitable for `plans/live-llm-enforcement-wave6-<hex>.md`.
"""

print("Dispatching Wave 6 planning prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": "You are the Principal Architect formulating an authoritative, code-grounded Wave 6 refactoring plan under docs/refactoring-wave-protocol.md.",
        },
        {"role": "user", "content": prompt},
    ],
    reasoning_effort="medium",
    max_completion_tokens=15000,
)

content = response.choices[0].message.content
out_path = Path("artifacts/wave6_token_governor_and_telemetry_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(f"Wave 6 architectural review written to {out_path} ({len(content)} chars)")
