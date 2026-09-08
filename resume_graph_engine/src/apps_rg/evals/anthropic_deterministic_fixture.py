"""Deterministic, no-provider evidence for the Anthropic Partnership fixture.

This module is intentionally *not* a product execution path.  It produces the
small, byte-bound handoff and L2-boundary artifacts used by the isolated test
fixture.  The consumer validator accepts the handoff only while the explicit
``APPS_RG_TEST_HARNESS`` guard is active.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


FIXTURE_HANDOFF_FILENAME = "apps_rg_anthropic_deterministic_fixture_handoff.v1.json"
FIXTURE_HANDOFF_SCHEMA_VERSION = "apps_rg.anthropic_deterministic_fixture_handoff.v1"
FIXTURE_EVAL_PROFILE_ID = "apps_rg.anthropic_deterministic_fixture.v1"
FIXTURE_EVIDENCE_CLASS = "TEST_FIXTURE_ONLY"
FIXTURE_HMAC_SECRET_ENV = "APPS_RG_DETERMINISTIC_FIXTURE_HMAC_SECRET"
TEST_HARNESS_ENV = "APPS_RG_TEST_HARNESS"
FIXTURE_RUN_RECEIPT_FILENAME = "deterministic_fixture_run_receipt.json"
FIXTURE_L2_OUTPUT_FILENAME = "deterministic_l2_fixture.json"

_IDENTITY_KEYS = (
    "producer_app_id",
    "consumer_app_id",
    "parent_run_id",
    "child_run_id",
    "request_id",
    "trace_root",
    "tenant_id",
    "target_company",
    "target_role",
    "jd_sha256",
    "brief_sha256",
    "policy_hash",
    "blueprint_hash",
    "schema_version",
)


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize fixture evidence deterministically for hashing/signing."""

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def fixture_signature(secret: str, payload: Mapping[str, Any]) -> str:
    """Return the test-fixture HMAC for a manifest body without its signature."""

    return "hmac-sha256:" + hmac.new(
        secret.encode("utf-8"),
        canonical_json_bytes(dict(payload)),
        hashlib.sha256,
    ).hexdigest()


def _normalized_input_bytes(jd_ref: str) -> bytes:
    source = Path(str(jd_ref or "").strip())
    raw = source.read_text(encoding="utf-8") if source.is_file() else str(jd_ref or "")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    return (normalized + "\n").encode("utf-8")


def _file_digest(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "artifact_ref": path.name,
        "sha256": sha256_bytes(raw),
        "byte_length": len(raw),
    }


def _identity(
    *,
    parent_run_id: str,
    child_run_id: str,
    request_id: str,
    trace_root: str,
    tenant_id: str,
    target_company: str,
    target_role: str,
    jd_sha256: str,
    brief_sha256: str,
    policy_hash: str,
    blueprint_hash: str,
) -> dict[str, str]:
    return {
        "producer_app_id": "apps_rg.deterministic_test_fixture",
        "consumer_app_id": "apps_rg",
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "request_id": request_id,
        "trace_root": trace_root,
        "tenant_id": tenant_id,
        "target_company": target_company,
        "target_role": target_role,
        "jd_sha256": jd_sha256,
        "brief_sha256": brief_sha256,
        "policy_hash": policy_hash,
        "blueprint_hash": blueprint_hash,
        "schema_version": "apps_rg.deterministic_fixture_run_identity.v1",
    }


