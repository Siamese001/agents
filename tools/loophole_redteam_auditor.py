#!/usr/bin/env python3
"""Adversarial Anti-BS & Loophole Red-Team Auditor & Counterfactual Mutation Engine.

Implements the deterministic 4-pillar scanner backing `.agents/skills/loophole-redteam-assurance/SKILL.md`:
- Pillar R1 (Mock, Stub & Canned-Fallback Hunter): LH-01, LH-03
- Pillar R2 (Fake-Test, Tautology & Fake-Coverage Hunter): LH-06, LH-07, LH-08
- Pillar R3 (Fake-Scan, Dead-Flag & Guard-Theater Hunter): LH-04, LH-05, LH-11, LH-12 (guardian tags)
- Pillar R4 (Agent-Prompt, Sandbox & Gate-Bypass Hunter): LH-02, LH-07 (branch prefix), LH-09, LH-10, LH-12 (precedent floor)

Also provides `--counterfactual-self-test`, which materializes ephemeral temporary sandboxes
containing all 12 planted loophole archetypes (`LH-01`..`LH-12`) plus a clean control repo,
proving fail-closed sensitivity (12/12 caught) and specificity (0 false positives on clean controls).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv
from tools.unified_agent_architecture import (
    contract_to_subagent_config,
    validate_delegation_contract,
)

bootstrap_shared_venv(REPO_ROOT)

PRODUCTION_ROOTS: tuple[str, ...] = (
    "agents",
    "apps_eval",
    "apps_model_telemetry",
    "apps_research",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "scripts",
    "tools",
)

TEST_ROOTS: tuple[str, ...] = (
    "tests",
    "resume_graph_engine/tests",
    "outreach_engine/tests",
    "apps_eval/tests",
    "scripts/local_llm",
    "resume_graph_engine/src/apps_rg/evals",
)

ALL_LOOPHOLE_IDS: tuple[str, ...] = (
    "LH-01",
    "LH-02",
    "LH-03",
    "LH-04",
    "LH-05",
    "LH-06",
    "LH-07",
    "LH-08",
    "LH-09",
    "LH-10",
    "LH-11",
    "LH-12",
)

_SIMULATED_ADAPTER_LITERALS: frozenset[str] = frozenset(
    {
        "simulated_default",
        "simulated-v1",
        "fake_default",
        "dummy_provider",
        "stub_provider",
    }
)
_MOCK_INSPECTION_ATTRS: frozenset[str] = frozenset({"mock_calls", "assert_called", "assert_called_once"})
_FORBIDDEN_MOCK_IMPORTS: frozenset[str] = frozenset({"unittest.mock", "mock"})
_FORBIDDEN_MOCK_SYMBOLS: frozenset[str] = frozenset({"MagicMock", "AsyncMock", "Mock", "patch", "monkeypatch", "mock"})
_GUARDIAN_LINE_RE = re.compile(r"#\s*guardian\s*:(.*)$", re.IGNORECASE)
_GUARDIAN_STRICT_RE = re.compile(r"^\s*(allow-[a-z][a-z0-9-]+)\s+--\s+(.+)$")

REDTEAM_SUBAGENT_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "task_id": "redteam-r1-mock-hunter",
        "parent_task_id": "loophole-redteam-coordinator",
        "objective": "Audit all 11 production roots for reachable simulated adapters, mock escape hatches, and canned SUCCESS fallbacks.",
        "scope_in": [
            "agents/",
            "apps_eval/",
            "apps_research/",
            "infrastructure/",
            "outreach_engine/",
            "resume_engine/",
            "resume_graph_engine/",
        ],
        "scope_out": ["No tracked file edits", "No external repository access"],
        "allowed_tools": ["read_file", "run_command"],
        "deliverable": {
            "format": "JSON",
            "target_path": "artifacts/governance/redteam_r1_mock_findings.json",
        },
        "definition_of_done": "Every R1 finding includes file, line, loophole_id, and counterfactual reproduction proof.",
        "budget": {"max_turns": 8, "max_tool_calls": 20, "timeout_seconds": 180},
        "escalation_rule": "Escalate to coordinator if confidence margin between real loophole and legitimate test seam is <= 20%.",
    },
    {
        "task_id": "redteam-r2-fake-test-hunter",
        "parent_task_id": "loophole-redteam-coordinator",
        "objective": "Audit all 6 test roots and testing-gap coverage logic for tautologies, pass-or-fail checks, mocked E2E masquerades, and name-collision coverage.",
        "scope_in": [
            "tests/",
            "resume_graph_engine/tests/",
            "outreach_engine/tests/",
            "apps_eval/tests/",
            "tools/testing_gaps_auditor.py",
        ],
        "scope_out": ["No tracked file edits", "No external repository access"],
        "allowed_tools": ["read_file", "run_command"],
        "deliverable": {
            "format": "JSON",
            "target_path": "artifacts/governance/redteam_r2_fake_test_findings.json",
        },
        "definition_of_done": "All tautological assertions, mocked high-assurance suites, and fake-coverage paths are cataloged with exact line references.",
        "budget": {"max_turns": 8, "max_tool_calls": 20, "timeout_seconds": 180},
        "escalation_rule": "Escalate to coordinator when a mock-guard unit test requires reclassification rather than deletion.",
    },
    {
        "task_id": "redteam-r3-fake-scan-hunter",
        "parent_task_id": "loophole-redteam-coordinator",
        "objective": "Audit deterministic linters, construct-validity scanners, and guardian exemptions using counterfactual fault injection.",
        "scope_in": [
            "tools/",
            "apps_eval/construct_validity.py",
            "config/governance/guardian_exemption_registry.yaml",
        ],
        "scope_out": ["No tracked file edits", "No external repository access"],
        "allowed_tools": ["read_file", "run_command"],
        "deliverable": {
            "format": "JSON",
            "target_path": "artifacts/governance/redteam_r3_fake_scan_findings.json",
        },
        "definition_of_done": "Counterfactual self-test proves 12/12 planted defects fail closed and clean controls yield 0 false positives.",
        "budget": {"max_turns": 8, "max_tool_calls": 20, "timeout_seconds": 180},
        "escalation_rule": "Escalate to coordinator if any scanner exemption ceiling requires policy registry sign-off.",
    },
    {
        "task_id": "redteam-r4-agent-bypass-hunter",
        "parent_task_id": "loophole-redteam-coordinator",
        "objective": "Audit the 7 on-demand assurance agents, flywheel sandbox preflights, readiness gates, and runtime prose/precedent guards for bypass loopholes.",
        "scope_in": [
            "automations/prompts/",
            "agents/orchestration/services/",
            "agents/context/precedent_bridge.py",
            "tools/verify_main_readiness.py",
            "tools/run_eval_flywheel_cycle.py",
        ],
        "scope_out": ["No tracked file edits", "No external repository access"],
        "allowed_tools": ["read_file", "run_command"],
        "deliverable": {
            "format": "JSON",
            "target_path": "artifacts/governance/redteam_r4_agent_bypass_findings.json",
        },
        "definition_of_done": "All prompt, sandbox, branch-prefix, and readiness-receipt bypass vectors are documented with remediation wave targets.",
        "budget": {"max_turns": 8, "max_tool_calls": 20, "timeout_seconds": 180},
        "escalation_rule": "Escalate to coordinator if closing a gate bypass conflicts with an active readiness lane definition.",
    },
)


@dataclass(frozen=True)
class LoopholeFinding:
    """Single deterministic anti-BS / loophole finding."""

    pillar: str
    loophole_id: str
    code: str
    severity: str
    file: str
    line: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_redteam_subagent_contracts() -> list[str]:
    """Verify all 4 red-team subagent contracts satisfy the 10-field schema and strict read-only tools."""
    errors: list[str] = []
    forbidden_write_tools = {"write_file", "edit_file", "write_to_file", "replace_file_content", "create_file"}
    for contract in REDTEAM_SUBAGENT_CONTRACTS:
        tid = str(contract.get("task_id") or "<unknown>")
        c_errs = validate_delegation_contract(contract)
        for err in c_errs:
            errors.append(f"{tid}: {err}")
        tools = {str(t) for t in contract.get("allowed_tools") or ()}
        overlap = sorted(tools & forbidden_write_tools)
        if overlap:
            errors.append(f"{tid}: Red-team read-only contract cannot declare write tools: {overlap}")
        if not c_errs:
            cfg = contract_to_subagent_config(contract)
            if not cfg.name:
                errors.append(f"{tid}: SubagentConfig projection produced empty name")
    return errors


def load_guardian_exemption_registry(repo_root: Path) -> dict[str, Any]:
    """Load `config/governance/guardian_exemption_registry.yaml` with deterministic fallback defaults."""
    reg_path = repo_root / "config" / "governance" / "guardian_exemption_registry.yaml"
    defaults: dict[str, Any] = {
        "allowed_exemption_types": [
            "allow-silent-swallow",
            "allow-broad-exception",
            "allow-broad-exception-cleanup",
            "allow-return-none-swallow",
            "allow-return-empty-dict",
            "allow-log-and-swallow",
            "allow-default-fallback",
            "allow-model-id",
            "allow-chokepoint-bypass",
            "allow-layer-violation",
            "allow-exception-type-erasure",
            "allow-retry-without-backoff",
            "allow-otel-optional",
            "allow-missing-hitl-on-irreversible",
            "allow-magic-config",
            "allow-path-string",
            "allow-fixture",
            "allow-secret",
            "allow-pass",
        ],
        "syntax_contract": {"min_justification_chars": 8},
    }
    if not reg_path.is_file():
        return defaults
    import yaml  # type: ignore[import-untyped]

    parsed = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else defaults


def _iter_prod_py_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for rel_root in PRODUCTION_ROOTS:
        base = repo_root / rel_root
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if any(p in py.parts for p in ("tests", "__pycache__", ".venv", "artifacts", "docs", "fixtures")):
                continue
            if py.name.startswith("test_") or py.name.endswith("_test.py"):
                continue
            files.append(py)
    return files


def _iter_test_py_files(repo_root: Path) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for rel_root in TEST_ROOTS:
        base = repo_root / rel_root
        if not base.is_dir():
            continue
        for py in sorted({*base.rglob("test_*.py"), *base.rglob("*_test.py")}):
            if "__pycache__" in py.parts or ".venv" in py.parts:
                continue
            resolved = py.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(py)
    return files


def _safe_parse_ast(file_path: Path) -> tuple[str, list[str], ast.Module | None, str | None]:
    try:
        src = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "", [], None, f"OSError: {exc}"
    lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError as exc:
        return src, lines, None, f"SyntaxError:{exc.lineno or 1}: {exc.msg}"
    return src, lines, tree, None


def scan_r1_mock_and_canned_fallbacks(repo_root: Path) -> list[LoopholeFinding]:
    """Pillar R1: Detect simulated production adapters and mock-attribute escape hatches (LH-01, LH-03)."""
    root = repo_root.resolve()
    findings: list[LoopholeFinding] = []
    scanner_self_paths = frozenset({"tools/loophole_redteam_auditor.py", "tools/audit_mock_reachability.py"})

    for py in _iter_prod_py_files(root):
        rel = py.relative_to(root).as_posix()
        if rel in scanner_self_paths:
            continue
        _src, _lines, tree, err = _safe_parse_ast(py)
        if err or tree is None:
            findings.append(
                LoopholeFinding("R1", "LH-01", "PROD_SYNTAX_ERROR", "HIGH", rel, 1, err or "Parse failure")
            )
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.strip().lower()
                if low in _SIMULATED_ADAPTER_LITERALS:
                    findings.append(
                        LoopholeFinding(
                            "R1",
                            "LH-01",
                            "SIMULATED_PROD_ADAPTER_LITERAL",
                            "CRITICAL",
                            rel,
                            getattr(node, "lineno", 1),
                            f"Production module embeds simulated adapter literal '{node.value}'.",
                        )
                    )
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "hasattr" and len(node.args) >= 2:
                    attr_arg = node.args[1]
                    if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                        if attr_arg.value in _MOCK_INSPECTION_ATTRS:
                            findings.append(
                                LoopholeFinding(
                                    "R1",
                                    "LH-03",
                                    "PROD_MOCK_ESCAPE_HATCH",
                                    "CRITICAL",
                                    rel,
                                    node.lineno,
                                    f"Production code inspects mock attribute '{attr_arg.value}' via hasattr().",
                                )
                            )
    return findings


def _file_uses_mock_ast(tree: ast.Module) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _FORBIDDEN_MOCK_IMPORTS or alias.name.startswith("unittest.mock"):
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = str(node.module or "")
            if mod in _FORBIDDEN_MOCK_IMPORTS or mod.startswith("unittest.mock"):
                hits.append((node.lineno, mod))
            for alias in node.names:
                if alias.name in _FORBIDDEN_MOCK_SYMBOLS:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (*node.args.args, *node.args.kwonlyargs):
                if arg.arg == "monkeypatch":
                    hits.append((node.lineno, "monkeypatch"))
    return hits


def scan_r2_fake_tests_and_coverage(repo_root: Path) -> list[LoopholeFinding]:
    """Pillar R2: Detect tautological tests, mocked E2E/live-LLM masquerades, and flat coverage (LH-06, LH-07, LH-08)."""
    root = repo_root.resolve()
    findings: list[LoopholeFinding] = []

    for py in _iter_test_py_files(root):
        rel = py.relative_to(root).as_posix()
        _src, _lines, tree, err = _safe_parse_ast(py)
        if err or tree is None:
            findings.append(
                LoopholeFinding("R2", "LH-06", "TEST_SYNTAX_ERROR", "HIGH", rel, 1, err or "Parse failure")
            )
            continue

        # 1. Tautological & pass-or-fail assertions (LH-06)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            test_expr = node.test
            if isinstance(test_expr, ast.Constant) and test_expr.value is True:
                findings.append(
                    LoopholeFinding(
                        "R2",
                        "LH-06",
                        "TAUTOLOGICAL_ASSERT_TRUE",
                        "HIGH",
                        rel,
                        node.lineno,
                        "Literal 'assert True' provides zero behavioral verification.",
                    )
                )
            elif isinstance(test_expr, ast.Compare) and len(test_expr.ops) == 1 and len(test_expr.comparators) == 1:
                op = test_expr.ops[0]
                right = test_expr.comparators[0]
                if isinstance(op, ast.Eq) and ast.dump(test_expr.left) == ast.dump(right):
                    findings.append(
                        LoopholeFinding(
                            "R2",
                            "LH-06",
                            "TAUTOLOGICAL_SELF_COMPARE",
                            "HIGH",
                            rel,
                            node.lineno,
                            "Tautological equality comparing an expression to itself.",
                        )
                    )
                elif isinstance(op, ast.In) and isinstance(right, (ast.List, ast.Tuple, ast.Set)):
                    vals = {c.value for c in right.elts if isinstance(c, ast.Constant)}
                    left_dump = ast.dump(test_expr.left).lower()
                    if {0, 1}.issubset(vals) and any(k in left_dump for k in ("returncode", "exit_code", "rc")):
                        findings.append(
                            LoopholeFinding(
                                "R2",
                                "LH-06",
                                "VACUOUS_EXIT_CODE_ASSERTION",
                                "HIGH",
                                rel,
                                node.lineno,
                                "Assertion accepts both exit code 0 (pass) and 1 (fail).",
                            )
                        )
                    elif {"PASS", "FAIL"}.issubset(vals) or {True, False}.issubset(vals):
                        if not any(k in left_dump for k in ("is_current", "flag", "bit")):
                            findings.append(
                                LoopholeFinding(
                                    "R2",
                                    "LH-06",
                                    "VACUOUS_PASS_OR_FAIL_ASSERTION",
                                    "HIGH",
                                    rel,
                                    node.lineno,
                                    "Assertion accepts both passing and failing outcomes.",
                                )
                            )

        # 2. Mocked high-assurance E2E / live-LLM suites (LH-07)
        low_rel = rel.lower()
        fname_low = Path(low_rel).name
        is_e2e_or_live = (
            "/end_to_end/" in f"/{low_rel}"
            or "live_llm" in fname_low
            or ("/unit/" not in f"/{low_rel}" and (fname_low.endswith("_e2e.py") or "_e2e_" in fname_low))
        )
        if is_e2e_or_live:
            mock_hits = _file_uses_mock_ast(tree)
            if mock_hits:
                first_line, sym = mock_hits[0]
                findings.append(
                    LoopholeFinding(
                        "R2",
                        "LH-07",
                        "MOCKED_E2E_OR_LIVE_LLM_MASQUERADE",
                        "CRITICAL",
                        rel,
                        first_line,
                        f"High-assurance E2E/live-LLM test imports or uses mock primitive '{sym}'.",
                    )
                )

    # 3. Inspect tools/testing_gaps_auditor.py for flat global name-collision coverage & substring handoff check (LH-08)
    tga_path = root / "tools" / "testing_gaps_auditor.py"
    if tga_path.is_file():
        src, lines, _tree, _err = _safe_parse_ast(tga_path)
        for idx, ln in enumerate(lines, 1):
            if "sym in referenced_symbols" in ln and "import" not in ln.lower():
                findings.append(
                    LoopholeFinding(
                        "R2",
                        "LH-08",
                        "FLAT_NAME_COLLISION_COVERAGE",
                        "HIGH",
                        "tools/testing_gaps_auditor.py",
                        idx,
                        "Global flat `sym in referenced_symbols` credits untested modules on common method names.",
                    )
                )
            if 'for tok in ("apps_rg_handoff"' in ln or "for tok in (" in ln and "tok in src" in "\n".join(lines[max(0, idx - 3) : idx + 3]):
                if "tok in src" in ln:
                    findings.append(
                        LoopholeFinding(
                            "R2",
                            "LH-08",
                            "SUBSTRING_HANDOFF_COVERAGE_CHECK",
                            "HIGH",
                            "tools/testing_gaps_auditor.py",
                            idx,
                            "Pillar 2 handoff check relies on raw `tok in src` substring match instead of AST import/call proof.",
                        )
                    )
        if "tok in src" in src and not any(f.code == "SUBSTRING_HANDOFF_COVERAGE_CHECK" for f in findings):
            for idx, ln in enumerate(lines, 1):
                if "tok in src" in ln:
                    findings.append(
                        LoopholeFinding(
                            "R2",
                            "LH-08",
                            "SUBSTRING_HANDOFF_COVERAGE_CHECK",
                            "HIGH",
                            "tools/testing_gaps_auditor.py",
                            idx,
                            "Pillar 2 handoff check relies on raw `tok in src` substring match instead of AST import/call proof.",
                        )
                    )
                    break

    return findings


def scan_r3_fake_scans_and_guard_theater(repo_root: Path) -> list[LoopholeFinding]:
    """Pillar R3: Detect dead shield wiring, unwired construct flags, silent SyntaxError swallows, and bad guardian tags (LH-04, LH-05, LH-11, LH-12)."""
    root = repo_root.resolve()
    findings: list[LoopholeFinding] = []

    # 1. LH-04: Dead reverse-importer expansion in tools/run_diff_scoped_eval_shield.py
    shield_path = root / "tools" / "run_diff_scoped_eval_shield.py"
    if shield_path.is_file():
        src, lines, _tree, _err = _safe_parse_ast(shield_path)
        for idx, ln in enumerate(lines, 1):
            if "repo_root=root if paths is not None else None" in ln:
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-04",
                        "DEAD_REVERSE_IMPORTER_ON_GIT_DIFF",
                        "CRITICAL",
                        "tools/run_diff_scoped_eval_shield.py",
                        idx,
                        "Reverse-importer expansion is disabled when paths is None (all live git-diff runs).",
                    )
                )
            if "expand_reverse_python_importers(" in ln and "hops=1" in ln and "2-hop" in src:
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-04",
                        "UNDER_EXPANDED_REVERSE_IMPORTERS",
                        "MEDIUM",
                        "tools/run_diff_scoped_eval_shield.py",
                        idx,
                        "Shield declares 2-hop expansion but hardcodes hops=1.",
                    )
                )

    # 2. LH-05: Unwired is_scanner_file / is_judge_test flags in tools/audit_eval_construct_validity.py
    acv_path = root / "tools" / "audit_eval_construct_validity.py"
    if acv_path.is_file():
        src, lines, _tree, _err = _safe_parse_ast(acv_path)
        if "scan_extended_construct_validity(" in src:
            if "is_scanner_file=True" not in src or "is_judge_test=True" not in src:
                line_no = next((i for i, l in enumerate(lines, 1) if "scan_extended_construct_validity(" in l), 1)
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-05",
                        "UNWIRED_EXTENDED_CONSTRUCT_VALIDITY_FLAGS",
                        "HIGH",
                        "tools/audit_eval_construct_validity.py",
                        line_no,
                        "scan_extended_construct_validity() never wires is_scanner_file=True or is_judge_test=True across tools/ and test roots.",
                    )
                )

    # 3. LH-11: Silent SyntaxError swallows & comment-bypassable allowlists in purity/overfitting linters
    for rel_linter in ("tools/lint_production_purity.py", "tools/lint_no_jd_overfitting.py"):
        lp = root / rel_linter
        if not lp.is_file():
            continue
        src, lines, tree, _err = _safe_parse_ast(lp)
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    exc_dump = ast.dump(node.type) if node.type is not None else ""
                    if "SyntaxError" in exc_dump:
                        for sub in ast.walk(node):
                            if isinstance(sub, ast.Return) and isinstance(sub.value, ast.List) and len(sub.value.elts) == 0:
                                findings.append(
                                    LoopholeFinding(
                                        "R3",
                                        "LH-11",
                                        "SCANNER_SILENT_SYNTAX_ERROR_RETURN_EMPTY",
                                        "HIGH",
                                        rel_linter,
                                        node.lineno,
                                        "Linter swallows SyntaxError and returns empty [] (0 violations).",
                                    )
                                )
                                break
        if rel_linter.endswith("lint_production_purity.py"):
            fixture_sub_pattern = '"config/' + 'fixtures/" in src_lines['
            for idx, ln in enumerate(lines, 1):
                if fixture_sub_pattern in ln:
                    findings.append(
                        LoopholeFinding(
                            "R3",
                            "LH-11",
                            "COMMENT_BYPASSABLE_FIXTURE_ALLOWLIST",
                            "HIGH",
                            rel_linter,
                            idx,
                            "Raw source-line substring fixture allowlist check can be bypassed via inline comments.",
                        )
                    )
                if '"apps_eval"' in ln and idx < 70 and "EXCLUDED_DIRECTORIES" in "\n".join(lines[max(0, idx - 10) : idx]):
                    findings.append(
                        LoopholeFinding(
                            "R3",
                            "LH-11",
                            "EXCLUDED_PRODUCTION_SUBSYSTEM_IN_PURITY_LINTER",
                            "MEDIUM",
                            rel_linter,
                            idx,
                            "Production subsystem `apps_eval` is globally excluded from lint_production_purity.py.",
                        )
                    )

    # 4. LH-12 (guardian tags): Validate all `# guardian:` comments across production roots against registry
    registry = load_guardian_exemption_registry(root)
    allowed_types = set(registry.get("allowed_exemption_types") or ())
    min_chars = int((registry.get("syntax_contract") or {}).get("min_justification_chars", 8))
    self_rel = "tools/loophole_redteam_auditor.py"

    for py in _iter_prod_py_files(root):
        rel = py.relative_to(root).as_posix()
        if rel == self_rel:
            continue
        _src, lines, _tree, _err = _safe_parse_ast(py)
        for idx, ln in enumerate(lines, 1):
            m_line = _GUARDIAN_LINE_RE.search(ln)
            if not m_line:
                continue
            body = m_line.group(1)
            m_strict = _GUARDIAN_STRICT_RE.match(body)
            if not m_strict:
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-12",
                        "MALFORMED_GUARDIAN_EXEMPTION",
                        "MEDIUM",
                        rel,
                        idx,
                        f"Malformed guardian exemption syntax (expected `# guardian: allow-<type> -- <justification>`): {body.strip()[:80]}",
                    )
                )
                continue
            g_type, justification = m_strict.group(1), m_strict.group(2).strip()
            if g_type not in allowed_types:
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-12",
                        "UNREGISTERED_GUARDIAN_EXEMPTION_TYPE",
                        "MEDIUM",
                        rel,
                        idx,
                        f"Guardian exemption type '{g_type}' is not in config/governance/guardian_exemption_registry.yaml.",
                    )
                )
            elif len(justification) < min_chars:
                findings.append(
                    LoopholeFinding(
                        "R3",
                        "LH-12",
                        "EMPTY_GUARDIAN_JUSTIFICATION",
                        "MEDIUM",
                        rel,
                        idx,
                        f"Guardian exemption '{g_type}' justification is too short (< {min_chars} chars).",
                    )
                )

    return findings


def scan_r4_agent_prompt_and_gate_bypasses(repo_root: Path) -> list[LoopholeFinding]:
    """Pillar R4: Detect regex prose mutators, chore-branch pinning gaps, sandbox drift skips, readiness pass-throughs, and precedent floor gaps (LH-02, LH-07, LH-09, LH-10, LH-12)."""
    root = repo_root.resolve()
    findings: list[LoopholeFinding] = []

    # 1. LH-02: Post-LLM regex prose mutators in agents/orchestration/services/
    for rel_svc in (
        "agents/orchestration/services/swarm_challenger.py",
        "agents/orchestration/services/executive_summary_repair.py",
    ):
        sp = root / rel_svc
        if not sp.is_file():
            continue
        _src, lines, _tree, _err = _safe_parse_ast(sp)
        for idx, ln in enumerate(lines, 1):
            if any(
                tok in ln
                for tok in (
                    "Accomplished leader with extensive experience",
                    "Accomplished professional with experience in",
                    "measurable enterprise growth",
                    "directed and executed",
                )
            ):
                findings.append(
                    LoopholeFinding(
                        "R4",
                        "LH-02",
                        "POST_LLM_REGEX_PROSE_MUTATOR",
                        "HIGH",
                        rel_svc,
                        idx,
                        "Runtime service splices candidate prose via hardcoded regex replacement (violates INV-NO-POST-LLM-PROSE-MUTATORS).",
                    )
                )

    # 2. LH-07 (branch prefix bypass): verify_fix_eval_pinning.py only enforcing fix/ branches
    vfp = root / "tools" / "verify_fix_eval_pinning.py"
    if vfp.is_file():
        _src, lines, _tree, _err = _safe_parse_ast(vfp)
        for idx, ln in enumerate(lines, 1):
            if 'branch.lower().startswith("fix/")' in ln:
                findings.append(
                    LoopholeFinding(
                        "R4",
                        "LH-07",
                        "CHORE_BRANCH_REGRESSION_PINNING_BYPASS",
                        "HIGH",
                        "tools/verify_fix_eval_pinning.py",
                        idx,
                        "Branch regression pinning only fail-closes on `fix/*`, letting `chore/*` assurance agent branches bypass test requirements.",
                    )
                )

    # 3. LH-09: Agent 5/7 --sandbox flywheel bypassing rollback locks and longitudinal drift
    fly_path = root / "tools" / "run_eval_flywheel_cycle.py"
    if fly_path.is_file():
        _src, lines, _tree, _err = _safe_parse_ast(fly_path)
        for idx, ln in enumerate(lines, 1):
            if "if eff_manifest is None and not sandbox:" in ln:
                findings.append(
                    LoopholeFinding(
                        "R4",
                        "LH-09",
                        "SANDBOX_SKIPS_LONGITUDINAL_DRIFT",
                        "HIGH",
                        "tools/run_eval_flywheel_cycle.py",
                        idx,
                        "`--sandbox` preflight skips loading evidence_manifest.json for longitudinal benchmark drift detection.",
                    )
                )
            if 'else (out / "learning_ledger.sqlite" if sandbox else' in ln:
                findings.append(
                    LoopholeFinding(
                        "R4",
                        "LH-09",
                        "SANDBOX_IGNORES_LIVE_ROLLBACK_LOCKS",
                        "HIGH",
                        "tools/run_eval_flywheel_cycle.py",
                        idx,
                        "`--sandbox` opens an empty learning_ledger.sqlite instead of snapshotting live rollback/cooldown locks.",
                    )
                )

    # 4. LH-10: Tier 2 main readiness deleted-suite pass-through & --dry-run PASS receipt
    vmr = root / "tools" / "verify_main_readiness.py"
    if vmr.is_file():
        src, lines, _tree, _err = _safe_parse_ast(vmr)
        for idx, ln in enumerate(lines, 1):
            if '"Optional suite not present"' in ln:
                findings.append(
                    LoopholeFinding(
                        "R4",
                        "LH-10",
                        "READINESS_DELETED_GATE_PASS_THROUGH",
                        "CRITICAL",
                        "tools/verify_main_readiness.py",
                        idx,
                        "Missing mandatory readiness stage script is marked PASS ('Optional suite not present') instead of failing closed.",
                    )
                )
        if "if not dry_run:" not in src and '"terminal_outcome": "PASS" if all_passed else "FAIL"' in src:
            line_no = next(
                (i for i, l in enumerate(lines, 1) if '"terminal_outcome": "PASS" if all_passed else "FAIL"' in l),
                1,
            )
            findings.append(
                LoopholeFinding(
                    "R4",
                    "LH-10",
                    "READINESS_DRY_RUN_WRITES_REUSABLE_PASS_RECEIPT",
                    "CRITICAL",
                    "tools/verify_main_readiness.py",
                    line_no,
                    "`--dry-run` writes a reusable terminal_outcome=PASS readiness receipt that `--recheck-failed-only` can consume.",
                )
            )

    # 5. LH-12 (runtime precedent fallback): Missing 0.65 confidence floor when self._store is None
    pb = root / "agents" / "context" / "precedent_bridge.py"
    if pb.is_file():
        src, lines, _tree, _err = _safe_parse_ast(pb)
        if "if not self._store:" in src and "should_surface = margin <= margin_threshold" in src:
            line_no = next(
                (i for i, l in enumerate(lines, 1) if "should_surface = margin <= margin_threshold" in l),
                1,
            )
            findings.append(
                LoopholeFinding(
                    "R4",
                    "LH-12",
                    "PRECEDENT_FALLBACK_MISSING_CONFIDENCE_FLOOR",
                    "HIGH",
                    "agents/context/precedent_bridge.py",
                    line_no,
                    "Degraded precedent fallback omits 0.65 confidence floor and single-option guard, enabling low-confidence PROCEED_AUTONOMOUSLY.",
                )
            )

    return findings


def audit_repository_loopholes(repo_root: Path) -> dict[str, Any]:
    """Execute all 4 adversarial red-team pillars across repo_root and return structured report."""
    root = repo_root.resolve()
    contract_errors = validate_redteam_subagent_contracts()
    r1 = scan_r1_mock_and_canned_fallbacks(root)
    r2 = scan_r2_fake_tests_and_coverage(root)
    r3 = scan_r3_fake_scans_and_guard_theater(root)
    r4 = scan_r4_agent_prompt_and_gate_bypasses(root)
    all_findings = [*r1, *r2, *r3, *r4]
    by_loophole: dict[str, int] = {}
    for item in all_findings:
        by_loophole[item.loophole_id] = by_loophole.get(item.loophole_id, 0) + 1

    return {
        "schema_version": "agents.loophole_redteam_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "status": "PASS" if (not all_findings and not contract_errors) else "FAIL",
        "contract_errors": contract_errors,
        "pillar_counts": {
            "R1_mock_stub_hunter": len(r1),
            "R2_fake_test_hunter": len(r2),
            "R3_fake_scan_hunter": len(r3),
            "R4_agent_bypass_hunter": len(r4),
        },
        "loophole_counts": dict(sorted(by_loophole.items())),
        "total_findings": len(all_findings),
        "findings": [f.to_dict() for f in all_findings],
    }


def _write_sandbox_file(base: Path, rel: str, content: str) -> None:
    target = base / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _materialize_planted_loopholes_sandbox(base: Path) -> None:
    """Materialize a synthetic repository containing all 12 loophole archetypes (LH-01..LH-12)."""
    _write_sandbox_file(
        base,
        "config/governance/guardian_exemption_registry.yaml",
        (
            "schema_version: '1.0.0'\n"
            "syntax_contract:\n"
            "  min_justification_chars: 8\n"
            "allowed_exemption_types:\n"
            "  - allow-silent-swallow\n"
        ),
    )
    # LH-01: Simulated default adapter literal
    _write_sandbox_file(
        base,
        "agents/gateway/model_gateway.py",
        'def _default_adapter():\n    return {"provider": "simulated_default", "model_id": "simulated-v1"}\n',
    )
    # LH-02: Post-LLM regex prose mutator
    _write_sandbox_file(
        base,
        "agents/orchestration/services/swarm_challenger.py",
        'def draft(t):\n    return t.replace("x", "Accomplished leader with extensive experience")\n',
    )
    # LH-03: Production hasattr mock escape hatch
    _write_sandbox_file(
        base,
        "agents/e2e_artifacts.py",
        'def verify(fn):\n    return hasattr(fn, "mock_calls")\n',
    )
    # LH-04: Dead reverse-importer expansion on git diff
    _write_sandbox_file(
        base,
        "tools/run_diff_scoped_eval_shield.py",
        '"""2-hop reverse dependency expansion."""\n'
        "def run(root, paths=None):\n"
        "    return select(repo_root=root if paths is not None else None)\n"
        "def expand(root, paths):\n"
        "    return expand_reverse_python_importers(root, paths, hops=1)\n",
    )
    # LH-05: Unwired construct validity flags
    _write_sandbox_file(
        base,
        "tools/audit_eval_construct_validity.py",
        "def audit(p):\n    return scan_extended_construct_validity(p)\n",
    )
    # LH-06: Tautological tests & pass-or-fail exit assertion
    _write_sandbox_file(
        base,
        "tests/unit/test_placeholder.py",
        "def test_fake():\n    assert True\n    x = 1\n    assert x == x\n    res_returncode = 1\n    assert res_returncode in (0, 1)\n",
    )
    # LH-07: Mocked E2E masquerade + fix/-only branch pinning
    _write_sandbox_file(
        base,
        "tests/integration/test_live_llm_e2e_fake.py",
        "from unittest.mock import patch\ndef test_live():\n    with patch('os.getenv'):\n        assert 2 == 1 + 1\n",
    )
    _write_sandbox_file(
        base,
        "tools/verify_fix_eval_pinning.py",
        'def check(branch):\n    is_fix = branch.lower().startswith("fix/")\n    return is_fix\n',
    )
    # LH-08: Global flat name-collision coverage & substring handoff check
    _write_sandbox_file(
        base,
        "tools/testing_gaps_auditor.py",
        'def audit(pubs, referenced_symbols, src):\n'
        '    cov = sum(1 for sym in pubs if sym in referenced_symbols)\n'
        '    ok = any(tok in src for tok in ("apps_rg_handoff",))\n'
        '    return cov, ok\n',
    )
    # LH-09: Sandbox skipping rollback locks & longitudinal drift
    _write_sandbox_file(
        base,
        "tools/run_eval_flywheel_cycle.py",
        'def run(out, repo_root, sandbox=True, eff_manifest=None):\n'
        '    p = None if False else (out / "learning_ledger.sqlite" if sandbox else repo_root / "x")\n'
        "    if eff_manifest is None and not sandbox:\n"
        "        return p\n"
        "    return p\n",
    )
    # LH-10: Readiness deleted-suite PASS & dry_run receipt write
    _write_sandbox_file(
        base,
        "tools/verify_main_readiness.py",
        'def run(argv, all_passed, dry_run):\n'
        '    if argv is None:\n'
        '        return (True, "Optional suite not present")\n'
        '    return {"terminal_outcome": "PASS" if all_passed else "FAIL"}\n',
    )
    # LH-11: Purity linter silent SyntaxError swallow & comment-bypassable fixture allowlist
    fixture_dir_tok = "config/" + "fixtures/"
    _write_sandbox_file(
        base,
        "tools/lint_production_purity.py",
        'EXCLUDED_DIRECTORIES = ("tests", "apps_eval")\n'
        "def check(src_lines, ln):\n"
        "    try:\n"
        "        pass\n"
        "    except SyntaxError:\n"
        "        return []\n"
        f'    if "{fixture_dir_tok}" in src_lines[ln - 1]:\n'
        "        return []\n"
        "    return [1]\n",
    )
    # LH-12: Malformed guardian tag + fail-open precedent fallback
    _write_sandbox_file(
        base,
        "agents/context/precedent_bridge.py",
        "class Bridge:\n"
        "    def eval(self, margin, margin_threshold):\n"
        "        if not self._store:\n"
        "            should_surface = margin <= margin_threshold\n"
        "            return should_surface\n"
        "        try:\n"
        "            return True\n"
        "        except Exception:  # guardian: bad-unregistered-tag\n"
        "            return False\n",
    )


def _materialize_clean_control_sandbox(base: Path) -> None:
    """Materialize a clean control sandbox repo that must yield 0 violations across all 4 pillars."""
    _write_sandbox_file(
        base,
        "config/governance/guardian_exemption_registry.yaml",
        (
            "schema_version: '1.0.0'\n"
            "syntax_contract:\n"
            "  min_justification_chars: 8\n"
            "allowed_exemption_types:\n"
            "  - allow-silent-swallow\n"
        ),
    )
    _write_sandbox_file(
        base,
        "agents/gateway/model_gateway.py",
        "def execute(adapter, req):\n"
        "    if adapter is None:\n"
        "        raise RuntimeError('No adapter registered')\n"
        "    return adapter(req)\n",
    )
    _write_sandbox_file(
        base,
        "agents/context/precedent_bridge.py",
        "def cleanup(resource):\n"
        "    try:\n"
        "        resource.close()\n"
        "    except OSError:  # guardian: allow-silent-swallow -- best-effort handle cleanup on exit\n"
        "        pass\n",
    )
    _write_sandbox_file(
        base,
        "tests/end_to_end/test_real_pipeline_e2e.py",
        "def test_real_behavior():\n    result = 2 + 2\n    assert result == 4\n",
    )


def run_counterfactual_self_test() -> dict[str, Any]:
    """Prove fail-closed sensitivity (12/12 planted loopholes caught) and specificity (0 clean false positives)."""
    contract_errors = validate_redteam_subagent_contracts()
    with tempfile.TemporaryDirectory(prefix="loophole_redteam_planted_") as planted_dir:
        planted_root = Path(planted_dir)
        _materialize_planted_loopholes_sandbox(planted_root)
        planted_report = audit_repository_loopholes(planted_root)

    with tempfile.TemporaryDirectory(prefix="loophole_redteam_clean_") as clean_dir:
        clean_root = Path(clean_dir)
        _materialize_clean_control_sandbox(clean_root)
        clean_report = audit_repository_loopholes(clean_root)

    caught_ids = sorted(planted_report["loophole_counts"].keys())
    missing_ids = [lid for lid in ALL_LOOPHOLE_IDS if lid not in caught_ids]
    clean_false_positives = int(clean_report["total_findings"])
    passed = (not contract_errors) and (len(missing_ids) == 0) and (clean_false_positives == 0)

    return {
        "schema_version": "agents.loophole_redteam_counterfactual_self_test.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "planted_count": len(ALL_LOOPHOLE_IDS),
        "caught_count": len(caught_ids),
        "caught_loophole_ids": caught_ids,
        "missed_loophole_ids": missing_ids,
        "planted_total_findings": int(planted_report["total_findings"]),
        "clean_control_false_positives": clean_false_positives,
        "clean_control_findings": clean_report["findings"],
        "contract_errors": contract_errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Adversarial Anti-BS & Loophole Red-Team Auditor & Counterfactual Self-Test."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root to audit.")
    parser.add_argument(
        "--counterfactual-self-test",
        action="store_true",
        help="Run 12-archetype planted mutation + clean negative control self-test.",
    )
    parser.add_argument("--audit-repo", action="store_true", help="Run 4-pillar loophole audit against --repo-root.")
    parser.add_argument("--verify-strict", action="store_true", help="Exit 1 if any repo loophole finding exists.")
    parser.add_argument("--write-receipt", type=Path, default=None, help="Write JSON report receipt to target path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout.")
    args = parser.parse_args(argv)

    run_self_test = bool(args.counterfactual_self_test)
    run_repo_audit = bool(args.audit_repo or args.verify_strict or not run_self_test)

    payload: dict[str, Any] = {
        "schema_version": "agents.loophole_redteam_cli.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    exit_code = 0

    if run_self_test:
        cf = run_counterfactual_self_test()
        payload["counterfactual_self_test"] = cf
        if cf["status"] != "PASS":
            exit_code = 1

    if run_repo_audit:
        audit = audit_repository_loopholes(args.repo_root.resolve())
        payload["repository_audit"] = audit
        if args.verify_strict and audit["status"] != "PASS":
            exit_code = 1

    payload["status"] = "PASS" if exit_code == 0 else "FAIL"

    if args.write_receipt is not None:
        receipt_path = args.write_receipt
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if "counterfactual_self_test" in payload:
            cf = payload["counterfactual_self_test"]
            print(
                f"[counterfactual-self-test] status={cf['status']} "
                f"caught={cf['caught_count']}/{cf['planted_count']} "
                f"clean_fp={cf['clean_control_false_positives']}"
            )
        if "repository_audit" in payload:
            au = payload["repository_audit"]
            print(
                f"[loophole-redteam-audit] status={au['status']} "
                f"total_findings={au['total_findings']} pillars={au['pillar_counts']}"
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
