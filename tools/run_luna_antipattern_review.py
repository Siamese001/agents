#!/usr/bin/env python3
"""Run Comprehensive Codebase Anti-Pattern Review on gpt-5.6-luna (medium) using env_agents."""

import os
import sys
from pathlib import Path

# 1. Load credentials from env_agents
env_file = Path("env_agents")
if not env_file.exists():
    raise FileNotFoundError("env_agents not found in repository root")

for line in env_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

from openai import OpenAI

client = OpenAI()

prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect reviewing this codebase: /Users/amitayer/Git/agents.

OPERATOR REQUEST:
"detailed review of code and find top antipatterns to refactor out of codebase - summarize in table prioritize"
Model: gpt-luna-5.6 (medium)
Credentials: env_agents

REPOSITORY FACTS & CURRENT MEASURED STATE:
1. Scale & Core Subsystems:
   - Root: `agents/` (unified CLI & orchestration state machine), `resume_graph_engine/` (Resume Graph Engine), `outreach_engine/` (Executive Outreach), `apps_research/` (Company & Role Research), `apps_eval/` (Evaluation framework), `apps_model_telemetry/`, `infrastructure/`, `config/`.
   - Total Python files: ~400+
   - Total lines: ~150,000+ lines of Python.

2. Extreme Monoliths (>2,000 lines in single files, 236 files ratcheted exceeding 600-line budget):
   - `resume_graph_engine/src/apps_rg/runtime/mandatory_run_outputs.py` (4,504 lines, 106 functions, 0 classes)
   - `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py` (4,473 lines, 43 functions, 0 classes)
   - `resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py` (3,363 lines, 49 functions, 0 classes)
   - `resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py` (3,158 lines, 102 functions, 1 class)
   - `resume_graph_engine/src/apps_rg/runtime/bindings/l1_cognitive_planner_v3.py` (3,116 lines, 47 functions, 1 class)
   - `resume_graph_engine/src/apps_rg/fact_inventory/augmented_skills_graph_sqlite.py` (3,019 lines, 59 functions, 0 classes)
   - `resume_graph_engine/src/apps_rg/runtime/orchestration/r3r4_whole_run_orchestration.py` (2,698 lines)
   - `resume_graph_engine/src/apps_rg/runtime/sections/role_episode_lane.py` (2,627 lines)
   - `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_voice_repair.py` (2,582 lines)
   - `resume_graph_engine/src/apps_rg/runtime/bindings/c0_binding.py` (2,551 lines)
   - `resume_graph_engine/src/apps_rg/runtime/c0/resume_graph_allocation.py` (2,497 lines)
   - `resume_graph_engine/src/apps_rg/bare_pipeline.py` (2,448 lines)
   - `resume_graph_engine/src/apps_rg/fact_inventory/c03_graph_kpi_health.py` (2,310 lines)
   - `resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector.py` (2,288 lines)
   - `apps_research/engines/company_brief_engine.py` (2,255 lines)
   - `resume_graph_engine/src/apps_rg/runtime/terminal_closeout_replay.py` (2,221 lines)
   - `apps_eval/runner/core.py` (2,150 lines)
   - `resume_graph_engine/src/apps_rg/runtime/sections/unify_bullets_lane.py` (2,133 lines)
   - `resume_graph_engine/src/apps_rg/runtime/sections/ibm_bullets_lane.py` (2,109 lines)
   - `resume_graph_engine/src/apps_rg/runtime/w5_end_to_end_pipeline.py` (2,083 lines)

3. Subtree Duplication:
   - `apps_research/` at root is an exact duplicate tree of `resume_graph_engine/src/apps_research/`.
   - `apps_eval/` at root is an exact duplicate tree of `resume_graph_engine/src/apps_eval/`.
   - `apps_model_telemetry/` at root is an exact duplicate of `resume_graph_engine/src/apps_model_telemetry/`.

4. Path Hacking & Packaging Fragility:
   - Over 200 occurrences of `sys.path.insert(0, ...)` across root entrypoints, engines, tools, and tests.

5. Pipeline Duality & Redundant Execution Modes:
   - Multiple competing ways to run resume generation: `bare_pipeline.py` (2,448 lines), `modular_resume_generation.py` (recently decomposed into 5 services), `canonical_dispatch.py`, and `w5_end_to_end_pipeline.py`.

6. Agentic Invariants & Feedback Loops:
   - Conflation of technical errors, format validation failures, and cognitive replanning.
   - Post-hoc gate-heavy blocking (e.g. 3,158 lines in `executive_summary_x2.py`) vs upstream agentic feedback or multi-turn revision loops.
   - Ad-hoc regex/heuristic repairs (e.g. `executive_summary_voice_repair.py` with 2,582 lines of manual patching) instead of LLM self-correction or structured prompts.

7. Configuration & SSOT Sprawl:
   - Provider profiles, model pins, and governance limits scattered between `config/`, `resume_graph_engine/config/`, `apps_research/config/`, and inline dictionaries.

YOUR TASK:
Provide a rigorous, code-grounded architectural review:
1. Executive Assessment: Overall architectural health score (1-10), key systemic risks, and root causes.
2. Top Anti-Patterns to Refactor Out:
   Identify the top 10 most critical architectural, structural, and agentic anti-patterns in this codebase.
   For each anti-pattern:
   - Anti-Pattern Name & Classification (e.g. Monolithic God Modules, Subtree Duplication, Dynamic Path Hacking, Pipeline Duality, Gate-Dependent Post-Hoc Validation vs Iterative Loops, Heuristic Patching vs Agentic Self-Correction, SSOT Configuration Sprawl, Mock/Stub Leakage, Untyped Mutable State Blobs, Fragmented Observability)
   - Evidence in Code: Exact files, line counts, and symbols.
   - Architectural & Operational Impact (blast radius, maintenance cost, cognitive load, debugging failure modes).
   - Concrete Refactoring Strategy & Target End-State.
3. Master Prioritized Anti-Pattern Summary Table:
   Provide a comprehensive Markdown table summarizing and prioritizing ALL identified anti-patterns:
   Columns:
   - Priority (P0, P1, P2, P3)
   - Anti-Pattern Name
   - Category (Architecture, Agentic Flow, Code Health, Governance)
   - Primary Files / Scope
   - Severity & Blast Radius (Critical / High / Medium)
   - Refactoring Complexity (Low / Medium / High / Extreme)
   - Recommended Remediation Protocol / Wave
4. 6-Wave Refactoring Roadmap:
   Structure the remediation into an actionable 6-wave plan under `docs/refactoring-wave-protocol.md` to systematically eliminate these anti-patterns with zero regressions.
"""

out_path = Path("artifacts/codebase_antipatterns_luna_review.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching codebase anti-pattern review prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": (
                "You are the Principal AI Systems & Sovereign Agentic Platform Architect. "
                "Provide an authoritative, code-grounded, exhaustive architectural anti-pattern review, "
                "a prioritized summary table, and a 6-wave refactoring roadmap."
            ),
        },
        {"role": "user", "content": prompt},
    ],
    reasoning_effort="medium",
    max_completion_tokens=25000,
)

content = response.choices[0].message.content
out_path.write_text(content, encoding="utf-8")
print(f"Review generated successfully! Written to {out_path} ({len(content)} chars)")
print("Usage:", response.usage)