def produce_anthropic_deterministic_handoff(
    *,
    artifact_dir: Path,
    jd_ref: str,
    parent_run_id: str,
    child_run_id: str,
    request_id: str,
    trace_root: str,
    tenant_id: str,
    target_company: str,
    target_role: str,
    policy_hash: str,
    blueprint_hash: str,
    secret: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Write a run-scoped, explicitly no-provider fixture handoff.

    ``secret`` is deliberately caller supplied and must only be present in the
    test process.  The manifest contains no API credential and cannot be
    accepted by a normal product process.
    """

    if not str(secret or "").strip():
        raise ValueError("fixture handoff requires a non-empty test HMAC secret")
    root = Path(artifact_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    normalized_jd = _normalized_input_bytes(jd_ref)
    normalized_jd_path = root / "job_description.normalized.txt"
    normalized_jd_path.write_bytes(normalized_jd)
    briefing_text = (
        "# Anthropic Partnership deterministic fixture\n\n"
        "This is TEST_FIXTURE_ONLY evidence for Manager of Applied AI "
        "Architecture, Partnerships. It records no provider or network calls.\n"
    )
    briefing_path = root / "briefing.md"
    briefing_path.write_text(briefing_text, encoding="utf-8", newline="\n")
    jd_sha256 = sha256_bytes(normalized_jd)
    brief_sha256 = sha256_bytes(briefing_path.read_bytes())
    identity = _identity(
        parent_run_id=parent_run_id,
        child_run_id=child_run_id,
        request_id=request_id,
        trace_root=trace_root,
        tenant_id=tenant_id,
        target_company=target_company,
        target_role=target_role,
        jd_sha256=jd_sha256,
        brief_sha256=brief_sha256,
        policy_hash=policy_hash,
        blueprint_hash=blueprint_hash,
    )
    if tuple(identity) != _IDENTITY_KEYS:
        raise AssertionError("fixture identity schema drifted")
    manifest_body: dict[str, Any] = {
        "schema_version": FIXTURE_HANDOFF_SCHEMA_VERSION,
        "fixture_policy_id": FIXTURE_EVAL_PROFILE_ID,
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "product_eligible": False,
        "provider_call_attempted": False,
        "network_call_attempted": False,
        "producer": {
            "producer_app_id": "apps_rg.deterministic_test_fixture",
            "test_harness_required": True,
        },
        "identity": identity,
        "artifacts": {
            "briefing": _file_digest(briefing_path),
            "normalized_jd": _file_digest(normalized_jd_path),
        },
        "created_at_utc": created_at_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    manifest = {
        **manifest_body,
        "fixture_signature": fixture_signature(secret, manifest_body),
    }
    manifest_path = root / FIXTURE_HANDOFF_FILENAME
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    return {
        "briefing_path": str(briefing_path),
        "manifest_path": str(manifest_path),
        "identity": identity,
        "manifest": manifest,
    }


def emit_deterministic_fixture_l2_artifacts(
    *,
    artifact_dir: Path,
    identity: Mapping[str, Any],
    upstream_fault: str,
) -> dict[str, str]:
    """Record the replaced L2 seam without representing it as product output."""

    root = Path(artifact_dir).resolve()
    missing = [key for key in ("parent_run_id", "child_run_id") if not str(identity.get(key) or "").strip()]
    if missing:
        raise ValueError(f"fixture L2 evidence missing identity values: {', '.join(missing)}")
    fixture_identity = {
        "parent_run_id": str(identity["parent_run_id"]),
        "child_run_id": str(identity["child_run_id"]),
        "section_attempt_id": "anthropic-fixture-attempt-001",
        "runtime_exhaust_bundle_id": "anthropic-fixture-exhaust-001",
    }
    l2_payload = {
        "schema_version": "apps_rg.deterministic_fixture_l2_boundary.v1",
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "fixture_policy_id": FIXTURE_EVAL_PROFILE_ID,
        "product_eligible": False,
        "provider_call_attempted": False,
        "network_call_attempted": False,
        "l2_external_seam_replaced": True,
        "upstream_fault": str(upstream_fault or ""),
        "identity": fixture_identity,
        "generated_resume": {
            "sections": {
                "executive_summary": "Applied AI architecture leader for partnership-facing platform strategy.",
                "experience": "Fixture evidence records orchestration only and makes no product quality claim.",
                "skills": "Applied AI architecture, partnerships, governance.",
            }
        },
    }
    l2_path = root / FIXTURE_L2_OUTPUT_FILENAME
    l2_path.write_bytes(canonical_json_bytes(l2_payload))
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / "generated_resume.json").write_bytes(
        canonical_json_bytes(l2_payload["generated_resume"])
    )
    (outputs / "resume.md").write_text(
        "# Deterministic fixture resume\n\n"
        "This file is TEST_FIXTURE_ONLY and is not a product resume.\n",
        encoding="utf-8",
        newline="\n",
    )
    receipt = {
        "schema_version": "apps_rg.deterministic_fixture_run_receipt.v1",
        "evidence_class": FIXTURE_EVIDENCE_CLASS,
        "fixture_policy_id": FIXTURE_EVAL_PROFILE_ID,
        "product_eligible": False,
        "provider_call_attempted": False,
        "network_call_attempted": False,
        "current_run_mutated": False,
        "future_run_only": True,
        "l2_external_seam_replaced": True,
        "upstream_fault": str(upstream_fault or ""),
        "identity": fixture_identity,
        "artifact_refs": {
            "fixture_handoff": FIXTURE_HANDOFF_FILENAME,
            "fixture_l2_output": FIXTURE_L2_OUTPUT_FILENAME,
            "u0_receipt": "u0_receipt.json",
            "l1_plan": "l1_plan_contract.json",
            "route_contract": "route_contract.json",
            "generated_resume": "outputs/generated_resume.json",
            "resume_markdown": "outputs/resume.md",
        },
    }
    receipt_path = root / FIXTURE_RUN_RECEIPT_FILENAME
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    return {
        "fixture_l2_output": str(l2_path),
        "fixture_run_receipt": str(receipt_path),
    }


__all__ = [
    "FIXTURE_EVAL_PROFILE_ID",
    "FIXTURE_EVIDENCE_CLASS",
    "FIXTURE_HANDOFF_FILENAME",
    "FIXTURE_HANDOFF_SCHEMA_VERSION",
    "FIXTURE_HMAC_SECRET_ENV",
    "FIXTURE_L2_OUTPUT_FILENAME",
    "FIXTURE_RUN_RECEIPT_FILENAME",
    "TEST_HARNESS_ENV",
    "canonical_json_bytes",
    "emit_deterministic_fixture_l2_artifacts",
    "fixture_signature",
    "produce_anthropic_deterministic_handoff",
    "sha256_bytes",
]
