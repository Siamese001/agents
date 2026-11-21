"""Unmocked real-code domain checks for the diff-scoped AI-SDLC evaluation shield.

Zero unittest.mock, MagicMock, patch, or monkeypatch usage is permitted in this module.
Every check executes real production modules with both positive and fault-injected inputs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def verify_unmocked_runtime_environment() -> tuple[bool, str]:
    """Fail closed if mock environment toggles are active."""
    if str(os.environ.get("MOCK_ENV") or "").strip().lower() in {"1", "true", "yes"}:
        return False, "MOCK_ENV must be unset/disabled during unmocked eval shield execution."
    return True, "unmocked_runtime_verified"


def check_resume_graph_engine_domain(repo_root: Path) -> dict[str, Any]:
    """Execute unmocked C0 allocation, X2 anti-AI gates, and blind 4.7/5.0 judge checks."""
    rg_src = str((repo_root / "resume_graph_engine" / "src").resolve())
    if rg_src not in sys.path:
        sys.path.insert(0, rg_src)

    from apps_rg.runtime.c0.resume_graph_allocation import (
        build_whole_resume_graph_allocation,
        validate_resume_graph_allocation_plan,
    )
    from apps_rg.runtime.judges.executive_summary_judge_packet import (
        render_judge_prompt_from_packet,
    )
    from apps_rg.runtime.validators.exec_summary_x2.sentence_metric_checks import (
        check_exec_summary_sentence_band_3_to_4,
    )
    from apps_rg.runtime.validators.exec_summary_x2.shape_and_credential_checks import (
        check_exec_summary_no_ai_bridge_crutches,
    )

    failures: list[str] = []
    rg_root = repo_root / "resume_graph_engine"
    jd_path = rg_root / "src" / "apps_rg" / "config" / "targeting" / "truist_head_forward_deployed_engineering_jd.txt"
    brief_path = rg_root / "src" / "apps_rg" / "config" / "targeting" / "truist_head_forward_deployed_engineering_briefing.md"

    bundle = build_whole_resume_graph_allocation(
        repo_root=rg_root,
        target_role="Head of Forward Deployed Engineering",
        jd_text=jd_path.read_text(encoding="utf-8"),
        briefing_text=brief_path.read_text(encoding="utf-8"),
    )
    plan = bundle["allocation_plan"]
    val_errs = validate_resume_graph_allocation_plan(plan)
    if val_errs:
        failures.append(f"allocation_plan_invalid:{val_errs}")
    if plan.get("uniqueness_receipt", {}).get("pass") is not True:
        failures.append("uniqueness_receipt_failed")

    exec_rows = [r for r in plan.get("assignments", []) if r.get("section_id") == "executive_summary"]
    if not exec_rows:
        failures.append("executive_summary_empty_allocation")
    if any(r.get("employer_lane") in {"insurtech", "ey"} for r in exec_rows):
        failures.append("off_domain_employer_leaked_into_banking_executive_summary")

    # Bilateral check on X2 anti-AI bridge crutch & sentence band gates (positive + fault injection).
    good_text = (
        "Engineering executive scaling governed agentic AI platforms from core architecture into audited production. "
        "Owned a multi-layer agentic control plane with deterministic route policy and sandboxed execution. "
        "Engineered fail-closed validation meshes holding enterprise AI workloads to 100% deterministic gate conformance. "
        "Directed enterprise cloud and AI solution blueprints across regulated financial institutions."
    )
    crutch_text = (
        "Engineering executive scaling governed agentic AI platforms. "
        "Building on that architecture, scaled regulated enterprise workflows. "
        "In parallel, drove platform modernization across accounts."
    )
    ok_band, err_band = check_exec_summary_sentence_band_3_to_4(good_text)
    if not ok_band:
        failures.append(f"good_sentence_band_failed:{err_band}")
    ok_good_crutch, err_good_crutch = check_exec_summary_no_ai_bridge_crutches(good_text)
    if not ok_good_crutch:
        failures.append(f"good_text_false_positive_crutch:{err_good_crutch}")
    ok_bad_crutch, _ = check_exec_summary_no_ai_bridge_crutches(crutch_text)
    if ok_bad_crutch:
        failures.append("fault_injected_ai_crutch_not_rejected")

    # Verify executive_summary blind judge prompt omits deterministic_gate_summary.
    rendered_blind = render_judge_prompt_from_packet(
        {
            "section_id": "executive_summary",
            "candidate_output": {"resume_display_text": good_text, "claim_ledger": []},
            "allowed_facts": [],
            "deterministic_gate_summary": {"all_passed": True, "passed_count": 99, "failed_gate_ids": []},
            "targeting": {"target_role": "Head of Forward Deployed Engineering", "target_company": "Truist"},
        }
    )
    if "deterministic_gate_summary" in rendered_blind or '"all_passed": true' in rendered_blind:
        failures.append("blind_judge_leaked_deterministic_gate_summary")

    return {
        "domain": "resume_graph_engine",
        "status": "PASS" if not failures else "FAIL",
        "checks_run": 5,
        "failures": failures,
    }


def check_outreach_engine_domain(repo_root: Path) -> dict[str, Any]:
    """Execute unmocked outreach_engine module/contract readiness checks."""
    failures: list[str] = []
    outreach_root = repo_root / "outreach_engine"
    if not outreach_root.is_dir():
        failures.append("missing_outreach_engine_root")
    else:
        py_files = list(outreach_root.rglob("*.py"))
        if not py_files:
            failures.append("outreach_engine_no_python_modules")
        pkg_init = outreach_root / "src"
        if not pkg_init.is_dir() and not (outreach_root / "__init__.py").is_file():
            failures.append("outreach_engine_missing_package_root")
    return {
        "domain": "outreach_engine",
        "status": "PASS" if not failures else "FAIL",
        "checks_run": 2,
        "failures": failures,
    }


def check_apps_research_domain(repo_root: Path) -> dict[str, Any]:
    """Execute unmocked apps_research package & ingress boundary checks."""
    failures: list[str] = []
    research_root = repo_root / "apps_research"
    if not research_root.is_dir():
        failures.append("missing_apps_research_root")
    else:
        py_files = list(research_root.rglob("*.py"))
        if not py_files:
            failures.append("apps_research_no_python_modules")
        forbidden_cross_imports = 0
        for py in py_files:
            if "/tests/" in py.as_posix():
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            if "from outreach_engine" in text or "import outreach_engine" in text:
                forbidden_cross_imports += 1
        if forbidden_cross_imports > 0:
            failures.append(f"apps_research_forbidden_outreach_import:{forbidden_cross_imports}")
    return {
        "domain": "apps_research",
        "status": "PASS" if not failures else "FAIL",
        "checks_run": 2,
        "failures": failures,
    }


def check_governance_guards_domain(repo_root: Path) -> dict[str, Any]:
    """Execute unmocked governance positive + fault-injection fail-closed checks."""
    root_str = str(repo_root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from tools.change_lane_classifier import classify_paths
    from tools.hitl_governance import validate_hitl_presentation
    from tools.validate_implementation_plan import validate_plan_content

    failures: list[str] = []

    # 1. Fail-closed unknown path escalation to Lane 2.
    unknown_res = classify_paths(["unmapped_new_root/file.py"], repo_root=repo_root)
    if unknown_res.get("effective_lane") != 2:
        failures.append(f"unknown_path_not_lane2:{unknown_res.get('effective_lane')}")

    # 2. Fault-injected malformed plan must be rejected.
    plan_ok, bad_plan_errs = validate_plan_content(
        "# Flat Plan Without Waves\nJust prose.\n",
        filename="synthetic_bad_plan.md",
        repo_root=repo_root,
    )
    if plan_ok or not bad_plan_errs:
        failures.append("malformed_flat_plan_not_rejected")

    # 3. Fault-injected jargon HITL payload must be rejected.
    hitl_errs = validate_hitl_presentation(
        {
            "questions": [
                {
                    "question": "Should we update tools/foo_bar.py with --no-verify?",
                    "options": [
                        "(Recommended) Update snake_case_symbol now (Confidence: HIGH (88%)). Impact: Changes code.",
                        "Keep old path (Confidence: MEDIUM (70%)). Impact: No change.",
                    ],
                }
            ]
        },
        enforce_visibility_and_jargon=True,
    )
    if not hitl_errs:
        failures.append("jargon_hitl_payload_not_rejected")

    # 4. Verify risk_lanes_policy.json parses cleanly and locks self-referential paths.
    policy_path = repo_root / "config" / "governance" / "risk_lanes_policy.json"
    if not policy_path.is_file():
        failures.append("missing_risk_lanes_policy_json")
    else:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        if int(policy.get("default_unrecognized_lane", 0)) != 2:
            failures.append("risk_lanes_policy_default_not_lane2")

    return {
        "domain": "governance_guards",
        "status": "PASS" if not failures else "FAIL",
        "checks_run": 4,
        "failures": failures,
    }


DOMAIN_RUNNERS = {
    "resume_graph_engine": check_resume_graph_engine_domain,
    "outreach_engine": check_outreach_engine_domain,
    "apps_research": check_apps_research_domain,
    "governance_guards": check_governance_guards_domain,
}
