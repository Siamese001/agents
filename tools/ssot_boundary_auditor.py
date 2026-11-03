#!/usr/bin/env python3
"""Agents Repository — 10-Dimension SSOT, Centralization, Sprawl & Subsystem Boundary Auditor.

Implements the deterministic Stage II (`Order 2/7`) boundary, config sprawl, anti-hardcoding,
prompt-to-code parity, policy registry sync, constitutional floor, MCP/hook portability, and
link-integrity auditor declared in `automations/prompts/agents_ssot_boundary_agent.md` and
`tools/validate_sidecar_separation.py`.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.check_config_ssot_drift import analyze_drift
from tools.lint_architecture_boundaries import run_architecture_linter
from tools.lint_layer_imports import PRODUCTION_DIRECTORIES as LAYER_PROD_DIRS, check_file_layer_imports
from tools.lint_model_neutral_naming import (
    PRODUCTION_DIRECTORIES as MODEL_PROD_DIRS,
    check_file_model_neutrality,
)
from tools.lint_model_pins import audit_model_pins
from tools.lint_production_purity import (
    PRODUCTION_DIRECTORIES as PURITY_PROD_DIRS,
    check_file_production_purity,
)
from tools.ssot_hardcoding_scanner import run_hardcoding_scan
from tools.ssot_sprawl_scanner import run_sprawl_scan
from tools.validate_sidecar_separation import DEFAULT_SIDECARS_ROOT, validate_sidecar_separation
from tools.validate_turn_gates import validate_pre_turn_gate

SUBSYSTEM_TARGETS: tuple[str, ...] = (
    "agents",
    "apps_model_telemetry",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "apps_research",
    "apps_eval",
    "infrastructure",
    "ops_scripts",
    "scripts",
)
SUBPROCESS_SCAN_DIRS: tuple[str, ...] = SUBSYSTEM_TARGETS + ("tools",)
GUARDIAN_COMMENT_RE = re.compile(r"#\s*guardian:", re.IGNORECASE)


def audit_cross_subsystem_encapsulation(repo_root: Path) -> list[dict[str, Any]]:
    """Verify zero illegal direct imports between outreach_engine and resume_engine / resume_graph_engine."""
    violations: list[dict[str, Any]] = []
    for rel_dir in SUBSYSTEM_TARGETS:
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            if "tests" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                elif isinstance(node, ast.Import):
                    mods.extend(alias.name for alias in node.names)
                for mod in mods:
                    if rel_dir.startswith("outreach_engine") and mod.startswith(
                        ("resume_engine", "resume_graph_engine", "apps_rg")
                    ):
                        violations.append(
                            {"file": str(py.relative_to(repo_root)), "line": node.lineno, "illegal_import": mod}
                        )
                    elif rel_dir.startswith(("resume_engine", "resume_graph_engine")) and mod.startswith(
                        ("outreach_engine", "apps_lic")
                    ):
                        violations.append(
                            {"file": str(py.relative_to(repo_root)), "line": node.lineno, "illegal_import": mod}
                        )
                    elif rel_dir == "infrastructure" and mod.startswith(
                        ("outreach_engine", "apps_lic", "resume_engine", "resume_graph_engine", "apps_rg")
                    ):
                        violations.append(
                            {"file": str(py.relative_to(repo_root)), "line": node.lineno, "illegal_import": mod}
                        )
    return violations


def audit_constitutional_ast_floor(repo_root: Path) -> dict[str, list[str]]:
    """Scan packages and tools/ for subprocess calls missing timeout= and unguarded bare Exception."""
    missing_timeouts: list[str] = []
    unguarded_exceptions: list[str] = []

    for rel_dir in SUBPROCESS_SCAN_DIRS:
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            if "tests" in py.parts:
                continue
            lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
            try:
                tree = ast.parse("\n".join(lines))
            except SyntaxError:
                continue
            rel_str = str(py.relative_to(repo_root))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                        and node.func.attr in ("run", "call", "check_call", "check_output")
                    ):
                        has_timeout = any(kw.arg == "timeout" for kw in node.keywords) or any(
                            kw.arg is None for kw in node.keywords
                        )
                        if not has_timeout:
                            missing_timeouts.append(f"{rel_str}:{node.lineno}: subprocess.{node.func.attr} missing timeout=")
                elif isinstance(node, ast.ExceptHandler):
                    if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                        line_txt = lines[node.lineno - 1] if 0 <= node.lineno - 1 < len(lines) else ""
                        prev_txt = lines[node.lineno - 2] if 0 <= node.lineno - 2 < len(lines) else ""
                        has_guardian = bool(GUARDIAN_COMMENT_RE.search(line_txt) or GUARDIAN_COMMENT_RE.search(prev_txt))
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass) and not has_guardian:
                            unguarded_exceptions.append(f"{rel_str}:{node.lineno}: silent 'except Exception: pass' without guardian")

    return {"missing_timeouts": missing_timeouts, "unguarded_exceptions": unguarded_exceptions}


def audit_mcp_hooks_and_links(repo_root: Path) -> list[str]:
    """Verify portable MCP launchers, runtime boundary subsystems, and AGENTS.md / conformance-map links."""
    issues: list[str] = []
    for mcp_rel in (".mcp.json", ".agents/mcp_config.json"):
        mcp_path = repo_root / mcp_rel
        if not mcp_path.is_file():
            issues.append(f"Missing MCP configuration file: {mcp_rel}")
            continue
        raw = mcp_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        for srv_name, srv_cfg in (data.get("mcpServers") or {}).items():
            if isinstance(srv_cfg, dict) and srv_cfg.get("command") == "cmd":
                issues.append(f"{mcp_rel}::{srv_name}: non-portable Windows 'cmd' launcher")
        if "C:\\Git\\" in raw:
            issues.append(f"{mcp_rel}: hardcoded Windows C:\\Git\\ path")

    for md_rel in ("AGENTS.md", ".agents/rules/conformance-map.md"):
        md_path = repo_root / md_rel
        if not md_path.is_file():
            issues.append(f"Missing governance document: {md_rel}")
            continue
        text = md_path.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]+\]\((?!https?://|file://|conversation://)([^)#]+)", text):
            target = m.group(1).strip()
            resolved = (repo_root / target).resolve() if (repo_root / target).exists() else (md_path.parent / target).resolve()
            if not resolved.exists():
                issues.append(f"{md_rel}: broken link target '{target}'")

    pre_turn = validate_pre_turn_gate(repo_root)
    if pre_turn["status"] != "PASS":
        issues.extend(f"pre_turn_gate: {iss}" for iss in pre_turn.get("issues", []))

    return issues


def run_ssot_boundary_audit(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
) -> dict[str, Any]:
    """Execute the 6-dimension SSOT, boundary, config drift, and governance sync audit."""
    root = repo_root.resolve()

    dim1_cross = audit_cross_subsystem_encapsulation(root)

    layer_violations: list[str] = []
    for prod_dir in LAYER_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in sorted(d.rglob("*.py")):
                for lineno, mod, msg in check_file_layer_imports(py, root):
                    layer_violations.append(f"{py.relative_to(root)}:{lineno}: {mod} ({msg})")

    purity_violations: list[str] = []
    for prod_dir in PURITY_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in sorted(d.rglob("*.py")):
                for lineno, cat, msg in check_file_production_purity(py, root):
                    purity_violations.append(f"{py.relative_to(root)}:{lineno}: [{cat}] {msg}")

    arch_res = run_architecture_linter(root)
    dim2_issues = layer_violations + purity_violations
    if not arch_res["is_clean"]:
        for cname, cdata in arch_res["checks"].items():
            dim2_issues.extend(f"{cname}: {v}" for v in cdata.get("violations", []))

    model_neutral_violations: list[str] = []
    for prod_dir in MODEL_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in sorted(d.rglob("*.py")):
                for lineno, tok, msg in check_file_model_neutrality(py, root):
                    model_neutral_violations.append(f"{py.relative_to(root)}:{lineno}: {tok} ({msg})")

    pin_findings = audit_model_pins(root)
    drift = analyze_drift(root)
    drift_issues = [f"config:{x}" for x in drift.get("unallowlisted_differing", [])] + [
        f"data:{x}" for x in drift.get("data_differing", [])
    ]
    dim3_issues = model_neutral_violations + [f"{f['file']}::{f['key']}: {f['message']}" for f in pin_findings] + drift_issues

    ast_floor = audit_constitutional_ast_floor(root)
    dim4_issues = ast_floor["missing_timeouts"] + ast_floor["unguarded_exceptions"]

    dim5_issues = audit_mcp_hooks_and_links(root)
    separation = validate_sidecar_separation(repo_root=root, sidecars_root=sidecars_root)
    sprawl_scan = run_sprawl_scan(root)
    hardcoding_scan = run_hardcoding_scan(root)

    dim7_sprawl_count = int(sprawl_scan.get("total_findings", 0))
    dim8_policy_sync = hardcoding_scan.get("policy_registry_sync_issues", [])
    dim9_hardcoded = hardcoding_scan.get("hardcoded_threshold_literals", []) + hardcoding_scan.get(
        "ast_hygiene_and_env_sprawl", []
    )
    dim10_parity = hardcoding_scan.get("prompt_code_parity_issues", [])
    total_centralization_defects = (
        dim7_sprawl_count + len(dim8_policy_sync) + len(dim9_hardcoded) + len(dim10_parity)
    )

    dimension_status = {
        "dim_1_cross_subsystem_encapsulation": "PASS" if not dim1_cross else "FAIL",
        "dim_2_layer_and_purity_boundaries": "PASS" if not dim2_issues else "FAIL",
        "dim_3_model_pins_and_ssot_drift": "PASS" if not dim3_issues else "FAIL",
        "dim_4_constitutional_ast_floor": "PASS" if not dim4_issues else "FAIL",
        "dim_5_mcp_hooks_and_conformance_links": "PASS" if not dim5_issues else "FAIL",
        "dim_6_sidecar_separation": "PASS" if separation["is_clean"] else "FAIL",
        "dim_7_multi_folder_config_sprawl": "PASS" if dim7_sprawl_count == 0 else "FAIL",
        "dim_8_policy_registry_synchronization": "PASS" if not dim8_policy_sync else "FAIL",
        "dim_9_unowned_hardcoded_thresholds": "PASS" if not dim9_hardcoded else "FAIL",
        "dim_10_prompt_to_code_numeric_parity": "PASS" if not dim10_parity else "FAIL",
    }
    is_clean = all(v == "PASS" for v in dimension_status.values())
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "repo_root": str(root),
        "dimension_status": dimension_status,
        "cross_subsystem_violations": dim1_cross,
        "layer_and_purity_issues": dim2_issues,
        "model_and_drift_issues": dim3_issues,
        "constitutional_floor_issues": dim4_issues,
        "mcp_hooks_link_issues": dim5_issues,
        "config_sprawl_scan": sprawl_scan,
        "hardcoding_and_parity_scan": hardcoding_scan,
        "total_centralization_defects": total_centralization_defects,
        "config_identical_count": len(drift.get("identical", [])),
        "data_identical_count": drift.get("data_identical_count", 0),
        "sidecar_separation": separation,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run 10-dimension SSOT, centralization, sprawl & subsystem boundary governance audit."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--sidecars-root", type=Path, default=DEFAULT_SIDECARS_ROOT, help="Global sidecars root")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output file path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args(argv)

    report = run_ssot_boundary_audit(repo_root=args.repo_root, sidecars_root=args.sidecars_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] 10-Dimension SSOT, Centralization & Boundary Audit "
            f"(config_identical={report['config_identical_count']}, "
            f"centralization_defects={report['total_centralization_defects']})"
        )

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
