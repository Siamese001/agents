"""W7.1 — patch-run mode: re-dispatch only failed lanes of an existing integrated run.

Synthetic run-dir fixtures only — no live provider calls. Covers auto-selection,
dependency ordering, input re-derivation, refusal paths, latest-dir determinism,
receipt schema, and --dry-run.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from apps_rg.repository_layout import resolve_repository_path
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.orchestration import patch_run as pr
from apps_rg.runtime.orchestration.patch_run import (
    PATCH_RUN_RECEIPT_ARTIFACT,
    PatchRunInputError,
    build_patch_plan,
    classify_all_lane_states,
    derive_patch_targeting,
    execute_patch_run,
    latest_lane_run_dir_any,
    parse_cli_command_flags,
    select_patch_lanes,
)


def test_patch_run_input_error_has_cli_config_exit_code() -> None:
    assert pr.PatchRunInputError.exit_code == 2

_GREEN_DEFAULT = tuple(
    lane
    for lane in GENERATED_LANES
    if lane not in ("headline", "executive_summary", "ibm_bullets", "ibm_narrative")
)


@pytest.fixture(autouse=True)
def _test_harness_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_repo(tmp_path: Path) -> Path:
    """Minimal standalone repo with the package marker required by repository_root."""
    repo = tmp_path / "repo"
    package = repo / "src" / "apps_rg"
    (package / "resume" / "base").mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    cfg_dir = repo / "config" / "profiles" / "apps_rg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "pipeline_defaults.yaml").write_text(
        'schema_version: "1.0"\napp_id: apps_rg\nprofile_type: pipeline_defaults\n'
        "pipeline_config:\n  default_timeout_seconds: 900\n"
        "namespace_defaults:\n"
        '  artifact_namespace: "artifacts/apps_rg/runs"\n'
        '  log_namespace: "apps_rg/pipeline_logs"\n',
        encoding="utf-8",
    )
    return repo


def _seed_jd_and_brief(repo: Path) -> tuple[Path, Path]:
    jd = resolve_repository_path(repo, "apps_rg/config/targeting/aig_jd.txt")
    jd.parent.mkdir(parents=True, exist_ok=True)
    jd.write_text("VP Global Head of Agentic AI Solutions JD body", encoding="utf-8")
    brief = resolve_repository_path(repo, "apps_rg/config/targeting/aig_brief.md")
    brief.write_text("AIG targeting brief", encoding="utf-8")
    return jd, brief


def _seed_lane_run(
    repo: Path,
    run_dir: Path,
    lane: str,
    run_id: str,
    *,
    x3_code: str = "X3_ALLOW",
    product_quality: str = "PASS",
    successful_pointer: bool = True,
    command: str | None = None,
) -> Path:
    lane_root = run_dir / "modular_r4" / "sections" / lane
    rd = lane_root / "real" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    _write_json(
        rd / "l2_output.json",
        {
            "section_id": lane,
            "run_id": run_id,
            "runtime_generation_status": "REAL_LLM",
            "product_quality_status": product_quality,
        },
    )
    _write_json(rd / "x3_disposition.json", {"x3_code": x3_code})
    _write_json(
        rd / "x2_gate_outputs.json",
        {"x2_passed": 1, "x2_failed": 0, "total_x2_gates": 1, "failed_gates": []},
    )
    cmd = command if command is not None else (
        "C:\\repo\\apps_rg\\__main__.py --target-company AIG "
        "--target-role VP Global Head of Agentic AI Solutions --target-level VP "
        "--jd apps_rg/config/targeting/aig_jd.txt "
        "--manual-brief apps_rg/config/targeting/aig_brief.md "
        f"--artifact-dir {run_dir}"
    )
    _write_json(
        rd / "run_manifest.json",
        {
            "run_id": run_id,
            "section_id": lane,
            "provider_requested": "external_claude",
            "provider_attempted": True,
            "runtime_generation_status": "REAL_LLM",
            "command": cmd,
        },
    )
    _write_json(
        rd / "provider_request.json",
        {"provider_requested": "external_claude", "provider_attempted": True},
    )
    ptr = {
        "run_id": run_id,
        "run_dir": rd.relative_to(repo).as_posix(),
        "section_id": lane,
    }
    _write_json(lane_root / "latest_real_run.json", ptr)
    if successful_pointer:
        _write_json(lane_root / "latest_successful_real_run.json", ptr)
    return rd


def _seed_integrated_run(
    tmp_path: Path,
    *,
    green: tuple[str, ...] = _GREEN_DEFAULT,
    blocked: tuple[str, ...] = ("headline", "executive_summary", "ibm_bullets"),
    pre_run_blocked: dict[str, str] | None = None,
    with_ingress: bool = True,
) -> tuple[Path, Path]:
    """Synthetic integrated run dir mirroring the attempt4 shape (7 green / 3 blocked /
    1 upstream-blocked by default)."""
    repo = _seed_repo(tmp_path)
    _seed_jd_and_brief(repo)
    run_dir = repo / "artifacts" / "apps_rg" / "e2e_aig_verify" / "attempt_fixture"
    (run_dir / "modular_r4" / "sections").mkdir(parents=True, exist_ok=True)
    if with_ingress:
        _write_json(
            run_dir / "ingress_raw.json",
            {
                "target_company": "AIG",
                "target_role": "VP Global Head of Agentic AI Solutions",
                "generation_mode": "strategic_tailor",
                "manual_brief": "apps_rg/config/targeting/aig_brief.md",
                "auto_research_internal": True,
                "research_via": None,
            },
        )
    for lane in green:
        _seed_lane_run(repo, run_dir, lane, f"{lane}_20260610_120000")
    for lane in blocked:
        _seed_lane_run(
            repo,
            run_dir,
            lane,
            f"{lane}_20260610_120000",
            x3_code="X3_BLOCK",
        )
    for lane, blocker in (pre_run_blocked or {"ibm_narrative": "UPSTREAM_BULLETS_NOT_FINALIZED"}).items():
        _write_json(
            run_dir / "modular_r4" / "sections" / lane / "integrated_lane_pre_run_failure.json",
            {
                "schema_version": "integrated_lane_pre_run_failure_v1",
                "lane_id": lane,
                "status": "PRE_RUN_BLOCKED",
                "blocker": blocker,
                "dispatch_result": {"fault": "upstream_not_finalized"},
            },
        )
    return repo, run_dir


# --------------------------------------------------------------- command parsing


def test_parse_cli_command_flags_multiword_values() -> None:
    cmd = (
        "C:\\x\\__main__.py --target-company AIG "
        "--target-role VP Global Head of Agentic AI Solutions --target-level VP "
        "--jd apps_rg/config/targeting/aig_jd.txt --manual-brief b.md --artifact-dir d"
    )
    flags = parse_cli_command_flags(cmd)
    assert flags["--target-company"] == "AIG"
    assert flags["--target-role"] == "VP Global Head of Agentic AI Solutions"
    assert flags["--target-level"] == "VP"
    assert flags["--jd"] == "apps_rg/config/targeting/aig_jd.txt"


# --------------------------------------------------------------- targeting derivation


def test_derive_patch_targeting_from_persisted_artifacts(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    t = derive_patch_targeting(repo, run_dir)
    assert t.target_company == "AIG"
    assert t.target_role == "VP Global Head of Agentic AI Solutions"
    assert t.target_level == "VP"
    assert t.job_description_ref.endswith("aig_jd.txt")
    assert Path(t.job_description_ref).is_file()
    assert t.manual_brief.endswith("aig_brief.md")
    assert t.generation_mode == "strategic_tailor"
    assert t.sources["target_company"] == "ingress_raw.json"
    assert "command:--jd" in t.sources["job_description_ref"]


def test_derive_patch_targeting_from_pointer_command_without_real_dirs(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    sections_root = run_dir / "modular_r4" / "sections"
    lane_rd = latest_lane_run_dir_any(sections_root, "competencies")
    assert lane_rd is not None
    command = json.loads((lane_rd / "run_manifest.json").read_text(encoding="utf-8"))["command"]

    for lane in GENERATED_LANES:
        lane_root = sections_root / lane
        for pointer_name in ("latest_successful_real_run.json", "latest_real_run.json"):
            pointer_path = lane_root / pointer_name
            if not pointer_path.is_file():
                continue
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["command"] = command
            pointer["run_dir"] = f"artifacts/apps_rg/runtime_proofs/missing_{lane}"
            _write_json(pointer_path, pointer)
        real_root = lane_root / "real"
        if real_root.is_dir():
            shutil.rmtree(real_root)

    t = derive_patch_targeting(repo, run_dir)
    assert t.target_company == "AIG"
    assert t.target_role == "VP Global Head of Agentic AI Solutions"
    assert t.target_level == "VP"
    assert t.job_description_ref.endswith("aig_jd.txt")
    assert t.sources["job_description_ref"].endswith(
        "latest_successful_real_run.json:command:--jd"
    )


def test_derive_patch_targeting_preserves_existing_lane_briefing(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    sections_root = run_dir / "modular_r4" / "sections"
    existing_briefing = "Existing accepted lane briefing text"
    for lane in ("competencies", "unify_bullets"):
        lane_rd = latest_lane_run_dir_any(sections_root, lane)
        assert lane_rd is not None
        _write_json(lane_rd / "runtime_payload.json", {"briefing": existing_briefing})
        _write_json(
            lane_rd / "section_input_usage_ledger.json",
            {"input_refs": {"briefing_hash": "majority_hash"}},
        )

    t = derive_patch_targeting(repo, run_dir)
    assert t.manual_brief == existing_briefing
    assert t.sources["manual_brief"] == (
        "lane:runtime_payload.majority_briefing_hash:majority_hash"
    )


def test_derive_targeting_uses_root_u0_request_when_lane_metadata_lacks_jd(
    tmp_path: Path,
) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    sections_root = run_dir / "modular_r4" / "sections"
    for lane in GENERATED_LANES:
        lane_rd = latest_lane_run_dir_any(sections_root, lane)
        if lane_rd is None:
            continue
        manifest_path = lane_rd / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["command"] = ""
        _write_json(manifest_path, manifest)

    _write_json(
        run_dir / "apps_rg_u0_validated_request.json",
        {
            "payload": {
                "app_payload": {
                    "target_company": "AIG",
                    "target_role": "VP Global Head of Agentic AI Solutions",
                    "job_description_ref": "apps_rg/config/targeting/aig_jd.txt",
                    "briefing_artifact_ref": "apps_rg/config/targeting/aig_brief.md",
                }
            }
        },
    )

    t = derive_patch_targeting(repo, run_dir)
    assert t.job_description_ref.endswith("aig_jd.txt")
    assert t.sources["job_description_ref"] == (
        "root:apps_rg_u0_validated_request.json:app_payload"
    )


def test_derive_targeting_preserves_authorized_handoff_path_over_lane_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    sections_root = run_dir / "modular_r4" / "sections"
    for lane in ("competencies", "unify_bullets"):
        lane_rd = latest_lane_run_dir_any(sections_root, lane)
        assert lane_rd is not None
        _write_json(lane_rd / "runtime_payload.json", {"briefing": "lane briefing text"})
        _write_json(
            lane_rd / "section_input_usage_ledger.json",
            {"input_refs": {"briefing_hash": "majority_hash"}},
        )

    seen: dict[str, str] = {}

    def _authorized(**kwargs: str) -> bool:
        seen.update(kwargs)
        return True

    monkeypatch.setattr(pr, "_is_authorized_handoff_reference", _authorized)
    t = derive_patch_targeting(repo, run_dir)
    assert t.manual_brief.endswith("aig_brief.md")
    assert t.sources["manual_brief"] == "ingress_raw.json"
    assert seen["brief_ref"].endswith("aig_brief.md")


def test_derive_targeting_jd_text_fallback_when_jd_file_gone(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    resolve_repository_path(repo, "apps_rg/config/targeting/aig_jd.txt").unlink()
    # Persist an app_payload JD text on one executed lane.
    lane_rd = latest_lane_run_dir_any(run_dir / "modular_r4" / "sections", "competencies")
    assert lane_rd is not None
    _write_json(
        lane_rd / "validated_request.json",
        {
            "payload": {
                "app_payload": {
                    "target_company": "AIG",
                    "target_role": "VP Global Head of Agentic AI Solutions",
                    "job_description_text": "Inline JD body from validated_request",
                    "user_constraints": {"briefing_text": "inline brief"},
                }
            }
        },
    )
    t = derive_patch_targeting(repo, run_dir)
    assert t.job_description_ref == ""
    assert t.job_description_text == "Inline JD body from validated_request"
    assert t.sources["job_description_text"] == "lane:validated_request.app_payload"


def test_derive_targeting_refuses_when_inputs_missing(tmp_path: Path) -> None:
    repo = _seed_repo(tmp_path)
    run_dir = repo / "artifacts" / "apps_rg" / "e2e_aig_verify" / "attempt_empty"
    (run_dir / "modular_r4" / "sections").mkdir(parents=True, exist_ok=True)
    with pytest.raises(PatchRunInputError) as ei:
        derive_patch_targeting(repo, run_dir)
    msg = str(ei.value)
    assert "target_company" in msg
    assert "jd" in msg


# --------------------------------------------------------------- selection + ordering


def test_auto_selection_picks_exactly_non_authorized_lanes(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    states = classify_all_lane_states(repo, run_dir)
    for lane in _GREEN_DEFAULT:
        assert states[lane]["authorized"], (lane, states[lane])
        assert states[lane]["state"] == "AUTHORIZED:X3_ALLOW"
    for lane in ("headline", "executive_summary", "ibm_bullets"):
        assert not states[lane]["authorized"]
        assert states[lane]["state"] == "EXECUTED_X3_BLOCK"
    assert not states["ibm_narrative"]["authorized"]

    targets = select_patch_lanes(states)
    assert set(targets) == {"headline", "executive_summary", "ibm_bullets", "ibm_narrative"}


def test_banked_lane_requires_binding_to_current_frozen_allocation(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    digest = "a" * 64
    _write_json(
        run_dir
        / "modular_r4"
        / "resume_graph_allocation"
        / "resume_graph_allocation_plan.json",
        {"allocation_plan_digest": digest},
    )
    lane_dir = latest_lane_run_dir_any(
        run_dir / "modular_r4" / "sections", "competencies"
    )
    assert lane_dir is not None

    missing = pr.classify_lane_state(repo, run_dir, "competencies")
    assert missing["authorized"] is False
    assert missing["state"] == "STALE_WHOLE_RESUME_GRAPH_AUTHORITY"
    assert missing["reason"] == "frozen_graph_claim_binding_missing"

    _write_json(
        lane_dir / "graph_claim_bindings.json",
        {
            "active": True,
            "status": "PASS",
            "pass": True,
            "allocation_plan_digest": "b" * 64,
            "claim_count": 2,
            "bound_claim_count": 2,
        },
    )
    mismatched = pr.classify_lane_state(repo, run_dir, "competencies")
    assert mismatched["authorized"] is False
    assert "frozen_graph_allocation_digest_mismatch" in mismatched["reason"]

    _write_json(
        lane_dir / "graph_claim_bindings.json",
        {
            "active": True,
            "status": "PASS",
            "pass": True,
            "allocation_plan_digest": digest,
            "claim_count": 2,
            "bound_claim_count": 2,
        },
    )
    current = pr.classify_lane_state(repo, run_dir, "competencies")
    assert current["authorized"] is True
    assert current["state"] == "AUTHORIZED:X3_ALLOW"


def test_ordering_narrative_after_its_bullets_lane(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    plan = build_patch_plan(run_dir)
    targets = plan.target_lanes
    assert targets.index("ibm_bullets") < targets.index("ibm_narrative")
    # Canonical dependency order overall.
    assert targets == [lane for lane in GENERATED_LANES if lane in set(targets)]


def test_refuse_authorized_lane_without_force(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    states = classify_all_lane_states(repo, run_dir)
    with pytest.raises(PatchRunInputError) as ei:
        select_patch_lanes(states, sections_csv="competencies,headline")
    assert "competencies" in str(ei.value)
    assert "--force-lanes" in str(ei.value)

    targets = select_patch_lanes(
        states, sections_csv="competencies,headline", force_lanes_csv="competencies"
    )
    assert targets == ["competencies", "headline"]


def test_refuse_unknown_section_and_unknown_force_lane(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    states = classify_all_lane_states(repo, run_dir)
    with pytest.raises(PatchRunInputError):
        select_patch_lanes(states, sections_csv="not_a_lane")
    with pytest.raises(PatchRunInputError):
        select_patch_lanes(states, force_lanes_csv="not_a_lane")


# --------------------------------------------------------------- refusal paths


def test_build_plan_refuses_missing_run_dir(tmp_path: Path) -> None:
    with pytest.raises(PatchRunInputError) as ei:
        build_patch_plan(tmp_path / "nope")
    assert "does not exist" in str(ei.value)


def test_build_plan_refuses_non_integrated_dir(tmp_path: Path) -> None:
    d = tmp_path / "plain"
    d.mkdir()
    with pytest.raises(PatchRunInputError) as ei:
        build_patch_plan(d)
    assert "modular_r4/sections" in str(ei.value)


def test_patch_runtime_preflight_blocks_missing_signing_secret_before_dispatch(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(PatchRunInputError, match="missing APPS_RG_ROUTE_HMAC_SECRET"):
        pr._run_patch_runtime_preflight(run_dir, environ={})

    receipt = json.loads(
        (run_dir / pr.PATCH_RUN_PREFLIGHT_ARTIFACT).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "BLOCKED"
    assert receipt["dispatch_eligible"] is False
    assert receipt["route_signing_secret_present"] is False
    assert receipt["secret_material_recorded"] is False


def test_patch_runtime_preflight_records_presence_without_secret_material(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    secret = "never-write-this-secret"
    receipt = pr._run_patch_runtime_preflight(
        run_dir,
        environ={
            "APPS_RG_ROUTE_HMAC_SECRET": secret,
            "APPS_RG_ROUTE_HMAC_KEY_ID": "patch-session-key",
        },
    )

    raw = (run_dir / pr.PATCH_RUN_PREFLIGHT_ARTIFACT).read_text(encoding="utf-8")
    assert receipt["status"] == "PASS"
    assert receipt["route_signing_key_id_present"] is True
    assert secret not in raw


# --------------------------------------------------------------- latest-dir determinism


def test_latest_lane_run_dir_is_lexicographic_not_mtime(tmp_path: Path) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    sections_root = run_dir / "modular_r4" / "sections"
    older = _seed_lane_run(repo, run_dir, "headline", "headline_20260609_010101", x3_code="X3_BLOCK")
    newer = latest_lane_run_dir_any(sections_root, "headline")
    assert newer is not None
    assert newer.name == "headline_20260610_120000"
    # Touch the older dir last — selection must stay deterministic (name order).
    import os

    os.utime(older, None)
    again = latest_lane_run_dir_any(sections_root, "headline")
    assert again is not None and again.name == "headline_20260610_120000"


# --------------------------------------------------------------- dry-run


def test_dry_run_prints_plan_and_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    plan = build_patch_plan(run_dir)
    result = execute_patch_run(plan, dry_run=True)
    out = capsys.readouterr().out
    assert result["exit_code"] == 0
    assert "PATCH RUN PLAN" in out
    assert "DRY RUN" in out
    assert "ibm_bullets, ibm_narrative, executive_summary, headline" in out
    # Dry run executes nothing and writes no receipt.
    assert not (run_dir / PATCH_RUN_RECEIPT_ARTIFACT).is_file()


# --------------------------------------------------------------- execute (stubbed)


def _stub_dispatch_factory(repo: Path, run_dir: Path, calls: list[str]):
    def _stub(*, plan: Any, lane: str, lane_provider: str) -> dict[str, Any]:
        calls.append(lane)
        rd = _seed_lane_run(repo, run_dir, lane, f"{lane}_20260611_090000")
        return {
            "exit_status": "success",
            "x3_disposition": "X3_ALLOW",
            "artifact_dir": str(rd),
        }

    return _stub


def test_execute_patch_run_dispatch_order_receipt_and_exit_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    real_find_repo_root = pr.find_repo_root
    monkeypatch.setattr(
        pr,
        "find_repo_root",
        lambda start=None: repo if start is None else real_find_repo_root(start),
    )
    # Companion upstream acceptance: stubbed run dirs do not carry full bullet
    # finalization evidence — accept once the bullets lane has been re-dispatched.
    import apps_rg.runtime.validators.companion_bullet_finalization as cbf

    monkeypatch.setattr(
        cbf,
        "companion_accepted_in_modular_sections_root",
        lambda *a, **k: True,
    )
    _patch_embedding_preflight(monkeypatch, [])

    calls: list[str] = []
    plan = build_patch_plan(run_dir)
    prior_states = {lane: plan.lane_states[lane]["state"] for lane in GENERATED_LANES}

    def _stub_aggregate(plan_arg: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "decisive_status": "PASS",
            "failure_reason": "",
            "full_success_eligibility": {"eligible": True, "reasons": []},
        }

    result = execute_patch_run(
        plan,
        dispatch_fn=_stub_dispatch_factory(repo, run_dir, calls),
        aggregate_fn=_stub_aggregate,
    )

    # Dispatch order: bullets before its companion narrative; canonical order overall.
    assert calls == ["ibm_bullets", "ibm_narrative", "executive_summary", "headline"]

    assert result["exit_code"] == 0
    assert result["all_lanes_authorized"] is True

    receipt_path = run_dir / PATCH_RUN_RECEIPT_ARTIFACT
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for key in (
        "patched_lanes",
        "prior_states",
        "new_states",
        "lane_dir_chosen_per_lane",
        "decisive_status",
        "full_success_eligibility",
        "exit_code",
    ):
        assert key in receipt, key
    assert receipt["patched_lanes"] == ["ibm_bullets", "ibm_narrative", "executive_summary", "headline"]
    assert receipt["prior_states"] == prior_states
    assert receipt["prior_states"]["headline"] == "EXECUTED_X3_BLOCK"
    assert receipt["new_states"]["headline"] == "AUTHORIZED:X3_ALLOW"
    assert receipt["new_states"]["competencies"] == "AUTHORIZED:X3_ALLOW"
    assert receipt["lane_dir_chosen_per_lane"]["headline"].endswith("headline_20260611_090000")
    # Banked lane untouched: chosen dir is still the original green run dir.
    assert receipt["lane_dir_chosen_per_lane"]["competencies"].endswith(
        "competencies_20260610_120000"
    )


def test_execute_patch_run_upstream_still_blocked_narrative_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    real_find_repo_root = pr.find_repo_root
    monkeypatch.setattr(
        pr,
        "find_repo_root",
        lambda start=None: repo if start is None else real_find_repo_root(start),
    )
    import apps_rg.runtime.validators.companion_bullet_finalization as cbf

    monkeypatch.setattr(
        cbf,
        "companion_accepted_in_modular_sections_root",
        lambda *a, **k: False,
    )
    _patch_embedding_preflight(monkeypatch, [])

    calls: list[str] = []
    plan = build_patch_plan(run_dir)
    result = execute_patch_run(
        plan,
        dispatch_fn=_stub_dispatch_factory(repo, run_dir, calls),
        aggregate_fn=lambda plan_arg, **kw: {
            "decisive_status": "FAIL",
            "failure_reason": "fatal_lane_recipe_policy:ibm_narrative:UPSTREAM_BULLETS_NOT_FINALIZED",
            "full_success_eligibility": {"eligible": False, "reasons": ["x"]},
        },
    )
    # Narrative lane never dispatched — pre-run blocked again.
    assert "ibm_narrative" not in calls
    assert result["exit_code"] == 1
    receipt = json.loads((run_dir / PATCH_RUN_RECEIPT_ARTIFACT).read_text(encoding="utf-8"))
    assert receipt["lane_dispatch_results"]["ibm_narrative"]["fault"] == "upstream_not_finalized"
    pre = json.loads(
        (
            run_dir
            / "modular_r4"
            / "sections"
            / "ibm_narrative"
            / "integrated_lane_pre_run_failure.json"
        ).read_text(encoding="utf-8")
    )
    assert pre["blocker"] == "UPSTREAM_BULLETS_NOT_FINALIZED"


# --------------------------------------------------------------- targeting threading (live defect 2026-06-11)


def _patch_embedding_preflight(
    monkeypatch: pytest.MonkeyPatch, preflight_calls: list[tuple[str, Any]]
) -> None:
    """Capture the whole-run embedding env preflight instead of mutating process env."""
    import apps_rg.runtime.embedding_settings as emb

    monkeypatch.setattr(
        emb,
        "bootstrap_apps_rg_embedding_env",
        lambda repo_root=None: preflight_calls.append(("bootstrap", repo_root)) or {},
    )
    monkeypatch.setattr(
        emb,
        "apply_apps_rg_embedding_env_guards",
        lambda *a, **k: preflight_calls.append(("guards", k.get("chroma_persist_dir")))
        or object(),
    )
    monkeypatch.setattr(
        emb,
        "write_embedding_settings_receipt",
        lambda artifact_dir, settings: preflight_calls.append(("receipt", artifact_dir))
        or None,
    )


def test_patch_run_restores_persisted_whole_resume_graph_bindings(tmp_path: Path) -> None:
    from apps_rg.runtime.c0.resume_graph_allocation import (
        ALL_CLAIM_BEARING_SECTIONS,
        finalize_resume_graph_allocation_plan,
    )

    run_dir = tmp_path / "run"
    allocation_dir = run_dir / "modular_r4" / "resume_graph_allocation"
    plan = finalize_resume_graph_allocation_plan(
        {
            "schema_version": "resume_graph_allocation_plan_v1",
            "allocation_scope": "WHOLE_RESUME",
            "global_uniqueness_claimed": True,
            "assignments": [
                {
                    "section_id": section_id,
                    "claim_unit_id": f"{section_id}:claim-1",
                    "candidate_id": f"candidate-{index}",
                    "skill_id": f"skill-{index}",
                    "metric_outcome_id": f"metric-{index}",
                    "normalized_metric_signature": f"signature-{index}",
                    "counts_toward_global_uniqueness": True,
                }
                for index, section_id in enumerate(ALL_CLAIM_BEARING_SECTIONS)
            ],
            "candidate_decisions": [],
            "candidate_conservation_receipt": {"pass": True},
            "durable_graph_state_mutated": False,
        }
    )
    artifacts = {
        "resume_graph_allocation_plan.json": plan,
        "resume_graph_usage_ledger.json": {"allocation_plan_digest": plan["allocation_plan_digest"]},
        "section_final_graph_evidence_contracts.json": {"headline": {"pass": True}},
        "c03_section_graph_plans.json": {"headline": {"section_id": "headline"}},
    }
    for name, payload in artifacts.items():
        _write_json(allocation_dir / name, payload)
    bindings = pr._whole_resume_graph_env_for_patch(run_dir)

    assert Path(bindings["APPS_RG_RESUME_GRAPH_ALLOCATION_PLAN"]).name == (
        "resume_graph_allocation_plan.json"
    )
    assert Path(bindings["APPS_RG_RESUME_GRAPH_USAGE_LEDGER"]).name == (
        "resume_graph_usage_ledger.json"
    )
    assert Path(bindings["APPS_RG_SECTION_FINAL_GRAPH_EVIDENCE_CONTRACTS"]).name == (
        "section_final_graph_evidence_contracts.json"
    )
    authority = pr._whole_resume_graph_rollup_authority(
        repo=tmp_path,
        run_dir=run_dir,
    )
    assert authority["resume_graph_allocation_plan_digest"] == plan[
        "allocation_plan_digest"
    ]
    assert authority["resume_graph_allocation_refs"] == {
        "allocation_plan": (
            "run/modular_r4/resume_graph_allocation/resume_graph_allocation_plan.json"
        ),
        "usage_ledger": (
            "run/modular_r4/resume_graph_allocation/resume_graph_usage_ledger.json"
        ),
        "section_final_evidence_contracts": (
            "run/modular_r4/resume_graph_allocation/section_final_graph_evidence_contracts.json"
        ),
        "section_plans": (
            "run/modular_r4/resume_graph_allocation/c03_section_graph_plans.json"
        ),
    }
    assert "resume_graph_w6_release_evidence" not in authority
    assert Path(bindings["APPS_RG_SECTION_GRAPH_SOURCE_PLANS"]).name == (
        "c03_section_graph_plans.json"
    )


def test_patch_run_rejects_partial_whole_resume_graph_authority(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_json(
        run_dir
        / "modular_r4"
        / "resume_graph_allocation"
        / "resume_graph_usage_ledger.json",
        {"allocation_plan_digest": "partial"},
    )

    with pytest.raises(PatchRunInputError, match="bundle is incomplete"):
        pr._whole_resume_graph_env_for_patch(run_dir)


def test_default_dispatch_threads_derived_jd_brief_into_canonical_primitives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live defect (attempt4 patch_run_1.log): plan derivation printed correct AIG
    targeting but the per-lane dispatch fell to DEFAULT_SSOT / REQUIRED_PROOF_ABSENT.
    The DEFAULT dispatch path (no dispatch_fn) MUST pass the derived JD ref / brief /
    level / mode into run_canonical_apps_rg_from_cli_primitives for every lane."""
    repo, run_dir = _seed_integrated_run(tmp_path)
    real_find_repo_root = pr.find_repo_root
    monkeypatch.setattr(
        pr,
        "find_repo_root",
        lambda start=None: repo if start is None else real_find_repo_root(start),
    )
    import apps_rg.runtime.validators.companion_bullet_finalization as cbf

    monkeypatch.setattr(
        cbf, "companion_accepted_in_modular_sections_root", lambda *a, **k: True
    )
    preflight_calls: list[tuple[str, Any]] = []
    _patch_embedding_preflight(monkeypatch, preflight_calls)

    captured: dict[str, dict[str, Any]] = {}

    def _capture_primitives(**kwargs: Any) -> dict[str, Any]:
        lane = str(kwargs.get("section") or "")
        captured[lane] = dict(kwargs)
        rd = _seed_lane_run(repo, run_dir, lane, f"{lane}_20260611_090000")
        return {
            "exit_status": "success",
            "x3_disposition": "X3_ALLOW",
            "artifact_dir": str(rd),
        }

    import apps_rg.runtime.orchestration.canonical_dispatch as cd

    monkeypatch.setattr(
        cd, "run_canonical_apps_rg_from_cli_primitives", _capture_primitives
    )

    plan = build_patch_plan(run_dir)
    result = execute_patch_run(
        plan,
        aggregate_fn=lambda plan_arg, **kw: {
            "decisive_status": "PASS",
            "failure_reason": "",
            "full_success_eligibility": {"eligible": True, "reasons": []},
        },
    )
    assert result["exit_code"] == 0
    assert set(captured) == {"ibm_bullets", "ibm_narrative", "executive_summary", "headline"}

    jd_abs = str(resolve_repository_path(repo, "apps_rg/config/targeting/aig_jd.txt").resolve())
    brief_abs = str(
        resolve_repository_path(repo, "apps_rg/config/targeting/aig_brief.md").resolve()
    )
    for lane, kwargs in captured.items():
        # Derived targeting — identical to the full-run CLI invocation primitives.
        assert kwargs["target_company"] == "AIG", lane
        assert kwargs["target_role"] == "VP Global Head of Agentic AI Solutions", lane
        assert kwargs["target_level"] == "VP", lane
        assert kwargs["generation_mode"] == "strategic_tailor", lane
        # --jd file path → job_description_ref primitive (jd legacy slot stays empty).
        assert kwargs["jd"] == "", lane
        assert kwargs["job_description_ref"] == jd_abs, lane
        assert kwargs["job_description_text"] == "", lane
        # --manual-brief path → briefing primitive.
        assert kwargs["manual_brief"] == brief_abs, lane
        # Each patch retry has an immutable lane-attempt root. This prevents a
        # materially larger valid evidence receipt from overwriting a prior
        # failed attempt in the flat lane directory.
        assert kwargs["section"] == lane
        attempt_dir = Path(str(kwargs["artifact_dir"]))
        assert attempt_dir.parent.name == "real"
        assert attempt_dir.parent.parent.name == lane
        assert attempt_dir.parent.parent.parent == run_dir / "modular_r4" / "sections"
        assert attempt_dir.name.startswith("p_")
        assert len(attempt_dir.name) == 8
        # The longest mandatory core-chain filename must remain below the
        # legacy Windows path limit used by this runtime boundary.
        assert len(str(attempt_dir / "integrated_runtime_entrypoint_invocation.json")) < 260
        assert kwargs["resume_path"] == ""
        assert str(kwargs["lane_provider"]).strip() != ""
        if lane == "ibm_narrative":
            assert kwargs["lane_provider"] == "external_openai"
            assert kwargs["lane_provider_resolution_source"] == "DEV_DEFAULT_EXTERNAL_OPENAI"
        else:
            assert kwargs["lane_provider"] == "external_claude"
            assert kwargs["lane_provider_resolution_source"] == "DEV_DEFAULT_EXTERNAL_CLAUDE"
        assert kwargs["lane_mock_judges"] is False
        assert kwargs["lane_allow_non_allow_exit_zero"] is False

    # Whole-run embedding env preflight (C0 evidence-room composition prerequisite)
    # MUST run in the patch context before any lane dispatch.
    kinds = [k for k, _ in preflight_calls]
    assert kinds == ["bootstrap", "guards", "receipt"]
    assert preflight_calls[0][1] == plan.repo
    assert preflight_calls[2][1] == plan.run_dir


