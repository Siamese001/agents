"""Wave 5 unit tests for whole-run fast cache, R1A v2 indexing, and section lane cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.__main__ import _evaluate_product_run
from apps_rg.cache.r1a_adapter import (
    check_r1a_cache,
    compute_r1a_key,
    prune_stale_r1a_entries,
    stamp_r1a_cache,
)
from apps_rg.cache.section_lane_cache import (
    compute_section_lane_cache_key,
    dispatch_lane_with_section_cache,
)
from apps_rg.cache.whole_run_entrypoint_preflight import (
    ENTRYPOINT_CANONICAL_DISPATCH,
    maybe_ingest_r1b_post_exit,
    run_whole_run_cache_preflight,
)
from apps_rg.cache.whole_run_fast_cache import (
    stamp_authorized_whole_run_r1a,
    try_serve_pre_research_whole_run_cache_hit,
)
from apps_rg.runtime.c0.resume_graph_allocation import SECTION_EVIDENCE_CONTRACTS_ENV
from apps_rg.runtime.orchestration.canonical_dispatch import build_raw_request_for_r4
from apps_rg.runtime.product_output_policy import lane_run_dir_meets_product_bar
from apps_rg.runtime.runtime_proof_layout import ACCEPTED_REAL_LLM_PROVIDER_PROFILES


def _seed_authorized_run(run_dir: Path, parent_run_id: str = "apps-rg-test-001") -> str:
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    payload = {"headline": "SVP Engineering | Partner AI | Platform | Lakehouse", "run": parent_run_id}
    raw_bytes = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    (run_dir / "outputs" / "generated_resume.json").write_bytes(raw_bytes)
    (run_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True, "parent_run_id": parent_run_id}),
        encoding="utf-8",
    )
    (run_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}),
        encoding="utf-8",
    )
    (run_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"x3_disposition": "X3D_ALLOW_FINISH"}),
        encoding="utf-8",
    )
    (run_dir / "runtime_identity_envelope.json").write_text(
        json.dumps({"parent_run_id": parent_run_id}),
        encoding="utf-8",
    )
    eval_dir = run_dir / "apps_eval" / "whole_run"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "eval_record.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "verdict": "PASS",
                "parent_run_id": parent_run_id,
                "scorecard": {"verdict": "PASS", "status": "PASS"},
            }
        ),
        encoding="utf-8",
    )
    return hashlib.sha256(raw_bytes).hexdigest()


def test_r1a_v1_compat_and_v2_jd_brief_isolation_plus_o1_index(tmp_path: Path) -> None:
    k_v1 = compute_r1a_key(
        source_resume_hash="res_hash",
        target_company="Anthropic",
        target_role="Partner Architect",
    )
    assert len(k_v1) == 64
    k_v2_a = compute_r1a_key(
        source_resume_hash="res_hash",
        target_company="Anthropic",
        target_role="Partner Architect",
        jd_hash="jd_aaa",
        briefing_hash="br_111",
    )
    k_v2_b = compute_r1a_key(
        source_resume_hash="res_hash",
        target_company="Anthropic",
        target_role="Partner Architect",
        jd_hash="jd_bbb",
        briefing_hash="br_111",
    )
    assert k_v2_a != k_v1
    assert k_v2_a != k_v2_b

    runs_dir = tmp_path / "runtime_proofs"
    r1 = runs_dir / "full_resume_a1"
    _seed_authorized_run(r1)
    stamp_r1a_cache(
        k_v2_a,
        run_dir=r1,
        policy_hash="pol_v1",
        jd_hash="jd_aaa",
        briefing_hash="br_111",
        extra_keys=[k_v1],
    )
    assert (runs_dir / "r1a_index.json").is_file()

    hit_exact = check_r1a_cache(k_v2_a, runs_dir=runs_dir, jd_hash="jd_aaa", briefing_hash="br_111")
    assert hit_exact == str(r1.resolve())

    miss_diff_jd = check_r1a_cache(k_v2_b, runs_dir=runs_dir, jd_hash="jd_bbb", briefing_hash="br_111")
    assert miss_diff_jd is None

    # Prune cleans stale policy-hash entries and updates index
    pruned = prune_stale_r1a_entries(runs_dir=runs_dir, policy_hash="pol_v2")
    assert pruned == ["full_resume_a1"]
    assert check_r1a_cache(k_v2_a, runs_dir=runs_dir) is None


def test_maybe_ingest_r1b_post_exit_stamps_r1a_even_when_r1b_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPS_RG_SEMANTIC_CACHE_R1B", raising=False)
    runs_dir = tmp_path / "runtime_proofs"
    art = runs_dir / "full_resume_stamped"
    _seed_authorized_run(art)

    raw_req = build_raw_request_for_r4(
        target_company="Anthropic",
        target_role="Partner Architect",
        target_level="Manager",
        jd="",
        job_description_ref="",
        job_description_text="Build partner ecosystem accelerators.",
        manual_brief="",
        resume_path="",
        source_resume_text="Led 106 engineers.",
        generation_mode="strategic_tailor",
    )
    raw_req["caller_brief_hash"] = str(raw_req.get("brief_hash") or "")
    preflight = run_whole_run_cache_preflight(
        entrypoint=ENTRYPOINT_CANONICAL_DISPATCH,
        raw_request=raw_req,
        target_company="Anthropic",
        target_role="Partner Architect",
        artifact_dir=art,
        runs_dir=runs_dir,
    )
    assert preflight.generation_required is True

    ingested_r1b = maybe_ingest_r1b_post_exit(
        raw_request=raw_req,
        artifact_dir=art,
        runs_dir=runs_dir,
    )
    assert ingested_r1b is None
    assert (art / "r1a_stamp.json").is_file()

    art2 = runs_dir / "full_resume_warm_next"
    art2.mkdir(parents=True, exist_ok=True)
    pf2 = run_whole_run_cache_preflight(
        entrypoint=ENTRYPOINT_CANONICAL_DISPATCH,
        raw_request=raw_req,
        target_company="Anthropic",
        target_role="Partner Architect",
        artifact_dir=art2,
        runs_dir=runs_dir,
    )
    assert pf2.generation_required is False
    assert pf2.outcome == "r1a_hit"
    assert Path(pf2.r1a_artifact_dir).resolve() == art.resolve()


def test_pre_research_fast_cache_serves_authorized_rejects_blocked_and_honors_no_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPS_RG_NO_CACHE", raising=False)
    monkeypatch.delenv("APPS_RG_REQUIRE_FRESH_RUN", raising=False)
    runs_dir = tmp_path / "runtime_proofs"
    origin = runs_dir / "full_resume_origin"
    origin_sha = _seed_authorized_run(origin, "apps-rg-auth-777")

    raw_req = build_raw_request_for_r4(
        target_company="Anthropic",
        target_role="Partner Architect",
        target_level="Manager",
        jd="",
        job_description_ref="",
        job_description_text="Enterprise AI deployment.",
        manual_brief="",
        resume_path="",
        source_resume_text="Enterprise architecture leader.",
        generation_mode="strategic_tailor",
    )
    raw_req["caller_brief_hash"] = str(raw_req.get("brief_hash") or "")
    assert stamp_authorized_whole_run_r1a(raw_request=raw_req, artifact_dir=origin) is True

    warm = runs_dir / "full_resume_warm"
    warm.mkdir(parents=True, exist_ok=True)
    res = try_serve_pre_research_whole_run_cache_hit(
        art=warm,
        target_company="Anthropic",
        target_role="Partner Architect",
        target_level="Manager",
        jd="",
        job_description_ref="",
        job_description_text="Enterprise AI deployment.",
        manual_brief="",
        resume_path="",
        source_resume_text="Enterprise architecture leader.",
        generation_mode="strategic_tailor",
        require_fresh_preflight=True,
        stage_ledger=None,
    )
    assert res is not None
    assert res["cache_hit"] is True
    assert res["provider_call_count"] == 0
    assert _evaluate_product_run(warm)["status"] == "PASS"
    assert (
        hashlib.sha256((warm / "outputs" / "generated_resume.json").read_bytes()).hexdigest()
        == origin_sha
    )

    # No-cache bypass
    monkeypatch.setenv("APPS_RG_NO_CACHE", "1")
    warm_nc = runs_dir / "full_resume_nc"
    warm_nc.mkdir(parents=True, exist_ok=True)
    assert (
        try_serve_pre_research_whole_run_cache_hit(
            art=warm_nc,
            target_company="Anthropic",
            target_role="Partner Architect",
            target_level="Manager",
            jd="",
            job_description_ref="",
            job_description_text="Enterprise AI deployment.",
            manual_brief="",
            resume_path="",
            source_resume_text="Enterprise architecture leader.",
            generation_mode="strategic_tailor",
            require_fresh_preflight=True,
            stage_ledger=None,
        )
        is None
    )

    # Rejects unauthorized origin bundle when require_fresh_preflight=True
    monkeypatch.delenv("APPS_RG_NO_CACHE", raising=False)
    (origin / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": False}), encoding="utf-8"
    )
    warm_unauth = runs_dir / "full_resume_unauth"
    warm_unauth.mkdir(parents=True, exist_ok=True)
    assert (
        try_serve_pre_research_whole_run_cache_hit(
            art=warm_unauth,
            target_company="Anthropic",
            target_role="Partner Architect",
            target_level="Manager",
            jd="",
            job_description_ref="",
            job_description_text="Enterprise AI deployment.",
            manual_brief="",
            resume_path="",
            source_resume_text="Enterprise architecture leader.",
            generation_mode="strategic_tailor",
            require_fresh_preflight=True,
            stage_ledger=None,
        )
        is None
    )


def test_section_lane_cache_pointer_rewrite_and_downstream_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider_profile = sorted(ACCEPTED_REAL_LLM_PROVIDER_PROFILES)[0]
    fake_repo = tmp_path / "resume_graph_engine"
    cache_root = fake_repo / "artifacts" / "apps_rg" / "cache" / "section_lanes_v1"
    contracts_file = tmp_path / "contracts.json"

    monkeypatch.setenv("APPS_RG_SECTION_CACHE_ENABLE", "1")
    monkeypatch.setenv("APPS_RG_SECTION_CACHE_ROOT", str(cache_root))
    monkeypatch.delenv("APPS_RG_NO_CACHE", raising=False)
    monkeypatch.setenv(SECTION_EVIDENCE_CONTRACTS_ENV, str(contracts_file))

    contracts_file.write_text(
        json.dumps(
            {
                "slalom_bullets": {
                    "source_section_plan_digest": "plan_sb_1",
                    "graph_digest": "g1",
                    "assignments": [{"claim_unit_id": "sb:1", "fact_id": "f1"}],
                },
                "slalom_narrative": {
                    "source_section_plan_digest": "plan_sn_1",
                    "graph_digest": "g1",
                    "assignments": [{"claim_unit_id": "sn:1", "fact_id": "f2"}],
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_dispatch(**kw: Any) -> dict[str, Any]:
        sec = str(kw["section"])
        calls.append(sec)
        ld = Path(kw["artifact_dir"])
        ld.mkdir(parents=True, exist_ok=True)
        rel = ld.resolve().relative_to(fake_repo.resolve()).as_posix()
        (ld / "l2_output.json").write_text(
            json.dumps(
                {
                    "runtime_generation_status": "REAL_LLM",
                    "product_quality_status": "PASS",
                    "section_id": sec,
                    "call_num": len(calls),
                }
            ),
            encoding="utf-8",
        )
        (ld / "provider_request.json").write_text(
            json.dumps({"provider_requested": provider_profile}), encoding="utf-8"
        )
        (ld / "x3_disposition.json").write_text(
            json.dumps({"x3_code": "X3_ALLOW", "x3_disposition": "X3_ALLOW"}), encoding="utf-8"
        )
        ptr = {
            "run_id": f"{sec}_{len(calls)}",
            "run_dir": rel,
            "provider_requested": provider_profile,
            "runtime_generation_status": "REAL_LLM",
            "section_id": sec,
        }
        (ld / "latest_successful_real_run.json").write_text(json.dumps(ptr), encoding="utf-8")
        (ld / "latest_real_run.json").write_text(json.dumps(ptr), encoding="utf-8")
        return {"exit_status": "success", "x3_disposition": "X3_ALLOW_FINISH"}

    r1 = fake_repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_1" / "lanes"
    for sec in ("slalom_bullets", "slalom_narrative"):
        dispatch_lane_with_section_cache(
            dispatch_fn=_fake_dispatch,
            repo=fake_repo,
            sections_root=r1,
            kwargs={
                "section": sec,
                "artifact_dir": str(r1 / sec),
                "target_company": "Anthropic",
                "target_role": "Partner Architect",
                "job_description_text": "AI Partner",
                "lane_provider": provider_profile,
            },
        )
    assert calls == ["slalom_bullets", "slalom_narrative"]

    # Warm repeat in new run dir -> 0 dispatch calls and pointer run_dir rewritten to r2!
    r2 = fake_repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_2" / "lanes"
    for sec in ("slalom_bullets", "slalom_narrative"):
        res = dispatch_lane_with_section_cache(
            dispatch_fn=_fake_dispatch,
            repo=fake_repo,
            sections_root=r2,
            kwargs={
                "section": sec,
                "artifact_dir": str(r2 / sec),
                "target_company": "Anthropic",
                "target_role": "Partner Architect",
                "job_description_text": "AI Partner",
                "lane_provider": provider_profile,
            },
        )
        assert res["section_cache_hit"] is True
        assert lane_run_dir_meets_product_bar(r2 / sec) == (True, "ok")
        ptr_doc = json.loads((r2 / sec / "latest_successful_real_run.json").read_text(encoding="utf-8"))
        assert "full_resume_2/lanes/" in ptr_doc["run_dir"]
    assert len(calls) == 2

    # Mutating upstream slalom_bullets l2_output invalidates downstream slalom_narrative key
    k_before = compute_section_lane_cache_key(
        sections_root=r2,
        kwargs={"section": "slalom_narrative", "target_company": "Anthropic"},
    )
    (r2 / "slalom_bullets" / "l2_output.json").write_text(
        json.dumps(
            {
                "runtime_generation_status": "REAL_LLM",
                "product_quality_status": "PASS",
                "section_id": "slalom_bullets",
                "edited": True,
            }
        ),
        encoding="utf-8",
    )
    k_after = compute_section_lane_cache_key(
        sections_root=r2,
        kwargs={"section": "slalom_narrative", "target_company": "Anthropic"},
    )
    assert k_before != k_after
