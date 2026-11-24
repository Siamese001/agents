"""Unified deterministic and live-adapter evaluation orchestrator for Resume & Outreach engines.

Pure JSON/filesystem module (zero SQLite imports to preserve domain storage isolation,
and zero direct ``apps_lic`` / ``apps_rg`` imports to keep ``apps_eval`` decoupled from
domain runtimes via subprocess boundaries).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_eval.adapters.outreach_engine import OutreachEngineEvalAdapter
from apps_eval.baselines import DEFAULT_BASELINE_DIR, baseline_path, load_baseline
from apps_eval.bootstrap_baselines import CORE_BASELINE_SUITES, SNAPSHOT_GRADER_ONLY_SUITES
from apps_eval.contracts import EvalRequest
from apps_eval.golden_suite_runner import evaluate_golden_flywheel_suite
from apps_eval.runner.core import compare_record_to_baseline, run_eval
from apps_eval.trends import emit_release_gate, emit_trend_dashboard

EVIDENCE_MANIFEST_SCHEMA_VERSION = "apps_eval.unified_evidence_manifest.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_python(repo_root: Path) -> str:
    for candidate in (
        repo_root / ".venv" / "bin" / "python",
        Path(sys.executable),
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _run_subprocess_json(
    python_bin: str,
    code: str,
    *,
    cwd: Path,
    timeout: int = 90,
) -> dict[str, Any]:
    proc = subprocess.run(
        [python_bin, "-c", code],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    stdout = proc.stdout.strip()
    if proc.returncode != 0:
        return {
            "status": "FAIL",
            "returncode": proc.returncode,
            "error": (proc.stderr or stdout)[-1200:],
        }
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return {
        "status": "FAIL",
        "returncode": proc.returncode,
        "error": f"unable to parse JSON from probe output: {stdout[-500:]}",
    }


def _probe_apps_rg_offline_e2e(repo_root: Path, python_bin: str, probe_dir: Path) -> dict[str, Any]:
    probe_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        f"repo = Path({str(repo_root)!r})\n"
        "for p in (repo, repo / 'resume_graph_engine' / 'src'):\n"
        "    if str(p) not in sys.path:\n"
        "        sys.path.insert(0, str(p))\n"
        "from apps_rg.bare_pipeline import run_bare_deterministic_e2e, evaluate_bare_run\n"
        "from apps_rg.runtime.c03_graph_sqlite_context import ensure_c03_graph_sqlite\n"
        f"res = run_bare_deterministic_e2e(artifact_root={str(probe_dir)!r})\n"
        "run_dir = Path(str(res.get('artifact_dir', '')))\n"
        "ev = evaluate_bare_run(run_dir) if run_dir.is_dir() else {'status': 'FAIL'}\n"
        "db_path = ensure_c03_graph_sqlite(repo / 'resume_graph_engine')\n"
        "req_files = ('resume.md', 'resume.docx', 'outreach_email.md', 'sources.json', 'evaluation.json')\n"
        "present = [f for f in req_files if (run_dir / f).is_file() and (run_dir / f).stat().st_size > 0]\n"
        "ok = res.get('status') == 'SUCCESS' and ev.get('status') == 'PASS' and len(present) == len(req_files) and db_path.is_file()\n"
        "print(json.dumps({\n"
        "  'status': 'PASS' if ok else 'FAIL',\n"
        "  'outcome_label': str(res.get('outcome_label', '')),\n"
        "  'eval_status': str(ev.get('status', '')),\n"
        "  'artifact_dir': str(run_dir),\n"
        "  'artifacts_verified': present,\n"
        "  'c03_graph_db_exists': bool(db_path.is_file()),\n"
        "  'checks': ev.get('checks', {}),\n"
        "}, sort_keys=True))\n"
    )
    t0 = time.perf_counter()
    res = _run_subprocess_json(python_bin, script, cwd=repo_root, timeout=120)
    res["elapsed_s"] = round(time.perf_counter() - t0, 3)
    return res


def _probe_apps_lic_g5_g6(repo_root: Path, python_bin: str) -> dict[str, Any]:
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        f"repo = Path({str(repo_root)!r})\n"
        "for p in (repo, repo / 'outreach_engine' / 'src'):\n"
        "    if str(p) not in sys.path:\n"
        "        sys.path.insert(0, str(p))\n"
        "from apps_lic.evals.meta_eval import evaluate_g6_meta_calibration\n"
        "from apps_lic.evals.repeatability import evaluate_g5_repeatability\n"
        "g6 = evaluate_g6_meta_calibration()\n"
        "g5 = evaluate_g5_repeatability()\n"
        "ok = bool(g6.passed and g5.passed)\n"
        "print(json.dumps({\n"
        "  'status': 'PASS' if ok else 'FAIL',\n"
        "  'g6': {\n"
        "    'passed': bool(g6.passed),\n"
        "    'corpus_size': int(g6.corpus_size),\n"
        "    'clean_item_count': int(g6.clean_item_count),\n"
        "    'defective_item_count': int(g6.defective_item_count),\n"
        "    'spearman_rho': round(float(g6.spearman_rho), 6),\n"
        "    'cohens_kappa': round(float(g6.cohens_kappa), 6),\n"
        "    'fpr': round(float(g6.fpr), 6),\n"
        "    'tpr': round(float(g6.tpr), 6),\n"
        "    'per_defect_class_tpr': dict(g6.per_defect_class_tpr),\n"
        "    'violations': list(g6.violations),\n"
        "  },\n"
        "  'g5': {\n"
        "    'passed': bool(g5.passed),\n"
        "    'item_count': int(g5.item_count),\n"
        "    'k_runs': int(g5.k_runs),\n"
        "    'max_std': round(float(g5.max_std), 6),\n"
        "    'mean_std': round(float(g5.mean_std), 6),\n"
        "    'std_ceiling': float(g5.std_ceiling),\n"
        "    'violations': list(g5.violations),\n"
        "  },\n"
        "}, sort_keys=True))\n"
    )
    t0 = time.perf_counter()
    res = _run_subprocess_json(python_bin, script, cwd=repo_root, timeout=90)
    res["elapsed_s"] = round(time.perf_counter() - t0, 3)
    return res


def _probe_apps_lic_bundle(
    repo_root: Path,
    python_bin: str,
    bundle_dir: Path,
    *,
    existing_bundle_dir: Path | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    target_dir = existing_bundle_dir
    if target_dir is None:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                python_bin,
                "-m",
                "outreach_engine",
                "run",
                "--demo",
                "--offline-smoke",
                "--no-research",
                "--artifact-dir",
                str(bundle_dir),
                "--json",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
        if proc.returncode != 0:
            return {
                "status": "FAIL",
                "error": (proc.stderr or proc.stdout)[-800:],
                "elapsed_s": round(time.perf_counter() - t0, 3),
            }
        target_dir = bundle_dir

    adapter = OutreachEngineEvalAdapter(repo_root=repo_root)
    verification = adapter.verify_bundle(target_dir, require_judge_quorum_file=False, strict=False)
    snapshot = adapter.evaluate_bundle(target_dir, scenario_id="outreach_offline_smoke_bundle", strict=False)
    ok = bool(verification.get("valid", False) or verification.get("passed", False))
    return {
        "status": "PASS" if ok else "FAIL",
        "bundle_dir": str(target_dir),
        "x3_disposition": snapshot.x3_disposition,
        "artifact_count": len(snapshot.artifacts),
        "verification": verification,
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }


def _select_suites(app: str, include_holdout: bool) -> list[str]:
    selected: list[str] = []
    if app in ("all", "apps_rg"):
        selected.append("apps_rg.dev.resume_generation")
        if include_holdout:
            selected.append("apps_rg.holdout.resume_generation")
    if app in ("all", "apps_lic"):
        selected.append("apps_lic.dev.outreach_message")
        if include_holdout:
            selected.append("apps_lic.holdout.outreach_message")
    return selected


def run_unified_eval_harness(
    repo_root: str | Path,
    *,
    app: str = "all",
    mode: str = "offline",
    include_holdout: bool = True,
    fast_dev: bool = False,
    out_dir: str | Path | None = None,
    baseline_dir: str | Path | None = None,
    rg_run_dir: str | Path | None = None,
    lic_run_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Execute the unified Resume & Outreach evaluation harness and emit a sealed evidence manifest."""
    if app not in ("all", "apps_rg", "apps_lic"):
        raise ValueError(f"unsupported app filter: {app}")
    if mode not in ("offline", "live"):
        raise ValueError(f"unsupported mode: {mode}")

    root = Path(repo_root).resolve()
    python_bin = _resolve_python(root)
    target_out = (
        Path(out_dir).resolve()
        if out_dir is not None
        else (root / "artifacts" / "eval_harness" / "latest").resolve()
    )
    runs_dir = target_out / "runs"
    trends_dir = target_out / "trends"
    probes_dir = target_out / "probes"
    runs_dir.mkdir(parents=True, exist_ok=True)
    trends_dir.mkdir(parents=True, exist_ok=True)
    probes_dir.mkdir(parents=True, exist_ok=True)

    resolved_baseline_dir = (
        Path(baseline_dir).resolve()
        if baseline_dir is not None
        else (root / DEFAULT_BASELINE_DIR).resolve()
    )
    effective_holdout = include_holdout and not fast_dev
    suites = _select_suites(app, effective_holdout)

    from infrastructure.config.env_loader import temporary_env_override

    suite_receipts: dict[str, dict[str, Any]] = {}
    l6_shadow_receipts: dict[str, dict[str, Any]] = {}
    started_at = _utc_now()
    t_start = time.perf_counter()

    env_patch: dict[str, str | None] = {"APPS_EVAL_RELEASE_GATE": "1"} if effective_holdout else {}
    with temporary_env_override(env_patch):
        for suite_id in suites:
            bpath = baseline_path(suite_id, resolved_baseline_dir)
            record = run_eval(
                EvalRequest(
                    suite_id=suite_id,
                    mode="snapshot",
                    deterministic_only=True,
                    baseline_path=str(bpath) if bpath.is_file() else None,
                    out_dir=str(runs_dir),
                    emit_l6_handoff=True,
                )
            )
            record_path = Path(record.artifact_paths["eval_record"])
            record_dict = json.loads(record_path.read_text(encoding="utf-8"))
            sc_dict = record.scorecard.to_dict()

            baseline_cmp: dict[str, Any] = {"compared": False, "verdict": "missing_baseline", "delta": 0.0}
            if bpath.is_file():
                baseline_dict = load_baseline(suite_id, resolved_baseline_dir)
                cmp = compare_record_to_baseline(record_dict, baseline_dict)
                baseline_cmp = cmp.to_dict()

            graders_ok = (
                int(sc_dict.get("finding_count", 0)) > 0
                and int(sc_dict.get("passed_findings", 0)) == int(sc_dict.get("finding_count", 0))
            )
            suite_ok = graders_ok and (
                suite_id in SNAPSHOT_GRADER_ONLY_SUITES or str(sc_dict.get("verdict", "")) == "pass"
            )
            suite_receipts[suite_id] = {
                "suite_id": suite_id,
                "app_id": record.app_id,
                "split": suite_id.split(".")[1] if "." in suite_id else "",
                "record_id": record.record_id,
                "eval_record_path": record_path.as_posix(),
                "eval_record_sha256": _sha256_file(record_path),
                "regression_flywheel_path": str(record.artifact_paths.get("regression_flywheel", "")),
                "verdict": str(sc_dict.get("verdict", "")),
                "score": float(sc_dict.get("score", 0.0)),
                "finding_count": int(sc_dict.get("finding_count", 0)),
                "passed_findings": int(sc_dict.get("passed_findings", 0)),
                "failed_findings": int(sc_dict.get("failed_findings", 0)),
                "scenario_count": int(sc_dict.get("scenario_count", 0)),
                "graders_all_passed": graders_ok,
                "suite_passed": suite_ok,
                "baseline_comparison": baseline_cmp,
                "regression_flywheel": record.regression_flywheel.to_dict(),
            }
            l6_path_str = str(
                record.artifact_paths.get("l6_shadow_bridge")
                or record.artifact_paths.get("apps_rg_l6_eval_handoff")
                or ""
            )
            l6_path = Path(l6_path_str) if l6_path_str else None
            l6_shadow_receipts[suite_id] = {
                "present": bool(l6_path and l6_path.is_file()),
                "path": l6_path.as_posix() if l6_path and l6_path.is_file() else "",
                "sha256": _sha256_file(l6_path) if l6_path and l6_path.is_file() else "",
            }

    # Engine-level probes
    apps_rg_e2e_receipt: dict[str, Any] | None = None
    if app in ("all", "apps_rg"):
        if fast_dev:
            apps_rg_e2e_receipt = {"status": "SKIPPED_FAST_DEV", "skipped": True}
        elif mode == "live" and rg_run_dir:
            rg_dir = Path(rg_run_dir).resolve()
            eval_json = rg_dir / "evaluation.json"
            apps_rg_e2e_receipt = {
                "status": "PASS" if rg_dir.is_dir() else "FAIL",
                "mode": "live",
                "artifact_dir": str(rg_dir),
                "evaluation_present": eval_json.is_file(),
            }
        else:
            apps_rg_e2e_receipt = _probe_apps_rg_offline_e2e(root, python_bin, probes_dir / "apps_rg_e2e")

    apps_lic_g5_g6_receipt: dict[str, Any] | None = None
    apps_lic_bundle_receipt: dict[str, Any] | None = None
    if app in ("all", "apps_lic"):
        apps_lic_g5_g6_receipt = _probe_apps_lic_g5_g6(root, python_bin)
        if fast_dev:
            apps_lic_bundle_receipt = {"status": "SKIPPED_FAST_DEV", "skipped": True}
        else:
            existing_lic = Path(lic_run_dir).resolve() if (mode == "live" and lic_run_dir) else None
            apps_lic_bundle_receipt = _probe_apps_lic_bundle(
                root, python_bin, probes_dir / "apps_lic_bundle", existing_bundle_dir=existing_lic
            )

    # Trend dashboard & release gate over persisted runs (apps_lic full verdict check + overall trend)
    trend_summary = emit_trend_dashboard(
        records_root=runs_dir,
        out_dir=trends_dir,
        emit_l6_shadow=True,
    )
    release_gate_lic = emit_release_gate(
        records_root=runs_dir,
        app_id="apps_lic" if app in ("all", "apps_lic") else app,
        min_samples=1,
        min_latest_pass_rate=1.0 if app != "apps_rg" else 0.0,
        min_window_pass_rate=1.0 if app != "apps_rg" else 0.0,
        max_latest_score_drop=0.05,
        out_dir=trends_dir,
        emit_l6_shadow=True,
    )

    golden_flywheel_receipt = evaluate_golden_flywheel_suite(
        repo_root=root,
        app_filter=app,
    )

    manifest: dict[str, Any] = {
        "schema_version": EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "started_at": started_at,
        "elapsed_s": round(time.perf_counter() - t_start, 3),
        "repo_root": root.as_posix(),
        "app_filter": app,
        "mode": mode,
        "include_holdout": effective_holdout,
        "fast_dev": fast_dev,
        "baseline_dir": resolved_baseline_dir.as_posix(),
        "suite_receipts": suite_receipts,
        "l6_shadow_handoff_receipts": l6_shadow_receipts,
        "apps_rg_e2e_receipt": apps_rg_e2e_receipt,
        "apps_lic_g5_g6_receipt": apps_lic_g5_g6_receipt,
        "apps_lic_bundle_receipt": apps_lic_bundle_receipt,
        "golden_flywheel_receipt": golden_flywheel_receipt,
        "trend_dashboard": trend_summary.to_dict() if hasattr(trend_summary, "to_dict") else dict(trend_summary),
        "release_gate_receipt": (
            release_gate_lic.to_dict() if hasattr(release_gate_lic, "to_dict") else dict(release_gate_lic)
        ),
    }

    manifest_path = target_out / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_path"] = manifest_path.as_posix()
    manifest["manifest_sha256"] = _sha256_file(manifest_path)
    return manifest
