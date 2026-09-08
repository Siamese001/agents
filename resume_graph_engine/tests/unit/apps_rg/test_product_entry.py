from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _ensure_runtime_boundary_policy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "apps_rg.runtime.runtime_boundary.configure_apps_rg_runtime_boundary",
        lambda repo_root=None: SimpleNamespace(
            policy_sha="test_policy_sha",
            environment_paths={},
        ),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.runtime_boundary.write_apps_rg_runtime_boundary_receipt",
        lambda art, boundary: art / "apps_rg_runtime_boundary_receipt.json",
    )


def _allow_local_runtime_independence(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
) -> None:
    from apps_rg.runtime import standalone_dependency_posture

    monkeypatch.setattr(
        standalone_dependency_posture,
        "verify_app_runtime_independence",
        lambda **kwargs: {"status": "APP_RUNTIME_INDEPENDENT"},
    )
    monkeypatch.setattr(
        standalone_dependency_posture,
        "write_app_runtime_independence_receipt",
        lambda **kwargs: run_dir / "runtime_independence_receipt.json",
    )


def test_product_entry_default_baseline_uses_the_source_package_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    monkeypatch.delenv("APPS_RG_E2E_BASELINE_REF", raising=False)
    expected = (
        tmp_path
        / "src"
        / "apps_rg"
        / "config"
        / "e2e_baselines"
        / "anthropic_partnership.v1.json"
    )

    assert product_entry._baseline_ref(tmp_path) == expected


def test_product_entry_mints_preflight_before_whole_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    run_dir = tmp_path / "full_resume_product"
    calls: list[str] = []
    monkeypatch.delenv("APPS_RG_WHOLE_RUN_ENVELOPE", raising=False)

    monkeypatch.setattr(product_entry, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        product_entry,
        "allocate_product_full_resume_artifact_dir",
        lambda repo, explicit: run_dir,
    )
    _allow_local_runtime_independence(monkeypatch, run_dir)

    def _preflight(**kwargs: object) -> SimpleNamespace:
        calls.append("preflight")
        (run_dir / "e2e_preflight_continuation_receipt.json").write_text(
            "{}\n", encoding="utf-8"
        )
        return SimpleNamespace(passed=True, result={}, receipt={}, bootstrap_receipt={})

    def _whole_run(**kwargs: object) -> dict[str, object]:
        calls.append("whole_run")
        assert os.environ["APPS_RG_WHOLE_RUN_ENVELOPE"] == "1"
        assert kwargs["artifact_dir"] == str(run_dir)
        assert kwargs["require_fresh_preflight"] is True
        assert str(kwargs["preflight_continuation_ref"]).endswith(
            "e2e_preflight_continuation_receipt.json"
        )
        assert kwargs["job_description_ref"] == ""
        assert kwargs["source_resume_text"] == "inline resume"
        assert kwargs["validated_input_bundle_digest"]
        assert Path(str(kwargs["manual_brief"])).is_file()
        return {"product_authorized": False, "pipeline_complete": False}

    monkeypatch.setattr(
        "apps_rg.runtime.e2e_preflight.run_fresh_e2e_preflight", _preflight
    )
    monkeypatch.setattr(
        "apps_rg.runtime.orchestration.r3r4_whole_run_orchestration."
        "run_whole_run_with_route_governance",
        _whole_run,
    )

    result = product_entry.run_product_whole_run_from_primitives(
        target_company="Anthropic",
        target_role="Manager",
        source_resume_text="inline resume",
        job_description_text="inline JD",
        manual_brief="inline brief",
    )

    assert calls == ["preflight", "whole_run"]
    assert result["authority_contract_id"] == "apps_research_rg_e2e_authority"
    assert Path(str(result["validated_input_bundle_ref"])).is_file()
    assert "APPS_RG_WHOLE_RUN_ENVELOPE" not in os.environ


def test_product_entry_materializes_owned_defaults_before_u0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    run_dir = tmp_path / "full_resume_defaults"
    captured: dict[str, object] = {}
    monkeypatch.setattr(product_entry, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        product_entry,
        "allocate_product_full_resume_artifact_dir",
        lambda repo, explicit: run_dir,
    )
    _allow_local_runtime_independence(monkeypatch, run_dir)
    monkeypatch.setattr(
        product_entry,
        "_canonical_anthropic_jd_text",
        lambda: "owned Anthropic JD",
    )
    monkeypatch.setattr(
        product_entry,
        "_canonical_base_resume_text",
        lambda: "owned base resume",
    )
    monkeypatch.setattr(
        "apps_rg.runtime.e2e_preflight.run_fresh_e2e_preflight",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            result={},
            receipt={},
            bootstrap_receipt={},
        ),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.orchestration.r3r4_whole_run_orchestration."
        "run_whole_run_with_route_governance",
        lambda **kwargs: captured.update(kwargs) or {},
    )

    product_entry.run_product_whole_run_from_primitives(
        target_company="Anthropic",
        target_role="Manager",
    )

    assert captured["job_description_text"] == "owned Anthropic JD"
    assert captured["source_resume_text"] == "owned base resume"


