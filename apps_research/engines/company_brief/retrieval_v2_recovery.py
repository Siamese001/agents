"""Same-run recovery, adaptive follow-up, and receipt assembly helpers for V2 retrieval."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

from apps_research.engines.company_brief.shared import _cbe


def _v2_document_ref(document: Any) -> tuple[str, str, str, float]:
    """Return canonical deduplication tuple for a retrieved search document."""
    return (
        str(getattr(document, "url", "") or ""),
        str(getattr(document, "title", "") or ""),
        str(getattr(document, "snippet", "") or ""),
        float(getattr(document, "score", 0.0) or 0.0),
    )


def _v2_document_payload(document: Any) -> dict[str, Any]:
    """Serialize a retrieved search document into a receipt payload dictionary."""
    url, title, snippet, score = _v2_document_ref(document)
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "score": score,
        "engines": list(getattr(document, "engines", ()) or ()),
    }


def _v2_exception_payload(
    *,
    attempt: int,
    status: str,
    exc: BaseException,
) -> dict[str, Any]:
    """Build normalized retrieval exception telemetry row."""
    return {
        "attempt": attempt,
        "status": status,
        "exception_type": type(exc).__name__,
        "exception_message": " ".join(str(exc).split()),
    }


def _v2_recover_from_same_run(
    *,
    plans: list[Any],
    findings: dict[str, str],
    family_receipts: list[dict[str, Any]],
    admissible_documents_by_family: dict[str, list[Any]],
    rerank_fn: Callable[..., list[Any]],
    apply_contextual_prefix_fn: Callable[..., str],
) -> dict[str, dict[str, Any]]:
    """Recover failed families using identity-admissible documents with explicit semantic signal."""
    recovery_patterns = _cbe("_SAME_RUN_RECOVERY_SIGNAL_PATTERNS", {})
    receipts_by_family = {str(row.get("family") or ""): row for row in family_receipts}
    for plan in plans:
        if findings.get(plan.family, "").strip():
            continue
        signal_pattern = recovery_patterns.get(plan.family)
        if signal_pattern is None:
            continue

        candidates: list[Any] = []
        donor_families: list[str] = []
        seen_candidates: set[tuple[str, str, str, float]] = set()
        for donor_plan in plans:
            donor_family = donor_plan.family
            if donor_family == plan.family:
                continue
            for candidate in admissible_documents_by_family.get(donor_family, []):
                payload = _v2_document_payload(candidate)
                semantic_text = " ".join((payload["title"], payload["snippet"]))
                if not signal_pattern.search(semantic_text):
                    continue
                candidate_ref = _v2_document_ref(candidate)
                if candidate_ref in seen_candidates:
                    continue
                seen_candidates.add(candidate_ref)
                candidates.append(candidate)
                if donor_family not in donor_families:
                    donor_families.append(donor_family)

        if not candidates:
            continue
        try:
            recovered_docs = rerank_fn(plan.query, candidates, cutoff=5)
        except (RuntimeError, ValueError) as exc:
            receipts_by_family[plan.family]["recovery"] = {
                "status": "RERANK_FAILED",
                "method": "same_run_identity_admissible_semantic_evidence",
                "donor_families": donor_families,
                "candidate_count": len(candidates),
                "exception_type": type(exc).__name__,
                "exception_message": " ".join(str(exc).split()),
            }
            continue
        if not recovered_docs:
            continue

        row = receipts_by_family[plan.family]
        recovered_chunks: list[str] = []
        for document in recovered_docs:
            payload = _v2_document_payload(document)
            if not payload["snippet"]:
                continue
            row["accepted_documents"].append(payload)
            chunk = f"- {payload['title']}: {payload['snippet']} ({payload['url']})"
            if payload["url"]:
                chunk = f"{chunk}\n{payload['url']}"
            recovered_chunks.append(
                apply_contextual_prefix_fn(
                    chunk,
                    doc_title=payload["title"],
                    surrounding_text=plan.query,
                )
            )
        recovered_blob = "\n\n".join(recovered_chunks)
        if not recovered_blob:
            continue

        findings[plan.family] = recovered_blob
        row["documents_after_rerank"] = len(recovered_docs)
        row["grounded_character_count"] = len(recovered_blob)
        row["finding_digest"] = "sha256:" + hashlib.sha256(recovered_blob.encode("utf-8")).hexdigest()
        row["retrieval_attempt_status"] = "RECOVERED_FROM_SAME_RUN"
        row["recovery"] = {
            "status": "PASS",
            "method": "same_run_identity_admissible_semantic_evidence",
            "donor_families": donor_families,
            "candidate_count": len(candidates),
            "accepted_count": len(row["accepted_documents"]),
            "semantic_signal_pattern": signal_pattern.pattern,
        }
    return receipts_by_family


def _v2_execute_adaptive_followups(
    *,
    topic: str,
    plans: list[Any],
    findings: dict[str, str],
    family_receipts: list[dict[str, Any]],
    receipts_by_family: dict[str, dict[str, Any]],
    fetch_fn: Callable[[Any], tuple[str, str, dict[str, Any], list[Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run bounded adaptive follow-up retrieval queries for uncovered families."""
    from apps_research.engines.query_decomposer import QueryPlan as _FallbackQueryPlan
    from apps_research.reasoning.adaptive_research_loop import (
        build_adaptive_research_revision as _fallback_revision,
    )

    build_revision = _cbe("build_adaptive_research_revision", _fallback_revision)
    query_plan_cls = _cbe("QueryPlan", _FallbackQueryPlan)

    adaptive_revision = build_revision(
        topic=topic,
        plans=plans,
        family_observations=family_receipts,
    )
    adaptive_execution: list[dict[str, Any]] = []
    for action in adaptive_revision["follow_up_queries"]:
        family = str(action["family"])
        parent_row = receipts_by_family[family]
        parent_plan = next(plan for plan in plans if plan.family == family)
        follow_up_plan = query_plan_cls(
            family=family,
            query=str(action["query"]),
            min_sources=parent_plan.min_sources,
            jd_boosted=True,
        )
        _family, follow_up_blob, follow_up_row, _documents = fetch_fn(follow_up_plan)
        execution_row = {
            "family": family,
            "query": str(action["query"]),
            "strategy": str(action["strategy"]),
            "trigger": dict(action["trigger"]),
            "retrieval_attempt_status": str(follow_up_row["retrieval_attempt_status"]),
            "accepted_document_count": len(follow_up_row["accepted_documents"]),
            "finding_digest": str(follow_up_row["finding_digest"]),
        }
        adaptive_execution.append(execution_row)
        parent_row["adaptive_follow_up"] = execution_row
        if not follow_up_blob:
            continue

        initial_blob = findings.get(family, "")
        findings[family] = "\n\n".join(blob for blob in (initial_blob, follow_up_blob) if blob)
        parent_row["accepted_documents"].extend(follow_up_row["accepted_documents"])
        parent_row["documents_before_rerank"] += follow_up_row["documents_before_rerank"]
        parent_row["documents_identity_admissible"] += follow_up_row["documents_identity_admissible"]
        parent_row["documents_after_rerank"] += follow_up_row["documents_after_rerank"]
        parent_row["grounded_character_count"] = len(findings[family])
        parent_row["finding_digest"] = "sha256:" + hashlib.sha256(findings[family].encode("utf-8")).hexdigest()
        if not initial_blob:
            parent_row["retrieval_attempt_status"] = "RECOVERED_BY_ADAPTIVE_FOLLOW_UP"
    return adaptive_revision, adaptive_execution


