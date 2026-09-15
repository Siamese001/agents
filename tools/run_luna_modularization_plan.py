#!/usr/bin/env python3
"""Consult gpt-5.6-luna (medium) using env_agents to formulate the 6-wave modularization implementation plan."""

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

prompt = """You are the Principal AI Systems & Sovereign Agentic Platform Architect reviewing this repository: /Users/amitayer/Git/agents.

OPERATOR INSTRUCTION:
The operator has requested to implement the modularization plan for the top monolithic files identified in the codebase review, operating strictly under:
1. The 6-Wave Refactoring Protocol (`docs/refactoring-wave-protocol.md`) — max 6 execution waves, each wave moving the system measurably closer to the target end-state without breaking changes.
2. File Budget Governance (`tools/lint_file_budgets.py`) — strict 600-line budget limit per file in production directories. All decomposed files must be <= 600 lines.
3. Backwards Compatibility — All existing public imports and entrypoints must be preserved via facade re-exports (`__all__` or proxy re-exports) so no callers or tests break.
4. Test Suite and Governance Green — Must maintain clean passes across `pytest` and `tools/verify_commit.py`.

THE TOP MONOLITHIC CANDIDATES:
1. `resume_graph_engine/src/apps_rg/runtime/mandatory_run_outputs.py` (4,504 lines, 106 functions, 0 classes)
2. `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py` (4,473 lines, 43 functions, 0 classes)
3. `resume_graph_engine/src/apps_rg/runtime/sections/headline_lane.py` (3,363 lines, 49 functions, 0 classes)
4. `resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py` (3,158 lines, 102 functions, 1 class)
5. `resume_graph_engine/src/apps_rg/runtime/bindings/l1_cognitive_planner_v3.py` (3,116 lines, 47 functions, 1 class)
6. `resume_graph_engine/src/apps_rg/fact_inventory/augmented_skills_graph_sqlite.py` (3,019 lines, 59 functions, 0 classes)
7. `resume_graph_engine/src/apps_rg/bare_pipeline.py` (2,448 lines, 67 functions, 1 class)
8. `apps_research/engines/company_brief_engine.py` (2,255 lines, 8 functions, 2 classes)
9. `resume_graph_engine/src/apps_rg/runtime/judges/bullet_pool_claude_selector.py` (2,288 lines, 40 functions, 2 classes)
10. `apps_eval/runner/core.py` (2,150 lines, 45 functions, 0 classes)
11. `apps_research/integrations/apps_rg_handoff.py` (1,749 lines, 29 functions, 4 classes)
12. `infrastructure/utils/precision_security_framework.py` (1,205 lines, 0 functions, 11 classes)

YOUR TASK:
Produce an authoritative, highly detailed, code-grounded architectural specification:
1. **6-Wave Modularization Convergence Roadmap**:
   - Organize the 12 files into 6 distinct, sequential, non-overlapping waves.
   - For each wave (Wave 1 to Wave 6), define:
     * Objective & Target Files
     * Expected Line Count Reductions
     * Risk & Blast Radius Containment
     * Acceptance Criteria & Verification Strategy
2. **Detailed Executable Specification for Wave 1**:
   - Select the highest-impact, lowest-coupling candidate for Wave 1 (e.g. `executive_summary_x2.py` validator decomposition OR `mandatory_run_outputs.py` OR `precision_security_framework.py`).
   - Specify:
     * Current file structure & anti-patterns
     * Target directory and sub-module file paths (all < 600 lines)
     * Exact function and class distribution into the new submodules
     * Facade design pattern in the original file location to ensure zero broken imports
     * Unit test suite design for the new modules
     * Ratchet adjustment in `config/governance/file_budgets_ratchet.json`
     * Step-by-step execution procedure
"""

out_path = Path("artifacts/modularization_plan_luna.md")
out_path.parent.mkdir(parents=True, exist_ok=True)

print("Dispatching modularization plan prompt to gpt-5.6-luna (medium)...")
response = client.chat.completions.create(
    model="gpt-5.6-luna",
    messages=[
        {
            "role": "system",
            "content": (
                "You are the Principal AI Systems & Sovereign Agentic Platform Architect. "
                "Provide an authoritative, rigorous, code-grounded 6-wave modularization roadmap "
                "and an exact executable specification for Wave 1."
            ),
        },
        {"role": "user", "content": prompt},
    ],
    reasoning_effort="medium",
    max_completion_tokens=25000,
)

content = response.choices[0].message.content
out_path.write_text(content, encoding="utf-8")
print(f"Plan generated successfully! Written to {out_path} ({len(content)} chars)")
print("Usage:", response.usage)
