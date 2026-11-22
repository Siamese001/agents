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


def test_feature2_real_llm_prose_mutators_are_gated_across_lanes() -> None:
    from apps_rg.runtime.sections.competencies_lane_runtime import reduce_competency_keyword_stuffing
    from apps_rg.runtime.sections.ibm_narrative_lane_runtime import (
        normalize_parsed_output as normalize_ibm_narr_parsed,
    )
    from apps_rg.runtime.sections.unify_bullets.repairs import (
        normalize_unify_parsed_without_ledger_synthesis,
    )

    # 1. ibm_narrative: allow_echo_repair=False leaves >5 commas, missing period, and non-mechanism text intact
    raw_ibm = "Led enterprise cloud programs, across banking, insurance, capital, risk, and operations"
    ibm_out = normalize_ibm_narr_parsed(
        {
            "narrative_sentence": raw_ibm,
            "claim_ledger": [{"claim_text": raw_ibm, "source_fact_ids": ["bul_ibm_001"]}],
        },
        {"selected_fact_plan": {"section_id": "ibm_narrative", "facts": []}},
        companion_text="",
        allow_echo_repair=False,
    )
    assert ibm_out is not None
    assert ibm_out["narrative_sentence"] == raw_ibm

    # 2. unify_bullets: allow_prose_mutation=False leaves bullet_text verbatim (no 6->six, no tense rewrite, no metric append, no CFO-aligned density swap)
    raw_b1 = "Managed cloud programs from 6 months to 3 weeks for enterprise clients."
    raw_b2 = "Directed CFO-aligned pricing and CFO-aligned commercial motions."
    unify_payload = {
        "allowed_fact_ids": ["bul_unify_001", "bul_unify_002"],
        "selected_fact_plan": {
            "section_id": "unify_bullets",
            "facts": [
                {"fact_id": "bul_unify_001", "claim_text": raw_b1, "metric_outcome_ids": ["m_1"]},
                {"fact_id": "bul_unify_002", "claim_text": raw_b2},
            ],
        },
    }
    unify_out = normalize_unify_parsed_without_ledger_synthesis(
        {
            "bullets": [
                {"bullet_id": "bul_unify_001", "bullet_text": raw_b1, "source_fact_ids": ["bul_unify_001"]},
                {"bullet_id": "bul_unify_002", "bullet_text": raw_b2, "source_fact_ids": ["bul_unify_002"]},
            ],
            "claim_ledger": [
                {"claim_text": raw_b1, "source_fact_ids": ["bul_unify_001"]},
                {"claim_text": raw_b2, "source_fact_ids": ["bul_unify_002"]},
            ],
        },
        unify_payload,
        allow_prose_mutation=False,
    )
    assert unify_out is not None
    assert unify_out["bullets"][0]["bullet_text"] == raw_b1
    assert unify_out["bullets"][1]["bullet_text"] == raw_b2

    # 3. competencies: allow_prose_mutation=False does not synonym-swap overloaded words inside phrases
    comp_doc = {
        "competencies": [
            {
                "category_label": f"Cat {i}",
                "terms": [
                    {"term": "platform execution architecture", "source_fact_ids": ["bul_unify_001"]},
                    {"term": "cloud platform governance", "source_fact_ids": ["bul_unify_001"]},
                    {"term": "agentic platform controls", "source_fact_ids": ["bul_unify_001"]},
                ],
            }
            for i in range(4)
        ]
    }
    reduce_competency_keyword_stuffing(comp_doc, allow_prose_mutation=False)
    for cat in comp_doc["competencies"]:
        terms_text = [t["term"] for t in cat["terms"]]
        assert terms_text == [
            "platform execution architecture",
            "cloud platform governance",
            "agentic platform controls",
        ]


def test_competencies_x1d_embeds_fact_packet_briefing_and_writes_packet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.judges import competencies_x1d
    from apps_rg.runtime.sections.lane_perf_sync_helpers import extract_lane_targeting_kwargs

    t_kw = extract_lane_targeting_kwargs(
        SimpleNamespace(
            target_title="Head of AI",
            target_company="Truist",
            jd_text="Lead agentic AI.",
            briefing="Emphasize governed platforms.",
        )
    )
    assert t_kw["briefing"] == "Emphasize governed platforms."

    captured: dict[str, Any] = {}

    def _fake_call_gemini(
        api_key: str,
        prompt: str,
        model: str,
        input_hash: str,
        provider_key: str,
        **kwargs: Any,
    ) -> JudgeOutput:
        captured["prompt"] = prompt
        captured["judge_receipt"] = kwargs.get("judge_receipt")
        captured["response_schema"] = kwargs.get("response_schema")
        out = competencies_x1d._mocked(provider_key, input_hash)
        out.evaluator_mode = "MODEL_BACKED"
        out.provider_status = "MODEL_BACKED_PASS"
        out.provider_available = True
        out.pass_ = True
        return out

    monkeypatch.setattr(competencies_x1d, "resolve_x1d_provider_credentials", lambda _k, _e: ("fake-key", ["GOOGLE_API_KEY"]))
    monkeypatch.setattr(competencies_x1d, "_call_gemini", _fake_call_gemini)

    fact_packet = {
        "allowed_fact_ids": ["bul_unify_001"],
        "facts": [{"fact_id": "bul_unify_001", "claim_text": "Scaled governed agentic platform."}],
    }
    outputs = competencies_x1d.run_competencies_judges(
        competencies=[{"category_label": "AI Architecture", "terms": [{"text": "Agentic Control Planes", "source_fact_id": "bul_unify_001", "source_fact_ids": ["bul_unify_001"]}]}],
        claim_ledger=[{"claim_text": "Agentic Control Planes", "source_fact_ids": ["bul_unify_001"]}],
        judge_keys=["gemini_pro"],
        mode="blocked_if_unavailable",
        artifact_base=tmp_path,
        allowed_fact_packet=fact_packet,
        deterministic_gate_summary={"pass": True, "failed_gates": []},
        **t_kw,
    )
    assert len(outputs) == 1 and outputs[0].pass_ is True
    assert "BRIEFING: Emphasize governed platforms." in captured["prompt"]
    assert "ALLOWED_FACT_PACKET:" in captured["prompt"]
    assert "Scaled governed agentic platform." in captured["prompt"]
    assert captured["response_schema"] == competencies_x1d.COMPETENCIES_JUDGE_RESPONSE_SCHEMA
    assert captured["judge_receipt"]["judge_packet_hash"]
    packet_file = tmp_path / "competencies_judge_packet.json"
    assert packet_file.is_file()
    pkt = json.loads(packet_file.read_text(encoding="utf-8"))
    assert pkt["targeting_context"]["briefing"] == "Emphasize governed platforms."
    assert pkt["allowed_fact_packet"] == fact_packet


