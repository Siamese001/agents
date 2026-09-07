"""W2 production-boundary failure and package-supersession contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime import apps_eval_replay as subject


def test_w2_w1_contract_refs_are_output_root_independent() -> None:
    refs = {
        subject._w1_contract_ref(subject.W1_RECONCILIATION_FILENAME),
        subject._w1_contract_ref(subject.W1_CORRECTION_FILENAME),
        subject._w1_contract_ref(subject.W1_COMPLETION_FILENAME),
        subject._w1_contract_ref(subject.W1_GUARD_FILENAME),
    }

    assert refs == {
        "w1/w1_authoritative_reconciliation.json",
        "w1/w1_authorization_correction_receipt.json",
        "w1/w1_completion_receipt.json",
        "w1/w1_zero_provider_guard_receipt.json",
    }
    assert all(not Path(ref).is_absolute() for ref in refs)
    assert all("\\" not in ref for ref in refs)

    with pytest.raises(
        subject.AppsEvalReplayError,
        match="unknown_w1_contract_artifact",
    ):
        subject._w1_contract_ref("unowned.json")


def _captured_failure(output: Path) -> dict[str, Path]:
    try:
        raise ValueError("injected apps eval failure")
    except ValueError as exc:
        return subject._emit_stage_failure(
            output=output,
            source_run_id="saved-run",
            exc=exc,
            attempt=1,
        )


def test_w2_real_failure_boundary_emits_receipt_and_error_span(
    tmp_path: Path,
) -> None:
    paths = _captured_failure(tmp_path)
    receipt = json.loads(paths["error_receipt"].read_text(encoding="utf-8"))
    span = json.loads(paths["error_span"].read_text(encoding="utf-8"))

    assert receipt["schema_version"] == subject.W2_ERROR_RECEIPT_SCHEMA
    assert receipt["status"] == "CAPTURED"
    assert receipt["stage_id"] == "APPS_EVAL"
    assert receipt["error_type"] == "ValueError"
    assert "injected apps eval failure" in receipt["traceback"]
    assert receipt["generation_retry_attempted"] is False
    assert receipt["generation_replayed"] is False
    assert receipt["judge_replayed"] is False
    assert receipt["uwg_operation_attempted"] is False
    assert subject._semantic_digest_valid(receipt) is True

    assert span["schema_version"] == subject.W2_ERROR_SPAN_SCHEMA
    assert span["status"] == "ERROR"
    assert span["trace_id"] == receipt["trace_id"]
    assert span["span_id"] == receipt["span_id"]
    assert span["provider_execution"] is False
    assert span["generation_execution"] is False
    assert span["judge_execution"] is False
    assert span["uwg_execution"] is False
    assert subject._semantic_digest_valid(span) is True


def test_w2_resume_receipt_binds_original_failure_without_upstream_replay(
    tmp_path: Path,
) -> None:
    _captured_failure(tmp_path)

    path = subject._emit_stage_resume(
        output=tmp_path,
        source_run_id="saved-run",
    )

    assert path is not None
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == subject.W2_RESUME_RECEIPT_SCHEMA
    assert receipt["status"] == "PASS"
    assert receipt["resume_from_stage"] == "APPS_EVAL"
    assert receipt["upstream_saved_artifacts_reused"] is True
    assert receipt["w1_replayed"] is False
    assert receipt["generation_replayed"] is False
    assert receipt["judge_replayed"] is False
    assert receipt["uwg_operation_attempted"] is False
    assert subject._semantic_digest_valid(receipt) is True


def test_w2_supersedes_unbound_packages_without_deleting_them(
    tmp_path: Path,
) -> None:
    root = tmp_path / "apps_eval/apps_rg_current_resume_generation"
    authoritative = root / "record-final"
    stale = root / "record-development"
    authoritative.mkdir(parents=True)
    stale.mkdir(parents=True)
    (authoritative / "eval_record.json").write_text("final\n", encoding="utf-8")
    (stale / "eval_record.json").write_text("development\n", encoding="utf-8")

    manifest, path = subject._supersede_unbound_eval_packages(
        output=tmp_path,
        authoritative_record_id="record-final",
    )

    quarantined = (
        tmp_path / "superseded_apps_eval_packages/record-development"
    )
    assert authoritative.is_dir()
    assert not stale.exists()
    assert (quarantined / "eval_record.json").read_text(encoding="utf-8") == (
        "development\n"
    )
    assert manifest["status"] == "PASS"
    assert manifest["superseded_package_count"] == 1
    assert manifest["canonical_package_count"] == 1
    assert manifest["canonical_package_ids"] == ["record-final"]
    assert manifest["destructive_delete_performed"] is False
    assert manifest["packages_recoverable"] is True
    assert subject._semantic_digest_valid(
        json.loads(path.read_text(encoding="utf-8"))
    )

    replayed, _ = subject._supersede_unbound_eval_packages(
        output=tmp_path,
        authoritative_record_id="record-final",
    )
    assert replayed == manifest


def test_w2_rehomes_stale_package_that_reuses_authoritative_record_id(
    tmp_path: Path,
) -> None:
    canonical = (
        tmp_path
        / "apps_eval/apps_rg_current_resume_generation/record-stable"
    )
    stale = tmp_path / "superseded_apps_eval_packages/record-stable"
    canonical.mkdir(parents=True)
    stale.mkdir(parents=True)
    (canonical / "eval_record.json").write_text(
        "canonical\n",
        encoding="utf-8",
    )
    (stale / "eval_record.json").write_text(
        "historical-root-dependent-bytes\n",
        encoding="utf-8",
    )

    manifest, _ = subject._supersede_unbound_eval_packages(
        output=tmp_path,
        authoritative_record_id="record-stable",
    )

    assert canonical.is_dir()
    assert not stale.exists()
    assert manifest["canonical_package_ids"] == ["record-stable"]
    assert manifest["rehomed_identity_collision_count"] == 1
    collision = manifest["rehomed_identity_collisions"][0]
    assert collision["original_record_id"] == "record-stable"
    assert collision["storage_record_id"].startswith(
        "record-stable--stale-"
    )
    assert collision["disposition"] == (
        "PRESERVED_STALE_PACKAGE_WITH_AUTHORITATIVE_ID"
    )
    preserved = tmp_path / collision["artifact_ref"] / "eval_record.json"
    assert preserved.read_text(encoding="utf-8") == (
        "historical-root-dependent-bytes\n"
    )
    assert manifest["destructive_delete_performed"] is False
    assert manifest["packages_recoverable"] is True
