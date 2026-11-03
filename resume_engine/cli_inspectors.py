"""Read-only inspection and CLI process exit helpers for resume_engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from pathlib import Path


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