def test_evra_competencies_6_to_8_and_headline_prefixes_with_fact_prompts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-live-key")
    captured_prompts: list[str] = []

    comps_6 = [
        {
            "category": f"Cat {i}",
            "category_label": f"Cat {i}",
            "competency_bundle_id": f"bundle_{i}",
            "terms": [{"term": f"Skill {i}A", "text": f"Skill {i}A", "source_fact_ids": [f"fact_{i}"]}],
        }
        for i in range(6)
    ]
    repaired_7 = {
        "repaired_competencies": [
            {"category": f"Cat {i}", "skills": [f"Grounded Skill {i}A", f"Grounded Skill {i}B"]}
            for i in range(7)
        ]
    }

    def _fake_comp_llm(_sec: str, prompt: str, **_kw: Any) -> dict[str, Any]:
        captured_prompts.append(prompt)
        return repaired_7

    monkeypatch.setattr(evra, "_call_llm_repair", _fake_comp_llm)
    updated, receipt = evra.repair_section_with_executive_voice_agent(
        section_id="competencies",
        candidate_data={"competencies": comps_6},
        diagnostic={"repair_needed": True, "findings": ["Need 7 categories"]},
        allowed_facts=[{"fact_id": "fact_0", "claim_text": "Built governed agentic runtime."}],
        targeting_context={
            "target_title": "Head of AI",
            "target_company": "Anthropic",
            "jd_text": "Partner AI systems",
            "briefing": "Prioritize partner architecture",
        },
        artifact_dir=tmp_path,
        mock_mode=False,
    )
    assert receipt.repair_succeeded is True
    assert len(updated["competencies"]) == 7
    assert updated["competencies"][6]["terms"][0]["source_fact_id"]
    assert updated["competencies"][6]["terms"][0]["source_fact_ids"]
    assert updated["competencies"][6]["terms"][0]["text"] == "Grounded Skill 6A"
    assert "Built governed agentic runtime." in captured_prompts[0]
    assert "Prioritize partner architecture" in captured_prompts[0]

    def _fake_hl_llm(_sec: str, prompt: str, **_kw: Any) -> dict[str, Any]:
        captured_prompts.append(prompt)
        return {
            "repaired_headline": "SVP Agentic Transformation | Governed AI Platforms | Cloud Modernization | Regulated Delivery"
        }

    monkeypatch.setattr(evra, "_call_llm_repair", _fake_hl_llm)
    hl_upd, hl_rec = evra.repair_section_with_executive_voice_agent(
        section_id="headline",
        candidate_data={"headline_line": "SVP Engineering | Old | Old2 | Old3"},
        diagnostic={"repair_needed": True, "findings": ["Improve headline"]},
        allowed_facts=[{"fact_id": "fact_1", "claim_text": "Led regulated cloud delivery."}],
        targeting_context={"target_title": "SVP AI", "target_company": "Truist", "jd_text": "JD", "briefing": "Brief"},
        artifact_dir=tmp_path,
        mock_mode=False,
    )
    assert hl_rec.repair_succeeded is True
    assert hl_upd["headline_line"].startswith("SVP Agentic Transformation |")
    assert "Led regulated cloud delivery." in captured_prompts[1]


