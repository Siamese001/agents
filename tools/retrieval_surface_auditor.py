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
import ast
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_PACKAGES = (
    "agents",
    "apps_eval",
    "apps_model_telemetry",
    "apps_research",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "scripts",
    "tools",
)


def _ensure_paths(repo_root: Path) -> None:
    for p in reversed(
        (
            repo_root,
            repo_root / "resume_graph_engine" / "src",
            repo_root / "outreach_engine" / "src",
        )
    ):
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)


def scan_untyped_public_retrieval_callables(repo_root: Path) -> list[dict[str, Any]]:
    """Fail-closed AST scan rejecting public functions/methods without return annotations."""
    missing: list[dict[str, Any]] = []
    for pkg in RETRIEVAL_PACKAGES:
        base = repo_root / pkg
        if not base.exists():
            continue
        for py_file in sorted(base.rglob("*.py")):
            rel = py_file.relative_to(repo_root).as_posix()
            if (
                "/tests/" in f"/{rel}"
                or "/artifacts/" in f"/{rel}"
                or py_file.name.startswith("test_")
                or py_file.name == "conftest.py"
            ):
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    if node.returns is None:
                        missing.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "callable": node.name,
                            }
                        )
    return missing


def _require_module(repo_root: Path, rel_path: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    mod, err = load_repo_module(repo_root, rel_path)
    if mod is None or err is not None:
        raise RuntimeError(err or f"Unable to load {rel_path}")
    return mod


def _probe_query_decomposition_and_intent_routing(repo_root: Path) -> dict[str, Any]:
    intent_mod = _require_module(repo_root, "apps_research/types/jd_intent_coverage.py")
    sr_mod = _require_module(repo_root, "apps_research/integrations/search_retrieval.py")

    ai_partner_jd = (
        "Lead strategic partnerships and co-sell alliances for enterprise AI agentic platform "
        "architecture with strict security compliance and risk governance."
    )
    inferred = intent_mod.infer_evidence_intents_from_text(ai_partner_jd)
    ids = set(intent_mod.intent_ids(inferred))
    families = set(intent_mod.required_families_for_intents(inferred))
    terms = set(intent_mod.signal_terms_for_intents(inferred))

    ambiguous_only = "Work closely with an internal design partner on UI typography."
    ambiguous_ids = set(intent_mod.intent_ids(intent_mod.infer_evidence_intents_from_text(ambiguous_only)))
    snap = sr_mod.retrieval_config_snapshot(query_families=sorted(families))

    gaps: list[str] = []
    expected_ids = {"partnerships", "platform_engineering", "security_trust", "applied_ai"}
    if not expected_ids.issubset(ids):
        gaps.append(f"Missing expected evidence intents: {expected_ids - ids}")
    if "partner_ecosystem" not in families or "tech_stack_and_tools" not in families:
        gaps.append(f"Required source families incomplete: {sorted(families)}")
    if not terms:
        gaps.append("Signal terms empty for inferred JD intents")
    if "partnerships" in ambiguous_ids:
        gaps.append("Ambiguous isolated word 'partner' falsely triggered partnerships intent")
    if snap.get("query_families") != sorted(families):
        gaps.append("retrieval_config_snapshot failed to preserve routed query families")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "inferred_intents": sorted(ids),
        "required_family_count": len(families),
    }


