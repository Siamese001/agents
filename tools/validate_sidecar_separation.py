#!/usr/bin/env python3
"""Mechanical validator and reconciler for Agents Repo sidecar prompt automations and cross-repo isolation.

Verifies and reconciles:
1. Disabled Manual Launcher Catalog (`INV-NO-DAILY-AGENTS-SCHEDULES` & `CATALOG_DISABLED_BY_DEFAULT`):
   - Zero active (`enabled: true`) background schedules for `agents-*` in `/Users/amitayer/.gemini/config/config.json` (`agents_scheduled_count == 0`).
   - All 8 approved `EXPECTED_AGENTS_SIDECARS` may be materialized in `/Users/amitayer/.gemini/config/sidecars/<id>/sidecar.json` as thin SSOT pointer dereferencers bound to `file:///Users/amitayer/Git/agents` (`projectId: f3cfd8ed-5fb8-40c7-b562-dbdf15522309`, `"enabled": false` in `config.json`) for manual one-click launch in the Antigravity Automations UI.
   - Any unapproved/rogue `agents-*` directory (not in `EXPECTED_AGENTS_SIDECARS`) or any `agents-*` directory missing its valid `file:///Users/amitayer/Git/agents/automations/prompts/agents_*_agent.md` pointer is rejected fail-closed.
2. Dedicated Behavioral Auditor Integrity: All 8 `automations/prompts/agents_*_agent.md` prompt specifications invoke their dedicated fail-closed behavioral auditor CLI (never generic `verify_commit.py` masquerades or print-only inline heredoc scripts).
3. Cross-Repo Firewall (`INV-REPO-SEPARATION-AGENTS-ONLY`): Every Agents prompt specification enforces `INV-REPO-SEPARATION-AGENTS-ONLY` and prohibits touching `/Users/amitayer/Git/decision-intelligence-engine`.
4. Decision Intelligence Engine Preservation: All Decision Intelligence Engine sidecars remain untouched and bound exclusively to `/Users/amitayer/Git/decision-intelligence-engine` with zero grants targeting `/Users/amitayer/Git/agents`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIDECARS_ROOT = Path.home() / ".gemini" / "config" / "sidecars"
AGENTS_CANONICAL_ROOT = str(Path.home() / "Git" / "agents")
NEE_CANONICAL_ROOT = str(Path.home() / "Git" / "decision-intelligence-engine")
AGENTS_PROJECT_ID = "f3cfd8ed-5fb8-40c7-b562-dbdf15522309"

EXPECTED_AGENTS_SIDECARS: dict[str, dict[str, Any]] = {
    "agents-storage-worktree-hygiene": {
        "display_name": "Agents Repo: Storage & Worktree Hygiene",
        "prompt_file": "agents_storage_worktree_hygiene_agent.md",
        "cron": "CRON_TZ=America/New_York 0 5 * * *",
        "disposition": "RETIRE_SIDECAR_TO_CLI",
        "target_skill": "agents-governance-hygiene",
        "deterministic_entrypoint": "tools/storage_worktree_hygiene.py",
        "requires_remediation_quota": True,
    },
    "agents-ssot-boundary-governance": {
        "display_name": "Agents Repo: SSOT & Boundary Governance",
        "prompt_file": "agents_ssot_boundary_agent.md",
        "cron": "CRON_TZ=America/New_York 20 5 * * *",
        "disposition": "RETIRE_SIDECAR_TO_HOOK",
        "target_skill": "scope-containment",
        "deterministic_entrypoint": "tools/ssot_boundary_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-core-runtime-orchestration": {
        "display_name": "Agents Repo: Core Runtime & Orchestration",
        "prompt_file": "agents_core_runtime_orchestration_agent.md",
        "cron": "CRON_TZ=America/New_York 40 5 * * *",
        "disposition": "CONSOLIDATE_WITH_RUNTIME_SKILL",
        "target_skill": "agent-runtime-engineering",
        "deterministic_entrypoint": "tools/agent_runtime_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-domain-applications-pipeline": {
        "display_name": "Agents Repo: Domain Applications & Pipelines",
        "prompt_file": "agents_domain_applications_pipeline_agent.md",
        "cron": "CRON_TZ=America/New_York 5 6 * * *",
        "disposition": "CONSOLIDATE_WITH_RETRIEVAL_SKILL",
        "target_skill": "agents-domain-assurance",
        "deterministic_entrypoint": "tools/e2e_functionality_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-research-retrieval-surface": {
        "display_name": "Agents Repo: Research & Retrieval Surface",
        "prompt_file": "agents_research_retrieval_surface_agent.md",
        "cron": "CRON_TZ=America/New_York 25 6 * * *",
        "disposition": "CONSOLIDATE_WITH_E2E_SKILL",
        "target_skill": "agents-domain-assurance",
        "deterministic_entrypoint": "tools/retrieval_surface_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-evals-judge-assurance": {
        "display_name": "Agents Repo: Evals & Judge Validity",
        "prompt_file": "agents_evals_judge_assurance_agent.md",
        "cron": "CRON_TZ=America/New_York 45 6 * * *",
        "disposition": "UPGRADE_TO_VALIDATOR_AND_SKILL",
        "target_skill": "receipt-auditor",
        "deterministic_entrypoint": "tools/validate_eval_rubrics.py",
        "requires_remediation_quota": True,
    },
    "agents-cost-token-budget": {
        "display_name": "Agents Repo: Cost & Token Budget",
        "prompt_file": "agents_cost_token_budget_agent.md",
        "cron": "CRON_TZ=America/New_York 5 7 * * *",
        "disposition": "RETIRE_SIDECAR_TO_HOOK",
        "target_skill": "operational-gates",
        "deterministic_entrypoint": "tools/cost_token_budget_auditor.py",
        "requires_remediation_quota": True,
    },
    "agents-testing-gaps-assurance": {
        "display_name": "Agents Repo: Testing Gaps Assurance",
        "prompt_file": "agents_testing_gaps_assurance_agent.md",
        "cron": "CRON_TZ=America/New_York 25 7 * * *",
        "disposition": "HYBRID_HOOK_SKILL",
        "target_skill": "testing-framework",
        "deterministic_entrypoint": "tools/testing_gaps_auditor.py",
        "requires_remediation_quota": True,
    },
}

EXPECTED_NEE_SIDECARS: tuple[str, ...] = (
    "agentic-repo-best-practices-scout",
    "corner-foresight-blindspot-scout",
    "energy-utilities-best-practices",
)

PROMPT_URI_RE = re.compile(r"file://(/[^\s\"']+?\.md)")

RETIRED_SCHEDULE_TIME_RE = re.compile(r"\b0[567]:[0-5][0-9]\s+ET\b")

REQUIRED_SHARED_CONTRACT_MARKERS: tuple[str, ...] = (
    "INV-REPO-SEPARATION-AGENTS-ONLY",
    "urn:agents:on-demand-assurance-control-matrix:2.0.0",
    "PREFLIGHT_ZERO_DEFECT_FAST_EXIT",
    "UNCONDITIONAL_WAVE_PLAN_MANDATE",
    "INV-REMEDIATION-QUOTA-FLOOR",
    "INV-DEFECT-ACCOUNTING-TABLE-GATE",
    "INV-RUNTIME-PROOF-5POINT",
    "INV-AUTOMATION-PERSISTENT-LEARNING-LOOP",
    "validate_implementation_plan.py",
    "--consolidate-sidecar",
    "--write-manifest",
    'cd "${WORKTREE_DIR}"',
    "Dimension Findings Table",
    "pr_governance.py",
)

REQUIRED_PROMPT_PARITY_MARKERS: tuple[str, ...] = (
    "INV-REPO-SEPARATION-AGENTS-ONLY",
    "urn:agents:on-demand-assurance-control-matrix:2.0.0",
    "PREFLIGHT_ZERO_DEFECT_FAST_EXIT",
    "UNCONDITIONAL_WAVE_PLAN_MANDATE",
    "INV-RUNTIME-PROOF-5POINT",
    "INV-AUTOMATION-PERSISTENT-LEARNING-LOOP",
    "Phase 0",
    "Step 0.1",
    "--consolidate-sidecar",
    "--write-manifest",
    'cd "${WORKTREE_DIR}"',
    "Phase 1",
    "Phase 1.5",
    "Phase 2",
    "Phase 3",
    "validate_implementation_plan.py",
    "Dimension Findings Table",
    "HITLDecisionStore",
    "pr_governance.py",
)


def build_agents_sidecar_payload(workflow_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Construct the thin SSOT pointer sidecar.json payload for an Agents workflow."""
    prompt_abs = f"{AGENTS_CANONICAL_ROOT}/automations/prompts/{spec['prompt_file']}"
    pointer_prompt = (
        f"Read and execute the task specification defined at file://{prompt_abs} "
        "following all rules and invariants within."
    )
    return {
        "builtin": "schedule",
        "restart_policy": "always",
        "args": [
            str(spec.get("cron") or "CRON_TZ=America/New_York 0 5 * * *"),
            "agentapi",
            "new-conversation",
            "--model=pro",
            "--",
            pointer_prompt,
        ],
        "display_name": str(spec["display_name"]),
        "agent_permissions": {
            "workspace_uris": [f"file://{AGENTS_CANONICAL_ROOT}"],
        },
    }


