"""Full-resume LLM coherence aggregation gate."""

from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.assembly.final_resume_x2 import gate_x2_full_resume_llm_coherence_aggregation
from apps_rg.runtime.assembly.full_resume_llm_coherence import (
    aggregate_full_resume_coherence,
    build_full_resume_evidence_packet,
    emit_full_resume_llm_coherence_review,
    run_full_resume_coherence_judges,
    _build_prompt,
)
from apps_rg.runtime.judges.executive_summary_x1d import (
    JudgeOutput,
    _filesystem_path,
    _write_artifact,
)


def _judge(*, key: str, pass_: bool, blocked: bool = False, mocked: bool = False) -> JudgeOutput:
    return JudgeOutput(
        judge_id=f"x1d_{key}_full_resume_coherence",
        provider_name=key,
        provider_key=key,
        evaluator_mode="MOCKED" if mocked else "LIVE",
        provider_status="MOCKED" if mocked else ("BLOCKED_PROVIDER_UNAVAILABLE" if blocked else "OK"),
        model_name="test",
        provider_available=not blocked and not mocked,
        provider_blocked=blocked,
        exact_provider_error="blocked" if blocked else None,
        rubric_version="test",
        input_hash="abc",
        output_hash="def",
        score=0.9 if pass_ else 0.2,
        score_scale="0_to_1",
        normalized_score=0.9 if pass_ else 0.2,
        threshold=0.8,
        normalized_threshold=0.8,
        pass_=pass_,
        decisive_failure=not pass_,
        findings=[],
        cited_sentence_indexes=[],
        remediation_suggestions=[],
    )


def test_provider_blocked_not_counted_as_pass():
    judges = [
        _judge(key="gemini_pro", pass_=True),
        _judge(key="openai_chatgpt", pass_=True, blocked=True),
        _judge(key="anthropic_claude", pass_=False, blocked=True),
    ]
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["model_backed_pass_count"] == 1
    assert agg["full_resume_coherence_pass"] is False


def test_quorum_pass_with_two_live_judges():
    judges = [
        _judge(key="gemini_pro", pass_=True),
        _judge(key="openai_chatgpt", pass_=True),
        _judge(key="anthropic_claude", pass_=False),
    ]
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is True


def test_two_judge_split_with_passing_mean_and_no_decisive_failure_passes_quorum():
    judges = [
        _judge(key="gemini_pro", pass_=True),  # score 0.9 >= 0.8
        JudgeOutput(
            judge_id="x1d_openai_chatgpt_full_resume_coherence",
            provider_name="openai_chatgpt",
            provider_key="openai_chatgpt",
            evaluator_mode="LIVE",
            provider_status="OK",
            model_name="gpt-5.6-sol",
            provider_available=True,
            provider_blocked=False,
            exact_provider_error=None,
            rubric_version="test",
            input_hash="abc",
            output_hash="def",
            score=3.7,
            score_scale="0_to_5",
            normalized_score=0.74,  # 3.7 / 5.0
            threshold=4.0,
            normalized_threshold=0.8,
            pass_=False,
            decisive_failure=False,  # soft fail, no decisive failure
            findings=["Dissenting commentary on role fit."],
            cited_sentence_indexes=[],
            remediation_suggestions=[],
        ),
    ]
    # Mean normalized score is (0.9 + 0.74) / 2 = 0.82 >= 0.80
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is True
    assert agg["decisive_reason"] == "quorum_pass_no_blockers"
    assert "judge_dissent:x1d_openai_chatgpt_full_resume_coherence" in agg["warnings"]


def test_two_judge_split_with_decisive_failure_blocks():
    judges = [
        _judge(key="gemini_pro", pass_=True),
        JudgeOutput(
            judge_id="x1d_openai_chatgpt_full_resume_coherence",
            provider_name="openai_chatgpt",
            provider_key="openai_chatgpt",
            evaluator_mode="LIVE",
            provider_status="OK",
            model_name="gpt-5.6-sol",
            provider_available=True,
            provider_blocked=False,
            exact_provider_error=None,
            rubric_version="test",
            input_hash="abc",
            output_hash="def",
            score=3.7,
            score_scale="0_to_5",
            normalized_score=0.74,
            threshold=4.0,
            normalized_threshold=0.8,
            pass_=False,
            decisive_failure=True,  # decisive blocker
            findings=["JD language used as primary proof."],
            cited_sentence_indexes=[],
            remediation_suggestions=[],
        ),
    ]
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is False


