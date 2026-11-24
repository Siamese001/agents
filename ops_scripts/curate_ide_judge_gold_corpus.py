#!/usr/bin/env python3
"""Curate frozen 48-item stratified gold candidate corpora (24 Resume + 24 Outreach) and DIE Studio blind pools.

Enforces:
- 24 Resume items (4 x 6 judge families; 8 clean_pass, 8 borderline, 8 subtle_defect)
- 24 Outreach items (12 x1d_quorum + 12 executive_judge_panel; 8 clean_pass, 8 borderline, 8 subtle_defect)
- `validate_query_input_quality`: Every query is a self-contained natural-language evaluation question (`is_clear_reactable_prompt == True`)
- `validate_nuanced_answer_calibration_difficulty`: Zero obvious caricature tells, >= 2 verified source anchors woven into every answer, explicit nuance profile
- 5-layer deduplication (`max_prompt_jaccard < 0.40`, `max_body_jaccard < 0.35`, unique `topic_family`)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge.gold_corpus import (
    GoldCandidateRecord,
    build_studio_blind_pool_dict,
    validate_stratification,
    write_gold_candidates_jsonl,
)


def build_resume_gold_candidates() -> list[GoldCandidateRecord]:
    """Return 24 stratified, nuanced Resume items (4 x 6 judge families; 8 clean_pass, 8 borderline, 8 subtle_defect)."""
    f_slalom_util = (
        "Slalom Senior Director (Jun 2026-Present): Led $3.5M utility modernization charter delivering SCADA grid-restoration intelligence with zero red escalations and a target 20% call-center deflection."
    )
    f_slalom_part = (
        "Slalom Partnerships (Jun 2026-Present): Directed $2.4M Anthropic Claude enablement workstream, launched 45-day Claude Code engineering pods, and scaled Gemini Enterprise adoption from 750 to 5,750+ seats."
    )
    f_slalom_maximo = (
        "Slalom Visual Asset SOW (Jun 2026-Present): Delivered six-figure multimodal inspection pipeline on power generation nameplates with 90% primary-field accuracy, 92% OCR accuracy, and 100% full-plate auto-acceptance into IBM Maximo."
    )
    f_unify_rev = (
        "Unify Consulting SVP Engineering, Agentic AI Platforms (Feb 2023-Jun 2026): Generated $22M in IP-led advisory and platform revenue by converting bespoke consulting projects into reusable platform services."
    )
    f_unify_acv = (
        "Unify Consulting Commercial Licensing (Feb 2023-Jun 2026): Unlocked $5M in annual contract value via CFO-aligned enterprise workflow adoption and consumption-based licensing."
    )
    f_unify_cycle = (
        "Unify Consulting Runtime Governance (Feb 2023-Jun 2026): Compressed lab-to-production deployment cycles from six months to three weeks using deterministic auditability and replayable runtime governance."
    )
    f_unify_reg = (
        "Unify Consulting Banking Controls (Feb 2023-Jun 2026): Reduced regulatory findings by 35% across banking rollouts via data usage controls, compliance checkpoints, and model-explainability standards."
    )
    f_ibm_aws = (
        "IBM Partner (Apr 2017-Oct 2022): Led AWS alliance co-sell motions across regulated financial services institutions delivering 20% joint revenue growth."
    )
    f_ibm_ml = (
        "IBM Partner Financial Engineering (Apr 2017-Oct 2022): Architected enterprise NLP and ML decision-support pipelines with governed data lineage and DevSecOps controls across banking and insurance clients."
    )

    all_facts = (
        f_slalom_util,
        f_slalom_part,
        f_slalom_maximo,
        f_unify_rev,
        f_unify_acv,
        f_unify_cycle,
        f_unify_reg,
        f_ibm_aws,
        f_ibm_ml,
    )

    return [
        # --- 1. HEADLINE (4 items: 2 clean_pass, 1 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_001",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_headline_hyperscaler_alliance_positioning",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate this Resume Headline for Anthropic (Head of Builder Partnerships, requiring Claude, Gemini, and AWS alliance adoption) on factual grounding and executive positioning?"
            ),
            candidate_text=(
                "SVP AI Partnerships & Cloud Alliances | Anthropic Claude, Gemini Enterprise & AWS Co-Sell Execution | Regulated Financial Systems"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws),
            source_provenance="full_resume_799cfd12ad34:headline_partner",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_002",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_headline_banking_governance_control_planes",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Assess this Resume Headline for Citigroup (SVP Enterprise AI Platforms, requiring Unify runtime governance and banking compliance controls) on mandate relevance and credibility?"
            ),
            candidate_text=(
                "SVP Engineering, Agentic AI Platforms | Regulated Banking Compliance & Explainability Controls | Reusable Enterprise Runtime Governance"
            ),
            allowed_facts=(f_unify_rev, f_unify_reg, f_unify_cycle),
            source_provenance="full_resume_799cfd12ad34:headline_svp_variant",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_003",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_headline_consulting_advisory_dilution",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            target_context=(
                "Evaluate this Resume Headline for Truist (Head of Forward Deployed Engineering, requiring technical platform differentiation over broad utility consulting) on mandate fit and clarity?"
            ),
            candidate_text=(
                "Senior Consulting & Technology Executive | Enterprise Banking & Utility Modernization | Cloud Partner Delivery & Governance Programs"
            ),
            allowed_facts=(f_slalom_util, f_unify_rev, f_ibm_aws),
            source_provenance="curated_borderline:headline_broad_consulting_framing",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_004",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_headline_pnl_scope_conflation",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess this Resume Headline for Invesco (SVP Regulated Banking Platforms, requiring disciplined Unify $22M IP revenue and $5M ACV scope attribution) on factual truth and authority?"
            ),
            candidate_text=(
                "SVP Regulated Banking AI Platforms | $27M Commercial Bank Balance-Sheet P&L Owner | Tier-1 Core Deposit & Credit Risk Engine Architect"
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_reg),
            subtle_defect_type="conflated_consulting_ip_revenue_with_bank_balance_sheet_pnl",
            source_provenance="curated_subtle_defect:headline_pnl_extrapolation",
        ),
        # --- 2. EXECUTIVE SUMMARY (4 items: 2 clean_pass, 1 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_005",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_summary_hyperscaler_cosell_conversion",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate this Executive Summary for Neo4j (VP Global Cloud Alliances, requiring Slalom hyperscaler enablement and IBM AWS co-sell growth) on attribution and voice?"
            ),
            candidate_text=(
                "Technology partnerships and platform executive who converts cloud and frontier model alliances into governed production adoption. "
                "At Slalom, directed a $2.4M Anthropic Claude enablement workstream with 45-day Claude Code pods while scaling Gemini Enterprise from "
                "750 to 5,750+ seats. Earlier as an IBM Partner, led AWS financial-services co-sell motions that delivered 20% joint revenue growth "
                "alongside governed NLP and DevSecOps pipelines for banking and insurance institutions."
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws, f_ibm_ml),
            source_provenance="full_resume_799cfd12ad34:executive_summary",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_006",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_summary_unify_slalom_platform_economics",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Assess this Executive Summary for Brown & Brown (SVP Enterprise AI Strategy, requiring Unify reusable platform licensing and Slalom SCADA delivery) on scope grounding?"
            ),
            candidate_text=(
                "Engineering leader specializing in policy-bound agentic AI platforms that clear enterprise model-risk review and drive recurring commercial value. "
                "As SVP Engineering at Unify Consulting, turned bespoke advisory engagements into reusable platform services generating $22M in IP-led revenue and "
                "$5M in annual contract value via CFO-aligned consumption licensing, while cutting banking regulatory findings by 35%. Currently leads a $3.5M utility "
                "modernization charter at Slalom delivering SCADA restoration intelligence with zero red escalations."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_reg, f_slalom_util),
            source_provenance="curated_clean:executive_summary_unify_slalom",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_007",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_summary_passive_attribution_underweight",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            target_context=(
                "Evaluate this Executive Summary for Truist (SVP AI Engineering, requiring Unify cycle-time compression and Slalom Claude enablement) on factual accuracy and executive cadence?"
            ),
            candidate_text=(
                "Experienced engineering executive with a background supporting enterprise AI modernization across consulting and financial services organizations. "
                "Participated in cross-functional programs at Unify Consulting that shortened lab-to-production deployment cycles from six months to three weeks "
                "and helped reduce banking regulatory findings by 35% through standardized explainability checkpoints. Currently supports Slalom's $2.4M Anthropic "
                "Claude enablement initiative and multi-team cloud readiness across enterprise accounts."
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_slalom_part),
            source_provenance="curated_borderline:executive_summary_diluted_authority",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_008",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_summary_additive_metric_synthesis_error",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess this Executive Summary for Citigroup (Managing Director of Banking AI, requiring verified Unify revenue, Slalom utility, and Gemini Enterprise metrics) on employer attribution?"
            ),
            candidate_text=(
                "Platform engineering executive who built a $30.5M annual recurring software subscription business inside a single regulated banking division by "
                "merging Unify Consulting's $22M IP-led revenue, $5M ACV, and Slalom's $3.5M utility charter into one commercial bank product line. Expanded "
                "dedicated banking Gemini Enterprise deployments from 750 to 5,750+ licensed wealth-management advisors while eliminating 35% of OCC consent orders."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_reg, f_slalom_util, f_slalom_part),
            subtle_defect_type="cross_firm_revenue_summation_and_occ_consent_order_extrapolation",
            source_provenance="curated_subtle_defect:executive_summary_composite_fabrication",
        ),
        # --- 3. COMPETENCIES (4 items: 1 clean_pass, 2 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_009",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_competencies_governed_platform_pillars",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate these Core Competencies for Brown & Brown (SVP Technology Innovation, requiring Unify agentic governance, AWS alliances, and Maximo telemetry) on clarity and proportion?"
            ),
            candidate_text=(
                "- Agentic Platform Architecture: Policy-bound multi-agent orchestration, deterministic runtime auditability, and reusable platform service design ($22M IP-led delivery).\n"
                "- Regulated AI Governance: Model-risk compliance checkpoints, explainability standards (35% fewer banking regulatory findings), and governed data lineage.\n"
                "- Hyperscaler & Frontier Alliances: AWS financial-services co-sell execution (20% joint growth), Anthropic Claude enablement pods, and Gemini Enterprise scaling.\n"
                "- Operational Telemetry & Velocity: Six-month to three-week release compression, SCADA restoration intelligence, and multimodal asset inspection into IBM Maximo."
            ),
            allowed_facts=all_facts,
            source_provenance="full_resume_799cfd12ad34:competencies",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_010",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_competencies_broad_functional_abstraction",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            target_context=(
                "Assess these Core Competencies for Neo4j (VP Platform Alliances, requiring Unify consumption licensing, IBM DevSecOps lineage, and Claude enablement) on grounding and relevance?"
            ),
            candidate_text=(
                "- Enterprise AI Delivery: Multi-agent workflow architecture, lab-to-production lifecycle standardization, and consumption-based platform licensing models.\n"
                "- Risk & Compliance Controls: Banking model-risk readiness, runtime explainability checkpoints, data usage guardrails, and DevSecOps pipeline lineage.\n"
                "- Cloud Partner Ecosystems: Joint hyperscaler solution blueprints, field engineering enablement across Anthropic Claude and Gemini Enterprise, and AWS alliance co-sell."
            ),
            allowed_facts=(f_unify_acv, f_unify_cycle, f_unify_reg, f_slalom_part, f_ibm_aws, f_ibm_ml),
            source_provenance="curated_borderline:competencies_unquantified_but_grounded",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_011",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="rg_competencies_internal_jargon_leakage",
            nuance_profile="DENSE_INSIDER_SHORTHAND_OR_CADENCE",
            target_context=(
                "Evaluate these Core Competencies for Invesco (Chief AI Advisor, requiring C-suite clarity across Slalom, Maximo, and Unify programs) on cold-reader comprehension and executive proportion?"
            ),
            candidate_text=(
                "- Pod & Charter Mechanics: 45-day Claude Code pod cadence management, SCADA feeder telemetry triage, and nameplate OCR auto-acceptance tuning for IBM Maximo.\n"
                "- Internal Lifecycle Gates: Replayable checkpoint instrumentation across six-month to three-week build pipelines and consumption SOW packaging ($5M ACV).\n"
                "- Alliance Seat Administration: Internal seat provisioning from 750 to 5,750+ Gemini Enterprise accounts and $2.4M enablement workstream tracking."
            ),
            allowed_facts=(f_slalom_util, f_slalom_part, f_slalom_maximo, f_unify_acv, f_unify_cycle),
            source_provenance="curated_borderline:competencies_operational_microlabels",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_012",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_competencies_adjacent_domain_fabrication",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess these Core Competencies for Citigroup (SVP Enterprise AI Governance, requiring verified Unify explainability controls and IBM AWS alliance proof) on factual faithfulness?"
            ),
            candidate_text=(
                "- Regulated Banking Risk Engines: Basel III intraday liquidity stress engines, Federal Reserve CCAR capital adequacy submissions, and SWIFT ISO 20022 wire settlement.\n"
                "- Governed AI Runtime Platforms: Deterministic auditability (six months to three weeks release compression), explainability controls (35% fewer findings), and DevSecOps lineage.\n"
                "- Commercial Platform Scaling: $22M IP-led reusable service architecture, $5M ACV consumption licensing, and 20% AWS financial-services joint revenue growth."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_cycle, f_unify_reg, f_ibm_aws, f_ibm_ml),
            subtle_defect_type="ungrounded_basel_ccar_and_swift_settlement_competencies",
            source_provenance="curated_subtle_defect:competencies_ungrounded_banking_core",
        ),
        # --- 4. EMPLOYMENT BULLETS (4 items: 1 clean_pass, 1 borderline, 2 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_013",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_bullets_unify_consulting_verified_impact",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate these Unify Consulting Bullets for Truist (Head of Forward Deployed Engineering, requiring reusable agentic platforms and banking compliance) on mechanism-to-outcome density?"
            ),
            candidate_text=(
                "- Generated $22M in IP-led revenue across enterprise lines of business by converting bespoke consulting delivery into reusable agentic AI platform services.\n"
                "- Unlocked $5M in annual contract value through CFO-aligned workflow adoption, structuring consumption-based licensing models tied to production usage.\n"
                "- Compressed lab-to-production deployment cycles from six months to three weeks by enforcing deterministic auditability and replayable runtime governance.\n"
                "- Reduced regulatory findings by 35% across banking AI rollouts by instituting data usage controls, compliance checkpoints, and model-explainability standards."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_cycle, f_unify_reg),
            source_provenance="full_resume_799cfd12ad34:unify_bullets",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_014",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_bullets_slalom_mixed_specificity",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            target_context=(
                "Assess these Slalom Bullets for Brown & Brown (SVP IT Strategy, requiring balanced SCADA modernization, Maximo inspection, and Claude enablement proof) on grounding and proportion?"
            ),
            candidate_text=(
                "- Directing a $3.5M utility modernization charter focused on SCADA grid-restoration intelligence, maintaining zero red escalations toward a 20% call-center deflection target.\n"
                "- Delivered a six-figure multimodal visual inspection pipeline on power generation equipment nameplates that reached 90% primary-field accuracy, 92% OCR accuracy, and 100% full-plate auto-acceptance into IBM Maximo.\n"
                "- Leading a $2.4M Anthropic Claude enablement workstream using 45-day Claude Code pods while supporting Gemini Enterprise growth from 750 to 5,750+ seats."
            ),
            allowed_facts=(f_slalom_util, f_slalom_part, f_slalom_maximo),
            source_provenance="curated_borderline:slalom_bullets_heavy_ocr_detail",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_015",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_bullets_anthropic_ibm_bcbs239_and_10m_duplicate",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Evaluate these five IBM Partner Bullets for Anthropic (Head of Builder Partnerships, requiring distinct AWS co-sell and banking modernization metrics) on differentiation and clarity?"
            ),
            candidate_text=(
                "IBM | Partner (Apr 2017 to Oct 2022) | Target JD: Anthropic Head of Builder Partnerships\n"
                "- Directed AWS Partner offering and accelerator management by packaging streaming analytics ecosystems into BCBS 239 solution blueprints that held 99.9% production uptime across banking portfolios.\n"
                "- Led global pre-sales solution engineering, executive workshops, and commercial validation pilots to convert buyer requirements into C-suite AWS architecture alignments driving $10M in net-new revenue.\n"
                "- Owned quota-aligned technical sales execution across priority accounts using BI forecasting and CRM pipeline governance that generated $10M in new annual recurring revenue via Salesforce deal analytics.\n"
                "- Architected enterprise cloud-native modernization waves by shifting legacy on-prem financial workloads into containerized microservices via BCBS 239 reference architectures sustaining 99.9% production uptime.\n"
                "- Drove IBM-AWS alliance co-sell motions, SI and ISV joint go-to-market programs, and partner territory planning across field teams to deliver 20% joint revenue growth."
            ),
            allowed_facts=(f_ibm_aws, f_ibm_ml),
            subtle_defect_type="intra_section_bcbs239_99_9pct_and_10m_duplicate_across_ibm_bullets",
            source_provenance="full_resume_e1d1e7775bb0:ibm_bullets_bcbs239_10m_repeat",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_016",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_bullets_target_converted_to_realized_outcome",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess these Slalom Bullets for Invesco (VP Enterprise Operations AI, requiring exact metric accuracy across SCADA deflection and Maximo OCR) on factual faithfulness?"
            ),
            candidate_text=(
                "- Completed a $3.5M utility modernization charter at Slalom that achieved a verified 28% permanent reduction in utility call-center volume and zero red escalations across SCADA grid restoration.\n"
                "- Achieved 100% primary-field and OCR extraction accuracy across all power generation nameplates ingested into IBM Maximo under a six-figure visual intelligence SOW.\n"
                "- Scaled Gemini Enterprise from 750 to 5,750+ active engineering seats across the $2.4M Anthropic Claude and Google Cloud practice."
            ),
            allowed_facts=(f_slalom_util, f_slalom_part, f_slalom_maximo),
            subtle_defect_type="target_deflection_claimed_as_realized_28pct_and_100pct_ocr_inflation",
            source_provenance="curated_subtle_defect:slalom_target_vs_realized_distortion",
        ),
        # --- 5. ROLE NARRATIVE (4 items: 1 clean_pass, 2 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_017",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_narrative_unify_platform_commercialization",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate this Unify Consulting Role Narrative for Neo4j (SVP Platform Engineering, requiring $22M IP commercialization and runtime governance) on mandate fit and concision?"
            ),
            candidate_text=(
                "Recruited as SVP Engineering to transition Unify Consulting from one-off advisory delivery into a reusable agentic AI platform business ($22M IP-led revenue, "
                "$5M ACV via consumption licensing). Standardized replayable runtime governance and model-explainability checkpoints that compressed client deployment timelines "
                "from six months to three weeks while cutting regulatory findings by 35% across banking rollouts."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_cycle, f_unify_reg),
            source_provenance="full_resume_799cfd12ad34:unify_narrative",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_018",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_narrative_slalom_dual_mandate_compression",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            target_context=(
                "Assess this Slalom Role Narrative for Brown & Brown (SVP Digital Transformation, bridging $3.5M utility SCADA delivery and $2.4M Claude enablement) on coherence and accuracy?"
            ),
            candidate_text=(
                "Serves as Senior Director across two parallel Slalom practices: leading a $3.5M utility modernization charter for SCADA grid-restoration intelligence "
                "(zero red escalations, target 20% call-center deflection) plus multimodal equipment inspection into IBM Maximo, while simultaneously directing the $2.4M "
                "Anthropic Claude enablement workstream and Gemini Enterprise expansion from 750 to 5,750+ seats."
            ),
            allowed_facts=(f_slalom_util, f_slalom_part, f_slalom_maximo),
            source_provenance="full_resume_799cfd12ad34:slalom_narrative_dual_focus",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_019",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="rg_narrative_ibm_generic_devsecops_bi_omits_aws_partner",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            target_context=(
                "Evaluate this IBM Partner Role Narrative for Anthropic (Applied AI & Builder Partnerships, requiring hyperscaler AWS alliance co-sell leadership) on target mandate relevance?"
            ),
            candidate_text=(
                "IBM | Partner (Apr 2017 to Oct 2022) | Target JD: Anthropic Applied AI & Builder Partnerships\n"
                "Managed internal engineering delivery for banking and insurance accounts by standardizing DevSecOps release pipelines, governed data lineage checkpoints, "
                "and executive BI reporting views across multi-team modernization projects, while coordinating quarterly release schedules and risk documentation for "
                "on-prem NLP decision-support models."
            ),
            allowed_facts=(f_ibm_aws, f_ibm_ml),
            source_provenance="curated_borderline:ibm_generic_devsecops_bi_omits_aws_partner",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_020",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_narrative_unify_headcount_and_ip_ownership_stretch",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess this Unify Consulting Role Narrative for Invesco (Chief AI Architect, requiring verified $22M IP platform scope and banking release velocity) on source evidence grounding?"
            ),
            candidate_text=(
                "Led a 180-engineer commercial software division at Unify Consulting (Feb 2023-Jun 2026), filing four foundational patents on deterministic agentic replay "
                "while generating $22M in IP-led platform revenue and $5M in CFO-aligned annual contract value. Compressed regulated banking releases from six months to three "
                "weeks and reduced regulatory audit findings by 35% across North American commercial banks."
            ),
            allowed_facts=(f_unify_rev, f_unify_acv, f_unify_cycle, f_unify_reg),
            subtle_defect_type="ungrounded_180_engineer_headcount_and_four_patents_claim",
            source_provenance="curated_subtle_defect:unify_narrative_headcount_patent_stretch",
        ),
        # --- 6. WHOLE-RESUME COHERENCE (4 items: 1 clean_pass, 1 borderline, 2 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_021",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="rg_coherence_chronological_progression_verified",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            target_context=(
                "Evaluate this Whole-Resume Excerpt for Citigroup (SVP AI Platforms & Cloud Alliances, spanning Slalom, Unify, and IBM) on chronological consistency and distinct attribution?"
            ),
            candidate_text=(
                "HEADLINE: SVP AI Platforms & Cloud Alliances | Regulated Banking Governance & Reusable Agentic Architecture\n"
                "CAREER PROGRESSION:\n"
                "1. Slalom (Senior Director, Jun 2026-Present): $3.5M utility SCADA modernization charter (zero red escalations, target 20% call-center deflection), "
                "IBM Maximo nameplate inspection (92% OCR accuracy), and $2.4M Anthropic Claude / Gemini Enterprise (750 to 5,750+ seats) enablement.\n"
                "2. Unify Consulting (SVP Engineering, Feb 2023-Jun 2026): $22M IP-led platform revenue, $5M ACV consumption licensing, 6-month to 3-week deployment "
                "compression, and 35% reduction in banking regulatory findings.\n"
                "3. IBM (Partner, Apr 2017-Oct 2022): AWS financial-services alliance co-sell (20% joint revenue growth) and governed banking/insurance NLP DevSecOps pipelines."
            ),
            allowed_facts=all_facts,
            source_provenance="full_resume_799cfd12ad34:whole_resume_arc",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_022",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="rg_coherence_title_calibration_tension",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            target_context=(
                "Assess this Whole-Resume Excerpt for Neo4j (VP Enterprise AI Alliances, bridging IBM Partner, Unify SVP Engineering, and Slalom Senior Director) on tenure coherence?"
            ),
            candidate_text=(
                "HEADLINE: Enterprise AI Platform & Alliances Executive | Banking Governance & Utility Modernization\n"
                "NARRATIVE THREAD: Moves from Partner-level financial-services cloud alliances at IBM (Apr 2017-Oct 2022; 20% AWS joint revenue growth) to building an "
                "IP-led agentic platform practice as SVP Engineering at Unify Consulting (Feb 2023-Jun 2026; $22M IP revenue, $5M ACV, 35% fewer banking regulatory findings), "
                "before joining national consultancy Slalom as Senior Director (Jun 2026-Present) to lead a $3.5M utility charter and $2.4M Anthropic Claude workstream."
            ),
            allowed_facts=all_facts,
            source_provenance="curated_borderline:whole_resume_svp_to_sr_director_bridge",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_023",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_coherence_summary_s3_vs_ibm_b5_echo_and_double_counting",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Evaluate this Whole-Resume Excerpt for Anthropic (Head of Strategic Cloud Partnerships, reviewing Summary S3 alongside Slalom, Unify, and IBM timelines) on cross-section differentiation?"
            ),
            candidate_text=(
                "TARGET JDS: Citi Head of AI Governance | Neo4j VP Global Strategic Alliances | Brown & Brown SVP IT Strategy | Invesco Chief AI Advisor\n"
                "EXECUTIVE SUMMARY (S3): Earlier as an IBM Partner, drove AWS financial-services alliance co-sell motions and joint go-to-market programs to deliver 20% joint revenue growth across regulated banking accounts.\n"
                "EXPERIENCE TIMELINE:\n"
                "- Slalom (SVP Engineering, Jan 2024-Present): Credited with $22M in IP-led agentic platform revenue, $3.5M utility SCADA modernization, and 750 to 5,750+ Gemini Enterprise seat growth.\n"
                "- Unify Consulting (SVP Engineering, Mar 2021-Dec 2024): Also credited with the same $22M IP-led platform revenue, $5M ACV consumption licensing, and 35% banking regulatory reduction.\n"
                "- IBM (Partner, Apr 2017-Oct 2022) Bullet B5: Drove AWS financial-services alliance co-sell motions and joint go-to-market programs to deliver 20% joint revenue growth across regulated banking accounts."
            ),
            allowed_facts=all_facts,
            subtle_defect_type="summary_s3_vs_ibm_b5_verbatim_echo_and_22m_double_counting",
            source_provenance="full_resume_e1d1e7775bb0:whole_resume_s3_b5_echo_and_collision",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_024",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="rg_coherence_target_bank_mandate_assimilation",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            target_context=(
                "Assess this Whole-Resume Excerpt for Truist (Head of Forward Deployed Engineering for Care Center AI, requiring Unify and Slalom proof) on employer attribution faithfulness?"
            ),
            candidate_text=(
                "HEADLINE: Head of Forward Deployed Engineering | Banking Care Center AI & Explainable Models\n"
                "SUMMARY & EXPERIENCE COHERENCE: Cites Unify Consulting's $22M IP-led revenue, six-month to three-week release compression, and 35% reduction in regulatory "
                "findings as work executed directly for Truist's Care Center division with explainable boosting models, while attributing Slalom's 20% deflection target for "
                "utility call centers to retail banking operations."
            ),
            allowed_facts=all_facts,
            subtle_defect_type="retroactive_assimilation_of_target_bank_care_center_into_history",
            source_provenance="curated_subtle_defect:whole_resume_target_mandate_assimilation",
        ),
    ]


def build_outreach_gold_candidates() -> list[GoldCandidateRecord]:
    """Return 24 stratified, nuanced Outreach items (12 x1d_quorum + 12 executive_judge_panel; 8 clean, 8 borderline, 8 subtle_defect)."""
    f_unify_cycle = (
        "fact_unify_cycle: Compressed lab-to-production AI deployment from six months to three weeks with deterministic auditability at Unify Consulting (Feb 2023-Jun 2026)."
    )
    f_unify_reg = (
        "fact_unify_reg: Reduced regulatory findings by 35% across banking AI rollouts via compliance checkpoints and model-explainability controls at Unify Consulting."
    )
    f_unify_rev = (
        "fact_unify_rev: Generated $22M in IP-led revenue and $5M annual contract value (ACV) via CFO-aligned consumption licensing converting bespoke consulting into reusable agentic platform services."
    )
    f_slalom_util = (
        "fact_slalom_util: Led $3.5M utility agentic AI modernization charter at Slalom (Jun 2026-Present) delivering SCADA restoration intelligence with zero red escalations and target 20% call-center deflection."
    )
    f_slalom_part = (
        "fact_slalom_part: Directed $2.4M Anthropic Claude enablement workstream with 45-day Claude Code pods and scaled Gemini Enterprise from 750 to 5,750+ seats at Slalom."
    )
    f_slalom_maximo = (
        "fact_slalom_maximo: Delivered six-figure multimodal equipment nameplate inspection pipeline at Slalom achieving 90% primary-field accuracy, 92% OCR accuracy, and 100% full-plate auto-acceptance into IBM Maximo."
    )
    f_ibm_aws = (
        "fact_ibm_aws: Led AWS alliance co-sell motions across regulated financial services as an IBM Partner (Apr 2017-Oct 2022), delivering 20% joint revenue growth and governed banking NLP/ML pipelines."
    )

    f_all = (
        f_unify_cycle,
        f_unify_reg,
        f_unify_rev,
        f_slalom_util,
        f_slalom_part,
        f_slalom_maximo,
        f_ibm_aws,
    )

    return [
        # --- x1d_quorum (12 items: 4 clean_pass, 4 borderline, 4 subtle_defect) ---
        GoldCandidateRecord(
            item_id="lic_gold_001",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_x1d_caio_governance_velocity_two_touch",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Does this two-touch Chief AI Officer email sequence balance peer executive authority, verified Unify banking governance proof, and a low-friction ask?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Governed AI deployment velocity in regulated banking)\n"
                "Pascal, moving agentic workflows from pilot into production without triggering model-risk bottlenecks is a tension we solved directly in banking rollouts. "
                "At Unify Consulting, embedding runtime compliance checkpoints and explainability controls cut regulatory findings by 35% while compressing lab-to-production "
                "cycles from six months to three weeks. Would a brief peer exchange on runtime governance checkpoints next week be useful?\n\n"
                "Touch 2 (Subject: Re: Governed AI deployment velocity in regulated banking)\n"
                "Adding one commercial detail from that architecture: packaging those governance gates into reusable platform services generated $22M in IP-led adoption "
                "and $5M in annual contract value without per-team rebuilds. Happy to share a two-page control-plane blueprint ahead of your quarterly platform review?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="curated_clean:x1d_caio_2touch_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_002",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_x1d_recruiter_svp_mandate_inmail",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="linkedin_inmail",
            recipient_class="recruiter",
            target_context=(
                "How effectively does this two-touch recruiter InMail map the candidate's Unify Consulting and Slalom metrics to an SVP Banking AI Platforms search?"
            ),
            candidate_text=(
                "Touch 1 (Subject: SVP AI Platforms mandate / Regulated Banking Governance)\n"
                "Hi Dana, reaching out regarding your search for an SVP to lead forward-deployed AI platforms in regulated financial services. As SVP Engineering at Unify "
                "Consulting, I built reusable agentic control planes ($22M IP-led revenue, $5M ACV) that compressed release cycles from six months to three weeks with 35% "
                "fewer banking regulatory findings. Worth a 10-minute alignment check this week?\n\n"
                "Touch 2 (Subject: Re: SVP AI Platforms mandate / Regulated Banking Governance)\n"
                "Quick context update: I currently lead a $3.5M utility modernization charter at Slalom with zero red escalations alongside a $2.4M Anthropic Claude "
                "enablement workstream. Happy to send a concise capability brief tailored to the hiring committee's criteria?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev, f_slalom_util, f_slalom_part),
            source_provenance="curated_clean:x1d_recruiter_2touch_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_003",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_x1d_vp_alliances_cosell_progression",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="email",
            recipient_class="vp_executive",
            target_context=(
                "Evaluate whether this two-touch VP of Cloud Alliances outreach connects Anthropic Claude, Gemini Enterprise, and IBM AWS co-sell proofs with distinct Touch 2 value?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Converting hyperscaler AI alliances into field production)\n"
                "Hi Marcus, partner co-sell motions often stall between executive demos and governed production rollout. At Slalom, I directed a $2.4M Anthropic Claude "
                "enablement workstream with 45-day Claude Code pods and scaled Gemini Enterprise from 750 to 5,750+ seats, building on earlier IBM AWS co-sell programs "
                "that delivered 20% joint revenue growth in financial services. Open to comparing field enablement blueprints next Thursday?\n\n"
                "Touch 2 (Subject: Re: Converting hyperscaler AI alliances into field production)\n"
                "One commercial lever that accelerated those partner rollouts: pairing reusable reference architectures with CFO-aligned consumption licensing unlocked "
                "$5M in annual contract value across enterprise accounts. Would a 15-minute exchange with your alliance architecture lead make sense?"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws, f_unify_rev),
            source_provenance="curated_clean:x1d_vp_alliances_2touch_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_004",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_x1d_coo_operational_reliability_inmail",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="linkedin_inmail",
            recipient_class="c_suite_executive",
            target_context=(
                "Does this two-touch operations executive InMail ground its reliability and auditability claims in verified Slalom SCADA/Maximo and Unify compliance evidence?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Audit-grade reliability for frontline agentic workflows)\n"
                "Hi Elena, scaling AI into regulated operations requires deterministic gates before field teams trust automated recommendations. Across our $3.5M utility "
                "SCADA charter (zero red escalations) and Unify banking rollouts (35% fewer regulatory findings), replayable runtime checkpoints resolved risk early. "
                "Open to a brief peer exchange on frontline governance?\n\n"
                "Touch 2 (Subject: Re: Audit-grade reliability for frontline agentic workflows)\n"
                "Sharing one concrete benchmark from our multimodal inspection pipeline: enforcing structured verification gates drove 92% OCR accuracy and 100% "
                "full-plate auto-acceptance into IBM Maximo. Can I send over a one-page reliability architecture summary?"
            ),
            allowed_facts=(f_slalom_util, f_unify_reg, f_slalom_maximo),
            source_provenance="curated_clean:x1d_csuite_2touch_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_005",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="lic_x1d_touch2_low_incremental_evidence",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Assess whether this two-touch email remains factually grounded in Unify Consulting banking governance despite a light Touch 2 follow-up?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Enterprise AI governance and release velocity)\n"
                "Hi Pascal, I have been following your banking technology modernization work. At Unify Consulting, our engineering team compressed lab-to-production AI "
                "deployment from six months to three weeks while reducing regulatory findings by 35% through runtime explainability controls. Would you be open to a brief "
                "introductory conversation next week?\n\n"
                "Touch 2 (Subject: Re: Enterprise AI governance and release velocity)\n"
                "Following up briefly on my note above in case it was buried during quarter-end reviews. Those reusable platform patterns also supported $22M in IP-led "
                "enterprise delivery, and I would welcome a quick 10-minute exchange if helpful?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="curated_borderline:x1d_generic_followup_low_hook",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_006",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="lic_x1d_unpersonalized_placeholder_salutation",
            nuance_profile="DENSE_INSIDER_SHORTHAND_OR_CADENCE",
            channel="linkedin_inmail",
            recipient_class="c_suite_executive",
            target_context=(
                "Does this two-touch InMail fail executive outreach standards due to generic salutation framing and awkward company-descriptor insertion despite accurate Unify metrics?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Regulated Commercial Bank / Forward Deployed AI Platform Alignment)\n"
                "Hi Banking Technology Leader, I have been following your institution's focus on top-10 U.S. commercial banking operations. In my recent Unify Consulting "
                "role, we compressed AI deployment from six months to three weeks with 35% fewer regulatory findings and $22M in IP-led platform revenue. Would you be open "
                "to a brief conversation next week?\n\n"
                "Touch 2 (Subject: Re: Regulated Commercial Bank / Forward Deployed AI Platform Alignment)\n"
                "Hi Banking Technology Leader, circling back on our governed agentic workflow results ($5M ACV via consumption licensing). Open to a 10-minute introductory call?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="truist_current_run:awkward_template_insertion",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_007",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="lic_x1d_recruiter_dense_metric_stack",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="email",
            recipient_class="recruiter",
            target_context=(
                "Evaluate whether this recruiter two-touch email remains credible and passable even though Touch 1 packs four separate financial metrics into a single paragraph?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Executive background for SVP AI Platforms search)\n"
                "Hi Jordan, reaching out regarding your executive search in enterprise AI platforms. My track record spans $22M in IP-led platform revenue and $5M ACV at "
                "Unify Consulting, a $3.5M utility modernization charter and $2.4M Anthropic Claude workstream at Slalom, plus 20% AWS joint revenue growth as an IBM Partner. "
                "Are you leading candidate intake for this mandate?\n\n"
                "Touch 2 (Subject: Re: Executive background for SVP AI Platforms search)\n"
                "Hi Jordan, adding one governance proof point relevant to financial-services searches: our runtime explainability checkpoints at Unify reduced banking "
                "regulatory findings by 35% while cutting release cycles from six months to three weeks. Open to a brief fit discussion?"
            ),
            allowed_facts=f_all,
            source_provenance="curated_borderline:x1d_recruiter_metric_heavy",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_008",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="lic_x1d_redundant_touch2_no_new_angle",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="email",
            recipient_class="vp_executive",
            target_context=(
                "Does this two-touch VP email fail sequence progression criteria because Touch 2 repeats the exact same Claude and Gemini seat metrics without adding a new angle?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Cloud AI partner enablement architecture)\n"
                "Hi Marcus, at Slalom I directed a $2.4M Anthropic Claude enablement workstream with 45-day Claude Code pods and scaled Gemini Enterprise from 750 to 5,750+ "
                "seats across enterprise engineering teams. I would like to schedule a 30-minute call this week to walk through my full partner curriculum.\n\n"
                "Touch 2 (Subject: Re: Cloud AI partner enablement architecture)\n"
                "Hi Marcus, reiterating my prior note regarding our $2.4M Anthropic Claude enablement workstream, 45-day Claude Code pods, and scaling Gemini Enterprise "
                "from 750 to 5,750+ seats. Please let me know when you have 30 minutes on your calendar to review?"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws),
            source_provenance="curated_borderline:x1d_repetitive_touch2_and_high_friction",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_009",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_x1d_unverified_conference_encounter",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Verify whether this two-touch Unify Consulting banking email fabricates an unverified prior panel interaction not present in the source evidence?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Following up from last Thursday's Charlotte AI risk symposium)\n"
                "Hi Pascal, really valued your panel remarks at last Thursday's Charlotte banking AI symposium, and our mutual colleague David suggested I follow up "
                "directly. At Unify Consulting, we cut banking regulatory findings by 35% and compressed deployment from six months to three weeks. Open to continuing the "
                "discussion next Tuesday?\n\n"
                "Touch 2 (Subject: Re: Following up from last Thursday's Charlotte AI risk symposium)\n"
                "Adding one note from our $22M IP-led platform rollout at Unify: deterministic runtime replay was the key to fast model-risk sign-off. Would a 15-minute "
                "peer exchange before your steering committee work?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            subtle_defect_type="fabricated_prior_symposium_encounter_and_mutual_referral",
            source_provenance="curated_subtle_defect:x1d_fake_familiarity",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_010",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_x1d_subtle_metric_and_scope_drift",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Check whether this two-touch email violates metric grounding by inflating Unify Consulting's 35% regulatory reduction and $22M revenue into larger banking claims?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Compressing regulated banking AI release cycles)\n"
                "Hi Pascal, balancing release speed with model-risk governance is critical as agentic workflows scale. At Unify Consulting, our deterministic control "
                "plane compressed deployment cycles from six months to ten days while cutting regulatory audit findings by 55% across Tier-1 banks. Open to a brief "
                "peer exchange next week?\n\n"
                "Touch 2 (Subject: Re: Compressing regulated banking AI release cycles)\n"
                "One additional data point: productizing those compliance checkpoints into reusable services generated $38M in IP-led software revenue and $9M in annual "
                "contract value. Happy to share a two-page architecture summary?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            subtle_defect_type="inflated_unify_metrics_3wk_to_10d_35pct_to_55pct_22m_to_38m",
            source_provenance="curated_subtle_defect:x1d_subtle_numeric_drift",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_011",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_x1d_premature_compensation_and_internal_org_claim",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="email",
            recipient_class="recruiter",
            target_context=(
                "Does this recruiter sequence on Unify Consulting banking governance violate peer friction standards by injecting unverified turnover claims and salary demands?"
            ),
            candidate_text=(
                "Touch 1 (Subject: SVP AI Platforms search & compensation alignment)\n"
                "Hi Dana, given the recent turnover across the care-center data teams at your client, my Unify Consulting track record ($22M IP-led "
                "revenue, $5M ACV, 35% fewer banking regulatory findings) is a direct fit. Before scheduling an introductory call, please confirm the role clears a $485K "
                "base salary plus guaranteed equity in year one?\n\n"
                "Touch 2 (Subject: Re: SVP AI Platforms search & compensation alignment)\n"
                "Following up on my note regarding the $3.5M Slalom utility charter and Unify governance metrics. Please confirm the cash and equity band today so we can proceed?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev, f_slalom_util),
            subtle_defect_type="unverified_target_churn_claim_and_cold_compensation_ultimatum",
            source_provenance="curated_subtle_defect:x1d_comp_ultimatum_and_rumor",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_012",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_x1d_vendor_pitch_persona_inversion",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="linkedin_inmail",
            recipient_class="vp_executive",
            target_context=(
                "Evaluate whether this two-touch InMail inverts the executive peer persona into a consulting SOW sales pitch offering to deploy Slalom pods for a fee?"
            ),
            candidate_text=(
                "Touch 1 (Subject: Proposal to deploy 45-day Claude Code pods for your Q2 roadmap)\n"
                "Hi Marcus, our consulting practice recently delivered a $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats, "
                "following a six-figure IBM Maximo visual inspection SOW (92% OCR accuracy). I would like to scope a paid six-week assessment SOW for your alliance "
                "engineering group this quarter. Can you invite your procurement lead to a 45-minute scoping workshop Thursday?\n\n"
                "Touch 2 (Subject: Re: Proposal to deploy 45-day Claude Code pods for your Q2 roadmap)\n"
                "Checking back on our consulting SOW availability: we have two 45-day pods coming off a $3.5M utility charter next month and can lock in preferred partner rates."
            ),
            allowed_facts=(f_slalom_part, f_slalom_maximo, f_slalom_util),
            subtle_defect_type="consulting_vendor_sow_sales_pitch_instead_of_executive_peer_outreach",
            source_provenance="curated_subtle_defect:x1d_vendor_sow_pitch_inversion",
        ),
        # --- executive_judge_panel (12 items: 4 clean_pass, 4 borderline, 4 subtle_defect) ---
        GoldCandidateRecord(
            item_id="lic_gold_013",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_panel_caio_single_touch_runtime_gates",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Does this single-touch Chief AI Officer email connect enterprise model-risk friction to verified Unify Consulting deployment and compliance outcomes?"
            ),
            candidate_text=(
                "Subject: Closing the gap between banking AI pilots and model-risk sign-off\n"
                "Pascal, your focus on aligning iterative model delivery with accountable banking governance addresses the exact bottleneck where most enterprise AI stalls. "
                "At Unify Consulting, embedding deterministic compliance checkpoints and explainability controls directly into the runtime path cut banking regulatory "
                "findings by 35% and compressed lab-to-production deployment from six months to three weeks. Would you be open to a brief peer conversation next week?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="curated_clean:panel_caio_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_014",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_panel_recruiter_concise_fit_inmail",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="linkedin_inmail",
            recipient_class="recruiter",
            target_context=(
                "How well does this concise recruiter InMail establish SVP platform scale and regulated banking governance fit within a low-friction 10-minute ask?"
            ),
            candidate_text=(
                "Subject: SVP AI Platforms / Regulated Banking Governance\n"
                "Hi Sarah, your search for an engineering leader to scale governed AI platforms aligns directly with my recent work as SVP Engineering at Unify Consulting "
                "($22M IP-led platform revenue, $5M ACV via CFO-aligned consumption licensing, and 35% fewer banking regulatory findings across six-month to three-week "
                "release cycles). Open to a quick 10-minute fit check this week?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="curated_clean:panel_recruiter_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_015",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_panel_vp_alliances_field_blueprints",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="email",
            recipient_class="vp_executive",
            target_context=(
                "Evaluate whether this VP of Cloud Alliances email grounds its field enablement thesis in verified Slalom Anthropic/Gemini and IBM AWS co-sell metrics?"
            ),
            candidate_text=(
                "Subject: Hyperscaler co-sell architecture and field enablement\n"
                "Hi Claire, scaling partner co-sell beyond initial demos hinges on reference blueprints that field engineers can deploy in regulated "
                "accounts. I directed a $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats at Slalom, after leading AWS "
                "co-sell motions in financial services at IBM that delivered 20% joint revenue growth. Would a 15-minute exchange on field enablement next week be useful?"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws),
            source_provenance="curated_clean:panel_vp_alliances_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_016",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            topic_family="lic_panel_board_risk_committee_brief",
            nuance_profile="CALIBRATED_EXEMPLARY_WITH_REAL_CONSTRAINT_TENSION",
            channel="email",
            recipient_class="board_member",
            target_context=(
                "Does this board technology committee note maintain peer board advisory gravitas while citing verified Slalom utility and Unify banking governance outcomes?"
            ),
            candidate_text=(
                "Subject: Auditability controls for frontline agentic AI programs\n"
                "Hi Robert, as regulated institutions expand agentic AI into customer and grid operations, deterministic auditability and fail-closed runtime gates often "
                "determine whether programs clear risk committee scrutiny. Across recent utility and banking charters ($3.5M Slalom SCADA modernization with zero red "
                "escalations; 35% fewer banking regulatory findings at Unify Consulting), embedding compliance checkpoints directly into the runtime path resolved governance "
                "delays early. Would you welcome a concise one-page benchmark note ahead of your next technology committee?"
            ),
            allowed_facts=(f_slalom_util, f_unify_reg, f_unify_cycle),
            source_provenance="curated_clean:panel_board_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_017",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="lic_panel_caio_generic_opening_hook",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Assess whether this Chief AI Officer email remains grounded in Unify Consulting and Slalom metrics despite opening with a broad industry hook?"
            ),
            candidate_text=(
                "Subject: Enterprise AI platform governance and delivery\n"
                "Hi Pascal, I lead enterprise AI platform engineering with experience across Slalom, Unify Consulting, and IBM. At Unify Consulting, our team reduced "
                "banking regulatory findings by 35%, compressed lab-to-production deployment from six months to three weeks, and delivered $22M in IP-led platform revenue. "
                "I would appreciate the chance to exchange notes on your current AI platform priorities. Are you open to a brief introductory call next week?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev, f_slalom_util, f_ibm_aws),
            source_provenance="curated_borderline:panel_slightly_generic_no_company_hook",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_018",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="lic_panel_inmail_exhaustive_resume_recitation",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="linkedin_inmail",
            recipient_class="recruiter",
            target_context=(
                "Does this recruiter InMail fail channel concision and proportion standards by dumping every career metric from IBM, Unify, and Slalom into one oversized block?"
            ),
            candidate_text=(
                "Subject: Candidacy for SVP of AI Platforms mandate\n"
                "Hi Sarah, I saw your posting for SVP of AI Platforms and wanted to share my complete career inventory across IBM, Unify Consulting, and Slalom. I generated "
                "$22M in IP-led platform revenue at Unify, unlocked $5M in ACV via CFO-aligned consumption licensing, compressed deployment from six months to three weeks, "
                "reduced banking regulatory findings by 35%, directed a $3.5M utility SCADA charter with zero red escalations and target 20% call-center deflection, delivered "
                "92% OCR accuracy into IBM Maximo, led a $2.4M Anthropic Claude workstream, scaled Gemini Enterprise from 750 to 5,750+ seats, and drove 20% AWS joint revenue "
                "growth at IBM. When can we schedule a 30-minute interview?"
            ),
            allowed_facts=f_all,
            source_provenance="curated_borderline:panel_inmail_over_length_resume_dump",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_019",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=True,
            topic_family="lic_panel_vp_alliances_sparse_mechanism",
            nuance_profile="MANDATE_CONSTRAINT_OMISSION",
            channel="email",
            recipient_class="vp_executive",
            target_context=(
                "Evaluate whether this VP of Alliances note passes grounding and low-friction standards on Slalom Gemini and IBM AWS metrics despite omitting 45-day pod details?"
            ),
            candidate_text=(
                "Subject: Enterprise AI alliance enablement benchmarks\n"
                "Hi Claire, thought our recent work scaling Gemini Enterprise from 750 to 5,750+ seats alongside a $2.4M Anthropic Claude enablement workstream at Slalom "
                "and 20% AWS financial-services joint revenue growth at IBM might be relevant as your team expands enterprise partner adoption. Open to a brief 15-minute "
                "exchange next week if partner GTM enablement is an active priority?"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws),
            source_provenance="curated_borderline:panel_brief_clean_but_light_context",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_020",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=False,
            topic_family="lic_panel_high_friction_multi_stakeholder_ask",
            nuance_profile="FRICTION_OR_PROPORTION_MISMATCH",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Does this Chief AI Officer email fail low-friction actionability by demanding a 45-minute multi-VP deck review on cold outreach despite accurate Unify metrics?"
            ),
            candidate_text=(
                "Subject: Deep-dive walkthrough of our agentic AI control plane\n"
                "Hi Pascal, your bank's focus on explainable AI aligns closely with our platform architecture at Unify Consulting, where we compressed lab-to-production "
                "cycles from six months to three weeks, generated $22M in IP-led revenue, and cut banking regulatory findings by 35%. I have attached a 28-slide technical "
                "deck and would like to book a 45-minute architecture review with you, your Head of Model Risk, and your VP of Platform Engineering this Friday afternoon."
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            source_provenance="curated_borderline:panel_high_friction_no_question",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_021",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_panel_industry_stat_misattributed_to_recipient",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Verify whether this banking email violates factual grounding by misattributing an 87% industry failure statistic as a direct claim against the recipient?"
            ),
            candidate_text=(
                "Subject: Resolving your division's model deployment backlog\n"
                "Hi Pascal, I noticed from recent public commentary that 87% of your bank's internal data science models are currently stalling before production due to "
                "linear IT handoffs and governance friction. At Unify Consulting, our runtime explainability checkpoints cut banking regulatory findings by 35% and "
                "compressed release cycles from six months to three weeks across $22M in IP-led platform delivery. Open to discussing how to clear that backlog next week?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            subtle_defect_type="misattributed_general_industry_87pct_stat_as_recipient_bank_failure",
            source_provenance="curated_subtle_defect:panel_hostile_misattribution",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_022",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_panel_cross_partner_metric_swap",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            channel="email",
            recipient_class="vp_executive",
            target_context=(
                "Check whether this VP of Alliances email swaps and blends metrics across Anthropic Claude, Gemini Enterprise, and Unify Consulting into ungrounded partner claims?"
            ),
            candidate_text=(
                "Subject: Scaling Anthropic Claude and AWS financial-services co-sell\n"
                "Hi Claire, turning model alliances into regulated adoption requires repeatable field engineering. At Slalom, I led a $5M ACV program for Anthropic Claude "
                "that grew Claude from 750 to 5,750+ seats across banking teams, building on my IBM tenure where our AWS alliance delivered 35% revenue growth in financial "
                "services. Would a 15-minute exchange next week be useful?"
            ),
            allowed_facts=(f_slalom_part, f_ibm_aws, f_unify_rev, f_unify_reg),
            subtle_defect_type="cross_entity_metric_swap_5m_acv_and_5750_seats_to_claude_35pct_to_aws",
            source_provenance="curated_subtle_defect:panel_metric_entity_swap",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_023",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_panel_raw_markdown_and_insider_handle_leak",
            nuance_profile="DENSE_INSIDER_SHORTHAND_OR_CADENCE",
            channel="email",
            recipient_class="recruiter",
            target_context=(
                "Does this Unify Consulting banking recruiter email violate clarity and peer authority by leaking raw Markdown syntax and internal artifact IDs into plain text?"
            ),
            candidate_text=(
                "Subject: SVP AI Platforms candidate follow-up and portfolio links\n"
                "Hi Sarah, I am hoping to be considered for your SVP of AI Platforms requisition and have compiled my Unify Consulting governance case studies ($22M IP-led "
                "revenue, 35% fewer banking regulatory findings, six-month to three-week release compression) inside [my architecture portfolio](https://github.com/org/repo) "
                "under artifact `full_resume_799cfd12ad34`. Could you forward my packet to the hiring manager and let me know if I qualify for a first-round screen?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            subtle_defect_type="raw_markdown_link_internal_artifact_id_leak_and_subordinate_posture",
            source_provenance="curated_subtle_defect:panel_subordinate_and_format_breach",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_024",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            topic_family="lic_panel_unverified_regulatory_examination_claim",
            nuance_profile="SUBTLE_SCOPE_OR_TEMPORAL_EXTRAPOLATION",
            channel="email",
            recipient_class="c_suite_executive",
            target_context=(
                "Determine whether this Chief AI Officer email violates factual grounding by speculating about an unverified OCC model-risk examination at the target bank?"
            ),
            candidate_text=(
                "Subject: Preparing for your Q3 OCC examination on care-center AI\n"
                "Hi Pascal, with your care-center AI teams preparing for next quarter's OCC consent review, establishing replayable audit trails before examiners "
                "arrive is critical. At Unify Consulting, our compliance checkpoints in the runtime path reduced banking findings by 35% and compressed deployment from "
                "six months to three weeks across $22M in platform rollouts. Open to a confidential 15-minute review next week?"
            ),
            allowed_facts=(f_unify_cycle, f_unify_reg, f_unify_rev),
            subtle_defect_type="unverified_speculative_q3_occ_examination_claim_on_recipient",
            source_provenance="curated_subtle_defect:panel_fabricated_regulatory_exam_rumor",
        ),
    ]


def main() -> int:
    rg_items = build_resume_gold_candidates()
    lic_items = build_outreach_gold_candidates()
    rg_errs = validate_stratification(rg_items, engine="resume_engine")
    lic_errs = validate_stratification(lic_items, engine="outreach_engine")
    if rg_errs or lic_errs:
        for e in rg_errs + lic_errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out_dir = REPO_ROOT / "data" / "judge_calibration"
    write_gold_candidates_jsonl(rg_items, out_dir / "resume_gold_candidates.v1.jsonl")
    write_gold_candidates_jsonl(lic_items, out_dir / "outreach_gold_candidates.v1.jsonl")

    pool_dir = REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets"
    pool_dir.mkdir(parents=True, exist_ok=True)
    rg_pool = build_studio_blind_pool_dict(rg_items, engine="resume_engine", repo_root=REPO_ROOT)
    lic_pool = build_studio_blind_pool_dict(lic_items, engine="outreach_engine", repo_root=REPO_ROOT)
    (pool_dir / "resume_blind_pool.v1.json").write_text(
        json.dumps(rg_pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (pool_dir / "outreach_blind_pool.v1.json").write_text(
        json.dumps(lic_pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    combined_items = list(rg_pool["items"]) + list(lic_pool["items"])
    combined_pool = {
        **rg_pool,
        "judge_surface": "combined_resume_and_outreach",
        "sample_count": len(combined_items),
        "items": combined_items,
    }
    (pool_dir / "combined_blind_pool.v1.json").write_text(
        json.dumps(combined_pool, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {len(rg_items)} resume + {len(lic_items)} outreach gold candidates to {out_dir} "
        f"and Studio pools to {pool_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