def test_headline_healing_reverts_when_rejudge_score_does_not_improve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.claim_ledger.headline_claim_ledger import build_headline_text_claim_coverage
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent
    from apps_rg.runtime.sections.headline_lane import (
        HEADLINE_WORD_MAX,
        HEADLINE_WORD_MIN,
        _coerce_segment_claim_ledger_rows,
        build_headline_canonical_claim_ledger_v2,
        evaluate_headline_literal_grounding,
        has_valid_headline_prefix,
        headline_resume_native_clarity_report,
        headline_word_count,
        normalize_headline_claim_ledger,
        recite_canonical_segments_to_bundle_facts,
        repair_headline_segment_citations_for_grounding,
    )
    from apps_rg.runtime.sections.lane_perf_sync_helpers import (
        execute_headline_judges_with_final_display_gate,
    )

    orig_hl = "SVP Engineering | Governed Agentic Platforms | Distributed Cloud Infrastructure | Regulated Delivery"
    cand_hl = "SVP Agentic Transformation | Governed Cloud Architecture | Enterprise Risk Controls | Regulated Scale"
    allowed = {"bul_unify_001"}
    orig_ledger = _coerce_segment_claim_ledger_rows(orig_hl, ["bul_unify_001"])
    runtime_payload = {
        "selected_fact_plan": {
            "facts": [
                {
                    "fact_id": "bul_unify_001",
                    "claim_text": "Governed agentic platforms, distributed cloud infrastructure, enterprise risk controls, and regulated scale delivery.",
                }
            ]
        },
        "jd_text": "Lead AI",
        "briefing": "Brief",
    }

    monkeypatch.setattr(
        ExecutiveVoiceRepairAgent,
        "repair_section_with_executive_voice_agent",
        lambda **_kw: (
            {"headline_line": cand_hl, "claim_ledger": orig_ledger},
            SimpleNamespace(repair_succeeded=True),
        ),
    )
    judge_scores = iter([3.8, 3.6])  # second judge rank is worse

    def _spy_judges(**_kw: Any) -> list[JudgeOutput]:
        sc = next(judge_scores)
        return [
            JudgeOutput(
                judge_id="j1",
                provider_name="Gemini",
                provider_key="gemini_pro",
                evaluator_mode="MODEL_BACKED",
                provider_status="MODEL_BACKED_FAIL",
                model_name="gemini-4-argon-medium",
                provider_available=True,
                provider_blocked=False,
                exact_provider_error=None,
                score=sc,
                normalized_score=sc / 5.0,
                threshold=4.0,
                normalized_threshold=0.8,
                pass_=False,
                findings=["Needs polish"],
            )
        ]

    final_hl, final_ledger, _canon, _cov, final_x1d = execute_headline_judges_with_final_display_gate(
        headline_line=orig_hl,
        parsed={"headline_line": orig_hl, "claim_ledger": orig_ledger},
        parsed_for_x2={"headline_line": orig_hl},
        claim_ledger=orig_ledger,
        canon_doc={"original": True},
        coverage={"original": True},
        allowed_fact_ids=allowed,
        proof_pool_metadata=None,
        runtime_payload=runtime_payload,
        judge_keys=["gemini_pro"],
        companion_context="",
        judge_mode="mocked",
        judge_allowed_mock=True,
        artifact_dir=tmp_path,
        allowed_fact_packet=[],
        target_title="SVP",
        target_company="Truist",
        word_min=HEADLINE_WORD_MIN,
        word_max=HEADLINE_WORD_MAX,
        word_count_fn=headline_word_count,
        has_valid_prefix_fn=has_valid_headline_prefix,
        clarity_report_fn=headline_resume_native_clarity_report,
        evaluate_grounding_fn=evaluate_headline_literal_grounding,
        coerce_segment_ledger_fn=_coerce_segment_claim_ledger_rows,
        recite_bundle_fn=recite_canonical_segments_to_bundle_facts,
        repair_grounding_fn=repair_headline_segment_citations_for_grounding,
        normalize_ledger_fn=normalize_headline_claim_ledger,
        build_canon_fn=build_headline_canonical_claim_ledger_v2,
        build_coverage_fn=build_headline_text_claim_coverage,
        run_judges_fn=_spy_judges,
        write_json_fn=lambda p, d: p.write_text(json.dumps(d), encoding="utf-8"),
    )
    assert final_hl == orig_hl
    assert final_ledger == orig_ledger
    assert final_x1d[0]["score"] == 3.8
    gate_doc = json.loads((tmp_path / "headline_final_display_pre_judge_gate.json").read_text(encoding="utf-8"))
    assert gate_doc["voice_repair_rejected"]["reason"] == "rejudge_not_improved"


def test_cosine_035_alignment_in_ibm_narrative_diagnostic_and_pa() -> None:
    from apps_rg.runtime.sections.ibm_narrative_lane_runtime import _cosine_echo_diagnostic_summary
    from apps_rg.runtime.sections.ibm_narrative_pa import _theme_budget_block

    diag = _cosine_echo_diagnostic_summary(
        "Led enterprise cloud architecture across regulated financial platforms.",
        ["Led enterprise cloud architecture and DevSecOps pipelines across regulated banking."],
    )
    assert "<=0.3500" in diag
    assert "<=0.2800" not in diag
    pa_block = _theme_budget_block("- bul_ibm_001: Led cloud platform delivery.")
    assert "<= 0.35" in pa_block
    assert "<= 0.28" not in pa_block


def test_unify_narrative_line979_runs_x1d_rewrite_after_pre_judge_rewrite_and_preserves_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.section_repair_ledger import init_ledger
    from apps_rg.runtime.sections import unify_narrative_lane as unl

    init_ledger(tmp_path, section_id="unify_narrative", run_id="run-unify-979")
    usage_path = tmp_path / "section_input_usage_ledger.json"
    usage_path.write_text('{"initial": true}\n', encoding="utf-8")

    # Draft 1 fails consulting phrase & technical specificity -> triggers pre-judge rewrite
    initial_parsed = {
        "narrative_sentence": "Owned Unify Consulting platform architecture, converting consulting delivery into services.",
        "claim_ledger": [{"claim_text": "Owned Unify Consulting platform architecture", "source_fact_ids": ["bul_unify_001"]}],
    }
    # Pre-judge rewrite succeeds X2 ("Drove..." + explicit mechanism "GraphRAG")
    pre_rw_narr = "Drove GraphRAG platform commercialization and governed agentic runtime architecture at Unify Consulting for regulated financial institutions."
    pre_rw_raw = json.dumps(
        {
            "narrative_sentence": pre_rw_narr,
            "claim_ledger": [{"claim_text": pre_rw_narr, "source_fact_ids": ["bul_unify_001"]}],
        }
    )
    # X1D judge-feedback rewrite produces worse score so X1D rewrite rejects, MUST keep pre_judge_accepted=True!
    x1d_rw_narr = "Spearheaded GraphRAG platform roadmap and governed agentic runtime systems at Unify Consulting for enterprise accounts."
    x1d_rw_raw = json.dumps(
        {
            "narrative_sentence": x1d_rw_narr,
            "claim_ledger": [{"claim_text": x1d_rw_narr, "source_fact_ids": ["bul_unify_001"]}],
        }
    )
    responses = iter([pre_rw_raw, x1d_rw_raw])
    monkeypatch.setattr(
        "apps_rg.runtime.providers.section_provider_call.call_section_model_provider",
        lambda *_a, **_k: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="claude-sonnet-5-5-medium",
            raw_model_output=next(responses),
            provider_response={},
        ),
    )
    judge_scores = iter([3.7, 3.5])
    monkeypatch.setattr(
        unl,
        "run_unify_narrative_judges",
        lambda **_kw: [
            JudgeOutput(
                judge_id="j1",
                provider_name="Gemini",
                provider_key="gemini_pro",
                evaluator_mode="MODEL_BACKED",
                provider_status="MODEL_BACKED_FAIL",
                model_name="gemini-4-argon-medium",
                provider_available=True,
                provider_blocked=False,
                exact_provider_error=None,
                score=next(judge_scores),
                normalized_score=0.74,
                threshold=4.0,
                normalized_threshold=0.8,
                pass_=False,
                findings=["Need stronger commercial specificity"],
            )
        ],
    )

    out_raw, out_parsed, out_x1d, accepted = unl.apply_unify_narrative_in_lane_healing(
        messages=[{"role": "user", "content": "Draft"}],
        provider_payload={"model": "claude-sonnet-5-5-medium"},
        provider_name="external_claude",
        raw_output="{}",
        parsed=initial_parsed,
        runtime_payload={
            "run_id": "run-unify-979",
            "allowed_fact_ids": ["bul_unify_001"],
            "selected_fact_plan": {"facts": [{"fact_id": "bul_unify_001"}]},
        },
        artifact_dir=tmp_path,
        runtime_generation_status="REAL_LLM",
        companion_text="",
        judge_keys=["gemini_pro"],
        judge_mode="blocked_if_unavailable",
        allowed_fact_packet={"allowed_fact_ids": ["bul_unify_001"], "facts": []},
        targeting_context={"target_title": "Head of AI"},
    )
    assert accepted is True
    assert out_raw == pre_rw_raw
    assert out_parsed is not None and out_parsed["narrative_sentence"] == pre_rw_narr
    assert out_x1d[0]["score"] == 3.7
    receipt = json.loads((tmp_path / "unify_narrative_judge_rewrite_receipt.json").read_text(encoding="utf-8"))
    assert receipt["pre_judge_rewrite"]["attempted"] is True
    assert receipt["pre_judge_rewrite"]["accepted"] is True
    assert receipt["judge_feedback_rewrite"]["attempted"] is True
    assert receipt["judge_feedback_rewrite"]["accepted"] is False
    assert receipt["judge_feedback_rewrite"]["rejected_reason"] == "rejudge_not_improved"


