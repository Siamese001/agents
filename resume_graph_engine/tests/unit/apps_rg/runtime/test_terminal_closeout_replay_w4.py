"""W4 acceptance for deterministic blocked-run terminal closeout."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

from apps_rg.runtime import terminal_closeout_replay as subject


REPO_ROOT = Path(__file__).resolve().parents[4]


def _canonical(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_semantic(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["semantic_digest"] = _canonical(result)
    _write_json(path, result)
    return result


def _file_binding(path: Path, *, root: Path) -> dict[str, Any]:
    return {
        "artifact_ref": path.relative_to(root).as_posix(),
        "byte_length": path.stat().st_size,
        "sha256": _sha(path),
    }


def _counters() -> dict[str, int]:
    return {
        "blocked_import_attempts": 0,
        "embedding_calls": 0,
        "judge_calls": 0,
        "model_calls": 0,
        "network_attempts": 0,
        "provider_calls": 0,
        "subprocess_attempts": 0,
    }


def _guard(
    path: Path,
    *,
    wave: str,
    source_run_id: str,
    completion: Mapping[str, Any],
    apps_eval: bool,
    l6: bool,
    source_manifest_sha256: str,
) -> dict[str, Any]:
    return _write_semantic(
        path,
        {
            "schema_version": "apps_rg.post_runtime_zero_provider_replay.v1",
            "wave": wave,
            "status": "PASS",
            "scope_complete": True,
            "source_run_id": source_run_id,
            "source_manifest_sha256": source_manifest_sha256,
            "source_unchanged": True,
            "attempt_counters": _counters(),
            "clean_import_state": True,
            "apps_eval_executed": apps_eval,
            "l6_executed": l6,
            "uwg_operation_attempted": False,
            "operation_completion_status": "PASS",
            "operation_completion_semantic_digest": completion[
                "semantic_digest"
            ],
        },
    )


def _build_prior_chain(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source-run"
    replay = tmp_path / "replay"
    source.mkdir()
    replay.mkdir()
    source_run_id = source.name
    digest = "sha256:" + "a" * 64

    source_entries = []
    for sequence, stage_id in enumerate(subject.EXPECTED_SOURCE_STAGE_IDS):
        receipt = _write_json(
            source
            / "e2e_ledger_receipts"
            / f"{sequence:04d}_{stage_id.lower()}.json",
            {
                "schema_version": f"test.{stage_id.lower()}.v1",
                "status": "PASS",
                "stage_id": stage_id,
            },
        )
        source_entries.append(
            {
                "sequence": sequence,
                "stage_id": stage_id,
                "status": "PASS",
                "authoritative_receipt_ref": receipt.relative_to(source).as_posix(),
                "authoritative_receipt_sha256": _sha(receipt),
            }
        )
    _write_json(
        source / "e2e_stage_ledger.json",
        {
            "schema_version": "apps_rg.e2e_stage_ledger.v2",
            "entries": source_entries,
        },
    )
    _write_json(
        source / "uwg_commit_receipt.json",
        {"schema_version": "L4-UWG-1.0.0", "commit_status": "COMMITTED"},
    )
    _write_json(
        source / "apps_rg_product_authorization_receipt.json",
        {
            "schema_version": "apps_rg.product_authorization_receipt.v1",
            "authorized": True,
        },
    )

    w0 = _write_semantic(
        replay / "w0_zero_provider_preflight_receipt.json",
        {
            "schema_version": "apps_rg.post_runtime_zero_provider_preflight.v1",
            "wave": "W0",
            "status": "PASS",
            "w0_scope_complete": True,
            "source_run_id": source_run_id,
            "source_unchanged": True,
            "source_manifest_sha256": digest,
            "attempt_counters": _counters(),
            "clean_import_state": True,
        },
    )
    assert w0["semantic_digest"]

    w1_dir = replay / "w1"
    x3_codes = {lane: "X3A_DENY_REROUTE" for lane in subject.EXPECTED_LANES}
    reconciliation = _write_semantic(
        w1_dir / "w1_authoritative_reconciliation.json",
        {
            "schema_version": "apps_rg.authority_reconciliation.v1",
            "status": "BLOCKED",
            "source_run_id": source_run_id,
            "product_authorized": False,
            "publish_allowed": False,
            "authorized_lane_count": 0,
            "blocked_lane_count": len(subject.EXPECTED_LANES),
            "authoritative_x3_codes": x3_codes,
        },
    )
    correction = _write_semantic(
        w1_dir / "w1_authorization_correction_receipt.json",
        {
            "schema_version": "apps_rg.authorization_correction.v1",
            "status": "PASS",
            "source_run_id": source_run_id,
            "corrected_product_authorized": False,
            "corrected_pipeline_complete": False,
            "correction_disposition": "SUPERSEDED_INVALID_AUTHORITY",
            "original_authorized_claim": True,
        },
    )
    assert correction["semantic_digest"]
    parallel = _write_semantic(
        w1_dir / "w1_l0_parallel_replay_proof.json",
        {
            "schema_version": "apps_rg.l0_parallel_artifact_replay.v1",
            "status": "PASS",
            "parallel_overlap_proven": True,
            "provider_or_model_execution": False,
        },
    )
    assert parallel["semantic_digest"]
    w1_completion = _write_semantic(
        w1_dir / "w1_completion_receipt.json",
        {
            "schema_version": "apps_rg.authority_reconciliation_completion.v1",
            "wave": "W1",
            "status": "PASS",
            "scope_complete": True,
            "source_run_id": source_run_id,
            "product_authorized": False,
            "pipeline_complete": False,
        },
    )
    _guard(
        w1_dir / "w1_zero_provider_guard_receipt.json",
        wave="W1",
        source_run_id=source_run_id,
        completion=w1_completion,
        apps_eval=False,
        l6=False,
        source_manifest_sha256=digest,
    )
    assert reconciliation["semantic_digest"]

    w2_dir = replay / "w2"
    eval_record_path = _write_json(
        w2_dir / "apps_eval" / "record" / "eval_record.json",
        {
            "schema_version": "apps_eval.completed_eval_record.v1",
            "record_id": "record-1",
            "created_at": "1970-01-01T00:00:00Z",
            "eval_execution_complete": True,
            "eval_verdict": "fail",
            "release_blocked": True,
        },
    )
    eval_seal_path = _write_json(
        w2_dir / "apps_eval" / "record" / "apps_rg_eval_package_seal.json",
        {"schema_version": "apps_eval.apps_rg_eval_package_seal.v1"},
    )
    supersession_path = w2_dir / "eval_package_supersession_manifest.json"
    _write_semantic(
        supersession_path,
        {
            "schema_version": "apps_rg.eval_package_supersession_manifest.v1",
            "status": "PASS",
            "authoritative_record_id": "record-1",
            "canonical_package_ids": ["record-1"],
            "canonical_package_count": 1,
            "superseded_package_count": 0,
            "superseded_packages": [],
            "destructive_delete_performed": False,
            "packages_recoverable": True,
        },
    )
    w2_completion = _write_semantic(
        w2_dir / "w2_completion_receipt.json",
        {
            "schema_version": "apps_rg.apps_eval_replay_completion.v1",
            "wave": "W2",
            "status": "PASS",
            "scope_complete": True,
            "source_run_id": source_run_id,
            "record_id": "record-1",
            "product_authorized": False,
            "pipeline_complete": False,
            "eval_execution_complete": True,
            "eval_verdict": "fail",
            "release_blocked": True,
            "w3_authorized": True,
            "admission_status": "FAIL",
            "admission_failure_modes": ["admission.product_authority_invalid"],
            "eval_record": _file_binding(eval_record_path, root=w2_dir),
            "eval_package_seal": _file_binding(eval_seal_path, root=w2_dir),
            "eval_package_supersession_manifest": _file_binding(
                supersession_path, root=w2_dir
            ),
        },
    )
    _guard(
        w2_dir / "w2_zero_provider_guard_receipt.json",
        wave="W2",
        source_run_id=source_run_id,
        completion=w2_completion,
        apps_eval=True,
        l6=False,
        source_manifest_sha256=digest,
    )

    w3_dir = replay / "w3"
    bindings = []
    lane_binding_paths = {}
    for lane in subject.EXPECTED_LANES:
        row = {
            "section_id": lane,
            "binding_status": "LEGACY_PACKAGE_ADVISORY",
            "source_evidence_status": "UNAVAILABLE_SOURCE_EVIDENCE",
            "source_evidence_reason_codes": [
                "GOVERNED_V40_PACKAGE_MISSING"
            ],
            "evidence_class": "CONTRACT_ONLY_ADVISORY",
            "apps_eval_row_count": 10,
            "l6_observation_row_count": 0,
            "proof_gaps": ["governed_v40_package_required_for_independent_binding"],
        }
        bindings.append(row)
        lane_binding_paths[lane] = _write_json(
            w3_dir / "independent_bindings" / f"{lane}.binding.json",
            row,
        )
    bindings_payload = _write_semantic(
        w3_dir / "l6_section_apps_eval_bindings.json",
        {
            "schema_version": "apps_rg.l6_section_apps_eval_bindings.v3",
            "eval_record_id": "record-1",
            "bindings": bindings,
        },
    )
    closure = _write_semantic(
        w3_dir / "l6_apps_eval_binding_closure_receipt.json",
        {
            "schema_version": "apps_rg.l6_apps_eval_binding_closure_receipt.v2",
            "binding_closure_status": "FAIL",
            "apps_eval_rows_bound": False,
            "unavailable_source_evidence_count": len(subject.EXPECTED_LANES),
            "unavailable_source_evidence_section_ids": list(
                subject.EXPECTED_LANES
            ),
            "checks": {
                "source_evidence_availability_classified": True,
                "unavailable_source_evidence_never_bound": True,
            },
        },
    )
    assert closure["semantic_digest"]
    calibration_path = w3_dir / "l6_judge_human_calibration_status.json"
    _write_semantic(
        calibration_path,
        {
            "schema_version": "apps_rg.l6_judge_human_calibration_status.v1",
            "status": "PASS",
            "calibration_status": "NOT_MEASURED",
            "human_labels_present": False,
            "n_calibration_samples": 0,
            "spearman_rho": None,
            "p_value": None,
            "informational_only": True,
            "required_for_exit": False,
            "release_authority_effect": "NONE",
        },
    )
    projection_bridge_path = _write_json(
        w3_dir / "projection" / "l6_shadow_bridge.json",
        {"schema_version": "apps_eval.l6_shadow_bridge.v2"},
    )
    w3_artifacts = []
    for role, path in (
        (
            "l6_section_apps_eval_bindings",
            w3_dir / "l6_section_apps_eval_bindings.json",
        ),
        (
            "l6_apps_eval_binding_closure",
            w3_dir / "l6_apps_eval_binding_closure_receipt.json",
        ),
        ("l6_judge_human_calibration_status", calibration_path),
        ("projection_l6_shadow_bridge", projection_bridge_path),
    ):
        w3_artifacts.append({"artifact_role": role, **_file_binding(path, root=w3_dir)})
    for lane, path in lane_binding_paths.items():
        w3_artifacts.append(
            {
                "artifact_role": f"{lane}_binding",
                **_file_binding(path, root=w3_dir),
            }
        )
    w3_seal_body = {
        "schema_version": "apps_rg.l6_shadow_replay_package_seal.v1",
        "status": "PASS",
        "record_id": "record-1",
        "artifact_count": len(w3_artifacts),
        "artifacts": w3_artifacts,
    }
    w3_seal_path = _write_json(
        w3_dir / "w3_l6_shadow_package_seal.json",
        {**w3_seal_body, "manifest_sha256": _canonical(w3_seal_body)},
    )
    w3_bindings_path = w3_dir / "l6_section_apps_eval_bindings.json"
    w3_closure_path = w3_dir / "l6_apps_eval_binding_closure_receipt.json"
    w3_completion = _write_semantic(
        w3_dir / "w3_completion_receipt.json",
        {
            "schema_version": "apps_rg.l6_shadow_replay_completion.v1",
            "wave": "W3",
            "status": "PASS",
            "scope_complete": True,
            "source_run_id": source_run_id,
            "record_id": "record-1",
            "product_authorized": False,
            "pipeline_complete": False,
            "l6_execution_complete": True,
            "l6_shadow_observability_verdict": "fail",
            "binding_closure_status": "FAIL",
            "release_blocked": True,
            "apps_eval_rows_bound": False,
            "w4_authorized": True,
            "calibration_status": "NOT_MEASURED",
            "human_labels_present": False,
            "n_calibration_samples": 0,
            "calibration_informational_only": True,
            "calibration_required_for_exit": False,
            "section_summary": {
                "sections_total": len(subject.EXPECTED_LANES),
                "sections_bound": 0,
                "sections_source_evidence_available": 0,
                "sections_source_evidence_unavailable": len(
                    subject.EXPECTED_LANES
                ),
                "source_evidence_status_by_section": {
                    lane: "UNAVAILABLE_SOURCE_EVIDENCE"
                    for lane in subject.EXPECTED_LANES
                },
                "observed_lane_ids": list(subject.EXPECTED_LANES),
            },
            "w3_package_seal": _file_binding(w3_seal_path, root=w3_dir),
            "l6_section_apps_eval_bindings": _file_binding(
                w3_bindings_path, root=w3_dir
            ),
            "l6_apps_eval_binding_closure": _file_binding(
                w3_closure_path, root=w3_dir
            ),
            "l6_judge_human_calibration_status": _file_binding(
                calibration_path, root=w3_dir
            ),
        },
    )
    _guard(
        w3_dir / "w3_zero_provider_guard_receipt.json",
        wave="W3",
        source_run_id=source_run_id,
        completion=w3_completion,
        apps_eval=False,
        l6=True,
        source_manifest_sha256=digest,
    )
    assert bindings_payload["semantic_digest"]
    return source, replay


def test_w4_closes_blocked_run_without_rewriting_runtime_truth(
    tmp_path: Path,
) -> None:
    source, replay = _build_prior_chain(tmp_path)

    result = subject.emit_w4_terminal_closeout_replay(
        source_run=source,
        output_dir=replay / "w4",
    )

    completion = result["completion"]
    assert completion["status"] == "PASS"
    assert completion["scope_complete"] is True
    assert completion["product_authorized"] is False
    assert completion["post_runtime_execution_complete"] is True
    assert completion["eval_verdict"] == "fail"
    assert completion["observability_complete"] is True
    assert completion["terminal_closed"] is True
    assert completion["terminal_outcome"] == "BLOCKED_NON_PRODUCT"
    assert completion["pipeline_complete"] is False
    assert completion["new_uwg_operation_attempted"] is False
    assert completion["determinism_replay"]["execution_count"] == 2
    assert completion["determinism_replay"]["artifact_bytes_stable"] is True
    assert completion["telemetry_summary"]["event_count"] == 17
    assert completion["telemetry_summary"]["l6_lane_event_count"] == 11
    assert completion["telemetry_summary"]["l6_calibration_event_count"] == 1
    assert completion["calibration_status"] == "NOT_MEASURED"
    assert completion["human_labels_present"] is False

    ledger = json.loads(
        (replay / "w4" / subject.W4_LEDGER_FILENAME).read_text(encoding="utf-8")
    )
    entries = {row["stage_id"]: row for row in ledger["entries"]}
    assert entries["APPS_RG_L2"]["status"] == "FAIL"
    assert entries["X2_AGGREGATION"]["status"] == "PASS"
    assert entries["X2_AGGREGATION"]["authority_effect"] == "NON_PRODUCT_ONLY"
    assert entries["X3_DISPOSITION"]["status"] == "FAIL"
    assert entries["PRODUCT_ELIGIBILITY"]["status"] == "BLOCKED"
    assert entries["UWG_COMMIT"]["status"] == "FAIL"
    assert entries["APPS_EVAL"]["status"] == "PASS"
    assert entries["APPS_EVAL"]["eval_verdict"] == "fail"
    assert entries["L6_OBSERVABILITY"]["status"] == "PASS"
    assert entries["L6_OBSERVABILITY"]["grain_parity_status"] == "FAIL"
    assert entries["TERMINAL_NON_PRODUCT"]["status"] == "PASS"

    valid, errors = subject.verify_terminal_non_product_manifest(
        result["terminal_manifest_path"],
        source_run=source,
        replay_root=replay,
    )
    assert valid is True
    assert errors == []


def test_terminal_manifest_detects_bound_receipt_mutation(tmp_path: Path) -> None:
    source, replay = _build_prior_chain(tmp_path)
    result = subject.emit_w4_terminal_closeout_replay(
        source_run=source,
        output_dir=replay / "w4",
    )
    receipt = source / "e2e_ledger_receipts" / "0000_fresh_preflight.json"
    original = receipt.read_bytes()
    receipt.write_bytes(b"!" + original[1:])

    valid, errors = subject.verify_terminal_non_product_manifest(
        result["terminal_manifest_path"],
        source_run=source,
        replay_root=replay,
    )

    assert valid is False
    assert any("digest_mismatch" in error for error in errors)


def test_terminal_manifest_rejects_duplicate_receipt_identity(
    tmp_path: Path,
) -> None:
    source, replay = _build_prior_chain(tmp_path)
    result = subject.emit_w4_terminal_closeout_replay(
        source_run=source,
        output_dir=replay / "w4",
    )
    manifest_path = Path(result["terminal_manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bound_receipts"][-1] = dict(manifest["bound_receipts"][0])
    manifest_body = {
        key: value
        for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    manifest["manifest_sha256"] = _canonical(manifest_body)
    _write_json(manifest_path, manifest)

    valid, errors = subject.verify_terminal_non_product_manifest(
        manifest_path,
        source_run=source,
        replay_root=replay,
    )

    assert valid is False
    assert "receipt_identities_unique" in errors


def test_w4_fails_closed_on_tampered_w3_completion(tmp_path: Path) -> None:
    source, replay = _build_prior_chain(tmp_path)
    path = replay / "w3" / "w3_completion_receipt.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("semantic_digest")
    payload["product_authorized"] = True
    completion = _write_semantic(path, payload)
    _guard(
        replay / "w3" / "w3_zero_provider_guard_receipt.json",
        wave="W3",
        source_run_id=source.name,
        completion=completion,
        apps_eval=False,
        l6=True,
        source_manifest_sha256=(
            json.loads(
                (replay / "w0_zero_provider_preflight_receipt.json").read_text(
                    encoding="utf-8"
                )
            )["source_manifest_sha256"]
        ),
    )

    with pytest.raises(
        subject.TerminalCloseoutReplayError,
        match="w3_evidence_invalid",
    ):
        subject.emit_w4_terminal_closeout_replay(
            source_run=source,
            output_dir=replay / "w4",
        )


def test_w4_fails_closed_on_source_manifest_chain_break(tmp_path: Path) -> None:
    source, replay = _build_prior_chain(tmp_path)
    guard_path = replay / "w3" / "w3_zero_provider_guard_receipt.json"
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    guard.pop("semantic_digest")
    guard["source_manifest_sha256"] = "sha256:" + "b" * 64
    _write_semantic(guard_path, guard)

    with pytest.raises(
        subject.TerminalCloseoutReplayError,
        match="w3_guard_invalid:source_manifest_continuity",
    ):
        subject.emit_w4_terminal_closeout_replay(
            source_run=source,
            output_dir=replay / "w4",
        )


def test_w4_module_load_is_stdlib_only() -> None:
    code = r'''
import importlib.util
import json
import sys

name = "_apps_rg_terminal_closeout_replay_test"
spec = importlib.util.spec_from_file_location(name, sys.argv[1])
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module
spec.loader.exec_module(module)
blocked = [
    item for item in sys.modules
    if item == "openai"
    or item.startswith("openai.")
    or item == "anthropic"
    or item.startswith("anthropic.")
    or item.startswith("apps_rg_runtime.L4_state")
]
assert blocked == []
print(json.dumps({"stdlib_only": True}))
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT / "src"), environment.get("PYTHONPATH", "")))
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(REPO_ROOT / "src/apps_rg/runtime/terminal_closeout_replay.py"),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"stdlib_only": True}
