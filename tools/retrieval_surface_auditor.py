#!/usr/bin/env python3
"""Behavioral 7-Pillar Research & Hybrid Retrieval Surface Auditor (Agent 4).

Replaces print-only inline scripts and static cache receipt checks with live,
fail-closed behavioral verification across:
1. Query decomposition & JD evidence intent routing.
2. Contextual chunking, provenance hashing, and token window fitting.
3. GraphDB 3-hop acyclicity, BGE-M3 L2/cosine spectrum, and Stage 2 metric boost.
4. Grounded targeting brief provenance & citation hygiene.
5. Empty-result, low-confidence, and missing-endpoint fail-closed abstention.
6. Pipeline latency & live in-memory multi-tier cache verification.
7. Cross-subsystem retrieval contract & fail-closed public return-type annotations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(DEFAULT_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_REPO_ROOT))

from tools._retrieval_surface_helpers import (  # noqa: E402
    RETRIEVAL_PACKAGES,
    _ensure_paths,
    _exported_symbol_typed,
    _facade_exemptions,
    _probe_chunking_and_context_window,
    _probe_query_decomposition_and_intent_routing,
    _require_module,
    _resolve_pkg_attr,
    _scan_module_ast,
    _static_str_seq,
    scan_untyped_public_retrieval_callables,
)


def _probe_graph_and_embeddings(repo_root: Path, *, read_only: bool = True) -> dict[str, Any]:
    from infrastructure.config.env_loader import get_main_repo_root

    graph_mod = _require_module(repo_root, "tools/verify_graph_integrity_and_embeddings.py")
    trav_mod = _require_module(repo_root, "tools/run_resume_graph_traversal_probe.py")

    roots = [repo_root]
    main_root = get_main_repo_root(repo_root)
    if main_root.is_dir() and main_root not in roots:
        roots.append(main_root)

    db_path = repo_root / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    for base in roots:
        cand = base / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
        if cand.is_file():
            db_path = cand
            break

    emb_dirs: list[Path] = [
        base / rel
        for base in roots
        for rel in (
            "artifacts/apps_rg/c03/graph_skill_embeddings",
            "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
            "resume_graph_engine/artifacts/apps_rg/c03/graph_skill_embeddings",
            "resume_graph_engine/artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
        )
    ]

    gaps: list[str] = []
    graph_res: dict[str, Any] = {}
    emb_res: dict[str, Any] = {}
    stage2_res: dict[str, Any] = {}
    trav_res: dict[str, Any] = {}
    custody_passed = False
    quad_chunk_count = 0
    lic_alloc_digest = ""
    try:
        with tempfile.TemporaryDirectory(prefix="retrieval_aud_graph_") as td:
            active_db = db_path
            if not active_db.is_file():
                from apps_rg.fact_inventory.augmented_skills_graph_sqlite import materialize_augmented_skills_graph_sqlite

                active_db = Path(td) / "augmented_skills_graph.sqlite"
                materialize_augmented_skills_graph_sqlite(db_path=active_db)
            graph_res = graph_mod.verify_graph_database(active_db, read_only=read_only)
            emb_res = graph_mod.verify_bge_m3_embeddings(emb_dirs, active_db, read_only=read_only)
            quad_res = graph_mod.verify_learned_sparse_and_colbert(active_db, read_only=read_only)
            stage2_res = graph_mod.verify_hybrid_retrieval_stage2(active_db)
            if quad_res.get("status") != "PASS":
                gaps.append("verify_learned_sparse_and_colbert did not return PASS")
            trav_res = trav_mod.run_resume_graph_traversal_probe(max_paths=100)
            from apps_rg.runtime.c0.c03_sqlite_graph_selection import select_c03_sqlite_graph_candidates
            from apps_rg.runtime.c03_graph_sqlite_context import ensure_c03_graph_sqlite
            from infrastructure.candidate_evidence.quad_hybrid_retriever import QuadHybridCandidateRetriever
            from infrastructure.candidate_evidence.sqlite_custody import verify_sqlite_custody

            custody_rep = verify_sqlite_custody(active_db)
            custody_passed = bool(
                custody_rep.passed
                and custody_rep.check_1_file_exists_nonzero
                and custody_rep.check_2_sqlite_header_and_quick_check
                and custody_rep.check_3_required_tables_and_fts5
                and custody_rep.check_4_candidate_node_count_and_schema
                and custody_rep.check_5_sha256_and_manifest_verified
                and len(custody_rep.candidate_graph_db_sha256) == 64
            )
            if not custody_passed:
                gaps.append(f"verify_sqlite_custody failed 5-check custody: {custody_rep.errors}")

            quad_retriever = QuadHybridCandidateRetriever(db_path=active_db)
            cand_pool = quad_retriever.retrieve(
                "Enterprise AI agentic platform architecture, cloud governance, and risk transformation"
            )
            quad_chunk_count = len(cand_pool.chunks)
            if (
                quad_chunk_count < 4
                or not cand_pool.pool_digest
                or cand_pool.chunks[0].channel_scores.final_score <= 0.0
                or not any(cand_pool.channels_executed.values())
            ):
                gaps.append(
                    f"QuadHybridCandidateRetriever failed 4-channel retrieval: chunks={quad_chunk_count}, "
                    f"channels={cand_pool.channels_executed}"
                )

            lic_c0_mod = _require_module(
                repo_root, "outreach_engine/src/apps_lic/runtime/c0/sequence_allocation.py"
            )
            dedup_chunks = [
                c
                for c in cand_pool.chunks
                if len({lic_c0_mod.normalize_metric_token(m) for m in c.metric_tokens if m})
                == len([m for m in c.metric_tokens if m])
            ]
            touch_specs = [
                lic_c0_mod.TouchSlotSpec(touch_number=1, channel="email", metric_required=False),
                lic_c0_mod.TouchSlotSpec(touch_number=2, channel="inmail", metric_required=False),
                lic_c0_mod.TouchSlotSpec(touch_number=3, channel="follow_up", metric_required=False),
            ]
            lic_plan = lic_c0_mod.solve_sequence_allocation(
                dedup_chunks,
                touch_specs,
                opportunity_id="opp_citi_ai_strategy",
                candidate_id="cand_enterprise_ai",
                candidate_graph_db_sha256=cand_pool.candidate_graph_db_sha256,
            )
            lic_alloc_digest = str(lic_plan.allocation_plan_digest or "")
            if (
                not lic_plan.uniqueness_receipt.get("passed")
                or len(lic_plan.assignments) != 3
                or len(lic_alloc_digest) != 64
            ):
                gaps.append(f"outreach_engine C0 solve_sequence_allocation failed: {lic_plan.uniqueness_receipt}")

            rg_root = (repo_root / "resume_graph_engine") if (repo_root / "resume_graph_engine").is_dir() else repo_root
            sel_db = Path(td) / "c03_selection_probe.sqlite"
            ensure_c03_graph_sqlite(rg_root, sel_db)
            c03_sel = select_c03_sqlite_graph_candidates(
                section_id="executive_summary", selected_fact_ids=["fact_engineering_platform_001"],
                role_family_key="SVP_ENGINEERING_AI_PLATFORM", pillar_hints=["pillar_agentic_runtime_governance"],
                repo_root=rg_root, db_path=sel_db,
            )
            if not c03_sel.get("selected_candidates"):
                gaps.append("select_c03_sqlite_graph_candidates returned 0 selected_candidates for executive_summary")
            import sqlite3
            with sqlite3.connect(f"file:{active_db.as_posix()}?mode=ro" if read_only else str(active_db), uri=read_only) as conn:
                blank_emp = conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE node_type IN ('fact','skill','metric_outcome') AND COALESCE(TRIM(employer),'') = ''"
                ).fetchone()[0]
                if blank_emp > 0:
                    gaps.append(f"augmented_skills_graph.sqlite has {blank_emp} blank employer rows on fact/skill/metric_outcome")
                elig_facts = conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'fact' AND external_eligible = 1"
                ).fetchone()[0]
                if elig_facts < 60:
                    gaps.append(f"augmented_skills_graph.sqlite has only {elig_facts} external_eligible=1 facts (<60)")
                orphan_rf = conn.execute(
                    "SELECT COUNT(*) FROM graph_nodes n WHERE n.node_type = 'role_family' AND NOT EXISTS (SELECT 1 FROM graph_edges e WHERE e.source_node_id = n.node_id OR e.target_node_id = n.node_id)"
                ).fetchone()[0]
                if orphan_rf > 0:
                    gaps.append(f"augmented_skills_graph.sqlite has {orphan_rf} orphaned role_family nodes")
            fv_fts = rg_root / "data/cache/sparse/fact_vectors.db"
            if fv_fts.is_file():
                with sqlite3.connect(f"file:{fv_fts.as_posix()}?mode=ro" if read_only else str(fv_fts), uri=read_only) as fconn:
                    fts_count = fconn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
                    if fts_count < 328:
                        gaps.append(f"fact_vectors.db has only {fts_count} indexed rows (<328)")
        if trav_res.get("status") != "PASS":
            gaps.append("run_resume_graph_traversal_probe did not return PASS")

        qrels_dir = repo_root / "data" / "qrels"
        qrels_coverage_passed = True
        qrels_weight_verdict = "NOT_CONFIGURED"
        if (qrels_dir / "qrels_partitions.v1.json").is_file():
            from tools.audit_qrels_coverage import audit_qrels_coverage

            qcov = audit_qrels_coverage(
                qrels_dir / "qrels_partitions.v1.json",
                qrels_dir / "qrels_independent_ground_truth.v1.json",
                qrels_dir / "qrels_authentic_candidate_pool.v1.json",
            )
            qrels_coverage_passed = qcov.get("gate_status") == "PASS"
            if not qrels_coverage_passed:
                gaps.append(f"QRELS coverage gate failed: {qcov.get('failures')}")
            wt_file = qrels_dir / "qrels_weight_calibration_results.v1.json"
            if wt_file.is_file():
                wt_data = json.loads(wt_file.read_text(encoding="utf-8"))
                qrels_weight_verdict = str(wt_data.get("verdict") or "UNKNOWN")
                if not wt_data.get("is_validated"):
                    gaps.append(f"QRELS 4-simplex weight calibration not validated: {qrels_weight_verdict}")
                ab_cal = wt_data.get("abstention_calibration") or {}
                if int(ab_cal.get("false_abstains", 1)) != 0:
                    gaps.append(f"QRELS abstention calibration has false_abstains={ab_cal.get('false_abstains')}")
    except Exception as exc:  # guardian: allow-broad-exception -- capture graph/embedding verification failure into pillar gaps
        gaps.append(f"Graph/embedding verification failed: {exc}")
        qrels_coverage_passed = False
        qrels_weight_verdict = "ERROR"

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "three_hop_paths": graph_res.get("three_hop_traversal_paths", 0),
        "verified_vectors": emb_res.get("verified_vectors_count", 0),
        "mean_cosine": emb_res.get("mean_cosine", 0.0),
        "stage2_top_assertion": stage2_res.get("top_assertion", ""),
        "candidate_evidence_custody_passed": custody_passed,
        "quad_hybrid_chunk_count": quad_chunk_count,
        "lic_c0_allocation_digest": lic_alloc_digest,
        "qrels_coverage_passed": qrels_coverage_passed,
        "qrels_weight_verdict": qrels_weight_verdict,
    }


def _probe_citation_and_provenance_contract(repo_root: Path) -> dict[str, Any]:
    contract_mod = _require_module(repo_root, "apps_research/types/apps_rg_targeting_brief_contract.py")
    raw_citation_leak = (
        "# Strategic Brief\n## Mandate\n"
        "- Strategy mandate relies on [1] raw footnote marker and https://untrusted.example/url.\n"
    )
    leak_verdict_lic = contract_mod.validate_targeting_brief_text(raw_citation_leak, profile="apps_lic")
    leak_verdict_rg = contract_mod.validate_targeting_brief_text(raw_citation_leak, profile="apps_rg")
    leak_rejected = (
        not bool(leak_verdict_lic.valid)
        and "link_present" in leak_verdict_lic.violations
        and "citation_present" in leak_verdict_lic.violations
        and not bool(leak_verdict_rg.valid)
        and "link_present" in leak_verdict_rg.violations
        and "citation_present" in leak_verdict_rg.violations
    )
    gaps = [] if leak_rejected else ["validate_targeting_brief_text failed to reject raw URL/citation leakage across apps_lic/apps_rg"]
    return {"passed": len(gaps) == 0, "gaps": gaps, "raw_leak_rejected": leak_rejected}


def _probe_fail_closed_abstention(repo_root: Path) -> dict[str, Any]:
    sr_mod = _require_module(repo_root, "apps_research/integrations/search_retrieval.py")
    delegation_mod = _require_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/integrations/managed_research_delegation.py",
    )
    bridge_mod = _require_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/integrations/apps_research_bridge.py",
    )
    lic_delegation_mod = _require_module(
        repo_root,
        "outreach_engine/src/apps_lic/integrations/managed_research_delegation.py",
    )
    lic_bridge_mod = _require_module(
        repo_root,
        "outreach_engine/src/apps_lic/integrations/apps_research_bridge.py",
    )

    gaps: list[str] = []
    prior_url = os.environ.pop("SEARXNG_BASE_URL", None)
    try:
        try:
            sr_mod._require_base_url()
            gaps.append("_require_base_url succeeded when SEARXNG_BASE_URL was unset")
        except RuntimeError:
            pass
    finally:
        if prior_url is not None:
            os.environ["SEARXNG_BASE_URL"] = prior_url

    class _WeakBridge:
        def fetch_briefing_for_company(self, company_name: str, job_title: str = "", **_: Any) -> Any:
            return bridge_mod.ResearchResult(
                company_name=company_name,
                job_title=job_title,
                briefing_text="",
                evidence_count=0,
                confidence_score=0.15,
                status="EMPTY",
                run_id="weak_probe",
            )

    req = delegation_mod.RequestForResumeBriefing(
        request_id="req_weak",
        run_id="run_weak",
        trace_id="trace_weak",
        company_name="ShadowCo",
        job_title="Architect",
        research_authorized=True,
        min_confidence_threshold=0.60,
    )
    res = delegation_mod.dispatch_resume_research_briefing(req, bridge=_WeakBridge())
    if not isinstance(res, delegation_mod.ResearchDispatchFailure):
        gaps.append("dispatch_resume_research_briefing did not fail closed on empty/low-confidence research")

    class _WeakOutreachBridge:
        def fetch(self, **kwargs: Any) -> Any:
            return lic_bridge_mod.ResearchResult(
                run_id=str(kwargs.get("run_id") or "weak_lic_run"),
                trace_id=str(kwargs.get("trace_id") or "weak_lic_trace"),
                request_id=str(kwargs.get("request_id") or "weak_lic_req"),
                is_blocked=False,
                block_reason="",
                is_stale=False,
                evidence_items=(),
                confidence_score=0.15,
                brief_sha256="",
                company_brief_text="",
                strategic_priorities=(),
                fetch_duration_ms=1.0,
                audit_ref="weak_lic_audit",
            )

    lic_req = lic_delegation_mod.RequestForOutreachBriefing(
        request_id="req_lic_weak",
        run_id="run_lic_weak",
        trace_id="trace_lic_weak",
        company_name="ShadowCo",
        job_title="VP AI",
        research_authorized=True,
        min_confidence_threshold=0.60,
    )
    lic_res = lic_delegation_mod.dispatch_outreach_research_briefing(lic_req, bridge=_WeakOutreachBridge())
    if not isinstance(lic_res, lic_delegation_mod.ResearchDispatchFailure):
        gaps.append("dispatch_outreach_research_briefing did not fail closed on empty/low-confidence research")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "failure_reason": getattr(res, "r5_reason_code", ""),
        "outreach_failure_reason": getattr(lic_res, "r5_reason_code", ""),
    }


def _probe_latency_and_live_caching(repo_root: Path) -> dict[str, Any]:
    vplc_mod = _require_module(repo_root, "tools/verify_pipeline_latency_caching.py")
    res = vplc_mod.run_verification(repo_root, quiet=True)
    gaps: list[str] = []
    if res.get("status") != "PASS":
        for section in ("static_prefixes", "compiler_cache_alignment", "deterministic_e2e", "live_cache_probes"):
            if not (res.get(section) or {}).get("passed"):
                gaps.append(f"verify_pipeline_latency_caching failed gate: {section}")
    from apps_rg.cache.briefing_cache import get_global_briefing_cache

    prior_pytest = os.environ.get("PYTEST_CURRENT_TEST")
    os.environ["PYTEST_CURRENT_TEST"] = "retrieval_surface_auditor::probe"
    try:
        pytest_cache = get_global_briefing_cache()
        if pytest_cache._cache_dir is not None:
            gaps.append("get_global_briefing_cache leaked disk cache_dir under PYTEST_CURRENT_TEST")
    finally:
        if prior_pytest is None:
            os.environ.pop("PYTEST_CURRENT_TEST", None)
        else:
            os.environ["PYTEST_CURRENT_TEST"] = prior_pytest

    import hashlib
    import time
    lic_res_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/pipeline/briefing_resolver.py")
    lic_resolver = lic_res_mod.GovernedBriefingResolver
    lic_resolver.clear_cache()
    exp_key = hashlib.sha256("OutreachTTLProbe::VP AI::".encode("utf-8")).hexdigest()
    with lic_resolver._lock:
        lic_resolver._cache[exp_key] = {
            "briefing_text": "# Expired Briefing",
            "digest": "sha256:expired",
            "confidence_score": 0.90,
            "evidence_count": 2,
            "airlock_sanitized": True,
            "strategic_priorities": ("Priority A",),
            "timestamp": time.time() - (lic_resolver.DEFAULT_CACHE_TTL_SECONDS + 86400.0),
            "is_verified": True,
        }
    exp_res = lic_resolver.resolve(company_name="OutreachTTLProbe", target_role="VP AI", auto_research=False)
    if exp_res.resolution_source != "HERMETIC_FALLBACK" or exp_key in lic_resolver._cache:
        gaps.append("GovernedBriefingResolver failed to evict expired 30-day TTL entry on lookup")
    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "live_cache_probes": res.get("live_cache_probes", {}),
        "outreach_ttl_eviction_verified": exp_res.resolution_source == "HERMETIC_FALLBACK",
    }


def run_retrieval_surface_audit(repo_root: Path | None = None, *, read_only: bool = True) -> dict[str, Any]:
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    _ensure_paths(root)
    untyped = scan_untyped_public_retrieval_callables(root)
    pillars = {
        "pillar_1_query_decomposition_and_intent_routing": _probe_query_decomposition_and_intent_routing(root),
        "pillar_2_chunking_and_context_window": _probe_chunking_and_context_window(root),
        "pillar_3_graphdb_traversal_and_embeddings": _probe_graph_and_embeddings(root, read_only=read_only),
        "pillar_4_provenance_and_citation_hygiene": _probe_citation_and_provenance_contract(root),
        "pillar_5_empty_result_fail_closed_abstention": _probe_fail_closed_abstention(root),
        "pillar_6_latency_and_live_multi_tier_caching": _probe_latency_and_live_caching(root),
        "pillar_7_cross_subsystem_typing_contract": {
            "passed": len(untyped) == 0,
            "gaps": [f"Untyped public retrieval callable {u['callable']} at {u['file']}:{u['line']}" for u in untyped[:15]],
            "untyped_public_callable_count": len(untyped),
        },
    }
    all_gaps = [f"[{name}] {g}" for name, res in pillars.items() for g in res.get("gaps", [])]
    passing_count = sum(1 for res in pillars.values() if res["passed"])
    is_clean = passing_count == len(pillars) and len(all_gaps) == 0
    return {
        "schema_version": "agents.retrieval_surface_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root), "read_only": read_only,
        "status": "PASS" if is_clean else "FAIL", "is_clean": is_clean,
        "passing_pillars": passing_count, "total_pillars": len(pillars),
        "total_gaps": len(all_gaps), "gaps": all_gaps, "pillars": pillars,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 7-pillar behavioral retrieval surface audit (Agent 4).")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--read-only", action="store_true", default=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_retrieval_surface_audit(args.repo_root.resolve(), read_only=args.read_only)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"[{report['status']}] Retrieval Surface Audit: {report['passing_pillars']}/{report['total_pillars']} pillars passing (gaps={report['total_gaps']})")
        for gap in report["gaps"]:
            print(f"  - {gap}")
    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
