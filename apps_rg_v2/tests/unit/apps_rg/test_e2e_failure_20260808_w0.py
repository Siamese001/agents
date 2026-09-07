"""Wave 0 freeze and executable regressions for the 2026-08-08 E2E failure."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest


FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "e2e_failure_20260808T062125Z_c9caf451"
)
CANONICAL_X3_CODES = {
    "X3A_DENY_REROUTE",
    "X3B_ESCALATE_HITL",
    "X3C_COMMIT_REQUEST_TO_UWG",
    "X3D_ALLOW_FINISH",
    "X3E_SAFE_ABSTAIN",
}


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _canonical_json_sha256(path: Path) -> str:
    canonical = json.dumps(
        _load(path),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _authority_digest(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _identity() -> dict[str, str]:
    return {
        "producer_app_id": "apps_research",
        "consumer_app_id": "apps_rg",
        "parent_run_id": "w0-parent",
        "child_run_id": "w0-child",
        "request_id": "w0-request",
        "trace_root": "w0-trace",
        "tenant_id": "w0-tenant",
        "target_company": "Anthropic",
        "target_role": "Partnerships Lead",
        "jd_sha256": "sha256:" + "1" * 64,
        "brief_sha256": "sha256:" + "2" * 64,
        "policy_hash": "sha256:" + "3" * 64,
        "blueprint_hash": "sha256:" + "4" * 64,
        "schema_version": "apps_research_rg_run_identity.v1",
    }


def _write_receipt(
    root: Path,
    stage_id: str,
    identity: dict[str, str],
    *,
    status: str = "PASS",
) -> Path:
    path = root / f"{stage_id.lower()}_receipt.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": f"w0.{stage_id.lower()}.v1",
                "stage_id": stage_id,
                "status": status,
                "identity": identity,
                "created_at_utc": "2026-08-08T06:21:25Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="module")
def fresh_failed_core_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    """Generate one deterministic L2 fault through the current app-owned spine."""
    root = tmp_path_factory.mktemp("w0_failed_core")
    from apps_rg.runtime.orchestration.integrated_spine_runner import (
        run_integrated_single_action_spine,
    )

    def _raise_invalid_argument() -> None:
        raise OSError(22, "Invalid argument")

    result = run_integrated_single_action_spine(
        raw_request={
            "jd_payload": {"title": "Partnerships Lead", "description": "JD"},
            "jd_hash": "w0-jd",
            "brief_hash": "w0-brief",
            "resume_hash": "w0-resume",
        },
        l2_callable=_raise_invalid_argument,
        artifact_dir=root,
        cache_preflight_evidence={},
        _test_mode=True,
    )
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        emit_core_runtime_authority,
    )

    emit_core_runtime_authority(root)
    assert result.fault == "OSError:[Errno 22] Invalid argument"
    return root, result


@pytest.fixture(scope="module")
def fresh_nonfault_core_run(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Any]:
    """Generate a non-fault current-spine run to exercise the allow-side logic."""
    root = tmp_path_factory.mktemp("w2_nonfault_core")
    from apps_rg.runtime.orchestration.integrated_spine_runner import (
        run_integrated_single_action_spine,
    )

    result = run_integrated_single_action_spine(
        raw_request={
            "jd_payload": {"title": "Partnerships Lead", "description": "JD"},
            "jd_hash": "w2-jd",
            "brief_hash": "w2-brief",
            "resume_hash": "w2-resume",
        },
        l2_callable=lambda: {"status": "ok"},
        artifact_dir=root,
        cache_preflight_evidence={},
        _test_mode=True,
    )
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        emit_core_runtime_authority,
    )

    emit_core_runtime_authority(root)
    assert result.fault == ""
    return root, result


def test_frozen_manifest_and_artifacts_are_canonical_json_bound() -> None:
    manifest = _load(FIXTURE_DIR / "manifest.json")
    assert manifest["schema_version"] == "apps_rg.e2e_failure_freeze.v1"
    assert manifest["source_agentic_core_commit"] == "cba1303f044f24af364b888122971cab7a972457"
    assert "agentic_core_spine_proof.json" in manifest["artifacts"]
    assert "agentic_core_how_trace.json" in manifest["artifacts"]
    assert manifest["product_authorized"] is False
    assert manifest["pipeline_complete"] is False
    for filename, binding in manifest["artifacts"].items():
        artifact = FIXTURE_DIR / filename
        assert artifact.is_file(), filename
        assert _canonical_json_sha256(artifact) == binding["canonical_json_sha256"]


def test_frozen_failure_signature_is_preserved() -> None:
    failure = _load(FIXTURE_DIR / "integrated_lane_pre_run_failure.json")
    witness = _load(FIXTURE_DIR / "runtime_execution_witness.json")["payload"]
    proof = _load(FIXTURE_DIR / "agentic_core_spine_proof.json")["payload"]
    assert failure["lane_id"] == "competencies"
    assert failure["dispatch_result"]["error"] == "[Errno 22] Invalid argument"
    assert witness["l2"]["status"] == "FAIL"
    assert "agentic_core" in _load(FIXTURE_DIR / "runtime_execution_witness.json")[
        "producer_component"
    ]
    assert proof["success"] is True


def test_lane_failure_envelope_is_actionable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """W1 acceptance is live; the immutable W0 artifact remains historical evidence."""
    from apps_rg.runtime.orchestration.section_lane_executor import (
        LaneExecutionContext,
        run_lane_in_context,
    )
    from apps_rg.runtime.runtime_proof_layout import MODULAR_R4_SECTIONS_ROOT_ENV

    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(tmp_path / "sections"))

    ctx = LaneExecutionContext(
        sections_root=str(tmp_path / "sections"),
        target_company="Anthropic",
        target_role="Partnerships Lead",
        job_description_ref="",
        job_description_text="JD",
        manual_brief="brief",
        lane_provider="external_claude",
        lane_x1d_judges="",
        lane_mock_judges=False,
        run_id="w1-live-run",
        canonical_run_identity=_identity(),
    )

    def _raise_invalid_argument(**_kwargs: object) -> dict[str, Any]:
        raise OSError(22, "Invalid argument")

    dispatch = run_lane_in_context(
        ctx,
        "competencies",
        dispatch_fn=_raise_invalid_argument,
    ).dispatch_result
    assert dispatch["exception_class"] == "OSError"
    assert dispatch["traceback"]
    assert dispatch["operation"]
    assert dispatch["callsite"]


def test_failed_l2_cannot_emit_successful_spine_proof(
    fresh_failed_core_run: tuple[Path, Any],
) -> None:
    root, result = fresh_failed_core_run
    authority = _load(root / "apps_rg_core_runtime_authority.json")
    raw_witness = _load(root / "runtime_execution_witness.json")["payload"]
    raw_proof = _load(root / "apps_rg_spine_proof.json")["payload"]
    proof = authority["normalized_contract"]["spine_proof"]
    assert result.fault
    assert raw_witness["l2"]["status"] == "FAIL"
    assert raw_proof["success"] is False
    assert raw_proof["exit_code"] != 0
    assert "apps_rg_spine_status" not in raw_proof
    assert proof["success"] is False
    assert proof["exit_code"] != 0
    assert proof["apps_rg_spine_status"] != "R4_SINGLE_ACTION_PROVEN"
    assert not any(
        row["code"] == "CORE_SPINE_SUCCESS_CONTRADICTS_L2_FAILURE"
        for row in authority["source_contract_violations"]
    )


def test_runtime_authority_modes_agree(
    fresh_failed_core_run: tuple[Path, Any],
) -> None:
    root, _ = fresh_failed_core_run
    authority = _load(root / "apps_rg_core_runtime_authority.json")
    modes = set(authority["normalized_contract"]["runtime_modes"].values())
    assert modes == {"fault"}
    assert not any(
        row["code"] == "CORE_RUNTIME_MODE_DIVERGENCE"
        for row in authority["source_contract_violations"]
    )


def test_how_trace_producer_and_verifier_are_compatible(
    fresh_failed_core_run: tuple[Path, Any],
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    root, _ = fresh_failed_core_run
    report = verify_core_runtime_authority(root)
    how = report.receipt["normalized_contract"]["how_trace"]
    assert report.valid is True
    assert how["deterministic_digest"]
    assert how["source_stored_digest"] == how["source_recomputed_digest"]
    assert not any(
        row["code"] == "CORE_HOW_TRACE_DIGEST_MISMATCH"
        for row in report.receipt["source_contract_violations"]
    )


def test_x3_producer_and_verifier_are_compatible(
    fresh_failed_core_run: tuple[Path, Any],
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    root, result = fresh_failed_core_run
    report = verify_core_runtime_authority(root)
    x3 = report.receipt["normalized_contract"]["x3"]
    assert x3.get("x3_disposition") in CANONICAL_X3_CODES
    assert result.x3_disposition == "X3A_DENY_REROUTE"
    assert report.valid is True


def test_spine_proof_producer_and_verifier_are_compatible(
    fresh_failed_core_run: tuple[Path, Any],
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    root, _ = fresh_failed_core_run
    report = verify_core_runtime_authority(root)
    refs = report.receipt["normalized_contract"]["spine_proof"]["resolved_refs"]
    assert report.valid is True
    assert refs
    assert all(row["resolved"] for row in refs.values())
    assert refs["runtime_l2_artifact_ref"]["artifact_ref"] == "l2_sealed_artifact.json"
    assert not any(
        row["code"] == "CORE_SPINE_L2_REF_VERIFIER_TARGET_DRIFT"
        for row in report.receipt["source_contract_violations"]
    )


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("X3A", "X3A_DENY_REROUTE"),
        ("X3B", "X3B_ESCALATE_HITL"),
        ("X3C", "X3C_COMMIT_REQUEST_TO_UWG"),
        ("X3D", "X3D_ALLOW_FINISH"),
        ("X3E", "X3E_SAFE_ABSTAIN"),
    ],
)
def test_core_x3_legacy_vocabulary_has_explicit_mapping(
    legacy: str,
    canonical: str,
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        canonicalize_core_x3,
    )

    assert canonicalize_core_x3(legacy) == canonical
    assert canonicalize_core_x3(canonical) == canonical


def test_core_x3_unknown_value_is_not_guessed() -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        canonicalize_core_x3,
    )

    assert canonicalize_core_x3("X3F") == ""


def test_core_runtime_authority_detects_bound_source_tampering(
    fresh_failed_core_run: tuple[Path, Any],
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    source, _ = fresh_failed_core_run
    run_dir = tmp_path / "tampered"
    shutil.copytree(source, run_dir)
    exhaust_path = run_dir / "runtime_exhaust_bundle.json"
    exhaust = _load(exhaust_path)
    exhaust["payload"]["runtime_mode"] = "tampered"
    exhaust_path.write_text(json.dumps(exhaust), encoding="utf-8")

    report = verify_core_runtime_authority(run_dir)

    assert report.valid is False
    assert (
        "CORE_RUNTIME_SOURCE_BINDING_CHANGED:runtime_exhaust_bundle.json"
        in report.errors
    )


def test_core_runtime_authority_rejects_semantically_contradictory_sources(
    fresh_failed_core_run: tuple[Path, Any],
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        emit_core_runtime_authority,
        verify_core_runtime_authority,
    )

    source, _ = fresh_failed_core_run
    run_dir = tmp_path / "contradictory"
    shutil.copytree(source, run_dir)
    proof_path = run_dir / "apps_rg_spine_proof.json"
    proof = _load(proof_path)
    proof["payload"]["success"] = True
    proof["payload"]["exit_code"] = 0
    proof["payload"]["blocking_gaps"] = []
    proof["payload"]["apps_rg_spine_status"] = "R4_SINGLE_ACTION_PROVEN"
    proof["artifact_hash"] = _authority_digest(proof["payload"])
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    receipt = emit_core_runtime_authority(run_dir)
    report = verify_core_runtime_authority(run_dir)

    assert receipt["normalized_contract"]["valid"] is False
    assert (
        "SOURCE_CONTRACT_VIOLATION:CORE_SPINE_SUCCESS_CONTRADICTS_L2_FAILURE"
        in receipt["normalized_contract"]["errors"]
    )
    assert report.valid is False
    assert "CORE_RUNTIME_NORMALIZED_CONTRACT_INVALID" in report.errors


def test_core_runtime_authority_rejects_self_asserted_normalization(
    fresh_failed_core_run: tuple[Path, Any],
    tmp_path: Path,
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    source, _ = fresh_failed_core_run
    run_dir = tmp_path / "self_asserted"
    shutil.copytree(source, run_dir)
    authority_path = run_dir / "apps_rg_core_runtime_authority.json"
    authority = _load(authority_path)
    authority["normalized_contract"]["how_trace"]["deterministic_digest"] = (
        "sha256:" + "f" * 64
    )
    authority.pop("deterministic_digest")
    authority["deterministic_digest"] = _authority_digest(authority)
    authority_path.write_text(json.dumps(authority), encoding="utf-8")

    report = verify_core_runtime_authority(run_dir)

    assert "CORE_RUNTIME_AUTHORITY_DIGEST_MISMATCH" not in report.errors
    assert "CORE_RUNTIME_AUTHORITY_DERIVATION_MISMATCH" in report.errors


def test_product_gate_consumes_normalized_authority_not_raw_core_x3(
    fresh_failed_core_run: tuple[Path, Any],
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import integrated_product_proof_gate as product_gate

    source, _ = fresh_failed_core_run
    run_dir = tmp_path / "product_gate"
    shutil.copytree(source, run_dir)
    product_manifest = run_dir / "apps_rg_product_manifest.json"
    product_manifest.write_text(
        json.dumps(
            {
                "route_id": "apps_rg.integrated_r4",
                "apps_rg_product_outcome_authorized": False,
                "x3_disposition": "X3A_DENY_REROUTE",
            }
        ),
        encoding="utf-8",
    )

    blockers = product_gate._live_product_outcome_blockers(
        run_dir,
        {
            "integrated_run_manifest": product_manifest,
            "apps_rg_core_runtime_authority.json": (
                run_dir / "apps_rg_core_runtime_authority.json"
            ),
        },
    )

    assert "core_runtime_authority_x3:X3A_DENY_REROUTE" not in blockers
    assert "apps_rg_whole_run_exit_authority_missing" in blockers
    assert "core_runtime_authority_spine_not_successful" in blockers
    assert "core_runtime_authority_outcome_not_authorized" not in blockers
    assert "integrated_exit_x3:X3A" not in blockers


def test_nonfault_current_spine_emits_valid_allow_side_evidence(
    fresh_nonfault_core_run: tuple[Path, Any],
) -> None:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        verify_core_runtime_authority,
    )

    root, result = fresh_nonfault_core_run
    report = verify_core_runtime_authority(root)
    receipt = report.receipt
    proof = receipt["normalized_contract"]["spine_proof"]

    assert report.valid is True
    assert set(receipt["normalized_contract"]["runtime_modes"].values()) == {"production"}
    raw_proof = _load(root / "apps_rg_spine_proof.json")["payload"]
    assert raw_proof["success"] is True
    assert raw_proof["exit_code"] == 0
    assert raw_proof["blocking_gaps"] == []
    assert proof["success"] is True
    assert proof["resolved_refs"]["runtime_l2_artifact_ref"]["artifact_ref"] == (
        "l2_sealed_artifact.json"
    )
    assert result.x3_disposition == "X3D_ALLOW_FINISH"
    assert receipt["outcome_authorized"] is True
    assert receipt["status"] == "PASS"


def test_product_ledger_survives_source_receipt_overwrite(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_stage_ledger import (
        ReceiptDerivedE2EStageLedger,
        verify_e2e_stage_ledger,
    )

    identity = _identity()
    ledger = ReceiptDerivedE2EStageLedger.create(
        artifact_dir=tmp_path,
        identity=identity,
    )
    receipt = _write_receipt(tmp_path, "FRESH_PREFLIGHT", identity)
    entry = ledger.record_from_receipt(
        stage_id="FRESH_PREFLIGHT",
        receipt_ref=receipt,
        next_stage_id="APPS_RG_U0",
    )
    receipt.write_text('{"schema_version":"overwritten.v1"}\n', encoding="utf-8")

    report = verify_e2e_stage_ledger(ledger.path)
    assert report.valid is True
    immutable_ref = tmp_path / entry["authoritative_receipt_ref"]
    assert immutable_ref.resolve() != receipt.resolve()


def test_pre_x3_failure_can_reach_sealed_terminal_non_product(tmp_path: Path) -> None:
    from apps_rg.runtime.e2e_stage_ledger import (
        ReceiptDerivedE2EStageLedger,
        verify_e2e_stage_ledger,
    )

    identity = _identity()
    ledger = ReceiptDerivedE2EStageLedger.create(
        artifact_dir=tmp_path,
        identity=identity,
    )
    stages = (
        ("FRESH_PREFLIGHT", "APPS_RG_U0", "PASS"),
        ("APPS_RG_U0", None, "PASS"),
        ("APPS_RG_L1", None, "PASS"),
        ("APPS_RG_L0", None, "PASS"),
        ("APPS_RG_C0", None, "FAIL"),
    )
    for stage_id, next_stage_id, status in stages:
        ledger.record_from_receipt(
            stage_id=stage_id,
            receipt_ref=_write_receipt(
                tmp_path,
                stage_id,
                identity,
                status=status,
            ),
            next_stage_id=next_stage_id,
        )

    from apps_rg.runtime.product_stage_authority import (
        emit_terminal_non_product_authority_receipt,
    )

    ledger_payload = _load(ledger.path)
    decisive = ledger_payload["entries"][-1]
    terminal = emit_terminal_non_product_authority_receipt(
        artifact_dir=tmp_path,
        identity=identity,
        decisive_stage_id="APPS_RG_C0",
        decisive_receipt_ref=decisive["authoritative_receipt_ref"],
        blocked_successor_stage_ids=(
            "APPS_RG_PA",
            "APPS_RG_L2",
            "X1_REVIEW",
            "X2_AGGREGATION",
            "X3_DISPOSITION",
            "PRODUCT_ELIGIBILITY",
        ),
    )
    ledger.record_from_receipt(
        stage_id="TERMINAL_NON_PRODUCT",
        receipt_ref=terminal,
    )
    seal = ledger.seal(
        terminal_state={
            "product_authorized": False,
            "pipeline_complete": False,
            "observability_repair_required": False,
        }
    )
    assert seal.is_file()
    report = verify_e2e_stage_ledger(ledger.path)
    payload = _load(ledger.path)
    assert report.valid is True
    assert report.complete is True
    assert report.sealed is True
    assert payload["entries"][-2]["next_stage_id"] == "TERMINAL_NON_PRODUCT"
    assert payload["entries"][-1]["stage_id"] == "TERMINAL_NON_PRODUCT"


def test_real_canonical_section_entry_uses_e2e_lane_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise the real canonical section runner; mock only the external core seam."""
    from apps_rg.runtime.orchestration.app_single_action_spine import (
        AppsRgSingleActionSpineRunResult,
        ROUTE_ID,
    )
    from apps_rg.runtime.orchestration.canonical_dispatch import (
        run_canonical_apps_rg_from_cli_primitives,
    )
    from apps_rg.runtime.runtime_proof_layout import MODULAR_R4_SECTIONS_ROOT_ENV

    checkout = tmp_path / "checkout"
    source_root = checkout / "src"
    package_init = source_root / "apps_rg" / "__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text("", encoding="utf-8")
    run_root = checkout / "artifacts" / "e2e_w0"
    sections_root = run_root / "modular_r4" / "sections"
    sections_root.mkdir(parents=True)
    (run_root / "spine_run_manifest.json").write_text("{}\n", encoding="utf-8")
    (sections_root / "sections_root_manifest.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(MODULAR_R4_SECTIONS_ROOT_ENV, str(sections_root))
    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "1")
    monkeypatch.setattr(
        "apps_rg.runtime.runtime_proof_layout.find_repo_root",
        lambda: source_root,
    )
    captured: dict[str, Any] = {}

    def _core_seam(**kwargs: Any) -> AppsRgSingleActionSpineRunResult:
        captured.update(kwargs)
        return AppsRgSingleActionSpineRunResult(
            run_id="w0-core-run",
            request_id="w0-core-request",
            route_id=ROUTE_ID,
            x3_disposition="X3A_DENY_REROUTE",
            terminal_r5=False,
            terminal_r5_reason="",
            artifact_dir=Path(kwargs["artifact_dir"]),
            fault="controlled-w0-core-boundary",
            l2_result={},
            execution_witness={},
        )

    monkeypatch.setattr(
        "apps_rg.runtime.orchestration.integrated_spine_runner.run_integrated_single_action_spine",
        _core_seam,
    )
    result = run_canonical_apps_rg_from_cli_primitives(
        target_company="Anthropic",
        target_role="Partnerships Lead",
        jd="Lead AI partnerships.",
        manual_brief="Evidence-bound brief.",
        section="competencies",
        artifact_dir="",
        lane_provider="mock",
        lane_mock_judges=True,
        lane_allow_test_mock_judges=True,
    )

    expected = (sections_root / "competencies").resolve()
    assert Path(captured["artifact_dir"]).resolve() == expected
    assert Path(result["artifact_dir"]).resolve() == expected
    assert result["fault"] == "controlled-w0-core-boundary"