def test_product_entry_restores_prior_envelope_after_orchestrator_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    run_dir = tmp_path / "full_resume_error"
    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "prior-value")
    monkeypatch.setattr(product_entry, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        product_entry,
        "allocate_product_full_resume_artifact_dir",
        lambda repo, explicit: run_dir,
    )
    _allow_local_runtime_independence(monkeypatch, run_dir)
    monkeypatch.setattr(
        "apps_rg.runtime.e2e_preflight.run_fresh_e2e_preflight",
        lambda **kwargs: SimpleNamespace(
            passed=True,
            result={},
            receipt={},
            bootstrap_receipt={},
        ),
    )

    def _fail_whole_run(**kwargs: object) -> dict[str, object]:
        assert os.environ["APPS_RG_WHOLE_RUN_ENVELOPE"] == "1"
        raise RuntimeError("whole-run failed")

    monkeypatch.setattr(
        "apps_rg.runtime.orchestration.r3r4_whole_run_orchestration."
        "run_whole_run_with_route_governance",
        _fail_whole_run,
    )

    with pytest.raises(RuntimeError, match="whole-run failed"):
        product_entry.run_product_whole_run_from_primitives(
            target_company="Anthropic",
            target_role="Manager",
        )

    assert os.environ["APPS_RG_WHOLE_RUN_ENVELOPE"] == "prior-value"


def test_product_entry_stops_when_preflight_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    run_dir = tmp_path / "full_resume_blocked"
    monkeypatch.setattr(product_entry, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        product_entry,
        "allocate_product_full_resume_artifact_dir",
        lambda repo, explicit: run_dir,
    )
    _allow_local_runtime_independence(monkeypatch, run_dir)
    monkeypatch.setattr(
        "apps_rg.runtime.e2e_preflight.run_fresh_e2e_preflight",
        lambda **kwargs: SimpleNamespace(
            passed=False,
            result={"exit_status": "error", "fault": "PREFLIGHT_BLOCKED"},
            receipt={"status": "BLOCKED"},
            bootstrap_receipt={},
        ),
    )

    result = product_entry.run_product_whole_run_from_primitives(
        target_company="Anthropic",
        target_role="Manager",
    )

    assert result["fault"] == "PREFLIGHT_BLOCKED"
    assert result["product_authorized"] is False
    assert result["pipeline_complete"] is False


def test_product_entry_blocks_before_preflight_without_local_runtime_independence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry
    from apps_rg.runtime import standalone_dependency_posture

    run_dir = tmp_path / "full_resume_dependency_blocked"
    monkeypatch.setattr(product_entry, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        product_entry,
        "allocate_product_full_resume_artifact_dir",
        lambda repo, explicit: run_dir,
    )
    monkeypatch.setattr(
        standalone_dependency_posture,
        "verify_app_runtime_independence",
        lambda **kwargs: {"status": "BLOCKED_LOCAL_RUNTIME_UNAVAILABLE"},
    )
    monkeypatch.setattr(
        standalone_dependency_posture,
        "write_app_runtime_independence_receipt",
        lambda **kwargs: run_dir / "runtime_independence_receipt.json",
    )
    monkeypatch.setattr(
        "apps_rg.runtime.e2e_preflight.run_fresh_e2e_preflight",
        lambda **kwargs: pytest.fail("preflight must not run without local runtime proof"),
    )

    result = product_entry.run_product_whole_run_from_primitives(
        target_company="Anthropic",
        target_role="Manager",
    )

    assert result["fault"] == "APP_RUNTIME_INDEPENDENCE_UNAVAILABLE"
    assert result["standalone_runtime_dependency_status"] == "BLOCKED_LOCAL_RUNTIME_UNAVAILABLE"
    assert result["product_authorized"] is False


def test_product_entry_rejects_non_fresh_explicit_artifact_dir(
    tmp_path: Path,
) -> None:
    from apps_rg.runtime import product_entry

    run_dir = tmp_path / "existing"
    run_dir.mkdir()
    (run_dir / "stale.json").write_text("{}\n", encoding="utf-8")

    result = product_entry.run_product_whole_run_from_primitives(
        target_company="Anthropic",
        target_role="Manager",
        artifact_dir=str(run_dir),
    )

    assert result["fault"] == "PRODUCT_ARTIFACT_DIR_UNSAFE"
    assert result["product_authorized"] is False


def test_canonical_dispatch_routes_only_full_scope_to_product_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_rg.runtime.orchestration import canonical_dispatch

    monkeypatch.setattr(
        "apps_rg.runtime.product_entry.run_product_whole_run_from_primitives",
        lambda **kwargs: {"route": "product"},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.spine.apps_rg_spine_run.run_apps_rg_spine",
        lambda **kwargs: {"route": "section", "scope": kwargs["scope"]},
    )

    product = canonical_dispatch.run_canonical_apps_rg_from_cli_primitives(
        target_company="Anthropic",
        target_role="Manager",
    )
    section = canonical_dispatch.run_canonical_apps_rg_from_cli_primitives(
        target_company="Anthropic",
        target_role="Manager",
        section="headline",
    )

    assert product == {"route": "product"}
    assert section == {"route": "section", "scope": "section"}
