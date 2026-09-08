"""App-owned authority adapter for the externally pinned core runtime bundle.

The standalone app cannot rewrite artifacts stamped by ``apps_rg``.  It
therefore consumes those artifacts, records source-contract drift, and emits a
separate content-bound normalization receipt that is the only core bundle view
the app may use for product authorization.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.failure_evidence import atomic_write_json


CORE_RUNTIME_AUTHORITY_ARTIFACT = "apps_rg_core_runtime_authority.json"
CORE_RUNTIME_AUTHORITY_SCHEMA = "apps_rg.core_runtime_authority.v1"

_CANONICAL_X3 = {
    "X3A_DENY_REROUTE",
    "X3B_ESCALATE_HITL",
    "X3C_COMMIT_REQUEST_TO_UWG",
    "X3D_ALLOW_FINISH",
    "X3E_SAFE_ABSTAIN",
}
_LEGACY_X3 = {
    "X3A": "X3A_DENY_REROUTE",
    "X3B": "X3B_ESCALATE_HITL",
    "X3C": "X3C_COMMIT_REQUEST_TO_UWG",
    "X3D": "X3D_ALLOW_FINISH",
    "X3E": "X3E_SAFE_ABSTAIN",
}
_SOURCE_ARTIFACTS = (
    "runtime_identity_envelope.json",
    "validated_request.json",
    "l1_plan_contract.json",
    "route_contract.json",
    "l3_bypass_receipt.json",
    "c0_bypass_receipt.json",
    "prompt_assembly_bypass_receipt.json",
    "terminal_ret_packet.json",
    "exit_review_packet.json",
    "x3_disposition_receipt.json",
    "runtime_execution_witness.json",
    "l2_sealed_artifact.json",
    "runtime_exhaust_bundle.json",
    "runtime_trace_snapshot.json",
    "apps_rg_how_trace.json",
    "integrated_runtime_artifact_manifest.json",
    "apps_rg_spine_proof.json",
)


@dataclass(frozen=True)
class CoreRuntimeAuthorityVerification:
    valid: bool
    errors: tuple[str, ...]
    receipt: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return (
        f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"
    )


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_envelope(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _payload(envelope: Mapping[str, Any]) -> dict[str, Any]:
    value = envelope.get("payload")
    return dict(value) if isinstance(value, Mapping) else {}


def canonicalize_core_x3(value: Any) -> str:
    """Map the pinned core's legacy X3 vocabulary to product-v2 codes."""

    if isinstance(value, Mapping):
        value = (
            value.get("x3_disposition")
            or value.get("x3_code")
            or value.get("disposition")
        )
    raw = str(value or "").strip()
    if raw in _CANONICAL_X3:
        return raw
    return _LEGACY_X3.get(raw, "")


def _source_binding(root: Path, filename: str) -> dict[str, Any]:
    path = root / filename
    envelope = _load_envelope(path)
    payload = _payload(envelope)
    recorded = str(envelope.get("artifact_hash") or "")
    recomputed = _digest(payload) if payload else ""
    return {
        "artifact_ref": filename,
        "present": path.is_file(),
        "producer_component": str(envelope.get("producer_component") or ""),
        "recorded_artifact_hash": recorded,
        "recomputed_artifact_hash": recomputed,
        "hash_matches": bool(recorded and recomputed and recorded == recomputed),
    }


def _how_trace_digest(payload: Mapping[str, Any]) -> str:
    body = {
        key: value for key, value in payload.items() if key != "deterministic_digest"
    }
    return _digest(body)


def _canonical_runtime_mode(
    *,
    l2_failed: bool,
    exhaust: Mapping[str, Any],
    how: Mapping[str, Any],
    spine: Mapping[str, Any],
) -> str:
    if l2_failed:
        return "fault"
    modes = [
        str(source.get("runtime_mode") or "").strip()
        for source in (exhaust, how, spine)
        if str(source.get("runtime_mode") or "").strip()
    ]
    if modes and len(set(modes)) == 1:
        return modes[0]
    if modes:
        counts = Counter(modes)
        candidate, count = counts.most_common(1)[0]
        if count > len(modes) / 2:
            return candidate
    return "unknown"


