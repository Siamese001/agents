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
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterator, NamedTuple, Sequence

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
_PRUNED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".worktrees",
        ".runtime",
        "node_modules",
    }
)
_PRUNED_REL_TREES: frozenset[str] = frozenset(
    {
        "artifacts",
        "resume_graph_engine/artifacts",
        "outreach_engine/artifacts",
        "resume_graph_engine/models",
        "resume_graph_engine/data",
        "outreach_engine/runs",
    }
)


class _ParsedPyEntry(NamedTuple):
    lines: list[str]
    tree: ast.AST | None


def _iter_py_files(base: Path, repo_root: Path, *, skip_tests: bool = False) -> Iterator[Path]:
    """Yield sorted Python files under `base`, pruning non-source runtime/cache/venv trees."""
    if not base.exists():
        return
    if base.is_file():
        if base.suffix == ".py":
            yield base
        return
    root_resolved = repo_root.resolve()
    collected: list[Path] = []
    for cur_root, dirs, files in os.walk(base, topdown=True, followlinks=False):
        cur_path = Path(cur_root)
        kept_dirs: list[str] = []
        for dname in sorted(dirs):
            if dname in _PRUNED_DIR_NAMES:
                continue
            if skip_tests and dname == "tests":
                continue
            cand = cur_path / dname
            try:
                rel = cand.resolve().relative_to(root_resolved).as_posix()
            except ValueError:
                rel = ""
            if rel in _PRUNED_REL_TREES:
                continue
            kept_dirs.append(dname)
        dirs[:] = kept_dirs
        for fname in sorted(files):
            if fname.endswith(".py"):
                collected.append(cur_path / fname)
    yield from sorted(collected)


def _get_parsed_py(py: Path, cache: dict[Path, _ParsedPyEntry]) -> _ParsedPyEntry:
    cached = cache.get(py)
    if cached is not None:
        return cached
    lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        tree: ast.AST | None = ast.parse("\n".join(lines), filename=str(py))
    except SyntaxError:
        tree = None
    entry = _ParsedPyEntry(lines=lines, tree=tree)
    cache[py] = entry
    return entry


def audit_cross_subsystem_encapsulation(
    repo_root: Path,
    *,
    parse_cache: dict[Path, _ParsedPyEntry] | None = None,
) -> list[dict[str, Any]]:
    """Verify zero illegal direct imports between outreach_engine and resume_engine / resume_graph_engine."""
    cache = parse_cache if parse_cache is not None else {}
    violations: list[dict[str, Any]] = []
    for rel_dir in SUBSYSTEM_TARGETS:
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for py in _iter_py_files(base, repo_root, skip_tests=True):
            if "tests" in py.parts:
                continue
            entry = _get_parsed_py(py, cache)
            if entry.tree is None:
                continue
            for node in ast.walk(entry.tree):
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


def audit_constitutional_ast_floor(
    repo_root: Path,
    *,
    parse_cache: dict[Path, _ParsedPyEntry] | None = None,
) -> dict[str, list[str]]:
    """Scan packages and tools/ for subprocess calls missing timeout= and unguarded bare Exception."""
    cache = parse_cache if parse_cache is not None else {}
    missing_timeouts: list[str] = []
    unguarded_exceptions: list[str] = []

    for rel_dir in SUBPROCESS_SCAN_DIRS:
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for py in _iter_py_files(base, repo_root, skip_tests=True):
            if "tests" in py.parts:
                continue
            entry = _get_parsed_py(py, cache)
            if entry.tree is None:
                continue
            lines = entry.lines
            rel_str = str(py.relative_to(repo_root))
            for node in ast.walk(entry.tree):
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


def _compute_ratchet_backlog(repo_root: Path, drift: dict[str, Any]) -> dict[str, int]:
    """Quantify grandfathered ratchet debt and physical config/data duplication so backlog is never hidden."""
    env_ratchet_files = 0
    env_ratchet_path = repo_root / "config" / "governance" / "env_lookup_ratchet.json"
    if env_ratchet_path.is_file():
        try:
            env_doc = json.loads(env_ratchet_path.read_text(encoding="utf-8"))
            fc = env_doc.get("file_counts", {}) if isinstance(env_doc, dict) else {}
            env_ratchet_files = sum(1 for v in fc.values() if isinstance(v, int) and v > 0)
        except (OSError, ValueError, TypeError):
            pass

    budget_total_files = 0
    budget_prod_files = 0
    budget_ratchet_path = repo_root / "config" / "governance" / "file_budgets_ratchet.json"
    if budget_ratchet_path.is_file():
        try:
            bdoc = json.loads(budget_ratchet_path.read_text(encoding="utf-8"))
            if isinstance(bdoc, dict):
                budget_total_files = len(bdoc)
                budget_prod_files = sum(
                    1 for k in bdoc if "/tests/" not in f"/{k}" and not Path(k).name.startswith("test_")
                )
        except (OSError, ValueError, TypeError):
            pass

    dup_configs = len(drift.get("identical", []))
    dup_data = int(drift.get("data_identical_count", 0))
    total = env_ratchet_files + budget_prod_files + dup_configs + dup_data
    return {
        "env_lookup_ratchet_files": env_ratchet_files,
        "file_budget_ratchet_prod_files": budget_prod_files,
        "file_budget_ratchet_total_files": budget_total_files,
        "duplicate_config_pairs": dup_configs,
        "duplicate_data_pairs": dup_data,
        "total_backlog_items": total,
    }


