"""Read-only inspection and CLI process exit helpers for resume_engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any


def add_inspector_subparsers(subparsers: Any) -> None:
    """Register preflight, models, cache, and doctor subcommands on the CLI parser."""
    preflight_parser = subparsers.add_parser(
        "preflight", help="validate provider credentials and live execution readiness"
    )
    preflight_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON preflight status.",
    )

    models_parser = subparsers.add_parser(
        "models", help="inspect resolved roles, pins, and catalog digest (read-only)"
    )
    models_parser.add_argument(
        "--role",
        default="",
        help="Optional specific role or section to inspect.",
    )
    models_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output.",
    )

    cache_parser = subparsers.add_parser(
        "cache", help="inspect briefing and vector cache status (read-only)"
    )
    cache_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit structured JSON output.",
    )

    doctor_parser = subparsers.add_parser(
        "doctor", help="fresh-checkout preflight diagnostics"
    )
    doctor_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any required prerequisite is missing.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    doctor_parser.add_argument(
        "doctor_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments forwarded to doctor CLI.",
    )


def build_run_flywheel_trace_kwargs(
    args: argparse.Namespace,
    result: dict[str, Any],
    elapsed_ms: float,
) -> dict[str, Any]:
    """Assemble post-run flywheel trace arguments for ``emit_post_run_trace_safe``."""
    from agents.observability.trace_collector import compute_scenario_fingerprint

    run_dir_str = str(result.get("artifact_dir") or result.get("run_dir") or "")
    is_smoke = bool(getattr(args, "offline_smoke", False) or getattr(args, "demo", False))
    raw_in = {
        "company": str(getattr(args, "company", "") or result.get("company") or ""),
        "role": str(getattr(args, "role", "") or result.get("role") or ""),
        "jd_path": str(getattr(args, "jd", "") or getattr(args, "jd_path", "") or ""),
        "offline_smoke": is_smoke,
    }
    scen_fp = compute_scenario_fingerprint(
        app_id="apps_rg",
        raw_input=raw_in,
        is_smoke_or_demo=is_smoke,
    )
    checks_map = result.get("checks") if isinstance(result.get("checks"), dict) else {}
    x2_map = (
        {str(k): bool(v) for k, v in checks_map.items()}
        if checks_map
        else {"terminal_success": result.get("status") == "SUCCESS"}
    )
    gate_outcomes: dict[str, Any] = {
        "status": result.get("status"),
        "outcome_label": str(result.get("outcome_label") or ""),
        "x3_disposition": str(result.get("x3_disposition") or ""),
        "x2_gates": x2_map,
    }
    if result.get("fault"):
        gate_outcomes["fault"] = str(result.get("fault"))
    if result.get("failure_stage"):
        gate_outcomes["failure_stage"] = str(result.get("failure_stage"))
    if result.get("error"):
        gate_outcomes["error"] = str(result.get("error"))
    return {
        "app_id": "apps_rg",
        "run_id": str(result.get("run_id") or "resume_run"),
        "terminal_status": "PASS" if result.get("status") == "SUCCESS" else "FAIL",
        "raw_input": raw_in,
        "output_summary": {
            "run_dir": run_dir_str,
            "outcome_label": str(result.get("outcome_label") or ""),
            "scenario_fingerprint": scen_fp,
        },
        "gate_outcomes": gate_outcomes,
        "telemetry": {"latency_ms": float(result.get("latency_ms") or elapsed_ms)},
        "scenario_fingerprint": scen_fp,
        "is_smoke_or_demo": is_smoke,
    }


def record_eval_flywheel_observation(
    run_path: Path,
    report: dict[str, Any],
    elapsed_ms: float,
) -> dict[str, Any]:
    """Ingest a read-only product evaluation into EvalFlywheelEngine and build trace kwargs."""
    from agents.observability.eval_flywheel import EvalFlywheelEngine
    from agents.observability.trace_collector import compute_scenario_fingerprint

    passed = report.get("status") == "PASS"
    observed_x3 = str(report.get("x3_disposition") or "").strip()
    effective_x3 = (
        "X3D_ALLOW_FINISH"
        if passed
        else (observed_x3 if observed_x3 and observed_x3 != "X3D_ALLOW_FINISH" else "X3A_DENY_REROUTE")
    )
    reasons = [str(r) for r in (report.get("failure_reasons") or ()) if str(r).strip()]
    if not passed and not reasons:
        reasons = [f"evaluation_status:{report.get('evaluation_status') or 'BLOCKED'}"]
    scen_fp = compute_scenario_fingerprint(
        app_id="apps_rg",
        raw_input={"run_id": run_path.name, "company": str(report.get("company") or "")},
    )
    EvalFlywheelEngine().ingest_product_run(
        app_id="apps_rg",
        run_id=run_path.name,
        x3_disposition=effective_x3,
        passed=passed,
        failure_reasons=reasons,
        score=1.0 if passed else 0.0,
        scenario_fingerprint=scen_fp,
    )
    checks_map = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    return {
        "app_id": "apps_rg",
        "run_id": run_path.name,
        "terminal_status": "PASS" if passed else "FAIL",
        "raw_input": {"run_dir": str(run_path), "scenario_fingerprint": scen_fp},
        "output_summary": {"run_dir": str(run_path), "x3_disposition": effective_x3},
        "gate_outcomes": {
            "x3_disposition": effective_x3,
            "failure_reasons": reasons,
            "x2_gates": {str(k): bool(v) for k, v in checks_map.items()}
            if checks_map
            else {"eval_passed": passed},
        },
        "telemetry": {"latency_ms": elapsed_ms},
        "scenario_fingerprint": scen_fp,
    }


def terminate_cli_cleanly(exit_code: int) -> None:
    """Flush stdout/stderr and enforce a 1.5s watchdog exit if background threads linger."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except OSError:
        pass

    active_non_daemon = [
        t
        for t in threading.enumerate()
        if t is not threading.main_thread() and not t.daemon and t.is_alive()
    ]
    if active_non_daemon:
        timer = threading.Timer(1.5, lambda: os._exit(exit_code))
        timer.daemon = True
        timer.start()
    sys.exit(exit_code)


