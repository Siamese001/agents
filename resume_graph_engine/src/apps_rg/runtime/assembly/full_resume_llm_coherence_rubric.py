"""Full-resume LLM coherence review rubric, lenses, and categorization (apps_rg)."""
from __future__ import annotations

from typing import Any, Sequence

FULL_RESUME_COHERENCE_RUBRIC_VERSION = "full_resume_llm_coherence_v3"

LENS_DEFINITIONS: tuple[str, ...] = (
    "narrative_coherence",
    "hr_recruiter_first_impression",
    "ats_semantic_taxonomy",
    "jd_briefing_resonance",
    "knockout_and_risk_vectors",
    "altitude_and_band_calibration",
)


def _categorize_finding_by_lens(finding: str) -> str:
    low = finding.lower()
    if any(
        k in low
        for k in (
            "narrative",
            "coherence",
            "end-to-end",
            "section ownership",
            "cross-section",
            "storyline",
        )
    ):
        return "narrative_coherence"
    if any(
        k in low
        for k in (
            "6-second",
            "recruiter",
            "scannab",
            "visual",
            "first impression",
            "white-space",
            "headline",
            "skimmab",
            "readability",
            "hierarchy",
        )
    ):
        return "hr_recruiter_first_impression"
    if any(
        k in low
        for k in (
            "ats",
            "taxonomy",
            "cluster",
            "nomenclature",
            "parseab",
            "keyword stuffing",
            "laundry",
            "competenc",
        )
    ):
        return "ats_semantic_taxonomy"
    if any(
        k in low
        for k in (
            "briefing",
            "jd",
            "job description",
            "strategic alignment",
            "target role",
            "market bet",
            "co-sell",
            "role fit",
        )
    ):
        return "jd_briefing_resonance"
    if any(
        k in low
        for k in (
            "knockout",
            "risk",
            "red flag",
            "believab",
            "vanity",
            "unverified",
            "attribution",
            "exaggerat",
            "unsupported",
            "gap",
        )
    ):
        return "knockout_and_risk_vectors"
    if any(
        k in low
        for k in (
            "altitude",
            "band",
            "seniority",
            "svp",
            "cto",
            "leveling",
            "downgrade",
            "junior",
            "ic ",
            "scope",
        )
    ):
        return "altitude_and_band_calibration"
    return "narrative_coherence"


def build_lens_analysis(judge_outputs: Sequence[Any]) -> dict[str, Any]:
    """Aggregate per-lens observations and blockers across judge outputs."""
    lens_observations: dict[str, list[dict[str, Any]]] = {
        lens: [] for lens in LENS_DEFINITIONS
    }
    for o in judge_outputs:
        findings = getattr(o, "findings", None)
        if isinstance(o, dict):
            findings = o.get("findings")
            jid = o.get("judge_id", "")
            decisive = bool(o.get("decisive_failure", False))
            pass_ = bool(o.get("pass", o.get("pass_", False)))
        else:
            jid = getattr(o, "judge_id", "")
            decisive = bool(getattr(o, "decisive_failure", False))
            pass_ = bool(getattr(o, "pass_", False))

        for f in findings or []:
            lens_key = _categorize_finding_by_lens(str(f))
            lens_observations[lens_key].append(
                {
                    "judge_id": jid,
                    "finding": str(f),
                    "decisive": decisive,
                    "pass": pass_,
                }
            )

    return {
        "rubric_version": FULL_RESUME_COHERENCE_RUBRIC_VERSION,
        "lenses_evaluated": list(LENS_DEFINITIONS),
        "lens_findings_count": {
            lens: len(items) for lens, items in lens_observations.items()
        },
        "lens_status": {
            lens: (
                "BLOCKER"
                if any(item["decisive"] for item in items)
                else ("OBSERVATION" if items else "CLEAR")
            )
            for lens, items in lens_observations.items()
        },
        "detailed_observations": lens_observations,
    }


