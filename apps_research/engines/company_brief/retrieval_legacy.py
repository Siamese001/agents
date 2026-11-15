"""Legacy and adaptive non-V2 retrieval mixin for CompanyBriefEngine."""
from __future__ import annotations

from typing import Dict

from apps_research.engines.company_brief.shared import _cbe


class _CompanyBriefRetrievalLegacyMixin:
    """Provides standard facet retrieval and non-V2 adaptive family fan-out retrieval."""

    def _run_research(self, *, topic: str, depth: str) -> Dict[str, str]:
        """Best-effort SearXNG research per facet.

        Returns a dict {facet_name: text_blob}. Missing SearXNG configuration
        fails closed instead of substituting a synthetic brief.
        """
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        findings: Dict[str, str] = {f: "" for f, _ in self._FACET_QUERIES}
        try:
            from apps_research.integrations.search_retrieval import retrieve
        except ImportError as exc:
            self.logger.warning(
                "[CompanyBriefEngine] search_retrieval unavailable; failing closed: %s",
                exc,
            )
            retrieve = None

        max_queries = {"shallow": 3, "standard": 6, "deep": 10}.get(depth, 6)

        for facet, q_template in self._FACET_QUERIES[:max_queries]:
            if retrieve is None:
                break
            query = q_template.format(company=topic)
            try:
                docs = retrieve(query, top_k=5)
                snippets = [d.snippet for d in docs if d.snippet]
                findings[facet] = "\n".join(snippets)[:4000]
            except Exception as exc:  # guardian: allow-broad-exception -- SearXNG HTTP errors are heterogeneous; per-facet fail-soft preserves partial brief
                self.logger.warning("[CompanyBriefEngine] SearXNG query failed (%s): %s", facet, exc)
        if not any((blob or "").strip() for blob in findings.values()):
            raise unavailable_err(
                f"{topic}: SearXNG research returned no grounded findings"
            )
        return findings

    def _run_research_adaptive(
        self,
        *,
        topic: str,
        depth_profile: str,
        jd_context: Dict[str, object],
    ) -> Dict[str, str]:
        """Run research using coverage-family fan-out from query_decomposer.

        Delegates family selection + query generation to
        ``decompose_coverage_families()``. Uses
        ``apps_research.integrations.search_retrieval.retrieve`` (the
        canonical SearXNG adapter) for the actual searches. Missing or empty
        retrieval fails closed; no curated company pack may stand in for
        grounded research.
        """
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        decompose = _cbe("decompose_coverage_families")
        depth_profiles = _cbe("_DEPTH_PROFILES")

        plans = decompose(topic, depth_profile, jd_context or None)
        findings: Dict[str, str] = {p.family: "" for p in plans}

        try:
            from apps_research.integrations.search_retrieval import retrieve
        except ImportError as exc:
            self.logger.warning(
                "[CompanyBriefEngine] search_retrieval unavailable; failing closed: %s",
                exc,
            )
            retrieve = None

        profile_cfg = depth_profiles.get(depth_profile, depth_profiles["COMPANY_BRIEF_STANDARD"])
        max_queries = profile_cfg["max_queries"]

        for plan in plans[:max_queries]:
            if retrieve is None:
                break
            try:
                docs = retrieve(plan.query, top_k=5)
            except RuntimeError as exc:
                self.logger.warning(
                    "[CompanyBriefEngine] SearXNG unavailable for family=%s: %s",
                    plan.family,
                    exc,
                )
                continue
            except Exception as exc:  # guardian: allow-broad-exception -- per-family SearXNG HTTP errors heterogeneous; fail-soft preserves partial brief
                self.logger.warning(
                    "[CompanyBriefEngine] SearXNG query failed (family=%s): %s",
                    plan.family,
                    exc,
                )
                continue
            snippets: list[str] = []
            for d in docs:
                if not (d.snippet or "").strip():
                    continue
                snippets.append(f"{d.title}: {d.snippet}")
                if d.url:
                    snippets.append(d.url)
            findings[plan.family] = "\n".join(snippets)[:4000]
        if not any((blob or "").strip() for blob in findings.values()):
            raise unavailable_err(
                f"{topic}: adaptive research returned no grounded findings"
            )
        return findings


__all__ = ["_CompanyBriefRetrievalLegacyMixin"]