def _make_fake_pool(section_id: str, facts: list[dict[str, Any]], allowed: Any) -> SimpleNamespace:
    return SimpleNamespace(
        bullet_rows=facts,
        allowed_fact_ids=allowed,
        selected_fact_plan={"facts": facts},
        proof_pool_metadata={},
        proof_pool_digest="dig",
        proof_pool_ref="ref",
        proof_source="augmented_skills_graph",
        broad_skills_ledger_ref="",
        broad_skills_ledger_digest="",
        broad_skills_ledger_present=False,
        srfs_ref="",
        srfs_present=False,
        base_resume_override_used=False,
        base_resume_fallback_used=False,
        targeting_inputs_used={},
        section=section_id,
    )


def test_role_episode_rewrite_preserves_generation_meta_and_selection_on_reject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections import role_episode_lane as rel_mod
    from apps_rg.runtime.sections.role_episode import lane_config as lc
    from apps_rg.runtime.sections.role_episode import lane_generation as lg

    cfg = lc._ROLE_LANES["slalom_bullets"]
    sel_path = tmp_path / "bullet_pool_selection.json"
    orig_sel_doc = {
        "selections": [
            {"bullet_id": "bul_slalom_001", "bullet_text": "Original bullet 1", "source_fact_ids": ["bul_slalom_001"]}
        ],
        "source_path_by_slot": {"bul_slalom_001": "sc_path_0"},
    }
    sel_bytes = (json.dumps(orig_sel_doc, indent=2) + "\n").encode("utf-8")
    sel_path.write_bytes(sel_bytes)

    orig_gen_meta = {
        "generation_mode": "sc",
        "selection_mode": "sc_selected",
        "selection_gate": {"pass": True, "score": 0.9},
        "source_path_by_slot": {"bul_slalom_001": "sc_path_0"},
    }
    facts = [
        {"fact_id": "bul_slalom_001", "claim_text": "Led enterprise engineering practice for regulated utility with measurable delivery velocity."}
    ]
    base = {
        "candidate_name": "Candidate",
        "facts": {
            "employment": [
                {"employer": "Slalom Consulting", "title": "Senior Director", "start_date": "2020", "end_date": "2023", "bullets": []}
            ]
        },
    }
    pool = _make_fake_pool("slalom_bullets", facts, ["bul_slalom_001"])

    _gen_fn = lambda **_k: (
        ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="claude-sonnet-5-5-medium",
            raw_model_output='{"bullets":[{"bullet_id":"bul_slalom_001","bullet_text":"Orig","source_fact_ids":["bul_slalom_001"]}]}',
            provider_response={},
        ),
        '{"bullets":[{"bullet_id":"bul_slalom_001","bullet_text":"Orig","source_fact_ids":["bul_slalom_001"]}]}',
        {"bullets": [{"bullet_id": "bul_slalom_001", "bullet_text": "Orig", "source_fact_ids": ["bul_slalom_001"]}]},
        "",
        orig_gen_meta,
    )
    _mat_fn = lambda **_k: (
        [{"bullet_id": "bul_slalom_001", "bullet_text": "Materialized bullet text.", "source_fact_ids": ["bul_slalom_001"]}],
        {"generation_method": "llm_selected_graph_bound_surface", "llm_output_used": True, "source_fact_ids": ["bul_slalom_001"], "final_materialized_acceptance_ok": True},
    )
    _x2_fn = lambda **_k: [{"gate_id": "g1", "pass": True}]
    _judge_fn = lambda **_k: [{"judge_id": "j1", "provider_key": "gemini_pro", "pass": False, "score": 3.5, "advisory_only": False}]
    for mod in (lg, rel_mod):
        monkeypatch.setattr(mod, "rel_posix", lambda *_a, **_k: "artifacts/test/slalom")
        monkeypatch.setattr(mod, "apply_proof_pool_to_usage_ledger", lambda doc, _p: doc)
        monkeypatch.setattr(mod, "generate_bullet_lane_with_sc_and_claude", _gen_fn)
        monkeypatch.setattr(mod, "_materialize_bullet_generation", _mat_fn)
        monkeypatch.setattr(mod, "run_role_episode_x2_gates", _x2_fn)
        monkeypatch.setattr(mod, "_judge_rows", _judge_fn)
    monkeypatch.setattr(
        "apps_rg.runtime.providers.section_provider_call.call_section_model_provider",
        lambda *_a, **_k: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="claude-sonnet-5-5-medium",
            raw_model_output='{"bullets":[{"bullet_id":"bul_slalom_001","bullet_text":"Rewritten bullet text.","source_fact_ids":["bul_slalom_001"]}]}',
            provider_response={},
        ),
    )

    res = lg.run_role_episode_generation_stage(
        SimpleNamespace(
            provider="external_claude",
            temperature=0.35,
            target_title="SVP",
            target_company="Truist",
            jd_text="JD",
            briefing="Brief",
            mock_judges=False,
        ),
        {
            "sid": "slalom_bullets",
            "cfg": cfg,
            "max_output_tokens": 1200,
            "run_id": "run-re-1",
            "artifact_dir": tmp_path,
            "runtime_payload": {"run_id": "run-re-1", "jd_text": "JD", "target_title": "SVP", "target_company": "Truist", "briefing": "Brief"},
            "pool": pool,
            "base": base,
            "selected_fact_plan": {"facts": facts},
            "allowed_fact_ids": ["bul_slalom_001"],
            "facts": facts,
            "companion_text": "",
            "prompt_text": "Write bullets",
            "prompt_hash": "ph" * 10,
            "compiled_obj": SimpleNamespace(system_preamble="sys"),
            "generation_model": "claude-sonnet-5-5-medium",
        },
        provider_gateway_fn=lambda *_a, **_k: None,
    )
    assert sel_path.read_bytes() == sel_bytes
    assert not (tmp_path / "bullet_pool_selection_pre_rewrite.json").exists()
    assert res["l2"]["generation_meta"] == orig_gen_meta
    assert orig_gen_meta["selection_mode"] == "sc_selected"


