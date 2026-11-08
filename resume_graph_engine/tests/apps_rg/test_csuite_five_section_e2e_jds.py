"""End-to-end verification of the unified canonical pipeline across Brown & Brown, AIG, and Citi."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.assembly.competencies_display import csuite_capability_display_rows
from apps_rg.runtime.assembly.full_resume_text import (
    flatten_final_resume_to_text,
    format_cert,
    format_edu,
)
from apps_rg.runtime.final_resume_outputs import emit_final_resume_product_outputs
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    CORE_EXPERIENCE_2017_PLUS_EMPLOYERS,
    FINAL_BULLET_COUNT,
    PEDIGREE_CAPSULE_PRE_2017_EMPLOYERS,
    REQUIRED_BULLET_IDS,
)
from apps_rg.runtime.run_output_contract import (
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_OUTPUT_TXT,
)
from apps_rg.runtime.sections.competencies_rigor import CSUITE_CAPABILITY_CATEGORY_LABELS

REPO_ROOT = Path(__file__).resolve().parents[3]
RG_SRC_ROOT = REPO_ROOT / "resume_graph_engine" / "src"
BASE_RESUME_PATH = RG_SRC_ROOT / "apps_rg" / "resume" / "base" / "amit_ayer_base_resume_v1.json"
COMP_BUNDLES_PATH = RG_SRC_ROOT / "apps_rg" / "fact_inventory" / "competency_capability_bundles.json"
TARGETING_DIR = RG_SRC_ROOT / "apps_rg" / "config" / "targeting"

TARGET_JDS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "brown_brown",
        "Brown & Brown",
        "SVP IT Strategy & Innovation",
        "brown_brown_svp_it_strategy_innovation_jd.txt",
        "brown_brown_svp_it_strategy_innovation_briefing.md",
    ),
    (
        "aig",
        "AIG",
        "VP Global Head Agentic AI",
        "aig_vp_global_head_agentic_ai_jd.txt",
        "aig_vp_global_head_agentic_ai_briefing.md",
    ),
    (
        "citi",
        "Citi",
        "Head of AI Strategy - Firmwide AI",
        "citi_head_of_ai_strategy_jd.txt",
        "citi_head_of_ai_strategy_briefing.md",
    ),
)


def _load_base_resume() -> dict[str, Any]:
    return json.loads(BASE_RESUME_PATH.read_text(encoding="utf-8"))


def test_canonical_base_fact_store_and_consolidated_role_contract() -> None:
    """Base facts load with consolidated Ernst & Young / Early Career Roles and 2-bullet InsurTech contract."""
    base = _load_base_resume()
    facts = base["facts"]
    employment = facts["employment"]

    assert [e["employer"] for e in employment] == [
        "Slalom",
        "Unify Consulting",
        "IBM",
        "InsurTech Cloud Solutions",
        "Ernst & Young / Early Career Roles",
    ]
    assert FINAL_BULLET_COUNT["insurtech_bullets"] == 2
    assert REQUIRED_BULLET_IDS["insurtech_bullets"] == ("bul_insurtech_001", "bul_insurtech_002")
    assert FINAL_BULLET_COUNT["ey_bullets"] == 0
    assert REQUIRED_BULLET_IDS["ey_bullets"] == ()

    comp_bundles = json.loads(COMP_BUNDLES_PATH.read_text(encoding="utf-8"))
    bundle_ids = {b["competency_bundle_id"] for b in comp_bundles["bundles"]}
    assert "ccb_insurance_domain_erm" in bundle_ids


def test_canonical_competency_rows_and_role_Consolidation(tmp_path: Path) -> None:
    """Canonical pipeline renders standard headings, 2 InsurTech bullets, and consolidated Early Career."""
    assert CORE_EXPERIENCE_2017_PLUS_EMPLOYERS == ("Slalom", "Unify Consulting", "IBM")
    assert PEDIGREE_CAPSULE_PRE_2017_EMPLOYERS == (
        "InsurTech Cloud Solutions",
        "Ernst & Young / Early Career Roles",
    )

    base = _load_base_resume()
    cap_rows = csuite_capability_display_rows(base)
    assert len(cap_rows) == 6
    assert tuple(label for label, _ in cap_rows) == CSUITE_CAPABILITY_CATEGORY_LABELS

    contract = emit_final_resume_product_outputs(
        tmp_path,
        repo_root=RG_SRC_ROOT,
        required=True,
        target_company="AIG",
        target_role="VP Global Head Agentic AI",
        jd_text=(TARGETING_DIR / "aig_vp_global_head_agentic_ai_jd.txt").read_text(encoding="utf-8"),
        briefing_text=(TARGETING_DIR / "aig_vp_global_head_agentic_ai_briefing.md").read_text(encoding="utf-8"),
    )
    assert contract["status"] == "PASS"
    rendered = (tmp_path / FINAL_RESUME_OUTPUT_TXT).read_text(encoding="utf-8")

    for heading in (
        "HEADLINE",
        "EXECUTIVE SUMMARY",
        "ENGINEERING & PLATFORM COMPETENCIES",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        "CERTIFICATIONS & CREDENTIALS",
    ):
        assert heading in rendered

    insurtech_idx = rendered.index("InsurTech Cloud Solutions \u2014 Chief Technology Officer")
    early_idx = rendered.index("Ernst & Young / Early Career Roles \u2014 Principal / Actuarial & Quantitative Consultant")
    edu_idx = rendered.index("EDUCATION")

    insurtech_block = rendered[insurtech_idx:early_idx]
    early_block = rendered[early_idx:edu_idx]

    insurtech_bullets = [ln for ln in insurtech_block.splitlines() if ln.strip().startswith("\u2022")]
    assert len(insurtech_bullets) == 2

    early_bullets = [ln for ln in early_block.splitlines() if ln.strip().startswith("\u2022")]
    assert len(early_bullets) == 4
    assert "Solvency II and AG43" in early_block
    assert "multi-Greek hedging" in early_block


def test_canonical_education_and_certification_formatters() -> None:
    """Verify format_edu and format_cert support both standard and dateless modes."""
    edu_sample = {"degree": "M.S. in Biostatistics", "institution": "Columbia University", "year": "2002"}
    cert_sample = {"name": "Fellow of the Society of Actuaries", "year": "2010"}
    assert "2002" in format_edu(edu_sample, dateless=False)
    assert "2002" not in format_edu(edu_sample, dateless=True)
    assert "2010" in format_cert(cert_sample, dateless=False)
    assert "2010" not in format_cert(cert_sample, dateless=True)


@pytest.mark.parametrize(("slug", "company", "role", "jd_filename", "briefing_filename"), TARGET_JDS)
def test_canonical_pipeline_e2e_across_three_jds(
    tmp_path: Path,
    slug: str,
    company: str,
    role: str,
    jd_filename: str,
    briefing_filename: str,
) -> None:
    """End-to-end canonical pipeline resume generation, whole-resume graph allocation, and DOCX verification."""
    jd_path = TARGETING_DIR / jd_filename
    briefing_path = TARGETING_DIR / briefing_filename
    assert jd_path.is_file(), f"Missing target JD: {jd_path}"
    assert briefing_path.is_file(), f"Missing target briefing: {briefing_path}"

    run_dir = tmp_path / slug
    contract = emit_final_resume_product_outputs(
        run_dir,
        repo_root=RG_SRC_ROOT,
        required=True,
        target_company=company,
        target_role=role,
        jd_text=jd_path.read_text(encoding="utf-8"),
        briefing_text=briefing_path.read_text(encoding="utf-8"),
    )
    assert contract["status"] == "PASS"
    assert contract["failed_gate_ids"] == []

    gp = contract["graph_evidence_plan"]
    assert len(str(gp.get("plan_digest") or "")) == 64
    assert len(str(gp.get("allocation_plan_digest") or "")) == 64
    assert gp["assignment_count"] == 48
    assert gp["selected_skill_ids"]
    if slug == "brown_brown":
        assert gp["target_role_profile"] == "insurance_it_strategy"
        assert "insurance_domain_modernization" in gp["selected_competency_families"]
    elif slug == "aig":
        assert gp["target_role_profile"] == "insurance_agentic_ai"
        assert "insurance_domain_modernization" in gp["selected_competency_families"]
        assert "agentic_platforms" in gp["selected_competency_families"]
    elif slug == "citi":
        assert gp["target_role_profile"] == "balanced_enterprise_ai"
        assert "data_governance_security" in gp["selected_competency_families"]

    spine_file = run_dir / FINAL_RESUME_ASSEMBLY_JSON_RELPATH
    txt_file = run_dir / FINAL_RESUME_OUTPUT_TXT
    docx_file = run_dir / FINAL_RESUME_DOCX_RELPATH
    assert spine_file.is_file()
    assert txt_file.is_file() and txt_file.stat().st_size > 1500
    assert docx_file.is_file() and docx_file.stat().st_size > 2000

    rendered_txt = txt_file.read_text(encoding="utf-8")
    assert company in rendered_txt
    assert role in rendered_txt
    assert "github.com/Siamese001/agents" in rendered_txt.splitlines()[1]
    assert "Boca Raton, FL" not in rendered_txt.splitlines()[1]


def test_canonical_exec_summary_synthesis_calibration_and_anti_past_title_gate(tmp_path: Path) -> None:
    """Verify canonical executive summary matches the 6-sentence calibration contract and rejects past-title lists."""
    import yaml
    from apps_rg.runtime.validators.executive_summary_x2 import (
        check_exec_summary_meta_filler_patterns,
        check_exec_summary_no_credential_dump,
        check_exec_summary_no_mechanism_inventory,
        check_exec_summary_paragraph_max_words,
        check_exec_summary_sentence_count_6,
        check_exec_summary_stock_bridge_count,
        check_synthesis_quality,
    )

    citi_dir = tmp_path / "citi"
    emit_final_resume_product_outputs(
        citi_dir,
        repo_root=RG_SRC_ROOT,
        required=True,
        target_company="Citi",
        target_role="Head of AI Strategy - Firmwide AI",
        jd_text=(TARGETING_DIR / "citi_head_of_ai_strategy_jd.txt").read_text(encoding="utf-8"),
        briefing_text=(TARGETING_DIR / "citi_head_of_ai_strategy_briefing.md").read_text(encoding="utf-8"),
    )
    spine = json.loads((citi_dir / FINAL_RESUME_ASSEMBLY_JSON_RELPATH).read_text(encoding="utf-8"))
    rendered = flatten_final_resume_to_text(spine)
    exec_sec = next(s for s in spine["sections"] if s["section_id"] == "executive_summary")
    thesis = exec_sec["l2_output_snapshot"]["resume_display_text"]

    for fn in (
        check_exec_summary_sentence_count_6,
        check_exec_summary_paragraph_max_words,
        check_exec_summary_meta_filler_patterns,
        check_exec_summary_no_credential_dump,
        check_exec_summary_no_mechanism_inventory,
        check_exec_summary_stock_bridge_count,
        check_synthesis_quality,
    ):
        ok, reason = fn(thesis)
        assert ok is True, f"{fn.__name__} failed: {reason}"

    for bad_phrase in ("former CTO", "Big-4 Principal", "past principal", "past CTO"):
        ok_bad, _ = check_exec_summary_meta_filler_patterns(f"Enterprise executive and {bad_phrase} scaling AI.")
        assert ok_bad is False

    root_prof = yaml.safe_load((REPO_ROOT / "config" / "provider_profiles.yaml").read_text(encoding="utf-8"))
    rg_prof = yaml.safe_load((RG_SRC_ROOT / "apps_rg" / "config" / "provider_profiles.yaml").read_text(encoding="utf-8"))
    cal_root = root_prof["ide_argon4_routing_policy"]["executive_summary_synthesis_calibration"]
    cal_rg = rg_prof["ide_argon4_routing_policy"]["executive_summary_synthesis_calibration"]
    assert cal_root == cal_rg
    assert cal_root["sentence_count_exact"] == 6
    assert cal_root["thesis_first_generation"] is True
    assert cal_root["forbid_past_title_stacking"] is True

    bb_dir = tmp_path / "bb"
    emit_final_resume_product_outputs(
        bb_dir,
        repo_root=RG_SRC_ROOT,
        required=True,
        target_company="Brown & Brown",
        target_role="SVP IT Strategy & Innovation",
        jd_text=(TARGETING_DIR / "brown_brown_svp_it_strategy_innovation_jd.txt").read_text(encoding="utf-8"),
        briefing_text=(TARGETING_DIR / "brown_brown_svp_it_strategy_innovation_briefing.md").read_text(encoding="utf-8"),
    )
    bb_rendered = (bb_dir / FINAL_RESUME_OUTPUT_TXT).read_text(encoding="utf-8")
    assert "github.com/Siamese001/agents" in bb_rendered.splitlines()[1]
    assert "Boca Raton, FL" not in bb_rendered.splitlines()[1]
    assert "Insurance Domain, Actuarial Risk & Carrier Operations" in bb_rendered
    assert "Solvency II and AG43" in bb_rendered
    assert "Ernst & Young / Early Career Roles" in bb_rendered
    assert "HEADLINE" in rendered
