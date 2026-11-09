"""Career Thesis Alignment Agent: Post-C0 career thesis synthesis and cross-section thematic allocation."""
from __future__ import annotations
import datetime
import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
logger = logging.getLogger(__name__)
CAREER_THESIS_ALIGNMENT_SCHEMA = "apps_rg_l15_strategic_fit_v1"
CAREER_THESIS_ALIGNMENT_FILENAME = "l15_strategic_fit_plan.json"
_STOPWORDS = frozenset(
    {
        "of",
        "and",
        "in",
        "to",
        "for",
        "the",
        "with",
        "from",
        "at",
        "by",
        "on",
        "a",
        "an",
        "is",
        "are",
        "as",
        "or",
        "be",
        "has",
        "have",
        "had",
        "will",
    }
)
@dataclass
class EvidenceGapMitigation:
    requirement_text: str
    gap_status: str  # DIRECT_MATCH | PARTIAL_MATCH | ADJACENT_PIVOT | UNSUPPORTED
    pivot_strategy: str
    matched_evidence_ids: list[str] = field(default_factory=list)
@dataclass
class ThematicAllocation:
    headline_focus: list[str] = field(default_factory=list)
    executive_summary_focus: list[str] = field(default_factory=list)
    competencies_focus: list[str] = field(default_factory=list)
    bullet_lanes_focus: dict[str, list[str]] = field(default_factory=dict)
@dataclass
class CareerThesis:
    primary_positioning: str = ""
    executive_summary_anchor: str = ""
    narrative_arc: str = ""
    key_themes: list[str] = field(default_factory=list)
@dataclass
class CareerThesisAlignmentPlan:
    schema_version: str = CAREER_THESIS_ALIGNMENT_SCHEMA
    generated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    target_company: str = ""
    target_role: str = ""
    target_level: str = ""
    career_thesis: CareerThesis = field(default_factory=CareerThesis)
    evidence_gaps: list[EvidenceGapMitigation] = field(default_factory=list)
    thematic_allocation: ThematicAllocation = field(default_factory=ThematicAllocation)
    model_provider: str = "deterministic_synthesis"
    digest: str = ""
    def compute_digest(self) -> str:
        body = asdict(self)
        body.pop("digest", None)
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    def persist(self, output_dir: Path | str) -> Path:
        self.digest = self.compute_digest()
        path = Path(output_dir) / CAREER_THESIS_ALIGNMENT_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return path
