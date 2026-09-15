#!/usr/bin/env python3
"""Mechanical Turn-Gate Validator for Antigravity Agents Workspace.

Enforces pre-turn (hooks presence, operating contract bound, runtime boundary, tool integrity)
and post-turn (HITL ambiguity margin, model neutrality, scratchpad transparency) gates.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_TIER1_TOOLS = (
    "hitl_governance.py",
    "lint_file_budgets.py",
    "lint_layer_imports.py",
    "lint_model_neutral_naming.py",
    "lint_secrets.py",
    "unified_agent_architecture.py",
    "validate_implementation_plan.py",
    "verify_commit.py",
)

REQUIRED_AGENTS_HEADERS = [
    "Plan First. Execute Second.",
    "Wave Refactoring Protocol",
    "Constitutional floor",
    "Pytest",
    "Antigravity Execution Adapter",
]


def validate_pre_turn_gate(repo_root: Path | None = None) -> dict[str, Any]:
    """Execute all pre-turn gate checks.

    Returns:
        Structured result dictionary with status 'PASS' or 'FAIL'.
    """
    root = Path(repo_root or ROOT).resolve()
    issues: list[str] = []
    checks: dict[str, Any] = {}

    # Check 1: Governance hooks presence and completeness
    hooks_path = root / ".agents" / "hooks.json"
    if not hooks_path.is_file():
        issues.append(f"Hooks configuration missing: {hooks_path}")
        checks["hooks_configuration"] = {"status": "FAIL"}
    else:
        try:
            hooks_data = json.loads(hooks_path.read_text(encoding="utf-8"))
            hook_count = len(hooks_data.get("hooks", []))
            checks["hooks_configuration"] = {
                "status": "PASS" if hook_count >= 7 else "FAIL",
                "hook_count": hook_count,
            }
            if hook_count < 7:
                issues.append(f"Expected >= 7 governance hooks, found {hook_count}")
        except Exception as exc:
            issues.append(f"Invalid hooks JSON: {exc}")
            checks["hooks_configuration"] = {"status": "FAIL", "error": str(exc)}

    # Check 2: Root agent operating contract & memory bound (<=200 lines)
    operating_contract = validate_agent_operating_contract(root)
    checks["operating_contract"] = operating_contract
    if operating_contract["status"] != "PASS":
        issues.extend(operating_contract["issues"])

    # Check 3: Runtime boundary configuration
    boundary_path = root / ".antigravity" / "runtime-boundary.json"
    if not boundary_path.is_file():
        issues.append(f"Runtime boundary configuration missing: {boundary_path}")
        checks["runtime_boundary"] = {"status": "FAIL"}
    else:
        try:
            boundary_data = json.loads(boundary_path.read_text(encoding="utf-8"))
            checks["runtime_boundary"] = {
                "status": "PASS",
                "boundary_rules": len(boundary_data.get("rules", boundary_data.get("boundary", {}))),
            }
        except Exception as exc:
            issues.append(f"Invalid runtime-boundary JSON: {exc}")
            checks["runtime_boundary"] = {"status": "FAIL", "error": str(exc)}

    # Check 4: Tier 1 verification tools presence
    tools_dir = root / "tools"
    missing_tools = [t for t in REQUIRED_TIER1_TOOLS if not (tools_dir / t).is_file()]
    if missing_tools:
        issues.append(f"Missing required Tier 1 tools in tools/: {missing_tools}")
        checks["tier1_tools"] = {"status": "FAIL", "missing": missing_tools}
    else:
        checks["tier1_tools"] = {"status": "PASS", "tools_count": len(REQUIRED_TIER1_TOOLS)}

    # Check 5: Conformance map integrity
    conformance_path = root / ".agents" / "rules" / "conformance-map.md"
    if not conformance_path.is_file():
        issues.append(f"Conformance map missing: {conformance_path}")
        checks["conformance_map"] = {"status": "FAIL"}
    else:
        conf_text = conformance_path.read_text(encoding="utf-8")
        has_stale_headers = "(AGENTS.md L" in conf_text
        checks["conformance_map"] = {
            "status": "FAIL" if has_stale_headers else "PASS",
            "has_stale_headers": has_stale_headers,
        }
        if has_stale_headers:
            issues.append("Conformance map contains stale hardcoded line-number headers.")

    overall_status = "PASS" if not issues else "FAIL"
    return {
        "gate": "PRE_TURN",
        "status": overall_status,
        "issues": issues,
        "checks": checks,
    }


def validate_agent_operating_contract(repo_root: Path | None = None) -> dict[str, Any]:
    """Validate root AGENTS.md concise memory bounds (<=200 lines) and structural integrity."""
    root = Path(repo_root or ROOT).resolve()
    issues: list[str] = []

    agents_md = root / "AGENTS.md"
    if not agents_md.is_file():
        issues.append("AGENTS.md missing at repository root.")
        return {"status": "FAIL", "issues": issues, "line_count": 0}

    text = agents_md.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > 200:
        issues.append(f"AGENTS.md exceeds recommended 200 lines memory bound ({len(lines)} lines).")

    for header in REQUIRED_AGENTS_HEADERS:
        if header not in text:
            issues.append(f"AGENTS.md missing required section: '{header}'")

    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "issues": issues,
        "line_count": len(lines),
    }


def evaluate_hitl_ambiguity(
    options: Sequence[dict[str, Any]],
    margin_threshold: float = 0.20,
) -> dict[str, Any]:
    """Evaluate candidate HITL options against the calibrated 20% ambiguity margin rule.

    If delta = c_top - c_second > margin_threshold:
        Decision is decisively resolved; agent should proceed autonomously.
    If delta <= margin_threshold:
        Decision is genuinely ambiguous; agent must surface atomic HITL.
    """
    if not options:
        return {
            "requires_hitl": False,
            "status": "EMPTY",
            "top_option": None,
            "margin": 0.0,
            "recommendation": "No options evaluated.",
        }

    scored = []
    for opt in options:
        score = float(opt.get("confidence_score", opt.get("confidence", 0.0)))
        scored.append((score, opt))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_opt = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = round(top_score - second_score, 4)

    requires_hitl = margin <= margin_threshold
    return {
        "requires_hitl": requires_hitl,
        "margin": margin,
        "margin_threshold": margin_threshold,
        "top_option": top_opt,
        "second_score": second_score,
        "top_score": top_score,
        "action": "SURFACE_HITL_ATOMIC" if requires_hitl else "PROCEED_AUTONOMOUSLY",
        "recommendation": (
            f"Margin Δ = {margin:.2%} is within {margin_threshold:.0%}: surface atomic HITL decision."
            if requires_hitl
            else f"Margin Δ = {margin:.2%} is > {margin_threshold:.0%}: proceed autonomously with top option."
        ),
    }


def validate_scratchpad_transparency(markdown_text: str) -> dict[str, Any]:
    """Verify that an agent response includes a compliant Reasoning Scratchpad & Telemetry block."""
    issues: list[str] = []
    has_header = (
        "Agent Reasoning Scratchpad" in markdown_text
        or "### 🧠" in markdown_text
        or "<scratchpad>" in markdown_text
    )
    if not has_header:
        issues.append("Missing mandatory 'Agent Reasoning Scratchpad' header.")

    has_model = any(k in markdown_text for k in ("Active Model", "Model ID", "Model & Provider", "Provider", "FRONTIER_"))
    if not has_model:
        issues.append("Missing Pillar 1: Active Model & Provider telemetry.")

    has_thinking = any(k in markdown_text for k in ("Cognitive Breakdown", "Thinking Deliberation", "Thinking & Deliberation", "Thinking:"))
    if not has_thinking:
        issues.append("Missing Pillar 2: Cognitive Breakdown & Thinking Deliberation.")

    has_steps = "Reasoning Steps" in markdown_text
    if not has_steps:
        issues.append("Missing Pillar 3: Ordered Reasoning Steps.")

    has_tools = any(k in markdown_text for k in ("API & Tool Invocations", "Tool Invocations", "API Calls", "Tool:"))
    if not has_tools:
        issues.append("Missing Pillar 4: API & Tool Invocations audit.")

    return {
        "status": "PASS" if not issues else "FAIL",
        "has_header": has_header,
        "has_model_telemetry": has_model,
        "has_cognitive_thinking": has_thinking,
        "has_reasoning_steps": has_steps,
        "has_tool_invocations": has_tools,
        "issues": issues,
    }


def validate_post_turn_gate(
    repo_root: Path | None = None,
    candidate_response: str | None = None,
    candidate_options: Sequence[dict[str, Any]] | None = None,
    require_scratchpad: bool = False,
) -> dict[str, Any]:
    """Execute all post-turn gate checks."""
    root = Path(repo_root or ROOT).resolve()
    issues: list[str] = []
    checks: dict[str, Any] = {}

    # Check 1: HITL Ambiguity Margin Check
    if candidate_options is not None:
        hitl_eval = evaluate_hitl_ambiguity(candidate_options)
        checks["hitl_ambiguity"] = hitl_eval
        if not hitl_eval["requires_hitl"] and candidate_response:
            if "### HITL Decision" in candidate_response:
                issues.append(
                    f"Surfaced HITL decision when margin was {hitl_eval['margin']:.2%} (> 20%). "
                    "Must proceed autonomously under recorded receipt."
                )

    # Check 2: Scratchpad transparency verification
    if candidate_response and (require_scratchpad or "Agent Reasoning Scratchpad" in candidate_response):
        scratchpad_eval = validate_scratchpad_transparency(candidate_response)
        checks["scratchpad_transparency"] = scratchpad_eval
        issues.extend(scratchpad_eval["issues"])

    overall_status = "PASS" if not issues else "FAIL"
    return {
        "gate": "POST_TURN",
        "status": overall_status,
        "issues": issues,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Pre-Turn and Post-Turn governance gates.")
    parser.add_argument(
        "--mode",
        choices=["pre-turn", "post-turn", "all"],
        default="all",
        help="Gate mode to evaluate.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
        help="Repository root path.",
    )
    args = parser.parse_args(argv)

    results: dict[str, Any] = {}
    exit_code = 0

    if args.mode in ("pre-turn", "all"):
        pre_result = validate_pre_turn_gate(args.repository_root)
        results["pre_turn"] = pre_result
        if pre_result["status"] != "PASS":
            exit_code = 1

    if args.mode in ("post-turn", "all"):
        post_result = validate_post_turn_gate(args.repository_root)
        results["post_turn"] = post_result
        if post_result["status"] != "PASS":
            exit_code = 1

    print(json.dumps(results, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
