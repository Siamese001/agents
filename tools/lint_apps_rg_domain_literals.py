#!/usr/bin/env python3
"""Ratchet linter preventing new hardcoded domain-vocabulary frozenset literals or standard exemptions in apps_rg."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ratchet ceiling after Wave 5 consolidation (down from 104 literal frozensets; may only decrease).
MAX_VALIDATOR_JUDGE_FROZENSET_CALLS = 100
MAX_QUALITY_ENGINE_FROZENSET_CALLS = 3

BANNED_IDENTIFIER_NAMES: frozenset[str] = frozenset({
    "_EXEMPT_STANDARD_NUMBERS",
    "EXEMPT_STANDARD_NUMBERS",
})

BANNED_RUBRIC_CARVEOUTS: tuple[str, ...] = (
    "such as head of forward deployed engineering at truist",
    "such as blend360",
    "e.g. anthropic/applied-ai",
)


def _count_frozenset_calls_in_tree(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "frozenset"
            and node.args
            and isinstance(node.args[0], ast.Set)
        ):
            count += 1
    return count


def audit_apps_rg_domain_literals(repo_root: Path | None = None) -> list[str]:
    """Return a list of violation strings if any domain-literal ratchet or banned exemption is violated."""
    root = (repo_root or REPO_ROOT).resolve()
    rg_runtime = root / "resume_graph_engine" / "src" / "apps_rg" / "runtime"
    if not rg_runtime.is_dir():
        return []

    errors: list[str] = []
    vj_frozenset_count = 0
    quality_frozenset_count = 0

    for sub in ("validators", "judges"):
        sub_dir = rg_runtime / sub
        if not sub_dir.is_dir():
            continue
        for py_path in sorted(sub_dir.rglob("*.py")):
            rel = py_path.relative_to(root).as_posix()
            text = py_path.read_text(encoding="utf-8", errors="replace")
            lower = text.lower()
            if sub == "judges":
                for carveout in BANNED_RUBRIC_CARVEOUTS:
                    if carveout in lower:
                        errors.append(
                            f"[AppsRG Domain Literal Ratchet] {rel}: contains banned target-company rubric carve-out {carveout!r}"
                        )
            try:
                tree = ast.parse(text, filename=str(py_path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in BANNED_IDENTIFIER_NAMES:
                    errors.append(
                        f"[AppsRG Domain Literal Ratchet] {rel}:{getattr(node, 'lineno', 1)}: "
                        f"banned hardcoded standard-number exemption {node.id!r}"
                    )
            vj_frozenset_count += _count_frozenset_calls_in_tree(tree)

    coherence_rubric = rg_runtime / "assembly" / "full_resume_llm_coherence_rubric.py"
    if coherence_rubric.is_file():
        lower_coh = coherence_rubric.read_text(encoding="utf-8", errors="replace").lower()
        for carveout in BANNED_RUBRIC_CARVEOUTS:
            if carveout in lower_coh:
                errors.append(
                    "[AppsRG Domain Literal Ratchet] "
                    f"{coherence_rubric.relative_to(root).as_posix()}: contains banned target-company rubric carve-out {carveout!r}"
                )

    quality_dir = rg_runtime / "quality"
    if quality_dir.is_dir():
        for py_path in sorted(quality_dir.rglob("*.py")):
            text = py_path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(text, filename=str(py_path))
            except SyntaxError:
                continue
            quality_frozenset_count += _count_frozenset_calls_in_tree(tree)

    if vj_frozenset_count > MAX_VALIDATOR_JUDGE_FROZENSET_CALLS:
        errors.append(
            "[AppsRG Domain Literal Ratchet] "
            f"validators+judges frozenset literal count ({vj_frozenset_count}) exceeds ratchet ceiling "
            f"({MAX_VALIDATOR_JUDGE_FROZENSET_CALLS}). Learn rare terms via RareTermLexicon or declarative config."
        )

    if quality_frozenset_count > MAX_QUALITY_ENGINE_FROZENSET_CALLS:
        errors.append(
            "[AppsRG Domain Literal Ratchet] "
            f"runtime/quality frozenset literal count ({quality_frozenset_count}) exceeds ceiling "
            f"({MAX_QUALITY_ENGINE_FROZENSET_CALLS}). Keep Overlap Engine free of hardcoded domain word lists."
        )

    return errors


def main() -> int:
    errs = audit_apps_rg_domain_literals(REPO_ROOT)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print(
        "[PASS] apps_rg domain literal ratchet clean "
        f"(ceiling={MAX_VALIDATOR_JUDGE_FROZENSET_CALLS}, quality_ceiling={MAX_QUALITY_ENGINE_FROZENSET_CALLS})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
