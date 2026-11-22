"""Unit and adversarial edge-case coverage for Plane A (judge healing & zero post-LLM prose mutation)
and Plane B (cold-runtime latency bounds: effort forwarding, 1-path passthrough, bounded C0 cache).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from apps_rg.runtime.c0.c0_perf_sync_helpers import (
    get_or_compute_bounded_section_retrieval,
    reset_c0_shared_retrieval_caches_for_tests,
)
from apps_rg.runtime.judges import x1d_ide_cli as ide_judge
from apps_rg.runtime.judges.bullet_pool_claude_selector import (
    run_claude_bullet_pool_selection,
)
from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.orchestration.ResumeRunRecoveryAgent import ResumeRunRecoveryAgent
from apps_rg.runtime.providers import ide_cli_generation as icg
from apps_rg.runtime.providers.agy_cli_transport import AgyResult
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.bullet_pool_reselection import (
    LaneRebuildState,
    run_bullet_judge_llm_rewrite,
)
from apps_rg.runtime.reasoning.bullet_lane_self_consistency import SelfConsistencyPath
from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as evra
from apps_rg.runtime.sections.headline_lane import HEADLINE_MAX_OUTPUT_TOKENS
from apps_rg.runtime.sections.ibm_narrative_lane_runtime import (
    apply_ibm_narrative_judge_feedback_rewrite,
)
from apps_rg.runtime.sections.role_episode.proof_selection import (
    _proof_authorized_narrative_from_selection,
)
from apps_rg.runtime.sections.unify_narrative_lane import (
    normalize_unify_narrative_parsed,
)


def test_real_llm_paths_enforce_zero_post_llm_prose_mutation() -> None:
    """REAL_LLM normalization must never splice 'GraphRAG-backed', 'enterprise AI', or consulting rewrites."""
    raw_unify = (
        "Owned Unify Consulting's platform architecture for dependency-graph retrieval, "
        "converting consulting delivery into reusable platform services."
    )
    doc = {
        "narrative_sentence": raw_unify,
        "claim_ledger": [{"claim_text": raw_unify, "source_fact_ids": ["bul_unify_001"]}],
    }
    norm_real = normalize_unify_narrative_parsed(
        doc,
        runtime_payload={"selected_fact_plan": {}, "allowed_fact_ids": ["bul_unify_001"]},
        allow_prose_mutation=False,
    )
    assert norm_real is not None
    assert norm_real["narrative_sentence"] == raw_unify
    assert "GraphRAG-backed" not in norm_real["narrative_sentence"]
    assert "consulting delivery" in norm_real["narrative_sentence"]

    # Role-episode REAL_LLM path keeps literal prose intact so X2/X1D judge exact model output
    role_parsed = {
        "narrative_sentence": "Directed regulated cloud architecture and frontier AI governance across banking portfolios.",
        "source_fact_ids": ["bul_slalom_001"],
    }
    facts = [
        {
            "fact_id": "bul_slalom_001",
            "claim_text": "Directed regulated cloud architecture and governance across banking portfolios.",
        }
    ]
    narr, sids, _src, used = _proof_authorized_narrative_from_selection(
        parsed=role_parsed,
        facts=facts,
        allowed=["bul_slalom_001"],
        section_id="slalom_narrative",
        allow_prose_mutation=False,
    )
    assert used is True
    assert sids == ["bul_slalom_001"]
    assert "frontier AI" in narr


def test_ibm_narrative_judge_feedback_rewrite_accepts_only_on_rank_improvement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.section_repair_ledger import init_ledger

    init_ledger(tmp_path, section_id="ibm_narrative", run_id="run-ibm-1")
    companion = (
        "bul_ibm_001: Led cloud platform modernization and automated DevSecOps pipeline controls across enterprise banking programs.\n"
        "bul_ibm_002: Built governed data models and lineage reporting across regulated financial institutions."
    )
    runtime_payload = {
        "run_id": "run-ibm-1",
        "allowed_fact_ids": ["bul_ibm_001", "bul_ibm_002"],
        "selected_fact_plan": {"facts": [{"fact_id": "bul_ibm_001"}, {"fact_id": "bul_ibm_002"}]},
    }
    initial_parsed = {
        "narrative_sentence": "At IBM, led cloud modernization, establishing data lineage.",
        "claim_ledger": [
            {"claim_text": "At IBM, led cloud modernization", "source_fact_ids": ["bul_ibm_001"]},
            {"claim_text": "establishing data lineage.", "source_fact_ids": ["bul_ibm_002"]},
        ],
    }
    failing_x1d = [
        {"judge_id": "j1", "provider_key": "gemini_pro", "pass": False, "score": 3.2, "findings": ["Too generic."]}
    ]
    repaired_json = json.dumps(
        {
            "narrative_sentence": (
                "At IBM, directed client-facing cloud architecture and DevSecOps release governance across banking engagements, "
                "establishing auditable data lineage for executive decision support."
            ),
            "selected_fact_plan": runtime_payload["selected_fact_plan"],
            "claim_ledger": [
                {
                    "claim_text": "At IBM, directed client-facing cloud architecture and DevSecOps release governance across banking engagements",
                    "source_fact_ids": ["bul_ibm_001"],
                },
                {
                    "claim_text": "establishing auditable data lineage for executive decision support.",
                    "source_fact_ids": ["bul_ibm_002"],
                },
            ],
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "gap_notes": [],
            "change_log": [],
            "self_check": {},
        }
    )

    monkeypatch.setattr(
        "apps_rg.runtime.sections.ibm_narrative_lane_runtime.generate_section",
        lambda *_a, **_k: ProviderResult(
            provider_requested="external_openai",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="gpt-5.6-luna",
            raw_model_output=repaired_json,
            provider_response={},
        ),
    )
    captured_packets: list[Any] = []

    def _fake_judges(**kwargs: Any) -> list[JudgeOutput]:
        captured_packets.append((kwargs.get("allowed_fact_packet"), kwargs.get("targeting_context")))
        return [
            JudgeOutput(
                judge_id="j1",
                provider_name="Gemini",
                provider_key="gemini_pro",
                evaluator_mode="MODEL_BACKED",
                provider_status="MODEL_BACKED_PASS",
                model_name="gemini-4-argon-high",
                provider_available=True,
                provider_blocked=False,
                exact_provider_error=None,
                score=4.8,
                normalized_score=0.96,
                threshold=4.0,
                normalized_threshold=0.8,
                pass_=True,
            )
        ]

    monkeypatch.setattr("apps_rg.runtime.sections.ibm_narrative_lane_runtime.run_ibm_narrative_judges", _fake_judges)
    new_raw, new_parsed, new_x1d, accepted = apply_ibm_narrative_judge_feedback_rewrite(
        messages=[{"role": "user", "content": "Draft IBM narrative"}],
        provider_payload={"model": "gpt-5.6-luna"},
        raw_output="{}",
        parsed=initial_parsed,
        x1d=failing_x1d,
        runtime_payload=runtime_payload,
        artifact_dir=tmp_path,
        runtime_generation_status="REAL_LLM",
        companion_text=companion,
        judge_keys=["gemini_pro"],
        judge_mode="blocked_if_unavailable",
        allowed_fact_packet={"allowed_fact_ids": ["bul_ibm_001", "bul_ibm_002"]},
        targeting_context={"target_company": "Truist", "targeting_only": True},
    )
    assert accepted is True
    assert new_parsed is not None and "client-facing cloud architecture" in new_parsed["narrative_sentence"]
    assert new_x1d[0]["pass"] is True
    assert captured_packets[0][0] == {"allowed_fact_ids": ["bul_ibm_001", "bul_ibm_002"]}
    assert captured_packets[0][1] == {"target_company": "Truist", "targeting_only": True}
    assert (tmp_path / "ibm_narrative_judge_rewrite_receipt.json").is_file()


def test_bullet_judge_llm_rewrite_reverts_when_rejudge_does_not_improve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.section_repair_ledger import init_ledger

    init_ledger(tmp_path, section_id="ibm_bullets", run_id="run-bul-1")
    usage_path = tmp_path / "section_input_usage_ledger.json"
    usage_path.write_text('{"original": true}\n', encoding="utf-8")

    monkeypatch.setattr(
        "apps_rg.runtime.providers.section_provider_call.call_section_model_provider",
        lambda *_a, **_k: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="gemini-4-neon-medium",
            raw_model_output='{"bullets": [{"bullet_id": "bul_ibm_001", "bullet_text": "Led cloud pipelines."}]}',
            provider_response={},
        ),
    )

    def _rebuild(doc: dict[str, Any]) -> LaneRebuildState:
        return LaneRebuildState(
            parsed=doc,
            bullets=list(doc.get("bullets") or []),
            claim_ledger=[{"claim_text": "Led cloud pipelines.", "source_fact_ids": ["bul_ibm_001"]}],
            coverage={},
            parsed_for_x2=doc,
            canon_doc={},
            usage_doc={"rewritten": True},
            display_text="- Led cloud pipelines.",
            parse_status="OK",
        )

    res, raw_after = run_bullet_judge_llm_rewrite(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        run_id="run-bul-1",
        provider_name="external_claude",
        provider_payload={"model": "claude-sonnet-5-5-medium"},
        base_messages=[{"role": "user", "content": "Write bullets"}],
        prior_raw_output='{"prior": true}',
        required_bullet_ids=("bul_ibm_001",),
        parsed={"bullets": []},
        bullets=[],
        claim_ledger=[],
        parsed_for_x2={},
        x1d=[{"judge_id": "j1", "provider_key": "gemini_pro", "pass": False, "score": 3.8, "findings": ["Weak"]}],
        x2=[{"gate_id": "g1", "pass": True}],
        usage_doc={"original": True},
        canon_doc={},
        runtime_generation_status="REAL_LLM",
        judge_mode="blocked_if_unavailable",
        parse_json_fn=lambda s: (json.loads(s), ""),
        post_chain=lambda d: d,
        rebuild_state=_rebuild,
        run_x2=lambda _st, _x1d: [{"gate_id": "g1", "pass": True}],
        run_judges=lambda _st, _keys: [
            {"judge_id": "j1", "provider_key": "gemini_pro", "pass": False, "score": 3.5, "findings": ["Worse"]}
        ],
        write_usage_ledger=lambda st: usage_path.write_text(json.dumps(st.usage_doc) + "\n", encoding="utf-8"),
        write_lane_artifacts=lambda _st, _x2: None,
    )
    assert res.fired is False
    assert raw_after == '{"prior": true}'
    # Byte-exact restore of section_input_usage_ledger.json on rejected rewrite
    assert json.loads(usage_path.read_text(encoding="utf-8")) == {"original": True}


def test_executive_voice_repair_agent_structured_competencies_preserves_source_fact_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-live-key")
    comps = [
        {
            "category": f"Cat {i}",
            "category_label": f"Cat {i}",
            "competency_bundle_id": f"bundle_{i}",
            "terms": [{"term": f"Skill {i}A", "source_fact_ids": [f"fact_{i}"]}],
        }
        for i in range(6)
    ]
    repaired_payload = {
        "repaired_competencies": [
            {"category": f"Refined Cat {i}", "skills": [f"Governed Skill {i}A", f"Platform Skill {i}B"]}
            for i in range(6)
        ]
    }
    monkeypatch.setattr(evra, "_call_llm_repair", lambda *_a, **_k: repaired_payload)
    updated, receipt = evra.repair_section_with_executive_voice_agent(
        section_id="competencies",
        candidate_data={"competencies": comps},
        diagnostic={"repair_needed": True, "findings": ["Improve specificity"], "remediation_suggestions": []},
        allowed_facts=[],
        targeting_context={"target_role": "SVP Engineering"},
        artifact_dir=tmp_path,
        mock_mode=False,
    )
    assert receipt.repair_succeeded is True
    assert receipt.repair_mechanism == "llm_repair_agent"
    assert updated["competencies"][0]["category_label"] == "Refined Cat 0"
    assert updated["competencies"][0]["terms"][0]["term"] == "Governed Skill 0A"
    assert updated["competencies"][0]["terms"][0]["source_fact_ids"] == ["fact_0"]
    assert updated["competencies"][0]["terms"][1]["source_fact_ids"] == ["fact_0"]


def test_recovery_agent_identifies_12th_stage_coherence_and_cross_section_failures(tmp_path: Path) -> None:
    asm = tmp_path / "modular_r4" / "final_resume_assembly"
    asm.mkdir(parents=True)
    (asm / "final_resume_x2_gate_outputs.json").write_text(
        json.dumps(
            {
                "gates": [
                    {
                        "gate_id": "x2_ibm_narrative_vs_ibm_bullets_cosine",
                        "pass": False,
                        "failure_reason": "ibm_narrative echoes companion bullets",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (asm / "x1d_full_resume_judge_outputs.json").write_text(
        json.dumps(
            {
                "full_resume_coherence_pass": False,
                "judges": [
                    {
                        "pass": False,
                        "findings": ["The Unify narrative overstates scope relative to Unify bullets."],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    agent = ResumeRunRecoveryAgent(artifact_dir=tmp_path, repo_root=tmp_path)
    whole_exit = {
        "status": "BLOCKED",
        "x3_disposition": "X3A_DENY_REROUTE",
        "signals": {
            "lane_rows": [
                {"lane": "ibm_narrative", "x3_code": "X3_ALLOW", "x2_failed": 0, "product_quality_status": "PASS"},
                {"lane": "unify_narrative", "x3_code": "X3_ALLOW", "x2_failed": 0, "product_quality_status": "PASS"},
            ]
        },
    }
    failing = agent.identify_failing_lanes(whole_exit, exec_summary_block={"blocked": False})
    assert "ibm_narrative" in failing
    assert "unify_narrative" in failing
    assert "unify_bullets" in failing


def test_ide_cli_effort_forwarding_and_low_effort_slug_stepping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert HEADLINE_MAX_OUTPUT_TOKENS == 2400

    # 1. Judge effort forwarding
    judge_calls: list[dict[str, Any]] = []

    def _fake_judge_agy(prompt: str, *, model: str, json_schema: Any = None, effort: str | None = None, **_kw: Any) -> AgyResult:
        judge_calls.append({"model": model, "effort": effort})
        good = {
            "score_scale": "0_to_5",
            "score": 4.8,
            "threshold": 4.0,
            "pass": True,
            "decisive_failure": False,
            "findings": ["Grounded."],
            "cited_sentence_indexes": [1],
            "remediation_suggestions": [],
        }
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response=json.dumps(good),
            structured_output=good,
            usage={"input_tokens": 80, "output_tokens": 40, "total_tokens": 120},
            duration_seconds=2.1,
            conversation_id="conv-judge-eff",
        )

    monkeypatch.setattr(ide_judge, "run_agy", _fake_judge_agy)
    out = ide_judge.call_ide_cli_judge(
        prompt="Grade headline",
        model="gemini-3.8-flash-medium",
        input_hash="h123",
        provider_key="openai_chatgpt",
        artifact_base=tmp_path,
        reasoning_effort="low",
        section_id="headline",
    )
    assert out.pass_ is True
    assert judge_calls[0]["effort"] == "low"
    req_file = next(p for p in tmp_path.iterdir() if "provider_request" in p.name)
    assert json.loads(req_file.read_text(encoding="utf-8"))["reasoning_effort"] == "low"

    # 2. Generation low-effort sibling stepping (gemini-4-neon-medium -> gemini-4-neon-low without mutating YAML)
    gen_calls: list[dict[str, Any]] = []

    def _fake_gen_agy(prompt: str, *, model: str, effort: str | None = None, **_kw: Any) -> AgyResult:
        gen_calls.append({"model": model, "effort": effort})
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response='{"headline_line": "SVP Engineering | Agentic AI Platforms | Cloud Modernization | Enterprise Governance"}',
            structured_output=None,
            usage={"input_tokens": 200, "output_tokens": 30, "total_tokens": 230},
            duration_seconds=3.1,
            conversation_id="conv-gen-low",
        )

    monkeypatch.setattr(icg, "run_agy", _fake_gen_agy)
    resp = icg.call_ide_cli_generation(
        request={"model": "claude-sonnet-5-5-high", "reasoning_effort": "low"},
        body={"model": "claude-sonnet-5-5-high", "messages": [{"role": "user", "content": "Draft headline"}]},
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": "/fake/agy"},
    )
    assert gen_calls[0]["model"] == "gemini-4-neon-low"
    assert resp["model"] == "gemini-4-neon-low"


def test_frozen_single_path_selector_passthrough_and_edge_guards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    monkeypatch.delenv("APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS", raising=False)

    compliant_bullet = {
        "bullet_id": "bul_ibm_001",
        "bullet_text": (
            "Architected automated DevSecOps release pipelines and Kubernetes governance controls across "
            "regulated banking cloud platforms, accelerating enterprise deployment velocity by 30%."
        ),
        "source_fact_ids": ["bul_ibm_001"],
    }
    valid_single = SelfConsistencyPath(
        path_index=0,
        temperature=0.35,
        runtime_generation_status="REAL_LLM",
        raw_output=json.dumps({"bullets": [compliant_bullet]}),
        parsed={
            "bullets": [compliant_bullet],
            "claim_ledger": [{"claim_text": compliant_bullet["bullet_text"], "source_fact_ids": ["bul_ibm_001"]}],
        },
        parse_error="",
        provider_result=None,
    )

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("LLM selector should not be called on compliant 1-path frozen allocation")

    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector._call_anthropic_pool_selector",
        _boom,
    )
    res = run_claude_bullet_pool_selection(
        section_id="ibm_bullets",
        slot_kind="bullets",
        paths=[valid_single],
        required_bullet_ids=("bul_ibm_001",),
        targeting_context={
            "frozen_allocation_materialized": True,
            "allowed_fact_ids": ["bul_ibm_001"],
        },
        artifact_dir=tmp_path,
    )
    assert res.selection_mode.endswith("_frozen_single_path_passthrough")
    assert len(res.selections) == 1 and res.selections[0]["bullet_id"] == "bul_ibm_001"
    assert (tmp_path / "bullet_pool_claude_selector_judge.json").is_file()


def test_bounded_section_retrieval_cache_deduplicates_and_restamps_timestamps(tmp_path: Path) -> None:
    reset_c0_shared_retrieval_caches_for_tests()

    @dataclass(frozen=True)
    class _FakeItem:
        evidence_id: str
        retrieval_timestamp: str

    @dataclass(frozen=True)
    class _FakeVerdict:
        gate_id: str
        evaluated_at: str
        evidence_digest: str

    calls = 0

    def _compute() -> tuple[list[Any], list[Any], str, list[str], list[tuple[str, float]], list[Any]]:
        nonlocal calls
        calls += 1
        return (
            [_FakeItem("ev1", "t0")],
            [_FakeVerdict("G_SECTION_RETRIEVAL", "t0", "d0")],
            "PASS",
            ["ref1"],
            [("dense:ibm_bullets", 0.91)],
            [],
        )

    payload = {"jd_text": "Head of FDE", "target_role": "Head of FDE", "target_company": "Truist"}
    r1 = get_or_compute_bounded_section_retrieval(
        chroma_path=str(tmp_path),
        collection_count=42,
        section_id_filter="ibm_bullets",
        app_payload=payload,
        evidence_digest="dig_1",
        timestamp_iso="2026-11-21T21:00:00Z",
        compute_fn=_compute,
    )
    r2 = get_or_compute_bounded_section_retrieval(
        chroma_path=str(tmp_path),
        collection_count=42,
        section_id_filter="ibm_bullets",
        app_payload=payload,
        evidence_digest="dig_2",
        timestamp_iso="2026-11-21T21:00:05Z",
        compute_fn=_compute,
    )
    assert calls == 1
    assert r2[0][0].retrieval_timestamp == "2026-11-21T21:00:05Z"
    assert r2[1][0].evaluated_at == "2026-11-21T21:00:05Z"
    assert r2[1][0].evidence_digest == "dig_2"

    # Changing collection_count invalidates cache
    get_or_compute_bounded_section_retrieval(
        chroma_path=str(tmp_path),
        collection_count=43,
        section_id_filter="ibm_bullets",
        app_payload=payload,
        evidence_digest="dig_3",
        timestamp_iso="2026-11-21T21:00:10Z",
        compute_fn=_compute,
    )
    assert calls == 2
    reset_c0_shared_retrieval_caches_for_tests()


def test_employment_targeting_context_propagates_frozen_allocation_materialized() -> None:
    from apps_rg.runtime.reasoning.bullet_pool_sync_helpers import resolve_employment_lane_sc_budgets
    from apps_rg.runtime.reasoning.employment_bullet_pool import (
        adaptive_sc_enabled_for_lane,
        build_employment_targeting_context,
        max_employment_regen_rounds,
        max_sc_path_count_for_lane,
        sc_path_count_for_lane,
    )

    ctx = build_employment_targeting_context(
        {
            "proof_pool_metadata": {"frozen_allocation_materialized": True},
            "allowed_fact_ids": ["bul_slalom_001", "bul_slalom_002", "bul_slalom_003"],
            "selected_fact_plan": {"facts": []},
        },
        section_lane="slalom_bullets",
    )
    assert ctx["frozen_allocation_materialized"] is True
    init_p, max_p, adap, _cfg_r, max_r = resolve_employment_lane_sc_budgets(
        section_lane="slalom_bullets",
        targeting_context=ctx,
        judge_mode="blocked_if_unavailable",
        sc_path_count_fn=sc_path_count_for_lane,
        max_sc_path_count_fn=max_sc_path_count_for_lane,
        adaptive_sc_fn=adaptive_sc_enabled_for_lane,
        max_regen_fn=max_employment_regen_rounds,
    )
    assert init_p == 1 and max_p == 1 and adap is False and max_r == 0
