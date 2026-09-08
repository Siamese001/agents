"""Freeze one preserved Apps RG run as the immutable RCA input boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping


FREEZE_FILENAME = "single_run_w0_input_freeze.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w0.v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object: {path}")
    return parsed, payload


def _file_reference(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": _sha256_bytes(payload),
        "semantic_digest": str(json.loads(payload.decode("utf-8")).get("semantic_digest", "")),
    }


def emit_single_run_w0_freeze(
    *,
    source_run: Path,
    w5_completion_path: Path,
    integrated_manifest_path: Path,
    output_dir: Path,
    source_manifest_builder: Callable[[Path], Mapping[str, Any]],
) -> dict[str, Any]:
    """Emit a deterministic, source-bound input receipt without replaying a stage."""

    source = source_run.resolve(strict=True)
    completion_path = w5_completion_path.resolve(strict=True)
    integrated_path = integrated_manifest_path.resolve(strict=True)
    completion, completion_bytes = _read_json(completion_path)
    integrated, integrated_bytes = _read_json(integrated_path)

    source_run_id = source.name
    real_run_ids = completion.get("real_run_ids")
    if not isinstance(real_run_ids, list) or source_run_id not in real_run_ids:
        raise ValueError(
            "selected source run is not bound by the supplied W5 completion receipt: "
            f"{source_run_id}"
        )
    if completion.get("status") != "PASS" or completion.get("scope_complete") is not True:
        raise ValueError("W5 completion receipt is not a complete PASS receipt")
    if integrated.get("status") != "PASS":
        raise ValueError("integrated W5 manifest is not PASS")

    source_manifest = dict(source_manifest_builder(source))
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W0",
        "status": "PASS",
        "scope": "SINGLE_RUN_RCA_INPUT_FREEZE",
        "replay_mode": "POST_RUNTIME_ARTIFACT_ONLY",
        "source_run_id": source_run_id,
        "source_run": source.as_posix(),
        "source_manifest_sha256": source_manifest["content_sha256"],
        "source_file_count": source_manifest["file_count"],
        "source_total_bytes": source_manifest["total_bytes"],
        "w5_completion": _file_reference(completion_path, completion_bytes),
        "integrated_manifest": _file_reference(integrated_path, integrated_bytes),
        "historical_scope": {
            "generation_lanes": 11,
            "judges": 21,
            "contract_handoffs": 21,
        },
        "allowed_work": [
            "deterministic_artifact_extraction",
            "deterministic_rca_rendering",
            "local_schema_and_digest_verification",
        ],
        "prohibited_work": [
            "apps_research_execution",
            "generation_execution",
            "provider_execution",
            "model_execution",
            "judge_execution",
            "embedding_execution",
            "network_execution",
            "source_run_mutation",
        ],
        "next_wave_authorized": True,
    }
    receipt["semantic_digest"] = _sha256_bytes(_canonical_json(receipt).encode("utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / FREEZE_FILENAME
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": receipt_path.as_posix()}


__all__ = ["FREEZE_FILENAME", "SCHEMA_VERSION", "emit_single_run_w0_freeze"]
