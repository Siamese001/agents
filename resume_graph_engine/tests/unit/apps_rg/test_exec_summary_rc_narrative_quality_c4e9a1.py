"""Unit tests for plan exec-summary-rc-narrative-quality-c4e9a1 (RC-H through RC-K)."""

from __future__ import annotations

import apps_rg.runtime.sections.executive_summary_voice_repair as voice_repair

from apps_rg.runtime.sections.exec_summary_graph_only_quality import (
    _flags_display_metric_echo_only,
    _sanitize_deprecated_commercialization_thread,
    _sanitize_unsupported_percent_tokens,
    _sanitize_unsupported_style_metric_echoes,
    apply_graph_only_generation_quality_repair,
)
from apps_rg.runtime.sections.executive_summary_voice_repair import (
    _repair_ai_partnership_judge_findings,
    _source_fact_ids_for_display_sentence,
    ensure_required_allowed_fact_utilization,
    finalize_executive_summary_coherence,
    polish_executive_summary_judge_alignment,
)
from apps_rg.runtime.sections.executive_summary_composition import (
    is_mechanism_inventory_sentence,
)
from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
    FACT_C0_DISPLAY_OVERRIDES,
    FSA_CREDENTIAL_FACT_ID,
    SENTENCE_ARC_SVP_STRATEGY,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    brushstroke_required_groups_from_composition_plan,
    check_exec_summary_allowed_fact_utilization,
    check_exec_summary_display_override_compliance,
    check_exec_summary_no_mechanism_inventory,
    check_exec_summary_no_sentence_fragment,
    check_exec_summary_strategy_no_commercialization_thread,
    check_synthesis_quality,
    check_synthesis_quality,
)


def test_s3_guidance_no_literal_22m_or_20_percent() -> None:
    guidance = SENTENCE_ARC_SVP_STRATEGY[2]["guidance"].lower()
    assert "$22m" not in guidance
    assert "20%" not in guidance
    assert "metric_raw" in guidance


def test_platform_control_repair_removes_live_mechanism_catalog() -> None:
    sentences = [
        "Engineering executive leads regulated modernization delivery.",
        "From that foundation, the leader architects an agentic AI platform control plane with policy-gated routing that dispatches decisions through explicit route and policy logic rather than ad hoc handling.",
        "Software dependency graph intelligence enables accelerated analysis.",
        "Runtime governance keeps execution traceable.",
        "Platform commercialization created IP-led revenue growth.",
        "The platform foundation supports enterprise adoption.",
    ]
    repaired = _repair_ai_partnership_judge_findings(
        sentences,
        selected_facts=[
            {"fact_id": "reb_unify_agentic_platform_architecture"},
        ],
    )

    is_inventory, _ = is_mechanism_inventory_sentence(sentences[1])
    repaired_inventory, reason = is_mechanism_inventory_sentence(repaired[1])
    assert is_inventory is True
    assert repaired_inventory is False, reason
    assert _source_fact_ids_for_display_sentence(repaired[1]) == [
        "reb_unify_agentic_platform_architecture"
    ]


