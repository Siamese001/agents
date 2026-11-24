"""Full-Resume Coherence Judge v3 Binding & Lens Aggregator (`<= 140L`, zero prose wall)."""
from __future__ import annotations

from typing import Any, Sequence

from apps_rg.runtime.judges.v3_section_judge import render_section_v3_rubric

FULL_RESUME_COHERENCE_RUBRIC_VERSION = "full_resume_coherence_judge_v3"
FULL_RESUME_COHERENCE_RUBRIC = render_section_v3_rubric("full_resume_coherence")

LENS_DEFINITIONS: tuple[str, ...] = (
    "narrative_coherence",
    "hr_recruiter_first_impression",
    "ats_semantic_taxonomy",
    "jd_briefing_resonance",
    "knockout_and_risk_vectors",
    "altitude_and_band_calibration",
)

LENS_METADATA: dict[str, dict[str, str]] = {
    "narrative_coherence": {
        "name": "Executive Leadership Storyline",
        "description": "End-to-end headline, summary, and experience alignment.",
    },
    "hr_recruiter_first_impression": {
        "name": "6-Second Initial Screen",
        "description": "Visual rhythm, scannability, and immediate value proposition.",
    },
    "ats_semantic_taxonomy": {
        "name": "Machine Parseability & Structure",
        "description": "Standard technology taxonomy and competency clustering.",
    },
    "jd_briefing_resonance": {
        "name": "Strategic Alignment without Claim Invention",
        "description": "Enterprise context resonance without unsupported claims.",
    },
    "knockout_and_risk_vectors": {
        "name": "Credibility & Skeptical Screener",
        "description": "Metric believability, lack of vanity claims, trajectory integrity.",
    },
    "altitude_and_band_calibration": {
        "name": "Executive Leveling",
        "description": "Calibration to target executive band without IC downgrade.",
    },
}


def _categorize_finding_by_lens(finding: str) -> str:
    low = finding.lower()
    if any(k in low for k in ("6-second", "recruiter", "scannab", "visual", "consistent_executive_voice")):
        return "hr_recruiter_first_impression"
    if any(k in low for k in ("ats", "taxonomy", "cluster", "keyword stuffing", "competenc")):
        return "ats_semantic_taxonomy"
    if any(k in low for k in ("briefing", "jd", "mandate", "target role", "unified_mandate_arc")):
        return "jd_briefing_resonance"
    if any(k in low for k in ("knockout", "risk", "believab", "attribution", "unverified", "unsupported", "hallucinat", "echo", "zero_cross_section_metric_echo")):
        return "knockout_and_risk_vectors"
    if any(k in low for k in ("altitude", "band", "seniority", "leveling", "junior")):
        return "altitude_and_band_calibration"
    return "narrative_coherence"


def build_lens_analysis(judge_outputs: Sequence[Any]) -> dict[str, Any]:
    lens_observations: dict[str, list[dict[str, Any]]] = {lens: [] for lens in LENS_DEFINITIONS}
    for o in judge_outputs:
        if isinstance(o, dict):
            findings, jid = o.get("findings"), o.get("judge_id", "")
            decisive, pass_ = bool(o.get("decisive_failure", False)), bool(o.get("pass", o.get("pass_", False)))
        else:
            findings, jid = getattr(o, "findings", None), getattr(o, "judge_id", "")
            decisive, pass_ = bool(getattr(o, "decisive_failure", False)), bool(getattr(o, "pass_", False))
        for f in findings or []:
            lens_key = _categorize_finding_by_lens(str(f))
            lens_observations[lens_key].append({"judge_id": jid, "finding": str(f), "decisive": decisive, "pass": pass_})

    return {
        "rubric_version": FULL_RESUME_COHERENCE_RUBRIC_VERSION,
        "lenses_evaluated": list(LENS_DEFINITIONS),
        "lens_findings_count": {lens: len(items) for lens, items in lens_observations.items()},
        "lens_status": {
            lens: ("BLOCKER" if any(i["decisive"] for i in items) else ("OBSERVATION" if items else "CLEAR"))
            for lens, items in lens_observations.items()
        },
        "detailed_observations": lens_observations,
    }


def build_recruitment_readiness_scorecard(
    lens_analysis: dict[str, Any],
    criteria_scores: dict[str, float],
    full_resume_coherence_pass: bool,
) -> dict[str, Any]:
    lens_status = lens_analysis.get("lens_status") or {}
    lens_counts = lens_analysis.get("lens_findings_count") or {}
    has_blockers = any(lens_status.get(k) == "BLOCKER" for k in LENS_DEFINITIONS)
    lens_summaries = {
        k: {
            "name": LENS_METADATA[k]["name"],
            "status": lens_status.get(k, "CLEAR"),
            "finding_count": lens_counts.get(k, 0),
            "description": LENS_METADATA[k]["description"],
        }
        for k in LENS_DEFINITIONS
    }
    if full_resume_coherence_pass and not has_blockers:
        tier, verdict = "STRONG_HIRE_INTERVIEW_READY", "Clear signal: verified executive scope with zero critical blockers."
    elif full_resume_coherence_pass:
        tier, verdict = "QUALIFIED_WITH_FLAGGED_RISKS", "Quorum passed with non-fatal observations."
    else:
        tier, verdict = "NEEDS_REMEDIATION", "Resume failed coherence quorum or triggered critical atomic check blockers."
    return {
        "readiness_tier": tier,
        "full_pass": full_resume_coherence_pass,
        "mean_normalized_score": criteria_scores.get("mean_normalized_score", 0.0),
        "recruiter_verdict": verdict,
        "lens_summaries": lens_summaries,
    }


__all__ = [
    "FULL_RESUME_COHERENCE_RUBRIC",
    "FULL_RESUME_COHERENCE_RUBRIC_VERSION",
    "LENS_DEFINITIONS",
    "_categorize_finding_by_lens",
    "build_lens_analysis",
    "build_recruitment_readiness_scorecard",
]
