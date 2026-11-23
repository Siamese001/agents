#!/usr/bin/env python3
"""Curate frozen 48-item stratified gold candidate corpora (24 Resume + 24 Outreach) for external human grading."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.graders.judge.gold_corpus import (
    GoldCandidateRecord,
    validate_stratification,
    write_gold_candidates_jsonl,
)


def build_resume_gold_candidates() -> list[GoldCandidateRecord]:
    """Return 24 stratified Resume items (4 x 6 judge families; 8 clean_pass, 8 borderline, 8 subtle_defect)."""
    f_slalom = (
        "Slalom Senior Director (Jun 2026-Present): $3.5M utility modernization charter, SCADA grid-restoration intelligence, zero red escalations, target 20% call-center deflection.",
        "Slalom: $2.4M Anthropic Claude enablement workstream, 45-day Claude Code pods, Gemini Enterprise growth from 750 to 5,750+ seats.",
        "Slalom: six-figure multi-modal visual asset intelligence SOW on power generation nameplates; 90% primary-field accuracy, 92% OCR accuracy, 100% full-plate auto-acceptance into IBM Maximo.",
    )
    f_unify = (
        "Unify Consulting SVP Engineering, Agentic AI Platforms (Feb 2023-Jun 2026): $22M IP-led revenue converting bespoke consulting into reusable platform services.",
        "Unify Consulting: $5M annual contract value unlocked via CFO-aligned enterprise AI workflow adoption and consumption-based licensing.",
        "Unify Consulting: compressed lab-to-production AI deployment cycles from six months to three weeks with deterministic auditability and replayable runtime governance.",
        "Unify Consulting: reduced regulatory findings by 35% across banking AI rollouts via data usage controls, compliance checkpoints, and model-explainability standards.",
    )
    f_ibm = (
        "IBM Partner (Apr 2017-Oct 2022): led AWS alliance co-sell motions across regulated financial services delivering 20% joint revenue growth.",
        "IBM Partner: architected enterprise NLP and ML decision-support pipelines with governed data lineage and DevSecOps controls across banking and insurance institutions.",
    )
    all_facts = f_slalom + f_unify + f_ibm
    target_svp = "Target Role: SVP of AI Platforms & Forward Deployed Engineering (Regulated Financial Services)"
    target_part = "Target Role: SVP of AI Partnerships & Cloud Alliance GTM (Enterprise Hyperscalers)"

    # 6 families x 4 items = 24 items
    # Tier balance across families:
    # headline: 2 clean, 1 borderline, 1 defect
    # executive_summary: 2 clean, 1 borderline, 1 defect
    # competencies: 1 clean, 2 borderline, 1 defect
    # employment_bullets: 1 clean, 1 borderline, 2 defect
    # role_narrative: 1 clean, 2 borderline, 1 defect
    # whole_resume_coherence: 1 clean, 1 borderline, 2 defect
    # Total: clean=8, borderline=8, defect=8!
    return [
        # --- 1. HEADLINE (4 items: 2 clean, 1 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_001",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_part,
            candidate_text="SVP AI Partnerships | Cloud AI Platforms | Partner GTM Solutions | Regulated Financial Systems",
            allowed_facts=f_slalom + f_ibm,
            source_provenance="full_resume_799cfd12ad34:headline",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_002",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_svp,
            candidate_text="SVP Engineering | Agentic AI Control Planes | Regulated Banking Governance | Reusable Platform Delivery",
            allowed_facts=f_unify + f_slalom,
            source_provenance="full_resume_799cfd12ad34:headline_svp_variant",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_003",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="borderline",
            expected_pass=True,
            target_context=target_svp,
            candidate_text="Senior Technology Leader | Enterprise AI Transformation | Cloud Delivery Modernization | Executive Stakeholder Alignment",
            allowed_facts=f_unify + f_ibm,
            source_provenance="curated_borderline:headline_generic_abstraction",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_004",
            engine="resume_engine",
            judge_family="headline",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text="SVP Engineering | $50M Banking AI P&L Owner | Forward-Deployed Zero-Touch Banking Paradigm",
            allowed_facts=f_unify + f_ibm,
            subtle_defect_type="stretched_metric_and_jd_parrot",
            source_provenance="curated_subtle_defect:headline_metric_stretch",
        ),
        # --- 2. EXECUTIVE SUMMARY (4 items: 2 clean, 1 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_005",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_part,
            candidate_text=(
                "Applied AI architecture and partnerships leader who turns cloud and model alliances into repeatable enterprise production adoption. "
                "Directed Anthropic Claude and Google Cloud co-innovation, delivering a $2.4M Claude enablement workstream, 45-day Claude Code pods, "
                "and Gemini Enterprise growth from 750 to 5,750+ seats. Led AWS alliance co-sell motions across regulated financial services to deliver "
                "20% joint revenue growth. Built partner co-sell channel motions, joint solution blueprints, and field enablement assets packaged around "
                "reusable AI platform services across cloud alliances."
            ),
            allowed_facts=f_slalom + f_ibm,
            source_provenance="full_resume_799cfd12ad34:executive_summary",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_006",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "Engineering executive who builds governed agentic AI platforms that pass enterprise model-risk review and generate commercial revenue. "
                "At Unify Consulting, converted bespoke advisory work into reusable AI platform services generating $22M in IP-led revenue and $5M in "
                "annual contract value through CFO-aligned consumption licensing. Compressed lab-to-production AI deployment from six months to three weeks "
                "while cutting banking regulatory findings by 35% through runtime compliance checkpoints and explainability controls. Currently leads a $3.5M "
                "utility modernization charter at Slalom combining multi-agent workflows with audit-grade telemetry."
            ),
            allowed_facts=f_unify + f_slalom,
            source_provenance="curated_clean:executive_summary_unify_slalom",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_007",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="borderline",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "Seasoned engineering leader with deep experience modernizing enterprise AI platforms across consulting and regulated financial services. "
                "Supported multi-agent platform adoption and partner co-sell initiatives, including a $2.4M Claude workstream and cloud alliance growth. "
                "Collaborated across product, risk, and executive leadership to establish lifecycle controls that shortened deployment timelines and "
                "improved compliance readiness across client organizations."
            ),
            allowed_facts=all_facts,
            source_provenance="curated_borderline:executive_summary_diluted_authority",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_008",
            engine="resume_engine",
            judge_family="executive_summary",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "Visionary AI executive driving synergistic forward-deployed transformation across regulated banking ecosystems. "
                "Grew Gemini Enterprise adoption from 750 to over 12,000 seats while delivering $38M in IP-led platform revenue and reducing "
                "banking regulatory findings by 55% across Tier-1 institutions. Proven track record of unlocking holistic enterprise value at scale."
            ),
            allowed_facts=all_facts,
            subtle_defect_type="subtle_metric_inflation_and_ai_filler",
            source_provenance="curated_subtle_defect:executive_summary_metric_stretch",
        ),
        # --- 3. COMPETENCIES (4 items: 1 clean, 2 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_009",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_part,
            candidate_text=(
                "Cloud & Partner Ecosystems: partner customer deal support engineering, partner alliance GTM execution leadership, joint hyperscaler reference blueprint co-design\n"
                "AI Platform Leadership: multi-agent orchestration control plane design, policy-bound autonomous runtime execution topology, reusable agentic platform runtime spine\n"
                "Governance, Risk & Compliance: fail-closed runtime control gate design, policy enforcement across autonomous execution paths, sandboxed decision workflows with audit trails\n"
                "LLMOps & Reliability: audit-ready reliability telemetry for governed systems, automated evaluation harnesses for behavior assurance, deterministic rollback safeguards for production LLMs"
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
            target_context=target_svp,
            candidate_text=(
                "AI Platforms: enterprise generative AI, LLM deployment, agentic orchestration, prompt engineering, cloud infrastructure\n"
                "Governance & Compliance: AI governance, risk management, model risk controls, regulatory readiness, audit compliance\n"
                "Leadership & Strategy: executive communication, stakeholder management, strategic planning, cross-functional delivery, vendor partnerships"
            ),
            allowed_facts=all_facts,
            source_provenance="curated_borderline:competencies_generic_laundry_list",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_011",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="borderline",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "Runtime Control Plane Orchestration Topology: multi-layer deterministic graph routing policy enforcement and fail-closed telemetry gate mesh architecture\n"
                "Hyperscaler Commercialization Acceleration Motion: partner co-innovation consumption licensing value modeling and executive pursuit architecture governance"
            ),
            allowed_facts=all_facts,
            source_provenance="curated_borderline:competencies_noun_stack_overload",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_012",
            engine="resume_engine",
            judge_family="competencies",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "Core Banking & Capital Markets: real-time SWIFT wire settlement engines, Basel III liquidity stress modeling, retail branch deposit core migration\n"
                "AI Platform Leadership: forward-deployed engineering pods, policy-bound agentic runtimes, regulatory compliance checkpoints"
            ),
            allowed_facts=all_facts,
            subtle_defect_type="unsupported_domain_skills_claimed",
            source_provenance="curated_subtle_defect:competencies_ungrounded_banking_core",
        ),
        # --- 4. EMPLOYMENT BULLETS (4 items: 1 clean, 1 borderline, 2 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_013",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "- Generated $22M in IP-led revenue across enterprise lines of business by converting bespoke consulting delivery into reusable platform services under a unified agentic AI operating model.\n"
                "- Unlocked $5M in annual contract value through CFO-aligned enterprise AI workflow adoption, structuring consumption-based licensing models to accelerate commercial value realization.\n"
                "- Compressed lab-to-production AI deployment cycles from six months to three weeks through standardized lifecycle practices that enforced deterministic auditability and replayable runtime governance.\n"
                "- Reduced regulatory findings by 35% across banking AI rollouts by instituting data usage controls, compliance checkpoints, and model-explainability standards to accelerate model-risk approval."
            ),
            allowed_facts=f_unify,
            source_provenance="full_resume_799cfd12ad34:unify_bullets",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_014",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="borderline",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "- Helped build a reusable agentic AI operating model that contributed to $22M in IP-led revenue across enterprise client lines of business.\n"
                "- Worked with finance stakeholders on consumption-based licensing models that supported $5M in annual contract value.\n"
                "- Improved deployment velocity from six months to three weeks using standardized lifecycle practices and runtime checks."
            ),
            allowed_facts=f_unify,
            source_provenance="curated_borderline:unify_bullets_weak_verbs_passive",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_015",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "- Architected a $3.5M utility modernization charter at Slalom and reduced banking regulatory findings by 35% across Tier-1 financial rollouts through model-explainability controls.\n"
                "- Directed a six-figure multi-modal visual asset intelligence SOW on power generation equipment nameplates achieving 92% OCR accuracy and 100% full-plate auto-acceptance into IBM Maximo."
            ),
            allowed_facts=f_slalom,
            subtle_defect_type="cross_employer_metric_misattribution",
            source_provenance="curated_subtle_defect:slalom_bullet_borrows_unify_35pct",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_016",
            engine="resume_engine",
            judge_family="employment_bullets",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "- Accelerated lab-to-production AI deployment cycles from six months to 48 hours via zero-touch autonomous governance pipelines across 40+ regulated banking subsidiaries.\n"
                "- Unlocked $11M in annual contract value through enterprise AI workflow licensing and cut regulatory findings by 52%."
            ),
            allowed_facts=f_unify,
            subtle_defect_type="subtle_metric_exaggeration",
            source_provenance="curated_subtle_defect:unify_bullets_inflated_numbers",
        ),
        # --- 5. ROLE NARRATIVE (4 items: 1 clean, 2 borderline, 1 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_017",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "Championed Unify Consulting's agentic AI control plane, combining GraphRAG grounding with runtime governance to make enterprise "
                "deployment dependable, turn solution capability into durable commercial infrastructure, and align architecture stewardship with "
                "scalable economics for regulated clients."
            ),
            allowed_facts=f_unify,
            source_provenance="full_resume_799cfd12ad34:unify_narrative",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_018",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="borderline",
            expected_pass=True,
            target_context=target_svp,
            candidate_text=(
                "Operationalized governed enterprise AI by converting multi-agent workflows and multimodal operational data into traceable production "
                "capabilities that improved response, strengthened regulated decision-making, and expanded client transformation value."
            ),
            allowed_facts=f_slalom,
            source_provenance="full_resume_799cfd12ad34:slalom_narrative_dense",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_019",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="borderline",
            expected_pass=False,
            target_context=target_part,
            candidate_text=(
                "Responsible for overseeing technology delivery and partner engagements at IBM, focusing on machine learning systems, cloud modernization, "
                "and helping regulated clients navigate digital transformation initiatives across banking and insurance verticals."
            ),
            allowed_facts=f_ibm,
            source_provenance="curated_borderline:ibm_narrative_subordinate_generic",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_020",
            engine="resume_engine",
            judge_family="role_narrative",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "I spearheaded a transformative, holistic AI revolution at Unify Consulting -- seamlessly orchestrating synergistic forward-deployed "
                "engineering excellence across Fortune 50 banking boards while owning a $150M global cloud P&L."
            ),
            allowed_facts=f_unify,
            subtle_defect_type="first_person_ai_slop_and_scope_inflation",
            source_provenance="curated_subtle_defect:unify_narrative_slop_and_pnl",
        ),
        # --- 6. WHOLE-RESUME COHERENCE (4 items: 1 clean, 1 borderline, 2 subtle_defect) ---
        GoldCandidateRecord(
            item_id="rg_gold_021",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=target_part,
            candidate_text=(
                "HEADLINE: SVP AI Partnerships | Cloud AI Platforms | Partner GTM Solutions | Regulated Financial Systems\n"
                "SUMMARY: Applied AI architecture and partnerships leader converting Anthropic, Google Cloud, and AWS alliances into enterprise adoption "
                "($2.4M Claude enablement, 750 to 5,750+ Gemini Enterprise seats, 20% AWS joint revenue growth).\n"
                "EXPERIENCE ARC: Slalom (Senior Director, Jun 2026-Present: $3.5M utility agentic modernization & visual asset intelligence) -> "
                "Unify Consulting (SVP Engineering, Feb 2023-Jun 2026: $22M IP-led revenue, $5M ACV, 6mo->3wk deployment, 35% fewer banking regulatory findings) -> "
                "IBM (Partner, Apr 2017-Oct 2022: AWS co-sell 20% joint revenue growth, banking ML/DevSecOps)."
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
            target_context=target_svp,
            candidate_text=(
                "HEADLINE: SVP AI Partnerships | Partner GTM Solutions | Cloud Alliances\n"
                "SUMMARY: Highlights $2.4M Claude partner enablement and AWS co-sell growth.\n"
                "EXPERIENCE ARC: Slalom focuses heavily on utility SCADA restoration and OCR equipment nameplates; Unify focuses on internal agentic "
                "platform engineering ($22M IP revenue, 35% fewer regulatory findings). Narrative shifts between alliance sales framing and hands-on "
                "platform governance without explicitly tying the two threads together."
            ),
            allowed_facts=all_facts,
            source_provenance="curated_borderline:whole_resume_split_positioning",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_023",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "HEADLINE: SVP Engineering | Regulated Banking AI Platforms\n"
                "SUMMARY: Cites $22M IP-led revenue and 35% regulatory findings reduction achieved across banking rollouts.\n"
                "EXPERIENCE ARC: Slalom (2023-Present) claims the $22M IP-led revenue and 6mo->3wk deployment compression; Unify Consulting (2021-2023) "
                "repeats the exact same $22M revenue claim verbatim while overlapping dates with IBM (2017-2022)."
            ),
            allowed_facts=all_facts,
            subtle_defect_type="cross_section_timeline_and_double_counting",
            source_provenance="curated_subtle_defect:whole_resume_date_and_metric_collision",
        ),
        GoldCandidateRecord(
            item_id="rg_gold_024",
            engine="resume_engine",
            judge_family="whole_resume_coherence",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=target_svp,
            candidate_text=(
                "HEADLINE: Head of Forward Deployed Engineering | Care Center AI Transformation | Accountable Explainable Boosting Machines\n"
                "SUMMARY: Repeats exact job description phrasing ('87% of data science projects fail due to linear IT misalignment', 'Accountable AI "
                "Explainable Boosting Machines for Truist Care Centers') as the candidate's own historical career thesis across Unify and IBM."
            ),
            allowed_facts=all_facts,
            subtle_defect_type="jd_and_briefing_parroting_as_history",
            source_provenance="curated_subtle_defect:whole_resume_jd_mimicry",
        ),
    ]


def build_outreach_gold_candidates() -> list[GoldCandidateRecord]:
    """Return 24 stratified Outreach items (12 x1d_quorum + 12 executive_judge_panel; 8 clean, 8 borderline, 8 subtle_defect)."""
    f_cand = (
        "fact_unify_cycle: Compressed lab-to-production AI deployment from six months to three weeks with deterministic auditability at Unify Consulting.",
        "fact_unify_reg: Reduced regulatory findings by 35% across banking AI rollouts via compliance checkpoints and explainability controls.",
        "fact_unify_rev: Generated $22M in IP-led revenue and $5M ACV converting bespoke consulting into reusable agentic AI platform services.",
        "fact_slalom_util: Led $3.5M utility agentic AI modernization charter at Slalom with zero red escalations.",
        "fact_slalom_part: Directed $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats.",
        "fact_ibm_aws: Led AWS alliance co-sell motions across regulated financial services delivering 20% joint revenue growth at IBM.",
    )
    ctx_caio = "Target: Chief AI & Data Officer at regulated U.S. commercial bank (verified public focus: AI governance, model explainability, enterprise adoption)."
    ctx_rec = "Target: Executive Technical Recruiter hiring SVP of AI Platforms / Forward Deployed Engineering for regulated financial services."
    ctx_vp = "Target: VP of Cloud Alliances at enterprise hyperscaler partner organization (verified focus: co-sell solution blueprints and field enablement)."

    return [
        # --- x1d_quorum (12 items: 4 clean_pass, 4 borderline, 4 subtle_defect) ---
        GoldCandidateRecord(
            item_id="lic_gold_001",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Governed AI deployment velocity in banking)\n"
                "Pascal, your emphasis on accountable, explainable AI rather than slow linear IT handoffs mirrors a problem we solved directly "
                "in regulated banking. At Unify Consulting, instituting runtime compliance checkpoints and explainability gates cut banking "
                "regulatory findings by 35% while compressing lab-to-production deployment from six months to three weeks. Would you be open "
                "to a brief peer exchange on model-risk checkpoints next week?\n\n"
                "Touch 2 (Subject: Re: Governed AI deployment velocity in banking)\n"
                "Circling back with one operational detail: packaging those governance controls into reusable platform services generated $22M "
                "in IP-led enterprise adoption without bespoke per-team rebuilds. Happy to share a two-page architecture pattern if useful ahead "
                "of your Q1 platform review?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:x1d_caio_2touch_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_002",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_rec,
            channel="linkedin_inmail",
            recipient_class="recruiter",
            candidate_text=(
                "Touch 1 (Subject: SVP AI Platforms / Regulated Banking)\n"
                "Hi Dana, saw your search for an SVP leading forward-deployed AI platforms in regulated banking. Most recently built reusable "
                "agentic AI control planes ($22M IP-led revenue, 35% fewer banking regulatory findings, 6-month to 3-week release compression). "
                "Worth a 10-minute alignment call this week?\n\n"
                "Touch 2 (Subject: Re: SVP AI Platforms / Regulated Banking)\n"
                "Quick follow-up: also currently leading a $3.5M multi-agent utility modernization charter with zero red escalations. Happy to "
                "send a concise executive brief tailored to the hiring manager's mandate if helpful?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:x1d_recruiter_2touch_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_003",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_vp,
            channel="email",
            recipient_class="vp_executive",
            candidate_text=(
                "Touch 1 (Subject: Repeatable cloud AI co-sell blueprints)\n"
                "Hi Marcus, turning hyperscaler alliances into repeatable field adoption usually stalls between architecture demos and production "
                "governance. Directed a $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats, "
                "building on earlier IBM AWS co-sell motions that drove 20% joint revenue growth in financial services. Open to comparing notes "
                "on partner GTM architecture next Thursday?\n\n"
                "Touch 2 (Subject: Re: Repeatable cloud AI co-sell blueprints)\n"
                "Sharing one concrete lever from those programs: structuring CFO-aligned consumption licensing unlocked $5M in annual contract "
                "value once field teams had reusable reference architectures. Would a 15-minute exchange with your partner engineering lead make sense?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_clean:x1d_vp_alliances_2touch_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_004",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_caio,
            channel="linkedin_inmail",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Model-risk checkpoints for agentic workflows)\n"
                "Hi Elena, your team's focus on moving agentic workflows past pilots without triggering model-risk friction resonated closely. "
                "Cut banking regulatory findings by 35% by embedding deterministic compliance checkpoints directly into the runtime path. "
                "Open to a short peer exchange?\n\n"
                "Touch 2 (Subject: Re: Model-risk checkpoints for agentic workflows)\n"
                "Adding one metric from our latest utility charter ($3.5M modernization, zero red escalations): replayable audit trails cut "
                "governance sign-off delays significantly. Can I share a brief architecture summary?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:x1d_csuite_2touch_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_005",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=True,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Enterprise AI platform leadership)\n"
                "Hi Pascal, I have been following your bank's technology modernization efforts. At Unify Consulting, I helped cut lab-to-production "
                "deployment from six months to three weeks and reduced regulatory findings by 35%. Would you have time for a brief introductory chat?\n\n"
                "Touch 2 (Subject: Re: Enterprise AI platform leadership)\n"
                "Following up briefly on my prior note in case it slipped past your inbox. Still happy to connect and share more about our "
                "regulated banking AI governance experience if helpful?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_borderline:x1d_generic_followup_low_hook",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_006",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=False,
            target_context=ctx_caio,
            channel="linkedin_inmail",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Truist / Head of Forward Deployed Engineering - Executive Alignment)\n"
                "Hi Hiring Leader, I have been following Truist's focus on top-10 U.S. commercial bank. In my recent work, compressed AI deployment "
                "from six months to three weeks with 35% fewer regulatory findings. Happy to share our operational scaling framework if useful. "
                "Would you be open to a brief conversation next week?\n\n"
                "Touch 2 (Subject: Re: Truist / Head of Forward Deployed Engineering)\n"
                "Hi Hiring Leader, following up briefly on my note. Thought of Truist given our recent results on governed agentic workflows. "
                "Open to a 10-minute introductory conversation?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="truist_current_run:awkward_template_insertion",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_007",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=True,
            target_context=ctx_rec,
            channel="email",
            recipient_class="recruiter",
            candidate_text=(
                "Touch 1 (Subject: Background for SVP AI Platforms search)\n"
                "Hi Jordan, reaching out regarding your executive search in enterprise AI platforms. My background includes $22M in IP-led "
                "platform revenue at Unify Consulting, $5M ACV from CFO-aligned licensing, and $2.4M in Claude partner enablement at Slalom. "
                "Are you the right person to connect with regarding this mandate?\n\n"
                "Touch 2 (Subject: Re: Background for SVP AI Platforms search)\n"
                "Hi Jordan, checking back in on my note from earlier this week. I also drove 20% AWS joint revenue growth as a Partner at IBM "
                "and would welcome a quick call to see if there is mutual fit?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_borderline:x1d_recruiter_metric_heavy_slight_template",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_008",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="borderline",
            expected_pass=False,
            target_context=ctx_vp,
            channel="email",
            recipient_class="vp_executive",
            candidate_text=(
                "Touch 1 (Subject: Cloud AI alliance architecture)\n"
                "Hi Marcus, led a $2.4M Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats. Would love to discuss "
                "how we can align our synergies on partner blueprints. Let me know when works best.\n\n"
                "Touch 2 (Subject: Re: Cloud AI alliance architecture)\n"
                "Hi Marcus, reiterating my note on scaling Gemini Enterprise from 750 to 5,750+ seats and our $2.4M Claude workstream. Let me know "
                "if you have 20 minutes to connect?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_borderline:x1d_repetitive_touch2_and_missing_q1",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_009",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Following up from last week's AI governance roundtable)\n"
                "Hi Pascal, it was great hearing your remarks at last week's Charlotte executive AI dinner — our mutual colleague Steve mentioned "
                "I should reach out directly. At Unify, we cut banking regulatory findings by 35%. Open to continuing the conversation Thursday?\n\n"
                "Touch 2 (Subject: Re: Following up from last week's AI governance roundtable)\n"
                "Bumping this up before your Friday steering committee. Happy to send over our governance playbook?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="fabricated_prior_interaction_and_mutual_ref",
            source_provenance="curated_subtle_defect:x1d_fake_familiarity",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_010",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Touch 1 (Subject: Scaling banking AI platforms)\n"
                "Hi Pascal, in my recent role I scaled distributed banking platforms processing $4.2B in annual volume at 99.995% reliability "
                "while cutting regulatory findings by 60%. Would you be open to a quick discussion next week?\n\n"
                "Touch 2 (Subject: Re: Scaling banking AI platforms)\n"
                "Following up on our $4.2B platform reliability track record. Can we find 15 minutes on Tuesday?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="ungrounded_and_stretched_candidate_metrics",
            source_provenance="curated_subtle_defect:x1d_unverified_4_2b_and_60pct",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_011",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_rec,
            channel="email",
            recipient_class="recruiter",
            candidate_text=(
                "Touch 1 (Subject: SVP AI Platforms - Confidential Strategy Alignment)\n"
                "Hi Dana, per our internal research dossier [CONFIDENTIAL_BRIEF_P2: executive churn risk in care centers], I am targeting a "
                "$475K base plus equity package and bring $22M in IP-led revenue. Can we schedule an urgent call today?\n\n"
                "Touch 2 (Subject: Re: SVP AI Platforms)\n"
                "Checking back — please let me know today if the comp band fits?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="confidential_brief_leak_and_cold_comp",
            source_provenance="curated_subtle_defect:x1d_privacy_and_comp_breach",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_012",
            engine="outreach_engine",
            judge_family="x1d_quorum",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_vp,
            channel="linkedin_inmail",
            recipient_class="vp_executive",
            candidate_text=(
                "Touch 1 (Subject: Truly inspired by your transformative cloud journey!)\n"
                "Hi Marcus! I hope this message finds you thriving — I am genuinely blown away by your visionary leadership! "
                "I am actively looking for my next SVP role and would be honored for just 45 minutes of your time this week to pitch "
                "how my $2.4M Claude experience can disrupt your partner ecosystem! ACT NOW before Q4 closes!\n\n"
                "Touch 2 (Subject: Re: Quick bump!)\n"
                "Just circling back — don't miss this chance to connect!"
            ),
            allowed_facts=f_cand,
            subtle_defect_type="sales_hype_ai_warmth_and_subordinate_plea",
            source_provenance="curated_subtle_defect:x1d_hype_and_ai_slop",
        ),
        # --- executive_judge_panel (12 items: 4 clean_pass, 4 borderline, 4 subtle_defect) ---
        GoldCandidateRecord(
            item_id="lic_gold_013",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Subject: Closing the gap between AI pilots and banking governance\n"
                "Pascal, your point that enterprise AI stalls when linear IT gates collide with iterative model delivery is spot-on. "
                "At Unify Consulting, embedding compliance checkpoints and explainability controls directly into the runtime path cut "
                "banking regulatory findings by 35% and compressed lab-to-production deployment from six months to three weeks. "
                "Would you be open to a brief peer conversation next week?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:panel_caio_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_014",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_rec,
            channel="linkedin_inmail",
            recipient_class="recruiter",
            candidate_text=(
                "Subject: SVP AI Platforms / Banking Governance\n"
                "Hi Sarah, your search for an SVP to scale governed AI platforms aligns directly with my recent work ($22M IP-led platform "
                "revenue, $5M ACV via CFO-aligned licensing, and 35% fewer banking regulatory findings). Open to a quick 10-minute fit check?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:panel_recruiter_inmail",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_015",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_vp,
            channel="email",
            recipient_class="vp_executive",
            candidate_text=(
                "Subject: Hyperscaler co-sell architecture & field enablement\n"
                "Hi Claire, scaling partner co-sell beyond initial demos usually hinges on reusable reference blueprints field engineers can "
                "deploy safely. Directed a $2.4M Anthropic Claude enablement workstream and scaled Gemini Enterprise from 750 to 5,750+ seats, "
                "after leading AWS financial-services co-sell motions at IBM that delivered 20% joint revenue growth. Would comparing field "
                "enablement lessons for 15 minutes next week be useful?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_clean:panel_vp_alliances_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_016",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="clean_pass",
            expected_pass=True,
            target_context=ctx_caio,
            channel="email",
            recipient_class="board_member",
            candidate_text=(
                "Subject: Board-level risk controls for enterprise agentic AI\n"
                "Hi Robert, as financial institutions expand agentic AI into frontline operations, auditability and fail-closed rollback often "
                "decide whether programs clear regulatory scrutiny. Across recent banking and utility charters ($3.5M modernization, zero red "
                "escalations; 35% fewer banking regulatory findings), deterministic runtime checkpoints resolved model-risk bottlenecks early. "
                "Would you welcome a concise one-page benchmark note ahead of your next technology committee?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_clean:panel_board_email",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_017",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=True,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Subject: Enterprise AI governance discussion\n"
                "Hi Pascal, I lead enterprise AI platform engineering with experience across Slalom, Unify Consulting, and IBM. We reduced "
                "banking regulatory findings by 35% and delivered $22M in platform revenue. I would appreciate the chance to learn more about "
                "your AI roadmap and see how I might be helpful. Are you free for a quick call?"
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_borderline:panel_slightly_generic_no_company_hook",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_018",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=False,
            target_context=ctx_rec,
            channel="linkedin_inmail",
            recipient_class="recruiter",
            candidate_text=(
                "Subject: Interested in SVP AI Platforms role\n"
                "Hi Sarah, I noticed your posting for SVP of AI Platforms and wanted to reach out immediately. Over the past decade at IBM, "
                "Unify Consulting, and Slalom, I have built enterprise AI platforms generating $22M in IP-led revenue, unlocked $5M in ACV, "
                "compressed lab-to-production deployment cycles from six months to three weeks, reduced regulatory findings by 35% across banking "
                "AI rollouts, directed a $2.4M Claude enablement workstream, and scaled Gemini Enterprise from 750 to 5,750+ seats. Please let me "
                "know when we can speak about my candidacy?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_borderline:panel_inmail_over_length_resume_dump",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_019",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=True,
            target_context=ctx_vp,
            channel="email",
            recipient_class="vp_executive",
            candidate_text=(
                "Subject: Partner enablement metrics\n"
                "Hi Claire, thought our work scaling Gemini Enterprise from 750 to 5,750+ seats and driving 20% AWS joint revenue growth at IBM "
                "might be relevant as your team expands enterprise AI alliances. Open to a brief exchange next week if partner GTM enablement is "
                "a current priority?"
            ),
            allowed_facts=f_cand,
            source_provenance="curated_borderline:panel_brief_clean_but_light_context",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_020",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="borderline",
            expected_pass=False,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Subject: Agentic AI architecture ideas\n"
                "Hi Pascal, your bank's focus on explainable AI is really compelling. We compressed lab-to-production cycles from six months "
                "to three weeks at Unify Consulting and cut regulatory findings by 35%. I'd love to send over my full slide deck and schedule "
                "a 30-minute walkthrough with you and your VPs."
            ),
            allowed_facts=f_cand[:4],
            source_provenance="curated_borderline:panel_high_friction_no_question",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_021",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Subject: Addressing your 87% model failure rate\n"
                "Hi Pascal, I saw that 87% of your bank's internal data science projects are currently failing due to IT friction. At Unify, "
                "we cut regulatory findings by 35% and delivered $22M in platform revenue. Open to fixing that gap next week?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="misattributed_industry_stat_as_target_accusation",
            source_provenance="curated_subtle_defect:panel_hostile_misattribution",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_022",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_vp,
            channel="email",
            recipient_class="vp_executive",
            candidate_text=(
                "Subject: Co-sell alliance growth\n"
                "Hi Claire, I led a $9.5M Anthropic Claude partnership and grew Gemini Enterprise from 750 to 15,000 seats while delivering "
                "45% AWS joint revenue growth at IBM. Open to a quick call next week?"
            ),
            allowed_facts=f_cand,
            subtle_defect_type="inflated_partner_metrics",
            source_provenance="curated_subtle_defect:panel_metric_stretch",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_023",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_rec,
            channel="email",
            recipient_class="recruiter",
            candidate_text=(
                "Subject: Please consider me for your SVP role\n"
                "Hi Sarah, I am desperately seeking my next executive leadership role and would be forever grateful if you could please "
                "put my resume in front of the hiring manager — I have [my portfolio](https://github.com/Siamese001) ready to review. "
                "Could you please hire me or set up an interview ASAP?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="subordinate_plea_em_dash_and_markdown_link",
            source_provenance="curated_subtle_defect:panel_subordinate_and_format_breach",
        ),
        GoldCandidateRecord(
            item_id="lic_gold_024",
            engine="outreach_engine",
            judge_family="executive_judge_panel",
            expected_tier="subtle_defect",
            expected_pass=False,
            target_context=ctx_caio,
            channel="email",
            recipient_class="c_suite_executive",
            candidate_text=(
                "Subject: Congrats on your upcoming unannounced fintech acquisition\n"
                "Hi Pascal, heard through backchannels that your team is preparing to restructure the care center AI org after next quarter's "
                "acquisition. With our 35% regulatory findings reduction at Unify, I'd love to advise you quietly. Open to a confidential chat?"
            ),
            allowed_facts=f_cand[:4],
            subtle_defect_type="unsupported_speculative_company_claim",
            source_provenance="curated_subtle_defect:panel_fabricated_insider_rumor",
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
    print(f"Wrote {len(rg_items)} resume + {len(lic_items)} outreach gold candidates to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