def _probe_chunking_and_context_window(repo_root: Path) -> dict[str, Any]:
    sr_mod = _require_module(repo_root, "apps_research/integrations/search_retrieval.py")
    prov_mod = _require_module(repo_root, "agents/context/provenance.py")
    budget_mod = _require_module(repo_root, "agents/context/budgeting.py")

    prefixed = sr_mod.apply_contextual_prefix(
        "Deployed hybrid retrieval with 42% lower p95 latency.",
        doc_title="Architecture Case Study",
        surrounding_text="Section 3: Retrieval Performance",
    )
    item_hi = prov_mod.ContextItem(
        source_id="src_case_study_1",
        source_type=prov_mod.ContextSourceType.RETRIEVED_EVIDENCE,
        content=prefixed,
        authority="verified",
        relevance_score=0.95,
    )
    item_lo = prov_mod.ContextItem(
        source_id="src_low_rel_2",
        source_type=prov_mod.ContextSourceType.EPHEMERAL_SCRATCH,
        content="Unrelated filler text " * 120,
        authority="advisory",
        relevance_score=0.15,
    )
    snap_a = prov_mod.ContextSnapshot(snapshot_id="snap_probe", items=(item_hi, item_lo), max_token_budget=4000)
    snap_b = prov_mod.ContextSnapshot(snapshot_id="snap_probe", items=(item_hi, item_lo), max_token_budget=4000)

    budget = budget_mod.TokenBudget(max_total_tokens=160, reserved_output_tokens=40)
    fitted_snap = budget.fit_items_to_budget([item_lo, item_hi])
    fitted = fitted_snap.items

    rre_mod = _require_module(repo_root, "apps_research/engines/research_retrieval_engine.py")
    prior_harness = os.environ.get("APPS_RG_TEST_HARNESS")
    os.environ["APPS_RG_TEST_HARNESS"] = "1"
    try:
        rre_engine = rre_mod.create_retrieval_engine(chromadb_path=None)
        rre_id_1 = rre_engine.index_research(
            content="Enterprise AI agentic platform architecture and partner ecosystem governance.",
            topic="AI Platform Strategy",
            artifact_mode="brief",
            quality_score=0.92,
            source_count=3,
            claim_types={"architecture": 4, "partnerships": 2},
            sources=["sec_10k", "gartner_mq", "partner_portal"],
        )
        rre_id_2 = rre_engine.index_research(
            content="Cloud data warehouse migration and governance roadmap.",
            topic="AI Platform Strategy",
            artifact_mode="brief",
            quality_score=0.86,
            source_count=2,
            claim_types={"architecture": 2, "security": 3},
            sources=["sec_10k", "cloud_blog"],
        )
        similar_res = rre_engine.find_similar_research("AI Platform Strategy", artifact_mode="brief", n_results=5)
        recs = rre_engine.recommend_sources("AI Platform Strategy", current_sources=["cloud_blog"])
        benchmark = rre_engine.get_quality_benchmark("brief")
    finally:
        if prior_harness is None:
            os.environ.pop("APPS_RG_TEST_HARNESS", None)
        else:
            os.environ["APPS_RG_TEST_HARNESS"] = prior_harness

    gaps: list[str] = []
    if "<document>Architecture Case Study</document>" not in prefixed:
        gaps.append("apply_contextual_prefix dropped document title envelope")
    if snap_a.provenance_digest != snap_b.provenance_digest:
        gaps.append("ContextSnapshot provenance_digest is non-deterministic")
    if len(fitted) != 1 or fitted[0].source_id != "src_case_study_1":
        gaps.append("TokenBudget.fit_items_to_budget failed to retain high-relevance evidence within cap")
    if not rre_id_1 or not rre_id_2 or len(similar_res) != 2:
        gaps.append("ResearchRetrievalEngine failed to index and retrieve multi-document artifacts")
    for rid, vec in rre_engine.store._embeddings.items():
        v_norm = sum(x * x for x in vec) ** 0.5
        if len(vec) != 1024 or abs(v_norm - 1.0) > 1e-4:
            gaps.append(
                f"InMemoryResearchStore vector {rid} violated 1024-d L2-normalized contract: "
                f"len={len(vec)}, norm={v_norm:.6f}"
            )
    if not recs or recs[0].get("source") != "sec_10k":
        gaps.append(f"ResearchRetrievalEngine.recommend_sources failed deterministic ranking: {recs}")
    if benchmark.get("sample_size") != 2:
        gaps.append(f"ResearchRetrievalEngine.get_quality_benchmark failed: {benchmark}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "provenance_digest": snap_a.provenance_digest[:16],
        "fitted_count": len(fitted),
        "research_similar_count": len(similar_res),
        "top_recommended_source": recs[0].get("source") if recs else "",
    }


