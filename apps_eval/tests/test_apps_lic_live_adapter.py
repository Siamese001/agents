from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from apps_eval.adapters.outreach_engine import (
    CANONICAL_STAGE_ORDER,
    OutreachEngineEvalAdapter,
    run_apps_lic_live,
    verify_sealed_outreach_run_bundle,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APPS_LIC_SPEC = importlib.util.find_spec("apps_lic")


def _write_sealed_bundle(
    bundle_dir: Path,
    *,
    execution_mode: str = "REAL_LLM",
    x3_disposition: str = "X3D_ALLOW_FINISH",
    quorum_passed: bool = True,
    x2_passed: bool = True,
    mean_score: float = 0.91,
    spread: float = 0.06,
    self_grading_blocked: bool = False,
    used_fallback: bool = False,
    provider_id: str = "anthropic",
    model_id: str = "claude-sonnet-4-6",
) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    digest_seed = "sha256:" + ("a" * 64)
    stages = [
        {
            "stage_id": st,
            "status": "PASS",
            "input_digest": digest_seed,
            "output_digest": digest_seed,
            "duration_ms": 1.0,
            "metrics": {"quorum_passed": quorum_passed, "drafter_judge_orthogonal": not self_grading_blocked},
        }
        for st in CANONICAL_STAGE_ORDER
    ]
    ledger = {
        "schema_version": "apps_lic.stage_ledger.v1",
        "run_id": "run-001",
        "mission_id": "mission-001",
        "execution_mode": execution_mode,
        "allocation_plan_digest": digest_seed,
        "candidate_graph_db_sha256": digest_seed,
        "stages": stages,
    }
    receipt = {
        "schema_version": "apps_lic.completion_receipt.v1",
        "run_id": "run-001",
        "mission_id": "mission-001",
        "completed_at": "2026-11-15T12:00:00Z",
        "x3_disposition": x3_disposition,
        "execution_mode": execution_mode,
        "quorum_passed": quorum_passed,
        "x2_passed": x2_passed,
        "pct_certificates_count": 3,
        "export_files": [
            "stage_execution_ledger.json",
            "terminal_manifest.json",
            "completion_receipt.json",
            "whole_sequence_judge_quorum.json",
            "RUN_BUNDLE_INDEX.json",
        ],
    }
    quorum = {
        "run_id": "run-001",
        "mission_id": "mission-001",
        "x2_passed": x2_passed,
        "quorum_passed": quorum_passed,
        "mean_score": mean_score,
        "spread": spread,
        "self_grading_blocked": self_grading_blocked,
        "used_fallback": used_fallback,
        "drafter_family": provider_id,
    }

    ledger_bytes = (json.dumps(ledger, indent=2, sort_keys=True) + "\n").encode("utf-8")
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    quorum_bytes = (json.dumps(quorum, indent=2, sort_keys=True) + "\n").encode("utf-8")

    (bundle_dir / "stage_execution_ledger.json").write_bytes(ledger_bytes)
    (bundle_dir / "completion_receipt.json").write_bytes(receipt_bytes)
    (bundle_dir / "whole_sequence_judge_quorum.json").write_bytes(quorum_bytes)

    artifacts = [
        {
            "artifact_id": "stage_execution_ledger",
            "artifact_ref": "stage_execution_ledger.json",
            "sha256": "sha256:" + hashlib.sha256(ledger_bytes).hexdigest(),
            "byte_length": len(ledger_bytes),
        },
        {
            "artifact_id": "completion_receipt",
            "artifact_ref": "completion_receipt.json",
            "sha256": "sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
            "byte_length": len(receipt_bytes),
        },
        {
            "artifact_id": "whole_sequence_judge_quorum",
            "artifact_ref": "whole_sequence_judge_quorum.json",
            "sha256": "sha256:" + hashlib.sha256(quorum_bytes).hexdigest(),
            "byte_length": len(quorum_bytes),
        },
    ]
    index_payload = {
        "schema_version": "apps_lic.run_bundle_index.v1",
        "run_id": "run-001",
        "mission_id": "mission-001",
        "execution_mode": execution_mode,
        "x3_disposition": x3_disposition,
        "artifacts": artifacts,
    }
    index_bytes = (json.dumps(index_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (bundle_dir / "RUN_BUNDLE_INDEX.json").write_bytes(index_bytes)
    index_sha = "sha256:" + hashlib.sha256(index_bytes).hexdigest()

    manifest = {
        "schema_version": "apps_lic.terminal_manifest.v1",
        "run_id": "run-001",
        "mission_id": "mission-001",
        "execution_mode": execution_mode,
        "x3_disposition": x3_disposition,
        "provider_id": provider_id,
        "model_id": model_id,
        "prompt_hash": digest_seed,
        "allocation_plan_digest": digest_seed,
        "artifacts": artifacts,
        "bundle_index_digest": index_sha,
    }
    (bundle_dir / "terminal_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_apps_eval_tree_has_zero_apps_lic_or_outreach_engine_imports() -> None:
    apps_eval_root = _REPO_ROOT / "apps_eval"
    offenders: list[str] = []
    for py_path in sorted(apps_eval_root.rglob("*.py")):
        if "__pycache__" in py_path.parts:
            continue
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in {"apps_lic", "outreach_engine"}:
                        offenders.append(f"{py_path.relative_to(_REPO_ROOT)}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                if top in {"apps_lic", "outreach_engine"}:
                    offenders.append(f"{py_path.relative_to(_REPO_ROOT)}:{node.lineno}:{mod}")
    assert offenders == []


def test_verify_sealed_outreach_run_bundle_passes_and_catches_tampering(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "sealed_run"
    _write_sealed_bundle(bundle_dir)

    report = verify_sealed_outreach_run_bundle(bundle_dir, require_judge_quorum_file=True)
    assert report["verified"] is True
    assert report["schema_valid"] is True
    assert report["digests_verified"] is True
    assert report["x3_disposition"] == "X3D_ALLOW_FINISH"

    adapter = OutreachEngineEvalAdapter()
    snapshot = adapter.evaluate_bundle(bundle_dir, scenario_id="sealed_case")
    assert snapshot.x3_disposition == "X3D_ALLOW_FINISH"
    assert snapshot.provenance["bundle_verified"] is True

    # Tamper with completion_receipt.json without updating RUN_BUNDLE_INDEX.json
    (bundle_dir / "completion_receipt.json").write_text('{"tampered": true}\n', encoding="utf-8")
    tampered = verify_sealed_outreach_run_bundle(bundle_dir)
    assert tampered["verified"] is False
    assert tampered["digests_verified"] is False


def test_verify_sealed_outreach_run_bundle_enforces_offline_smoke_and_quorum(tmp_path: Path) -> None:
    bad_smoke = tmp_path / "bad_smoke"
    _write_sealed_bundle(bad_smoke, execution_mode="OFFLINE_SMOKE", x3_disposition="X3D_ALLOW_FINISH")
    res_smoke = verify_sealed_outreach_run_bundle(bad_smoke)
    assert res_smoke["verified"] is False
    assert any("offline_smoke_not_isolated_to_x3e_safe_abstain" in e for e in res_smoke["errors"])

    good_smoke = tmp_path / "good_smoke"
    _write_sealed_bundle(good_smoke, execution_mode="OFFLINE_SMOKE", x3_disposition="X3E_SAFE_ABSTAIN")
    assert verify_sealed_outreach_run_bundle(good_smoke)["verified"] is True

    bad_quorum = tmp_path / "bad_quorum"
    _write_sealed_bundle(bad_quorum, mean_score=0.78, spread=0.25, quorum_passed=True)
    res_quorum = verify_sealed_outreach_run_bundle(bad_quorum)
    assert res_quorum["verified"] is False
    assert any("quorum_threshold_violation" in e for e in res_quorum["errors"])


def test_apps_lic_live_adapter_forwards_redesign_inputs(monkeypatch: Any, tmp_path: Path) -> None:
    if _APPS_LIC_SPEC is None:
        pytest.skip("apps_lic runtime source is excluded from standalone scope")

    captured: dict[str, object] = {}

    def fake_build_cli_ingress_raw(**kwargs: object) -> dict[str, object]:
        captured["build_kwargs"] = dict(kwargs)
        return {"raw": "ingress"}

    def fake_run_canonical_apps_lic_spine(raw_ingress: dict[str, object], artifact_dir: Path) -> dict[str, str]:
        captured["raw_ingress"] = dict(raw_ingress)
        captured["artifact_dir"] = artifact_dir
        return {
            "x3_code": "X3D_ALLOW_FINISH",
            "message": "ok",
            "rationale": "ok",
            "compliance_notes": "ok",
        }

    dispatch_module = importlib.import_module(".".join(("apps_lic", "runtime", "dispatch", "canonical_dispatch")))
    monkeypatch.setattr(dispatch_module, "build_cli_ingress_raw", fake_build_cli_ingress_raw)
    monkeypatch.setattr(dispatch_module, "run_canonical_apps_lic_spine", fake_run_canonical_apps_lic_spine)

    snapshot = run_apps_lic_live(
        "redesign_case",
        {
            "channel": "linkedin",
            "recipient_class": "recruiter",
            "outreach_mode": "cold",
            "manual_brief": "JD-anchored recruiter outreach",
            "lead_profile": {"name": "Jordan", "role_context": "hiring senior AI platform leaders"},
            "campaign_objective": "open a recruiter conversation",
            "connection_status": "NOT_CONNECTED",
            "premium_available": False,
            "allow_research": True,
            "audience_segment": "recruiting",
            "message_type_hint": "role_specific",
            "message_modifiers": {
                "uses_jd": True,
                "application_status_claimed": True,
                "uses_sensitive_constraints": False,
            },
            "application_status": "applied",
            "desired_next_step": "short screen",
            "governed_opportunity_facts": [
                {
                    "namespace": "apps_lic_jd_facts",
                    "fact_id": "jd_1",
                    "source_snapshot_id": "jd:example",
                    "fact_text": "Role requires senior AI platform leadership.",
                }
            ],
            "c0_required_namespaces": ["apps_lic_jd_facts"],
        },
        tmp_path / "artifacts",
    )

    build_kwargs = captured["build_kwargs"]
    assert isinstance(build_kwargs, dict)
    assert build_kwargs["recipient_class"] == "recruiter"
    assert build_kwargs["channel"] == "linkedin"
    assert build_kwargs["outreach_mode"] == "cold"
    assert build_kwargs["manual_brief"] == "JD-anchored recruiter outreach"
    assert build_kwargs["allow_research"] is True
    assert build_kwargs["connection_status"] == "NOT_CONNECTED"
    assert build_kwargs["premium_available"] is False
    assert build_kwargs["audience_segment"] == "recruiting"
    assert build_kwargs["message_type_hint"] == "role_specific"
    assert build_kwargs["application_status"] == "applied"
    assert build_kwargs["desired_next_step"] == "short screen"
    assert build_kwargs["c0_required_namespaces"] == ["apps_lic_jd_facts"]
    assert captured["raw_ingress"] == {"raw": "ingress"}
    assert captured["artifact_dir"] == tmp_path / "artifacts"
    assert snapshot.app_id == "apps_lic"
    assert snapshot.scenario_id == "redesign_case"
    assert snapshot.x3_disposition == "X3D_ALLOW_FINISH"
    assert snapshot.output["result"]["message"] == "ok"