def reconcile_agents_sidecars(
    *,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
    project_id: str = AGENTS_PROJECT_ID,
) -> dict[str, Any]:
    """Materialize all 8 EXPECTED_AGENTS_SIDECARS as disabled manual launchers in sidecars_root and config.json."""
    sidecars_root.mkdir(parents=True, exist_ok=True)
    reconciled: list[str] = []
    for workflow_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        sc_dir = sidecars_root / workflow_id
        sc_dir.mkdir(parents=True, exist_ok=True)
        payload = build_agents_sidecar_payload(workflow_id, spec)
        (sc_dir / "sidecar.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        reconciled.append(workflow_id)

    config_file = sidecars_root.parent / "config.json"
    config_synced = 0
    if config_file.is_file():
        cfg = json.loads(config_file.read_text(encoding="utf-8"))
        sidecars_map = cfg.setdefault("sidecars", {})
        for workflow_id in EXPECTED_AGENTS_SIDECARS:
            sidecars_map[workflow_id] = {
                "enabled": False,
                "projectId": project_id,
            }
            config_synced += 1
        config_file.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        try:
            os.utime(config_file, None)
        except OSError:
            pass

    try:
        os.utime(sidecars_root, None)
    except OSError:
        pass

    return {
        "reconciled_count": len(reconciled),
        "reconciled_sidecars": reconciled,
        "config_synced": config_synced,
    }


def validate_sidecar_separation(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
) -> dict[str, Any]:
    """Validate disabled manual launchers, zero active background schedules, dedicated auditors, and repo isolation."""
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

    # 2. Validate all 8 on-demand Agents prompt specs and dedicated behavioral auditor entrypoints
    validated_prompts_count = 0
    for workflow_id, spec in EXPECTED_AGENTS_SIDECARS.items():
        if not workflow_id.startswith("agents-"):
            violations.append(f"{workflow_id}: Missing mandatory 'agents-' workflow prefix")

        if not spec.get("requires_remediation_quota", False):
            violations.append(
                f"{workflow_id}: requires_remediation_quota must be True across all 8 assurance workflows (C04)"
            )

        det_ep = str(spec.get("deterministic_entrypoint") or "")
        if not det_ep or det_ep == "tools/verify_commit.py":
            violations.append(
                f"{workflow_id}: deterministic_entrypoint must be a dedicated behavioral auditor, not '{det_ep}'"
            )

        local_prompt = prompts_dir / spec["prompt_file"]
        if not local_prompt.is_file():
            violations.append(f"{workflow_id}: missing repository prompt file {local_prompt}")
        else:
            p_text = local_prompt.read_text(encoding="utf-8")
            for marker in REQUIRED_PROMPT_PARITY_MARKERS:
                if marker not in p_text:
                    violations.append(f"{spec['prompt_file']}: missing mandatory parity marker '{marker}'")
            if det_ep and Path(det_ep).name not in p_text:
                violations.append(
                    f"{spec['prompt_file']}: missing mandatory invocation of dedicated behavioral auditor '{det_ep}'"
                )
            if "<<'PY'" in p_text or '<<"PY"' in p_text:
                violations.append(
                    f"{spec['prompt_file']}: contains inline heredoc script instead of fail-closed auditor CLI"
                )
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
            if RETIRED_SCHEDULE_TIME_RE.search(p_text) or "MODE: scheduled" in p_text:
                violations.append(
                    f"{spec['prompt_file']}: retains retired daily cron timestamp or 'MODE: scheduled' boilerplate"
                )
            p15_idx = p_text.find("Phase 1.5")
            cons_idx = p_text.find("--consolidate-sidecar")
            if p15_idx != -1 and cons_idx != -1 and cons_idx < p15_idx:
                violations.append(
                    f"{spec['prompt_file']}: invokes --consolidate-sidecar before Phase 1.5 read-only preflight"
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

        if det_ep and (repo_root.resolve() / "tools").is_dir() and not (repo_root.resolve() / det_ep).is_file():
            violations.append(
                f"{workflow_id}: declared deterministic_entrypoint '{det_ep}' missing under {repo_root.resolve()}"
            )

    routing_doc = repo_root / ".agents" / "rules" / "sidecar-automation-routing.md"
    if routing_doc.is_file():
        routing_text = routing_doc.read_text(encoding="utf-8")
        for workflow_id, spec in EXPECTED_AGENTS_SIDECARS.items():
            det_ep = str(spec.get("deterministic_entrypoint") or "")
            if det_ep and det_ep not in routing_text:
                violations.append(
                    f".agents/rules/sidecar-automation-routing.md: missing canonical checker '{det_ep}' for {workflow_id}"
                )

    hygiene_skill = repo_root / ".agents" / "skills" / "agents-governance-hygiene" / "SKILL.md"
    if hygiene_skill.is_file():
        skill_text = hygiene_skill.read_text(encoding="utf-8")
        if "PREFLIGHT_ZERO_DEFECT_FAST_EXIT" not in skill_text:
            violations.append(
                ".agents/skills/agents-governance-hygiene/SKILL.md: missing PREFLIGHT_ZERO_DEFECT_FAST_EXIT read-only gate"
            )

    # 3. Validate sidecars_root and config.json:
    #    - Approved EXPECTED_AGENTS_SIDECARS may exist as disabled manual launchers pointing to AGENTS_CANONICAL_ROOT
    #    - Any unapproved agents-* directory or active (enabled: true) schedule is a fail-closed violation
    #    - NEE sidecars must never reference AGENTS_CANONICAL_ROOT
    agents_scheduled_count = 0
    agents_catalog_count = 0
    validated_nee_count = 0
    if sidecars_root.is_dir():
        for child in sorted(sidecars_root.iterdir()):
            if not child.is_dir():
                continue
            sc_file = child / "sidecar.json"
            if child.name.startswith("agents-"):
                if child.name not in EXPECTED_AGENTS_SIDECARS:
                    agents_scheduled_count += 1
                    violations.append(
                        f"Unapproved background schedule directory '{child.name}' present in {sidecars_root}; "
                        f"Agents checks must run via pre-save gates and on-demand skills only"
                    )
                    continue
                if not sc_file.is_file():
                    agents_scheduled_count += 1
                    violations.append(f"Agents sidecar '{child.name}' missing sidecar.json")
                    continue
                try:
                    ag_payload = json.loads(sc_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    agents_scheduled_count += 1
                    violations.append(f"Agents sidecar '{child.name}' invalid JSON: {exc}")
                    continue
                ag_args = ag_payload.get("args", [])
                expected_prompt_file = EXPECTED_AGENTS_SIDECARS[child.name]["prompt_file"]
                expected_uri = f"file://{AGENTS_CANONICAL_ROOT}/automations/prompts/{expected_prompt_file}"
                ws_uris = (ag_payload.get("agent_permissions") or {}).get("workspace_uris") or []
                if (
                    not isinstance(ag_args, list)
                    or not ag_args
                    or expected_uri not in str(ag_args[-1])
                    or ws_uris != [f"file://{AGENTS_CANONICAL_ROOT}"]
                ):
                    agents_scheduled_count += 1
                    violations.append(
                        f"Unapproved background schedule directory '{child.name}' present in {sidecars_root} "
                        f"with invalid pointer or workspace_uris"
                    )
                    continue
                if NEE_CANONICAL_ROOT in json.dumps(ag_payload):
                    agents_scheduled_count += 1
                    violations.append(
                        f"Agents sidecar '{child.name}' references forbidden NEE path '{NEE_CANONICAL_ROOT}'"
                    )
                    continue
                agents_catalog_count += 1
                continue

            if not sc_file.is_file():
                continue
            try:
                nee_payload = json.loads(sc_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
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
                for sid, s_cfg in sorted(registered_sidecars.items()):
                    if sid.startswith("agents-") or sid in EXPECTED_AGENTS_SIDECARS:
                        if sid not in EXPECTED_AGENTS_SIDECARS:
                            agents_scheduled_count += 1
                            violations.append(
                                f"Global config.json retains unapproved schedule entry '{sid}'; remove to enforce on-demand only"
                            )
                        elif not isinstance(s_cfg, dict) or s_cfg.get("enabled") is not False:
                            agents_scheduled_count += 1
                            violations.append(
                                f"Global config.json retains active background schedule entry '{sid}' (enabled must be false)"
                            )
        except (OSError, json.JSONDecodeError) as exc:
            violations.append(f"Invalid JSON in global config.json: {exc}")

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "agents_scheduled_count": agents_scheduled_count,
        "agents_catalog_count": agents_catalog_count,
        "agents_prompt_count": validated_prompts_count,
        "agents_sidecar_count": validated_prompts_count,
        "nee_sidecar_count": validated_nee_count,
        "collision_count": len(violations),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents on-demand separation and mirrored disabled sidecars.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Agents repository root")
    parser.add_argument("--sidecars-root", type=Path, default=DEFAULT_SIDECARS_ROOT, help="Global sidecars root")
    parser.add_argument("--reconcile", action="store_true", help="Materialize disabled manual launchers in sidecars-root")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    if args.reconcile:
        reconcile_agents_sidecars(sidecars_root=args.sidecars_root.resolve())

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
                f"{result['agents_catalog_count']} disabled manual launchers, "
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
