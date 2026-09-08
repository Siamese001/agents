"""Public CLI coverage for the governed full Apps RG path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg import __main__ as cli
from apps_rg.runtime.bindings.l0_binding import (
    l0_route_apps_rg,
    reset_route_profiles_cache,
)
from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
    ROUTE_FAMILY_R3R4,
)
from apps_rg.runtime.spine_contracts import L1PlanContract


def test_zero_argument_cli_dispatches_the_governed_product_entry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    run_dir = tmp_path / "full-run"
    run_dir.mkdir()

    def fake_dispatch(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "artifact_dir": str(run_dir),
            "product_authorized": True,
            "pipeline_complete": True,
        }

    monkeypatch.setattr(
        cli,
        "run_canonical_apps_rg_from_cli_primitives",
        fake_dispatch,
    )
    monkeypatch.setattr(
        cli,
        "_inline_evaluations",
        lambda _result: {"status": "PASS"},
    )

    assert cli.main([]) == 0
    assert captured == {
        "target_company": cli.DEFAULT_TARGET_COMPANY,
        "target_role": cli.DEFAULT_TARGET_ROLE,
        "jd": cli._DEFAULT_JD_PATH.read_text(encoding="utf-8"),
        "job_description_text": cli._DEFAULT_JD_PATH.read_text(encoding="utf-8"),
        "source_resume_text": cli._DEFAULT_RESUME_PATH.read_text(encoding="utf-8"),
        "artifact_dir": "",
    }


def test_public_full_resume_route_is_active_outside_test_posture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production CLI full resume must not fall through to the simple route."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("APPS_RG_L0_TEST_POSTURE", raising=False)
    monkeypatch.delenv("APPS_RG_ENABLE_MANAGED_WORKFLOW_L0", raising=False)
    monkeypatch.setenv("APPS_RG_ROUTE_HMAC_SECRET", "test-route-signing-secret")
    reset_route_profiles_cache()

    route = l0_route_apps_rg(
        L1PlanContract(
            request_id="request-full-resume",
            run_id="run-full-resume",
            app_id="apps_rg",
            trace_id="trace-full-resume",
            grounding_required=True,
            apps_research_call_required=True,
            model_generation_required=True,
            task_spec={"generation_mode": "strategic_tailor"},
            query_spec={"jd_hash": "jd", "resume_hash": "resume"},
            support_expectation={"targeting": "required"},
            merge_required_hint=True,
        )
    )

    assert route.route_family == ROUTE_FAMILY_R3R4
    assert route.route_profile_ref.endswith("full_resume_managed::v1")
    assert route.allowed_next_stage == frozenset({"L3"})


def test_full_eval_requires_the_apps_eval_package_l6_and_e2e_ledger(
    tmp_path: Path,
) -> None:
    (tmp_path / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True}),
        encoding="utf-8",
    )
    (tmp_path / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}),
        encoding="utf-8",
    )
    (tmp_path / "x3_disposition_receipt.json").write_text(
        json.dumps({"disposition": "X3D_ALLOW_FINISH"}),
        encoding="utf-8",
    )
    eval_dir = tmp_path / "apps_eval" / "test_run"
    eval_dir.mkdir(parents=True)
    (eval_dir / "eval_record.json").write_text(
        json.dumps({"status": "PASS", "score": 1.0}),
        encoding="utf-8",
    )

    report = cli._evaluate_product_run(tmp_path)

    assert report["status"] == "PASS"
    assert report["pipeline_complete"] is True
    assert report["product_authorized"] is True
    assert report["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert report["completion_receipt_ref"] == "apps_rg_pipeline_completion_receipt.json"
    assert report["x3_receipt_ref"] == "x3_disposition_receipt.json"
    assert report["apps_eval_record_count"] == 1
    assert cli.main(["eval", "--run-dir", str(tmp_path)]) == 0


def test_full_eval_uses_sealed_ledger_state_and_the_referenced_eval_package(
    tmp_path: Path,
) -> None:
    """The eval reader finds nested eval records and supports fallback receipts."""
    eval_record = (
        tmp_path
        / "apps_eval"
        / "apps_rg_current_resume_generation"
        / "record-123"
        / "eval_record.json"
    )
    eval_record.parent.mkdir(parents=True)
    eval_record.write_text(
        json.dumps({"verdict": "PASS", "score": 0.95}),
        encoding="utf-8",
    )
    (tmp_path / "apps_rg_post_x3_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True}),
        encoding="utf-8",
    )
    (tmp_path / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}),
        encoding="utf-8",
    )
    (tmp_path / "apps_rg_whole_run_exit_review_packet.json").write_text(
        json.dumps({"disposition": "X3D_ALLOW_FINISH"}),
        encoding="utf-8",
    )

    report = cli._evaluate_product_run(tmp_path)

    assert report["status"] == "PASS"
    assert report["pipeline_complete"] is True
    assert report["product_authorized"] is True
    assert report["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert report["completion_receipt_ref"] == "apps_rg_post_x3_completion_receipt.json"
    assert report["x3_receipt_ref"] == "apps_rg_whole_run_exit_review_packet.json"
    assert report["apps_eval_record_count"] == 1


def test_cli_returns_nonzero_when_full_e2e_evaluation_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir = tmp_path / "incomplete"
    run_dir.mkdir()
    monkeypatch.setattr(
        cli,
        "run_canonical_apps_rg_from_cli_primitives",
        lambda **_kwargs: {
            "artifact_dir": str(run_dir),
            "product_authorized": True,
            "pipeline_complete": True,
        },
    )
    monkeypatch.setattr(
        cli,
        "_inline_evaluations",
        lambda _result: {"status": "FAIL", "apps_eval_records": []},
    )

    assert cli.main(["run"]) == 1
    captured = capsys.readouterr()
    assert captured.out.index("FULL_RESUME") < captured.out.index("EVALS")
    assert captured.out.index("EVALS") < captured.out.index("RUNTIME_DETAILS")
    assert "UNAVAILABLE:" in captured.out


def test_public_cli_uses_distinct_product_and_evaluation_exit_classes(
    tmp_path: Path,
) -> None:
    # Exit code 1 for blocked eval report
    assert cli.main(["eval", "--run-dir", str(tmp_path)]) == 1
    # Exit code 2 for invalid CLI action
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["invalid_action"])
    assert excinfo.value.code == 2


def test_zero_provider_eval_returns_execution_class_for_a_partial_run(
    tmp_path: Path,
) -> None:
    report = cli._evaluate_product_run(tmp_path)

    assert report["status"] == "BLOCKED"
    assert report["pipeline_complete"] is False
    assert report["product_authorized"] is False
    assert report["x3_disposition"] == ""
    assert report["apps_eval_record_count"] == 0
    assert cli.main(["eval", "--run-dir", str(tmp_path)]) == 1


def test_public_cli_show_action_reads_stored_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "FINAL_RESUME_OUTPUT.txt").write_text("Senior Systems Engineer", encoding="utf-8")
    assert cli.main(["show", "--run-dir", str(tmp_path), "--artifact", "resume"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Senior Systems Engineer"

    # Evaluation inspection via show
    (tmp_path / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True}),
        encoding="utf-8",
    )
    assert cli.main(["show", "--run-dir", str(tmp_path), "--artifact", "evaluation"]) == 0
    eval_out = capsys.readouterr().out
    eval_json = json.loads(eval_out)
    assert eval_json["schema_version"] == "apps_rg.public_cli_product_evaluation.v1"