def _probe_graph_and_embeddings(repo_root: Path) -> dict[str, Any]:
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

    emb_dirs: list[Path] = []
    for base in roots:
        emb_dirs.extend(
            [
                base / "artifacts/apps_rg/c03/graph_skill_embeddings",
                base / "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
                base / "resume_graph_engine/artifacts/apps_rg/c03/graph_skill_embeddings",
                base / "resume_graph_engine/artifacts/apps_rg/c03/graph_evidence_cluster_embeddings",
            ]
        )

    gaps: list[str] = []
    graph_res: dict[str, Any] = {}
    emb_res: dict[str, Any] = {}
    stage2_res: dict[str, Any] = {}
    trav_res: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="retrieval_aud_graph_") as td:
            active_db = db_path
            if not active_db.is_file():
                from apps_rg.fact_inventory.augmented_skills_graph_sqlite import materialize_augmented_skills_graph_sqlite

                active_db = Path(td) / "augmented_skills_graph.sqlite"
                materialize_augmented_skills_graph_sqlite(db_path=active_db)
            graph_res = graph_mod.verify_graph_database(active_db)
            emb_res = graph_mod.verify_bge_m3_embeddings(emb_dirs, active_db)
            stage2_res = graph_mod.verify_hybrid_retrieval_stage2(active_db)
            trav_res = trav_mod.run_resume_graph_traversal_probe(max_paths=100)
            from apps_rg.runtime.c0.c03_sqlite_graph_selection import select_c03_sqlite_graph_candidates
            from apps_rg.runtime.c03_graph_sqlite_context import ensure_c03_graph_sqlite

            rg_root = (repo_root / "resume_graph_engine") if (repo_root / "resume_graph_engine").is_dir() else repo_root
            sel_db = Path(td) / "c03_selection_probe.sqlite"
            ensure_c03_graph_sqlite(rg_root, sel_db)
            c03_sel = select_c03_sqlite_graph_candidates(
                section_id="executive_summary",
                selected_fact_ids=["fact_engineering_platform_001"],
                role_family_key="SVP_ENGINEERING_AI_PLATFORM",
                pillar_hints=["pillar_agentic_runtime_governance"],
                repo_root=rg_root,
                db_path=sel_db,
            )
            if not c03_sel.get("selected_candidates"):
                gaps.append("select_c03_sqlite_graph_candidates returned 0 selected_candidates for executive_summary")
            import sqlite3
            with sqlite3.connect(active_db) as conn:
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
                with sqlite3.connect(fv_fts) as fconn:
                    fts_count = fconn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
                    if fts_count < 328:
                        gaps.append(f"fact_vectors.db has only {fts_count} indexed rows (<328)")
        if trav_res.get("status") != "PASS":
            gaps.append("run_resume_graph_traversal_probe did not return PASS")
    except Exception as exc:  # guardian: allow-broad-exception -- capture graph/embedding verification failure into pillar gaps
        gaps.append(f"Graph/embedding verification failed: {exc}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "three_hop_paths": graph_res.get("three_hop_traversal_paths", 0),
        "verified_vectors": emb_res.get("verified_vectors_count", 0),
        "mean_cosine": emb_res.get("mean_cosine", 0.0),
        "stage2_top_assertion": stage2_res.get("top_assertion", ""),
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

    p1 = _probe_query_decomposition_and_intent_routing(root)
    p2 = _probe_chunking_and_context_window(root)
    p3 = _probe_graph_and_embeddings(root)
    p4 = _probe_citation_and_provenance_contract(root)
    p5 = _probe_fail_closed_abstention(root)
    p6 = _probe_latency_and_live_caching(root)
    untyped = scan_untyped_public_retrieval_callables(root)
    p7 = {
        "passed": len(untyped) == 0,
        "gaps": [f"Untyped public retrieval callable {u['callable']} at {u['file']}:{u['line']}" for u in untyped[:15]],
        "untyped_public_callable_count": len(untyped),
    }

    pillars = {
        "pillar_1_query_decomposition_and_intent_routing": p1,
        "pillar_2_chunking_and_context_window": p2,
        "pillar_3_graphdb_traversal_and_embeddings": p3,
        "pillar_4_provenance_and_citation_hygiene": p4,
        "pillar_5_empty_result_fail_closed_abstention": p5,
        "pillar_6_latency_and_live_multi_tier_caching": p6,
        "pillar_7_cross_subsystem_typing_contract": p7,
    }
    all_gaps: list[str] = []
    passing_count = 0
    for name, res in pillars.items():
        if res["passed"]:
            passing_count += 1
        for g in res.get("gaps", []):
            all_gaps.append(f"[{name}] {g}")

    is_clean = passing_count == len(pillars) and len(all_gaps) == 0
    return {
        "schema_version": "agents.retrieval_surface_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "read_only": read_only,
        "status": "PASS" if is_clean else "FAIL",
        "is_clean": is_clean,
        "passing_pillars": passing_count,
        "total_pillars": len(pillars),
        "total_gaps": len(all_gaps),
        "gaps": all_gaps,
        "pillars": pillars,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 7-pillar behavioral retrieval surface audit (Agent 4).")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT, help="Repository root to audit")
    parser.add_argument("--read-only", action="store_true", default=True, help="Run in hermetic read-only mode")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON receipt output path")
    parser.add_argument("--json", action="store_true", help="Emit JSON report on stdout")
    args = parser.parse_args(argv)

    report = run_retrieval_surface_audit(args.repo_root.resolve(), read_only=args.read_only)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["is_clean"] else "FAIL"
        print(
            f"[{status}] Retrieval Surface Audit: {report['passing_pillars']}/{report['total_pillars']} "
            f"pillars passing (gaps={report['total_gaps']})"
        )
        for gap in report["gaps"]:
            print(f"  - {gap}")

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
