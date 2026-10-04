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


def build_run_manifest_data(
    artifact_dir: Path | str,
    *,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract usage records and assemble the canonical run manifest dictionary."""
    root = Path(artifact_dir).resolve()
    usage_file = root / "external_model_usage_ledger.jsonl"
    records: list[dict[str, Any]] = []
    if usage_file.is_file():
        try:
            records = [
                json.loads(line)
                for line in usage_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception:
            records = []

    rollup = compute_run_cost_rollup(records)

    reg_digest = ""
    try:
        from apps_rg.runtime.model_registry import get_registry_digest

        reg_digest = get_registry_digest()
    except Exception:
        pass

    req_models = sorted(
        list(
            {
                str(r.get("requested_model") or r.get("model"))
                for r in records
                if r.get("requested_model") or r.get("model")
            }
        )
    )
    obs_models = sorted(
        list(
            {
                str(r.get("observed_model") or r.get("model"))
                for r in records
                if r.get("observed_model") or r.get("model")
            }
        )
    )

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
