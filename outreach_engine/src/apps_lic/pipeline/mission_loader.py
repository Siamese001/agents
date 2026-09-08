"""Polymorphic Mission and Opportunity Loader for outreach_engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)


class MissionLoader:
    """Loads and standardizes candidate profiles and target opportunities."""

    @staticmethod
    def load_from_file(brief_path: str | Path) -> Tuple[CandidateProfile, TargetOpportunity]:
        path = Path(brief_path)
        if not path.is_file():
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            cand = repo_root / path
            if cand.is_file():
                path = cand
            else:
                raise FileNotFoundError(f"Brief/mission file not found: {brief_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return MissionLoader.load_from_dict(data, default_id=path.stem)

    @staticmethod
    def load_from_dict(data: Dict[str, Any], default_id: str = "mission_01") -> Tuple[CandidateProfile, TargetOpportunity]:
        # Structure 1: Full mission fixture (e.g. charles_truist_mission.json)
        if "sender_profile" in data and "recipient_profile" in data:
            sp = data["sender_profile"]
            rp = data["recipient_profile"]
            jd = data.get("job_description", {})

            candidate = CandidateProfile(
                candidate_id=f"cand_{default_id}",
                full_name=sp.get("name", "Executive Candidate"),
                target_title=sp.get("title", jd.get("title", "Engineering Leader")),
                executive_summary=sp.get("background", "Senior enterprise systems leader."),
                verified_facts=[
                    CandidateFact(
                        fact_id="fact_01",
                        category="architecture",
                        statement="architected layered agentic systems (L0 routing through L6 observability) with AST dependency governance",
                    ),
                    CandidateFact(
                        fact_id="fact_02",
                        category="delivery",
                        statement="delivered multi-MCP enterprise agentic tooling for frontline banking care operations",
                    ),
                ],
                key_competencies=["Agentic AI", "Enterprise Architecture", "LLM Guardrails", "HITL Systems"],
            )

            company_name = rp.get("company") or jd.get("company") or "Target Company"
            company_context = jd.get("company_context", "")

            priorities = []
            if jd.get("summary"):
                priorities.append(jd["summary"])
            if jd.get("responsibilities"):
                priorities.extend(jd["responsibilities"][:2])

            opportunity = TargetOpportunity(
                opportunity_id=f"opp_{default_id}",
                company_name=company_name,
                role_title=jd.get("title", "Head of Enterprise Strategy"),
                industry="Banking & Financial Services",
                recipient_name=rp.get("name", "Executive Partner"),
                recipient_title=rp.get("title", "Executive Leader"),
                recipient_class=RecipientClass.EXECUTIVE_PEER,
                relationship_distance=RelationshipDistance.COLD,
                strategic_priorities=priorities,
                briefing_text=company_context,
            )
            return candidate, opportunity

        # Structure 2: Simple brief (e.g. truist_pascal_brief.json)
        if "recipient_company" in data:
            candidate = CandidateProfile(
                candidate_id=f"cand_{default_id}",
                full_name=data.get("candidate_name", "Alex Mercer"),
                target_title=data.get("target_role", "VP of Engineering"),
                executive_summary="Senior enterprise technology executive.",
                verified_facts=[
                    CandidateFact(
                        fact_id="fact_01",
                        category="scale",
                        statement="scaled enterprise core platform processing high-volume financial transactions",
                    )
                ],
            )
            opportunity = TargetOpportunity(
                opportunity_id=f"opp_{default_id}",
                company_name=data.get("recipient_company", "Target Company"),
                role_title=data.get("target_role", "Engineering Leader"),
                industry="Financial Services",
                recipient_name=data.get("recipient_name", "Hiring Leader"),
                recipient_title=data.get("recipient_title", "Head of Engineering"),
                recipient_class=RecipientClass.HIRING_MANAGER,
                relationship_distance=RelationshipDistance.COLD,
                strategic_priorities=["Core platform modernization"],
                briefing_text=data.get("freeform_text", ""),
            )
            return candidate, opportunity

        # Structure 3: apps_research handoff envelope format
        if "payload" in data and "company_brief" in data.get("payload", {}):
            payload = data["payload"]
            candidate = CandidateProfile(
                candidate_id=f"cand_{default_id}",
                full_name="Alex Mercer",
                target_title="VP of Engineering",
                executive_summary="Enterprise engineering leader.",
                verified_facts=[
                    CandidateFact(
                        fact_id="fact_01",
                        category="scale",
                        statement="scaled core enterprise platforms with 99.995% reliability",
                    )
                ],
            )
            opportunity = TargetOpportunity(
                opportunity_id=f"opp_{default_id}",
                company_name=payload.get("company_brief", "Target Enterprise"),
                role_title="Head of Engineering",
                industry="Enterprise Technology",
                recipient_name="Talent Lead",
                recipient_title="Director of Talent",
                recipient_class=RecipientClass.TALENT_PARTNER,
                relationship_distance=RelationshipDistance.COLD,
                strategic_priorities=payload.get("role_areas_of_focus", []) or payload.get("industry_trends", []),
                briefing_text=payload.get("company_brief", ""),
            )
            return candidate, opportunity

        raise ValueError("Unrecognized brief structure in data payload")


__all__ = ["MissionLoader"]
