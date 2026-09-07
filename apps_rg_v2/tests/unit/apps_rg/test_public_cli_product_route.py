"""The public command must dispatch the governed whole-resume product route."""
from __future__ import annotations

import json
from pathlib import Path

from apps_rg import __main__ as cli
from apps_rg.runtime.bindings.l0_binding import (
    l0_route_apps_rg,
    reset_route_profiles_cache,
)
from apps_rg.runtime.spine_contracts import L1PlanContract


def _write_completed_product_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "FINAL_RESUME_OUTPUT.txt").write_text("# Final resume\n", encoding="utf-8")
    (run_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True}), encoding="utf-8"
    )
    (run_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}), encoding="utf-8"
    )
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"x3_code": "X3D_ALLOW_FINISH"}), encoding="utf-8"
    )
    eval_dir = run_dir / "apps_eval" / "current"
    eval_dir.mkdir(parents=True)
    (eval_dir / "eval_record.json").write_text(
        json.dumps({"status": "PASS", "evaluation_id": "test-eval"}), encoding="utf-8"
    )


def _write_current_layout_product_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "FINAL_RESUME_OUTPUT.txt").write_text("# Final resume\n", encoding="utf-8")
    (run_dir / "apps_rg_post_x3_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True}), encoding="utf-8"
    )
    (run_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}), encoding="utf-8"
    )
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"payload": {"x3_disposition": "X3D_ALLOW_FINISH"}}),
        encoding="utf-8",
    )
    (run_dir / "apps_rg_whole_run_exit_review_packet.json").write_text(
        json.dumps({"x3_disposition": "X3D_ALLOW_FINISH"}), encoding="utf-8"
    )
    eval_dir = run_dir / "apps_eval" / "current"
    eval_dir.mkdir(parents=True)
    (eval_dir / "eval_record.json").write_text(
        json.dumps({"status": "PASS", "evaluation_id": "test-eval"}), encoding="utf-8"
    )


def test_run_uses_governed_product_route_and_prints_required_inline_outputs(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    run_dir = tmp_path / "governed_product_run"
    _write_completed_product_run(run_dir)
    received: dict[str, object] = {}

    def fake_product(**kwargs: object) -> dict[str, object]:
        received.update(kwargs)
        return {
            "exit_status": "success",
            "outcome_authorized": True,
            "artifact_dir": str(run_dir),
        }

    monkeypatch.setattr(cli, "run_canonical_apps_rg_from_cli_primitives", fake_product)

    assert cli.main(["run"]) == 0

    assert "Manager of Applied AI Architecture" in str(received["target_role"])
    assert "Manager of Applied AI Architecture" in str(received["job_description_text"])
    assert '"facts"' in str(received["source_resume_text"])
    out = capsys.readouterr().out
    assert "FULL_RESUME" in out
    assert "EVALS" in out
    assert "RUNTIME_DETAILS" in out
    assert "apps_eval_record_count" in out


def test_product_default_baseline_resolves_inside_the_package_tree() -> None:
    from apps_rg.runtime.product_entry import _baseline_ref

    resolved = _baseline_ref(Path(__file__).resolve().parents[3])

    assert resolved.is_file()
    assert resolved.parts[-5:] == (
        "src",
        "apps_rg",
        "config",
        "e2e_baselines",
        "anthropic_partnership.v1.json",
    )


def test_production_full_resume_route_is_managed_without_activation_flag(
    monkeypatch,
) -> None:
    monkeypatch.delenv("APPS_RG_ENABLE_MANAGED_WORKFLOW_L0", raising=False)
    monkeypatch.delenv("APPS_RG_MANAGED_WORKFLOW_TEST_ENABLED", raising=False)
    reset_route_profiles_cache()
    plan = L1PlanContract(
        request_id="req-production-route",
        run_id="run-production-route",
        app_id="apps_rg",
        trace_id="trace-production-route",
        grounding_required=True,
        merge_required_hint=True,
        task_spec={"generation_mode": "strategic_tailor"},
        query_spec={"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        support_expectation={"provenance_required": True},
    )

    route = l0_route_apps_rg(plan)

    assert route.route_family == "R3R4_MANAGED_WORKFLOW"
    assert route.execution_form == "MANAGED_WORKFLOW"


def test_eval_and_show_read_governed_product_artifacts(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "governed_product_run"
    _write_completed_product_run(run_dir)

    assert cli.main(["eval", "--run-dir", str(run_dir)]) == 0
    assert '"status": "PASS"' in capsys.readouterr().out

    assert cli.main(["show", "--run-dir", str(run_dir), "--artifact", "resume"]) == 0
    assert capsys.readouterr().out == "# Final resume\n"


def test_public_cli_evaluation_reads_current_post_x3_artifact_layout(tmp_path: Path) -> None:
    run_dir = tmp_path / "current_product_run"
    _write_current_layout_product_run(run_dir)

    report = cli._evaluate_product_run(run_dir)

    assert report["status"] == "PASS"
    assert report["completion_receipt_ref"] == "apps_rg_post_x3_completion_receipt.json"
    assert report["x3_receipt_ref"] == "x3_disposition_receipt.json"
    assert report["x3_disposition"] == "X3D_ALLOW_FINISH"


def test_run_accepts_current_product_receipts_with_advisory_l6_gap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "current_product_run"
    _write_current_layout_product_run(run_dir)
    monkeypatch.setattr(
        cli,
        "run_canonical_apps_rg_from_cli_primitives",
        lambda **kwargs: {
            "exit_status": "success",
            "outcome_authorized": True,
            "artifact_dir": str(run_dir),
        },
    )

    result = cli._run_product_from_cli(
        cli._build_parser().parse_args(["run"])
    )

    assert result["status"] == "SUCCESS"
    assert result["outcome_label"] == "GOVERNED_PRODUCT_AUTHORIZED"


def test_run_uses_final_product_receipts_when_dispatch_keeps_an_earlier_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "current_product_run"
    _write_current_layout_product_run(run_dir)
    monkeypatch.setattr(
        cli,
        "run_canonical_apps_rg_from_cli_primitives",
        lambda **kwargs: {
            "exit_status": "error",
            "outcome_authorized": False,
            "artifact_dir": str(run_dir),
        },
    )

    result = cli._run_product_from_cli(cli._build_parser().parse_args(["run"]))

    assert result["status"] == "SUCCESS"
    assert result["outcome_authorized"] is True
    assert result["canonical_exit_status"] == "error"
    assert result["canonical_outcome_authorized"] is False
    assert result["authority_source"] == "post_x3_completion_and_apps_eval"