def test_x2_before_x1d_skips_judges_and_adjudication_when_pre_x2_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections.unify_bullets import stage_generation as unify_sg
    from apps_rg.runtime.sections.ibm_bullets import stage_generation as ibm_sg
    from apps_rg.runtime.sections import unify_bullets_lane as ubl
    from apps_rg.runtime.sections import ibm_bullets_lane as ibl

    # 1. unify_bullets stage_generation skips run_unify_bullets_judges when pre_x2 fails
    unify_judge_calls: list[Any] = []
    monkeypatch.setattr(
        unify_sg,
        "generate_bullet_lane_with_sc_and_claude",
        lambda **_k: (
            ProviderResult(
                provider_requested="external_claude",
                provider_attempted=True,
                provider_available=True,
                exact_provider_error=None,
                runtime_generation_status="REAL_LLM",
                model="claude-sonnet-5-5-medium",
                raw_model_output='{"bullets":[{"bullet_id":"bul_unify_001","bullet_text":"Short.","source_fact_ids":["bul_unify_001"]}],"claim_ledger":[{"claim_text":"Short.","source_fact_ids":["bul_unify_001"]}]}',
                provider_response={},
            ),
            '{"bullets":[{"bullet_id":"bul_unify_001","bullet_text":"Short.","source_fact_ids":["bul_unify_001"]}],"claim_ledger":[{"claim_text":"Short.","source_fact_ids":["bul_unify_001"]}]}',
            {"bullets": [{"bullet_id": "bul_unify_001", "bullet_text": "Short.", "source_fact_ids": ["bul_unify_001"]}], "claim_ledger": [{"claim_text": "Short.", "source_fact_ids": ["bul_unify_001"]}]},
            "",
            {"selection_mode": "sc"},
        ),
    )
    monkeypatch.setattr(unify_sg, "rel_posix", lambda *_a, **_k: "artifacts/test/unify")
    for m in (unify_sg, ubl):
        monkeypatch.setattr(m, "run_unify_bullets_x2_gates", lambda **_k: [SimpleNamespace(to_dict=lambda: {"gate_id": "x2_unify_fail", "pass": False})])
        monkeypatch.setattr(m, "run_unify_bullets_judges", lambda **_k: unify_judge_calls.append(1) or [])
        monkeypatch.setattr(m, "apply_proof_pool_to_usage_ledger", lambda doc, _p: doc)
    u_dir = tmp_path / "unify"
    u_dir.mkdir()
    u_ctx = unify_sg.run_unify_generation_and_x2_stage(
        SimpleNamespace(provider="external_claude", temperature=0.35, mock_judges=False),
        {
            "artifact_dir": u_dir,
            "base": {},
            "pool": _make_fake_pool("unify_bullets", [], {"bul_unify_001"}),
            "unify_header": {},
            "allowed_fact_ids": {"bul_unify_001"},
            "selected_fact_plan": {"facts": []},
            "runtime_payload": {"run_id": "r1", "jd_text": "JD", "selected_fact_plan": {"facts": []}},
            "input_payload_hash": "iph",
            "section_compiled": SimpleNamespace(apps_rg_prompt_template_ref="ref", artifact=SimpleNamespace(template_id="tpl")),
            "messages": [{"role": "user", "content": "u"}],
            "prompt_hash": "ph",
            "section_model": "claude-sonnet-5-5-medium",
            "provider_payload": {"model": "claude-sonnet-5-5-medium"},
            "provider_request_data": {"model": "claude-sonnet-5-5-medium"},
        },
    )
    assert unify_judge_calls == []
    unify_proof_rows = [j for j in u_ctx["x1d"] if not j.get("advisory_only")]
    assert unify_proof_rows and all(j["evaluator_mode"] == "BLOCKED_PRE_JUDGE_GATE" for j in unify_proof_rows)

    # 2. ibm_bullets stage_generation skips run_ibm_bullets_judges when pre_x2 fails
    ibm_judge_calls: list[Any] = []
    monkeypatch.setattr(
        ibm_sg,
        "generate_bullet_lane_with_sc_and_claude",
        lambda **_k: (
            ProviderResult(
                provider_requested="external_claude",
                provider_attempted=True,
                provider_available=True,
                exact_provider_error=None,
                runtime_generation_status="REAL_LLM",
                model="claude-sonnet-5-5-medium",
                raw_model_output='{"bullets":[{"bullet_id":"bul_ibm_001","bullet_text":"Short.","source_fact_ids":["bul_ibm_001"]}],"claim_ledger":[{"claim_text":"Short.","source_fact_ids":["bul_ibm_001"]}]}',
                provider_response={},
            ),
            '{"bullets":[{"bullet_id":"bul_ibm_001","bullet_text":"Short.","source_fact_ids":["bul_ibm_001"]}],"claim_ledger":[{"claim_text":"Short.","source_fact_ids":["bul_ibm_001"]}]}',
            {"bullets": [{"bullet_id": "bul_ibm_001", "bullet_text": "Short.", "source_fact_ids": ["bul_ibm_001"]}], "claim_ledger": [{"claim_text": "Short.", "source_fact_ids": ["bul_ibm_001"]}]},
            "",
            {"selection_mode": "sc"},
        ),
    )
    monkeypatch.setattr(ibm_sg, "rel_posix", lambda *_a, **_k: "artifacts/test/ibm")
    for m in (ibm_sg, ibl):
        monkeypatch.setattr(m, "run_ibm_bullets_x2_gates", lambda **_k: [SimpleNamespace(to_dict=lambda: {"gate_id": "x2_ibm_fail", "pass": False})])
        monkeypatch.setattr(m, "run_ibm_bullets_judges", lambda **_k: ibm_judge_calls.append(1) or [])
        monkeypatch.setattr(m, "apply_proof_pool_to_usage_ledger", lambda doc, _p: doc)
    i_dir = tmp_path / "ibm"
    i_dir.mkdir()
    i_ctx = ibm_sg.run_ibm_generation_and_x2_stage(
        SimpleNamespace(provider="external_claude", temperature=0.35, mock_judges=False, jd_text="JD", x1d_judges=""),
        {
            "artifact_dir": i_dir,
            "base": {},
            "pool": _make_fake_pool("ibm_bullets", [], {"bul_ibm_001"}),
            "ibm_header": {},
            "ibm_facts": [],
            "allowed_fact_ids": {"bul_ibm_001"},
            "selected_fact_plan": {"facts": []},
            "runtime_payload": {"run_id": "r1", "jd_text": "JD", "selected_fact_plan": {"facts": []}},
            "input_payload_hash": "iph",
            "section_compiled": SimpleNamespace(apps_rg_prompt_template_ref="ref", artifact=SimpleNamespace(template_id="tpl")),
            "messages": [{"role": "user", "content": "u"}],
            "prompt_hash": "ph",
            "section_model": "claude-sonnet-5-5-medium",
            "provider_payload": {"model": "claude-sonnet-5-5-medium"},
            "provider_request_data": {"model": "claude-sonnet-5-5-medium"},
            "tagged": {"model": "claude-sonnet-5-5-medium"},
        },
    )
    assert ibm_judge_calls == []
    ibm_proof_rows = [j for j in i_ctx["x1d"] if not j.get("advisory_only")]
    assert ibm_proof_rows and all(j["evaluator_mode"] == "BLOCKED_PRE_JUDGE_GATE" for j in ibm_proof_rows)

    # 3. Verify adjudicator escalation guard in unify_bullets_lane and ibm_bullets_lane source checks (not _x2_failed_ids)
    assert "(not _x2_failed_ids)" in Path(ubl.__file__).read_text(encoding="utf-8")
    assert "(not _x2_failed_ids)" in Path(ibl.__file__).read_text(encoding="utf-8")


