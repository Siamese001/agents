"""Synthetic resume-package proof tree shared by standalone unit tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.internal.resume_package_disposition import X3_ALLOW_CODE
from apps_rg.runtime.package.resume_package_manifest import (
    RUNTIME_PROOFS,
    ResumePackageProofPaths,
    resolve_resume_package_paths,
)
from apps_rg.runtime.shadow.l6_handoff_packet import build_l6_shadow_handoff_dict

_ART = RUNTIME_PROOFS
_CORE_X3_ALLOW = "X3D_ALLOW_FINISH"


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mk_x2(pass_all: bool) -> dict[str, object]:
    if pass_all:
        return {
            "gate_family": "test",
            "all_pass": True,
            "failed_gate_ids": [],
            "gates": [],
        }
    return {
        "gate_family": "test",
        "all_pass": False,
        "failed_gate_ids": ["x2_fake_fail"],
        "gates": [
            {
                "gate_id": "x2_fake_fail",
                "pass": False,
                "gate_type": "deterministic",
            }
        ],
    }


def _x3_stub(code: str = X3_ALLOW_CODE) -> dict[str, object]:
    return {
        "x3_code": code,
        "authorization_scope": "PLUMBING_ONLY",
        "proceed_to_runtime": False,
        "pass": code == X3_ALLOW_CODE,
        "decisive_reason": "",
        "review_reason": None if code == X3_ALLOW_CODE else "review",
    }


def _emit_lane_dir(repo_root: Path, lane_key: str) -> dict[str, str]:
    lane_dir = repo_root / _ART / f"synth_lane_{lane_key}"
    lane_dir.mkdir(parents=True, exist_ok=True)
    (lane_dir / "provider_request.json").write_text(
        json.dumps(
            {
                "provider_requested": "retired_provider_profile",
                "provider_attempted": True,
                "model": "Synthetic/RetiredProviderStub",
                "temperature": 0.4,
                "max_tokens": 1200,
                "prompt_hash": "a" * 16,
            }
        ),
        encoding="utf-8",
    )
    run_id = f"synthetic_{lane_key}"
    l2: dict[str, object] = {
        "run_id": run_id,
        "section_id": lane_key,
        "runtime_generation_status": "REAL_LLM",
        "product_quality_status": "PASS",
        "product_quality_reason": "synthetic_fixture",
        "prompt_id": f"synthetic_prompt_{lane_key}",
        "prompt_hash": "b" * 16,
    }
    if lane_key == "unify_bullets":
        bullet_ids = [f"bul_unify_{index:03d}" for index in range(1, 7)]
        l2["bullets"] = [
            {
                "bullet_id": bullet_id,
                "bullet_text": f"text for {bullet_id}",
                "has_metric": bullet_id == "bul_unify_006",
                "metric_raw": "metric" if bullet_id == "bul_unify_006" else "",
                "source_fact_ids": [bullet_id],
            }
            for bullet_id in bullet_ids
        ]
    elif lane_key == "ibm_bullets":
        l2["bullets"] = [
            {
                "bullet_id": bullet_id,
                "bullet_text": f"ibm {bullet_id}",
                "has_metric": False,
                "metric_raw": "",
                "source_fact_ids": [bullet_id],
            }
            for bullet_id in (
                "bul_ibm_001",
                "bul_ibm_002",
                "bul_ibm_003",
                "bul_ibm_004",
                "bul_ibm_005",
            )
        ]

    (lane_dir / "l2_output.json").write_text(json.dumps(l2), encoding="utf-8")
    (lane_dir / "x1d_llm_judge_outputs.json").write_text(
        json.dumps({"judges": []}), encoding="utf-8"
    )
    (lane_dir / "x2_gate_outputs.json").write_text(
        json.dumps(_mk_x2(True)), encoding="utf-8"
    )
    (lane_dir / "x3_disposition.json").write_text(
        json.dumps(
            {
                **_x3_stub(),
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "core_exit_authority_ref": "x3_disposition_receipt.json",
            }
        ),
        encoding="utf-8",
    )
    exhaust = {
        "schema_version": "section_runtime_exhaust_bundle_v1",
        "section_id": lane_key,
        "run_id": run_id,
        "x3_code": X3_ALLOW_CODE,
        "current_run_closed": True,
        "created_after_exit": True,
    }
    (lane_dir / "runtime_exhaust_bundle.json").write_text(
        json.dumps(exhaust), encoding="utf-8"
    )
    (lane_dir / "exit_disposition_receipt.json").write_text(
        json.dumps(
            {
                "x3_code": X3_ALLOW_CODE,
                "run_id": run_id,
                "section_x3_authoritative": False,
                "section_x3_mirror_only": True,
                "spine_x3_claimed": False,
                "canonical_exit_claimed": False,
            }
        ),
        encoding="utf-8",
    )
    core_payload = {"x3_disposition": _CORE_X3_ALLOW, "disposition": "X3D"}
    (lane_dir / "x3_disposition_receipt.json").write_text(
        json.dumps(
            {
                "producer_component": (
                    "apps_rg.runtime.entrypoints."
                    "integrated_single_action_spine_run"
                ),
                "artifact_hash": _digest(core_payload),
                "payload": core_payload,
            }
        ),
        encoding="utf-8",
    )
    core_authority = {
        "schema_version": "apps_rg.core_runtime_authority.v1",
        "source_artifact_bindings": [
            {
                "artifact_ref": "x3_disposition_receipt.json",
                "present": True,
                "hash_matches": True,
            }
        ],
        "normalized_contract": {
            "valid": True,
            "x3": {"x3_disposition": _CORE_X3_ALLOW},
            "spine_proof": {"success": True},
        },
        "status": "PASS",
        "outcome_authorized": True,
    }
    core_authority["deterministic_digest"] = _digest(core_authority)
    (lane_dir / "apps_rg_core_runtime_authority.json").write_text(
        json.dumps(core_authority),
        encoding="utf-8",
    )
    (lane_dir / "l6_shadow_handoff_receipt.json").write_text(
        json.dumps({"section_id": lane_key, "run_id": run_id, "handoff_sealed": True}),
        encoding="utf-8",
    )

    l6 = build_l6_shadow_handoff_dict(
        artifact_dir=lane_dir,
        repo_root=repo_root,
        section_id=lane_key,
        prompt_id=str(l2["prompt_id"]),
        temperature=0.4,
        max_tokens=1200,
    )
    (lane_dir / "l6_shadow_eval_package.json").write_text(
        json.dumps(l6), encoding="utf-8"
    )

    return {
        "l2_output.json": f"{_ART}/synth_lane_{lane_key}/l2_output.json",
        "x1d_llm_judge_outputs.json": (
            f"{_ART}/synth_lane_{lane_key}/x1d_llm_judge_outputs.json"
        ),
        "x2_gate_outputs.json": f"{_ART}/synth_lane_{lane_key}/x2_gate_outputs.json",
        "x3_disposition.json": f"{_ART}/synth_lane_{lane_key}/x3_disposition.json",
        "exit_disposition_receipt.json": (
            f"{_ART}/synth_lane_{lane_key}/exit_disposition_receipt.json"
        ),
        "x3_disposition_receipt.json": (
            f"{_ART}/synth_lane_{lane_key}/x3_disposition_receipt.json"
        ),
        "apps_rg_core_runtime_authority.json": (
            f"{_ART}/synth_lane_{lane_key}/apps_rg_core_runtime_authority.json"
        ),
        "l6_shadow_eval_package.json": (
            f"{_ART}/synth_lane_{lane_key}/l6_shadow_eval_package.json"
        ),
    }


def _write_minimal_fixture_tree(repo_root: Path) -> ResumePackageProofPaths:
    """Build a coherent fake proof tree with all generated lanes allowed."""
    lanes: dict[str, object] = {}
    for lane_key in GENERATED_LANES:
        refs = _emit_lane_dir(repo_root, lane_key)
        lanes[lane_key] = {
            "runtime_generation_status": "REAL_LLM",
            "x2_failed": 0,
            "x3_code": _CORE_X3_ALLOW,
            "artifact_refs": refs,
        }

    rollup_dir = repo_root / _ART / "generated_lane_rollup"
    rollup_dir.mkdir(parents=True, exist_ok=True)
    (rollup_dir / "generated_lane_rollup.json").write_text(
        json.dumps({"rollup_id": "synthetic_rollup", "lanes": lanes}),
        encoding="utf-8",
    )

    locked_dir = repo_root / _ART / "locked_copy"
    locked_dir.mkdir(parents=True, exist_ok=True)
    (locked_dir / "locked_copy_manifest.json").write_text("{}", encoding="utf-8")
    (locked_dir / "locked_copy_x2_gate_outputs.json").write_text(
        json.dumps(_mk_x2(True)), encoding="utf-8"
    )

    assembly_dir = repo_root / _ART / "final_resume_assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    (assembly_dir / "final_resume.json").write_text("{}", encoding="utf-8")
    (assembly_dir / "final_resume_manifest.json").write_text(
        json.dumps(
            {
                "calls": {
                    "provider_calls_made": False,
                    "PROVIDER_MODEL_calls_made": False,
                    "retired_provider_calls_made": False,
                    "judge_calls_made": False,
                },
                "rollup_id_source": "synthetic",
            }
        ),
        encoding="utf-8",
    )
    (assembly_dir / "final_resume_x2_gate_outputs.json").write_text(
        json.dumps(_mk_x2(True)), encoding="utf-8"
    )

    manifest_dir = repo_root / _ART / "docx_manifest"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "docx_manifest.json").write_text(
        json.dumps(
            {
                "guarantees": {
                    "provider_calls_made": False,
                    "PROVIDER_MODEL_calls_made": False,
                    "retired_provider_calls_made": False,
                    "judge_calls_made": False,
                }
            }
        ),
        encoding="utf-8",
    )
    (manifest_dir / "docx_manifest_x2_gate_outputs.json").write_text(
        json.dumps(_mk_x2(True)), encoding="utf-8"
    )

    docx_dir = repo_root / _ART / "docx"
    docx_dir.mkdir(parents=True, exist_ok=True)
    docx_rel = f"{_ART}/docx/out.docx"
    (docx_dir / "out.docx").write_bytes(b"fake docx")
    (docx_dir / "docx_render_manifest.json").write_text(
        json.dumps(
            {
                "output_docx": docx_rel,
                "verification": {
                    key: False
                    for key in (
                        "provider_calls_made",
                        "PROVIDER_MODEL_calls_made",
                        "retired_provider_calls_made",
                        "judge_calls_made",
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    (docx_dir / "docx_render_x2_gate_outputs.json").write_text(
        json.dumps(_mk_x2(True)), encoding="utf-8"
    )

    return resolve_resume_package_paths(
        repo_root=repo_root,
        output_rel=f"{_ART}/resume_package",
    )