def test_ai_partnership_coherence_repair_removes_repeated_internal_surface_jargon() -> None:
    sentences = [
        "Engineering executive leading governed agentic AI platform delivery, embedding release automation and security scanning into regulated modernization delivery paths as the foundation for enterprise-scale platform architecture.",
        "From that release-discipline base, the leader architects a governed agentic AI platform control plane, productizing route-policy dispatch and proof-bundle lineage into a scalable execution surface.",
        "Software dependency graph intelligence enables accelerated legacy-system analysis, exposes architecture dependency chains, and improves transformation visibility across enterprise complexity.",
        "In parallel, gate-verdict contracts and human override escalation paths anchor control and evidence discipline, ensuring every policy-gated agent execution surface carries auditable proof-bundle lineage.",
        "That governance foundation also underpins platform productization leadership, generating $22M in IP-led revenue growth alongside expansion of the policy-gated agent execution surface across enterprise programs.",
        "That combined discipline positions governed agentic systems architecture to extend across new enterprise engagements, scaling execution surfaces while sustaining proof-bundle lineage and gate-verdict rigor.",
    ]

    repaired = _repair_ai_partnership_judge_findings(
        sentences,
        selected_facts=[
            {"fact_id": "reb_ibm_devsecops_release_resilience"},
            {"fact_id": "reb_unify_agentic_platform_architecture"},
            {"fact_id": "reb_unify_platform_commercialization_leadership"},
        ],
    )

    text = " ".join(repaired).lower()
    synthesis_ok, synthesis_reason = check_synthesis_quality(" ".join(repaired))
    assert repaired[1].startswith("On that foundation, architected an agentic AI platform")
    assert "$22M" in repaired[4]
    assert "the leader" not in text
    assert "proof-bundle" not in text
    assert "execution surface" not in text
    assert "gate-verdict" not in text
    assert synthesis_ok, synthesis_reason


def test_fsa_display_override_has_strategic_connector() -> None:
    text = FACT_C0_DISPLAY_OVERRIDES[FSA_CREDENTIAL_FACT_ID]
    # Opener must be a strategic "That <noun>" connector. Avoid "governance discipline"
    # because EXEC_SUMMARY_FORBIDDEN_META_PHRASES bans it as meta-filler scaffolding,
    # which would trigger synthesis regen and strip the anchor on re-attempt.
    assert text.lower().startswith("that regulatory foundation"), (
        "Override opener must avoid the forbidden meta-filler phrase 'governance discipline' "
        "to keep RetiredProvider synthesis from getting rejected on attempt 1 and dropping the X2 anchor."
    )
    assert "governance discipline" not in text.lower()
    assert "informing data governance" in text.lower()


def test_fsa_display_override_is_complete_sentence() -> None:
    ok, reason = check_exec_summary_no_sentence_fragment(
        FACT_C0_DISPLAY_OVERRIDES[FSA_CREDENTIAL_FACT_ID]
    )
    assert ok, reason


def test_flags_display_metric_echo_only() -> None:
    assert _flags_display_metric_echo_only({"unsupported_percent_tokens": ["20%"]}) is True
    assert (
        _flags_display_metric_echo_only(
            {
                "unsupported_percent_tokens": ["20%"],
                "had_unsupported_gross_margin": True,
            }
        )
        is True
    )
    assert (
        _flags_display_metric_echo_only(
            {
                "unsupported_percent_tokens": ["20%"],
                "mechanical_opener_stack": True,
            }
        )
        is False
    )


def test_sanitize_unsupported_percent_preserves_connective_opener() -> None:
    before = (
        "Enterprise technology leader who aligns governed AI platforms. "
        "Building on that foundation, supply-chain modernization generated $22M "
        "in efficiency capture and expanded operating margins by 20% while growing the team."
    )
    after = _sanitize_unsupported_percent_tokens(before, ["20%"])
    assert "building on that foundation" in after.lower()
    assert "20%" not in after


def test_sanitize_style_metric_echoes_strips_22m_when_unsupported() -> None:
    resume = (
        "Technology leader aligning platforms. "
        "Building on that foundation, modernization generated $22M in revenue."
    )
    facts = [{"fact_id": "fact_governance_003", "claim_text": "Cut errors by 40%"}]
    cleaned = _sanitize_unsupported_style_metric_echoes(resume, plan_facts=facts)
    assert "$22m" not in cleaned.lower()
    assert "building on that foundation" in cleaned.lower()


