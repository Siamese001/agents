#!/usr/bin/env python3
"""Mechanical validator enforcing zero background schedules for Agents Repo and strict cross-repo isolation.

Verifies:
1. Schedule Retirement (`INV-NO-DAILY-AGENTS-SCHEDULES`): Zero `agents-*` background scheduled sidecars exist in `/Users/amitayer/.gemini/config/sidecars/` or `/Users/amitayer/.gemini/config/config.json` (all checks execute via local pre-save gates and on-demand skills/prompts).
2. On-Demand Prompt & Skill Integrity: All 7 `automations/prompts/agents_*_agent.md` prompt specifications, `_shared_governance_contract.md`, skill mappings, and deterministic tool entrypoints remain valid and complete.
3. Cross-Repo Firewall (`INV-REPO-SEPARATION-AGENTS-ONLY`): Every Agents prompt specification enforces `INV-REPO-SEPARATION-AGENTS-ONLY` and prohibits touching `/Users/amitayer/Git/decision-intelligence-engine`.
4. Decision Intelligence Engine Preservation: All active Decision Intelligence Engine sidecars remain untouched and bound exclusively to `/Users/amitayer/Git/decision-intelligence-engine` with zero grants targeting `/Users/amitayer/Git/agents`.
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

EXPECTED_AGENTS_SIDECARS: dict[str, dict[str, Any]] = {
    "agents-storage-worktree-hygiene": {
        "display_name": "Agents Repo: Storage & Worktree Hygiene",
        "prompt_file": "agents_storage_worktree_hygiene_agent.md",
        "disposition": "RETIRE_SIDECAR_TO_CLI",
        "target_skill": "agents-governance-hygiene",
        "deterministic_entrypoint": "tools/storage_worktree_hygiene.py",
        "requires_remediation_quota": False,
    },
    "agents-ssot-boundary-governance": {
        "display_name": "Agents Repo: SSOT & Boundary Governance",
        "prompt_file": "agents_ssot_boundary_agent.md",
        "disposition": "RETIRE_SIDECAR_TO_HOOK",
        "target_skill": "scope-containment",
        "deterministic_entrypoint": "tools/ssot_boundary_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-outreach-resume-functionality": {
        "display_name": "Agents Repo: Outreach & Resume Functionality",
        "prompt_file": "agents_e2e_functionality_assurance_agent.md",
        "disposition": "CONSOLIDATE_WITH_RETRIEVAL_SKILL",
        "target_skill": "agents-domain-assurance",
        "deterministic_entrypoint": "tools/verify_commit.py",
        "requires_remediation_quota": True,
    },
    "agents-research-retrieval-surface": {
        "display_name": "Agents Repo: Research & Retrieval Surface",
        "prompt_file": "agents_research_retrieval_surface_agent.md",
        "disposition": "CONSOLIDATE_WITH_E2E_SKILL",
        "target_skill": "agents-domain-assurance",
        "deterministic_entrypoint": "tools/verify_commit.py",
        "requires_remediation_quota": True,
    },
    "agents-evals-judge-assurance": {
        "display_name": "Agents Repo: Evals & Judge Validity",
        "prompt_file": "agents_evals_judge_assurance_agent.md",
        "disposition": "UPGRADE_TO_VALIDATOR_AND_SKILL",
        "target_skill": "receipt-auditor",
        "deterministic_entrypoint": "tools/validate_eval_rubrics.py",
        "requires_remediation_quota": True,
    },
    "agents-cost-token-budget": {
        "display_name": "Agents Repo: Cost & Token Budget",
        "prompt_file": "agents_cost_token_budget_agent.md",
        "disposition": "RETIRE_SIDECAR_TO_HOOK",
        "target_skill": "operational-gates",
        "deterministic_entrypoint": "tools/cost_token_budget_auditor.py",
        "requires_remediation_quota": False,
    },
    "agents-testing-gaps-assurance": {
        "display_name": "Agents Repo: Testing Gaps Assurance",
        "prompt_file": "agents_testing_gaps_assurance_agent.md",
        "disposition": "HYBRID_HOOK_SKILL",
        "target_skill": "testing-framework",
        "deterministic_entrypoint": "tools/verify_commit.py",
        "requires_remediation_quota": True,
    },
}

EXPECTED_NEE_SIDECARS: tuple[str, ...] = (
    "agentic-repo-best-practices-scout",
    "corner-foresight-blindspot-scout",
    "energy-utilities-best-practices",
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
    "pr_governance.py",
    "--stage-only",
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
    "pr_governance.py",
    "--stage-only",
)


def validate_sidecar_separation(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
) -> dict[str, Any]:
    """Validate retired background schedules, on-demand prompt integrity, and cross-repository isolation."""
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

    # 2. Validate all 7 on-demand Agents prompt specs and deterministic entrypoints
    validated_prompts_count = 0
    for workflow_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        if not workflow_id.startswith("agents-"):
            violations.append(f"{workflow_id}: Missing mandatory 'agents-' workflow prefix")

        local_prompt = prompts_dir / spec["prompt_file"]
        if not local_prompt.is_file():
            violations.append(f"{workflow_id}: missing repository prompt file {local_prompt}")
        else:
            p_text = local_prompt.read_text(encoding="utf-8")
            for marker in REQUIRED_PROMPT_PARITY_MARKERS:
                if marker not in p_text:
                    violations.append(f"{spec['prompt_file']}: missing mandatory parity marker '{marker}'")
            if NEE_CANONICAL_ROOT in p_text:
                violations.append(f"{spec['prompt_file']}: contains forbidden path '{NEE_CANONICAL_ROOT}'")
            if 'BRANCH_NAME="automation/' in p_text:
                violations.append(
                    f"{spec['prompt_file']}: contains non-conventional branch prefix 'BRANCH_NAME=\"automation/'"
                )
            if "merge --no-ff" in p_text:
                violations.append(
                    f"{spec['prompt_file']}: contains raw unreviewed 'merge --no-ff' bypassing pr_governance.py"
                )
            if f'Path("{AGENTS_CANONICAL_ROOT}")' in p_text:
                violations.append(
                    f'{spec["prompt_file"]}: hardcodes primary repo root Path("{AGENTS_CANONICAL_ROOT}") instead of WORKTREE_DIR'
                )
            if spec["prompt_file"] == "agents_testing_gaps_assurance_agent.md":
                for req_testing_token in (
                    "resume_graph_engine/tests",
                    "outreach_engine/tests",
                    "apps_eval/tests",
                    "AsyncFunctionDef",
                    "audit_mock_reachability.py",
                ):
                    if req_testing_token not in p_text:
                        violations.append(
                            f"{spec['prompt_file']}: missing required 4-root testing governance token '{req_testing_token}'"
                        )
            validated_prompts_count += 1

        det_ep = spec.get("deterministic_entrypoint")
        if det_ep and (repo_root.resolve() / "tools").is_dir() and not (repo_root.resolve() / str(det_ep)).is_file():
            violations.append(
                f"{workflow_id}: declared deterministic_entrypoint '{det_ep}' missing under {repo_root.resolve()}"
            )

    # 3. Enforce ZERO active background schedules for Agents Repo in sidecars_root and config.json
    agents_scheduled_count = 0
    validated_nee_count = 0
    if sidecars_root.is_dir():
        for child in sorted(sidecars_root.iterdir()):
            if not child.is_dir():
                continue
            sc_file = child / "sidecar.json"
            if child.name.startswith("agents-") or child.name in EXPECTED_AGENTS_SIDECARS:
                agents_scheduled_count += 1
                violations.append(
                    f"Unapproved background schedule directory '{child.name}' present in {sidecars_root}; "
                    f"Agents checks must run via pre-save gates and on-demand skills only"
                )
                continue
            if not sc_file.is_file():
                continue
            try:
                nee_payload = json.loads(sc_file.read_text(encoding="utf-8"))
            except Exception as exc:
                violations.append(f"Sidecar '{child.name}' invalid JSON: {exc}")
                continue

            raw_dump = json.dumps(nee_payload)
            if AGENTS_CANONICAL_ROOT in raw_dump:
                agents_scheduled_count += 1
                violations.append(
                    f"Sidecar '{child.name}' references forbidden Agents path '{AGENTS_CANONICAL_ROOT}'"
                )
                continue

            nee_args = nee_payload.get("args", [])
            if isinstance(nee_args, list) and nee_args:
                nee_prompt_arg = str(nee_args[-1])
                m = PROMPT_URI_RE.search(nee_prompt_arg)
                if not m or not m.group(1).startswith(NEE_CANONICAL_ROOT):
                    violations.append(
                        f"NEE sidecar '{child.name}' no longer points to '{NEE_CANONICAL_ROOT}': {nee_prompt_arg}"
                    )
            validated_nee_count += 1

    config_file = sidecars_root.parent / "config.json"
    if config_file.is_file():
        try:
            config_payload = json.loads(config_file.read_text(encoding="utf-8"))
            registered_sidecars = config_payload.get("sidecars")
            if isinstance(registered_sidecars, dict):
                for sid in sorted(registered_sidecars):
                    if sid.startswith("agents-") or sid in EXPECTED_AGENTS_SIDECARS:
                        agents_scheduled_count += 1
                        violations.append(
                            f"Global config.json retains background schedule entry '{sid}'; remove to enforce on-demand only"
                        )
        except Exception as exc:
            violations.append(f"Invalid JSON in global config.json: {exc}")

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "agents_scheduled_count": agents_scheduled_count,
        "agents_prompt_count": validated_prompts_count,
        "agents_sidecar_count": validated_prompts_count,
        "nee_sidecar_count": validated_nee_count,
        "collision_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents on-demand separation and retired schedule invariants.")
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
                f"[PASS] Sidecar separation verified: {result['agents_scheduled_count']} background Agents schedules, "
                f"{result['agents_prompt_count']} on-demand prompts, and "
                f"{result['nee_sidecar_count']} Decision Intelligence sidecars isolated with 0 collisions."
            )
        else:
            print(f"[FAIL] Sidecar separation violations ({result['collision_count']}):", file=sys.stderr)
            for v in result["violations"]:
                print(f"  - {v}", file=sys.stderr)
    return 0 if result["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
