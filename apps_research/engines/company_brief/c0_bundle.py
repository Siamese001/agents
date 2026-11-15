"""C0 evidence bundle construction, PA gate evaluation, and brief assembly mixin."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from apps_research.engines.company_brief.shared import _cbe


class _CompanyBriefC0BundleMixin:
    """Provides JD context resolution, 7-object C0 bundle assembly, and PA gate evaluation."""

    @staticmethod
    def _resolve_jd_context(input_data: Any) -> Dict[str, Any]:
        """Extract and normalise JD context from input_data.

        Accepts either a plain dict under 'jd_context' key or a
        'jd_anchor' path. Computes jd_content_hash when absent.
        """
        jd: Any = None
        if isinstance(input_data, dict):
            jd = input_data.get("jd_context")
        elif hasattr(input_data, "jd_context"):
            jd = getattr(input_data, "jd_context", None)

        if not isinstance(jd, dict) or not jd:
            return {}

        result: Dict[str, Any] = dict(jd)
        if not result.get("jd_content_hash"):
            content = str(result.get("content") or result.get("jd_ref") or "")
            if content:
                result["jd_content_hash"] = "sha256-" + hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest()[:16]
        return result

    def _build_c0_bundle(
        self,
        *,
        topic: str,
        depth_profile: str,
        profile_cfg: Dict[str, Any],
        findings: Dict[str, str],
        synthesis: Dict[str, Any],
        jd_context: Dict[str, Any],
        retrieval_contract: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build the 7-object C0 output bundle from research findings + synthesis."""
        from apps_research.integrations.search_retrieval import retrieval_config_snapshot  # noqa: PLC0415
        from apps_research.prompt_assembly.consumer_briefs import extract_jd_text  # noqa: PLC0415
        from apps_research.reasoning.research_multi_agent import run_dialectical_evidence_triad

        describe_contract = _cbe("describe_jd_retrieval_contract")
        profile_req_families = _cbe("_PROFILE_REQUIRED_FAMILIES")

        contract = retrieval_contract or describe_contract(jd_context or None)
        required_families = list(
            dict.fromkeys(
                list(profile_req_families.get(depth_profile, []))
                + list(contract.get("required_evidence_families", []))
            )
        )
        retrieval_snapshot = retrieval_config_snapshot(query_families=list(findings.keys()))
        jd_present = bool(jd_context)
        jd_text = extract_jd_text(jd_context=jd_context).strip() if jd_present else ""
        direct_jd_role_context = bool(jd_text)

        coverage_entries: List[Dict[str, Any]] = []
        covered = 0
        for fam in required_families:
            blob = findings.get(fam, "")
            has_content = bool(blob and blob.strip())
            has_direct_jd_support = fam == "role_context" and direct_jd_role_context
            is_covered = has_content or has_direct_jd_support
            if is_covered:
                covered += 1
            coverage_entries.append(
                {
                    "family": fam,
                    "covered": is_covered,
                    "source_count": (
                        len(blob.split("\n"))
                        if has_content
                        else (1 if has_direct_jd_support else 0)
                    ),
                    "support_kind": (
                        "retrieved_web"
                        if has_content
                        else ("direct_jd_document" if has_direct_jd_support else "missing")
                    ),
                }
            )

        jd_req_families = ["role_context", "tech_stack_and_tools"] if jd_present else []
        jd_covered = sum(
            1
            for entry in coverage_entries
            if entry["family"] in jd_req_families and entry["covered"]
        )
        overall_coverage_score = covered / len(required_families) if required_families else 0.0
        jd_coverage_score = jd_covered / len(jd_req_families) if jd_req_families else 0.0
        briefing_coverage_matrix = {
            "profile_id": depth_profile,
            "families": coverage_entries,
            "overall_coverage_score": round(overall_coverage_score, 4),
            "jd_coverage_score": round(jd_coverage_score, 4),
            "recruiter_outreach_overlay_present": False,
        }

        all_urls: List[str] = []
        all_content_lines: List[str] = []
        for blob in findings.values():
            for line in blob.split("\n"):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                all_content_lines.append(stripped_line)
                if stripped_line.startswith("http"):
                    all_urls.append(stripped_line)

        total_url_sources = len(set(all_urls))
        total_citation_anchors = len(all_urls) if all_urls else len(all_content_lines)
        total_sources = total_url_sources if total_url_sources > 0 else covered
        source_portfolio_summary = {
            "total_final_sources": total_sources,
            "total_citation_anchors": total_citation_anchors,
            "authoritative_anchor_present": total_sources > 0,
            "source_urls": sorted(set(all_urls))[:50],
            "direct_jd_source_present": direct_jd_role_context,
            "direct_jd_content_hash": (
                str(jd_context.get("jd_content_hash") or "") if direct_jd_role_context else ""
            ),
        }

        unsupported = max(0, len(required_families) - covered)
        claim_evidence_map = {
            "total_claims": len(required_families),
            "supported_count": covered,
            "unsupported_direct_evidence_count": unsupported,
            "unsupported_claim_count": unsupported,
        }

        dialectical_claims: List[Dict[str, Any]] = [
            {"claim_id": f"{fam_key}_{line_idx + 1}", "family": fam_key, "text": line.strip()}
            for fam_key, blob in findings.items()
            for line_idx, line in enumerate(str(blob or "").splitlines())
            if line.strip() and not line.strip().startswith("http")
        ]
        triad_result = run_dialectical_evidence_triad(dialectical_claims)
        contradiction_matrix = {
            "schema_version": "c0_contradiction_matrix.v1",
            "total_contradictions": int(triad_result.get("total_contradictions", 0)),
            "contradictions_detected": int(triad_result.get("contradictions_detected", 0)),
            "unresolved_critical": int(triad_result.get("unresolved_critical", 0)),
            "resolved_count": int(triad_result.get("resolved_count", 0)),
            "resolutions": list(triad_result.get("resolutions", [])),
        }

        fresh_summary = triad_result.get("freshness_summary", {})
        freshness_report = {
            "schema_version": "c0_freshness_report.v1",
            "policy_id": f"freshness::apps_research::{depth_profile.split('_')[-1].lower()}",
            "sources": list(fresh_summary.get("stale_sources", [])),
            "stale_excluded_count": int(fresh_summary.get("stale_excluded_count", 0)),
            "gate_fail_triggered": False,
            "stale_section_ids": list(fresh_summary.get("stale_section_ids", [])),
        }

        gap_families = [str(entry["family"]) for entry in coverage_entries if not entry["covered"]]
        section_gap_report = {
            "gap_families": gap_families,
            "gap_count": len(gap_families),
        }

        synthesis_guidance: Dict[str, Any] = {
            "depth_profile": depth_profile,
            "gate_verdict": "PENDING",
            "gate_caveat": "",
            "degraded_packet_reason": "",
            "ordered_sections": required_families,
            "jd_evidence_intents": list(contract.get("intent_ids", [])),
            "jd_required_evidence_families": list(contract.get("required_evidence_families", [])),
            "direct_jd_evidence_families": ["role_context"] if direct_jd_role_context else [],
        }
        if jd_present:
            synthesis_guidance["jd_focal_angle"] = jd_context.get("jd_ref", "")
            synthesis_guidance["apps_rg_downstream_fields"] = {
                "jd_ref": jd_context.get("jd_ref"),
                "jd_content_hash": jd_context.get("jd_content_hash"),
                "responsibilities": jd_context.get("responsibilities", []),
            }

        bundle: Dict[str, Any] = {
            "briefing_coverage_matrix": briefing_coverage_matrix,
            "source_portfolio_summary": source_portfolio_summary,
            "claim_evidence_map": claim_evidence_map,
            "contradiction_matrix": contradiction_matrix,
            "freshness_report": freshness_report,
            "section_gap_report": section_gap_report,
            "retrieval_config": retrieval_snapshot,
            "jd_retrieval_contract": contract,
            "synthesis_guidance": synthesis_guidance,
        }
        if jd_present:
            bundle["jd_context"] = dict(jd_context)
        return bundle

    def _evaluate_c0_pa_gate(
        self,
        *,
        c0_bundle: Dict[str, Any],
        depth_profile: str,
    ) -> tuple[str, str, str]:
        """Evaluate the C0 PA gate; return (verdict, caveat, degraded_reason).

        Verdict values: 'PASS', 'WEAK_WITH_CAVEATS', 'FAIL'.
        """
        depth_profiles = _cbe("_DEPTH_PROFILES")
        profile_cfg = depth_profiles.get(
            depth_profile, depth_profiles["COMPANY_BRIEF_STANDARD"]
        )
        min_sources = profile_cfg["min_sources"]
        coverage_floor = profile_cfg["coverage_floor"]
        gate_weak_floor = profile_cfg["gate_weak_floor"]

        sps = c0_bundle.get("source_portfolio_summary", {})
        total_sources = sps.get("total_final_sources", 0)
        authoritative = sps.get("authoritative_anchor_present", False)

        bcm = c0_bundle.get("briefing_coverage_matrix", {})
        coverage_score = bcm.get("overall_coverage_score", 0.0)

        contradiction_matrix = c0_bundle.get("contradiction_matrix", {})
        unresolved_critical = contradiction_matrix.get("unresolved_critical", 0)

        freshness = c0_bundle.get("freshness_report", {})
        freshness_fail = freshness.get("gate_fail_triggered", False)

        cem = c0_bundle.get("claim_evidence_map", {})
        unsupported = cem.get("unsupported_direct_evidence_count", 0)

        if total_sources < min_sources:
            return (
                "FAIL",
                "",
                f"Insufficient sources: {total_sources} found, {min_sources} required for {depth_profile}.",
            )
        if unresolved_critical > 0:
            return ("FAIL", "", f"Unresolved critical contradictions: {unresolved_critical}.")
        if freshness_fail:
            return ("FAIL", "", "Freshness gate triggered.")

        if coverage_score >= coverage_floor and authoritative and unsupported == 0:
            return ("PASS", "", "")

        if coverage_score >= gate_weak_floor:
            caveats = []
            if coverage_score < coverage_floor:
                caveats.append(f"coverage {coverage_score:.0%} below floor {coverage_floor:.0%}")
            if not authoritative:
                caveats.append("no authoritative anchor")
            if unsupported > 0:
                caveats.append(f"{unsupported} unsupported claims")
            return ("WEAK_WITH_CAVEATS", "; ".join(caveats), "")

        return ("FAIL", "", f"Coverage {coverage_score:.0%} below weak floor {gate_weak_floor:.0%}.")

    @staticmethod
    def _targeting_c0_gate_allows_handoff(
        *,
        c0_bundle: Dict[str, Any],
        gate_verdict: str,
    ) -> bool:
        """Return whether a C0 result is safe to hand to the Apps RG target lane."""
        verdict = str(gate_verdict or "").upper()
        if verdict == "PASS":
            return True
        if verdict != "WEAK_WITH_CAVEATS":
            return False

        coverage_matrix = c0_bundle.get("briefing_coverage_matrix")
        contract = c0_bundle.get("jd_retrieval_contract")
        source_summary = c0_bundle.get("source_portfolio_summary")
        contradictions = c0_bundle.get("contradiction_matrix")
        freshness = c0_bundle.get("freshness_report")
        if not all(
            isinstance(value, dict)
            for value in (coverage_matrix, contract, source_summary, contradictions, freshness)
        ):
            return False

        required_families = {
            str(family).strip()
            for family in contract.get("required_evidence_families", [])
            if str(family).strip()
        }
        if not required_families:
            return False
        covered_families = {
            str(entry.get("family") or "").strip()
            for entry in coverage_matrix.get("families", [])
            if isinstance(entry, dict) and bool(entry.get("covered"))
        }
        if "role_context" not in covered_families:
            return False
        if not required_families.issubset(covered_families):
            return False
        if not bool(source_summary.get("authoritative_anchor_present")):
            return False
        if int(source_summary.get("total_final_sources") or 0) < 1:
            return False
        if int(contradictions.get("unresolved_critical") or 0) > 0:
            return False
        if bool(freshness.get("gate_fail_triggered")):
            return False
        return True

    @staticmethod
    def _assemble_brief(*, topic: str, synthesis: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "company": topic,
            "fetched_at": now,
            "source": "apps_research",
            "freshness_ttl_days": 30,
            "overview": {
                "tagline": synthesis.get("tagline", topic),
                "founded": synthesis.get("founded"),
                "size_band": synthesis.get("size_band"),
                "ownership": synthesis.get("ownership"),
                "headquarters": synthesis.get("headquarters"),
                "core_offerings": synthesis.get("core_offerings", []) or [],
            },
            "company_archetype": synthesis.get("company_archetype"),
            "company_dna": synthesis.get("company_dna", {}) or {},
            "strategic_priorities": synthesis.get("strategic_priorities", []) or [],
            "customer_profile": {
                "verticals": synthesis.get("verticals", []) or [],
                "buyer_titles": synthesis.get("buyer_titles", []) or [],
                "typical_engagement_size": synthesis.get("typical_engagement_size"),
            },
            "tech_stack_signals": synthesis.get("tech_stack_signals", []) or [],
            "commercial_motion": synthesis.get("commercial_motion", []) or [],
            "partner_ecosystem": synthesis.get("partner_ecosystem", []) or [],
            "adoption_motion": synthesis.get("adoption_motion", []) or [],
            "leadership": synthesis.get("leadership", []) or [],
            "competitive_set": synthesis.get("competitive_set", []) or [],
            "recent_moves": synthesis.get("recent_moves", []) or [],
            "language_to_mirror": synthesis.get("language_to_mirror", []) or [],
            "language_to_avoid": synthesis.get("language_to_avoid", []) or [],
        }


__all__ = ["_CompanyBriefC0BundleMixin"]