def test_duplicate_certifications_in_competencies_fails_deterministic_blocker(tmp_path: Path):
    final = {
        "final_resume_hash": "deadbeef",
        "candidate_identity": {"candidate_name": "Test", "header_contact": {}},
        "sections": [
            {
                "section_id": "competencies",
                "assemble_order": 10,
                "l2_output_snapshot": {
                    "competencies": [
                        {
                            "category_label": "Certifications",
                            "terms": [
                                {"text": "AWS Certified Solutions Architect", "source_fact_id": "f1"},
                                {"text": "Databricks Lakehouse Fundamentals", "source_fact_id": "f1"},
                                {"text": "Fellow of the Society of Actuaries", "source_fact_id": "f1"},
                            ],
                            "source_fact_ids": ["f1"],
                        }
                    ]
                },
            },
            {
                "section_id": "certifications",
                "assemble_order": 12,
                "copied_text_exact": json.dumps([{"name": "AWS Certified Solutions Architect"}]),
            },
        ],
    }
    review = emit_full_resume_llm_coherence_review(
        final_resume=final,
        final_resume_path=tmp_path / "final_resume.json",
        output_dir=tmp_path,
        mode="mocked",
    )
    assert review["full_resume_coherence_pass"] is False
    assert any("credential" in b for b in review["blockers"])
    gate = gate_x2_full_resume_llm_coherence_aggregation(review, required=True)
    assert gate.pass_ is False


def test_locked_experience_credential_is_not_competencies_duplication(tmp_path: Path):
    final = {
        "final_resume_hash": "f00d",
        "candidate_identity": {"candidate_name": "Test", "header_contact": {}},
        "sections": [
            {
                "section_id": "headline",
                "assemble_order": 1,
                "l2_output_snapshot": {"headline_line": "SVP Engineering | Agentic AI Platforms"},
            },
            {
                "section_id": "executive_summary",
                "assemble_order": 2,
                "l2_output_snapshot": {
                    "resume_display_text": "Executive leader building governed AI platforms."
                },
            },
            {
                "section_id": "competencies",
                "assemble_order": 3,
                "l2_output_snapshot": {
                    "competencies": [
                        {
                            "category_label": "AI Platform Architecture",
                            "terms": [
                                {"text": "runtime governance", "source_fact_id": "f1"},
                                {"text": "multi-agent orchestration", "source_fact_id": "f1"},
                            ],
                            "source_fact_ids": ["f1"],
                        }
                    ]
                },
            },
            {
                "section_id": "early_career",
                "assemble_order": 12,
                "copied_text_exact": json.dumps(
                    {
                        "employer": "Early Career Roles",
                        "title": "Actuarial Consultant and Quantitative Roles",
                        "location": "Philadelphia, PA",
                        "start_date": "2002-10",
                        "end_date": "2009-09",
                        "bullets": [
                            {
                                "text": (
                                    "As a Fellow of the Society of Actuaries (FSA), "
                                    "priced derivatives and built stochastic capital models."
                                )
                            }
                        ],
                    }
                ),
            },
            {
                "section_id": "education",
                "assemble_order": 13,
                "copied_text_exact": json.dumps([]),
            },
            {
                "section_id": "certifications",
                "assemble_order": 14,
                "copied_text_exact": json.dumps([{"name": "Fellow of the Society of Actuaries"}]),
            },
        ],
    }
    review = emit_full_resume_llm_coherence_review(
        final_resume=final,
        final_resume_path=tmp_path / "final_resume.json",
        output_dir=tmp_path / "review",
        mode="mocked",
    )

    assert not any("credential_name_in_competencies_block" in b for b in review["blockers"])
    assert any(
        "credential_section_ownership_duplicate:Fellow of the Society of Actuaries" in b
        for b in review["blockers"]
    )


