"""Wave 6 E2E certification: multi-JD allocation, ATS must-have coverage, PCT gate, DOCX lineage seal."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps_rg.runtime.aggregation.cross_section.gate_runner import run_cross_section_x2_gates
from apps_rg.runtime.assembly.full_resume_text import flatten_final_resume_to_text
from apps_rg.runtime.c0.allocation.orchestration import build_whole_resume_graph_allocation
from apps_rg.runtime.c0.allocation.contracts_and_validation import validate_resume_graph_allocation_plan
from apps_rg.runtime.exit.resume_exit_checks import CheckVerdict, run_exit_checks
from apps_rg.runtime.final_resume_docx import export as export_docx, read_docx_custom_properties
from apps_rg.runtime.validators.ats_validator import evaluate_ats_jd_requirement_coverage
from apps_rg.runtime.validators.proof_carrying_text_verifier import (
    build_pct_certificate,
    verify_pct_certificate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_spine_fixture(*, headline: str, summary: str, competencies: list[str], bullet_text: str) -> dict:
    return {
        "candidate_identity": {
            "candidate_name": "Amit Ayer",
            "location": "New York, NY",
            "email": "amit@example.com",
            "phone": "+1-555-0100",
        },
        "sections": [
            {
                "section_id": "headline",
                "section_kind": "generated_lane",
                "rendered_text": headline,
                "l2_output_snapshot": {
                    "headline_line": headline,
                    "claim_ledger": [
                        {"claim_text": headline, "source_fact_ids": ["fact_certs_001", "fact_engineering_platform_001"]}
                    ],
                },
            },
            {
                "section_id": "executive_summary",
                "section_kind": "generated_lane",
                "rendered_text": summary,
                "l2_output_snapshot": {
                    "resume_display_text": summary,
                    "claim_ledger": [
                        {"claim_text": summary, "source_fact_ids": ["fact_solvency_001", "fact_rag_insurance_001"]}
                    ],
                },
            },
            {
                "section_id": "competencies",
                "section_kind": "generated_lane",
                "rendered_text": " | ".join(competencies),
                "l2_output_snapshot": {
                    "categories": [
                        {"category_label": "Core Competencies", "terms": competencies}
                    ],
                    "claim_ledger": [
                        {"claim_text": c, "source_fact_ids": ["fact_governance_001"]} for c in competencies
                    ],
                },
            },
            {
                "section_id": "unify_bullets",
                "section_kind": "generated_lane",
                "rendered_text": bullet_text,
                "l2_output_snapshot": {
                    "bullets": [{"text": bullet_text}],
                    "claim_ledger": [
                        {"claim_text": bullet_text, "source_fact_ids": ["fact_rag_insurance_001"]}
                    ],
                },
            },
        ],
    }


def test_wave6_multi_jd_allocation_ats_pct_and_docx_lineage_seal(tmp_path: Path) -> None:
    # 1. Insurance / Risk Chief AI Officer whole-resume graph allocation
    ins_jd = (
        "Chief AI Officer for regulated insurer owning Solvency II capital modeling, "
        "AG43 reserving, Enterprise Risk Management (ERM), Fellow of the Society of Actuaries (FSA) rigor, "
        "Guidewire claims and underwriting modernization, GraphRAG retrieval, and AWS AI governance."
    )
    ins_bundle = build_whole_resume_graph_allocation(
        repo_root=REPO_ROOT,
        target_role="Chief AI Officer, Regulated Insurance",
        jd_text=ins_jd,
    )
    ins_plan = ins_bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(ins_plan) == []
    assert ins_plan["quad_retrieval_receipt"]["executed"] is True
    assert ins_plan["mandate_route"]["track_weights"]["track_actuarial_risk_derivatives"] >= 0.22
    assert "cert_fsa_001" in ins_plan["credential_elevation_ids"]

    # 2. General Tech SVP Engineering whole-resume graph allocation (no actuarial spam)
    tech_jd = (
        "SVP Engineering scaling multi-agent LLM platforms, distributed systems, microservices, "
        "cloud modernization on AWS, and LLMOps reliability."
    )
    tech_bundle = build_whole_resume_graph_allocation(
        repo_root=REPO_ROOT,
        target_role="SVP Engineering, AI Platforms",
        jd_text=tech_jd,
    )
    tech_plan = tech_bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(tech_plan) == []
    assert tech_plan["quad_retrieval_receipt"]["executed"] is True
    assert tech_plan["mandate_route"]["track_weights"]["track_actuarial_risk_derivatives"] <= 0.12
    assert tech_plan["two_page_slot_budget"]["ey_bullets"] == 1
    assert tech_plan["two_page_slot_budget"]["early_career_bullets"] == 1

    # 3. ATS JD requirement coverage closeout gate (pass + fail-closed missing terms)
    spine = _build_spine_fixture(
        headline="Chief AI Officer | Fellow of the Society of Actuaries (FSA) | Governed AI Architecture",
        summary=(
            "Executive AI leader uniting Fellow of the Society of Actuaries (FSA) rigor, "
            "Enterprise Risk Management (ERM), Solvency II and AG43 actuarial governance, "
            "and Retrieval-Augmented Generation (RAG) with GraphRAG platforms on AWS."
        ),
        competencies=[
            "Enterprise Risk Management (ERM)",
            "Guidewire Underwriting & Claims Modernization",
            "AWS AI Governance & GraphRAG",
        ],
        bullet_text=(
            "Architected governed GraphRAG and multi-agent AI governance workflows for regulated "
            "underwriting and claims automation on AWS."
        ),
    )
    ats_pass = evaluate_ats_jd_requirement_coverage(spine, ins_jd, min_coverage=0.70)
    assert ats_pass.passed is True
    assert ats_pass.coverage_ratio >= 0.85
    assert "fsa" in ats_pass.acronym_pair_hits
    assert "erm" in ats_pass.acronym_pair_hits

    ats_fail = evaluate_ats_jd_requirement_coverage(
        {"headline": "General Operations Manager"},
        ins_jd,
        min_coverage=0.70,
    )
    assert ats_fail.passed is False
    assert len(ats_fail.missing_terms) >= 5

    # 4. Proof-Carrying Text certificate + cross-section X2 closeout wiring
    rendered = flatten_final_resume_to_text(spine)
    allowed_facts = {
        "fact_certs_001",
        "fact_engineering_platform_001",
        "fact_solvency_001",
        "fact_rag_insurance_001",
        "fact_governance_001",
    }
    pct_cert = build_pct_certificate(
        generated_text=rendered,
        claimed_fact_ids=sorted(allowed_facts),
        banned_words_clean=True,
    )
    assert verify_pct_certificate(rendered, pct_cert, allowed_fact_ids=allowed_facts) is True
    tampered_cert = dict(pct_cert, text_hash="0" * 64)
    assert verify_pct_certificate(rendered, tampered_cert, allowed_fact_ids=allowed_facts) is False

    gates, *_ = run_cross_section_x2_gates(
        repo=REPO_ROOT,
        final_resume_blob=spine,
        fingerprint={},
        sealed_index={},
        jd_text=ins_jd,
        ats_min_coverage=0.70,
        pct_certificate=pct_cert,
        pct_allowed_fact_ids=allowed_facts,
    )
    gate_map = {g.gate_id: g for g in gates}
    assert gate_map["x2_cross_section_ats_jd_coverage"].verdict == "PASS"
    assert gate_map["x2_cross_section_pct_certificate"].verdict == "PASS"

    # 5. Exit checks H_ATS_COVERAGE and H_PCT_CERTIFICATE fail closed on violations
    exit_fail = run_exit_checks(
        {
            "headline": {"text": "Chief AI Officer"},
            "executive_summary": {"text": "Governed enterprise AI leadership across regulated insurance systems."},
            "roles": [],
            "competencies": {"items": ["Enterprise Risk Management", "Governed AI Platforms"]},
            "ats_coverage_receipt": ats_fail.to_dict(),
            "pct_certificate": tampered_cert,
            "rendered_text": rendered,
        }
    )
    exit_ids = {r.check_id: r.verdict for r in exit_fail.check_results}
    assert exit_ids["H_ATS_COVERAGE"] == CheckVerdict.FAIL
    assert exit_ids["H_PCT_CERTIFICATE"] == CheckVerdict.FAIL
    assert exit_fail.sendable is False

    # 6. DOCX custom properties lineage seal
    pct_sha = hashlib.sha256(json.dumps(pct_cert, sort_keys=True).encode("utf-8")).hexdigest()
    spine["pct_certificate"] = pct_cert
    spine["lineage"] = {
        "build_run_id": "run_wave6_e2e_test",
        "sqlite_graph_digest": ins_plan["selection_policy"]["graph_snapshot_digest"],
        "base_resume_json_hash": "base_resume_sha_wave6_verified",
        "pct_certificate_sha256": pct_sha,
        "ats_coverage_ratio": f"{ats_pass.coverage_ratio:.4f}",
    }
    json_path = tmp_path / "final_resume.json"
    docx_path = tmp_path / "final_resume.docx"
    json_path.write_text(json.dumps(spine, indent=2), encoding="utf-8")
    export_docx(json_path, docx_path)

    sealed_props = read_docx_custom_properties(docx_path)
    assert sealed_props["build_run_id"] == "run_wave6_e2e_test"
    assert sealed_props["sqlite_graph_digest"] == ins_plan["selection_policy"]["graph_snapshot_digest"]
    assert sealed_props["base_resume_json_hash"] == "base_resume_sha_wave6_verified"
    assert sealed_props["pct_certificate_sha256"] == pct_sha
    assert sealed_props["ats_coverage_ratio"] == f"{ats_pass.coverage_ratio:.4f}"
    assert sealed_props["rendered_text_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
