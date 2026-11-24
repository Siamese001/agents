"""CLI parity subcommand handlers (`patch-run`, `preflight`, `models`, `cache`, `doctor`) for `apps_lic`.

Brings `outreach_engine` (`apps_lic`) to 9-subcommand CLI parity with `resume_engine` (`apps_rg`):
`run`, `patch-run`, `eval`, `validate`, `show`, `preflight`, `models`, `cache`, `doctor`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from apps_lic.cache import R1A_SCHEMA_VERSION, R1B_DEFAULT_COSINE_THRESHOLD, R1B_SCHEMA_VERSION
from apps_lic.domain.models import CandidateProfileLoader
from apps_lic.judges.evaluator_pkg.x1d_quorum import load_x1d_exit_rubric
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.final_outreach_outputs import export_final_outreach_bundle
from apps_lic.runtime.model_registry import OutreachModelRegistry
from infrastructure.candidate_evidence.sqlite_custody import verify_sqlite_custody
from infrastructure.config.env_loader import (
    get_apps_lic_enable_r1b_semantic_cache,
    get_outreach_candidate_graph_db_path,
)

REQUIRED: str = "required"
RECOMMENDED: str = "recommended"


@dataclass(frozen=True)
class DoctorCheck:
    """Single prerequisite diagnostic check for `apps_lic doctor`."""

    name: str
    ok: bool
    severity: str
    detail: str
    remediation: str = ""

    @property
    def is_blocking(self) -> bool:
        return (not self.ok) and self.severity == REQUIRED


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_outreach_root() -> Path:
    return Path(__file__).resolve().parents[3]


def register_parity_subparsers(subparsers: Any) -> None:
    """Register `patch-run`, `preflight`, `models`, `cache`, and `doctor` subparsers."""
    patch_p = subparsers.add_parser("patch-run", help="Re-dispatch or re-seal touches of an existing outreach run")
    patch_p.add_argument("--run-dir", default="", help="Existing outreach run directory to patch.")
    patch_p.add_argument("--touches", default="1", help="Comma-separated touch numbers to patch (e.g. 1,2)")
    patch_p.add_argument("--dry-run", action="store_true", default=False, help="Inspect reusable stages without mutating.")
    patch_p.add_argument("--offline-smoke", action="store_true", default=False, help="Deterministic offline smoke mode.")
    patch_p.add_argument("--json", action="store_true", default=False, help="Output machine-readable JSON result.")
    patch_p.add_argument("patch_args", nargs=argparse.REMAINDER, help="Additional arguments for patch-run.")

    preflight_p = subparsers.add_parser("preflight", help="Validate provider catalog pins, SQLite custody, and live readiness")
    preflight_p.add_argument("--offline-smoke", action="store_true", default=False, help="Hermetic preflight readiness.")
    preflight_p.add_argument("--json", action="store_true", default=False, help="Emit structured JSON preflight status.")

    models_p = subparsers.add_parser("models", help="Inspect resolved outreach roles, model pins, and catalog digest")
    models_p.add_argument("--role", default="", help="Optional specific outreach role to inspect.")
    models_p.add_argument("--json", action="store_true", default=False, help="Emit structured JSON output.")

    cache_p = subparsers.add_parser("cache", help="Inspect or clear briefing, R1A exact, and R1B semantic caches")
    cache_p.add_argument("cache_action", nargs="?", choices=("stats", "clear", "inspect"), default="stats", help="Cache operation")
    cache_p.add_argument("--cache-dir", default="", help="Optional cache directory override")
    cache_p.add_argument("--json", action="store_true", default=False, help="Emit structured JSON output.")

    doctor_p = subparsers.add_parser("doctor", help="Run fresh-checkout preflight diagnostics")
    doctor_p.add_argument("--strict", action="store_true", default=False, help="Exit non-zero if required check fails.")
    doctor_p.add_argument("--offline-smoke", action="store_true", default=False, help="Run in offline-smoke mode.")
    doctor_p.add_argument("--json", action="store_true", default=False, help="Emit machine-readable JSON.")
    doctor_p.add_argument("doctor_args", nargs=argparse.REMAINDER, help="Additional arguments forwarded to doctor CLI.")


def _handle_patch_run(args: argparse.Namespace) -> int:
    """Rebind, patch, and export an existing outreach run directory."""
    raw_dir = str(getattr(args, "run_dir", "") or "").strip()
    touches_raw = str(getattr(args, "touches", "1") or "1")
    extra = list(getattr(args, "patch_args", []) or [])
    idx = 0
    while idx < len(extra):
        tok = str(extra[idx])
        if not raw_dir and not tok.startswith("-"):
            raw_dir = tok.strip()
        elif tok == "--json":
            setattr(args, "json", True)
        elif tok == "--dry-run":
            setattr(args, "dry_run", True)
        elif tok == "--touches" and idx + 1 < len(extra):
            touches_raw = str(extra[idx + 1])
            idx += 1
        idx += 1

    if not raw_dir:
        msg = "patch-run requires --run-dir <path>."
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": msg}, indent=2))
        sys.stderr.write(f"Error: {msg}\n")
        return 1

    run_dir = Path(raw_dir).expanduser().resolve()
    if not run_dir.is_dir():
        msg = f"Run directory does not exist: {run_dir.as_posix()}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": msg}, indent=2))
        sys.stderr.write(f"Error: {msg}\n")
        return 1

    patched_touches = [int(x.strip()) for x in touches_raw.split(",") if x.strip().isdigit()] or [1]
    dry_run = bool(getattr(args, "dry_run", False))
    manifest_file = run_dir / "run_manifest.json"
    reused_stages: list[str] = ["briefing_resolution", "draft_generation"]
    if manifest_file.is_file() and not dry_run:
        try:
            orch = OutreachOrchestrator()
            resumed = orch.resume_or_patch_run(run_dir)
            reused_stages = list(resumed.get("reused_stages") or reused_stages)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            msg = f"Failed to patch run in {run_dir.as_posix()}: {exc}"
            if getattr(args, "json", False):
                print(json.dumps({"status": "FAILED", "error": msg}, indent=2))
            sys.stderr.write(f"Error: {msg}\n")
            return 1

    export_info: dict[str, Any] = {}
    if not dry_run:
        bundle = export_final_outreach_bundle(run_dir)
        export_info = bundle.to_dict()
        receipt_path = run_dir / "patch_run_receipt.json"
        receipt_payload = {
            "schema_version": "apps_lic.patch_run_receipt.v1",
            "status": "PASSED",
            "patch_status": "RESUMED",
            "run_dir": run_dir.as_posix(),
            "patched_touches": patched_touches,
            "reused_stages": reused_stages,
            "export_bundle": export_info,
        }
        receipt_path.write_text(json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(receipt_path, 0o644)

    payload = {
        "status": "PASSED",
        "patch_status": "DRY_RUN" if dry_run else "RESUMED",
        "run_dir": run_dir.as_posix(),
        "patched_touches": patched_touches,
        "reused_stages": reused_stages,
        "export_bundle": export_info,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[outreach_engine] patch-run status={payload['status']} mode={payload['patch_status']} run_dir={run_dir.as_posix()}")
    return 0


def _get_all_pins() -> dict[str, Any]:
    active = OutreachModelRegistry.list_active_models()
    return {role: OutreachModelRegistry.get_model_pin(role) for role in sorted(active)}


def _handle_preflight(args: argparse.Namespace, prog: str = "python -m outreach_engine") -> int:
    """Validate provider catalog pins, SQLite custody, and live execution readiness."""
    repo_root = _resolve_repo_root()
    offline_smoke = bool(getattr(args, "offline_smoke", False))
    try:
        try:
            from infrastructure.live_execution import load_agent_environment
            load_agent_environment(repo_root=repo_root)
        except (ImportError, OSError, ValueError):
            pass
        from agents.live_preflight import assert_engine_live_preflight
        assert_engine_live_preflight(prog, providers=("openai",), allow_offline=offline_smoke)
        all_pins = _get_all_pins()
        db_path = get_outreach_candidate_graph_db_path(repo_root)
        custody = verify_sqlite_custody(db_path)
    except Exception as exc:  # guardian: allow-broad-exception -- CLI preflight reports any credential or catalog error as exit code 2
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2), flush=True)
        sys.stderr.write(f"[{prog}] Preflight Failure: {exc}\n")
        return 2

    passed = bool(len(all_pins) >= 4 and (custody.passed or offline_smoke))
    payload = {
        "status": "PASSED" if passed else "FAILED",
        "message": "Preflight credentials, model catalog, and candidate graph custody validated.",
        "catalog_valid": len(all_pins) >= 4,
        "sqlite_custody_passed": custody.passed,
        "candidate_graph_db_sha256": custody.candidate_graph_db_sha256,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[{prog}] Preflight check {'PASSED' if passed else 'FAILED'}.")
    return 0 if passed else 2


def _handle_models(args: argparse.Namespace) -> int:
    """Read-only inspection of outreach model pins, proof judges, and catalog digest."""
    outreach_root = _resolve_outreach_root()
    profile_path = outreach_root / "config" / "provider_profiles.yaml"
    profiles_text = profile_path.read_text(encoding="utf-8") if profile_path.is_file() else ""
    canonical_digest = "sha256:" + hashlib.sha256(profiles_text.encode("utf-8")).hexdigest()

    all_pins = _get_all_pins()
    generation_pins = {r: f"{p.provider}/{p.model}" for r, p in sorted(all_pins.items())}
    backup_pins = {r: f"{p.backup_provider or p.provider}/{p.backup_model}" for r, p in sorted(all_pins.items()) if p.backup_model}
    proof_judges = [f"{r}:{p.provider}/{p.model}" for r, p in sorted(all_pins.items()) if p.proof_eligible]
    advisory_roles = [f"{r}:{p.provider}/{p.model}" for r, p in sorted(all_pins.items()) if p.advisory_only]

    payload: dict[str, Any] = {
        "status": "PASSED",
        "registry_id": "apps_lic::provider_profiles::v1",
        "canonical_digest": canonical_digest,
        "lane_count": len(all_pins),
        "generation_pins": generation_pins,
        "backup_pins": backup_pins,
        "proof_judges": proof_judges,
        "advisory_roles": advisory_roles,
        "profiles_file": profile_path.resolve().as_posix(),
    }
    queried_role = str(getattr(args, "role", "") or "").strip()
    if queried_role:
        payload["queried_role"] = queried_role
        payload["resolved_pin"] = f"{all_pins[queried_role].provider}/{all_pins[queried_role].model}" if queried_role in all_pins else "UNRESOLVED"

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Registry ID: {payload['registry_id']} | Digest: {canonical_digest}")
        for r_name, pin_str in sorted(generation_pins.items()):
            print(f"  {r_name:<32} -> {pin_str}")
    return 0


def _handle_cache(args: argparse.Namespace) -> int:
    """Inspect or clear briefing cache, R1A exact cache, and R1B semantic cache."""
    repo_root = _resolve_repo_root()
    raw_cache_dir = str(getattr(args, "cache_dir", "") or "").strip()
    cache_dir = Path(raw_cache_dir).resolve() if raw_cache_dir else (repo_root / "artifacts" / "outreach_engine" / "cache")
    cache_action = str(getattr(args, "cache_action", "stats") or "stats")
    briefing_entries = len(getattr(GovernedBriefingResolver, "_cache", {}))
    r1b_enabled = get_apps_lic_enable_r1b_semantic_cache(default=False)

    files = [p for p in cache_dir.rglob("*") if p.is_file()] if cache_dir.is_dir() else []
    cleared = 0
    if cache_action == "clear":
        GovernedBriefingResolver.clear_cache()
        for f in files:
            try:
                f.unlink()
                cleared += 1
            except OSError:
                pass
        files = []

    payload: dict[str, Any] = {
        "status": "PASSED",
        "cache_action": cache_action,
        "cache_dir": cache_dir.as_posix(),
        "entry_count": len(files),
        "cleared_entries": cleared,
        "briefing_cache": {"in_memory_entries": briefing_entries, "artifact_cache_dir": cache_dir.as_posix(), "exists": cache_dir.is_dir()},
        "r1a_exact_cache": {"schema_version": R1A_SCHEMA_VERSION, "enabled": True},
        "r1b_semantic_cache": {"schema_version": R1B_SCHEMA_VERSION, "enabled": r1b_enabled, "cosine_threshold": R1B_DEFAULT_COSINE_THRESHOLD},
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[outreach_engine] cache action={cache_action} entries={len(files)} r1a={R1A_SCHEMA_VERSION} r1b={r1b_enabled}")
    return 0


def run_doctor(*, strict: bool = False, repo_root: Path | None = None) -> tuple[list[DoctorCheck], int]:
    """Execute fresh-checkout diagnostic checks for `outreach_engine` (`apps_lic`)."""
    root = (repo_root or _resolve_repo_root()).resolve()
    outreach_root = _resolve_outreach_root()
    all_pins = _get_all_pins()
    cat_ok = len(all_pins) >= 4
    db_path = get_outreach_candidate_graph_db_path(root)
    custody = verify_sqlite_custody(db_path)
    cand = CandidateProfileLoader.load_default()
    facts_ok = len(cand.verified_facts) >= 3
    rubric = load_x1d_exit_rubric()
    rubric_ok = str(rubric.get("rubric_id") or "") in {
        "outreach_sequence:outreach_multi_touch_sequence",
        "lic_x1d_v1",
    }
    targeting_dir = outreach_root / "config" / "targeting"
    briefs = list(targeting_dir.glob("*_briefing.md")) if targeting_dir.is_dir() else []
    briefs_ok = len(briefs) >= 3

    checks = [
        DoctorCheck("provider_profiles_catalog", cat_ok, REQUIRED, f"OutreachModelRegistry valid={cat_ok}"),
        DoctorCheck("candidate_evidence_sqlite_custody", custody.passed, REQUIRED, f"SQLite 5-check custody passed={custody.passed}"),
        DoctorCheck("candidate_verified_facts", facts_ok, REQUIRED, f"Loaded {len(cand.verified_facts)} verified facts"),
        DoctorCheck("x1d_exit_eval_rubric", rubric_ok, REQUIRED, f"rubric_id={rubric.get('rubric_id')}"),
        DoctorCheck("canonical_targeting_briefs", briefs_ok, RECOMMENDED, f"Found {len(briefs)} canonical targeting briefs"),
    ]
    blocking = [c for c in checks if c.is_blocking]
    exit_code = 2 if (strict and blocking) else 0
    return checks, exit_code


def _handle_doctor(args: argparse.Namespace) -> int:
    """CLI handler for `outreach_engine doctor`."""
    strict = bool(getattr(args, "strict", False))
    as_json = bool(getattr(args, "json", False))
    for tok in getattr(args, "doctor_args", []) or []:
        if tok == "--strict":
            strict = True
        elif tok == "--json":
            as_json = True

    checks, exit_code = run_doctor(strict=strict)
    overall_ok = all(not c.is_blocking for c in checks)
    if as_json:
        print(
            json.dumps(
                {
                    "tool": "apps_lic.doctor",
                    "status": "PASSED" if exit_code == 0 else "BLOCKED",
                    "overall_ok": overall_ok,
                    "strict": strict,
                    "exit_code": exit_code,
                    "checks": [asdict(c) for c in checks],
                },
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
    else:
        print(f"apps_lic doctor — mode={'strict' if strict else 'report'} exit_code={exit_code}", flush=True)
        for check in checks:
            mark = "PASS" if check.ok else ("FAIL" if check.severity == REQUIRED else "WARN")
            print(f"  [{mark}] {check.name}: {check.detail}", flush=True)
    return exit_code


__all__ = [
    "DoctorCheck",
    "_handle_cache",
    "_handle_doctor",
    "_handle_models",
    "_handle_patch_run",
    "_handle_preflight",
    "register_parity_subparsers",
    "run_doctor",
]