def run_ssot_boundary_audit(
    *,
    repo_root: Path = REPO_ROOT,
    sidecars_root: Path = DEFAULT_SIDECARS_ROOT,
    include_ratchet_backlog: bool = False,
) -> dict[str, Any]:
    """Execute the 10-dimension SSOT, boundary, config drift, and governance sync audit."""
    root = repo_root.resolve()
    parse_cache: dict[Path, _ParsedPyEntry] = {}

    dim1_cross = audit_cross_subsystem_encapsulation(root, parse_cache=parse_cache)

    layer_violations: list[str] = []
    for prod_dir in LAYER_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in _iter_py_files(d, root, skip_tests=True):
                entry = _get_parsed_py(py, parse_cache)
                if entry.tree is None:
                    continue
                for lineno, mod, msg in check_file_layer_imports(py, root, tree=entry.tree, lines=entry.lines):
                    layer_violations.append(f"{py.relative_to(root)}:{lineno}: {mod} ({msg})")

    purity_violations: list[str] = []
    for prod_dir in PURITY_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in _iter_py_files(d, root, skip_tests=True):
                entry = _get_parsed_py(py, parse_cache)
                if entry.tree is None:
                    continue
                for lineno, cat, msg in check_file_production_purity(py, root, tree=entry.tree, lines=entry.lines):
                    purity_violations.append(f"{py.relative_to(root)}:{lineno}: [{cat}] {msg}")

    ast_tree_cache: dict[Path, ast.AST | None] = {p: e.tree for p, e in parse_cache.items()}
    arch_res = run_architecture_linter(root, ast_cache=ast_tree_cache)
    dim2_issues = layer_violations + purity_violations
    if not arch_res["is_clean"]:
        for cname, cdata in arch_res["checks"].items():
            dim2_issues.extend(f"{cname}: {v}" for v in cdata.get("violations", []))

    model_neutral_violations: list[str] = []
    for prod_dir in MODEL_PROD_DIRS:
        d = root / prod_dir
        if d.exists():
            for py in _iter_py_files(d, root, skip_tests=True):
                entry = _get_parsed_py(py, parse_cache)
                if entry.tree is None:
                    continue
                for lineno, tok, msg in check_file_model_neutrality(py, root, tree=entry.tree, lines=entry.lines):
                    model_neutral_violations.append(f"{py.relative_to(root)}:{lineno}: {tok} ({msg})")

    pin_findings = audit_model_pins(root)
    drift = analyze_drift(root)
    drift_issues = [f"config:{x}" for x in drift.get("unallowlisted_differing", [])] + [
        f"data:{x}" for x in drift.get("data_differing", [])
    ]
    dim3_issues = model_neutral_violations + [f"{f['file']}::{f['key']}: {f['message']}" for f in pin_findings] + drift_issues

    ast_floor = audit_constitutional_ast_floor(root, parse_cache=parse_cache)
    dim4_issues = ast_floor["missing_timeouts"] + ast_floor["unguarded_exceptions"]

    dim5_issues = audit_mcp_hooks_and_links(root)
    separation = validate_sidecar_separation(repo_root=root, sidecars_root=sidecars_root)
    sprawl_scan = run_sprawl_scan(root)
    ast_tree_cache.update({p: e.tree for p, e in parse_cache.items()})
    hardcoding_scan = run_hardcoding_scan(root, ast_cache=ast_tree_cache)

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
    ratchet_backlog = _compute_ratchet_backlog(root, drift)
    dims_clean = all(v == "PASS" for v in dimension_status.values())
    backlog_blocks = include_ratchet_backlog and ratchet_backlog["total_backlog_items"] > 0
    is_clean = dims_clean and not backlog_blocks
    status = "PASS" if is_clean else ("BACKLOG_ACTION_REQUIRED" if dims_clean else "FAIL")
    return {
        "status": status,
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
        "ratchet_backlog": ratchet_backlog,
        "sidecar_separation": separation,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run 10-dimension SSOT, centralization, sprawl & subsystem boundary governance audit."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--sidecars-root", type=Path, default=DEFAULT_SIDECARS_ROOT, help="Global sidecars root")
    parser.add_argument(
        "--include-ratchet-backlog",
        action="store_true",
        help="Treat grandfathered env/file-budget ratchets and duplicate config/data pairs as active remediation backlog.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output file path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args(argv)

    report = run_ssot_boundary_audit(
        repo_root=args.repo_root,
        sidecars_root=args.sidecars_root,
        include_ratchet_backlog=args.include_ratchet_backlog,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] 10-Dimension SSOT, Centralization & Boundary Audit "
            f"(config_identical={report['config_identical_count']}, "
            f"centralization_defects={report['total_centralization_defects']}, "
            f"ratchet_backlog={report['ratchet_backlog']['total_backlog_items']})"
        )

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