def handle_models(args: argparse.Namespace) -> int:
    """Read-only inspection of model catalog, provider profiles, and registry digest."""
    repo_root = Path(__file__).resolve().parent.parent
    profile_path = repo_root / "config" / "provider_profiles.yaml"
    if not profile_path.is_file():
        profile_path = (
            repo_root / "resume_graph_engine" / "src" / "apps_rg" / "config" / "provider_profiles.yaml"
        )
    catalog_path = repo_root / "config" / "model_catalog.json"
    if not catalog_path.is_file():
        catalog_path = repo_root / "resume_graph_engine" / "config" / "model_catalog.json"

    profiles_text = profile_path.read_text(encoding="utf-8") if profile_path.is_file() else ""
    catalog_text = catalog_path.read_text(encoding="utf-8") if catalog_path.is_file() else ""

    digest_input = profiles_text + "\n---\n" + catalog_text
    canonical_digest = "sha256:" + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    fallback_reasons: list[str] = []

    try:
        from apps_rg.runtime.model_registry import (
            registry_digest as get_reg_digest,
        )

        canonical_digest = "sha256:" + get_reg_digest()
    except Exception as exc:
        fallback_reasons.append(f"registry_digest_fallback:{type(exc).__name__}")

    import yaml

    data = yaml.safe_load(profiles_text) if profiles_text else {}
    registry_id = data.get("provider_profile_registry_id", "apps_rg::provider_profiles::v1")
    profiles = data.get("profiles", {})

    generation_pins: dict[str, str] = {}
    backup_pins: dict[str, str] = {}
    for prof in profiles.values():
        if isinstance(prof, dict):
            for sec, m in (prof.get("model_by_section") or {}).items():
                generation_pins[sec] = m
            for sec, m in (prof.get("anthropic_limit_backup_model_by_section") or {}).items():
                backup_pins[sec] = m

    payload: dict[str, object] = {
        "status": "PASS",
        "registry_id": registry_id,
        "canonical_digest": canonical_digest,
        "embedding_model": "BAAI/bge-m3",  # guardian: allow-model-id -- canonical BGE-M3 embedding model
        "embedding_dimension": 1024,
        "generation_pins": generation_pins,
        "backup_pins": backup_pins,
        "profiles_file": str(profile_path),
        "catalog_file": str(catalog_path),
    }
    if fallback_reasons:
        payload["fallback_reasons"] = fallback_reasons

    if getattr(args, "role", ""):
        role = args.role
        pinned = generation_pins.get(role) or backup_pins.get(role)
        try:
            from apps_rg.runtime.model_registry import resolve as resolve_reg_role

            resolved_obj = resolve_reg_role(role)
            pinned = resolved_obj.snapshot_id
        except Exception as exc:
            fallback_reasons.append(f"role_resolve_fallback:{type(exc).__name__}")
        payload["queried_role"] = role
        payload["resolved_pin"] = pinned or "UNRESOLVED"

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Registry ID:        {registry_id}")
        print(f"Canonical Digest:   {canonical_digest}")
        print("Embedding Model:    BAAI/bge-m3 (dim: 1024)")  # guardian: allow-model-id -- CLI summary display
        print(f"Profiles File:      {profile_path}")
        print("\n--- Section Generation Pins ---")
        for sec, pin in sorted(generation_pins.items()):
            print(f"  {sec:<25} -> {pin}")
        if backup_pins:
            print("\n--- Anthropic Limit Backup Pins ---")
            for sec, pin in sorted(backup_pins.items()):
                print(f"  {sec:<25} -> {pin}")
    return 0


def handle_cache(args: argparse.Namespace) -> int:
    """Read-only inspection of application and semantic cache directories."""
    repo_root = Path(__file__).resolve().parent.parent
    briefing_dir = repo_root / "artifacts" / "apps_rg" / "cache" / "briefings"
    vector_dir = repo_root / "artifacts" / "apps_rg" / "vector_indices"

    briefing_count = len(list(briefing_dir.glob("*.json"))) if briefing_dir.is_dir() else 0
    vector_indices = [p.name for p in vector_dir.iterdir() if p.is_dir()] if vector_dir.is_dir() else []

    payload = {
        "status": "PASS",
        "briefing_cache": {
            "path": str(briefing_dir),
            "exists": briefing_dir.is_dir(),
            "cached_briefings_count": briefing_count,
        },
        "vector_cache": {
            "path": str(vector_dir),
            "exists": vector_dir.is_dir(),
            "indexed_collections": vector_indices,
        },
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("--- Apps RG Cache Inspection ---")
        print(f"Briefing Cache:  {briefing_dir} (cached items: {briefing_count})")
        print(f"Vector Cache:    {vector_dir} (indices: {len(vector_indices)})")
        for idx in vector_indices:
            print(f"  - {idx}")
    return 0
