"""Compatibility location for the app-owned runtime producer normalizer.

The active single-action runner now emits its own sealed bundle.  This module
remains only as a stable import location for callers that need the local
outcome projection helper.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.failure_evidence import atomic_write_json


ADAPTER_SCHEMA = "apps_rg.runtime_producer_adapter.v2"
L2_SEALED_ARTIFACT = "l2_sealed_artifact.json"


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def emit_l2_sealed_projection(
    artifact_dir: Path,
    witness: Mapping[str, Any],
) -> str:
    """Seal the app-owned L2 projection derived from a runtime witness."""

    root = Path(artifact_dir).resolve()
    l2 = witness.get("l2") if isinstance(witness.get("l2"), Mapping) else {}
    payload = {
        "schema_version": "apps_rg.l2_sealed_projection.v2",
        "producer_adapter": ADAPTER_SCHEMA,
        "run_id": str(witness.get("run_id") or ""),
        "request_id": str(witness.get("request_id") or ""),
        "trace_root": str(witness.get("trace_root") or ""),
        "route_id": str(witness.get("route_id") or ""),
        "executed": bool(l2.get("executed")),
        "status": str(l2.get("status") or "UNKNOWN"),
        "fault": str(l2.get("fault") or ""),
        "sub_stages": list(l2.get("sub_stages") or []),
        "source_witness_ref": "runtime_execution_witness.json",
    }
    artifact_hash = _digest(payload)
    atomic_write_json(
        root / L2_SEALED_ARTIFACT,
        {
            "producer_component": "apps_rg.runtime.orchestration.runtime_producer_adapter",
            "producer_module": "runtime_producer_adapter",
            "producer_function_or_class": "emit_l2_sealed_projection",
            "artifact_hash": artifact_hash,
            "payload": payload,
        },
    )
    return artifact_hash


__all__ = ["ADAPTER_SCHEMA", "L2_SEALED_ARTIFACT", "emit_l2_sealed_projection"]