def _build_core_runtime_authority(
    artifact_dir: Path,
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Derive the authority receipt exclusively from bound source artifacts."""

    root = Path(artifact_dir).resolve()
    envelopes = {name: _load_envelope(root / name) for name in _SOURCE_ARTIFACTS}
    payloads = {name: _payload(envelope) for name, envelope in envelopes.items()}
    bindings = [_source_binding(root, name) for name in _SOURCE_ARTIFACTS]
    violations: list[dict[str, Any]] = []
    for binding in bindings:
        if not binding["present"]:
            violations.append(
                {
                    "code": "CORE_SOURCE_ARTIFACT_MISSING",
                    "artifact_ref": binding["artifact_ref"],
                }
            )
        elif not binding["hash_matches"]:
            violations.append(
                {
                    "code": "CORE_SOURCE_ARTIFACT_HASH_MISMATCH",
                    "artifact_ref": binding["artifact_ref"],
                }
            )

    witness = payloads["runtime_execution_witness.json"]
    exhaust = payloads["runtime_exhaust_bundle.json"]
    how = payloads["apps_rg_how_trace.json"]
    spine = payloads["apps_rg_spine_proof.json"]
    x3 = payloads["x3_disposition_receipt.json"]
    l2 = witness.get("l2") if isinstance(witness.get("l2"), Mapping) else {}
    l2_fault = str(l2.get("fault") or exhaust.get("l2_fault") or "")
    l2_failed = bool(
        l2_fault or str(l2.get("status") or "").upper() in {"FAIL", "FAILED", "ERROR"}
    )
    runtime_mode = _canonical_runtime_mode(
        l2_failed=l2_failed,
        exhaust=exhaust,
        how=how,
        spine=spine,
    )
    source_modes = {
        "runtime_exhaust_bundle.json": str(exhaust.get("runtime_mode") or ""),
        "apps_rg_how_trace.json": str(how.get("runtime_mode") or ""),
        "apps_rg_spine_proof.json": str(spine.get("runtime_mode") or ""),
    }
    if len({value for value in source_modes.values() if value}) > 1:
        violations.append(
            {
                "code": "CORE_RUNTIME_MODE_DIVERGENCE",
                "observed": source_modes,
            }
        )

    raw_x3 = x3.get("x3_disposition") or x3.get("disposition")
    canonical_x3 = canonicalize_core_x3(raw_x3)
    if str(x3.get("x3_disposition") or "") not in _CANONICAL_X3:
        violations.append(
            {
                "code": "CORE_X3_LEGACY_OR_MISSING_FIELD",
                "observed": str(raw_x3 or ""),
            }
        )

    source_how_digest = str(how.get("deterministic_digest") or "")
    recomputed_source_how_digest = _how_trace_digest(how) if how else ""
    if source_how_digest != recomputed_source_how_digest:
        violations.append(
            {
                "code": "CORE_HOW_TRACE_DIGEST_MISMATCH",
                "stored": source_how_digest,
                "recomputed": recomputed_source_how_digest,
            }
        )
    normalized_how_payload = dict(how)
    normalized_how_payload["runtime_mode"] = runtime_mode
    normalized_how_digest = _how_trace_digest(normalized_how_payload)

    if l2_failed and bool(spine.get("success")):
        violations.append(
            {
                "code": "CORE_SPINE_SUCCESS_CONTRADICTS_L2_FAILURE",
                "l2_fault": l2_fault,
            }
        )

    hash_to_artifact = {
        str(binding["recorded_artifact_hash"]): str(binding["artifact_ref"])
        for binding in bindings
        if binding["hash_matches"]
    }
    ref_fields = (
        "runtime_identity_ref",
        "runtime_intake_ref",
        "runtime_l1_plan_ref",
        "runtime_route_contract_ref",
        "runtime_l3_bypass_ref",
        "runtime_c0_receipt_ref",
        "runtime_prompt_assembly_ref",
        "runtime_l2_artifact_ref",
        "runtime_exit_disposition_ref",
        "runtime_exhaust_ref",
        "otel_or_runtime_trace_ref",
        "artifact_manifest_ref",
        "how_trace_ref",
    )
    resolved_refs: dict[str, dict[str, Any]] = {}
    for field in ref_fields:
        value = str(spine.get(field) or "")
        if not value:
            continue
        target = hash_to_artifact.get(value, "")
        resolved_refs[field] = {
            "artifact_hash": value,
            "artifact_ref": target,
            "resolved": bool(target),
        }
        if not target:
            violations.append(
                {
                    "code": "CORE_SPINE_REF_UNRESOLVED",
                    "field": field,
                    "artifact_hash": value,
                }
            )
    l2_ref = resolved_refs.get("runtime_l2_artifact_ref") or {}
    if l2_ref.get("artifact_ref") == "terminal_ret_packet.json":
        l2_ref["evidence_role"] = (
            "failed_l2_terminal_evidence" if l2_failed else "terminal_l2_evidence"
        )
        violations.append(
            {
                "code": "CORE_SPINE_L2_REF_VERIFIER_TARGET_DRIFT",
                "artifact_ref": "terminal_ret_packet.json",
            }
        )

    blocking_gaps = [str(value) for value in spine.get("blocking_gaps", [])]
    if l2_failed:
        blocking_gaps.append(f"L2_EXECUTION_FAILED:{l2_fault}")
    blocking_gaps = list(dict.fromkeys(value for value in blocking_gaps if value))
    normalized_spine_success = bool(
        not l2_failed
        and spine.get("success") is True
        and _int_or(spine.get("exit_code"), 1) == 0
        and not blocking_gaps
    )
    normalized_spine = {
        "runtime_mode": runtime_mode,
        "success": normalized_spine_success,
        "exit_code": 0 if normalized_spine_success else 1,
        "apps_rg_spine_status": (
            "R4_SINGLE_ACTION_PROVEN"
            if normalized_spine_success
            else "R4_SINGLE_ACTION_BLOCKED"
        ),
        "blocking_gaps": blocking_gaps,
        "resolved_refs": resolved_refs,
    }
    normalized_modes = {
        "runtime_exhaust": runtime_mode,
        "how_trace": runtime_mode,
        "spine_proof": runtime_mode,
    }
    normalized_errors: list[str] = []
    if runtime_mode == "unknown" or len(set(normalized_modes.values())) != 1:
        normalized_errors.append("NORMALIZED_RUNTIME_MODE_INVALID")
    if canonical_x3 not in _CANONICAL_X3:
        normalized_errors.append("NORMALIZED_X3_INVALID")
    if any(not binding["hash_matches"] for binding in bindings):
        normalized_errors.append("SOURCE_ARTIFACT_BINDING_INVALID")
    if any(not row["resolved"] for row in resolved_refs.values()):
        normalized_errors.append("NORMALIZED_SPINE_REF_UNRESOLVED")
    # Normalization may explain legacy drift, but it may not turn a
    # contradictory source bundle into a valid governed contract.  A producer
    # contradiction is itself terminal verifier evidence.
    normalized_errors.extend(
        f"SOURCE_CONTRACT_VIOLATION:{row.get('code')}"
        for row in violations
        if str(row.get("code") or "")
    )
    normalized_errors = list(dict.fromkeys(normalized_errors))
    normalized_contract_valid = not normalized_errors
    outcome_authorized = bool(
        normalized_contract_valid
        and normalized_spine_success
        and canonical_x3 == "X3D_ALLOW_FINISH"
    )
    receipt: dict[str, Any] = {
        "schema_version": CORE_RUNTIME_AUTHORITY_SCHEMA,
        "generated_at_utc": generated_at_utc,
        "producer_component": "apps_rg.runtime.orchestration.core_runtime_authority",
        "source_runtime_subject": "apps_rg",
        "source_artifact_bindings": bindings,
        "source_contract_violations": violations,
        "normalized_contract": {
            "valid": normalized_contract_valid,
            "errors": normalized_errors,
            "runtime_modes": normalized_modes,
            "how_trace": {
                "source_ref": "apps_rg_how_trace.json",
                "source_stored_digest": source_how_digest,
                "source_recomputed_digest": recomputed_source_how_digest,
                "deterministic_digest": normalized_how_digest,
            },
            "x3": {
                "source_ref": "x3_disposition_receipt.json",
                "legacy_disposition": str(raw_x3 or ""),
                "x3_disposition": canonical_x3,
            },
            "spine_proof": normalized_spine,
        },
        "status": "PASS" if outcome_authorized else "BLOCKED",
        "outcome_authorized": outcome_authorized,
    }
    receipt["deterministic_digest"] = _digest(receipt)
    return receipt


def emit_core_runtime_authority(artifact_dir: Path) -> dict[str, Any]:
    """Normalize the core bundle without overwriting core-owned evidence."""

    root = Path(artifact_dir).resolve()
    receipt = _build_core_runtime_authority(
        root,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    atomic_write_json(root / CORE_RUNTIME_AUTHORITY_ARTIFACT, receipt)
    return receipt


def verify_core_runtime_authority(
    artifact_dir: Path,
) -> CoreRuntimeAuthorityVerification:
    """Verify the app-owned normalization receipt and every source binding."""

    root = Path(artifact_dir).resolve()
    receipt = _load_envelope(root / CORE_RUNTIME_AUTHORITY_ARTIFACT)
    errors: list[str] = []
    if receipt.get("schema_version") != CORE_RUNTIME_AUTHORITY_SCHEMA:
        errors.append("CORE_RUNTIME_AUTHORITY_SCHEMA_INVALID")
    stored = str(receipt.get("deterministic_digest") or "")
    body = dict(receipt)
    body.pop("deterministic_digest", None)
    if stored != _digest(body):
        errors.append("CORE_RUNTIME_AUTHORITY_DIGEST_MISMATCH")
    expected = _build_core_runtime_authority(
        root,
        generated_at_utc=str(receipt.get("generated_at_utc") or ""),
    )
    if receipt != expected:
        errors.append("CORE_RUNTIME_AUTHORITY_DERIVATION_MISMATCH")
    for binding in receipt.get("source_artifact_bindings", []):
        if not isinstance(binding, Mapping):
            errors.append("CORE_RUNTIME_SOURCE_BINDING_INVALID")
            continue
        current = _source_binding(root, str(binding.get("artifact_ref") or ""))
        if current != dict(binding):
            errors.append(
                f"CORE_RUNTIME_SOURCE_BINDING_CHANGED:{binding.get('artifact_ref')}"
            )
    normalized = receipt.get("normalized_contract")
    if not isinstance(normalized, Mapping) or normalized.get("valid") is not True:
        errors.append("CORE_RUNTIME_NORMALIZED_CONTRACT_INVALID")
    else:
        modes = normalized.get("runtime_modes")
        if not isinstance(modes, Mapping) or len(set(modes.values())) != 1:
            errors.append("CORE_RUNTIME_NORMALIZED_MODE_DIVERGENCE")
        x3 = normalized.get("x3")
        code = x3.get("x3_disposition") if isinstance(x3, Mapping) else ""
        if code not in _CANONICAL_X3:
            errors.append("CORE_RUNTIME_NORMALIZED_X3_INVALID")
        proof = normalized.get("spine_proof")
        if not isinstance(proof, Mapping):
            errors.append("CORE_RUNTIME_NORMALIZED_SPINE_INVALID")
        elif bool(proof.get("success")) != (
            _int_or(proof.get("exit_code"), 1) == 0
            and not list(proof.get("blocking_gaps") or [])
        ):
            errors.append("CORE_RUNTIME_NORMALIZED_SPINE_SEMANTICS_INVALID")
    authorized = receipt.get("outcome_authorized") is True
    if authorized:
        normalized = receipt.get("normalized_contract") or {}
        x3 = normalized.get("x3") if isinstance(normalized, Mapping) else {}
        proof = normalized.get("spine_proof") if isinstance(normalized, Mapping) else {}
        if not (
            isinstance(x3, Mapping)
            and x3.get("x3_disposition") == "X3D_ALLOW_FINISH"
            and isinstance(proof, Mapping)
            and proof.get("success") is True
        ):
            errors.append("CORE_RUNTIME_AUTHORIZATION_SEMANTICS_INVALID")
    return CoreRuntimeAuthorityVerification(not errors, tuple(errors), receipt)


__all__ = [
    "CORE_RUNTIME_AUTHORITY_ARTIFACT",
    "CORE_RUNTIME_AUTHORITY_SCHEMA",
    "CoreRuntimeAuthorityVerification",
    "canonicalize_core_x3",
    "emit_core_runtime_authority",
    "verify_core_runtime_authority",
]
