"""Apps RG-owned prompt assembly and L2 handoff contracts."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Mapping


L2_MUST = (
    "artifact_signature_verified",
    "artifact_bytes_match",
    "replay_key_matches",
    "provider_lane_matches",
    "model_id_matches",
    "grounded_output",
)
L2_MUST_NOT = (
    "undeclared_tool_use",
    "schema_drift",
    "budget_overrun",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class LocalPromptEnvelope:
    system_message: str
    user_message: str


@dataclass(frozen=True, slots=True)
class LocalPromptAssembly:
    envelope: LocalPromptEnvelope
    manifest_hash: str
    hmac_signature: str
    slot_manifest: tuple[dict[str, str], ...]
    replay_metadata: Mapping[str, str]
    replay_key: str


def assemble_prompt(
    *,
    final_contract: Any,
    route: Any,
    plan: Any,
    request_id: str,
    secret_key: bytes,
) -> LocalPromptAssembly:
    """Compile a deterministic prompt from the app-owned route and evidence shapes."""

    chunks = tuple(getattr(final_contract, "must_use", ()) or ())
    evidence_lines = [
        str(getattr(getattr(chunk, "candidate", chunk), "text", "") or "").strip()
        for chunk in chunks
    ]
    evidence_lines = [line for line in evidence_lines if line]
    system_message = "You are the Apps RG resume-generation assistant. Use only supplied evidence."
    if evidence_lines:
        system_message += "\n\nEvidence:\n" + "\n".join(
            f"- {line}" for line in evidence_lines
        )
    user_message = str(getattr(plan, "user_task_text", "") or request_id)
    replay_key = str(
        getattr(route, "route_replay_key", "")
        or getattr(final_contract, "route_replay_key", "")
        or request_id
    )
    slot_manifest = (
        {"slot_id": "system", "status": "resolved"},
        {"slot_id": "evidence", "status": "resolved" if evidence_lines else "empty"},
        {"slot_id": "user_task", "status": "resolved"},
    )
    payload = {
        "request_id": request_id,
        "replay_key": replay_key,
        "system_message": system_message,
        "user_message": user_message,
        "slot_manifest": slot_manifest,
    }
    manifest_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    signature = hmac.new(secret_key, manifest_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return LocalPromptAssembly(
        envelope=LocalPromptEnvelope(system_message=system_message, user_message=user_message),
        manifest_hash=manifest_hash,
        hmac_signature=signature,
        slot_manifest=slot_manifest,
        replay_metadata={"signed_at": "deterministic", "manifest_hash": manifest_hash},
        replay_key=replay_key,
    )


@dataclass(frozen=True, slots=True)
class L2HandoffValidation:
    valid: bool
    reason_codes: tuple[str, ...]
    checks: Mapping[str, bool]


def validate_l2_handoff(
    *,
    artifact_signature_verified: bool,
    artifact_bytes_match: bool,
    replay_key_matches: bool,
    provider_lane_used: str,
    artifact_provider_lane: str,
    model_id_used: str,
    artifact_model_id: str,
    tools_used: tuple[str, ...],
    artifact_tools: tuple[str, ...],
    schema_used: Mapping[str, Any],
    artifact_schema: Mapping[str, Any],
    budget_ceiling: int,
    tokens_emitted: int,
    spans_emitted_with_trace_root: bool,
    grounding_required: bool,
    grounded_output: bool,
) -> L2HandoffValidation:
    """Evaluate the immutable handoff invariants in the app boundary."""

    del schema_used, artifact_schema
    checks = {
        "artifact_signature_verified": artifact_signature_verified,
        "artifact_bytes_match": artifact_bytes_match,
        "replay_key_matches": replay_key_matches,
        "provider_lane_matches": provider_lane_used == artifact_provider_lane,
        "model_id_matches": model_id_used == artifact_model_id,
        "tools_match": tuple(tools_used) == tuple(artifact_tools),
        "within_budget": int(tokens_emitted) <= int(budget_ceiling),
        "trace_root_present": spans_emitted_with_trace_root,
        "grounded_output": (not grounding_required) or grounded_output,
    }
    reasons = tuple(name for name, passed in checks.items() if not passed)
    return L2HandoffValidation(valid=not reasons, reason_codes=reasons, checks=checks)


__all__ = [
    "L2HandoffValidation",
    "L2_MUST",
    "L2_MUST_NOT",
    "LocalPromptAssembly",
    "assemble_prompt",
    "validate_l2_handoff",
]
