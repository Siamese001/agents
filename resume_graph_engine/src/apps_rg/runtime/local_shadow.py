"""Apps RG-owned deterministic parity calculation for L6 shadow evidence."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence


SEALED_APPS_RG_OBSERVATION_ORIGIN = "apps_rg_sealed_runtime_observation"


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_artifact_hash(value: Any) -> str:
    """Return the canonical content hash for an app-owned JSON artifact."""

    return _digest(value)


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Read object rows from a local JSONL artifact, failing closed on bad rows."""

    rows: list[dict[str, Any]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL row {number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row {number} is not an object")
        rows.append(row)
    return rows


def write_independent_parity(path: Path | str, payload: Mapping[str, Any]) -> Path:
    """Atomically write an app-local parity result."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, target)
    return target


def build_independent_apps_eval_parity(
    *,
    run_id: str,
    runtime_exhaust_bundle_id: str,
    microstep_contract_digest: str,
    apps_eval_scorecard_ref: str,
    l6_observation_ref: str,
    apps_eval_rows: Sequence[Mapping[str, Any]],
    l6_observations: Sequence[Mapping[str, Any]],
    observation_origin: str,
    expected_observation_bundle_id: str,
    parent_run_id: str,
    child_run_id: str,
    section_attempt_id: str,
    eval_record_id: str,
    snapshot_digest: str,
    registry_digest: str,
    source_run_root: str,
    repository_root: str,
    compare_artifact_digests: bool,
) -> dict[str, Any]:
    """Compare persisted scorecard and observability rows without execution."""

    del source_run_root, repository_root, compare_artifact_digests
    expected_ids = {
        str(row.get("microstep_id") or row.get("row_id") or "")
        for row in apps_eval_rows
        if str(row.get("microstep_id") or row.get("row_id") or "")
    }
    observed_ids = {
        str(row.get("microstep_id") or row.get("observation_id") or "")
        for row in l6_observations
        if str(row.get("microstep_id") or row.get("observation_id") or "")
    }
    reasons: list[str] = []
    if observation_origin != SEALED_APPS_RG_OBSERVATION_ORIGIN:
        reasons.append("observation_origin_invalid")
    if not runtime_exhaust_bundle_id:
        reasons.append("runtime_exhaust_bundle_id_missing")
    if runtime_exhaust_bundle_id != expected_observation_bundle_id:
        reasons.append("runtime_exhaust_bundle_id_mismatch")
    if not expected_ids:
        reasons.append("apps_eval_rows_missing")
    if not observed_ids:
        reasons.append("l6_observations_missing")
    missing = sorted(expected_ids - observed_ids)
    if missing:
        reasons.append("unobserved_microsteps:" + ",".join(missing))
    status = "PASS" if not reasons else "FAIL"
    payload = {
        "schema_version": "apps_rg.local_independent_parity.v1",
        "run_id": run_id,
        "eval_record_id": eval_record_id,
        "runtime_exhaust_bundle_id": runtime_exhaust_bundle_id,
        "microstep_contract_digest": microstep_contract_digest,
        "apps_eval_scorecard_ref": apps_eval_scorecard_ref,
        "l6_observation_ref": l6_observation_ref,
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "section_attempt_id": section_attempt_id,
        "snapshot_digest": snapshot_digest,
        "registry_digest": registry_digest,
        "apps_eval_row_count": len(apps_eval_rows),
        "l6_observation_row_count": len(l6_observations),
        "independent_observations": bool(l6_observations),
        "expected_microstep_ids": sorted(expected_ids),
        "observed_microstep_ids": sorted(observed_ids),
        "proof_gaps": reasons,
        "grain_parity_status": status,
    }
    payload["parity_digest"] = _digest(payload)
    return payload


__all__ = [
    "SEALED_APPS_RG_OBSERVATION_ORIGIN",
    "build_independent_apps_eval_parity",
    "compute_artifact_hash",
    "read_jsonl",
    "write_independent_parity",
]