def _v2_build_receipt(
    *,
    topic: str,
    resolved_depth_profile: str,
    config_snapshot: dict[str, Any],
    config_digest: str,
    plans: list[Any],
    family_receipts: list[dict[str, Any]],
    adaptive_revision: dict[str, Any],
    adaptive_execution: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble digest-sealed apps_research V2 retrieval receipt."""
    grounded_family_count = sum(
        1
        for row in family_receipts
        if row["retrieval_attempt_status"]
        in {"PASS", "RECOVERED_FROM_SAME_RUN", "RECOVERED_BY_ADAPTIVE_FOLLOW_UP"}
    )
    receipt: dict[str, Any] = {
        "schema_version": "apps_research.retrieval_receipt.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "depth_profile": resolved_depth_profile,
        "configuration": config_snapshot,
        "configuration_digest": config_digest,
        "families": family_receipts,
        "adaptive_research_revision": adaptive_revision,
        "adaptive_research_execution": adaptive_execution,
        "summary": {
            "status": "PASS" if grounded_family_count else "BLOCKED",
            "planned_family_count": len(plans),
            "grounded_family_count": grounded_family_count,
            "grounded_source_count": sum(len(row["accepted_documents"]) for row in family_receipts),
            "unexplained_failure_count": sum(
                1 for row in family_receipts if row["retrieval_attempt_status"] == "PENDING"
            ),
        },
    }
    digest_payload = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt["receipt_digest"] = "sha256:" + hashlib.sha256(digest_payload).hexdigest()
    return receipt


__all__ = [
    "_v2_build_receipt",
    "_v2_document_payload",
    "_v2_document_ref",
    "_v2_exception_payload",
    "_v2_execute_adaptive_followups",
    "_v2_recover_from_same_run",
]
