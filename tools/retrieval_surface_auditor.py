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
RETRIEVAL_PATH_RE = re.compile(r"(retriev|search|graph|rank|chunk|research|provenance|context)", re.IGNORECASE)
RETRIEVAL_PACKAGES = (
    "agents",
    "apps_research",
    "resume_graph_engine/src",
    "outreach_engine/src",
    "resume_engine",
    "infrastructure",
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
            if "/tests/" in f"/{rel}" or py_file.name.startswith("test_"):
                continue
            if not RETRIEVAL_PATH_RE.search(rel):
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

    gaps: list[str] = []
    if "<document>Architecture Case Study</document>" not in prefixed:
        gaps.append("apply_contextual_prefix dropped document title envelope")
    if snap_a.provenance_digest != snap_b.provenance_digest:
        gaps.append("ContextSnapshot provenance_digest is non-deterministic")
    if len(fitted) != 1 or fitted[0].source_id != "src_case_study_1":
        gaps.append("TokenBudget.fit_items_to_budget failed to retain high-relevance evidence within cap")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "provenance_digest": snap_a.provenance_digest[:16],
        "fitted_count": len(fitted),
    }


def _probe_graph_and_embeddings(repo_root: Path) -> dict[str, Any]:
    graph_mod = _require_module(repo_root, "tools/verify_graph_integrity_and_embeddings.py")
    trav_mod = _require_module(repo_root, "tools/run_resume_graph_traversal_probe.py")

    roots = [repo_root]
    if repo_root.parent.name == ".worktrees":
        primary = repo_root.parent.parent.resolve()
        if primary.is_dir():
            roots.append(primary)

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
        graph_res = graph_mod.verify_graph_database(db_path)
        emb_res = graph_mod.verify_bge_m3_embeddings(emb_dirs, db_path)
        stage2_res = graph_mod.verify_hybrid_retrieval_stage2()
        trav_res = trav_mod.run_resume_graph_traversal_probe(max_paths=100)
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
    leak_verdict = contract_mod.validate_targeting_brief_text(raw_citation_leak, profile="apps_lic")
    leak_rejected = (
        not bool(leak_verdict.valid)
        and "link_present" in leak_verdict.violations
        and "citation_present" in leak_verdict.violations
    )
    gaps = [] if leak_rejected else ["validate_targeting_brief_text failed to reject raw URL/citation leakage"]
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

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "failure_reason": getattr(res, "r5_reason_code", ""),
    }


def _probe_latency_and_live_caching(repo_root: Path) -> dict[str, Any]:
    vplc_mod = _require_module(repo_root, "tools/verify_pipeline_latency_caching.py")
    res = vplc_mod.run_verification(repo_root, quiet=True)
    gaps: list[str] = []
    if res.get("status") != "PASS":
        for section in ("static_prefixes", "compiler_cache_alignment", "deterministic_e2e", "live_cache_probes"):
            if not (res.get(section) or {}).get("passed"):
                gaps.append(f"verify_pipeline_latency_caching failed gate: {section}")
    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "live_cache_probes": res.get("live_cache_probes", {}),
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
