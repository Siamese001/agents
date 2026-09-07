"""Focused Anthropic Partnership fixture E2E with no LLM/provider calls."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps_eval.adapters.apps_rg import (
    build_source_artifact_manifest,
    normalize_anthropic_deterministic_fixture_snapshot,
    source_artifact_manifest_digest,
)
from apps_eval.coverage import build_apps_rg_microstep_evaluation
from apps_eval.runner.core import run_anthropic_deterministic_fixture_eval
from apps_rg.evals.anthropic_deterministic_fixture import (
    FIXTURE_EVAL_PROFILE_ID,
    FIXTURE_EVIDENCE_CLASS,
    emit_deterministic_fixture_l2_artifacts,
    produce_anthropic_deterministic_handoff,
    sha256_bytes,
)
from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff


_TARGET_COMPANY = "Anthropic"
_TARGET_ROLE = "Manager of Applied AI Architecture, Partnerships"
_REQUEST_ID = "req-anthropic-deterministic-fixture-001"
_RUN_ID = "00000000-0000-0000-0000-000000000901"
_TRACE_ID = "00000000-0000-0000-0000-000000000902"
_CHILD_RUN_ID = "anthropic-fixture-child-001"
_TENANT_ID = "default"
_FIXTURE_SECRET = "pytest-anthropic-deterministic-fixture-secret"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fixture_handoff(
    *,
    run_root: Path,
    jd_path: Path,
) -> dict[str, object]:
    repo = _repo_root()
    return produce_anthropic_deterministic_handoff(
        artifact_dir=run_root,
        jd_ref=str(jd_path),
        parent_run_id=_RUN_ID,
        child_run_id=_CHILD_RUN_ID,
        request_id=_REQUEST_ID,
        trace_root=_TRACE_ID,
        tenant_id=_TENANT_ID,
        target_company=_TARGET_COMPANY,
        target_role=_TARGET_ROLE,
        policy_hash=sha256_bytes(
            (repo / "config/certification/apps_research_rg_e2e_authority_contract.v1.json").read_bytes()
        ),
        blueprint_hash=sha256_bytes(
            (repo / "src/apps_research/config/domain_contract/runtime_customization_package.company_brief.v1.json").read_bytes()
        ),
        secret=_FIXTURE_SECRET,
    )


def test_deterministic_fixture_handoff_is_rejected_outside_test_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    jd_path = _repo_root() / "src/apps_rg/config/targeting/jd_anthropic_partnerships_2026.json"
    handoff = _fixture_handoff(run_root=tmp_path, jd_path=jd_path)
    monkeypatch.setenv("APPS_RG_DETERMINISTIC_FIXTURE_HMAC_SECRET", _FIXTURE_SECRET)
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)

    validation = validate_apps_research_handoff(
        brief_ref=str(handoff["briefing_path"]),
        jd_ref=str(jd_path),
        require_observed=True,
    )

    assert validation.observed is True
    assert validation.valid is False
    assert validation.reason == "test_fixture_handoff_not_allowed_outside_test_harness"


def test_static_anthropic_brief_is_not_a_fixture_handoff() -> None:
    static_brief = _repo_root() / "tests/fixtures/apps_rg/brief_anthropic_partnerships_2026.json"
    validation = validate_apps_research_handoff(
        brief_ref=str(static_brief),
        jd_ref=str(_repo_root() / "src/apps_rg/config/targeting/jd_anthropic_partnerships_2026.json"),
        require_observed=True,
    )
    assert validation.observed is False
    assert validation.valid is False
    assert validation.reason == "missing_apps_research_handoff_v2"


def test_anthropic_partnership_fixture_e2e_runs_real_u0_l1_l0_and_fixture_eval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Run the real ingress/U0/L1/L0 sequence and replace L2 only.

    The deliberately faulted L2 stub proves this is not a product success path;
    the isolated Apps Eval profile then evaluates the exact fixture evidence.
    """

    from apps_rg.cache.whole_run_entrypoint_preflight import WholeRunCachePreflightOutcome
    from apps_rg.runtime.orchestration import r3r4_whole_run_orchestration as orch

    run_root = tmp_path / "anthropic_fixture_run"
    jd_path = _repo_root() / "src/apps_rg/config/targeting/jd_anthropic_partnerships_2026.json"
    monkeypatch.setenv("APPS_RG_DETERMINISTIC_FIXTURE_HMAC_SECRET", _FIXTURE_SECRET)
    monkeypatch.setenv("APPS_RG_L1_ALLOW_EMPTY_PROFILE_DIGEST", "1")
    monkeypatch.delenv("APPS_RG_MOCK_RESEARCH", raising=False)
    handoff = _fixture_handoff(run_root=run_root, jd_path=jd_path)

    original_envelope = orch._build_cli_ingress_envelope

    def _fixed_envelope(**kwargs: object) -> SimpleNamespace:
        envelope = original_envelope(**kwargs)
        return SimpleNamespace(
            **{
                **vars(envelope),
                "request_id": _REQUEST_ID,
                "run_id": _RUN_ID,
                "trace_id": _TRACE_ID,
                "tenant_id": _TENANT_ID,
            }
        )

    seam_calls: list[dict[str, object]] = []

    class _FixtureL2Result:
        run_id = _RUN_ID
        request_id = _REQUEST_ID
        x3_disposition = "TEST_FIXTURE_ONLY"
        fault = "TEST_FIXTURE_L2_SEAM_REPLACED"
        terminal_r5 = False
        execution_witness = {"c0": {"status": "TEST_FIXTURE_ONLY"}}
        l2_result = None

    def _fixture_l2_seam(**kwargs: object) -> _FixtureL2Result:
        seam_calls.append(dict(kwargs))
        artifact_dir = Path(str(kwargs["artifact_dir"]))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "r4_run_manifest.json").write_text(
            json.dumps(
                {
                    "chain_kind": "R4_SINGLE_ACTION",
                    "route_family": "R4_SINGLE_ACTION",
                    "fixture_only": True,
                }
            ),
            encoding="utf-8",
        )
        return _FixtureL2Result()

    def _unexpected_research_or_network(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("fixture E2E attempted research/provider/network access")

    monkeypatch.setattr(orch, "_build_cli_ingress_envelope", _fixed_envelope)
    monkeypatch.setattr(orch, "_research_bridge", _unexpected_research_or_network)
    monkeypatch.setattr(orch, "run_integrated_single_action_spine", _fixture_l2_seam)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.run_whole_run_cache_preflight",
        lambda **kwargs: WholeRunCachePreflightOutcome(
            entrypoint="canonical_dispatch",
            generation_required=True,
        ),
    )
    monkeypatch.setattr(orch, "emit_integrated_run_bundle_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps_rg.cache.whole_run_entrypoint_preflight.maybe_ingest_r1b_post_exit",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_whole_run_cache_preflight_artifact",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "apps_rg.cache.cache_preflight_evidence.write_cache_miss_receipt",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(socket, "create_connection", _unexpected_research_or_network)
    monkeypatch.setattr(socket.socket, "connect", _unexpected_research_or_network)

    result = orch.run_whole_run_with_route_governance(
        target_company=_TARGET_COMPANY,
        target_role=_TARGET_ROLE,
        jd=str(jd_path),
        job_description_ref=str(jd_path),
        job_description_text=jd_path.read_text(encoding="utf-8"),
        manual_brief=str(handoff["briefing_path"]),
        source_resume_text="Applied AI architecture and partnerships leader.",
        generation_mode="strategic_tailor",
        artifact_dir=str(run_root),
        auto_research_internal=True,
        require_fresh_preflight=False,
    )

    assert len(seam_calls) == 1
    assert result["product_authorized"] is False
    assert result["pipeline_complete"] is False
    assert result["fault"] == "TEST_FIXTURE_L2_SEAM_REPLACED"
    assert result["research_delegation_executed"] is False
    for name in ("u0_receipt.json", "l1_plan_contract.json", "route_contract.json"):
        payload = json.loads((run_root / name).read_text(encoding="utf-8"))
        assert payload["status"] == "PASS"
        assert payload["identity"]["parent_run_id"] == _RUN_ID
        assert payload["identity"]["child_run_id"] == _CHILD_RUN_ID

    emit_deterministic_fixture_l2_artifacts(
        artifact_dir=run_root,
        identity=handoff["identity"],
        upstream_fault=str(result["fault"]),
    )
    snapshot = normalize_anthropic_deterministic_fixture_snapshot(
        scenario_id="anthropic_deterministic_fixture",
        artifact_dir=run_root,
    )
    source_before = source_artifact_manifest_digest(
        build_source_artifact_manifest(run_root)
    )
    record = run_anthropic_deterministic_fixture_eval(
        snapshot,
        out_dir=str(tmp_path / "fixture_eval"),
    )
    source_after = source_artifact_manifest_digest(
        build_source_artifact_manifest(run_root)
    )

    assert source_after == source_before
    assert record.contract_profile_id == FIXTURE_EVAL_PROFILE_ID
    assert record.evidence_class == FIXTURE_EVIDENCE_CLASS
    assert record.product_eligible is False
    assert record.scorecard.verdict == "pass"
    assert record.scorecard.coverage_summary["coverage_complete"] is True
    assert record.scorecard.coverage_summary["release_blocked"] is False
    assert all(
        row["contract_profile_id"] == FIXTURE_EVAL_PROFILE_ID
        for row in record.scorecard.scorecard_rows
    )
    for role in ("eval_record", "l6_handoff", "l6_shadow_bridge"):
        assert Path(record.artifact_paths[role]).is_file()
    package_seal = json.loads(
        Path(record.artifact_paths["eval_record"]).with_name(
            "apps_rg_eval_package_seal.json"
        ).read_text(encoding="utf-8")
    )
    assert package_seal["contract_profile_id"] == FIXTURE_EVAL_PROFILE_ID
    assert package_seal["evidence_class"] == FIXTURE_EVIDENCE_CLASS
    assert package_seal["product_eligible"] is False
    l6_handoff = json.loads(
        Path(record.artifact_paths["l6_handoff"]).read_text(encoding="utf-8")
    )
    assert l6_handoff["contract_profile_id"] == FIXTURE_EVAL_PROFILE_ID
    assert l6_handoff["evidence_class"] == FIXTURE_EVIDENCE_CLASS
    assert l6_handoff["product_eligible"] is False
    bridge = json.loads(
        Path(record.artifact_paths["l6_shadow_bridge"]).read_text(encoding="utf-8")
    )
    assert bridge["contract_profile_id"] == FIXTURE_EVAL_PROFILE_ID
    assert bridge["evidence_class"] == FIXTURE_EVIDENCE_CLASS
    assert bridge["product_eligible"] is False
    assert bridge["current_run_mutated"] is False

    product_profile = build_apps_rg_microstep_evaluation(
        suite_id="apps_rg.dev.resume_generation",
        scenario_id=snapshot.scenario_id,
        snapshot=snapshot,
        run_id="product-profile-isolation-check",
        created_at="1970-01-01T00:00:00Z",
    )
    assert product_profile["coverage_summary"].release_blocked is True
