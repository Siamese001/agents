#!/usr/bin/env python3
"""Transitive Dependency Impact Test Selector for Sharded Multi-Agent Waves."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_ROOTS: tuple[str, ...] = (
    "tests",
    "resume_graph_engine/tests",
    "outreach_engine/tests",
    "apps_eval/tests",
    "resume_engine/tests",
    "apps_research/tests",
)

_PINNED_SUITES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("tools/pr_governance", "tools/verify_merge_receipt", "tools/verify_post_merge"), "tests/test_pr_merge_queue_governance.py"),
    (("tools/hook_dispatch.py", ".agents/hooks.json"), "tests/test_hook_dispatch.py"),
    (("tools/validate_implementation_plan.py", "tools/implementation_plan_core/"), "tests/test_implementation_plan_governance.py"),
    (("tools/validate_turn_gates.py",), "tests/test_turn_gates.py"),
    (("tools/prompt_scope_isolation.py", "tools/unified_agent_architecture.py"), "tests/test_unified_agent_architecture.py"),
)


def _extract_module_tokens(rel_path: str) -> set[str]:
    norm = rel_path.replace("\\", "/").strip("/")
    p = Path(norm)
    tokens: set[str] = set()
    if p.stem and p.stem != "__init__":
        tokens.add(p.stem)
    elif p.parent.name:
        tokens.add(p.parent.name)
    parts = [pt for pt in p.with_suffix("").parts if pt not in ("src", "__init__")]
    if len(parts) >= 2:
        tokens.add(".".join(parts[-2:]))
    if parts:
        tokens.add(".".join(parts))
    return {t for t in tokens if len(t) >= 3}


def _scan_test_imports(test_file: Path) -> set[str]:
    try:
        src = test_file.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(test_file))
    except (OSError, SyntaxError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
                found.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
                found.update(node.module.split("."))
            for alias in node.names:
                found.add(alias.name)
    return found


def select_impacted_tests(
    changed_files: Sequence[str],
    repo_root: Path = REPO_ROOT,
    max_files_per_batch: int = 4,
) -> dict[str, object]:
    """Compute impacted test files and Class-A-compliant batches (<= 4 files per batch)."""
    root = repo_root.resolve()
    norm_changed = [f.replace("\\", "/").strip("/") for f in changed_files if f.strip()]
    selected: list[str] = []

    for f in norm_changed:
        if (f.startswith("tests/") or "/tests/" in f) and f.endswith(".py") and (root / f).is_file():
            if f not in selected:
                selected.append(f)
        for prefixes, suite in _PINNED_SUITES:
            if any(f.startswith(pfx) for pfx in prefixes) and (root / suite).is_file():
                if suite not in selected:
                    selected.append(suite)

    target_tokens: set[str] = set()
    for f in norm_changed:
        if f.endswith(".py"):
            target_tokens.update(_extract_module_tokens(f))

    if target_tokens:
        for test_root in TEST_ROOTS:
            tdir = root / test_root
            if not tdir.is_dir():
                continue
            for tf in sorted(tdir.rglob("test_*.py")):
                rel_tf = tf.relative_to(root).as_posix()
                if rel_tf in selected:
                    continue
                stem_match = any(
                    tf.stem == f"test_{tok}" or tf.stem.startswith(f"test_{tok}_")
                    for tok in target_tokens
                    if "." not in tok
                )
                if stem_match:
                    selected.append(rel_tf)
                    continue
                imported = _scan_test_imports(tf)
                if target_tokens.intersection(imported):
                    selected.append(rel_tf)

    batch_size = max(1, min(int(max_files_per_batch), 4))
    batches = [selected[i : i + batch_size] for i in range(0, len(selected), batch_size)]
    return {
        "changed_files": norm_changed,
        "selected_tests": selected,
        "total_selected": len(selected),
        "batches": batches,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select transitive impacted pytest files for changed files.")
    parser.add_argument("--changed-files", nargs="*", default=[], help="Changed repository-relative file paths.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    result = select_impacted_tests(args.changed_files, repo_root=args.repo_root.resolve())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for batch in result["batches"]:  # type: ignore[attr-defined]
            print(" ".join(batch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