def test_apply_repair_percent_sanitize_only_skips_full_rewrite() -> None:
    allowed = {
        "fact_engineering_platform_001",
        "fact_governance_003",
        "fact_governance_003_metric_e5abeb74",
        "fact_exec_002",
    }
    parsed = {
        "resume_display_text": (
            "Technology strategy executive who aligns enterprise IT direction. "
            "Through that operating model, platform work cut regulatory reporting errors by 40%. "
            "In parallel, the ML engineering organization grew from 8 to 28 specialists. "
            "That governance discipline is grounded in quantitative rigor established through "
            "FSA-chartered actuarial work in capital modeling and portfolio stress analytics. "
            "Against that delivery foundation, large-scale regulatory IT transformations advanced "
            "legacy-modernization programs for major institutions. "
            "Software dependency graph intelligence enables accelerated legacy-system analysis."
        ),
        "claim_ledger": [
            {"claim_text": "x", "source_fact_ids": ["fact_governance_003"]},
            {"claim_text": "y", "source_fact_ids": ["fact_exec_002"]},
            {"claim_text": "z", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "a", "source_fact_ids": ["fact_quant_hpc_003"]},
            {"claim_text": "b", "source_fact_ids": ["fact_consulting_001"]},
            {"claim_text": "c", "source_fact_ids": ["fact_engineering_platform_002"]},
        ],
    }
    # Inject unsupported 20% in one sentence only
    parsed["resume_display_text"] = parsed["resume_display_text"].replace(
        "by 40%", "by 40% and expanded margins by 20%"
    )
    plan_facts = [
        {"fact_id": "fact_governance_003", "claim_text": "Cut errors by 40%", "metric_raw": "40%"},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled team 8 to 28", "metric_raw": "8 to 28"},
        {
            "fact_id": "fact_engineering_platform_001",
            "claim_text": "Governed agentic AI platform",
        },
    ]
    repaired, meta = apply_graph_only_generation_quality_repair(
        parsed,
        allowed_fact_ids=allowed,
        plan_facts=plan_facts,
    )
    assert meta.get("repair_kind") == "display_metric_echo_sanitize_only"
    assert "20%" not in str(repaired.get("resume_display_text") or "")
    assert "through that operating model" in str(repaired.get("resume_display_text") or "").lower()


def test_display_override_compliance_passes_with_anchor() -> None:
    override = FACT_C0_DISPLAY_OVERRIDES[FSA_CREDENTIAL_FACT_ID]
    ok, reason = check_exec_summary_display_override_compliance(
        override,
        [{"claim_text": "x", "source_fact_ids": [FSA_CREDENTIAL_FACT_ID]}],
    )
    assert ok, reason


def test_display_override_compliance_fails_without_anchor() -> None:
    ok, reason = check_exec_summary_display_override_compliance(
        "Established quantitative rigor through FSA work only.",
        [{"claim_text": "x", "source_fact_ids": [FSA_CREDENTIAL_FACT_ID]}],
    )
    assert not ok
    assert reason and "DISPLAY_OVERRIDE" in reason


def test_display_override_compliance_allows_regulator_foundation_paraphrase() -> None:
    override = FACT_C0_DISPLAY_OVERRIDES[FSA_CREDENTIAL_FACT_ID]
    paraphrase = override.replace("governance discipline", "regulatory foundation")
    ok, reason = check_exec_summary_display_override_compliance(
        paraphrase,
        [{"claim_text": "x", "source_fact_ids": [FSA_CREDENTIAL_FACT_ID]}],
    )
    assert ok, reason


def test_sanitize_commercialization_thread_replaces_platform_phrase() -> None:
    before = (
        "Enterprise leader aligning platforms. Building on that foundation, "
        "platform commercialization generated significant revenue."
    )
    after = _sanitize_deprecated_commercialization_thread(before)
    assert "commercialization" not in after.lower()
    assert "platform revenue outcomes" in after.lower()
    assert "building on that foundation" in after.lower()


def test_apply_repair_commercialization_sanitize_when_no_other_flags() -> None:
    parsed = {
        "resume_display_text": (
            "Technology strategy executive who aligns enterprise IT direction. "
            "Building on that foundation, platform commercialization generated revenue."
        ),
        "claim_ledger": [],
    }
    repaired, meta = apply_graph_only_generation_quality_repair(
        parsed,
        allowed_fact_ids=set(),
        plan_facts=[],
    )
    assert meta.get("repair_kind") == "commercialization_thread_sanitize_only"
    assert "commercialization" not in str(repaired.get("resume_display_text") or "").lower()