def test_provider_artifact_write_recreates_missing_parent(tmp_path: Path):
    artifact = tmp_path / "missing" / "x1d_provider_request.json"

    written = _write_artifact(artifact, {"ok": True})

    assert Path(written).is_file()
    assert json.loads(artifact.read_text(encoding="utf-8")) == {"ok": True}


def test_provider_artifact_write_handles_long_windows_path(tmp_path: Path):
    base = tmp_path
    filename = "x1d_gemini_provider_request_20260705_185523_857.json"
    while len(str((base / filename).resolve(strict=False))) <= 260:
        base = base / f"deep_segment_{len(base.parts):02d}"
    artifact = base / filename

    written = _write_artifact(artifact, {"ok": True})

    assert json.loads(Path(_filesystem_path(Path(written))).read_text(encoding="utf-8")) == {"ok": True}


def test_full_resume_coherence_judge_request_artifact_survives_long_run_root(
    monkeypatch,
    tmp_path: Path,
):
    base = tmp_path
    filename = "x1d_gemini_provider_request_20260705_185523_857.json"
    while len(str((base / filename).resolve(strict=False))) <= 260:
        base = base / f"deep_segment_{len(base.parts):02d}"
    artifact_base = base / "coherence_judge_providers"
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFakeSecret01234567890123456789012")

    judges = run_full_resume_coherence_judges(
        full_resume_text="SVP agentic AI platform engineering resume.",
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        judge_roster=["gemini_pro"],
        artifact_base=artifact_base,
    )

    assert judges[0].provider_status == "NETWORK_TESTS_NOT_ENABLED"
    assert "No such file or directory" not in str(judges[0].exact_provider_error)
    request_artifacts = sorted(Path(_filesystem_path(artifact_base)).glob("*provider_request*.json"))
    assert request_artifacts


def test_strong_resume_passes_deterministic_preflight_when_judges_pass(tmp_path: Path):
    final = {
        "final_resume_hash": "cafebabe",
        "candidate_identity": {"candidate_name": "Test", "header_contact": {}},
        "sections": [
            {
                "section_id": "headline",
                "assemble_order": 1,
                "l2_output_snapshot": {"headline_line": "SVP Engineering | Agentic AI Platforms"},
            },
            {
                "section_id": "executive_summary",
                "assemble_order": 2,
                "l2_output_snapshot": {
                    "resume_display_text": "Executive leader building agentic AI platforms with governance."
                },
            },
            {
                "section_id": "competencies",
                "assemble_order": 10,
                "l2_output_snapshot": {
                    "competencies": [
                        {
                            "category_label": "Agentic AI Platform Architecture",
                            "terms": [
                                {"text": "deterministic routing", "source_fact_id": "b1"},
                                {"text": "multi-agent orchestration", "source_fact_id": "b1"},
                                {"text": "GraphRAG retrieval", "source_fact_id": "b1"},
                            ],
                            "source_fact_ids": ["b1"],
                        },
                        {
                            "category_label": "AI Reliability and Evaluation",
                            "terms": [
                                {"text": "validation gates", "source_fact_id": "b2"},
                                {"text": "telemetry instrumentation", "source_fact_id": "b2"},
                                {"text": "rollback controls", "source_fact_id": "b2"},
                            ],
                            "source_fact_ids": ["b2"],
                        },
                        {
                            "category_label": "Enterprise Data and Governance",
                            "terms": [
                                {"text": "data catalogs", "source_fact_id": "b3"},
                                {"text": "regulatory reporting controls", "source_fact_id": "b3"},
                                {"text": "automated validation frameworks", "source_fact_id": "b3"},
                            ],
                            "source_fact_ids": ["b3"],
                        },
                        {
                            "category_label": "Cloud and Distributed Infrastructure",
                            "terms": [
                                {"text": "AWS", "source_fact_id": "b4"},
                                {"text": "Databricks Lakehouse", "source_fact_id": "b4"},
                                {"text": "microservices", "source_fact_id": "b4"},
                            ],
                            "source_fact_ids": ["b4"],
                        },
                        {
                            "category_label": "Platform Commercialization",
                            "terms": [
                                {"text": "reusable IP strategy", "source_fact_id": "b5"},
                                {"text": "managed AI services", "source_fact_id": "b5"},
                                {"text": "enterprise adoption", "source_fact_id": "b5"},
                            ],
                            "source_fact_ids": ["b5"],
                        },
                        {
                            "category_label": "Engineering Leadership",
                            "terms": [
                                {"text": "platform roadmap ownership", "source_fact_id": "b6"},
                                {"text": "ML engineering scale-out", "source_fact_id": "b6"},
                                {"text": "cross-functional delivery governance", "source_fact_id": "b6"},
                            ],
                            "source_fact_ids": ["b6"],
                        },
                    ]
                },
            },
            {
                "section_id": "certifications",
                "assemble_order": 12,
                "copied_text_exact": json.dumps([{"name": "AWS Certified Solutions Architect"}]),
            },
        ],
    }
    judges = run_full_resume_coherence_judges(
        full_resume_text="SVP agentic AI platform engineering resume.",
        target_company="Brown & Brown",
        target_role="Senior Vice President, IT Strategy & Innovation",
        mode="mocked",
    )
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    # mocked judges never pass quorum — artifact still emitted with explicit fail
    assert agg["full_resume_coherence_pass"] is False
    review = emit_full_resume_llm_coherence_review(
        final_resume=final,
        final_resume_path=tmp_path / "final_resume.json",
        output_dir=tmp_path / "strong",
        target_company="Brown & Brown",
        target_role="SVP IT Strategy",
        mode="mocked",
    )
    assert (tmp_path / "strong" / "full_resume_llm_coherence_review.json").is_file()
    pre_blockers = review.get("blockers") or []
    assert not any("credential_duplication" in b for b in pre_blockers)


