"""End-to-end verification of the 5-Section Seven-Figure C-Suite Executive Resume across all 3 JDs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from apps_rg.bare_pipeline import run_csuite_five_section_jd_e2e
from apps_rg.runtime.assembly.competencies_display import csuite_capability_display_rows
from apps_rg.runtime.assembly.full_resume_text import (
    flatten_csuite_five_section_resume_to_text,
    format_cert,
    format_edu,
    format_value_bar_text,
)
from apps_rg.runtime.final_resume_outputs import (
    emit_csuite_five_section_outputs,
    validate_csuite_five_section_text,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    CORE_EXPERIENCE_2017_PLUS_EMPLOYERS,
    CSUITE_EXPERIENCE_SPACE_SPLIT,
    PEDIGREE_CAPSULE_PRE_2017_EMPLOYERS,
)
from apps_rg.runtime.section_display_labels import (
    CSUITE_FIVE_SECTION_HEADINGS,
    DATELESS_CREDENTIALS_FOOTER_HEADING,
    EXECUTIVE_AGENTIC_CAPABILITIES_HEADING,
    EXECUTIVE_EXPERIENCE_2017_PRESENT_HEADING,
    EXECUTIVE_INVESTMENT_THESIS_HEADING,
    PRIOR_CSUITE_PEDIGREE_HEADING,
    resolve_competencies_heading,
)
from apps_rg.runtime.sections.competencies_rigor import CSUITE_CAPABILITY_CATEGORY_LABELS
from apps_rg.runtime.sections.section_product_shape_ssot import (
    CSUITE_CAPABILITY_CATEGORY_COUNT,
    CSUITE_FIVE_SECTION_COUNT,
    CSUITE_VALUE_BAR_COLUMN_COUNT,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RG_SRC_ROOT = REPO_ROOT / "resume_graph_engine" / "src"
BASE_RESUME_PATH = RG_SRC_ROOT / "apps_rg" / "resume" / "base" / "amit_ayer_base_resume_v1.json"
RG_SCHEMA_PATH = RG_SRC_ROOT / "apps_rg" / "rg_output_schema.json"
SLALOM_BUNDLES_PATH = RG_SRC_ROOT / "apps_rg" / "fact_inventory" / "slalom_role_episode_bundles.json"
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


def test_wave1_base_fact_store_and_five_section_contract() -> None:
    """Wave 1: Base facts load with 4 Value Bar metrics, 6 capability categories, and 5-section headings."""
    base = _load_base_resume()
    facts = base["facts"]

    # 1. 4-column Value Bar
    value_bar = facts.get("value_bar")
    assert isinstance(value_bar, list)
    assert len(value_bar) == CSUITE_VALUE_BAR_COLUMN_COUNT == 4
    headers = [c["header"] for c in value_bar]
    assert headers == [
        "$82M+ COMMERCIAL P&L",
        "+20% MARGIN & COST",
        "106-ENGINEER SCALE",
        "VELOCITY & SAFETY",
    ]

    # 2. 6 capability categories absorbing flagship platforms
    csuite_caps = facts.get("csuite_capability_categories")
    assert isinstance(csuite_caps, list)
    assert len(csuite_caps) == CSUITE_CAPABILITY_CATEGORY_COUNT == 6
    assert tuple(c["category"] for c in csuite_caps) == CSUITE_CAPABILITY_CATEGORY_LABELS

    # 3. 5-section headings & schema fields
    assert len(CSUITE_FIVE_SECTION_HEADINGS) == CSUITE_FIVE_SECTION_COUNT == 5
    assert CSUITE_FIVE_SECTION_HEADINGS == (
        EXECUTIVE_INVESTMENT_THESIS_HEADING,
        EXECUTIVE_AGENTIC_CAPABILITIES_HEADING,
        EXECUTIVE_EXPERIENCE_2017_PRESENT_HEADING,
        PRIOR_CSUITE_PEDIGREE_HEADING,
        DATELESS_CREDENTIALS_FOOTER_HEADING,
    )
    assert resolve_competencies_heading("csuite_five_section") == EXECUTIVE_AGENTIC_CAPABILITIES_HEADING

    schema = json.loads(RG_SCHEMA_PATH.read_text(encoding="utf-8"))
    sec_props = schema["properties"]["sections"]["properties"]
    assert "value_bar" in sec_props
    assert "prior_leadership_capsule" in sec_props
    assert "dateless_credentials" in sec_props

    # 4. Slalom & Competency bundle stores mark flagship absorption
    slalom_bundles = json.loads(SLALOM_BUNDLES_PATH.read_text(encoding="utf-8"))
    comp_bundles = json.loads(COMP_BUNDLES_PATH.read_text(encoding="utf-8"))
    assert slalom_bundles["invariants"]["csuite_five_section_flagship_absorbed"] is True
    assert comp_bundles["invariants"]["csuite_five_section_flagship_absorbed"] is True


def test_wave2_section1_value_bar_and_section2_flagship_capabilities() -> None:
    """Wave 2: Section 1 renders headline, 4-column Value Bar, and 6-sentence thesis; Section 2 renders 6 categories."""
    base = _load_base_resume()
    vb_lines = format_value_bar_text(base["facts"]["value_bar"])
    assert len(vb_lines) >= 5
    vb_blob = "\n".join(vb_lines)
    for token in ("$82M+ COMMERCIAL P&L", "+20% MARGIN & COST", "106-ENGINEER SCALE", "VELOCITY & SAFETY"):
        assert token in vb_blob

    cap_rows = csuite_capability_display_rows(base)
    assert len(cap_rows) == 6
    labels = tuple(label for label, _ in cap_rows)
    assert labels == CSUITE_CAPABILITY_CATEGORY_LABELS
    combined_summaries = " ".join(summary for _, summary in cap_rows)
    for absorbed in ("18-role", "20%-margin", "1024-d BGE-M3", "Universal Write Gateway", "$22M revenue", "FSA"):
        assert absorbed in combined_summaries


def test_wave3_section3_core_experience_and_section4_pedigree_capsule() -> None:
    """Wave 3: Section 3 renders 2017+ roles with Mandate lines; Section 4 renders pre-2017 roles as compact capsule."""
    assert CORE_EXPERIENCE_2017_PLUS_EMPLOYERS == ("Slalom", "Unify Consulting", "IBM")
    assert PEDIGREE_CAPSULE_PRE_2017_EMPLOYERS == (
        "InsurTech Cloud Solutions",
        "Ernst & Young / Early Career Roles",
    )
    assert CSUITE_EXPERIENCE_SPACE_SPLIT == {"core_2017_plus": 0.85, "pedigree_capsule_pre_2017": 0.15}

    base = _load_base_resume()
    rendered = flatten_csuite_five_section_resume_to_text(
        base,
        target_company="AIG",
        target_role="VP Global Head Agentic AI",
    )
    sec3_idx = rendered.index(f"3. {EXECUTIVE_EXPERIENCE_2017_PRESENT_HEADING}")
    sec4_idx = rendered.index(f"4. {PRIOR_CSUITE_PEDIGREE_HEADING}")
    sec5_idx = rendered.index(f"5. {DATELESS_CREDENTIALS_FOOTER_HEADING}")

    sec3_text = rendered[sec3_idx:sec4_idx]
    sec4_text = rendered[sec4_idx:sec5_idx]

    for employer in ("Slalom", "Unify Consulting", "IBM"):
        assert employer in sec3_text
        assert employer not in sec4_text
    assert sec3_text.count("Mandate:") == 3
    assert "106-software-engineer" in sec3_text
    assert "<250ms Dual-Track Live Executive Copilot" in sec3_text
    assert "Universal Write Gateway" in sec3_text

    for employer in ("InsurTech Cloud Solutions", "Ernst & Young"):
        assert employer in sec4_text
        assert employer not in sec3_text
    assert "Earlier Quantitative Foundation:" in sec4_text
    assert "Towers Perrin, ING, and Aetna" in sec4_text


def test_wave4_section5_dateless_credentials_footer_and_docx_export(tmp_path: Path) -> None:
    """Wave 4: Section 5 renders with zero four-digit years in text and Word outputs."""
    edu_sample = {"degree": "M.S. in Biostatistics", "institution": "Columbia University", "year": "2002"}
    cert_sample = {"name": "Fellow of the Society of Actuaries", "year": "2010"}
    assert "2002" in format_edu(edu_sample, dateless=False)
    assert "2002" not in format_edu(edu_sample, dateless=True)
    assert "2010" in format_cert(cert_sample, dateless=False)
    assert "2010" not in format_cert(cert_sample, dateless=True)

    report = emit_csuite_five_section_outputs(
        tmp_path,
        target_company="Brown & Brown",
        target_role="SVP IT Strategy & Innovation",
        repo_root=RG_SRC_ROOT,
    )
    assert report["status"] == "PASS"
    assert report["text_validation"]["status"] == "PASS"
    assert report["docx_validation"]["status"] == "PASS"
    assert report["text_validation"]["section5_year_tokens"] == []
    assert report["docx_validation"]["section5_year_tokens"] == []


@pytest.mark.parametrize(("slug", "company", "role", "jd_filename", "briefing_filename"), TARGET_JDS)
def test_wave5_csuite_five_section_e2e_across_three_jds(
    tmp_path: Path,
    slug: str,
    company: str,
    role: str,
    jd_filename: str,
    briefing_filename: str,
) -> None:
    """Wave 5: End-to-end 5-section C-suite resume generation and DOCX verification across all 3 target JDs."""
    jd_path = TARGETING_DIR / jd_filename
    briefing_path = TARGETING_DIR / briefing_filename
    assert jd_path.is_file(), f"Missing target JD: {jd_path}"
    assert briefing_path.is_file(), f"Missing target briefing: {briefing_path}"

    report = run_csuite_five_section_jd_e2e(
        target_company=company,
        target_role=role,
        jd_path=jd_path,
        briefing_path=briefing_path,
        artifact_root=tmp_path / slug,
    )
    assert report["status"] == "PASS"
    assert report["briefing_loaded"] is True
    assert report["text_validation"]["status"] == "PASS"
    assert report["docx_validation"]["status"] == "PASS"
    gp = report["graph_evidence_plan"]
    assert len(str(gp.get("plan_digest") or "")) == 64
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

    run_dir = Path(report["artifact_dir"])
    txt_file = run_dir / "CSUITE_FINAL_RESUME.txt"
    docx_file = run_dir / "outputs" / "csuite_resume.docx"
    assert txt_file.is_file() and txt_file.stat().st_size > 1500
    assert docx_file.is_file() and docx_file.stat().st_size > 2000

    rendered_txt = txt_file.read_text(encoding="utf-8")
    assert company in rendered_txt
    assert role.upper() in rendered_txt or role in rendered_txt
    validation = validate_csuite_five_section_text(rendered_txt)
    assert validation["status"] == "PASS"
    assert validation["failed_checks"] == []
    assert validation["checks"]["six_sentence_calibrated_thesis"] is True
    assert not re.search(r"\b(?:2002|2010|2023|2024|2025)\b", rendered_txt.split(f"5. {DATELESS_CREDENTIALS_FOOTER_HEADING}")[-1])


def test_wave6_exec_summary_synthesis_calibration_and_anti_past_title_gate() -> None:
    """Verify IDE/C-suite executive summary synthesis matches the 6-sentence calibration contract and rejects past-title lists."""
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

    base = _load_base_resume()
    rendered = flatten_csuite_five_section_resume_to_text(
        base,
        target_company="Citi",
        target_role="Head of AI Strategy - Firmwide AI",
    )
    sec1_start = rendered.index(f"1. {EXECUTIVE_INVESTMENT_THESIS_HEADING}")
    sec2_start = rendered.index(f"2. {EXECUTIVE_AGENTIC_CAPABILITIES_HEADING}")
    sec1_lines = [
        ln.strip()
        for ln in rendered[sec1_start:sec2_start].splitlines()[1:]
        if ln.strip() and not ln.strip().startswith(("[", "|", "-", "+"))
    ]
    thesis = " ".join(sec1_lines)
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

    bb_rendered = flatten_csuite_five_section_resume_to_text(
        base,
        target_company="Brown & Brown",
        target_role="SVP IT Strategy & Innovation",
    )
    assert "github.com/Siamese001/agents" in bb_rendered.splitlines()[1]
    assert "Boca Raton, FL" not in bb_rendered.splitlines()[1]
    assert "Insurance Domain, Actuarial Risk & Carrier Operations" in bb_rendered
    assert "Solvency II and AG43" in bb_rendered

    aig_rendered = flatten_csuite_five_section_resume_to_text(
        base,
        target_company="AIG",
        target_role="VP Global Head Agentic AI",
    )
    assert "Insurance Underwriting, Claims & Actuarial Risk (FSA)" in aig_rendered