def test_ensure_governance_fact_utilization_inserts_basel_sentence() -> None:
    parsed = {
        "resume_display_text": (
            "Enterprise technology leader who aligns governed AI platforms. "
            "Designs and operates platform runtimes with deterministic controls. "
            "Directed large-scale regulatory IT transformations across institutions. "
            "Software dependency graph intelligence enables legacy analysis. "
            "FSA-chartered actuarial work informs data governance at scale. "
            "Federated platform capabilities preserve lineage discipline at scale."
        ),
        "claim_ledger": [
            {"claim_text": "a", "source_fact_ids": ["fact_exec_002"]},
            {"claim_text": "b", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "c", "source_fact_ids": ["fact_consulting_001"]},
            {"claim_text": "d", "source_fact_ids": ["fact_engineering_platform_002"]},
            {"claim_text": "e", "source_fact_ids": ["fact_quant_hpc_003"]},
            {"claim_text": "f", "source_fact_ids": ["fact_engineering_platform_002"]},
        ],
    }
    facts = [
        {"fact_id": "fact_exec_002", "claim_text": "Scaled team"},
        {"fact_id": "fact_engineering_platform_001", "claim_text": "Platform"},
        {"fact_id": "fact_consulting_001", "claim_text": "Consulting"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Graph"},
        {"fact_id": "fact_quant_hpc_003", "claim_text": "FSA work"},
        {"fact_id": "fact_governance_003", "claim_text": "Basel III cut errors 40%"},
        {"fact_id": "fact_certs_001", "claim_text": "Certs"},
    ]
    patched, receipt = ensure_required_allowed_fact_utilization(parsed, selected_facts=facts)
    assert "fact_governance_003" in receipt.get("patched_fact_ids", [])
    assert "basel iii" in str(patched.get("resume_display_text") or "").lower()
    assert "40%" in str(patched.get("resume_display_text") or "")
    cited = {
        fid
        for row in patched.get("claim_ledger") or []
        for fid in (row.get("source_fact_ids") or [])
    }
    assert "fact_governance_003" in cited


def test_ensure_unify_commercialization_fact_utilization_inserts_b4_sentence() -> None:
    parsed = {
        "resume_display_text": (
            "Enterprise technology leader who led AWS modernization for regulated workloads. "
            "Governed agentic platform architecture gave teams reliable runtime controls. "
            "IBM-AWS co-sell motions and accelerators packaged modernization patterns. "
            "Insurance regulatory standards kept partner-led delivery compliant. "
            "Decision-support data models connected modernization to executive decisions. "
            "Distributed cloud execution paired with partner-channel leadership for alliance GTM."
        ),
        "claim_ledger": [
            {"claim_text": "a", "source_fact_ids": ["reb_insurtech_aws_migration_execution"]},
            {"claim_text": "b", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "c", "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {"claim_text": "d", "source_fact_ids": ["reb_insurtech_insurance_regulatory_cloud_adoption_standards"]},
            {"claim_text": "e", "source_fact_ids": ["reb_ibm_data_modeling_bi_decision_support"]},
            {"claim_text": "f", "source_fact_ids": ["reb_unify_partner_channel_cosell"]},
        ],
    }
    facts = [
        {"fact_id": "reb_insurtech_aws_migration_execution", "claim_text": "AWS modernization"},
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Agentic platform architecture"},
        {"fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm", "claim_text": "IBM-AWS co-sell"},
        {
            "fact_id": "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
            "claim_text": "Insurance regulatory cloud adoption standards",
        },
        {"fact_id": "reb_ibm_data_modeling_bi_decision_support", "claim_text": "Decision support"},
        {"fact_id": "reb_unify_partner_channel_cosell", "claim_text": "Partner channel co-sell"},
        {
            "fact_id": "reb_unify_platform_commercialization_leadership",
            "claim_text": "Platform commercialization leadership grew IP-led revenue and margins",
        },
    ]

    patched, receipt = ensure_required_allowed_fact_utilization(parsed, selected_facts=facts)

    assert "reb_unify_platform_commercialization_leadership" in receipt.get("patched_fact_ids", [])
    assert "ip-led revenue" in str(patched.get("resume_display_text") or "").lower()
    cited = {
        fid
        for row in patched.get("claim_ledger") or []
        for fid in (row.get("source_fact_ids") or [])
    }
    assert "reb_unify_platform_commercialization_leadership" in cited


def test_ensure_devsecops_brushstroke_survives_dependency_graph_override() -> None:
    """A required IBM delivery root must not be lost to the graph display anchor."""
    parsed = {
        "resume_display_text": (
            "Engineering executive leads governed agentic AI platform architecture for regulated enterprises. "
            "Software dependency graph intelligence enables accelerated legacy-system analysis, exposes architecture dependency chains, and improves transformation visibility across enterprise complexity. "
            "The agentic platform control plane keeps autonomous execution traceable end to end. "
            "Human override paths keep autonomous execution reviewable. "
            "Platform productization converted governed architecture into $22M in IP-led revenue. "
            "That productized footing extends applied AI partner architecture into enterprise ecosystems."
        ),
        "claim_ledger": [
            {"claim_text": "s1", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "s2", "source_fact_ids": ["fact_engineering_platform_002"]},
            {"claim_text": "s3", "source_fact_ids": ["skill_unify_agentic_runtime_proof_bundle_lineage"]},
            {"claim_text": "s4", "source_fact_ids": ["skill_unify_agentic_human_override_escalation_paths"]},
            {"claim_text": "s5", "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
            {"claim_text": "s6", "source_fact_ids": ["fact_engineering_platform_006"]},
        ],
    }
    facts = [
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Agentic platform architecture"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Dependency graph intelligence"},
        {"fact_id": "reb_ibm_devsecops_release_resilience", "claim_text": "Embedded release automation and security scanning"},
        {"fact_id": "reb_unify_platform_commercialization_leadership", "claim_text": "Platform productization"},
    ]

    patched, receipt = ensure_required_allowed_fact_utilization(parsed, selected_facts=facts)

    assert "reb_ibm_devsecops_release_resilience" in receipt["patched_fact_ids"]
    assert "regulated devsecops release governance" in str(patched["resume_display_text"]).lower()
    ok, reason, _ = check_exec_summary_allowed_fact_utilization(
        patched["claim_ledger"],
        {str(f["fact_id"]) for f in facts},
        required_brushstroke_groups=[
            ["reb_unify_agentic_platform_architecture"],
            ["reb_ibm_devsecops_release_resilience"],
            ["reb_unify_platform_commercialization_leadership"],
        ],
    )
    assert ok, reason


def test_finalize_reapplies_required_fact_utilization_after_terminal_polish(
    monkeypatch,
) -> None:
    """Later polish must not erase a final required graph binding."""
    parsed = {
        "resume_display_text": (
            "Engineering executive leads governed agentic AI platform architecture for regulated enterprises. "
            "Software dependency graph intelligence enables accelerated legacy-system analysis, exposes architecture dependency chains, and improves transformation visibility across enterprise complexity. "
            "The agentic platform control plane keeps autonomous execution traceable end to end. "
            "Human override paths keep autonomous execution reviewable. "
            "Platform productization converted governed architecture into $22M in IP-led revenue. "
            "That productized footing extends applied AI partner architecture into enterprise ecosystems."
        ),
        "claim_ledger": [
            {"claim_text": "s1", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "s2", "source_fact_ids": ["fact_engineering_platform_002"]},
            {"claim_text": "s3", "source_fact_ids": ["skill_unify_agentic_runtime_proof_bundle_lineage"]},
            {"claim_text": "s4", "source_fact_ids": ["skill_unify_agentic_human_override_escalation_paths"]},
            {"claim_text": "s5", "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
            {"claim_text": "s6", "source_fact_ids": ["fact_engineering_platform_006"]},
        ],
    }
    facts = [
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Agentic platform architecture"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Dependency graph intelligence"},
        {"fact_id": "reb_ibm_devsecops_release_resilience", "claim_text": "Embedded release automation and security scanning"},
        {"fact_id": "reb_unify_platform_commercialization_leadership", "claim_text": "Platform productization"},
    ]

    def _erase_required_bindings_after_initial_repair(value, **_kwargs):
        out = dict(value)
        out["resume_display_text"] = str(out["resume_display_text"]).replace(
            "Regulated DevSecOps release governance strengthened modernization delivery with controlled deployment discipline.",
            "In parallel, proof-bundle lineage preserves accountable intervention across the runtime.",
        )
        out["resume_display_text"] = str(out["resume_display_text"]).replace(
            "From that foundation, the leader architects an agentic AI platform control plane with explicit decision rules.",
            "Engineering leadership sets regulated enterprise direction.",
        )
        ledger = [dict(row) for row in out.get("claim_ledger") or []]
        ledger[0] = {
            "claim_text": "Engineering leadership sets regulated enterprise direction.",
            "source_fact_ids": ["fact_engineering_platform_002"],
        }
        ledger[3] = {
            "claim_text": "In parallel, proof-bundle lineage preserves accountable intervention across the runtime.",
            "source_fact_ids": ["skill_unify_agentic_runtime_proof_bundle_lineage"],
        }
        out["claim_ledger"] = ledger
        return out, {"applied": True}

    monkeypatch.setattr(
        voice_repair,
        "polish_executive_summary_judge_alignment",
        _erase_required_bindings_after_initial_repair,
    )

    finalized, receipt = finalize_executive_summary_coherence(
        parsed,
        selected_facts=facts,
        allowed_fact_ids={str(fact["fact_id"]) for fact in facts},
        target_role="Manager of Applied AI Architecture, Partnerships",
    )

    repaired_ids = receipt["final_allowed_fact_utilization"]["patched_fact_ids"]
    assert "reb_ibm_devsecops_release_resilience" in repaired_ids
    assert "reb_unify_agentic_platform_architecture" in repaired_ids
    assert "regulated devsecops release governance" in str(
        finalized["resume_display_text"]
    ).lower()
    assert "agentic ai platform control plane" in str(
        finalized["resume_display_text"]
    ).lower()
    cited = {
        str(fact_id)
        for row in finalized["claim_ledger"]
        for fact_id in row.get("source_fact_ids") or []
    }
    assert "reb_ibm_devsecops_release_resilience" in cited
    assert "reb_unify_agentic_platform_architecture" in cited


def test_polish_dedupes_dependency_graph_and_weaves_team_metric() -> None:
    duplicate_resume = (
        "Enterprise technology leader who unifies governed AI platforms. "
        "Through that operating model, Basel III and CCAR data lineage cut regulatory reporting errors by 40%. "
        "Software dependency graph intelligence enables accelerated legacy-system analysis, "
        "exposes architecture dependency chains, and improves transformation visibility across enterprise complexity. "
        "That regulatory foundation is grounded in FSA-chartered actuarial work in capital modeling. "
        "Directed large-scale regulatory IT transformations and legacy-modernization programs for major institutions. "
        "Built and applied software dependency graph intelligence to accelerate legacy-system analysis."
    )
    parsed = {
        "resume_display_text": duplicate_resume,
        "claim_ledger": [
            {"claim_text": "a", "source_fact_ids": ["fact_exec_002"]},
            {"claim_text": "b", "source_fact_ids": ["fact_governance_003"]},
            {"claim_text": "c", "source_fact_ids": ["fact_engineering_platform_002"]},
            {"claim_text": "d", "source_fact_ids": ["fact_quant_hpc_003"]},
            {"claim_text": "e", "source_fact_ids": ["fact_consulting_001"]},
            {"claim_text": "f", "source_fact_ids": ["fact_engineering_platform_002"]},
        ],
    }
    facts = [
        {"fact_id": "fact_exec_002", "claim_text": "Scaled team 8 to 28"},
        {"fact_id": "fact_governance_003", "claim_text": "Basel cut errors 40%"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Graph intelligence"},
        {"fact_id": "fact_quant_hpc_003", "claim_text": "FSA work"},
        {"fact_id": "fact_consulting_001", "claim_text": "Consulting"},
    ]
    polished, receipt = polish_executive_summary_judge_alignment(parsed, selected_facts=facts)
    text = str(polished.get("resume_display_text") or "").lower()
    assert receipt.get("applied") is True
    assert text.count("dependency graph") == 1
    assert "8 to 28" in text
    cited = {
        fid
        for row in polished.get("claim_ledger") or []
        for fid in (row.get("source_fact_ids") or [])
    }
    assert "fact_engineering_platform_002" in cited


def test_polish_restores_graph_override_when_team_displaced_slot() -> None:
    """Regression: platform weave must not replace dependency-graph DISPLAY_OVERRIDE."""
    parsed = {
        "resume_display_text": (
            "Enterprise technology leader who unifies governed AI platforms. "
            "Through that operating model, Basel III and CCAR data lineage cut regulatory reporting errors by 40%. "
            "Scaled the ML engineering organization from 8 to 28 specialists. "
            "That regulatory foundation is grounded in FSA-chartered actuarial work in capital modeling. "
            "Directed large-scale regulatory IT transformations for major financial institutions. "
            "Designs and operates platform runtimes with deterministic controls and traceable execution."
        ),
        "claim_ledger": [],
    }
    facts = [
        {"fact_id": "fact_exec_002", "claim_text": "Scaled team 8 to 28"},
        {"fact_id": "fact_governance_003", "claim_text": "Basel cut errors 40%"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Graph intelligence"},
        {"fact_id": "fact_engineering_platform_001", "claim_text": "Agentic AI platform"},
        {"fact_id": "fact_quant_hpc_003", "claim_text": "FSA work"},
        {"fact_id": "fact_consulting_001", "claim_text": "Consulting"},
    ]
    polished, receipt = polish_executive_summary_judge_alignment(parsed, selected_facts=facts)
    text = str(polished.get("resume_display_text") or "").lower()
    assert receipt.get("applied") is True
    assert "dependency graph intelligence enables accelerated" in text
    cited = {
        fid
        for row in polished.get("claim_ledger") or []
        for fid in (row.get("source_fact_ids") or [])
    }
    assert "fact_engineering_platform_002" in cited


def test_graph_override_preserves_required_devsecops_brushstroke() -> None:
    """A late graph display override cannot evict the composition's sole DevSecOps fact."""
    parsed = {
        "resume_display_text": (
            "Technology strategy executive who leads governed agentic AI platform architecture. "
            "Designs and operates the agentic platform control plane with bounded review. "
            "Embedded release automation and security scanning into regulated modernization delivery paths. "
            "Runtime proof-bundle lineage gives decisions a traceable evidentiary record. "
            "Platform productization generated $22M in IP-led revenue. "
            "Platform commercialization leadership integrates enterprise-scale outcomes."
        ),
        "claim_ledger": [
            {"claim_text": "s1", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "s2", "source_fact_ids": ["skill_unify_agentic_human_override_escalation_paths"]},
            {"claim_text": "s3", "source_fact_ids": ["reb_ibm_devsecops_release_resilience"]},
            {"claim_text": "s4", "source_fact_ids": ["skill_unify_agentic_runtime_proof_bundle_lineage"]},
            {"claim_text": "s5", "source_fact_ids": ["metric_unify_22m_ip_led_revenue"]},
            {"claim_text": "s6", "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
        ],
        "executive_summary_composition_plan": {
            "brushstrokes": [
                {"required_fact_ids": ["reb_ibm_devsecops_release_resilience"]},
                {"required_fact_ids": ["reb_unify_agentic_platform_architecture"]},
                {"required_fact_ids": []},
                {"required_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
            ]
        },
    }
    facts = [
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Agentic platform"},
        {"fact_id": "reb_ibm_devsecops_release_resilience", "claim_text": "DevSecOps release"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Dependency graph"},
        {"fact_id": "reb_unify_platform_commercialization_leadership", "claim_text": "Commercialization"},
    ]

    polished, _receipt = polish_executive_summary_judge_alignment(parsed, selected_facts=facts)
    text = str(polished.get("resume_display_text") or "").lower()
    cited = {
        fact_id
        for row in polished.get("claim_ledger") or []
        for fact_id in (row.get("source_fact_ids") or [])
    }
    plan = parsed["executive_summary_composition_plan"]
    utilization_ok, reason, _ = check_exec_summary_allowed_fact_utilization(
        list(polished.get("claim_ledger") or []),
        {fact["fact_id"] for fact in facts},
        required_brushstroke_groups=brushstroke_required_groups_from_composition_plan(plan),
    )

    assert "dependency graph intelligence enables accelerated" in text
    assert "release automation and security scanning" in text
    assert "reb_ibm_devsecops_release_resilience" in cited
    assert utilization_ok is True, reason


def test_graph_override_preserves_live_devsecops_pipeline_wording() -> None:
    """The live provider wording must be recognized before an override selects a slot."""
    parsed = {
        "resume_display_text": (
            "An engineering executive leads governed agentic AI platform architecture. "
            "Designs the control plane for a multi-agent orchestration system, combining policy-gated routing, "
            "human override escalation paths, and replay-key audit manifest lineage. "
            "From that commercial base, embedding automated release pipelines and DevSecOps scanning into "
            "modernization delivery paths gave platform teams a repeatable deployment blueprint. "
            "Runtime proof-bundle lineage gives decisions a traceable evidentiary record. "
            "Platform productization generated $22M in IP-led revenue. "
            "Platform commercialization leadership integrates enterprise-scale outcomes."
        ),
        "claim_ledger": [],
        "executive_summary_composition_plan": {
            "brushstrokes": [
                {"required_fact_ids": ["reb_ibm_devsecops_release_resilience"]},
                {"required_fact_ids": ["reb_unify_agentic_platform_architecture"]},
                {"required_fact_ids": []},
                {"required_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
            ]
        },
    }
    facts = [
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Agentic platform"},
        {"fact_id": "reb_ibm_devsecops_release_resilience", "claim_text": "DevSecOps release"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Dependency graph"},
        {"fact_id": "reb_unify_platform_commercialization_leadership", "claim_text": "Commercialization"},
    ]

    polished, _receipt = polish_executive_summary_judge_alignment(parsed, selected_facts=facts)
    text = str(polished.get("resume_display_text") or "").lower()
    cited = {
        fact_id
        for row in polished.get("claim_ledger") or []
        for fact_id in (row.get("source_fact_ids") or [])
    }

    assert "dependency graph intelligence enables accelerated" in text
    assert "automated release pipelines and devsecops scanning" in text
    assert "reb_ibm_devsecops_release_resilience" in cited
    mechanism_ok, mechanism_reason = check_exec_summary_no_mechanism_inventory(
        str(polished.get("resume_display_text") or ""),
        polished,
    )
    assert mechanism_ok is True, mechanism_reason


def test_strategy_lane_blocks_commercialization_thread() -> None:
    ok, reason = check_exec_summary_strategy_no_commercialization_thread(
        "Leader aligning commercialization into one IT strategy agenda.",
        target_role="SVP IT Strategy & Innovation",
    )
    assert not ok
    assert reason and "commercialization" in reason.lower()
