"""V2 retrieval pipeline mixin for CompanyBriefEngine."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

from apps_research.engines.company_brief.retrieval_v2_recovery import (
    _v2_build_receipt,
    _v2_document_payload,
    _v2_document_ref,
    _v2_exception_payload,
    _v2_execute_adaptive_followups,
    _v2_recover_from_same_run,
)
from apps_research.engines.company_brief.shared import _cbe


class _CompanyBriefRetrievalV2Mixin:
    """Provides V2 coverage-family retrieval, reranking, recovery, and receipt writing."""

    def _run_research_v2(
        self,
        *,
        topic: str,
        depth_profile: str | None = None,
        jd_context: Dict[str, Any] | None = None,
        depth: str | None = None,
        retrieval_receipt_path: Path | None = None,
    ) -> Dict[str, str]:
        """V2 retrieval pipeline: plan coverage families -> retrieve -> rerank.

        Plan §P1.4 + §P2.4 (parallel dispatch). Uses a thread pool for
        per-sub-query retrieval (I/O-bound HTTP calls to SearXNG) so
        wall-clock scales sub-linearly with fan-out. Missing retrieval
        dependencies fail closed.
        """
        import concurrent.futures

        from apps_research.engines.query_decomposer import decompose_coverage_families
        from apps_research.integrations.reranker_adapter import rerank
        from apps_research.integrations.search_retrieval import (
            RetryableRetrievalTransportError,
            apply_contextual_prefix,
            retrieval_config_snapshot,
            retrieve,
        )

        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        resolve_depth = _cbe("_resolve_depth_profile")
        depth_profiles = _cbe("_DEPTH_PROFILES")
        infer_intents = _cbe("infer_evidence_intents")
        req_families_fn = _cbe("required_families_for_intents")
        identity_matches = _cbe("_company_identity_matches")

        resolved_depth_profile = depth_profile or resolve_depth(depth or "standard")
        try:
            plans = decompose_coverage_families(topic, resolved_depth_profile, jd_context or None)
        except ValueError as exc:
            raise unavailable_err(
                f"{topic}: v2 research decomposition failed: {exc}"
            ) from exc
        profile_cfg = depth_profiles.get(
            resolved_depth_profile, depth_profiles["COMPANY_BRIEF_STANDARD"]
        )
        company_name = str((jd_context or {}).get("company_name") or "").strip() or topic
        max_queries = int(profile_cfg["max_queries"])
        if jd_context:
            required_targeting_families = [
                "company_basics",
                "role_context",
                "competitive_landscape",
                "leadership_and_org",
                "recent_news_and_signals",
                *req_families_fn(infer_intents(jd_context)),
            ]
            planned_families = {plan.family for plan in plans}
            required_planned_count = len(
                {family for family in required_targeting_families if family in planned_families}
            )
            max_queries = max(max_queries, required_planned_count)
        plans = plans[:max_queries]

        config_snapshot = retrieval_config_snapshot(query_families=[plan.family for plan in plans])
        config_bytes = json.dumps(
            config_snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        config_digest = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        base_url_origin = str(config_snapshot.get("base_url_origin") or "").rstrip("/")
        endpoint = f"{base_url_origin}/search" if base_url_origin else "UNCONFIGURED"

        def _fetch(plan: Any) -> tuple[str, str, dict[str, Any], list[Any]]:
            search_queries = (plan.query, *plan.supplemental_queries)
            row: dict[str, Any] = {
                "family": plan.family,
                "query": plan.query,
                "queries": list(search_queries),
                "min_sources": plan.min_sources,
                "jd_boosted": plan.jd_boosted,
                "retrieval_endpoint": endpoint,
                "configuration_identity": {
                    "provider": config_snapshot.get("provider"),
                    "provider_profile": config_snapshot.get("provider_profile"),
                    "digest": config_digest,
                },
                "retrieval_attempt_status": "PENDING",
                "attempts": [],
                "query_receipts": [],
                "documents_before_rerank": 0,
                "documents_identity_admissible": 0,
                "documents_after_rerank": 0,
                "accepted_documents": [],
                "snippets_rejected": [],
                "grounded_character_count": 0,
                "finding_digest": "",
            }
            docs: list[Any] = []
            seen_docs: set[tuple[str, str, str, float]] = set()
            retry_available = True
            query_failed = False
            for search_query in search_queries:
                query_receipt: dict[str, Any] = {
                    "query": search_query,
                    "status": "PENDING",
                    "attempts": [],
                    "documents_returned": 0,
                }
                query_docs: list[Any] = []
                attempt = 1
                while True:
                    try:
                        query_docs = retrieve(search_query, top_k=10)
                    except RetryableRetrievalTransportError as exc:
                        status = "RETRY" if retry_available else "FAILED"
                        payload = _v2_exception_payload(attempt=attempt, status=status, exc=exc)
                        row["attempts"].append(payload)
                        query_receipt["attempts"].append(payload)
                        if retry_available:
                            retry_available = False
                            attempt += 1
                            continue
                        query_receipt["status"] = "FAILED"
                        query_failed = True
                        break
                    except (RuntimeError, ValueError) as exc:
                        payload = _v2_exception_payload(attempt=attempt, status="FAILED", exc=exc)
                        row["attempts"].append(payload)
                        query_receipt["attempts"].append(payload)
                        query_receipt["status"] = "FAILED"
                        query_failed = True
                        break
                    payload = {"attempt": attempt, "status": "PASS"}
                    row["attempts"].append(payload)
                    query_receipt["attempts"].append(payload)
                    query_receipt["status"] = "PASS"
                    query_receipt["documents_returned"] = len(query_docs)
                    break
                row["query_receipts"].append(query_receipt)
                for document in query_docs:
                    ref = _v2_document_ref(document)
                    if ref not in seen_docs:
                        seen_docs.add(ref)
                        docs.append(document)

            row["documents_before_rerank"] = len(docs)
            if not docs:
                row["retrieval_attempt_status"] = "FAILED" if query_failed else "ZERO_DOCUMENTS"
                return plan.family, "", row, []

            identity_docs: list[Any] = []
            for document in docs:
                payload = _v2_document_payload(document)
                missing_fields = [
                    field
                    for field in ("title", "url", "snippet")
                    if not str(payload.get(field) or "").strip()
                ]
                if not payload["engines"]:
                    missing_fields.append("engines")
                if missing_fields:
                    row["snippets_rejected"].append(
                        {
                            "url": payload["url"],
                            "title": payload["title"],
                            "reason": "REQUIRED_EVIDENCE_FIELDS_MISSING",
                            "missing_fields": missing_fields,
                        }
                    )
                    continue
                if not identity_matches(company_name=company_name, document=payload):
                    row["snippets_rejected"].append(
                        {
                            "url": payload["url"],
                            "title": payload["title"],
                            "reason": "COMPANY_IDENTITY_MISMATCH",
                        }
                    )
                    continue
                identity_docs.append(document)
            docs = identity_docs

            row["documents_identity_admissible"] = len(docs)
            if not docs:
                row["retrieval_attempt_status"] = "NO_ADMISSIBLE_DOCUMENTS"
                return plan.family, "", row, []

            try:
                top = rerank(plan.query, docs, cutoff=5)
            except (RuntimeError, ValueError) as exc:
                row["retrieval_attempt_status"] = "RERANK_FAILED"
                row["rerank_exception"] = _v2_exception_payload(attempt=1, status="FAILED", exc=exc)
                return plan.family, "", row, docs

            row["documents_after_rerank"] = len(top)
            top_refs = {_v2_document_ref(document) for document in top}
            for document in docs:
                if _v2_document_ref(document) not in top_refs:
                    row["snippets_rejected"].append(
                        {
                            "url": str(getattr(document, "url", "") or ""),
                            "title": str(getattr(document, "title", "") or ""),
                            "reason": "RERANK_DROPPED",
                        }
                    )
            if not top:
                row["retrieval_attempt_status"] = "RERANK_EMPTY"
                return plan.family, "", row, docs

            chunks: list[str] = []
            for d in top:
                if not d.snippet:
                    row["snippets_rejected"].append(
                        {"url": str(d.url or ""), "title": str(d.title or ""), "reason": "EMPTY_SNIPPET"}
                    )
                    continue
                row["accepted_documents"].append(_v2_document_payload(d))
                chunk = f"- {d.title}: {d.snippet} ({d.url})"
                if d.url:
                    chunk = f"{chunk}\n{d.url}"
                chunks.append(
                    apply_contextual_prefix(
                        chunk,
                        doc_title=d.title,
                        surrounding_text=plan.query,
                    )
                )
            blob = "\n\n".join(chunks)
            row["grounded_character_count"] = len(blob)
            row["finding_digest"] = (
                "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest() if blob else ""
            )
            row["retrieval_attempt_status"] = "PASS" if blob else "NO_ADMISSIBLE_SNIPPETS"
            return plan.family, blob, row, docs

        findings: Dict[str, str] = {plan.family: "" for plan in plans}
        family_receipts: list[dict[str, Any]] = []
        admissible_documents_by_family: dict[str, list[Any]] = {}
        max_workers = max(1, min(5, len(plans)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for family, blob, family_receipt, admissible_documents in pool.map(_fetch, plans):
                findings[family] = blob
                family_receipts.append(family_receipt)
                admissible_documents_by_family[family] = admissible_documents

        receipts_by_family = _v2_recover_from_same_run(
            plans=plans,
            findings=findings,
            family_receipts=family_receipts,
            admissible_documents_by_family=admissible_documents_by_family,
            rerank_fn=rerank,
            apply_contextual_prefix_fn=apply_contextual_prefix,
        )
        adaptive_revision, adaptive_execution = _v2_execute_adaptive_followups(
            topic=topic,
            plans=plans,
            findings=findings,
            family_receipts=family_receipts,
            receipts_by_family=receipts_by_family,
            fetch_fn=_fetch,
        )
        receipt = _v2_build_receipt(
            topic=topic,
            resolved_depth_profile=resolved_depth_profile,
            config_snapshot=config_snapshot,
            config_digest=config_digest,
            plans=plans,
            family_receipts=family_receipts,
            adaptive_revision=adaptive_revision,
            adaptive_execution=adaptive_execution,
        )
        if retrieval_receipt_path is not None:
            self._write_retrieval_receipt(retrieval_receipt_path, receipt)

        if not any((blob or "").strip() for blob in findings.values()):
            receipt_ref = str(retrieval_receipt_path) if retrieval_receipt_path else "not_configured"
            raise unavailable_err(
                f"{topic}: v2 research returned no grounded findings; retrieval_receipt={receipt_ref}"
            )
        return findings

    @staticmethod
    def _resolve_retrieval_receipt_path(jd_context: Dict[str, Any]) -> Path | None:
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        raw_path = str(jd_context.get("_retrieval_receipt_path") or "").strip()
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_absolute():
            raise unavailable_err("retrieval receipt path must be absolute")
        resolved = path.resolve()
        runs_root = resolved.parent / "runs"
        if resolved.name != "retrieval_receipt.json" or not runs_root.is_dir():
            raise unavailable_err(
                "retrieval receipt path must be beside the existing Apps Research runs directory"
            )
        return resolved

    @staticmethod
    def _write_retrieval_receipt(path: Path, receipt: dict[str, Any]) -> None:
        payload = json.dumps(
            receipt,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        temporary_path = path.with_name(path.name + ".tmp")
        temporary_path.write_bytes(payload)
        os.replace(temporary_path, path)


__all__ = ["_CompanyBriefRetrievalV2Mixin"]