def test_competencies_lane_x2_before_x1d_and_revert_on_worse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections import competencies_lane_execution as cle
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as ev_mod
    from apps_rg.runtime.judges import competencies_x1d as comp_x1d_mod
    from apps_rg.runtime.c0 import section_proof_loader as spl

    cle._ensure_helpers_hydrated()
    facts = [
        {"fact_id": f"bul_unify_00{i}", "claim_text": f"Led enterprise AI architecture program {i}."}
        for i in range(1, 7)
    ]
    base_comps = [
        {
            "category": f"Cat {i}",
            "category_label": f"Cat {i}",
            "terms": [
                {"term": f"Platform Architecture {i}", "text": f"Platform Architecture {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
                {"term": f"Governance Controls {i}", "text": f"Governance Controls {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
                {"term": f"Cloud Engineering {i}", "text": f"Cloud Engineering {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
            ],
        }
        for i in range(1, 7)
    ]
    repaired_comps = [
        {
            "category": f"Repaired Cat {i}",
            "category_label": f"Repaired Cat {i}",
            "terms": [
                {"term": f"Agentic Control Planes {i}", "text": f"Agentic Control Planes {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
                {"term": f"Deterministic Gates {i}", "text": f"Deterministic Gates {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
                {"term": f"Lineage Governance {i}", "text": f"Lineage Governance {i}", "source_fact_id": f"bul_unify_00{i}", "source_fact_ids": [f"bul_unify_00{i}"]},
            ],
        }
        for i in range(1, 7)
    ]

    monkeypatch.setattr(
        spl,
        "load_section_proof_for_lane",
        lambda **_k: (
            _make_fake_pool("competencies", facts, {f["fact_id"] for f in facts}),
            {"candidate_name": "Candidate"},
            tmp_path / "base.json",
            "bh",
            None,
        ),
    )
    monkeypatch.setattr("apps_rg.runtime.sections.upstream_evidence_block.wire_spine_c0_fec_or_block", lambda **_k: None)
    monkeypatch.setattr(cle, "compile_competencies_prompt", lambda *_a, **_k: SimpleNamespace(
        section_id="competencies",
        apps_rg_prompt_template_ref="ref",
        artifact=SimpleNamespace(template_id="tpl", prompt_hash="ph", slot_count=6, messages=[{"role": "user", "content": "u"}]),
    ))
    monkeypatch.setattr(cle, "rel_posix", lambda *_a, **_k: "artifacts/test/comp")
    monkeypatch.setattr("apps_rg.runtime.c0.section_proof_loader.apply_proof_pool_to_usage_ledger", lambda doc, _p: doc)
    monkeypatch.setattr(cle, "competencies_provider_preflight_disabled", lambda: True)
    monkeypatch.setattr(
        "apps_rg.runtime.reasoning.bullet_lane_generation.generate_bullet_lane_with_sc_and_claude",
        lambda **_k: (
            ProviderResult(
                provider_requested="external_claude",
                provider_attempted=True,
                provider_available=True,
                exact_provider_error=None,
                runtime_generation_status="REAL_LLM",
                model="claude-sonnet-5-5-medium",
                raw_model_output=json.dumps({"competencies": base_comps}),
                provider_response={},
            ),
            json.dumps({"competencies": base_comps}),
            {"competencies": base_comps, "claim_ledger": [{"claim_text": "Platform Architecture 1", "source_fact_ids": ["bul_unify_001"]}]},
            "",
            {"selection_mode": "sc"},
        ),
    )
    monkeypatch.setattr(cle, "find_bullet_restatement_term", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "collapse_duplicate_competency_terms", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "repair_structured_competencies_source_facts", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "coerce_structured_competencies_resume_support", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "dedupe_structured_competency_terms", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "reduce_competency_keyword_stuffing", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "canonicalize_competency_terms_for_proof", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "expand_structured_competencies_min_two_terms", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "prune_claim_ledger_bullet_paste", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "apps_rg.runtime.sections.competencies_capability_projection.finalize_competencies_v3_output",
        lambda p, **_k: p,
    )
    monkeypatch.setattr("apps_rg.runtime.section_l2_lane_integration.prepare_section_l2_before_provider", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_l2_lane_integration.finalize_section_l2_after_output", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_runtime_exhaust_lane_integration.finalize_section_runtime_exhaust_before_l6", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_runtime_exhaust_lane_integration.gate_section_l6_shadow_after_exhaust", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.spine.exit_lane_hooks.finalize_section_exit_after_l2", lambda *_a, **_k: None)
    monkeypatch.setattr(cle, "finalize_runtime_proof_run", lambda *_a, **_k: None)

    # Case A: pre-X2 fails -> skip run_competencies_judges & emit BLOCKED_PRE_JUDGE_GATE
    comp_judge_calls: list[Any] = []
    monkeypatch.setattr(comp_x1d_mod, "run_competencies_judges", lambda **kw: comp_judge_calls.append(kw) or [])
    monkeypatch.setattr(ev_mod, "repair_section_with_executive_voice_agent", lambda **_k: ({}, SimpleNamespace(repair_attempted=False, repair_succeeded=False)))
    monkeypatch.setattr(
        cle,
        "run_competencies_x2_gates",
        lambda **_k: [SimpleNamespace(to_dict=lambda: {"gate_id": "x2_comp_fail", "pass": False, "severity": "BLOCK"})],
    )
    dir_a = tmp_path / "comp_a"
    dir_a.mkdir()
    res_a = cle.run_competencies_lane_execution(
        SimpleNamespace(
            provider="external_claude",
            temperature=0.35,
            target_title="Head of AI",
            target_company="Truist",
            jd_text="JD",
            briefing="Brief",
            base_resume="",
            mock_judges=False,
            allow_non_allow_exit_zero=False,
            allow_test_mock_judges=False,
            allow_test_mock_provider=False,
            x1d_judges="gemini_pro",
        ),
        artifact_dir_override=dir_a,
        print_output=False,
    )
    assert comp_judge_calls == []
    x1d_a = json.loads((dir_a / "x1d_llm_judge_outputs.json").read_text(encoding="utf-8"))["judges"]
    assert x1d_a[0]["evaluator_mode"] == "BLOCKED_PRE_JUDGE_GATE"

    # Case B: pre-X2 passes -> initial judge fails -> EVRA repairs -> re-judge score is WORSE -> revert!
    monkeypatch.setattr(
        cle,
        "run_competencies_x2_gates",
        lambda **kw: [
            SimpleNamespace(to_dict=lambda: {"gate_id": "x2_comp_ok", "pass": True, "severity": "BLOCK"}),
            SimpleNamespace(to_dict=lambda: {"gate_id": "x2_x1d_required_judges_present", "pass": bool(kw.get("x1d_judges")), "severity": "BLOCK"}),
        ],
    )
    scores_b = iter([3.8, 3.5])

    def _fake_comp_judge(**kw: Any) -> list[JudgeOutput]:
        comp_judge_calls.append(kw)
        sc = next(scores_b)
        return [
            JudgeOutput(
                judge_id="x1d_gemini_pro_competencies",
                provider_name="Gemini",
                provider_key="gemini_pro",
                evaluator_mode="MODEL_BACKED",
                provider_status="MODEL_BACKED_FAIL",
                model_name="gemini-4-argon-medium",
                provider_available=True,
                provider_blocked=False,
                exact_provider_error=None,
                score=sc,
                normalized_score=sc / 5.0,
                threshold=4.0,
                normalized_threshold=0.8,
                pass_=False,
                findings=["Needs specificity"],
            )
        ]

    monkeypatch.setattr(comp_x1d_mod, "run_competencies_judges", _fake_comp_judge)
    monkeypatch.setattr(
        ev_mod,
        "repair_section_with_executive_voice_agent",
        lambda **_k: (
            {"competencies": repaired_comps},
            SimpleNamespace(repair_attempted=True, repair_succeeded=True),
        ),
    )
    dir_b = tmp_path / "comp_b"
    dir_b.mkdir()
    res_b = cle.run_competencies_lane_execution(
        SimpleNamespace(
            provider="external_claude",
            temperature=0.35,
            target_title="Head of AI",
            target_company="Truist",
            jd_text="JD",
            briefing="Brief",
            base_resume="",
            mock_judges=False,
            allow_non_allow_exit_zero=False,
            allow_test_mock_judges=False,
            allow_test_mock_provider=False,
            x1d_judges="gemini_pro",
        ),
        artifact_dir_override=dir_b,
        print_output=False,
    )
    assert len(comp_judge_calls) == 2
    assert comp_judge_calls[0]["allowed_fact_packet"]["allowed_fact_ids"] == [f"bul_unify_00{i}" for i in range(1, 7)]
    assert comp_judge_calls[0]["targeting_context"]["briefing"] == "Brief"
    comps_out_b = json.loads((dir_b / "competencies_output.json").read_text(encoding="utf-8"))
    assert comps_out_b[0]["category_label"] == "Cat 1"
    x1d_b = json.loads((dir_b / "x1d_llm_judge_outputs.json").read_text(encoding="utf-8"))["judges"]
    assert x1d_b[0]["score"] == 3.8
    vr_b = json.loads((dir_b / "competencies_voice_repair_receipt.json").read_text(encoding="utf-8"))
    assert vr_b["accepted"] is False
    assert vr_b["rejected_reason"] == "rejudge_not_improved"


def test_ibm_narrative_lane_x2_before_x1d_skips_judges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections import ibm_narrative_lane_execution as ine
    from apps_rg.runtime.c0 import section_proof_loader as spl

    ine._ensure_helpers_hydrated()
    facts = [{"fact_id": "bul_ibm_001", "claim_text": "Led cloud modernization at IBM."}]
    monkeypatch.setattr(
        spl,
        "load_section_proof_for_lane",
        lambda **_k: (
            _make_fake_pool("ibm_narrative", facts, {"bul_ibm_001"}),
            {"candidate_name": "Candidate", "facts": {"employment": [{"employer": "IBM", "title": "Partner", "bullets": [{"bullet_id": "bul_ibm_001", "text": "Led cloud modernization."}]}]}},
            tmp_path / "base.json",
            "bh",
            None,
        ),
    )
    monkeypatch.setattr(ine, "rel_posix", lambda *_a, **_k: "artifacts/test/ibm_narr")
    monkeypatch.setattr("apps_rg.runtime.c0.section_proof_loader.apply_proof_pool_to_usage_ledger", lambda doc, _p: doc)
    monkeypatch.setattr(ine, "load_companion_ibm_bullets_context", lambda: {"status": "FINALIZED", "text": "- bul_ibm_001: Led cloud modernization."})
    monkeypatch.setattr(ine, "resolve_effective_lane_l2_path", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.sections.upstream_evidence_block.wire_spine_c0_fec_or_block", lambda **_k: None)
    monkeypatch.setattr(ine, "compile_ibm_narrative_prompt", lambda *_a, **_k: SimpleNamespace(
        section_id="ibm_narrative",
        apps_rg_prompt_template_ref="ref",
        artifact=SimpleNamespace(template_id="tpl", prompt_hash="ph", slot_count=1, messages=[{"role": "user", "content": "u"}]),
    ))
    monkeypatch.setattr(ine, "run_ibm_narrative_judge_credentials_preflight", lambda *_a, **_k: {"preflight_blocked": False})
    monkeypatch.setattr("apps_rg.runtime.section_l2_lane_integration.prepare_section_l2_before_provider", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_l2_lane_integration.finalize_section_l2_after_output", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_runtime_exhaust_lane_integration.finalize_section_runtime_exhaust_before_l6", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.section_runtime_exhaust_lane_integration.gate_section_l6_shadow_after_exhaust", lambda *_a, **_k: None)
    monkeypatch.setattr("apps_rg.runtime.spine.exit_lane_hooks.finalize_section_exit_after_l2", lambda *_a, **_k: None)
    monkeypatch.setattr(ine, "finalize_runtime_proof_run", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "apps_rg.runtime.providers.section_provider_call.call_section_model_provider",
        lambda *_a, **_k: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="claude-sonnet-5-5-medium",
            raw_model_output='{"narrative_sentence":"Directed IBM cloud delivery, establishing lineage.","claim_ledger":[{"claim_text":"Directed IBM cloud delivery","source_fact_ids":["bul_ibm_001"]}]}',
            provider_response={},
        ),
    )
    monkeypatch.setattr(ine, "apply_ibm_narrative_theme_overpack_repair", lambda **kw: (kw["raw_output"], kw["parsed"], False))
    monkeypatch.setattr(
        ine,
        "run_ibm_narrative_x2_gates",
        lambda **_k: [SimpleNamespace(to_dict=lambda: {"gate_id": "x2_ibm_narr_fail", "pass": False})],
    )
    judge_calls: list[Any] = []
    monkeypatch.setattr(ine, "run_ibm_narrative_judges", lambda **kw: judge_calls.append(kw) or [])

    res = ine.run_ibm_narrative_lane_execution(
        SimpleNamespace(
            provider="external_openai",
            temperature=0.35,
            target_title="SVP",
            target_company="Truist",
            jd_text="JD",
            briefing="Brief",
            base_resume="",
            mock_judges=False,
            allow_non_allow_exit_zero=False,
            allow_test_mock_judges=False,
            allow_test_mock_provider=False,
            x1d_judges="gemini_pro",
        ),
        artifact_dir_override=tmp_path,
        print_output=False,
    )
    assert judge_calls == []
    ibm_x1d = json.loads((tmp_path / "x1d_llm_judge_outputs.json").read_text(encoding="utf-8"))["judges"]
    assert ibm_x1d[0]["evaluator_mode"] == "BLOCKED_PRE_JUDGE_GATE"


