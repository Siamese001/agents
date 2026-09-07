"""Apps RG exit-to-observability bundle contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import uuid


@dataclass(frozen=True, slots=True)
class RuntimeExhaustBundle:
    bundle_id: str = ""
    request_id: str = ""
    run_id: str = ""
    trace_root: str = ""
    route_contract_ref: str = ""
    sealed_result_ref: str = ""
    gate_mesh_result_ref: str = ""
    exit_disposition_ref: str = ""
    runtime_receipt_refs: tuple[str, ...] = field(default_factory=tuple)
    l5_certification_packet_ref: str = ""
    l5_certification_packet_digest: str = ""
    l5_certification_status: str = ""
    learning_profile_ref: str = ""
    meta_feedback_profile_ref: str = ""
    learning_signals: tuple[str, ...] = field(default_factory=tuple)
    created_after_exit: bool = False
    current_run_closed: bool = False
    created_at: str = ""
    deterministic_digest: str = ""
    schema_version: str = "apps_rg_exhaust.v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "trace_root": self.trace_root,
            "route_contract_ref": self.route_contract_ref,
            "sealed_result_ref": self.sealed_result_ref,
            "gate_mesh_result_ref": self.gate_mesh_result_ref,
            "exit_disposition_ref": self.exit_disposition_ref,
            "runtime_receipt_refs": list(self.runtime_receipt_refs),
            "l5_certification_packet_ref": self.l5_certification_packet_ref,
            "l5_certification_packet_digest": self.l5_certification_packet_digest,
            "l5_certification_status": self.l5_certification_status,
            "learning_profile_ref": self.learning_profile_ref,
            "meta_feedback_profile_ref": self.meta_feedback_profile_ref,
            "learning_signals": list(self.learning_signals),
            "created_after_exit": self.created_after_exit,
            "current_run_closed": self.current_run_closed,
            "created_at": self.created_at,
            "deterministic_digest": self.deterministic_digest,
            "schema_version": self.schema_version,
        }


def build_runtime_exhaust_bundle(
    *,
    request_id: str,
    run_id: str,
    trace_root: str,
    exit_disposition_ref: str,
    route_contract_ref: str = "",
    sealed_result_ref: str = "",
    gate_mesh_result_ref: str = "",
    runtime_receipt_refs: tuple[str, ...] = (),
    l5_certification_packet_ref: str = "",
    l5_certification_packet_digest: str = "",
    l5_certification_status: str = "",
    learning_profile_ref: str = "",
    meta_feedback_profile_ref: str = "",
    learning_signals: tuple[str, ...] = (),
) -> RuntimeExhaustBundle:
    if not exit_disposition_ref:
        raise ValueError("build_runtime_exhaust_bundle: exit_disposition_ref is required")
    created_at = datetime.now(timezone.utc).isoformat()
    bundle_id = f"reb::{run_id}::{uuid.uuid4().hex[:8]}"
    digest_body = {
        "bundle_id": bundle_id,
        "request_id": request_id,
        "run_id": run_id,
        "trace_root": trace_root,
        "route_contract_ref": route_contract_ref,
        "sealed_result_ref": sealed_result_ref,
        "gate_mesh_result_ref": gate_mesh_result_ref,
        "exit_disposition_ref": exit_disposition_ref,
        "l5_certification_packet_ref": l5_certification_packet_ref,
        "l5_certification_packet_digest": l5_certification_packet_digest,
        "l5_certification_status": l5_certification_status,
        "created_after_exit": True,
        "current_run_closed": True,
        "created_at": created_at,
    }
    digest = sha256(json.dumps(digest_body, sort_keys=True).encode("utf-8")).hexdigest()
    return RuntimeExhaustBundle(
        bundle_id=bundle_id,
        request_id=request_id,
        run_id=run_id,
        trace_root=trace_root,
        route_contract_ref=route_contract_ref,
        sealed_result_ref=sealed_result_ref,
        gate_mesh_result_ref=gate_mesh_result_ref,
        exit_disposition_ref=exit_disposition_ref,
        runtime_receipt_refs=runtime_receipt_refs,
        l5_certification_packet_ref=l5_certification_packet_ref,
        l5_certification_packet_digest=l5_certification_packet_digest,
        l5_certification_status=l5_certification_status,
        learning_profile_ref=learning_profile_ref,
        meta_feedback_profile_ref=meta_feedback_profile_ref,
        learning_signals=learning_signals,
        created_after_exit=True,
        current_run_closed=True,
        created_at=created_at,
        deterministic_digest=digest,
    )


__all__ = ["RuntimeExhaustBundle", "build_runtime_exhaust_bundle"]
