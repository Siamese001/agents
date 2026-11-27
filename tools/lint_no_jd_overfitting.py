#!/usr/bin/env python3
"""Tier 1 Anti-Overfitting Linter (INV-ANTI-OVERFITTING-MULTI-JD).

Detects hardcoded target-company or single-JD conditional branches in production runtime
code outside explicitly allowlisted targeting config/profile registries, with optional
ratchet baseline enforcement so legacy debt can only burn down and never grow.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent

TARGET_COMPANY_TOKENS: frozenset[str] = frozenset(
    {
        "truist",
        "brown & brown",
        "brown_brown",
        "invesco",
        "citi",
        "citigroup",
        "aig",
        "aveva",
        "blend",
        "neo4j",
    }
)
_UNAMBIGUOUS_COMPANY_WORD_RE = re.compile(
    r"\b(?:truist|brown\s*&\s*brown|brown_brown|invesco|citigroup|aveva|neo4j)\b",
    re.IGNORECASE,
)

PRODUCTION_SCAN_ROOTS: tuple[str, ...] = (
    "resume_graph_engine/src",
    "resume_engine",
    "outreach_engine",
    "apps_research",
    "agents",
)

ALLOWLISTED_PATH_FRAGMENTS: tuple[str, ...] = (
    "/config/targeting/",
    "/tests/",
    "/fixtures/",
    "/evals/",
)

DEFAULT_BASELINE_RELPATH = "config/governance/jd_overfitting_baseline.json"


def _is_allowlisted(relpath: str) -> bool:
    norm = "/" + relpath.replace("\\", "/").strip("/") + "/"
    return any(frag in norm for frag in ALLOWLISTED_PATH_FRAGMENTS)


def _extract_string_literals(node: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            val = sub.value.strip().lower()
            if val in TARGET_COMPANY_TOKENS:
                hits.append((getattr(sub, "lineno", 1), val))
            elif 0 < len(val) <= 80:
                m = _UNAMBIGUOUS_COMPANY_WORD_RE.search(val)
                if m:
                    hits.append((getattr(sub, "lineno", 1), m.group(0).lower()))
    return hits


def check_file_no_jd_overfitting(file_path: Path, repo_root: Path) -> list[dict[str, Any]]:
    """Inspect a single Python file for hardcoded target-company conditional branches."""
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = str(file_path).replace("\\", "/")
    if _is_allowlisted(rel):
        return []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except OSError as exc:
        return [
            {
                "code": "JD_OVERFITTING_READ_ERROR",
                "file": rel,
                "line": 1,
                "token": "<os_error>",
                "message": f"Failed reading production module during JD overfitting scan: {exc}",
            }
        ]
    except SyntaxError as exc:
        return [
            {
                "code": "JD_OVERFITTING_SYNTAX_ERROR",
                "file": rel,
                "line": exc.lineno or 1,
                "token": "<syntax_error>",
                "message": f"SyntaxError prevents JD overfitting verification: {exc.msg}",
            }
        ]

    violations: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    def _record(lineno: int, token: str, code: str = "JD_COMPANY_OVERFITTING_BRANCH") -> None:
        key = (lineno, token)
        if key in seen:
            return
        seen.add(key)
        violations.append(
            {
                "code": code,
                "file": rel,
                "line": lineno,
                "token": token,
                "message": (
                    f"Hardcoded target-company conditional or dispatch on '{token}' in production code "
                    "(use generalizable role profiles / targeting config instead)."
                ),
            }
        )

    for node in ast.walk(tree):
        cond: ast.AST | None = None
        if isinstance(node, (ast.If, ast.IfExp)):
            cond = node.test
        elif isinstance(node, ast.Compare):
            cond = node
        elif isinstance(node, ast.Dict):
            dict_keys = [
                (getattr(k, "lineno", 1), k.value.strip().lower())
                for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.strip().lower() in TARGET_COMPANY_TOKENS
            ]
            if len(dict_keys) >= 2:
                for lineno, token in dict_keys:
                    _record(lineno, token, code="JD_COMPANY_OVERFITTING_DISPATCH_DICT")
            continue
        elif isinstance(node, ast.Call):
            fn_attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if fn_attr in ("startswith", "endswith", "compile", "search", "match"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        low = arg.value.strip().lower()
                        for tok in TARGET_COMPANY_TOKENS:
                            if low == tok or (fn_attr in ("compile", "search", "match") and f"\\b{tok}" in low):
                                _record(getattr(arg, "lineno", 1), tok, code="JD_COMPANY_OVERFITTING_CALL")
            continue
        if cond is None:
            continue
        for lineno, token in _extract_string_literals(cond):
            _record(lineno, token)
    return violations


def load_baseline(repo_root: Path) -> dict[str, int]:
    path = repo_root / DEFAULT_BASELINE_RELPATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        counts = data.get("file_counts") or {}
        return {str(k).replace("\\", "/"): int(v) for k, v in counts.items()}
    except (OSError, ValueError, TypeError):
        return {}


def scan_files(
    files: Sequence[Path],
    repo_root: Path,
    *,
    use_baseline: bool = True,
) -> dict[str, Any]:
    baseline = load_baseline(repo_root) if use_baseline else {}
    all_hits: list[dict[str, Any]] = []
    unbaselined: list[dict[str, Any]] = []

    for f in files:
        if not f.is_file() or f.suffix != ".py":
            continue
        hits = check_file_no_jd_overfitting(f, repo_root)
        if not hits:
            continue
        all_hits.extend(hits)
        rel = hits[0]["file"]
        ceiling = baseline.get(rel, 0)
        if len(hits) > ceiling:
            unbaselined.extend(hits[ceiling:])

    return {
        "schema_version": "agents.no_jd_overfitting_lint.v1",
        "status": "PASS" if not unbaselined else "FAIL",
        "total_hits": len(all_hits),
        "unbaselined_count": len(unbaselined),
        "violations": unbaselined,
        "all_hits": all_hits,
    }


def collect_production_files(repo_root: Path) -> list[Path]:
    out: list[Path] = []
    for rel_root in PRODUCTION_SCAN_ROOTS:
        base = repo_root / rel_root
        if base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint production code for single-JD / company overfitting branches.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--all", action="store_true", help="Scan all production Python roots.")
    parser.add_argument("--files", nargs="*", default=(), help="Explicit Python files to scan.")
    parser.add_argument("--no-baseline", action="store_true", help="Ignore legacy baseline ratchet.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    files = collect_production_files(repo_root) if args.all or not args.files else [Path(p) for p in args.files]
    report = scan_files(files, repo_root, use_baseline=not args.no_baseline)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[lint-no-jd-overfitting] status={report['status']} "
            f"total_hits={report['total_hits']} unbaselined={report['unbaselined_count']}"
        )
        for v in report["violations"]:
            print(f"  - [{v['code']}] {v['file']}:{v['line']}: {v['message']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
