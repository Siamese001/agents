"""Seal non-product acceptance semantics for a canonical single-run RCA."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DECISION_FILENAME = "single_run_w3_acceptance_decision.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w3.v1"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object: {path}")
    return parsed, payload


def _binding(path: Path, payload: bytes) -> dict[str, Any]:
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "semantic_digest": str(json.loads(payload.decode("utf-8")).get("semantic_digest", "")),
    }


def emit_single_run_w3_acceptance_decision(*, w2_manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    """Write an explicit non-product acceptance decision from the canonical RCA."""

    manifest_path = w2_manifest_path.resolve(strict=True)
    manifest, manifest_bytes = _read_json(manifest_path)
    terminal = manifest.get("terminal_state")
    timeline = manifest.get("timeline")
    causes = manifest.get("root_causes")
    if not isinstance(terminal, dict) or not isinstance(timeline, dict) or not isinstance(causes, dict):
        raise ValueError("W2 canonical RCA is incomplete")
    post_runtime = timeline.get("post_runtime")
    if (
        manifest.get("status") != "PASS"
        or manifest.get("wave") != "W2"
        or terminal.get("pipeline_reconstructed") is not True
        or terminal.get("terminal_outcome") != "BLOCKED_NON_PRODUCT"
        or terminal.get("production_authority_granted") is not False
        or terminal.get("publication_allowed") is not False
        or not isinstance(post_runtime, dict)
        or post_runtime.get("apps_eval_verdict") != "fail"
        or post_runtime.get("l6_binding_closure_status") != "FAIL"
        or post_runtime.get("human_labels_present") is not False
        or causes.get("model_identity", {}).get("affected_lanes") != 11
    ):
        raise ValueError("W2 canonical RCA does not support the required non-product decision")

    decision: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W3",
        "status": "PASS",
        "scope": "SINGLE_RUN_RCA_ACCEPTANCE_SEMANTICS",
        "source_run_id": manifest["source_run_id"],
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "canonical_rca": _binding(manifest_path, manifest_bytes),
        "evidence_acceptance": {
            "status": "PIPELINE_RECONSTRUCTED",
            "accepted_for": ["root_cause_analysis", "historical_execution_trace", "non_product_terminal_explanation"],
            "not_accepted_for": ["product_authorization", "publication", "live_model_pin_qualification", "human_calibration", "retrieval_qualification"],
        },
        "product_authority": {
            "status": "DENIED",
            "reasons": [
                "ALL_11_L2_HANDOFFS_AND_SPINES_FAILED_MODEL_IDENTITY",
                "APPS_EVAL_VERDICT_FAIL",
                "L6_BINDING_CLOSURE_FAIL",
                "LIVE_MODEL_PIN_NOT_QUALIFIED",
            ],
        },
        "human_authority": {
            "status": "NOT_MEASURED",
            "human_labels_present": False,
            "calibration_status": post_runtime["l6_calibration_status"],
        },
        "w6_contract": {
            "status": "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY",
            "executed": False,
            "allowed_actions": ["verify_single_run_evidence", "record_local_branch_acceptance"],
            "prohibited_claims": ["product_authorized", "publication_allowed", "live_model_pin_qualified", "human_calibrated"],
        },
        "next_wave_authorized": True,
    }
    decision["semantic_digest"] = _digest(decision)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / DECISION_FILENAME
    path.write_text(json.dumps(decision, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**decision, "decision_path": path.as_posix()}


__all__ = ["DECISION_FILENAME", "SCHEMA_VERSION", "emit_single_run_w3_acceptance_decision"]