def test_default_dispatch_threads_inline_jd_text_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the persisted --jd file is gone, the inline job_description_text fallback
    derived from validated_request.app_payload must reach the dispatch primitives."""
    repo, run_dir = _seed_integrated_run(tmp_path)
    resolve_repository_path(repo, "apps_rg/config/targeting/aig_jd.txt").unlink()
    lane_rd = latest_lane_run_dir_any(run_dir / "modular_r4" / "sections", "competencies")
    assert lane_rd is not None
    _write_json(
        lane_rd / "validated_request.json",
        {
            "payload": {
                "app_payload": {
                    "target_company": "AIG",
                    "target_role": "VP Global Head of Agentic AI Solutions",
                    "job_description_text": "Inline JD body from validated_request",
                    "user_constraints": {"briefing_text": "inline brief"},
                }
            }
        },
    )
    real_find_repo_root = pr.find_repo_root
    monkeypatch.setattr(
        pr,
        "find_repo_root",
        lambda start=None: repo if start is None else real_find_repo_root(start),
    )
    import apps_rg.runtime.validators.companion_bullet_finalization as cbf

    monkeypatch.setattr(
        cbf, "companion_accepted_in_modular_sections_root", lambda *a, **k: True
    )
    _patch_embedding_preflight(monkeypatch, [])

    captured: dict[str, dict[str, Any]] = {}

    def _capture_primitives(**kwargs: Any) -> dict[str, Any]:
        lane = str(kwargs.get("section") or "")
        captured[lane] = dict(kwargs)
        rd = _seed_lane_run(repo, run_dir, lane, f"{lane}_20260611_090000")
        return {
            "exit_status": "success",
            "x3_disposition": "X3_ALLOW",
            "artifact_dir": str(rd),
        }

    import apps_rg.runtime.orchestration.canonical_dispatch as cd

    monkeypatch.setattr(
        cd, "run_canonical_apps_rg_from_cli_primitives", _capture_primitives
    )

    plan = build_patch_plan(run_dir)
    execute_patch_run(
        plan,
        aggregate_fn=lambda plan_arg, **kw: {
            "decisive_status": "PASS",
            "failure_reason": "",
            "full_success_eligibility": {"eligible": True, "reasons": []},
        },
    )
    assert captured, "no lanes dispatched"
    for lane, kwargs in captured.items():
        assert kwargs["job_description_ref"] == "", lane
        assert kwargs["job_description_text"] == "Inline JD body from validated_request", lane


# --------------------------------------------------------------- aggregation (partial)


def test_aggregate_refreshes_evidence_status_and_fails_on_missing_lane(
    tmp_path: Path,
) -> None:
    repo, run_dir = _seed_integrated_run(tmp_path)
    # No dispatch — headline/executive_summary/ibm_bullets are still X3_BLOCK and
    # ibm_narrative has no run dir; aggregation must mark FAIL and refresh evidence.
    plan = build_patch_plan(run_dir)
    agg = pr.aggregate_patched_run(
        plan,
        lane_dispatch_results={},
        lane_provider="",
        run_token="patch_test",
    )
    assert agg["decisive_status"] == "FAIL"
    assert agg["failure_reason"].startswith(
        ("phase1_incomplete_lane_artifacts", "fatal_lane_recipe_policy")
    )
    status = json.loads(
        (run_dir / "integrated_lane_evidence_status.json").read_text(encoding="utf-8")
    )
    assert status["integrated_run_id"] == run_dir.name
    missing = {row["lane_id"] for row in status["missing_lanes"]}
    assert "ibm_narrative" in missing
    calls_doc = json.loads(
        (run_dir / "modular_r4" / "section_provider_calls.json").read_text(encoding="utf-8")
    )
    assert calls_doc["patch_run"] is True
    assert calls_doc["decisive_status"] == "FAIL"
    assert calls_doc["lane_provider_global_override"] == ""
    assert calls_doc["lane_provider_by_lane"]["competencies"] == "external_claude"
    assert calls_doc["lane_provider_by_lane"]["ibm_bullets"] == "external_claude"
    assert calls_doc["lane_provider_by_lane"]["ibm_narrative"] == "external_openai"
    assert agg["lane_provider_by_lane"]["competencies"] == "external_claude"
