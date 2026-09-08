"""Contract tests for Apps RG's frozen-input eval and independent L6 audit."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from apps_rg.runtime.evaluation_assurance import (
    derive_evaluation_decision,
    run_l6_evaluation_audit,
)
from apps_rg.runtime.evaluation_manifest import (
    EXPECTED_LANES,
    _LANE_ARTIFACTS,
    _ROOT_ARTIFACTS,
    emit_candidate_evaluation_manifest,
    validate_candidate_evaluation_manifest,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _seed_qualified_candidate(root: Path) -> Path:
    """Create the smallest byte-complete V2 product input bundle."""

    for _role, ref, required in _ROOT_ARTIFACTS:
        if required:
            _write_json(root / ref, {"status": "PASS", "ref": ref})
    _write_json(
        root / "runtime_identity_envelope.json",
        {
            "payload": {
                "parent_run_id": "parent-001",
                "child_run_id": "child-001",
            }
        },
    )
    _write_json(
        root / "FINAL_RESUME_OUTPUT.json",
        {
            "final_resume_json": {
                "relpath": "modular_r4/final_resume_assembly/final_resume.json"
            }
        },
    )
    _write_json(
        root / "modular_r4" / "final_resume_assembly" / "final_resume.json",
        {"sections": []},
    )
    for lane_id in EXPECTED_LANES:
        lane = root / "lanes" / lane_id
        for _role, filename, required in _LANE_ARTIFACTS:
            if required:
                _write_json(
                    lane / filename,
                    {
                        "run_id": f"{lane_id}-attempt-001",
                        "status": "PASS",
                        "current_run_mutated": False,
                    },
                )
    return emit_candidate_evaluation_manifest(root)


def _qualified_eval_record(root: Path) -> SimpleNamespace:
    manifest, errors = validate_candidate_evaluation_manifest(root)
    assert errors == []
    binding = next(
        row
        for row in manifest["artifact_bindings"]
        if row["lane_id"] == "headline" and row["role"] == "lane_x2_gate_outputs"
    )
    eval_dir = root / "apps_eval" / "record-001"
    eval_record = eval_dir / "eval_record.json"
    _write_json(eval_record, {"record_id": "eval-001"})
    scorecard_rows = eval_dir / "scorecard_rows.jsonl"
    scorecard_rows.parent.mkdir(parents=True, exist_ok=True)
    scorecard_rows.write_text("{}\n", encoding="utf-8")
    component_scorecards = eval_dir / "component_scorecards.csv"
    component_scorecards.write_text("component_id\n", encoding="utf-8")
    coverage_matrix = eval_dir / "coverage_matrix.csv"
    coverage_matrix.write_text("row_id\n", encoding="utf-8")
    regression_summary = eval_dir / "regression.json"
    _write_json(regression_summary, {"verdict": "pass"})
    package_artifacts = {
        "eval_record": eval_record,
        "scorecard_rows": scorecard_rows,
        "component_scorecards": component_scorecards,
        "coverage_matrix": coverage_matrix,
        "regression_summary": regression_summary,
    }
    _write_json(
        eval_dir / "apps_rg_eval_package_seal.json",
        {
            "record_id": "eval-001",
            "artifacts": [
                {
                    "artifact_role": role,
                    "artifact_ref": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "byte_length": path.stat().st_size,
                }
                for role, path in package_artifacts.items()
            ],
        },
    )
    row = {
        "row_id": "headline-x2-pass",
        "required": True,
        "lane_id": "headline",
        "artifact_role": "lane_x2_gate_outputs",
        "evidence_ref": binding["artifact_ref"],
        "evidence_digest": "sha256:" + binding["sha256"],
        **binding["identity"],
        "verdict": "PASS",
        "failure_mode": "",
    }
    source_identity_row = {
        "row_id": "source-identity-pass",
        "required": True,
        "lane_id": "",
        "artifact_role": "source_identity",
        "evidence_ref": str(root),
        "evidence_digest": "opaque-snapshot-manifest-digest",
        "parent_run_id": manifest["product_identity"]["parent_run_id"],
        "child_run_id": manifest["product_identity"]["child_run_id"],
        "verdict": "PASS",
        "failure_mode": "",
    }
    return SimpleNamespace(
        record_id="eval-001",
        eval_execution_complete=True,
        artifact_paths={
            "eval_record": str(eval_record),
            "scorecard_rows": str(eval_dir / "scorecard_rows.jsonl"),
        },
        scorecard=SimpleNamespace(
            scorecard_rows=[row, source_identity_row],
            coverage_summary={"coverage_complete": True},
        ),
    )


def test_candidate_manifest_reopens_exact_bytes_and_detects_tampering(
    tmp_path: Path,
) -> None:
    _seed_qualified_candidate(tmp_path)

    _manifest, errors = validate_candidate_evaluation_manifest(tmp_path)
    assert errors == []

    (tmp_path / "lanes" / "headline" / "x2_gate_outputs.json").write_text(
        '{"status":"TAMPERED"}\n', encoding="utf-8"
    )
    _manifest, errors = validate_candidate_evaluation_manifest(tmp_path)
    assert "candidate_evaluation_binding_digest_mismatch" in errors
    assert "candidate_evaluation_binding_length_mismatch" in errors


def test_l6_audit_independently_reopens_scorecard_sources_and_decision(
    tmp_path: Path,
) -> None:
    _seed_qualified_candidate(tmp_path)
    record = _qualified_eval_record(tmp_path)

    audit = run_l6_evaluation_audit(artifact_dir=tmp_path, eval_record=record)
    decision = derive_evaluation_decision(eval_record=record, l6_audit=audit)

    assert audit["l6_integrity_status"] == "PASS"
    assert audit["apps_eval_rows_bound"] is True
    assert decision["evaluation_validity"] == "PASS"
    assert decision["deterministic_product_status"] == "PASS"


def test_l6_audit_rejects_cross_run_or_digest_mismatched_scorecard_row(
    tmp_path: Path,
) -> None:
    _seed_qualified_candidate(tmp_path)
    record = _qualified_eval_record(tmp_path)
    record.scorecard.scorecard_rows[0]["evidence_digest"] = "not-the-frozen-byte-digest"
    record.scorecard.scorecard_rows[0]["child_run_id"] = "another-run"

    audit = run_l6_evaluation_audit(artifact_dir=tmp_path, eval_record=record)

    assert audit["l6_integrity_status"] == "FAIL"
    reasons = audit["row_errors"][0]["reason"]
    assert "l6_evidence_digest_mismatch" in reasons
    assert "l6_identity_mismatch:child_run_id" in reasons


def test_decision_distinguishes_invalid_evaluation_from_product_failure() -> None:
    base = SimpleNamespace(
        eval_execution_complete=True,
        scorecard=SimpleNamespace(
            coverage_summary={"coverage_complete": True},
            scorecard_rows=[],
        ),
    )
    audit = {
        "l6_integrity_status": "PASS",
        "checks": {"eval_package_seal_present": True},
    }
    invalid = SimpleNamespace(
        eval_execution_complete=True,
        scorecard=SimpleNamespace(
            coverage_summary={"coverage_complete": True},
            scorecard_rows=[
                {
                    "required": True,
                    "verdict": "FAIL",
                    "failure_mode": "evidence.source_identity_missing",
                }
            ],
        ),
    )
    product_failure = SimpleNamespace(
        eval_execution_complete=True,
        scorecard=SimpleNamespace(
            coverage_summary={"coverage_complete": True},
            scorecard_rows=[
                {
                    "required": True,
                    "verdict": "FAIL",
                    "failure_mode": "product.x2_gate_failed",
                }
            ],
        ),
    )

    assert derive_evaluation_decision(eval_record=base, l6_audit=audit)[
        "evaluation_status"
    ] == "PASS"
    assert derive_evaluation_decision(eval_record=invalid, l6_audit=audit)[
        "evaluation_status"
    ] == "EVALUATION_INVALID"
    assert derive_evaluation_decision(eval_record=product_failure, l6_audit=audit)[
        "evaluation_status"
    ] == "PRODUCT_FAIL"


class TestEvaluationAssurance(unittest.TestCase):
    def test_candidate_manifest_reopens_exact_bytes_and_detects_tampering(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_candidate_manifest_reopens_exact_bytes_and_detects_tampering(Path(tmpdir))

    def test_l6_audit_independently_reopens_scorecard_sources_and_decision(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_l6_audit_independently_reopens_scorecard_sources_and_decision(Path(tmpdir))

    def test_l6_audit_rejects_cross_run_or_digest_mismatched_scorecard_row(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            test_l6_audit_rejects_cross_run_or_digest_mismatched_scorecard_row(Path(tmpdir))

    def test_decision_distinguishes_invalid_evaluation_from_product_failure(self) -> None:
        test_decision_distinguishes_invalid_evaluation_from_product_failure()


if __name__ == "__main__":
    unittest.main()
