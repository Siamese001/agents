"""Independently verify the complete zero-LLM single-run RCA chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping


VERIFICATION_FILENAME = "single_run_w4_verification.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w4.v1"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value, payload


def _semantic_valid(value: dict[str, Any]) -> bool:
    body = dict(value)
    recorded = body.pop("semantic_digest", None)
    return isinstance(recorded, str) and recorded == _digest(body)


def _binding_matches(binding: Any, path: Path, payload: bytes) -> bool:
    if not isinstance(binding, dict):
        return False
    parsed = json.loads(payload.decode("utf-8"))
    return (
        binding.get("artifact_ref") == path.name
        and binding.get("byte_length") == len(payload)
        and binding.get("sha256") == "sha256:" + hashlib.sha256(payload).hexdigest()
        and binding.get("semantic_digest") == parsed.get("semantic_digest", "")
    )


def _verify_w5_artifacts(rows: Any, evidence_root: Path) -> tuple[bool, list[str]]:
    if not isinstance(rows, list) or len(rows) != 14:
        return False, ["verified_w5_artifact_count"]
    failures: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("verified") is not True:
            failures.append("unverified_w5_artifact")
            continue
        ref = str(row.get("artifact_ref") or "")
        candidate = (evidence_root / ref).resolve()
        try:
            candidate.relative_to(evidence_root)
        except ValueError:
            failures.append(f"w5_artifact_escape:{ref}")
            continue
        if not candidate.is_file():
            failures.append(f"w5_artifact_missing:{ref}")
            continue
        payload = candidate.read_bytes()
        if row.get("byte_length") != len(payload):
            failures.append(f"w5_artifact_length:{ref}")
        if row.get("sha256") != "sha256:" + hashlib.sha256(payload).hexdigest():
            failures.append(f"w5_artifact_digest:{ref}")
    return not failures, failures


def verify_single_run_w4(
    *,
    source_run: Path,
    w0_freeze_path: Path,
    w1_packet_path: Path,
    w2_manifest_path: Path,
    w3_decision_path: Path,
    w5_evidence_root: Path,
    output_dir: Path,
    source_manifest_builder: Callable[[Path], Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify W0-W3 identity, semantics, evidence hashes, and authority boundaries."""

    source = source_run.resolve(strict=True)
    w0_path = w0_freeze_path.resolve(strict=True)
    w1_path = w1_packet_path.resolve(strict=True)
    w2_path = w2_manifest_path.resolve(strict=True)
    w3_path = w3_decision_path.resolve(strict=True)
    evidence_root = w5_evidence_root.resolve(strict=True)
    w0, w0_bytes = _read(w0_path)
    w1, w1_bytes = _read(w1_path)
    w2, w2_bytes = _read(w2_path)
    w3, _w3_bytes = _read(w3_path)
    source_manifest = dict(source_manifest_builder(source))
    source_run_id = source.name
    w5_ok, w5_failures = _verify_w5_artifacts(w1.get("verified_w5_artifacts"), evidence_root)
    checks = {
        "w0_semantic": w0.get("status") == "PASS" and w0.get("wave") == "W0" and _semantic_valid(w0),
        "w0_source_identity": w0.get("source_run_id") == source_run_id and w0.get("source_manifest_sha256") == source_manifest.get("content_sha256"),
        "w1_semantic": w1.get("status") == "PASS" and w1.get("wave") == "W1" and _semantic_valid(w1),
        "w1_binds_w0": _binding_matches(w1.get("w0_freeze"), w0_path, w0_bytes),
        "w1_counts": w1.get("extracted_counts") == {"generation_lanes": 11, "judges": 21, "contract_handoffs": 21},
        "w1_w5_artifacts": w5_ok,
        "w2_semantic": w2.get("status") == "PASS" and w2.get("wave") == "W2" and _semantic_valid(w2),
        "w2_binds_w1": _binding_matches(w2.get("w1_packet"), w1_path, w1_bytes),
        "w2_root_causes": (
            w2.get("root_causes", {}).get("model_identity", {}).get("affected_lanes") == 11
            and w2.get("root_causes", {}).get("token_accounting", {}).get("affected_lanes") == 11
            and w2.get("root_causes", {}).get("token_accounting", {}).get("recomputed_output_token_failures") == 0
        ),
        "w3_semantic": w3.get("status") == "PASS" and w3.get("wave") == "W3" and _semantic_valid(w3),
        "w3_binds_w2": _binding_matches(w3.get("canonical_rca"), w2_path, w2_bytes),
        "shared_source_identity": len({w0.get("source_run_id"), w1.get("source_run_id"), w2.get("source_run_id"), w3.get("source_run_id"), source_run_id}) == 1,
        "terminal_non_product": (
            w2.get("terminal_state", {}).get("terminal_outcome") == "BLOCKED_NON_PRODUCT"
            and w2.get("terminal_state", {}).get("production_authority_granted") is False
            and w2.get("terminal_state", {}).get("publication_allowed") is False
            and w3.get("product_authority", {}).get("status") == "DENIED"
        ),
        "w6_evidence_only": (
            w3.get("w6_contract", {}).get("status") == "AUTHORIZED_EVIDENCE_ACCEPTANCE_ONLY"
            and w3.get("w6_contract", {}).get("executed") is False
        ),
    }
    failures = [name for name, passed in checks.items() if not passed] + w5_failures
    if failures:
        raise ValueError("W4 verification failed: " + ",".join(sorted(set(failures))))
    verification: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W4",
        "status": "PASS",
        "scope": "SINGLE_RUN_RCA_DETERMINISTIC_VERIFICATION",
        "source_run_id": source_run_id,
        "source_manifest_sha256": source_manifest["content_sha256"],
        "checks": checks,
        "verified_w5_artifact_count": 14,
        "production_authority_granted": False,
        "publication_allowed": False,
        "next_wave_authorized": True,
    }
    verification["semantic_digest"] = _digest(verification)
    output_dir.mkdir(parents=True, exist_ok=True)
    verification_path = output_dir / VERIFICATION_FILENAME
    verification_path.write_text(json.dumps(verification, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**verification, "verification_path": verification_path.as_posix()}


__all__ = ["SCHEMA_VERSION", "VERIFICATION_FILENAME", "verify_single_run_w4"]
