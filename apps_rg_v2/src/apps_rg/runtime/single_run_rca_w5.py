"""Emit the final zero-LLM closeout for one verified Apps RG RCA."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CLOSEOUT_FILENAME = "single_run_w5_zero_llm_closeout.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w5.v1"
_ZERO_COUNTERS = ("provider_calls", "model_calls", "judge_calls", "embedding_calls", "network_attempts", "subprocess_attempts")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value, payload


def _binding(path: Path, payload: bytes) -> dict[str, Any]:
    parsed = json.loads(payload.decode("utf-8"))
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "semantic_digest": str(parsed.get("semantic_digest", "")),
    }


def emit_single_run_w5_zero_llm_closeout(
    *,
    w2_manifest_path: Path,
    w3_decision_path: Path,
    w4_verification_path: Path,
    w5_guard_receipt_path: Path,
    finalization_counters: dict[str, int],
    output_dir: Path,
) -> dict[str, Any]:
    """Seal a single-run RCA after all deterministic verification has passed."""

    w2_path = w2_manifest_path.resolve(strict=True)
    w3_path = w3_decision_path.resolve(strict=True)
    w4_path = w4_verification_path.resolve(strict=True)
    guard_path = w5_guard_receipt_path.resolve(strict=True)
    w2, w2_bytes = _read(w2_path)
    w3, w3_bytes = _read(w3_path)
    w4, w4_bytes = _read(w4_path)
    guard, guard_bytes = _read(guard_path)
    guard_counters = guard.get("attempt_counters")
    source_run_ids = {w2.get("source_run_id"), w3.get("source_run_id"), w4.get("source_run_id")}
    if (
        len(source_run_ids) != 1
        or None in source_run_ids
        or w2.get("status") != "PASS"
        or w3.get("status") != "PASS"
        or w4.get("status") != "PASS"
        or w4.get("next_wave_authorized") is not True
        or not isinstance(guard_counters, dict)
        or guard.get("status") != "PASS"
        or guard.get("source_unchanged") is not True
        or any(guard_counters.get(key) != 0 for key in _ZERO_COUNTERS)
        or any(finalization_counters.get(key) != 0 for key in _ZERO_COUNTERS)
        or w2.get("terminal_state", {}).get("terminal_outcome") != "BLOCKED_NON_PRODUCT"
        or w2.get("terminal_state", {}).get("production_authority_granted") is not False
        or w3.get("w6_contract", {}).get("status") != "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY"
        or w3.get("w6_contract", {}).get("executed") is not False
        or not all(w4.get("checks", {}).values())
    ):
        raise ValueError("W5 closeout prerequisites are not satisfied")
    closeout: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W5",
        "status": "PASS",
        "qualification_status": "PASS",
        "scope_complete": True,
        "source_run_id": w2["source_run_id"],
        "source_manifest_sha256": w2["source_manifest_sha256"],
        "canonical_rca": _binding(w2_path, w2_bytes),
        "acceptance_decision": _binding(w3_path, w3_bytes),
        "verification": _binding(w4_path, w4_bytes),
        "primary_zero_provider_guard": _binding(guard_path, guard_bytes),
        "zero_llm_runtime": {
            "primary_guard_counters": {key: guard_counters[key] for key in _ZERO_COUNTERS},
            "finalization_guard_counters": {key: finalization_counters[key] for key in _ZERO_COUNTERS},
            "source_unchanged": True,
        },
        "terminal_state": "BLOCKED_NON_PRODUCT",
        "production_authority_granted": False,
        "publication_allowed": False,
        "live_generation_executed": False,
        "live_model_pin_qualified": False,
        "w6_authorized": True,
        "w6_contract": "EVIDENCE_ACCEPTANCE_ONLY",
    }
    closeout["semantic_digest"] = _digest(closeout)
    output_dir.mkdir(parents=True, exist_ok=True)
    closeout_path = output_dir / CLOSEOUT_FILENAME
    closeout_path.write_text(json.dumps(closeout, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**closeout, "closeout_path": closeout_path.as_posix()}


__all__ = ["CLOSEOUT_FILENAME", "SCHEMA_VERSION", "emit_single_run_w5_zero_llm_closeout"]
