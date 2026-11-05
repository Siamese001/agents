"""Canonical Run Manifest builder for resume_engine and apps_rg.

Computes run-level telemetry rollups:
- Model Registry v2 digest
- Requested models and observed models
- Token rollup (input, output, cached, cache write, total)
- Cost rollup (total cost in USD, or "unpriced_model" indicator)
- Cache hit ratio
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from apps_model_telemetry.pricing import compute_run_cost_rollup


def _collect_usage_records_from_root_and_lanes(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect JSONL usage records and fallback lane run_manifest dicts without double-counting."""
    records: list[dict[str, Any]] = []
    seen_lines: set[str] = set()
    fallback_lane_manifests: list[dict[str, Any]] = []

    def _read_jsonl(p: Path) -> bool:
        if not p.is_file():
            return False
        added = False
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s or s in seen_lines:
                    continue
                seen_lines.add(s)
                records.append(json.loads(s))
                added = True
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            return False
        return added

    _read_jsonl(root / "external_model_usage_ledger.jsonl")

    lanes_dir = root / "lanes"
    if lanes_dir.is_dir():
        for lane_dir in sorted(p for p in lanes_dir.iterdir() if p.is_dir()):
            has_jsonl = _read_jsonl(lane_dir / "external_model_usage_ledger.jsonl")
            if not has_jsonl:
                mf_path = lane_dir / "run_manifest.json"
                if mf_path.is_file():
                    try:
                        doc = json.loads(mf_path.read_text(encoding="utf-8"))
                        if isinstance(doc, dict):
                            fallback_lane_manifests.append(doc)
                    except (OSError, json.JSONDecodeError, ValueError, TypeError):
                        pass
    return records, fallback_lane_manifests


def build_run_manifest_data(
    artifact_dir: Path | str,
    *,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract usage records and assemble the canonical run manifest dictionary."""
    root = Path(artifact_dir).resolve()
    records, fallback_lane_manifests = _collect_usage_records_from_root_and_lanes(root)

    rollup = compute_run_cost_rollup(records)

    reg_digest = ""
    try:
        from apps_rg.runtime.model_registry import get_registry_digest

        reg_digest = get_registry_digest()
    except (ImportError, OSError, ValueError, TypeError, RuntimeError):
        pass

    req_set = {
        str(r.get("requested_model") or r.get("model"))
        for r in records
        if r.get("requested_model") or r.get("model")
    }
    obs_set = {
        str(r.get("observed_model") or r.get("model"))
        for r in records
        if r.get("observed_model") or r.get("model")
    }
    for lmf in fallback_lane_manifests:
        for m in lmf.get("requested_models") or []:
            if m:
                req_set.add(str(m))
        for m in lmf.get("observed_models") or []:
            if m:
                obs_set.add(str(m))
        ltok = lmf.get("tokens")
        if isinstance(ltok, dict):
            for k in (
                "total_input_tokens",
                "total_output_tokens",
                "total_cached_tokens",
                "total_cache_write_tokens",
                "total_tokens",
            ):
                rollup[k] = int(rollup.get(k) or 0) + int(ltok.get(k) or 0)
        lcost = lmf.get("cost")
        if isinstance(lcost, dict):
            c_val = lcost.get("total_cost_usd")
            if isinstance(c_val, (int, float)):
                base_c = rollup.get("total_cost_usd")
                rollup["total_cost_usd"] = round(
                    (float(base_c) if isinstance(base_c, (int, float)) else 0.0) + float(c_val),
                    6,
                )

    req_models = sorted(req_set)
    obs_models = sorted(obs_set)

    if extra_fields:
        if not req_models and extra_fields.get("provider_requested"):
            req_models = [str(extra_fields["provider_requested"])]
        if not obs_models and extra_fields.get("provider_attempted"):
            obs_models = [str(extra_fields["provider_attempted"])]

    manifest: dict[str, Any] = {
        "schema_version": "apps_rg.run_manifest.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": root.name,
        "registry_digest": reg_digest,
        "requested_models": req_models,
        "observed_models": obs_models,
        "tokens": {
            "total_input_tokens": rollup["total_input_tokens"],
            "total_output_tokens": rollup["total_output_tokens"],
            "total_cached_tokens": rollup["total_cached_tokens"],
            "total_cache_write_tokens": rollup["total_cache_write_tokens"],
            "total_tokens": rollup["total_tokens"],
        },
        "cost": {
            "total_cost_usd": (
                rollup["total_cost_usd"]
                if rollup["total_cost_usd"] is not None
                else "unpriced_model"
            ),
            "has_unpriced_models": rollup["has_unpriced_models"],
            "status": (
                "unpriced_model"
                if rollup["has_unpriced_models"] and rollup["total_cost_usd"] is None
                else "ok"
            ),
        },
        "cache_hit_ratio": rollup["cache_hit_ratio"],
    }
    if extra_fields:
        manifest.update(extra_fields)
    return manifest
