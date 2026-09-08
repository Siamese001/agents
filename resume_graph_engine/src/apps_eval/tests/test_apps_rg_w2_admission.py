from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path

from apps_eval.adapters.apps_rg import normalize_existing_apps_rg_run_snapshot
from apps_eval.runner.core import (
    run_current_snapshot_eval,
    verify_apps_rg_eval_package_seal,
)
from apps_eval.tests._apps_rg_evidence import emit_verified_current_run_evidence


_TEST_SECRET = "apps-eval-test-route-secret-32-bytes-minimum"
_TEST_KEY_ID = "apps-eval-test-key"


def _emit_product_run(root: Path, monkeypatch) -> None:
    outputs = root / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "generated_resume.json").write_text(
        json.dumps(
            {
                "sections": {
                    "executive_summary": "Strategic technology leader " * 8,
                    "experience": "Led enterprise modernization " * 12,
                    "skills": "AI architecture partnerships delivery",
                }
            }
        ),
        encoding="utf-8",
    )
    (outputs / "resume.md").write_text(
        "# Resume\n\nVerified output\n",
        encoding="utf-8",
    )
    emit_verified_current_run_evidence(root, monkeypatch)


def _write_keyring(path: Path, key: bytes) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "apps_rg.route_hmac_verifier_keyring.v1",
                "keys": {
                    _TEST_KEY_ID: {
                        "algorithm": "HMAC-SHA256",
                        "status": "ACTIVE",
                        "key_b64": base64.b64encode(key).decode("ascii"),
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_stable_verifier_keyring_replays_without_ephemeral_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "product_run"
    _emit_product_run(root, monkeypatch)
    keyring = tmp_path / "verifier-keyring.json"
    _write_keyring(keyring, _TEST_SECRET.encode("utf-8"))
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_SECRET")
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_VERIFIER_KEYRING", str(keyring))

    snapshot = normalize_existing_apps_rg_run_snapshot(
        scenario_id="stable-verifier",
        result={},
        artifact_dir=root,
    )

    assert snapshot.provenance["preflight_verified"] is True
    assert snapshot.provenance["preflight_verification_status"] == "VERIFIED"
    assert (
        snapshot.provenance["preflight_verifier_key_source"]
        == "STABLE_VERIFIER_KEYRING"
    )
    assert snapshot.provenance["preflight_verifier_key_id"] == _TEST_KEY_ID
    assert snapshot.provenance["preflight_verifier_material_sha256"].startswith(
        "sha256:"
    )


def test_missing_historical_key_is_unverifiable_not_forged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "product_run"
    _emit_product_run(root, monkeypatch)
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_SECRET")
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_VERIFIER_KEYRING", raising=False)

    snapshot = normalize_existing_apps_rg_run_snapshot(
        scenario_id="missing-key",
        result={},
        artifact_dir=root,
    )

    errors = snapshot.provenance["preflight_verification_errors"]
    assert snapshot.provenance["preflight_verified"] is False
    assert (
        snapshot.provenance["preflight_verification_status"]
        == "UNVERIFIABLE_KEY_MATERIAL"
    )
    assert "preflight_verifier_key_material_missing" in errors
    assert "preflight_continuation_signature_invalid" not in errors
    assert "preflight_consumption_signature_invalid" not in errors


def test_invalid_signature_completes_as_sealed_fail_not_exception(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "product_run"
    _emit_product_run(root, monkeypatch)
    keyring = tmp_path / "wrong-verifier-keyring.json"
    _write_keyring(keyring, b"wrong-verifier-material-is-at-least-32-bytes")
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_SECRET")
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_VERIFIER_KEYRING", str(keyring))
    snapshot = normalize_existing_apps_rg_run_snapshot(
        scenario_id="invalid-signature",
        result={},
        artifact_dir=root,
    )

    record = run_current_snapshot_eval(
        snapshot,
        out_dir=str(tmp_path / "eval-invalid-signature"),
        emit_l6_shadow_bridge=False,
        git_commit_override="",
        platform_override="test-zero-provider",
    )

    admission_rows = [
        row
        for row in record.scorecard.scorecard_rows
        if row["component_id"] == "apps_rg.eval_admission"
    ]
    assert record.eval_execution_complete is True
    assert record.eval_verdict == "fail"
    assert record.release_blocked is True
    assert record.preflight_verification_status == "INVALID"
    assert any(
        row["failure_mode"] == "admission.preflight_signature_invalid"
        and row["verdict"] == "FAIL"
        for row in admission_rows
    )
    assert verify_apps_rg_eval_package_seal(
        Path(record.artifact_paths["eval_record"]).parent
    ) == (True, [])


def test_invalid_authority_and_missing_identity_complete_deterministically(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "product_run"
    _emit_product_run(root, monkeypatch)
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_SECRET")
    monkeypatch.delenv("APPS_RG_ROUTE_HMAC_VERIFIER_KEYRING", raising=False)
    snapshot = normalize_existing_apps_rg_run_snapshot(
        scenario_id="w2-admission",
        result={},
        artifact_dir=root,
    )
    snapshot = replace(
        snapshot,
        parent_run_id="",
        child_run_id="",
        provenance={
            **snapshot.provenance,
            "source_seal_verified": False,
            "source_seal_verification_errors": [
                "w1_authorization_superseded_invalid_authority"
            ],
            "product_authorized": False,
            "product_authorization_correction_disposition": (
                "SUPERSEDED_INVALID_AUTHORITY"
            ),
        },
    )
    out_dir = tmp_path / "eval-w2"

    first = run_current_snapshot_eval(
        snapshot,
        out_dir=str(out_dir),
        emit_l6_shadow_bridge=False,
        git_commit_override="",
        platform_override="test-zero-provider",
    )
    first_bytes = Path(first.artifact_paths["eval_record"]).read_bytes()
    second = run_current_snapshot_eval(
        snapshot,
        out_dir=str(out_dir),
        emit_l6_shadow_bridge=False,
        git_commit_override="",
        platform_override="test-zero-provider",
    )

    failure_modes = {
        row["failure_mode"]
        for row in second.scorecard.scorecard_rows
        if row["component_id"] == "apps_rg.eval_admission"
        and row["verdict"] == "FAIL"
    }
    assert first.record_id == second.record_id
    assert first_bytes == Path(second.artifact_paths["eval_record"]).read_bytes()
    assert second.eval_execution_complete is True
    assert second.eval_verdict == "fail"
    assert second.release_blocked is True
    assert second.admission_status == "FAIL"
    assert failure_modes == {
        "admission.preflight_unverifiable_key_material",
        "admission.product_authority_invalid",
        "admission.source_identity_missing",
    }
    assert Path(second.artifact_paths["l6_handoff"]).is_file()
    assert not (
        Path(second.artifact_paths["eval_record"]).parent
        / "l6_shadow_bridge.json"
    ).exists()
    assert verify_apps_rg_eval_package_seal(
        Path(second.artifact_paths["eval_record"]).parent
    ) == (True, [])