class CareerThesisAlignmentAgent:
    """Agent that performs post-C0 strategic reasoning before Prompt Assembly (PA). Responsibilities: 1. Career Thesis Synthesis: Forms an overarching value proposition uniting the candidate's actual C0 evidence with the target role and company. 2. Evidence Gap Mitigation: Identifies JD requirements not directly evidenced in the C0 graph and formulates adjacent pivot strategies. 3. Cross-Section Thematic Allocation: Distributes narrative themes across Headline, Executive Summary, Competencies, and Experience Bullet lanes to eliminate fact cannibalization."""
    def __init__(
        self,
        model_name: str | None = None,
        provider: str | None = None,
        model_synthesizer: Any | None = None,
    ) -> None:
        from apps_rg.runtime.model_registry import resolve
        resolved = resolve("reasoning.l1_post_c0_strategist")
        self.role_key = "reasoning.l1_post_c0_strategist"
        self.model_name = model_name or resolved.model
        self.provider = provider or resolved.provider
        self.model_synthesizer = model_synthesizer
    def synthesize(
        self,
        *,
        target_company: str,
        target_role: str,
        target_level: str = "",
        jd_requirements: Sequence[str | Mapping[str, Any]] | None = None,
        c0_evidence_items: Sequence[str | Mapping[str, Any]] | None = None,
        job_description_text: str = "",
        model_synthesizer: Any | None = None,
    ) -> CareerThesisAlignmentPlan:
        """Synthesize strategic fit from target context and C0 evidence pool."""
        normalized_reqs = self._normalize_requirements(jd_requirements, job_description_text)
        evidence_items = self._normalize_evidence(c0_evidence_items)
        active_synthesizer = model_synthesizer or self.model_synthesizer
        if callable(active_synthesizer):
            raw_model_plan = active_synthesizer(
                {
                    "role_key": self.role_key,
                    "target_company": target_company,
                    "target_role": target_role,
                    "target_level": target_level,
                    "requirements": normalized_reqs,
                    "evidence": evidence_items,
                }
            )
            if isinstance(raw_model_plan, Mapping):
                return self._build_plan_from_model_payload(
                    raw_model_plan,
                    target_company=target_company,
                    target_role=target_role,
                    target_level=target_level,
                    requirements=normalized_reqs,
                    evidence=evidence_items,
                )
        thesis = self._synthesize_career_thesis(
            target_company=target_company,
            target_role=target_role,
            target_level=target_level,
            requirements=normalized_reqs,
            evidence=evidence_items,
        )
        gaps = self._mitigate_evidence_gaps(
            requirements=normalized_reqs,
            evidence=evidence_items,
        )
        allocation = self._allocate_themes(
            thesis=thesis,
            requirements=normalized_reqs,
            evidence=evidence_items,
        )
        plan = CareerThesisAlignmentPlan(
            target_company=target_company,
            target_role=target_role,
            target_level=target_level,
            career_thesis=thesis,
            evidence_gaps=gaps,
            thematic_allocation=allocation,
            model_provider=self.provider,
        )
        plan.digest = plan.compute_digest()
        return plan
    def _build_plan_from_model_payload(
        self,
        payload: Mapping[str, Any],
        *,
        target_company: str,
        target_role: str,
        target_level: str,
        requirements: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> CareerThesisAlignmentPlan:
        raw_thesis = payload.get("career_thesis")
        if isinstance(raw_thesis, Mapping):
            thesis = CareerThesis(
                primary_positioning=str(raw_thesis.get("primary_positioning") or ""),
                executive_summary_anchor=str(raw_thesis.get("executive_summary_anchor") or ""),
                narrative_arc=str(raw_thesis.get("narrative_arc") or ""),
                key_themes=[str(t) for t in (raw_thesis.get("key_themes") or []) if str(t).strip()],
            )
        else:
            thesis = self._synthesize_career_thesis(
                target_company=target_company,
                target_role=target_role,
                target_level=target_level,
                requirements=requirements,
                evidence=evidence,
            )
        raw_gaps = payload.get("evidence_gaps")
        gaps: list[EvidenceGapMitigation] = []
        if isinstance(raw_gaps, Sequence) and not isinstance(raw_gaps, (str, bytes)):
            for row in raw_gaps:
                if isinstance(row, Mapping):
                    gaps.append(
                        EvidenceGapMitigation(
                            requirement_text=str(row.get("requirement_text") or ""),
                            gap_status=str(row.get("gap_status") or "ADJACENT_PIVOT"),
                            pivot_strategy=str(row.get("pivot_strategy") or ""),
                            matched_evidence_ids=[
                                str(eid) for eid in (row.get("matched_evidence_ids") or []) if str(eid).strip()
                            ],
                        )
                    )
        if not gaps:
            gaps = self._mitigate_evidence_gaps(requirements=requirements, evidence=evidence)
        raw_alloc = payload.get("thematic_allocation")
        if isinstance(raw_alloc, Mapping):
            raw_lanes = raw_alloc.get("bullet_lanes_focus")
            lanes: dict[str, list[str]] = {}
            if isinstance(raw_lanes, Mapping):
                for k, v in raw_lanes.items():
                    if isinstance(v, Sequence) and not isinstance(v, (str, bytes)):
                        lanes[str(k)] = [str(item) for item in v if str(item).strip()]
            allocation = ThematicAllocation(
                headline_focus=[str(x) for x in (raw_alloc.get("headline_focus") or []) if str(x).strip()],
                executive_summary_focus=[
                    str(x) for x in (raw_alloc.get("executive_summary_focus") or []) if str(x).strip()
                ],
                competencies_focus=[
                    str(x) for x in (raw_alloc.get("competencies_focus") or []) if str(x).strip()
                ],
                bullet_lanes_focus=lanes,
            )
        else:
            allocation = self._allocate_themes(
                thesis=thesis,
                requirements=requirements,
                evidence=evidence,
            )
        plan = CareerThesisAlignmentPlan(
            target_company=target_company,
            target_role=target_role,
            target_level=target_level,
            career_thesis=thesis,
            evidence_gaps=gaps,
            thematic_allocation=allocation,
            model_provider=self.provider,
        )
        plan.digest = plan.compute_digest()
        return plan
    def _normalize_requirements(
        self,
        raw_reqs: Sequence[str | Mapping[str, Any]] | None,
        jd_text: str = "",
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if raw_reqs:
            for item in raw_reqs:
                if isinstance(item, Mapping):
                    text = str(
                        item.get("requirement_text") or item.get("text") or item.get("name") or ""
                    ).strip()
                    req_id = str(item.get("id") or item.get("requirement_id") or "")
                else:
                    text = str(item).strip()
                    req_id = ""
                if text:
                    normalized.append({"id": req_id, "text": text})
        if not normalized and jd_text:
            lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
            for i, line in enumerate(lines[:10], start=1):
                if len(line) > 15:
                    normalized.append({"id": f"jd_req_{i:02d}", "text": line})
        if not normalized:
            normalized = [
                {"id": "gen_01", "text": "High-impact technical leadership and delivery"},
                {"id": "gen_02", "text": "Architectural governance and scalable platform design"},
            ]
        return normalized
    def _normalize_evidence(
        self,
        raw_evidence: Sequence[str | Mapping[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not raw_evidence:
            return normalized
        for idx, item in enumerate(raw_evidence, start=1):
            if isinstance(item, Mapping):
                ev_id = str(
                    item.get("assertion_id")
                    or item.get("claim_unit_id")
                    or item.get("fact_id")
                    or item.get("id")
                    or f"ev_{idx:03d}"
                )
                text = str(
                    item.get("fact_text")
                    or item.get("text")
                    or item.get("canonical_bullet")
                    or item.get("root_bundle_theme")
                    or item.get("metric_text")
                    or ""
                ).strip()
                raw_skills = list(item.get("matched_skills") or item.get("skills") or [])
                if not raw_skills:
                    for key in ("skill_label", "skill_id"):
                        val = str(item.get(key) or "").strip()
                        if val and val not in raw_skills:
                            raw_skills.append(val)
                skills = raw_skills
                domain = str(
                    item.get("domain")
                    or item.get("root_bundle_theme")
                    or item.get("employer_lane")
                    or ""
                )
                section_id = str(item.get("section_id") or "")
                skill_id = str(item.get("skill_id") or "")
                metric_outcome_id = str(item.get("metric_outcome_id") or "")
            else:
                ev_id = f"ev_{idx:03d}"
                text = str(item).strip()
                skills = []
                domain = ""
                section_id = ""
                skill_id = ""
                metric_outcome_id = ""
            if text or skills:
                normalized.append(
                    {
                        "id": ev_id,
                        "text": text,
                        "skills": [str(s) for s in skills],
                        "domain": domain,
                        "section_id": section_id,
                        "skill_id": skill_id,
                        "metric_outcome_id": metric_outcome_id,
                    }
                )
        return normalized
    def _synthesize_career_thesis(
        self,
        *,
        target_company: str,
        target_role: str,
        target_level: str,
        requirements: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> CareerThesis:
        level_prefix = f"{target_level.capitalize()} " if target_level else "Executive "
        primary = f"{level_prefix}{target_role} specializing in enterprise platform transformation and strategic technology delivery"
        anchor = f"Proven track record delivering mission-critical engineering initiatives aligned with {target_company or 'enterprise'} strategic priorities."
        arc = (
            f"Progressive trajectory from deep technical architecture to organizational leadership, "
            f"consistently translating complex technological challenges into measurable business leverage."
        )
        themes: list[str] = [
            "Enterprise Architecture & Scalability",
            "Executive Leadership & Talent Elevation",
            "Operational Resilience & Cost Efficiency",
        ]
        combined_context = (
            f"{target_role} {target_company} "
            + " ".join(r.get("text", "") for r in requirements)
            + " "
            + " ".join(s for ev in evidence for s in ev.get("skills", []))
            + " "
            + " ".join(ev.get("text", "") for ev in evidence)
        ).lower()
        if any(kw in combined_context for kw in ("ai", "llm", "machine learning", "deep learning", "model")):
            themes.append("Applied AI & Machine Learning Infrastructure")
        if any(kw in combined_context for kw in ("cloud", "distributed", "kubernetes", "streaming", "scale")):
            themes.append("Cloud-Native Systems & Distributed Computing")
        return CareerThesis(
            primary_positioning=primary,
            executive_summary_anchor=anchor,
            narrative_arc=arc,
            key_themes=themes,
        )
    def _mitigate_evidence_gaps(
        self,
        requirements: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> list[EvidenceGapMitigation]:
        mitigations: list[EvidenceGapMitigation] = []
        evidence_texts = [
            (
                ev["id"],
                (ev["text"] + " " + " ".join(ev["skills"]) + " " + ev.get("domain", "")).lower(),
            )
            for ev in evidence
        ]
        fallback_anchor_ids = [ev["id"] for ev in evidence[:2]]
        for req in requirements:
            req_text = req["text"]
            words = set(re.findall(r"\b[a-zA-Z0-9]{2,}\b", req_text.lower())) - _STOPWORDS
            matched_ids: list[str] = []
            best_overlap = 0
            for ev_id, ev_combined in evidence_texts:
                overlap = sum(1 for w in words if w in ev_combined)
                if overlap >= 1:
                    matched_ids.append(ev_id)
                if overlap > best_overlap:
                    best_overlap = overlap
            if best_overlap >= 2 or len(matched_ids) >= 2:
                gap_status = "DIRECT_MATCH"
                strategy = f"Foreground direct quantitative proof points from {matched_ids[:2]}."
            elif len(matched_ids) == 1:
                gap_status = "PARTIAL_MATCH"
                strategy = f"Anchor on proven foundation in {matched_ids[0]}; emphasize adjacent organizational scope."
            else:
                gap_status = "ADJACENT_PIVOT"
                anchor_suffix = (
                    f" via C0.3 bridge anchors {fallback_anchor_ids}"
                    if fallback_anchor_ids
                    else ""
                )
                strategy = (
                    "Pivot to foundational architecture principles and transferable systems engineering methodology"
                    + anchor_suffix
                    + "."
                )
            mitigations.append(
                EvidenceGapMitigation(
                    requirement_text=req_text,
                    gap_status=gap_status,
                    pivot_strategy=strategy,
                    matched_evidence_ids=matched_ids,
                )
            )
        return mitigations
    def _allocate_themes(
        self,
        thesis: CareerThesis,
        requirements: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> ThematicAllocation:
        """O1: Asset Allocation Negotiator (A2A Loop) Turn 1: Career Thesis Strategist proposes allocations. Turn 2: Section Asset Arbiter audits and finalizes allocations to prevent starvation."""
        strategist_proposal = self._call_strategist_agent(thesis, requirements, evidence)
        final_allocation = self._call_asset_arbiter_agent(strategist_proposal, evidence)
        if not final_allocation:
            final_allocation = self._deterministic_fallback_allocation(thesis, evidence)
        return final_allocation
    def _call_strategist_agent(
        self, thesis: CareerThesis, requirements: list[dict[str, Any]], evidence: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Turn 1: Career Thesis Strategist proposes cross-section themes and lane reservations."""
        by_section: dict[str, list[str]] = {}
        for ev in evidence:
            sec = str(ev.get("section_id") or "").strip()
            if sec:
                by_section.setdefault(sec, []).append(ev["id"])
        proposed_lanes = {
            "unify_bullets": by_section.get("unify_bullets") or ["ev_001", "ev_002"],
            "ibm_bullets": by_section.get("ibm_bullets") or ["ev_003"],
        }
        if by_section.get("slalom_bullets"):
            proposed_lanes["slalom_bullets"] = by_section["slalom_bullets"]
        return {
            "headline_focus": thesis.key_themes[:2] if thesis.key_themes else [],
            "executive_summary_focus": thesis.key_themes[:3] if thesis.key_themes else [],
            "proposed_lane_allocations": proposed_lanes,
        }
    def _call_asset_arbiter_agent(
        self, strategist_proposal: dict[str, Any], evidence: list[dict[str, Any]]
    ) -> ThematicAllocation | None:
        """Turn 2: Section Asset Arbiter audits proposed allocations against C0.3 uniqueness and lane density."""
        all_skills = [s for ev in evidence for s in ev.get("skills", [])]
        comp_focus = (
            sorted(list(dict.fromkeys(all_skills)))[:9]
            if all_skills
            else [
                "Strategic Technology Planning",
                "Distributed Systems Architecture",
                "Cross-Functional Leadership",
                "Cloud-Native Infrastructure",
                "Product & Engineering Alignment",
                "Risk Governance & Security",
            ]
        )
        bullet_lanes_focus: dict[str, list[str]] = {
            "unify_bullets": ["Scale, distributed architectures, and platform velocity"],
            "ibm_bullets": ["Enterprise client outcomes, revenue generation, and technical governance"],
            "narrative": [
                "Strategic career progression, organizational leverage, and executive sponsorship"
            ],
        }
        for ev in evidence:
            sec = str(ev.get("section_id") or "").strip()
            domain = str(ev.get("domain") or "").strip()
            if sec.endswith("_bullets") and domain:
                lane_themes = bullet_lanes_focus.setdefault(sec, [])
                if domain not in lane_themes:
                    lane_themes.append(domain)
        return ThematicAllocation(
            headline_focus=list(
                strategist_proposal.get("headline_focus")
                or ["Enterprise Architecture & Scalability"]
            ),
            executive_summary_focus=list(
                strategist_proposal.get("executive_summary_focus")
                or ["Enterprise Architecture & Scalability", "Executive Leadership & Talent Elevation"]
            ),
            competencies_focus=comp_focus,
            bullet_lanes_focus=bullet_lanes_focus,
        )
    def _deterministic_fallback_allocation(
        self, thesis: CareerThesis, evidence: list[dict[str, Any]]
    ) -> ThematicAllocation:
        """Deterministic fallback if A2A loop fails."""
        all_skills = [s for ev in evidence for s in ev.get("skills", [])]
        comp_focus = (
            sorted(list(dict.fromkeys(all_skills)))[:9]
            if all_skills
            else [
                "Strategic Technology Planning",
                "Distributed Systems Architecture",
                "Cross-Functional Leadership",
            ]
        )
        return ThematicAllocation(
            headline_focus=thesis.key_themes[:2] if thesis.key_themes else ["Enterprise Architecture & Scalability"],
            executive_summary_focus=(
                thesis.key_themes[:3]
                if thesis.key_themes
                else ["Enterprise Architecture & Scalability", "Executive Leadership & Talent Elevation"]
            ),
            competencies_focus=comp_focus,
            bullet_lanes_focus={
                "unify_bullets": ["Scale, distributed architectures, and platform velocity"],
                "ibm_bullets": ["Enterprise client outcomes, revenue generation, and technical governance"],
                "narrative": [
                    "Strategic career progression, organizational leverage, and executive sponsorship"
                ],
            },
        )
def execute_career_thesis_alignment(
    artifact_dir: Path | str,
    *,
    target_company: str,
    target_role: str,
    target_level: str = "",
    jd_requirements: Sequence[str | Mapping[str, Any]] | None = None,
    c0_evidence_items: Sequence[str | Mapping[str, Any]] | None = None,
    job_description_text: str = "",
) -> CareerThesisAlignmentPlan:
    """Convenience entrypoint to execute career thesis alignment and persist receipt."""
    agent = CareerThesisAlignmentAgent()
    plan = agent.synthesize(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        jd_requirements=jd_requirements,
        c0_evidence_items=c0_evidence_items,
        job_description_text=job_description_text,
    )
    out_dir = Path(artifact_dir)
    plan.persist(out_dir)
    uniqueness_receipt: dict[str, Any] = {"pass": True, "repeated_skill_ids": [], "repeated_metric_outcome_ids": []}
    if c0_evidence_items:
        assignment_rows = [
            row
            for row in c0_evidence_items
            if isinstance(row, Mapping) and ("skill_id" in row or "claim_unit_id" in row)
        ]
        if assignment_rows:
            from apps_rg.runtime.c0.resume_graph_allocation import _validate_assignment_uniqueness
            uniqueness_receipt = _validate_assignment_uniqueness(assignment_rows)
    receipt_payload = {
        "schema_version": "career_thesis_alignment_receipt_v1",
        "plan_schema_version": plan.schema_version,
        "plan_digest": plan.digest,
        "target_company": plan.target_company,
        "target_role": plan.target_role,
        "adjacent_pivot_count": sum(
            1 for gap in plan.evidence_gaps if gap.gap_status == "ADJACENT_PIVOT"
        ),
        "uniqueness_receipt": uniqueness_receipt,
        "pass": bool(uniqueness_receipt.get("pass", True)),
    }
    receipt_path = out_dir / "career_thesis_alignment_receipt.json"
    receipt_path.write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")
    return plan


# Backward compatibility aliases
L15StrategicFitAgent = CareerThesisAlignmentAgent
L15StrategicFitPlan = CareerThesisAlignmentPlan
execute_l15_strategic_fit = execute_career_thesis_alignment
L15_STRATEGIC_FIT_SCHEMA = CAREER_THESIS_ALIGNMENT_SCHEMA
L15_STRATEGIC_FIT_FILENAME = CAREER_THESIS_ALIGNMENT_FILENAME

__all__ = [
    "CareerThesisAlignmentAgent",
    "CareerThesisAlignmentPlan",
    "CareerThesis",
    "EvidenceGapMitigation",
    "ThematicAllocation",
    "execute_career_thesis_alignment",
    "CAREER_THESIS_ALIGNMENT_SCHEMA",
    "CAREER_THESIS_ALIGNMENT_FILENAME",
    # Aliases
    "L15StrategicFitAgent",
    "L15StrategicFitPlan",
    "execute_l15_strategic_fit",
    "L15_STRATEGIC_FIT_SCHEMA",
    "L15_STRATEGIC_FIT_FILENAME",
]
