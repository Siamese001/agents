#!/usr/bin/env python3
"""Deterministic evaluator, judge rubric, schema, and holdout dataset validator across all 5 config roots and 315 data files."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(REPO_ROOT)

import yaml  # type: ignore  # noqa: E402
from tools._eval_rubrics_helpers import (  # noqa: E402
    CONFIG_ROOTS,
    DATA_ROOTS,
    _DEF_NODES,
    _probe_app_graders,
    _run_live_apps_eval_probes,
    _validate_eval_modules_ast_and_schemas,
)
from tools.hitl_governance import load_approved_provider_models  # noqa: E402
from tools.lint_production_purity import PRODUCTION_DIRECTORIES, check_file_production_purity  # noqa: E402


def _validate_exit_and_domain_rubrics(repo_root: Path) -> tuple[int, list[str]]:
    """Validate exit-eval rubrics and domain rubrics across all 5 configuration roots."""
    violations: list[str] = []
    count = 0

    for rub_rel in ("config/exit_eval_rubrics", "resume_graph_engine/config/exit_eval_rubrics"):
        rubrics_dir = repo_root / rub_rel
        if not rubrics_dir.is_dir():
            continue
        for yf in sorted(rubrics_dir.glob("*.yaml")):
            if yf.name.startswith("_"):
                continue
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
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

    # Validate outreach_engine/config/rubrics/*.yaml
    outreach_rub_dir = repo_root / "outreach_engine" / "config" / "rubrics"
    if outreach_rub_dir.is_dir():
        for yf in sorted(outreach_rub_dir.glob("*.yaml")):
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: YAML parse error: {exc}")
                continue
            if not isinstance(doc, dict) or not doc.get("rubric_id"):
                violations.append(f"{rel}: missing rubric_id")
                continue
            prev_min = -1.0
            for band in doc.get("score_bands") or []:
                if isinstance(band, dict) and "min_score" in band:
                    ms = float(band["min_score"])
                    if not (0.0 <= ms <= 1.0) or ms < prev_min:
                        violations.append(f"{rel}: invalid or non-monotonic score_bands min_score {ms}")
                    prev_min = ms
            lenses = doc.get("lenses")
            if isinstance(lenses, dict) and lenses:
                wsum = 0.0
                for lname, lcfg in lenses.items():
                    if not isinstance(lcfg, dict):
                        continue
                    w, thr = float(lcfg.get("weight", 0.0)), float(lcfg.get("threshold", 0.0))
                    if not (0.0 <= w <= 1.0) or not (0.0 <= thr <= 1.0):
                        violations.append(f"{rel}::{lname}: lens weight/threshold outside [0.0, 1.0]")
                    wsum += w
                if abs(wsum - 1.0) > 1e-6:
                    violations.append(f"{rel}: outreach lenses weights sum to {wsum:.4f} != 1.0")

    apps_eval_rub_dir = repo_root / "apps_eval" / "rubrics"
    if apps_eval_rub_dir.is_dir():
        for yf in sorted(apps_eval_rub_dir.glob("*.yaml")):
            count += 1
            rel = str(yf.relative_to(repo_root))
            try:
                doc = yaml.safe_load(yf.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                violations.append(f"{rel}: YAML parse error: {exc}")
                continue
            if not isinstance(doc, dict) or not isinstance(doc.get("dimensions"), list):
                violations.append(f"{rel}: missing dimensions list")
                continue
            wsum = 0.0
            for dim in doc["dimensions"]:
                if not isinstance(dim, dict):
                    continue
                did, w = str(dim.get("id", "<unnamed>")), float(dim.get("weight", 0.0))
                if not (0.0 <= w <= 1.0):
                    violations.append(f"{rel}::{did}: weight {w} outside [0.0, 1.0]")
                if dim.get("informational_only") is True and w > 0.0:
                    violations.append(f"{rel}::{did}: informational_only dimension must have weight 0.0, got {w}")
                wsum += w
            if abs(wsum - 1.0) > 1e-6:
                violations.append(f"{rel}: rubric dimensions sum to {wsum:.4f} != 1.0")

    res_rub = repo_root / "apps_research" / "config" / "domain_contract" / "eval_rubrics.yaml"
    if res_rub.is_file():
        count += 1
        rel = str(res_rub.relative_to(repo_root))
        try:
            items = yaml.safe_load(res_rub.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            violations.append(f"{rel}: YAML parse error: {exc}")
            items = None
        if not isinstance(items, list) or not items:
            violations.append(f"{rel}: expected non-empty list of eval rubrics")
        else:
            for item in (it for it in items if isinstance(it, dict)):
                rid, wsum = str(item.get("eval_rubric_id", "<unnamed>")), 0.0
                for sdim in (sd for sd in (item.get("score_dimensions") or []) if isinstance(sd, dict)):
                    w, mrs = float(sdim.get("weight", 0.0)), float(sdim.get("min_required_score", 0.0))
                    if not (0.0 <= w <= 1.0) or not (0.0 <= mrs <= 1.0):
                        violations.append(f"{rel}::{rid}: score_dimension weight/min_required_score outside [0.0, 1.0]")
                    wsum += w
                if abs(wsum - 1.0) > 1e-6:
                    violations.append(f"{rel}::{rid}: score_dimensions weights sum to {wsum:.4f} != 1.0")

    return count, violations


def _validate_judge_rubrics_and_profiles(repo_root: Path) -> list[str]:
    """Validate judge rubric banks and approved model pins across all 5 config roots."""
    violations: list[str] = []
    for j_rel in ("config/judges/rubrics.yaml", "resume_graph_engine/config/judges/rubrics.yaml"):
        j_rubric = repo_root / j_rel
        if not j_rubric.is_file():
            continue
        try:
            doc = yaml.safe_load(j_rubric.read_text(encoding="utf-8")) or {}
            for dname, cfg in (doc.get("dimensions") or {}).items():
                if not isinstance(cfg, dict):
                    continue
                smin, smax = float(cfg.get("scale_min", 1)), float(cfg.get("scale_max", 5))
                warn_t, pass_t = float(cfg.get("warn_threshold", smin)), float(cfg.get("pass_threshold", smax))
                ubudget = float(cfg.get("unknown_budget", 0.0))
                if not (smin <= warn_t <= pass_t <= smax):
                    violations.append(f"{j_rel}::{dname}: invalid threshold ordering ({smin} <= {warn_t} <= {pass_t} <= {smax})")
                if not (0.0 <= ubudget <= 1.0):
                    violations.append(f"{j_rel}::{dname}: unknown_budget {ubudget} outside [0.0, 1.0]")
        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            violations.append(f"{j_rel}: failed parsing judge rubrics: {exc}")

    approved = load_approved_provider_models(repo_root)
    if not approved:
        return violations

    prof_path = repo_root / "config" / "provider_profiles.yaml"
    if prof_path.is_file():
        doc = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}
        for tier, pmap in (doc.get("judge_models") or {}).items():
            if isinstance(pmap, dict):
                for prov, mid in pmap.items():
                    if str(mid).lower() not in approved:
                        violations.append(f"config/provider_profiles.yaml::judge_models.{tier}.{prov}: unapproved '{mid}'")

    for rel_p, top_key in (
        ("outreach_engine/config/provider_profiles.yaml", "profiles"),
        ("apps_research/config/domain_contract/provider_profile.company_brief.v1.yaml", "approved_model_lanes"),
    ):
        fp = repo_root / rel_p
        if fp.is_file():
            doc = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            for kname, kcfg in (doc.get(top_key) or {}).items() if isinstance(doc.get(top_key), dict) else ():
                if isinstance(kcfg, dict) and kcfg.get("model") and str(kcfg["model"]).lower() not in approved:
                    violations.append(f"{rel_p}::{kname}: unapproved '{kcfg['model']}'")

    apps_eval_rub_dir = repo_root / "apps_eval" / "rubrics"
    if apps_eval_rub_dir.is_dir():
        for yf in sorted(apps_eval_rub_dir.glob("*.yaml")):
            doc = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            pin = (doc.get("judge_model_pin") or {}) if isinstance(doc, dict) else {}
            if isinstance(pin, dict) and pin.get("model") and str(pin["model"]).lower() not in approved:
                violations.append(f"{yf.relative_to(repo_root)}::judge_model_pin: unapproved '{pin['model']}'")

    res_jprof = repo_root / "apps_research" / "config" / "domain_contract" / "judge_profile.company_brief.v1.yaml"
    if res_jprof.is_file():
        doc = yaml.safe_load(res_jprof.read_text(encoding="utf-8")) or {}
        hj = (doc.get("apps_rg_handoff_judge") or {}) if isinstance(doc, dict) else {}
        if isinstance(hj, dict) and hj.get("model") and str(hj["model"]).lower() not in approved:
            violations.append(f"{res_jprof.relative_to(repo_root)}::apps_rg_handoff_judge: unapproved '{hj['model']}'")

    return violations


_RUNTIME_CACHE_DIR_PARTS: frozenset[str] = frozenset({"cache", "__pycache__", ".pytest_cache", ".ruff_cache"})
_RUNTIME_BINARY_SIDE_SUFFIXES: tuple[str, ...] = ("-wal", "-shm", "-journal", ".sqlite", ".sqlite3", ".db", ".bin", ".lock")


def _validate_data_holdout_surface(repo_root: Path) -> tuple[int, dict[str, int], list[str]]:
    """Validate structural integrity across all 3 data roots (`data`, `outreach_engine/data`, `resume_graph_engine/data`)."""
    violations, file_count, counts_by_root = [], 0, {}
    for d_rel in DATA_ROOTS:
        data_dir = repo_root / d_rel
        if not data_dir.is_dir():
            continue
        root_count = 0
        for fp in sorted(data_dir.rglob("*")):
            if not fp.is_file() or fp.is_symlink():
                continue
            rel_parts = fp.relative_to(data_dir).parts
            if any(p in _RUNTIME_CACHE_DIR_PARTS for p in rel_parts[:-1]) or fp.name.endswith(_RUNTIME_BINARY_SIDE_SUFFIXES):
                continue
            file_count += 1
            root_count += 1
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
                    jsonl_rows = 0
                    for line in fp.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            json.loads(line)
                            jsonl_rows += 1
                    if (
                        "outreach_engine/data/evals/holdout/" in rel.replace("\\", "/")
                        or fp.name == "outreach_holdout_corpus.v1.jsonl"
                    ) and jsonl_rows < 50:
                        violations.append(
                            f"{rel}: outreach holdout JSONL has {jsonl_rows} rows (< 50 required)"
                        )
                elif fp.suffix == ".csv":
                    csv_rows = [
                        row
                        for row in csv.reader(fp.read_text(encoding="utf-8").splitlines())
                        if any(cell.strip() for cell in row)
                    ]
                    data_rows = max(0, len(csv_rows) - 1)
                    if "outreach_engine/data/evals/holdout/" in rel.replace("\\", "/") and data_rows < 50:
                        violations.append(
                            f"{rel}: outreach holdout CSV has {data_rows} data rows (< 50 required)"
                        )
                elif fp.suffix in (".yaml", ".yml"):
                    yaml.safe_load(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, yaml.YAMLError, csv.Error) as exc:
                violations.append(f"{rel}: malformed dataset payload ({exc})")
        counts_by_root[d_rel] = root_count
    lic_holdout_dir = repo_root / "outreach_engine" / "data" / "evals" / "holdout"
    if lic_holdout_dir.is_dir():
        if not (lic_holdout_dir / "outreach_holdout_corpus.v1.jsonl").is_file():
            violations.append(
                "outreach_engine/data/evals/holdout/outreach_holdout_corpus.v1.jsonl: missing holdout corpus"
            )
        if not list(lic_holdout_dir.glob("*.csv")):
            violations.append(
                "outreach_engine/data/evals/holdout/*.csv: missing holdout CSV files"
            )
    violations.extend(_check_git_ignored_holdout_files(repo_root))
    return file_count, counts_by_root, violations


def _check_git_ignored_holdout_files(repo_root: Path) -> list[str]:
    """Fail closed if any holdout/benchmark data file on disk is git-ignored and untracked."""
    if not (repo_root / ".git").exists():
        return []
    candidates: list[str] = []
    for d_rel in DATA_ROOTS:
        data_dir = repo_root / d_rel
        if not data_dir.is_dir():
            continue
        for fp in sorted(data_dir.rglob("*")):
            if not fp.is_file() or fp.is_symlink() or fp.name == ".gitkeep":
                continue
            rel_parts = fp.relative_to(data_dir).parts
            if any(p in _RUNTIME_CACHE_DIR_PARTS for p in rel_parts[:-1]) or fp.name.endswith(_RUNTIME_BINARY_SIDE_SUFFIXES):
                continue
            candidates.append(fp.relative_to(repo_root).as_posix())
    if not candidates:
        return []
    try:
        ig_proc = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "--", *candidates],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        ignored = [ln.strip() for ln in ig_proc.stdout.splitlines() if ln.strip()]
        if not ignored:
            return []
        tr_proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--", *ignored],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        tracked = {ln.strip() for ln in tr_proc.stdout.splitlines() if ln.strip()}
        return [
            f"{rel_p}: holdout/benchmark data file is git-ignored and untracked"
            for rel_p in ignored
            if rel_p not in tracked
        ]
    except (OSError, subprocess.SubprocessError):
        return []


def validate_eval_rubrics(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Audits evaluation modules, schemas, live graders, rubrics, judge profiles, holdouts, and purity."""
    root = repo_root.resolve()
    violations: list[str] = []

    if not (root / "tests").is_dir():
        violations.append("Missing mandatory tests/ directory for evaluation verification.")

    eval_mod_count, schema_count, mod_errs = _validate_eval_modules_ast_and_schemas(root)
    violations.extend(mod_errs)
    violations.extend(_run_live_apps_eval_probes(root))

    exit_rubric_count, rubric_errs = _validate_exit_and_domain_rubrics(root)
    violations.extend(rubric_errs)
    violations.extend(_validate_judge_rubrics_and_profiles(root))

    data_file_count, data_counts_by_root, data_errs = _validate_data_holdout_surface(root)
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
        "status": "PASS" if is_clean else "FAIL", "is_clean": is_clean,
        "config_roots_audited": [r for r in CONFIG_ROOTS if (root / r).is_dir()],
        "eval_module_count": eval_mod_count, "validated_schema_count": schema_count,
        "exit_rubric_count": exit_rubric_count, "data_file_count": data_file_count,
        "data_counts_by_root": data_counts_by_root, "purity_violation_count": len(purity_errs),
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
        print(f"[{rep['status']}] Validated {rep['eval_module_count']} eval modules, {rep['validated_schema_count']} schemas, {rep['exit_rubric_count']} rubrics, and {rep['data_file_count']} data files ({len(rep['violations'])} violations).")
    return 0 if rep["is_clean"] else 1


__all__ = [
    "CONFIG_ROOTS",
    "DATA_ROOTS",
    "_DEF_NODES",
    "_probe_app_graders",
    "_run_live_apps_eval_probes",
    "_validate_data_holdout_surface",
    "_validate_eval_modules_ast_and_schemas",
    "_validate_exit_and_domain_rubrics",
    "_validate_judge_rubrics_and_profiles",
    "main",
    "validate_eval_rubrics",
]


if __name__ == "__main__":
    sys.exit(main())
