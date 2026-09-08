"""Wave 2 regressions for retired compatibility authority surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_legacy_full_scope_reports_observation_not_authorization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome
    from apps_rg.runtime.orchestration import canonical_dispatch as dispatch

    class _Result:
        run_id = "legacy-run"
        request_id = "legacy-request"
        x3_disposition = "X3D_ALLOW_FINISH"
        fault = ""
        terminal_r5 = False

    monkeypatch.setattr(
        dispatch,
        "build_raw_request_for_r4",
        lambda **_kwargs: {"jd_payload": {"title": "role"}, "resume_hash": "resume"},
    )
    monkeypatch.setattr(dispatch, "_default_artifact_dir", lambda _value: tmp_path)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **_kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch", generation_required=True
        ),
    )
    monkeypatch.setattr(
        dispatch, "run_integrated_single_action_spine", lambda **_kwargs: _Result()
    )
    monkeypatch.setattr(dispatch, "emit_integrated_run_bundle_index", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch, "_augment_integrated_manifest_with_apps_rg_docx", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dispatch, "_augment_r4_run_manifest_for_apps_rg_l2_fault", lambda *_args, **_kwargs: None)

    result = dispatch.run_canonical_full_resume_from_cli_primitives(
        target_company="Acme", target_role="Security Lead", jd="inline JD"
    )

    assert result["exit_status"] == "error"
    assert result["execution_status"] == "non_product_completed"
    assert result["outcome_authorized"] is False
    assert result["product_authorized"] is False
    assert result["pipeline_complete"] is False
    assert result["observed_exit_status"] == "success"
    assert result["fault"] == "NON_PRODUCT_COMPATIBILITY_NOT_AUTHORIZING"


def test_compatibility_brief_loader_never_uses_remote_url() -> None:
    from apps_rg.runtime.orchestration.canonical_dispatch import _read_optional_brief

    assert _read_optional_brief("http://127.0.0.1/internal-metadata") == ""


def test_pin_flag_is_rejected_before_section_execution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from apps_rg import __main__ as cli

    monkeypatch.setattr(cli, "_build_parser", lambda: _parser_with_pin())
    assert cli.main(["--pin"]) == 2
    assert "--pin is retired" in capsys.readouterr().err


def _parser_with_pin():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", action="store_true")
    parser.add_argument("--assemble-from-pinned", action="store_true")
    return parser