FULL_RESUME_COHERENCE_RUBRIC = """
You are evaluating a COMPLETE assembled executive resume (all sections) for release coherence, talent acquisition resonance, and strategic target alignment.
Deterministic X2 gates are authoritative for hard proof; your verdict informs full_resume_coherence_pass only when aggregated with quorum.

Return JSON only with: score_scale, score, threshold, pass, decisive_failure, findings, cited_sentence_indexes, remediation_suggestions.

EVALUATION LENSES & CORE DIMENSIONS:
Evaluate the resume across these six distinct recruitment, screening, and strategic alignment lenses:

1. narrative_coherence (Executive Leadership Storyline):
   - End-to-end alignment: headline -> executive summary -> professional experience -> competencies tell one coherent, authoritative SVP/CTO/Platform story.
   - Cross-section consistency: titles, dates, metrics, employers, and scope remain consistent across sections.
   - Section ownership: credentials appear ONLY under CERTIFICATIONS & CREDENTIALS — never duplicated inside competencies.

2. hr_recruiter_first_impression (6-Second Initial Screen):
   - Visual rhythm, scannability, and cognitive ease: clear section hierarchy, no wall-of-text fatigue.
   - Immediate value proposition: does the headline + executive summary instantly signal top-tier leadership caliber?
   - Marquee proof points: key achievements and enterprise scale are immediately legible within a 6-second recruiter skim.

3. ats_semantic_taxonomy (Machine Parseability & Structure):
   - Standard domain nomenclature: technologies, methodologies, and platforms follow established industry taxonomies.
   - Executive capability clustering: competencies organized in structured clusters (3–6 high-signal items per category), not unclustered keyword laundry.
   - Non-duplication: competencies do not restate bullets or executive summary verbatim.

4. jd_briefing_resonance (Strategic Alignment without Claim Invention):
   - Strategic alignment: resonance with the company's enterprise challenges, platform architecture, co-sell motions, and transformation imperatives outlined in the JD briefing.
   - TARGETING CONTEXT ONLY: JD briefing informs strategic framing and altitude, NEVER candidate proof.
   - Flag unsupported claims: reject any JD-only or briefing-only phrasing presented as candidate proof without backing in the candidate evidence packet.

5. knockout_and_risk_vectors (Credibility & Skeptical Screener):
   - Metric believability & attribution: quantifiable metrics are grounded in believable organizational scale (e.g., team size, budget, revenue impact).
   - Absence of ungrounded vanity claims: no defensive phrasing, exaggerated solo-attribution, or unbacked buzzwords.
   - Trajectory integrity: career progression is stable, logical, and senior.

6. altitude_and_band_calibration (Executive Leveling):
   - Calibration to target executive band: platform architecture, GTM alliance co-sell, runtime governance, model evaluation frameworks, and enterprise portfolio leadership matching executive requirements.
   - No IC downgrade: do NOT penalize maintaining SVP engineering leadership rather than an individual contributor (IC) junior researcher persona. Downward title/scope distortion is strictly forbidden.

CANDIDATE_EVIDENCE_PACKET is candidate proof, not targeting context. Graph IDs and source-fact IDs in that packet are the claim-authority spine. A globally unique metric or skill may be intentionally allocated to one rendered section; do not call it unsupported merely because the same wording is not duplicated in professional experience. Still flag a claim when the packet provides no candidate-evidence binding or when the rendered claim conflicts with its evidence.

AUTHORITATIVE CANDIDATE PROFILE & TARGETING BAR:
- The candidate is an executive technology leader (SVP Engineering / CTO / Partner).
- When targeting technical, platform, or applied research roles (such as "Applied AI Research Engineer" at Anthropic or similar frontier labs), the candidate's executive platform posture (platform architecture, GTM alliance co-sell, runtime governance telemetry, model eval frameworks, and enterprise portfolio expansion) is authoritative, intentional, and required.
- The Anthropic Applied AI role explicitly specifies owning the technical<>GTM handshake, enterprise reference architectures, and translating customer adoption into research/product feedback.
- For dimension `ats_alignment_without_keyword_stuffing` and `role_fit`: Do NOT mark TARGET_ROLE_MISMATCH or penalize the resume for maintaining executive SVP engineering leadership rather than an individual contributor (IC) junior researcher persona. Downward title/scope distortion or asking for an IC hands-on research downgrade is explicitly forbidden by the `seniority_downgrade` blocker. Evaluate role fit on how well executive platform/GTM leadership meets the enterprise scale, governance, and adoption scope of the role.
- For dimension `resume_voice`: Technical platform terminology (e.g., runtime governance telemetry, control planes, model evaluation frameworks) is expected at the SVP Engineering bar; do not cite it as negative jargon density unless genuinely vacuous buzzwords.

Lines marked [NOT COMPLETED: <section> — <reason>] are intentional gaps — do not score as prose; judge flow/overlap only on completed sections.

Decisive failure (blockers):
- Credential names duplicated in ENGINEERING & PLATFORM COMPETENCIES
- JD/briefing language used as primary proof for unsupported skills
- Severe incoherence or seniority downgrade vs SVP engineering/platform bar
- Competencies section is keyword stuffing with no executive clusters
""".strip()

__all__ = [
    "FULL_RESUME_COHERENCE_RUBRIC",
    "FULL_RESUME_COHERENCE_RUBRIC_VERSION",
    "LENS_DEFINITIONS",
    "_categorize_finding_by_lens",
    "build_lens_analysis",
]