def test_gate_requires_artifact_when_enabled():
    g = gate_x2_full_resume_llm_coherence_aggregation(None, required=True)
    assert g.pass_ is False
    g2 = gate_x2_full_resume_llm_coherence_aggregation(
        {"full_resume_coherence_pass": True},
        required=True,
    )
    assert g2.pass_ is True


def test_candidate_evidence_packet_preserves_unique_metric_authority_without_diagnostics():
    final = {
        "sections": [
            {
                "section_id": "executive_summary",
                "l2_output_snapshot": {
                    "claim_ledger": [
                        {
                            "claim_text": "Scaled an IP portfolio to $22M in revenue.",
                            "source_fact_ids": ["fact_engineering_platform_006"],
                        }
                    ],
                    "selected_fact_plan": {
                        "allocation_plan_digest": "a" * 64,
                        "graph_candidate_decision_ledger": ["must-not-leak"],
                        "facts": [
                            {
                                "fact_id": "reb_unify_platform_commercialization_leadership",
                                "claim_text": "Platform productization and IP-led revenue",
                                "source_fact_ids": ["fact_engineering_platform_006"],
                                "graph_skill_node_ids": ["skill_agentic_platform_productization"],
                                "metric_outcome_ids": ["metric_unify_22m_ip_led_revenue"],
                                "metric_values": ["$22M IP-led revenue"],
                                "allocation_claim_unit_ids": ["executive_summary:claim:01"],
                                "verification_status": "allocation_authority_pass",
                            }
                        ],
                    },
                },
            }
        ]
    }

    packet = build_full_resume_evidence_packet(final)
    encoded = json.dumps(packet, sort_keys=True)
    fact = packet["sections"][0]["selected_candidate_facts"][0]

    assert fact["metric_outcome_ids"] == ["metric_unify_22m_ip_led_revenue"]
    assert fact["metric_values"] == ["$22M IP-led revenue"]
    assert "graph_candidate_decision_ledger" not in encoded
    prompt = _build_prompt(
        full_resume_text="EXECUTIVE SUMMARY\nScaled an IP portfolio to $22M in revenue.",
        target_company="Anthropic",
        target_role="Partnerships Lead",
        jd_context="JD asks for partner growth.",
        evidence_packet=packet,
    )
    assert "CANDIDATE_EVIDENCE_PACKET (candidate proof)" in prompt
    assert "TARGETING_CONTEXT (not proof)" in prompt
    assert "surface-text repetition is not required" in prompt
