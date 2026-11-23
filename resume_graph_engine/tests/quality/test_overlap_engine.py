"""Unit tests for Wave 1 shared Overlap Engine and corpus-learned RareTermLexicon."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.quality import (
    OverlapPolicy,
    RareTermLexicon,
    ResumeUnit,
    compute_idf_cosine_similarity,
    evaluate_resume_overlap,
    extract_normalized_number_units,
    load_default_overlap_policy,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "overlap" / "anthropic_e1d1e7775bb0_ibm.json"


def _load_anthropic_fixture_units() -> tuple[dict, list[ResumeUnit]]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    units: list[ResumeUnit] = []
    for idx, sent in enumerate(data["executive_summary_sentences"], start=1):
        units.append(
            ResumeUnit(
                unit_id=f"executive_summary:S{idx}",
                section_id="executive_summary",
                text=sent,
                employer=None,
                unit_kind="summary_sentence",
            )
        )
    units.append(
        ResumeUnit(
            unit_id="ibm_narrative:N1",
            section_id="ibm_narrative",
            text=data["ibm_narrative"],
            employer="ibm",
            unit_kind="narrative",
        )
    )
    for idx, bul in enumerate(data["ibm_bullets"], start=1):
        units.append(
            ResumeUnit(
                unit_id=f"ibm_bullets:B{idx}",
                section_id="ibm_bullets",
                text=bul,
                employer="ibm",
                unit_kind="bullet",
            )
        )
    return data, units


def test_learned_lexicon_discovers_rare_standards_without_hardcoded_lists() -> None:
    lexicon = RareTermLexicon.from_default_fact_inventory()
    assert lexicon.corpus_size > 500
    # Learned directly from corpus statistics (df_ratio <= 1.6% and capitalization consistency >= 85%)
    for expected_rare in ("bcbs 239", "soc 2", "ccar", "salesforce", "scada", "basel iii", "ag43", "maximo", "guidewire"):
        extracted = lexicon.extract_signature_terms(f"Implemented {expected_rare.upper() if len(expected_rare) <= 4 else expected_rare.title()} controls.")
        assert any(expected_rare in item for item in extracted) or expected_rare in lexicon.signature_terms, (
            f"Expected corpus-learned lexicon to recognize rare signature term {expected_rare!r}"
        )
    # General platform terms (>3% corpus frequency) are NOT capped at 1 occurrence
    assert "aws" not in lexicon.signature_terms
    assert "governance" not in lexicon.signature_terms
    assert "platform" not in lexicon.signature_terms


def test_learned_lexicon_catches_unseen_new_standard_codes_automatically() -> None:
    lexicon = RareTermLexicon.from_default_fact_inventory()
    # Brand-new regulatory codes never typed into any list (df=0 in fact inventory)
    sigs = lexicon.extract_signature_terms(
        "Enforced SR 11-7 model risk validation and ISO 27001 controls across banking pipelines."
    )
    assert "sr 11-7" in sigs
    assert "iso 27001" in sigs


def test_number_unit_canonicalization_merges_surface_variants() -> None:
    a = extract_normalized_number_units("Generated $10 million in net-new revenue and 99.9 percent uptime.")
    b = extract_normalized_number_units("Delivered $10M ARR while sustaining 99.9% production uptime.")
    assert a == ["$10m", "99.9%"]
    assert b == ["$10m", "99.9%"]


def test_anthropic_fixture_fails_all_repeat_types_and_echo_pairs() -> None:
    fixture_data, units = _load_anthropic_fixture_units()
    lexicon = RareTermLexicon.from_default_fact_inventory()
    policy = load_default_overlap_policy()

    report = evaluate_resume_overlap(units, lexicon=lexicon, policy=policy)
    assert report.verdict == "FAIL"
    assert report.passed is False

    # 1. Repeated signature terms caught
    assert "bcbs 239" in report.repeated_signature_terms
    assert report.repeated_signature_terms["bcbs 239"] == ("ibm_bullets:B1", "ibm_bullets:B4")
    assert "salesforce" in report.repeated_signature_terms
    assert report.repeated_signature_terms["salesforce"] == ("executive_summary:S3", "ibm_bullets:B3")

    # 2. Repeated numeric KPIs caught
    assert "99.9%" in report.repeated_numbers
    assert report.repeated_numbers["99.9%"] == ("ibm_bullets:B1", "ibm_bullets:B4")
    assert "$10m" in report.repeated_numbers
    assert set(report.repeated_numbers["$10m"]) == {"executive_summary:S3", "ibm_bullets:B2", "ibm_bullets:B3"}
    assert "20%" in report.repeated_numbers
    assert set(report.repeated_numbers["20%"]) == {"executive_summary:S3", "ibm_bullets:B5"}

    # 3. IDF-weighted cosine catches both B1<->B4 within IBM and S3<->B5 cross-section echo
    b1 = fixture_data["ibm_bullets"][0]
    b4 = fixture_data["ibm_bullets"][3]
    b1_b4_cos, b1_b4_shared = compute_idf_cosine_similarity(b1, b4, lexicon)
    assert b1_b4_cos > policy.max_within_section_idf_cosine
    assert "bcbs 239" in b1_b4_shared
    assert "99.9%" in b1_b4_shared

    s3 = fixture_data["executive_summary_sentences"][2]
    b5 = fixture_data["ibm_bullets"][4]
    s3_b5_cos, _ = compute_idf_cosine_similarity(s3, b5, lexicon)
    assert s3_b5_cos > policy.max_cross_section_idf_cosine


def test_dense_embedder_failure_fails_closed_with_unknown_verdict() -> None:
    _, units = _load_anthropic_fixture_units()

    def _broken_embedder(_texts):
        raise RuntimeError("Simulated BGE runtime unavailable")

    report = evaluate_resume_overlap(units[:3], dense_embedder=_broken_embedder)
    assert report.verdict == "UNKNOWN"
    assert report.passed is False
    assert any(f.finding_type == "DENSE_EMBEDDING_UNAVAILABLE" for f in report.findings)


def test_clean_non_overlapping_units_pass_overlap_engine() -> None:
    units = [
        ResumeUnit(
            unit_id="executive_summary:S1",
            section_id="executive_summary",
            text="Applied AI architecture and partnerships executive who turns cloud alliances into repeatable enterprise adoption.",
            unit_kind="summary_sentence",
        ),
        ResumeUnit(
            unit_id="ibm_narrative:N1",
            section_id="ibm_narrative",
            text="Operationalized AWS modernization at IBM through reusable reference architectures and executive-to-delivery solution discipline for regulated clients.",
            employer="ibm",
            unit_kind="narrative",
        ),
        ResumeUnit(
            unit_id="ibm_bullets:B1",
            section_id="ibm_bullets",
            text="Directed AWS Partner offering and accelerator management by packaging streaming analytics ecosystems and partner data-provider playbooks into reusable migration blueprints.",
            employer="ibm",
            unit_kind="bullet",
        ),
        ResumeUnit(
            unit_id="ibm_bullets:B2",
            section_id="ibm_bullets",
            text="Led global pre-sales solution engineering and commercial validation pilots to convert buyer requirements into C-suite architecture alignments driving $10M in net-new revenue.",
            employer="ibm",
            unit_kind="bullet",
        ),
        ResumeUnit(
            unit_id="ibm_bullets:B3",
            section_id="ibm_bullets",
            text="Architected enterprise cloud-native modernization waves shifting legacy on-prem financial workloads into containerized microservices via BCBS 239-aligned landing zones sustaining 99.9% production uptime.",
            employer="ibm",
            unit_kind="bullet",
        ),
        ResumeUnit(
            unit_id="ibm_bullets:B4",
            section_id="ibm_bullets",
            text="Drove alliance co-sell motions, SI and ISV joint go-to-market programs, and territory planning across cross-functional field teams to deliver 20% joint revenue growth.",
            employer="ibm",
            unit_kind="bullet",
        ),
    ]
    report = evaluate_resume_overlap(units)
    assert report.verdict == "PASS", report.diagnostic_summary()
    assert report.passed is True
    assert not report.findings


def test_c0_solver_blocks_intersecting_metric_fingerprints() -> None:
    from apps_rg.runtime.c0.allocation.solver import allocate_candidate_sets

    slot_specs = [
        {
            "slot_id": "bul_ibm_001",
            "section_id": "ibm_bullets",
            "employer_lane": "ibm",
            "metric_required": False,
            "metric_outcome_required": True,
            "counts_toward_global_uniqueness": True,
        },
        {
            "slot_id": "bul_ibm_002",
            "section_id": "ibm_bullets",
            "employer_lane": "ibm",
            "metric_required": False,
            "metric_outcome_required": True,
            "counts_toward_global_uniqueness": True,
        },
    ]

    def _cand(cid: str, slot_id: str, skill_id: str, root_id: str, metric_id: str, metric_text: str, score: float) -> dict:
        return {
            "candidate_id": cid,
            "section_id": "ibm_bullets",
            "claim_unit_id": slot_id,
            "skill_id": skill_id,
            "fact_id": f"exp_ibm_{root_id}",
            "root_id": root_id,
            "employer_lane": "ibm",
            "source_family": "ibm",
            "metric_outcome_id": metric_id,
            "metric_text": metric_text,
            "graph_path_ids": [f"path:{cid}"],
            "edge_ids": [f"edge:{cid}"],
            "citation_refs": [f"cite:{cid}"],
            "authority_pass": True,
            "proof_strength_raw": score,
            "path_confidence_raw": score,
            "source_independence_score": score,
            "target_alignment_score": score,
        }

    # Both slot 1 top choice and slot 2 top choice have DIFFERENT full metric strings,
    # yet share the BCBS 239 + 99.9% fingerprint. Slot 2 must fall back to its non-colliding alternative.
    candidate_sets = {
        "bul_ibm_001": [
            _cand(
                "c_b1_bcbs",
                "bul_ibm_001",
                "sk_ibm_1",
                "reb_ibm_aws_modernization_architecture",
                "metric_ibm_regulated_reference_architecture_reuse",
                "BCBS 239-aligned cloud reference architectures sustaining 99.9% production uptime across regulated financial environments",
                0.95,
            ),
        ],
        "bul_ibm_002": [
            _cand(
                "c_b2_dup_bcbs",
                "bul_ibm_002",
                "sk_ibm_2",
                "reb_ibm_offering_accelerator_management",
                "metric_ibm_reusable_aws_partner_blueprints",
                "BCBS 239-aligned AWS partner solution blueprints and reusable migration accelerators sustaining 99.9% production uptime",
                0.94,
            ),
            _cand(
                "c_b2_streaming",
                "bul_ibm_002",
                "sk_ibm_3",
                "reb_ibm_offering_accelerator_management",
                "metric_ibm_aws_streaming_partner_pipelines",
                "Reusable streaming analytics ecosystems and partner data-provider onboarding playbooks",
                0.85,
            ),
        ],
    }

    plan = allocate_candidate_sets(
        candidate_sets=candidate_sets,
        slot_specs=slot_specs,
        graph_digest="gd_test",
        policy_digest="pd_test",
    )
    selected_ids = {row["claim_unit_id"]: row["candidate_id"] for row in plan["assignments"]}
    assert selected_ids["bul_ibm_001"] == "c_b1_bcbs"
    assert selected_ids["bul_ibm_002"] == "c_b2_streaming"
    assert plan["uniqueness_receipt"]["pass"] is True
    assert plan["uniqueness_receipt"]["repeated_metric_fingerprint_tokens"] == []


def test_c03_health_reports_same_employer_fingerprint_collisions() -> None:
    from apps_rg.fact_inventory.c03_graph_kpi_health import detect_same_employer_metric_fingerprint_collisions

    collisions = detect_same_employer_metric_fingerprint_collisions()
    ibm_pairs = {
        (row["left_metric_outcome_id"], row["right_metric_outcome_id"]): row["shared_fingerprint_tokens"]
        for row in collisions
        if row["employer"].upper() == "IBM"
    }
    assert any(
        "sig:bcbs 239" in tokens and "num:99.9%" in tokens
        for tokens in ibm_pairs.values()
    )
    assert any("num:$10m" in tokens for tokens in ibm_pairs.values())


def test_wave3_section_and_cross_section_gates_fail_closed_on_anthropic_fixture() -> None:
    from apps_rg.runtime.aggregation.cross_section.gate_runner import run_cross_section_x2_gates
    from apps_rg.runtime.aggregation.warn_policy import (
        cross_section_product_pass,
        cross_section_structural_pass,
        evaluate_warn_policy,
    )
    from apps_rg.runtime.validators.ibm_bullets_x2 import run_ibm_bullets_x2_gates

    fixture_data, _ = _load_anthropic_fixture_units()
    ibm_bullet_rows = [
        {"bullet_id": f"bul_ibm_00{i}", "bullet_text": txt, "source_fact_ids": [f"bul_ibm_00{i}"]}
        for i, txt in enumerate(fixture_data["ibm_bullets"], start=1)
    ]
    ibm_gates = run_ibm_bullets_x2_gates(
        bullets=ibm_bullet_rows,
        parsed_output={"bullets": ibm_bullet_rows},
        claim_ledger=[],
        allowed_fact_ids={f"bul_ibm_00{i}" for i in range(1, 6)},
        jd_text="",
        runtime_generation_status="REAL_LLM",
    )
    by_gid = {g.gate_id: g for g in ibm_gates}
    assert "x2_overlap_engine" in by_gid
    assert by_gid["x2_overlap_engine"].pass_ is False
    assert "bcbs 239" in str(by_gid["x2_overlap_engine"].failure_reason).lower()

    # Cross-section assembly gate runner must emit FAIL (never WARN)
    final_resume_blob = {
        "sections": [
            {
                "section_id": "executive_summary",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "resume_display_text": " ".join(fixture_data["executive_summary_sentences"]),
                    "claim_ledger": [],
                },
            },
            {
                "section_id": "ibm_narrative",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "narrative_sentence": fixture_data["ibm_narrative"],
                    "claim_ledger": [],
                },
            },
            {
                "section_id": "ibm_bullets",
                "section_kind": "generated_lane",
                "l2_output_snapshot": {
                    "bullets": ibm_bullet_rows,
                    "claim_ledger": [],
                },
            },
        ]
    }
    cross_gates, *_ = run_cross_section_x2_gates(
        repo=Path(__file__).resolve().parents[2],
        final_resume_blob=final_resume_blob,
        fingerprint={},
        sealed_index={},
    )
    cross_by_id = {g.gate_id: g for g in cross_gates}
    assert cross_by_id["x2_overlap_engine"].verdict == "FAIL"
    assert cross_by_id["x2_cross_section_section_intent_conflict"].verdict == "FAIL"
    assert cross_section_structural_pass(cross_gates) is False
    assert cross_section_product_pass(cross_gates) is False
    wp = evaluate_warn_policy(cross_gates=cross_gates)
    assert "x2_overlap_engine" in wp["fail_gate_ids"]
    assert "x2_cross_section_section_intent_conflict" in wp["fail_gate_ids"]


def test_wave4_judge_rubrics_enforce_decisive_failure_on_repeats_and_ban_company_carveouts() -> None:
    from apps_rg.runtime.assembly.full_resume_llm_coherence_rubric import FULL_RESUME_COHERENCE_RUBRIC
    from apps_rg.runtime.judges.competencies_x1d import COMPETENCIES_RUBRIC
    from apps_rg.runtime.judges.employment_bullet_judge_rubric import grade_only_rubric_text
    from apps_rg.runtime.judges.executive_summary_judge_packet import (
        GRAPH_ONLY_GRADE_ONLY_RUBRIC,
        SRFS_GRADE_ONLY_RUBRIC,
    )
    from apps_rg.runtime.judges.grade_only_judge_packet import build_grade_only_judge_packet
    from apps_rg.runtime.judges.ibm_narrative_x1d import NARRATIVE_RUBRIC as IBM_NARRATIVE_RUBRIC
    from apps_rg.runtime.judges.role_episode_x1d import ROLE_EPISODE_RUBRIC
    from apps_rg.runtime.judges.unify_narrative_x1d import NARRATIVE_RUBRIC as UNIFY_NARRATIVE_RUBRIC

    rubrics = {
        "ibm_bullets": grade_only_rubric_text("ibm_bullets", bullet_count=5, bullet_id_range="bul_ibm_001..005"),
        "unify_bullets": grade_only_rubric_text("unify_bullets", bullet_count=6, bullet_id_range="bul_unify_001..006"),
        "ibm_narrative": IBM_NARRATIVE_RUBRIC,
        "unify_narrative": UNIFY_NARRATIVE_RUBRIC,
        "role_episode": ROLE_EPISODE_RUBRIC,
        "competencies": COMPETENCIES_RUBRIC,
        "exec_summary_srfs": SRFS_GRADE_ONLY_RUBRIC,
        "exec_summary_graph": GRAPH_ONLY_GRADE_ONLY_RUBRIC,
        "full_resume_coherence": FULL_RESUME_COHERENCE_RUBRIC,
    }
    banned_target_company_carveouts = ("truist", "blend360", "brown & brown", "e.g. anthropic")
    for name, text in rubrics.items():
        lower = text.lower()
        assert "decisive_failure=true and pass=false" in lower, f"{name} missing decisive failure repeat rule"
        assert "never excuse a repeated standard or figure as 'minor'" in lower, f"{name} missing anti-minor excuse rule"
        for banned in banned_target_company_carveouts:
            assert banned not in lower, f"{name} contains target-company carve-out {banned!r}"

    # Verify JudgePacket receives the Overlap Engine report on the Anthropic IBM block
    fixture_data, _ = _load_anthropic_fixture_units()
    ibm_bullet_rows = [
        {"bullet_id": f"bul_ibm_00{i}", "bullet_text": txt, "source_fact_ids": [f"bul_ibm_00{i}"]}
        for i, txt in enumerate(fixture_data["ibm_bullets"], start=1)
    ]
    pkt = build_grade_only_judge_packet(
        section_id="ibm_bullets",
        candidate_output={"bullets": ibm_bullet_rows},
        section_rubric=rubrics["ibm_bullets"],
        rubric_ref="test_ref",
    )
    ov_rep = pkt["overlap_engine_report"]
    assert ov_rep["verdict"] == "FAIL"
    assert "bcbs 239" in ov_rep["repeated_signature_terms"]
    assert "99.9%" in ov_rep["repeated_numbers"]
    assert "$10m" in ov_rep["repeated_numbers"]


def test_wave5_domain_literal_ratchet_and_standard_exemption_ban() -> None:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.lint_apps_rg_domain_literals import audit_apps_rg_domain_literals

    errors = audit_apps_rg_domain_literals(repo_root)
    assert errors == [], f"Domain literal ratchet failed: {errors}"


def test_wave0_and_wave5_overlap_replay_entrypoints(tmp_path: Path) -> None:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from ops_scripts.apps_rg_overlap_replay import (
        collect_existing_gate_verdicts,
        extract_number_tokens,
        main as replay_main,
        normalize_number_token,
        parse_final_resume_units,
        resolve_proofs_dirs,
        run_baseline,
        run_parity,
        scan_baseline_flaws_for_units,
    )

    assert normalize_number_token("$10 Million") == "$10m"
    assert extract_number_tokens("Drove $10M and 99.9% uptime") == ["$10m", "99.9%"]
    sample_resume = (
        "AMIT AYER\n"
        "Edgewater, NJ\n"
        "Enterprise AI Leader | Cloud Architecture | Agentic Governance\n"
        "EXECUTIVE SUMMARY\n"
        "Built governed multi-agent platforms across banking and insurance enterprises. "
        "Directed 105 engineers delivering cloud transformations.\n"
        "CORE COMPETENCIES\n"
        "Architecture: Agentic AI Architecture, Cloud Modernization\n"
        "PROFESSIONAL EXPERIENCE\n"
        "IBM — Partner\n"
        "Edgewater, NJ | Apr 2017 – Oct 2022\n"
        "Operationalized AWS modernization at IBM across banking clients.\n"
        "• Directed AWS Partner blueprints aligned to BCBS 239 holding 99.9% uptime.\n"
        "• Architected enterprise cloud landing zones aligned to BCBS 239 holding 99.9% uptime.\n"
    )
    units = parse_final_resume_units(sample_resume)
    assert len(units) >= 5
    flaws = scan_baseline_flaws_for_units(units)
    assert flaws["has_flaws"] is True
    assert "99.9%" in flaws["repeated_numbers"]
    assert collect_existing_gate_verdicts(tmp_path)["present"] is False
    proof_dirs = resolve_proofs_dirs()
    assert isinstance(proof_dirs, list)
    baseline_out = tmp_path / "baseline_ledger.json"
    parity_out = tmp_path / "parity.json"
    b_res = run_baseline(baseline_out)
    assert b_res["total_resumes"] == len(proof_dirs)
    p_res = run_parity(baseline_out, parity_out)
    assert p_res["parity_100_percent"] is True
    assert replay_main(["--mode", "parity", "--out-dir", str(tmp_path)]) == 0


