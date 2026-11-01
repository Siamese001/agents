"""Regression tests for research boundary policy persisted bundle role-identity filtering."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from apps_lic.integrations.research_boundary_policy import (
    _find_valid_persisted_artifact_bundle,
    _normalize_role,
)


def _create_test_bundle(
    run_dir: Path,
    *,
    company_name: str,
    target_role: str,
    brief_text: str = "",
    status: str = "PASS",
    is_verified: bool = True,
    is_blocked: bool = False,
    confidence: float = 0.95,
) -> None:
    """Create a verified persisted artifact bundle for role testing."""
    run_dir.mkdir(parents=True, exist_ok=True)
    if not brief_text:
        brief_text = (
            f"# Research Briefing: {company_name}\n\n"
            f"## Strategic Mandate\n- Entity: {company_name}\n- Target Role: {target_role}\n\n"
            f"## Strategic Priorities\n- Deliver engineering excellence\n- Platform scalability\n"
        )
    brief_bytes = (brief_text + "\n").encode("utf-8")
    brief_sha = "sha256:" + hashlib.sha256(brief_bytes).hexdigest()

    (run_dir / "company_brief.md").write_bytes(brief_bytes)
    (run_dir / "company_brief.json").write_text(
        json.dumps({
            "company_name": company_name,
            "company_brief_text": brief_text,
            "priorities": ["Deliver engineering excellence", "Platform scalability"],
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    u0_receipt = {
        "schema_version": "apps_research.u0_receipt.v1",
        "status": "PASS" if is_verified else "UNVERIFIED",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "authority_validation_receipt": {
            "passed": is_verified,
            "allowed": is_verified,
        },
        "reflection_receipt": {
            "legacy_authority_scan_passed": is_verified,
        },
        "raw_input_sha256": "sha256:" + "0" * 64,
        "normalized_input_sha256": "sha256:" + "0" * 64,
        "run_id": run_dir.name,
        "trace_root": f"trace-{run_dir.name}",
    }
    u0_bytes = (json.dumps(u0_receipt, indent=2) + "\n").encode("utf-8")
    (run_dir / "apps_research_u0_receipt.json").write_bytes(u0_bytes)

    commit_manifest = {
        "schema_version": "apps_research.apps_rg_bundle_commit_manifest.v1",
        "status": "COMMITTED" if is_verified else "COMMITTED_UNVERIFIED",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "u0_receipt_sha256": "sha256:" + hashlib.sha256(u0_bytes).hexdigest(),
    }
    (run_dir / "bundle_commit_manifest.json").write_text(
        json.dumps(commit_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    handoff = {
        "schema_version": "apps_research.apps_rg_handoff.v2",
        "authority_contract_id": "apps_research_rg_e2e_authority",
        "identity": {
            "company_name": company_name,
            "target_company": company_name,
            "target_role": target_role,
            "run_id": run_dir.name,
            "child_run_id": run_dir.name,
            "trace_id": f"trace-{run_dir.name}",
            "trace_root": f"trace-{run_dir.name}",
            "brief_sha256": brief_sha,
        },
        "status": status,
        "is_blocked": is_blocked,
        "confidence_score": confidence,
        "mandatory_gate_receipts": {
            gid: {"status": "PASS", "score": 1.0}
            for gid in ("G5", "G6", "G7", "G21", "G24", "G26")
        } if is_verified else {},
        "exit_authorization": {
            "x3_code": "X3D_ALLOW_FINISH" if is_verified else "X3D_BLOCKED",
        },
        "producer": {
            "producer_app_id": "apps_research",
            "attestation_sha256": "sha256:" + "0" * 64,
        },
    }
    (run_dir / "apps_research_apps_rg_handoff_v2.json").write_text(
        json.dumps(handoff, indent=2) + "\n",
        encoding="utf-8",
    )

    meta = {
        "run_id": run_dir.name,
        "request_id": f"req-{run_dir.name}",
        "trace_id": f"trace-{run_dir.name}",
        "company_name": company_name,
        "confidence_score": confidence,
        "resolution_source": "WEB_RESEARCH",
        "is_verified": is_verified,
        "is_blocked": is_blocked,
    }
    (run_dir / "run_metadata.json").write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )


def test_normalize_role():
    assert _normalize_role("SVP, Engineering") == "svp engineering"
    assert _normalize_role("Chief Marketing Officer") == "chief marketing officer"
    assert _normalize_role("VP of Software Engineering") == "vp software engineering"


def test_persisted_bundle_filters_by_matching_role(tmp_path: Path):
    """When multiple bundles exist for the same company, the matching role bundle is selected."""
    root = tmp_path / "artifacts"
    root.mkdir()

    # Create older bundle for SVP Engineering
    dir_eng = root / "run_eng"
    _create_test_bundle(dir_eng, company_name="Acme", target_role="SVP Engineering")

    # Create newer bundle for Chief Marketing Officer
    dir_cmo = root / "run_cmo"
    _create_test_bundle(dir_cmo, company_name="Acme", target_role="Chief Marketing Officer")

    # Request SVP Engineering - should match dir_eng even though dir_cmo is newer
    bundle, reason = _find_valid_persisted_artifact_bundle(
        artifact_runs_root=root,
        company_name="Acme",
        job_title="SVP Engineering",
    )
    assert bundle is not None
    assert reason == "reused_persisted_artifact"
    assert bundle.apps_research_handoff_envelope["identity"]["target_role"] == "SVP Engineering"

    # Request Chief Marketing Officer - should match dir_cmo
    bundle_cmo, reason_cmo = _find_valid_persisted_artifact_bundle(
        artifact_runs_root=root,
        company_name="Acme",
        job_title="Chief Marketing Officer",
    )
    assert bundle_cmo is not None
    assert reason_cmo == "reused_persisted_artifact"
    assert bundle_cmo.apps_research_handoff_envelope["identity"]["target_role"] == "Chief Marketing Officer"


def test_persisted_bundle_returns_none_on_role_mismatch(tmp_path: Path):
    """When only a different role bundle exists for the company, returns None cleanly."""
    root = tmp_path / "artifacts"
    root.mkdir()

    # Create bundle only for Chief Marketing Officer
    dir_cmo = root / "run_cmo"
    _create_test_bundle(dir_cmo, company_name="Acme", target_role="Chief Marketing Officer")

    # Request VP of Engineering - should return None so downstream falls back to fresh/canonical
    bundle, reason = _find_valid_persisted_artifact_bundle(
        artifact_runs_root=root,
        company_name="Acme",
        job_title="VP of Engineering",
    )
    assert bundle is None
    assert reason == "no_valid_bundle_found"
