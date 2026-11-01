#!/usr/bin/env python3
"""Mechanical validator enforcing separation between Agents Repo sidecars and Decision Intelligence Engine sidecars.

Verifies:
1. Namespace Isolation: All 7 Agents Repo sidecars use `agents-*` directory names and `Agents Repo: ` display prefixes.
2. Prompt Dereference & Workspace Containment: Every `agents-*` sidecar points to `/Users/amitayer/Git/agents/automations/prompts/agents_*_agent.md` and restricts `workspace_uris` and `access_grants` to `/Users/amitayer/Git/agents`.
3. Cross-Repo Firewall (`INV-REPO-SEPARATION-AGENTS-ONLY`): Every Agents prompt specification enforces `INV-REPO-SEPARATION-AGENTS-ONLY` and prohibits touching `/Users/amitayer/Git/decision-intelligence-engine`.
4. Disjoint Schedule Window: All 7 Agents sidecars run in the 05:30-07:00 America/New_York window with zero cron collisions against the 17 Decision Intelligence Engine sidecars.
5. Decision Intelligence Engine Preservation: All 17 existing Decision Intelligence Engine sidecars remain intact and bound to `/Users/amitayer/Git/decision-intelligence-engine`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIDECARS_ROOT = Path("/Users/amitayer/.gemini/config/sidecars")
AGENTS_CANONICAL_ROOT = "/Users/amitayer/Git/agents"
NEE_CANONICAL_ROOT = "/Users/amitayer/Git/decision-intelligence-engine"

EXPECTED_AGENTS_SIDECARS: dict[str, dict[str, str]] = {
    "agents-storage-worktree-hygiene": {
        "display_name": "Agents Repo: Storage & Worktree Hygiene",
        "cron": "CRON_TZ=America/New_York 30 5 * * *",
        "prompt_file": "agents_storage_worktree_hygiene_agent.md",
    },
    "agents-ssot-boundary-governance": {
        "display_name": "Agents Repo: SSOT & Boundary Governance",
        "cron": "CRON_TZ=America/New_York 45 5 * * *",
        "prompt_file": "agents_ssot_boundary_agent.md",
    },
    "agents-outreach-resume-functionality": {
        "display_name": "Agents Repo: Outreach & Resume Functionality",
        "cron": "CRON_TZ=America/New_York 5 6 * * *",
        "prompt_file": "agents_e2e_functionality_assurance_agent.md",
    },
    "agents-research-retrieval-surface": {
        "display_name": "Agents Repo: Research & Retrieval Surface",
        "cron": "CRON_TZ=America/New_York 15 6 * * *",
        "prompt_file": "agents_research_retrieval_surface_agent.md",
    },
    "agents-evals-judge-assurance": {
        "display_name": "Agents Repo: Evals & Judge Validity",
        "cron": "CRON_TZ=America/New_York 30 6 * * *",
        "prompt_file": "agents_evals_judge_assurance_agent.md",
    },
    "agents-cost-token-budget": {
        "display_name": "Agents Repo: Cost & Token Budget",
        "cron": "CRON_TZ=America/New_York 45 6 * * *",
        "prompt_file": "agents_cost_token_budget_agent.md",
    },
    "agents-testing-gaps-assurance": {
        "display_name": "Agents Repo: Testing Gaps Assurance",
        "cron": "CRON_TZ=America/New_York 0 7 * * *",
        "prompt_file": "agents_testing_gaps_assurance_agent.md",
    },
}

EXPECTED_NEE_SIDECARS: tuple[str, ...] = (
    "agentic-repo-best-practices-scout",
    "autonomous-storage-repository-clutter-hygiene-protocol",
    "corner-foresight-blindspot-scout",
    "e2e-critical-functionality-assurance-agent",
    "energy-utilities-best-practices",
    "evals-surface-assurance-agent",
    "google-slalom-weekly-sync",
    "hotspot-value-enhancement-agent",
    "knowledge-graph-hygiene-agent",
    "nea-charter-portfolio-roster",
    "pipeline-outcome-retrieval-assurance",
    "pr-queue-governance-observer",
    "retrieval-surface-assurance-agent",
    "ssot-configuration-deduplication-model-pinning-anti-hardcoding",
    "system-learning-assurance-agent",
    "testing-gaps-assurance-agent",
    "tokenomics-cost-optimization-agent",
)

PROMPT_URI_RE = re.compile(r"file://(/[^\s\"']+?\.md)")

REQUIRED_SHARED_CONTRACT_MARKERS: tuple[str, ...] = (
    "INV-REPO-SEPARATION-AGENTS-ONLY",
    "urn:agents:scheduled-task-common-control-matrix:1.0.0",
    "UNCONDITIONAL_WAVE_PLAN_MANDATE",
    "INV-WT-EPHEMERAL-SCHEDULED",
    "INV-RUNTIME-PROOF-5POINT",
    "INV-AUTOMATION-PERSISTENT-LEARNING-LOOP",
    "validate_implementation_plan.py",
    "--consolidate-sidecar",
    "Dimension Findings Table",
)

REQUIRED_PROMPT_PARITY_MARKERS: tuple[str, ...] = (
    "INV-REPO-SEPARATION-AGENTS-ONLY",
    "urn:agents:scheduled-task-common-control-matrix:1.0.0",
    "UNCONDITIONAL_WAVE_PLAN_MANDATE",
    "INV-RUNTIME-PROOF-5POINT",
    "INV-AUTOMATION-PERSISTENT-LEARNING-LOOP",
    "Phase 0",
    "Step 0.1",
    "--consolidate-sidecar",
    "Phase 1",
    "Phase 1.5",
    "Phase 2",
    "Phase 3",
    "validate_implementation_plan.py",
    "Dimension Findings Table",
    "HITLDecisionStore",
)


def validate_sidecar_separation(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
) -> dict[str, Any]:
    """Validate namespace, prompt, permission, schedule separation, and Decision Intelligence structural parity."""
    violations: list[str] = []
    prompts_dir = repo_root / "automations" / "prompts"

    # 1. Check shared governance contract
    shared_contract = prompts_dir / "_shared_governance_contract.md"
    if not shared_contract.is_file():
        violations.append(f"Missing shared governance contract: {shared_contract}")
    else:
        shared_text = shared_contract.read_text(encoding="utf-8")
        for marker in REQUIRED_SHARED_CONTRACT_MARKERS:
            if marker not in shared_text:
                violations.append(f"_shared_governance_contract.md missing mandatory parity marker '{marker}'")
        if NEE_CANONICAL_ROOT in shared_text:
            violations.append(f"_shared_governance_contract.md contains forbidden path '{NEE_CANONICAL_ROOT}'")

    agents_crons: dict[str, str] = {}
    nee_crons: dict[str, str] = {}
    display_names: dict[str, str] = {}

    # 2. Validate all 7 Agents Repo sidecars and their prompt specs
    validated_agents_count = 0
    for sidecar_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        if not sidecar_id.startswith("agents-"):
            violations.append(f"{sidecar_id}: Missing mandatory 'agents-' directory prefix")

        sc_file = sidecars_root / sidecar_id / "sidecar.json"
        if not sc_file.is_file():
            violations.append(f"Missing Agents sidecar config: {sc_file}")
            continue

        try:
            payload = json.loads(sc_file.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(f"{sidecar_id}: Invalid JSON in sidecar.json: {exc}")
            continue

        if payload.get("builtin") != "schedule":
            violations.append(f"{sidecar_id}: builtin must be 'schedule'")
        if payload.get("restart_policy") != "always":
            violations.append(f"{sidecar_id}: restart_policy must be 'always'")

        disp = str(payload.get("display_name") or "")
        if not disp.startswith("Agents Repo: "):
            violations.append(f"{sidecar_id}: display_name '{disp}' must start with 'Agents Repo: '")
        if disp != spec["display_name"]:
            violations.append(f"{sidecar_id}: display_name '{disp}' != expected '{spec['display_name']}'")
        if disp in display_names:
            violations.append(f"{sidecar_id}: duplicate display_name '{disp}' with {display_names[disp]}")
        display_names[disp] = sidecar_id

        args = payload.get("args")
        if not isinstance(args, list) or len(args) < 5:
            violations.append(f"{sidecar_id}: args must be a list of [cron, 'agentapi', 'new-conversation', ..., '--', prompt]")
            continue

        cron_expr = str(args[0])
        if cron_expr != spec["cron"]:
            violations.append(f"{sidecar_id}: cron '{cron_expr}' != expected '{spec['cron']}'")
        if cron_expr in agents_crons:
            violations.append(f"{sidecar_id}: duplicate cron '{cron_expr}' with {agents_crons[cron_expr]}")
        agents_crons[cron_expr] = sidecar_id

        prompt_arg = str(args[-1])
        expected_uri = f"file://{AGENTS_CANONICAL_ROOT}/automations/prompts/{spec['prompt_file']}"
        if expected_uri not in prompt_arg:
            violations.append(f"{sidecar_id}: prompt arg does not dereference '{expected_uri}'")

        # Check permissions isolation
        perms = payload.get("agent_permissions")
        if not isinstance(perms, dict):
            violations.append(f"{sidecar_id}: missing agent_permissions block")
        else:
            ws_uris = perms.get("workspace_uris", [])
            if ws_uris != [f"file://{AGENTS_CANONICAL_ROOT}"]:
                violations.append(
                    f"{sidecar_id}: workspace_uris must be strictly ['file://{AGENTS_CANONICAL_ROOT}'], got {ws_uris}"
                )
            grants = perms.get("access_grants", [])
            if not grants:
                violations.append(f"{sidecar_id}: access_grants must not be empty")
            for grant in grants:
                if NEE_CANONICAL_ROOT in str(grant):
                    violations.append(f"{sidecar_id}: forbidden Decision Intelligence Engine grant '{grant}'")
                if str(grant) in ("command(*)", "read_file(*)", "read_file(/)", "write_file(*)", "write_file(/)"):
                    violations.append(f"{sidecar_id}: overly broad wildcard grant '{grant}'")

        # Validate local repository prompt file
        local_prompt = prompts_dir / spec["prompt_file"]
        if not local_prompt.is_file():
            violations.append(f"{sidecar_id}: missing repository prompt file {local_prompt}")
        else:
            p_text = local_prompt.read_text(encoding="utf-8")
            for marker in REQUIRED_PROMPT_PARITY_MARKERS:
                if marker not in p_text:
                    violations.append(f"{spec['prompt_file']}: missing mandatory parity marker '{marker}'")
            if NEE_CANONICAL_ROOT in p_text:
                violations.append(f"{spec['prompt_file']}: contains forbidden path '{NEE_CANONICAL_ROOT}'")

        validated_agents_count += 1

    # 3. Verify all 17 Decision Intelligence Engine sidecars are untouched and disjoint
    validated_nee_count = 0
    for nee_id in EXPECTED_NEE_SIDECARS:
        if nee_id.startswith("agents-"):
            violations.append(f"NEE sidecar '{nee_id}' unexpectedly starts with 'agents-'")
        nee_file = sidecars_root / nee_id / "sidecar.json"
        if not nee_file.is_file():
            violations.append(f"Decision Intelligence Engine sidecar missing: {nee_file}")
            continue
        try:
            nee_payload = json.loads(nee_file.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(f"NEE sidecar '{nee_id}' invalid JSON: {exc}")
            continue

        nee_disp = str(nee_payload.get("display_name") or "")
        if nee_disp in display_names:
            violations.append(f"Display name collision between '{nee_id}' and '{display_names[nee_disp]}': '{nee_disp}'")

        nee_args = nee_payload.get("args", [])
        if isinstance(nee_args, list) and nee_args:
            nee_cron = str(nee_args[0])
            nee_crons[nee_cron] = nee_id
            if nee_cron in agents_crons:
                violations.append(
                    f"Cron schedule collision between NEE '{nee_id}' and Agents '{agents_crons[nee_cron]}': '{nee_cron}'"
                )
            nee_prompt_arg = str(nee_args[-1])
            m = PROMPT_URI_RE.search(nee_prompt_arg)
            if not m or not m.group(1).startswith(NEE_CANONICAL_ROOT):
                violations.append(
                    f"NEE sidecar '{nee_id}' no longer points to '{NEE_CANONICAL_ROOT}': {nee_prompt_arg}"
                )

        validated_nee_count += 1

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "agents_sidecar_count": validated_agents_count,
        "nee_sidecar_count": validated_nee_count,
        "collision_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents vs NEE sidecar separation invariants.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Agents repository root")
    parser.add_argument("--sidecars-root", type=Path, default=DEFAULT_SIDECARS_ROOT, help="Global sidecars root")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    result = validate_sidecar_separation(
        repo_root=args.repo_root.resolve(),
        sidecars_root=args.sidecars_root.resolve(),
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["is_clean"]:
            print(
                f"[PASS] Sidecar separation verified: {result['agents_sidecar_count']} Agents sidecars and "
                f"{result['nee_sidecar_count']} Decision Intelligence sidecars isolated with 0 collisions."
            )
        else:
            print(f"[FAIL] Sidecar separation violations ({result['collision_count']}):", file=sys.stderr)
            for v in result["violations"]:
                print(f"  - {v}", file=sys.stderr)
    return 0 if result["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
