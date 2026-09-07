"""W3 acceptance for deterministic, independent L6 shadow replay."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from apps_rg.runtime import l6_shadow_replay as subject


REPO_ROOT = Path(__file__).resolve().parents[4]


def _scorecard_row(lane_id: str) -> dict[str, object]:
    digest = "sha256:" + "1" * 64
    return {
        "suite_id": "apps_rg.current.resume_generation",
        "scenario_id": "post-runtime-test",
        "app_id": "apps_rg",
        "row_id": f"row-{lane_id}",
        "microstep_id": f"{lane_id}.X1D.judge_result.pass",
        "stage_id": "X1D",
        "component_id": "apps_rg.generated_lane",
        "subcomponent_id": "lane_x1d_judge_panel",
        "verdict": "FAIL",
        "score": 0.0,
        "severity": "BLOCK",
        "required": True,
        "run_id": "eval-record",
        "lane_id": lane_id,
        "gate_id": "x1d",
        "artifact_role": "lane_x1d_llm_judge_outputs",
        "artifact_ref": f"modular_r4/sections/{lane_id}/x1d_llm_judge_outputs.json",
        "evidence_ref": f"modular_r4/sections/{lane_id}/x1d_llm_judge_outputs.json",
        "evidence_digest": digest,
        "failure_mode": "evidence.source_identity_missing",
        "failure_family": "evidence",
        "parent_run_id": "parent",
        "child_run_id": "child",
        "section_attempt_id": "",
        "eval_record_id": "eval-record",
        "runtime_exhaust_bundle_id": "",
        "microstep_contract_digest": digest,
        "registry_digest": digest,
        "snapshot_digest": digest,
    }


def test_legacy_l6_packages_remain_advisory_and_never_bind(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "w3"
    rows = [_scorecard_row(lane) for lane in subject.EXPECTED_LANES]
    for lane in subject.EXPECTED_LANES:
        lane_dir = source / "modular_r4" / "sections" / lane
        lane_dir.mkdir(parents=True)
        (lane_dir / "l6_shadow_eval_package.json").write_text(
            json.dumps({"schema_version": "apps_rg.l6_shadow_eval_package.v1"}),
            encoding="utf-8",
        )
    record = SimpleNamespace(
        record_id="eval-record",
        snapshot_digest="sha256:" + "1" * 64,
        registry_digest="sha256:" + "1" * 64,
    )

    result = subject._write_independent_bindings(
        source=source,
        output_dir=output,
        record=record,
        scorecard_rows=rows,
        scorecard_ref="sealed-scorecard.jsonl",
    )

    assert result["summary"]["sections_total"] == 11
    assert result["summary"]["sections_legacy"] == 11
    assert result["summary"]["sections_bound"] == 0
    assert result["summary"]["apps_eval_rows_bound"] is False
    assert result["closure"]["binding_closure_status"] == "FAIL"
    assert result["closure"]["evidence_class"] == "CONTRACT_ONLY_ADVISORY"
    assert all(
        binding["binding_status"] == "LEGACY_PACKAGE_ADVISORY"
        and binding["source_evidence_status"]
        == "UNAVAILABLE_SOURCE_EVIDENCE"
        and binding["source_evidence_reason_codes"]
        == ["GOVERNED_V40_PACKAGE_MISSING"]
        and binding["evidence_class"] == "CONTRACT_ONLY_ADVISORY"
        for binding in result["payload"]["bindings"]
    )
    assert result["summary"]["sections_source_evidence_available"] == 0
    assert result["summary"]["sections_source_evidence_unavailable"] == 11
    assert result["closure"]["checks"][
        "source_evidence_availability_classified"
    ] is True
    assert result["closure"]["checks"][
        "unavailable_source_evidence_never_bound"
    ] is True


def test_missing_l6_package_is_explicit_unavailable_source_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "w3"
    rows = [_scorecard_row(lane) for lane in subject.EXPECTED_LANES]
    record = SimpleNamespace(
        record_id="eval-record",
        snapshot_digest="sha256:" + "1" * 64,
        registry_digest="sha256:" + "1" * 64,
    )

    result = subject._write_independent_bindings(
        source=source,
        output_dir=output,
        record=record,
        scorecard_rows=rows,
        scorecard_ref="sealed-scorecard.jsonl",
    )

    assert result["summary"]["sections_missing"] == 11
    assert result["summary"]["sections_source_evidence_unavailable"] == 11
    assert result["closure"]["unavailable_source_evidence_count"] == 11
    assert all(
        row["binding_status"] == "MISSING_PACKAGE"
        and row["source_evidence_status"] == "UNAVAILABLE_SOURCE_EVIDENCE"
        for row in result["payload"]["bindings"]
    )


def test_no_human_labels_emit_informational_not_measured_calibration(
    tmp_path: Path,
) -> None:
    payload, path = subject._emit_calibration_status(
        output_dir=tmp_path,
        source_run_id="saved-run",
        record_id="eval-record",
    )

    assert payload["schema_version"] == subject.W3_CALIBRATION_SCHEMA
    assert payload["calibration_status"] == "NOT_MEASURED"
    assert payload["human_labels_present"] is False
    assert payload["n_calibration_samples"] == 0
    assert payload["spearman_rho"] is None
    assert payload["p_value"] is None
    assert payload["informational_only"] is True
    assert payload["required_for_exit"] is False
    assert payload["release_authority_effect"] == "NONE"
    assert payload["human_grade_inference_attempted"] is False
    assert subject._semantic_digest_valid(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _captured_l6_failure(output: Path) -> dict[str, Path]:
    try:
        raise LookupError("injected L6 shadow failure")
    except LookupError as exc:
        return subject._emit_stage_failure(
            output=output,
            source_run_id="saved-run",
            exc=exc,
            attempt=1,
        )


def test_l6_failure_and_resume_bind_saved_w2_without_upstream_replay(
    tmp_path: Path,
) -> None:
    paths = _captured_l6_failure(tmp_path)
    error = json.loads(paths["error_receipt"].read_text(encoding="utf-8"))
    span = json.loads(paths["error_span"].read_text(encoding="utf-8"))
    assert error["schema_version"] == subject.W3_ERROR_RECEIPT_SCHEMA
    assert error["stage_id"] == "L6_SHADOW_OBSERVABILITY"
    assert "injected L6 shadow failure" in error["traceback"]
    assert error["w1_replayed"] is False
    assert error["w2_replayed"] is False
    assert error["apps_eval_replayed"] is False
    assert error["generation_replayed"] is False
    assert span["apps_eval_execution"] is False
    assert span["provider_execution"] is False

    resume_path = subject._emit_stage_resume(
        output=tmp_path,
        source_run_id="saved-run",
        w2={
            "completion_path": tmp_path / "../w2/w2_completion_receipt.json",
            "completion": {"semantic_digest": "sha256:w2-completion"},
            "guard_path": tmp_path / "../w2/w2_zero_provider_guard_receipt.json",
            "guard": {"semantic_digest": "sha256:w2-guard"},
        },
    )

    assert resume_path is not None
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    assert resume["schema_version"] == subject.W3_RESUME_RECEIPT_SCHEMA
    assert resume["status"] == "PASS"
    assert resume["resume_from_stage"] == "L6_SHADOW_OBSERVABILITY"
    assert resume["w1_replayed"] is False
    assert resume["w2_replayed"] is False
    assert resume["apps_eval_replayed"] is False
    assert resume["generation_replayed"] is False
    assert resume["w2_completion_semantic_digest"] == "sha256:w2-completion"
    assert subject._semantic_digest_valid(resume)


def test_eval_package_seal_reopens_every_bound_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "eval"
    run_dir.mkdir()
    roles = {
        "eval_record": "eval_record.json",
        "scorecard_rows": "scorecard_rows.jsonl",
        "component_scorecards": "component_scorecards.csv",
        "coverage_matrix": "coverage_matrix.csv",
        "regression_summary": "regression.json",
    }
    artifacts = []
    for role, name in roles.items():
        path = run_dir / name
        path.write_text(f"{role}\n", encoding="utf-8")
        artifacts.append(
            {
                "artifact_role": role,
                "artifact_ref": name,
                "byte_length": path.stat().st_size,
                "sha256": subject._sha256_file(path),
            }
        )
    body = {
        "schema_version": "apps_eval.apps_rg_eval_package_seal.v1",
        "status": "PASS",
        "record_id": "record",
        "artifacts": artifacts,
    }
    (run_dir / "apps_rg_eval_package_seal.json").write_text(
        json.dumps({**body, "manifest_sha256": subject._canonical_digest(body)}),
        encoding="utf-8",
    )

    valid, errors = subject._verify_eval_package_seal(run_dir)
    assert valid is True
    assert errors == []

    (run_dir / "scorecard_rows.jsonl").write_text("tampered\n", encoding="utf-8")
    valid, errors = subject._verify_eval_package_seal(run_dir)
    assert valid is False
    assert "eval_package_seal_artifact_digest_mismatch:scorecard_rows" in errors


def test_local_shadow_replay_keeps_provider_and_uwg_modules_out(
    tmp_path: Path,
) -> None:
    code = r'''
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

module_name = "_apps_rg_l6_shadow_replay_test"
spec = importlib.util.spec_from_file_location(module_name, sys.argv[2])
assert spec is not None and spec.loader is not None
replay = importlib.util.module_from_spec(spec)
sys.modules[module_name] = replay
spec.loader.exec_module(replay)
record = type("Record", (), {"record_id": "record"})()
root = Path(sys.argv[1])
paths = replay._emit_projection_bridge(
    record,
    root,
    eval_record_path="eval_record.json",
    l6_handoff_path="l6_handoff.json",
)
first = {
    key: hashlib.sha256(Path(value).read_bytes()).hexdigest()
    for key, value in paths.items()
}
paths = replay._emit_projection_bridge(
    record,
    root,
    eval_record_path="eval_record.json",
    l6_handoff_path="l6_handoff.json",
)
second = {
    key: hashlib.sha256(Path(value).read_bytes()).hexdigest()
    for key, value in paths.items()
}
assert first == second
assert "openai" not in sys.modules
assert "anthropic" not in sys.modules
bridge = json.loads(Path(paths["l6_shadow_bridge"]).read_text(encoding="utf-8"))
assert bridge["deterministic_replay"] is True
assert bridge["projection_consistency_only"] is True
assert bridge["evidence_class"] == "CONTRACT_ONLY_ADVISORY"
print(json.dumps({"stable": True, "artifact_count": len(paths)}))
'''
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            (
                str(REPO_ROOT / "src"),
                environment.get("PYTHONPATH", ""),
            ),
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(tmp_path / "projection"),
            str(REPO_ROOT / "src/apps_rg/runtime/l6_shadow_replay.py"),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"artifact_count": 10, "stable": True}
