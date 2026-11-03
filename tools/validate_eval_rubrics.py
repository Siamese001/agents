#!/usr/bin/env python3
"""Deterministic evaluator, judge rubric, and holdout dataset validator for the Agents repository.

Verifies:
1. Non-empty evaluation modules across `apps_eval/` and `tools/`.
2. Exit-evaluation rubric YAML schemas (`config/exit_eval_rubrics/*.yaml`) with `[0.0, 1.0]`
   threshold and scale bounds and weighted sum consistency.
3. Judge rubric bank (`config/judges/rubrics.yaml`) scale/threshold ordering and unknown budgets.
4. Judge model profile bindings in `config/provider_profiles.yaml` against approved catalog models.
5. Structural integrity and parseability of all benchmark, certification, and holdout files in `data/`.
6. Production derivation purity (`tools/lint_production_purity.py`) ensuring zero holdout leakage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(REPO_ROOT)

import yaml  # type: ignore  # noqa: E402
from tools.hitl_governance import load_approved_provider_models  # noqa: E402
from tools.lint_production_purity import (  # noqa: E402
    PRODUCTION_DIRECTORIES,
    check_file_production_purity,
)


def _validate_exit_eval_rubrics(repo_root: Path) -> tuple[int, list[str]]:
    violations: list[str] = []
    rubrics_dir = repo_root / "config" / "exit_eval_rubrics"
    if not rubrics_dir.is_dir():
        return 0, []

    count = 0
    for yf in sorted(rubrics_dir.glob("*.yaml")):
        if yf.name.startswith("_"):
            continue
        count += 1
        rel = str(yf.relative_to(repo_root))
        try:
            doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(f"{rel}: YAML parse error: {exc}")
            continue
        if not isinstance(doc, dict):
            violations.append(f"{rel}: rubric root must be a mapping")
            continue

        if "aggregate_threshold" in doc:
            agg = float(doc["aggregate_threshold"])
            if not (0.0 <= agg <= 1.0):
                violations.append(f"{rel}: aggregate_threshold {agg} outside [0.0, 1.0]")

        dims = doc.get("dimensions")
        if not isinstance(dims, list) or not dims:
            violations.append(f"{rel}: missing non-empty dimensions list")
            continue

        weight_sum = 0.0
        has_weights = False
        for dim in dims:
            if not isinstance(dim, dict):
                continue
            dname = str(dim.get("name", "<unnamed>"))
            scale = dim.get("scale")
            if isinstance(scale, list) and len(scale) == 2:
                lo, hi = float(scale[0]), float(scale[1])
                if lo < 0.0 or hi > 1.0 or lo >= hi:
                    violations.append(f"{rel}::{dname}: invalid normalized scale {scale} (expected [0.0, 1.0])")
            if "threshold" in dim:
                thr = float(dim["threshold"])
                if not (0.0 <= thr <= 1.0):
                    violations.append(f"{rel}::{dname}: threshold {thr} outside [0.0, 1.0]")
            if "weight" in dim:
                has_weights = True
                w = float(dim["weight"])
                if not (0.0 <= w <= 1.0):
                    violations.append(f"{rel}::{dname}: weight {w} outside [0.0, 1.0]")
                weight_sum += w

        if doc.get("composition") == "weighted" and has_weights and abs(weight_sum - 1.0) > 1e-6:
            violations.append(f"{rel}: weighted dimensions sum to {weight_sum:.4f} != 1.0")

    return count, violations


def _validate_judge_rubrics_and_profiles(repo_root: Path) -> list[str]:
    violations: list[str] = []
    j_rubric = repo_root / "config" / "judges" / "rubrics.yaml"
    if j_rubric.is_file():
        rel = str(j_rubric.relative_to(repo_root))
        try:
            doc = yaml.safe_load(j_rubric.read_text(encoding="utf-8")) or {}
            dims = doc.get("dimensions") or {}
            for dname, cfg in dims.items():
                if not isinstance(cfg, dict):
                    continue
                smin = float(cfg.get("scale_min", 1))
                smax = float(cfg.get("scale_max", 5))
                warn_t = float(cfg.get("warn_threshold", smin))
                pass_t = float(cfg.get("pass_threshold", smax))
                ubudget = float(cfg.get("unknown_budget", 0.0))
                if not (smin <= warn_t <= pass_t <= smax):
                    violations.append(
                        f"{rel}::{dname}: invalid threshold ordering ({smin} <= {warn_t} <= {pass_t} <= {smax})"
                    )
                if not (0.0 <= ubudget <= 1.0):
                    violations.append(f"{rel}::{dname}: unknown_budget {ubudget} outside [0.0, 1.0]")
        except Exception as exc:
            violations.append(f"{rel}: failed parsing judge rubrics: {exc}")

    prof_path = repo_root / "config" / "provider_profiles.yaml"
    if prof_path.is_file():
        approved = load_approved_provider_models(repo_root)
        doc = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        judge_models = doc.get("judge_models") or {}
        for tier, pmap in judge_models.items():
            if isinstance(pmap, dict):
                for prov, mid in pmap.items():
                    if str(mid).lower() not in approved:
                        violations.append(f"config/provider_profiles.yaml::judge_models.{tier}.{prov}: unapproved '{mid}'")

    return violations


def _validate_data_holdout_surface(repo_root: Path) -> tuple[int, list[str]]:
    violations: list[str] = []
    data_dir = repo_root / "data"
    if not data_dir.is_dir():
        return 0, []

    file_count = 0
    for fp in sorted(data_dir.rglob("*")):
        if not fp.is_file() or fp.is_symlink():
            continue
        file_count += 1
        if fp.name == ".gitkeep":
            continue
        rel = str(fp.relative_to(repo_root))
        if fp.stat().st_size == 0:
            violations.append(f"{rel}: empty benchmark/holdout data file")
            continue
        try:
            if fp.suffix == ".json":
                json.loads(fp.read_text(encoding="utf-8"))
            elif fp.suffix == ".jsonl":
                for idx, line in enumerate(fp.read_text(encoding="utf-8").splitlines(), 1):
                    if line.strip():
                        json.loads(line)
            elif fp.suffix in (".yaml", ".yml"):
                yaml.safe_load(fp.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append(f"{rel}: malformed dataset payload ({exc})")

    return file_count, violations


def validate_eval_rubrics(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Audits evaluation modules, rubric score bounds, judge profiles, holdout datasets, and purity."""
    root = repo_root.resolve()
    violations: list[str] = []

    if not (root / "tests").is_dir():
        violations.append("Missing mandatory tests/ directory for evaluation verification.")

    py_files: list[Path] = []
    for sub in ("apps_eval", "tools"):
        base = root / sub
        if base.is_dir():
            py_files.extend(sorted(base.rglob("*eval*.py")))

    for p in py_files:
        if p.stat().st_size == 0:
            violations.append(f"Empty evaluation module detected: {p.relative_to(root)}")

    exit_rubric_count, rubric_errs = _validate_exit_eval_rubrics(root)
    violations.extend(rubric_errs)
    violations.extend(_validate_judge_rubrics_and_profiles(root))

    data_file_count, data_errs = _validate_data_holdout_surface(root)
    violations.extend(data_errs)

    purity_errs: list[str] = []
    for prod_dir in PRODUCTION_DIRECTORIES:
        d = root / prod_dir
        if d.exists():
            for py in sorted(d.rglob("*.py")):
                for lineno, cat, msg in check_file_production_purity(py, root):
                    purity_errs.append(f"{py.relative_to(root)}:{lineno}: [{cat}] {msg}")
    violations.extend(purity_errs)

    is_clean = len(violations) == 0
    return {
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "eval_module_count": len(py_files),
        "exit_rubric_count": exit_rubric_count,
        "data_file_count": data_file_count,
        "purity_violation_count": len(purity_errs),
        "violations": violations,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agents evaluation rubrics, judge bounds, and holdout data.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rep = validate_eval_rubrics(args.repo_root.resolve())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(
            f"[{rep['status']}] Validated {rep['eval_module_count']} eval modules, "
            f"{rep['exit_rubric_count']} exit rubrics, and {rep['data_file_count']} data files "
            f"({len(rep['violations'])} violations)."
        )
    return 0 if rep["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
