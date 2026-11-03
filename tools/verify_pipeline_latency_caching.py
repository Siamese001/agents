#!/usr/bin/env python3
"""End-to-End Pipeline Latency & Live Multi-Tier Caching Verification Harness.

Validates:
1. Static System Prefix Lengths (>= 1,024 tokens for provider prefix caching).
2. Compiler Cache-Aligned Slot Ordering (R0 and E0 precede dynamic C0).
3. Deterministic Offline Pipeline Execution (run_bare_deterministic_e2e).
4. Live Multi-Tier Cache Probes (prefix fingerprint & usage ratio,
   3-breakpoint cache receipt math, ExactRequestIdentity store/lookup,
   and GovernedBriefingResolver cache hit) without reading static receipts.
5. Wave 5 Pre-Research Whole-Run Fast Cache (< 5.0s warm hit, 0 provider calls,
   exact output SHA-256 parity, modified-JD miss, and --no-cache bypass).
6. Wave 5 Content-Addressed Section Lane Cache (< 1.0s per unchanged lane,
   0 provider calls on unchanged lanes, selective invalidation on partial edit).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_paths(repo_root: Path) -> None:
    candidates = (
        repo_root,
        repo_root / "resume_graph_engine" / "src",
        repo_root / "outreach_engine" / "src",
    )
    for p in reversed(candidates):
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)


def _approved_models(repo_root: Path) -> tuple[str, str]:
    profiles_path = repo_root / "config" / "provider_profiles.yaml"
    data = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    profiles = data.get("profiles") or {}
    openai_models = (profiles.get("external_openai_generator") or {}).get("model_by_section") or {}
    claude_models = (profiles.get("external_claude_generator") or {}).get("model_by_section") or {}
    if not openai_models or not claude_models:
        raise RuntimeError("Missing approved generator models in config/provider_profiles.yaml")
    return str(next(iter(openai_models.values()))), str(next(iter(claude_models.values())))


def _require_module(repo_root: Path, rel_path: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    mod, err = load_repo_module(repo_root, rel_path)
    if mod is None or err is not None:
        raise RuntimeError(err or f"Unable to load {rel_path}")
    return mod


def verify_static_prefixes(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)

    cb_mod = _require_module(root, "apps_research/prompt_assembly/company_brief_prompts.py")
    bp_mod = _require_module(root, "resume_graph_engine/src/apps_rg/prompt_assembly/bare_prompts.py")

    prompts = {
        "BARE_PIPELINE_L2_SYSTEM_PROMPT": str(bp_mod.BARE_PIPELINE_L2_SYSTEM_PROMPT),
        "BARE_PIPELINE_RESEARCH_SYSTEM_PROMPT": str(bp_mod.BARE_PIPELINE_RESEARCH_SYSTEM_PROMPT),
        "COMPANY_BRIEF_STATIC_SYSTEM_PROMPT": str(cb_mod.COMPANY_BRIEF_STATIC_SYSTEM_PROMPT),
    }
    details: dict[str, dict[str, Any]] = {}
    all_passed = True
    if not quiet:
        print("\n--- 1. Verifying Static Prefix Lengths (>= 1,024 tokens) ---")
    for name, p_text in prompts.items():
        char_len = len(p_text)
        est_tokens = int(char_len / 4.0)
        passes = char_len >= 4000
        details[name] = {"chars": char_len, "est_tokens": est_tokens, "passed": passes}
        if not quiet:
            print(f"  [{'PASS' if passes else 'FAIL'}] {name}: {char_len} chars, ~{est_tokens} est tokens")
        if not passes:
            all_passed = False
    return {"passed": all_passed, "prompts": details}


def verify_compiler_cache_alignment(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)

    comp_mod = _require_module(root, "resume_graph_engine/src/apps_rg/prompt_assembly/compiler.py")
    order = tuple(comp_mod.CACHE_ALIGNED_SLOT_ORDER)
    ca_c0 = order.index("C0")
    ca_r0 = order.index("R0")
    ca_e0 = order.index("E0")
    passed = (ca_r0 < ca_c0) and (ca_e0 < ca_c0)
    if not quiet:
        print("\n--- 2. Verifying Compiler Cache-Aligned Slot Ordering ---")
        print(
            f"  [{'PASS' if passed else 'FAIL'}] Schema (R0={ca_r0}) and Examples (E0={ca_e0}) "
            f"precede Dynamic Evidence (C0={ca_c0})"
        )
    return {"passed": passed, "slot_order": list(order), "r0_index": ca_r0, "e0_index": ca_e0, "c0_index": ca_c0}


def verify_deterministic_e2e(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)
    from apps_rg.bare_pipeline import evaluate_bare_run, run_bare_deterministic_e2e

    if not quiet:
        print("\n--- 3. Verifying Deterministic Offline E2E Pipeline ---")
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vplc_bare_e2e_") as td:
        result = run_bare_deterministic_e2e(artifact_root=td)
        elapsed = round(time.perf_counter() - t0, 3)
        status = result.get("status")
        outcome = result.get("outcome_label")
        eval_res = evaluate_bare_run(result["artifact_dir"]) if status == "SUCCESS" else {"status": "FAIL"}
    passed = (
        status == "SUCCESS"
        and outcome == "DETERMINISTIC_OFFLINE_PASS"
        and eval_res.get("status") == "PASS"
    )
    if not quiet:
        print(f"  [{'PASS' if passed else 'FAIL'}] run_bare_deterministic_e2e: {status} ({outcome}) in {elapsed}s")
    return {
        "passed": passed,
        "status": status,
        "outcome_label": outcome,
        "evaluation_status": eval_res.get("status"),
        "elapsed_seconds": elapsed,
    }


def verify_live_cache_probes(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    """Execute live in-memory multi-tier cache verification without reading static receipts."""
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)
    from tools.cost_token_budget_probes import run_pillar_2_live_probes, run_pillar_4_live_probes

    if not quiet:
        print("\n--- 4. Verifying Live In-Memory Multi-Tier Cache Probes ---")

    openai_model, claude_model = _approved_models(root)
    p2_gaps, p2_metrics = run_pillar_2_live_probes(root, claude_model=claude_model, openai_model=openai_model)
    p4_gaps, briefing_chars = run_pillar_4_live_probes(root, model_pin=openai_model)

    openai_ok = (
        len([g for g in p2_gaps if "prefix_fingerprint" in g or "chat_usage_metrics" in g or "normalize_static" in g])
        == 0
        and len(p2_gaps) == 0
    )
    anthropic_ok = len(p2_gaps) == 0 and int(p2_metrics.get("cache_marker_count", 0)) >= 2
    exact_and_brief_ok = len(p4_gaps) == 0 and briefing_chars > 0

    passed = openai_ok and anthropic_ok and exact_and_brief_ok
    if not quiet:
        print(
            f"  [{'PASS' if passed else 'FAIL'}] Models: {openai_model} / {claude_model} | "
            f"Breakpoints: {p2_metrics.get('cache_marker_count', 0)} | "
            f"Exact & Briefing Gaps: {len(p4_gaps)}"
        )
    return {
        "passed": passed,
        "approved_model": openai_model,
        "approved_claude_model": claude_model,
        "openai_prefix_ok": openai_ok,
        "anthropic_breakpoint_ok": anthropic_ok,
        "exact_and_briefing_ok": exact_and_brief_ok,
        "gaps": p2_gaps + p4_gaps,
    }


def _seed_authorized_whole_run(source_dir: Path, parent_run_id: str) -> str:
    (source_dir / "outputs").mkdir(parents=True, exist_ok=True)
    resume_payload = {
        "schema_version": "apps_rg.generated_resume.v1",
        "headline": "SVP Engineering | Partner Ecosystem Accelerators | Governed Platform Architecture | Distributed Lakehouse Infrastructure",
        "parent_run_id": parent_run_id,
    }
    resume_bytes = (json.dumps(resume_payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (source_dir / "outputs" / "generated_resume.json").write_bytes(resume_bytes)
    (source_dir / "FINAL_RESUME_OUTPUT.json").write_text(
        json.dumps({"status": "PASS", "authorized": True}, indent=2) + "\n", encoding="utf-8"
    )
    (source_dir / "apps_rg_pipeline_completion_receipt.json").write_text(
        json.dumps({"pipeline_complete": True, "parent_run_id": parent_run_id}, indent=2) + "\n",
        encoding="utf-8",
    )
    (source_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps({"authorized": True}, indent=2) + "\n", encoding="utf-8"
    )
    (source_dir / "x3_disposition_receipt.json").write_text(
        json.dumps({"x3_disposition": "X3D_ALLOW_FINISH"}, indent=2) + "\n", encoding="utf-8"
    )
    (source_dir / "runtime_identity_envelope.json").write_text(
        json.dumps({"parent_run_id": parent_run_id}, indent=2) + "\n", encoding="utf-8"
    )
    eval_dir = source_dir / "apps_eval" / "whole_run"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "eval_record.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "verdict": "PASS",
                "parent_run_id": parent_run_id,
                "scorecard": {"verdict": "PASS", "status": "PASS"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(resume_bytes).hexdigest()


def verify_whole_run_fast_cache(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    """Verify Wave 5 pre-research whole-run fast cache (< 5.0s, 0 model calls, invalidation, no-cache)."""
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)
    from apps_rg.__main__ import _evaluate_product_run
    from apps_rg.cache.whole_run_fast_cache import (
        stamp_authorized_whole_run_r1a,
        try_serve_pre_research_whole_run_cache_hit,
    )
    from apps_rg.runtime.orchestration.canonical_dispatch import build_raw_request_for_r4

    if not quiet:
        print("\n--- 5. Verifying Pre-Research Whole-Run Fast Cache (< 5.0s) ---")

    prev_no_cache = os.environ.pop("APPS_RG_NO_CACHE", None)
    prev_fresh = os.environ.pop("APPS_RG_REQUIRE_FRESH_RUN", None)
    try:
        with tempfile.TemporaryDirectory(prefix="vplc_wholerun_") as td:
            runs_dir = Path(td) / "runtime_proofs"
            origin_dir = runs_dir / "full_resume_origin000001"
            warm_dir = runs_dir / "full_resume_warm00000002"
            mod_dir = runs_dir / "full_resume_mod000000003"
            nocache_dir = runs_dir / "full_resume_nocache00004"
            for d in (origin_dir, warm_dir, mod_dir, nocache_dir):
                d.mkdir(parents=True, exist_ok=True)

            origin_sha = _seed_authorized_whole_run(origin_dir, "apps-rg-origin-001")
            jd_text = "Partner AI Architecture Lead driving hyperscaler alliances and enterprise production adoption."
            resume_text = "SVP Engineering leading 106 engineers across analytics, lakehouse, and AI delivery."
            raw_req = build_raw_request_for_r4(
                target_company="Anthropic",
                target_role="Manager of Applied AI Architecture, Partnerships",
                target_level="Manager",
                jd="",
                job_description_ref="",
                job_description_text=jd_text,
                manual_brief="",
                resume_path="",
                source_resume_text=resume_text,
                generation_mode="strategic_tailor",
            )
            raw_req["caller_brief_hash"] = str(raw_req.get("brief_hash") or "")
            stamped = stamp_authorized_whole_run_r1a(raw_request=raw_req, artifact_dir=origin_dir)

            t0 = time.perf_counter()
            warm_res = try_serve_pre_research_whole_run_cache_hit(
                art=warm_dir,
                target_company="Anthropic",
                target_role="Manager of Applied AI Architecture, Partnerships",
                target_level="Manager",
                jd="",
                job_description_ref="",
                job_description_text=jd_text,
                manual_brief="",
                resume_path="",
                source_resume_text=resume_text,
                generation_mode="strategic_tailor",
                require_fresh_preflight=True,
                stage_ledger=None,
            )
            warm_elapsed = round(time.perf_counter() - t0, 4)
            warm_eval = _evaluate_product_run(warm_dir)
            warm_out = warm_dir / "outputs" / "generated_resume.json"
            warm_sha = hashlib.sha256(warm_out.read_bytes()).hexdigest() if warm_out.is_file() else ""

            mod_res = try_serve_pre_research_whole_run_cache_hit(
                art=mod_dir,
                target_company="Anthropic",
                target_role="Manager of Applied AI Architecture, Partnerships",
                target_level="Manager",
                jd="",
                job_description_ref="",
                job_description_text=jd_text + " Plus new Kubernetes multi-region requirement.",
                manual_brief="",
                resume_path="",
                source_resume_text=resume_text,
                generation_mode="strategic_tailor",
                require_fresh_preflight=True,
                stage_ledger=None,
            )

            os.environ["APPS_RG_NO_CACHE"] = "1"
            nocache_res = try_serve_pre_research_whole_run_cache_hit(
                art=nocache_dir,
                target_company="Anthropic",
                target_role="Manager of Applied AI Architecture, Partnerships",
                target_level="Manager",
                jd="",
                job_description_ref="",
                job_description_text=jd_text,
                manual_brief="",
                resume_path="",
                source_resume_text=resume_text,
                generation_mode="strategic_tailor",
                require_fresh_preflight=True,
                stage_ledger=None,
            )
    finally:
        if prev_no_cache is None:
            os.environ.pop("APPS_RG_NO_CACHE", None)
        else:
            os.environ["APPS_RG_NO_CACHE"] = prev_no_cache
        if prev_fresh is None:
            os.environ.pop("APPS_RG_REQUIRE_FRESH_RUN", None)
        else:
            os.environ["APPS_RG_REQUIRE_FRESH_RUN"] = prev_fresh

    passed = bool(
        stamped
        and isinstance(warm_res, dict)
        and warm_res.get("cache_hit") is True
        and int(warm_res.get("provider_call_count", -1)) == 0
        and warm_elapsed < 5.0
        and warm_eval.get("status") == "PASS"
        and warm_sha == origin_sha
        and mod_res is None
        and nocache_res is None
    )
    if not quiet:
        print(
            f"  [{'PASS' if passed else 'FAIL'}] Warm Hit: {warm_elapsed}s (< 5.0s) | "
            f"Eval: {warm_eval.get('status')} | SHA Match: {warm_sha == origin_sha} | "
            f"Modified-JD Miss: {mod_res is None} | No-Cache Bypass: {nocache_res is None}"
        )
    return {
        "passed": passed,
        "warm_elapsed_seconds": warm_elapsed,
        "provider_call_count": 0 if isinstance(warm_res, dict) else -1,
        "warm_eval_status": warm_eval.get("status"),
        "sha256_match": warm_sha == origin_sha,
        "origin_sha256": origin_sha,
        "modified_jd_missed": mod_res is None,
        "no_cache_bypassed": nocache_res is None,
    }


def _write_valid_lane_bundle(repo: Path, lane_dir: Path, lane: str, provider_profile: str, version_tag: str) -> None:
    lane_dir.mkdir(parents=True, exist_ok=True)
    rel = lane_dir.resolve().relative_to(repo.resolve()).as_posix()
    (lane_dir / "l2_output.json").write_text(
        json.dumps(
            {
                "runtime_generation_status": "REAL_LLM",
                "product_quality_status": "PASS",
                "section_id": lane,
                "version_tag": version_tag,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (lane_dir / "provider_request.json").write_text(
        json.dumps({"provider_requested": provider_profile}, indent=2) + "\n", encoding="utf-8"
    )
    (lane_dir / "x3_disposition.json").write_text(
        json.dumps({"x3_code": "X3_ALLOW", "x3_disposition": "X3_ALLOW"}, indent=2) + "\n",
        encoding="utf-8",
    )
    ptr = {
        "run_id": f"{lane}_{version_tag}",
        "run_dir": rel,
        "provider_requested": provider_profile,
        "runtime_generation_status": "REAL_LLM",
        "section_id": lane,
    }
    for name in ("latest_successful_real_run.json", "latest_real_run.json"):
        (lane_dir / name).write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")


def verify_partial_section_cache(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    """Verify Wave 5 section-lane cache reuses unchanged lanes (< 1.0s) and invalidates edited role + dependents."""
    root = (repo_root or DEFAULT_ROOT).resolve()
    _ensure_paths(root)
    from apps_rg.cache.section_lane_cache import dispatch_lane_with_section_cache
    from apps_rg.runtime.c0.resume_graph_allocation import SECTION_EVIDENCE_CONTRACTS_ENV
    from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
    from apps_rg.runtime.product_output_policy import lane_run_dir_meets_product_bar
    from apps_rg.runtime.runtime_proof_layout import ACCEPTED_REAL_LLM_PROVIDER_PROFILES

    if not quiet:
        print("\n--- 6. Verifying Partial-Edit Section Lane Cache Reuse (< 1.0s/hit) ---")

    provider_profile = sorted(ACCEPTED_REAL_LLM_PROVIDER_PROFILES)[0]
    prev_env = {
        k: os.environ.get(k)
        for k in (
            "APPS_RG_SECTION_CACHE_ENABLE",
            "APPS_RG_SECTION_CACHE_ROOT",
            "APPS_RG_NO_CACHE",
            SECTION_EVIDENCE_CONTRACTS_ENV,
        )
    }
    try:
        with tempfile.TemporaryDirectory(prefix="vplc_seccache_") as td:
            base = Path(td)
            fake_repo = base / "resume_graph_engine"
            cache_root = fake_repo / "artifacts" / "apps_rg" / "cache" / "section_lanes_v1"
            run1_sections = fake_repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_r1" / "lanes"
            run2_sections = fake_repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_r2" / "lanes"
            contracts_path = base / "section_contracts.json"

            def _write_contracts(ibm_fact: str, global_plan_digest: str) -> None:
                doc = {}
                for lane in GENERATED_LANES:
                    fact = ibm_fact if lane == "ibm_bullets" else f"fact_{lane}_v1"
                    doc[lane] = {
                        "allocation_plan_digest": global_plan_digest,
                        "source_section_plan_digest": f"plan_{lane}_{fact}",
                        "graph_digest": "graph_v1",
                        "representation_mode": "WHOLE_RESUME",
                        "assignments": [{"claim_unit_id": f"{lane}:01", "fact_id": fact, "selection_margin": 0.25}],
                    }
                contracts_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

            os.environ["APPS_RG_SECTION_CACHE_ENABLE"] = "1"
            os.environ["APPS_RG_SECTION_CACHE_ROOT"] = str(cache_root)
            os.environ.pop("APPS_RG_NO_CACHE", None)
            os.environ[SECTION_EVIDENCE_CONTRACTS_ENV] = str(contracts_path)

            _write_contracts("fact_ibm_v1", "global_digest_v1")
            run1_calls: list[str] = []

            def _dispatch_run1(**kw: Any) -> dict[str, Any]:
                sec = str(kw["section"])
                run1_calls.append(sec)
                _write_valid_lane_bundle(fake_repo, Path(kw["artifact_dir"]), sec, provider_profile, "v1")
                return {"exit_status": "success", "x3_disposition": "X3_ALLOW_FINISH"}

            for lane in GENERATED_LANES:
                dispatch_lane_with_section_cache(
                    dispatch_fn=_dispatch_run1,
                    repo=fake_repo,
                    sections_root=run1_sections,
                    kwargs={
                        "section": lane,
                        "artifact_dir": str(run1_sections / lane),
                        "target_company": "Anthropic",
                        "target_role": "Manager of Applied AI Architecture, Partnerships",
                        "job_description_text": "Partner AI Architecture Lead",
                        "lane_provider": provider_profile,
                        "lane_x1d_judges": "panel",
                    },
                )

            # Simulate partial edit to ONLY ibm_bullets (global_plan_digest also shifts across all sections)
            _write_contracts("fact_ibm_EDITED_v2", "global_digest_v2")
            run2_calls: list[str] = []
            hit_latencies: dict[str, float] = {}
            product_bar_ok = True

            def _dispatch_run2(**kw: Any) -> dict[str, Any]:
                sec = str(kw["section"])
                run2_calls.append(sec)
                _write_valid_lane_bundle(fake_repo, Path(kw["artifact_dir"]), sec, provider_profile, "v2")
                return {"exit_status": "success", "x3_disposition": "X3_ALLOW_FINISH"}

            t_partial_start = time.perf_counter()
            for lane in GENERATED_LANES:
                t_lane = time.perf_counter()
                res = dispatch_lane_with_section_cache(
                    dispatch_fn=_dispatch_run2,
                    repo=fake_repo,
                    sections_root=run2_sections,
                    kwargs={
                        "section": lane,
                        "artifact_dir": str(run2_sections / lane),
                        "target_company": "Anthropic",
                        "target_role": "Manager of Applied AI Architecture, Partnerships",
                        "job_description_text": "Partner AI Architecture Lead",
                        "lane_provider": provider_profile,
                        "lane_x1d_judges": "panel",
                    },
                )
                dt = round(time.perf_counter() - t_lane, 4)
                if res.get("section_cache_hit"):
                    hit_latencies[lane] = dt
                ok, _ = lane_run_dir_meets_product_bar(run2_sections / lane)
                if not ok:
                    product_bar_ok = False
            partial_elapsed = round(time.perf_counter() - t_partial_start, 4)
    finally:
        for k, v in prev_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    expected_hits = {
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "insurtech_bullets",
        "slalom_narrative",
        "unify_narrative",
        "insurtech_narrative",
    }
    expected_misses = {"ibm_bullets", "ibm_narrative", "headline", "executive_summary"}
    max_hit_s = max(hit_latencies.values()) if hit_latencies else 999.0
    passed = (
        len(run1_calls) == 11
        and set(hit_latencies.keys()) == expected_hits
        and set(run2_calls) == expected_misses
        and max_hit_s < 1.0
        and partial_elapsed < 65.0
        and product_bar_ok
    )
    if not quiet:
        print(
            f"  [{'PASS' if passed else 'FAIL'}] Unchanged Lane Hits: {len(hit_latencies)}/7 "
            f"(max {max_hit_s}s < 1.0s) | Re-executed Dependents: {sorted(run2_calls)} | "
            f"Total Partial Elapsed: {partial_elapsed}s"
        )
    return {
        "passed": passed,
        "unchanged_lane_hits": sorted(hit_latencies.keys()),
        "reexecuted_lanes": sorted(run2_calls),
        "max_hit_seconds": max_hit_s,
        "partial_elapsed_seconds": partial_elapsed,
        "product_bar_ok": product_bar_ok,
    }


def run_verification(
    repo_root: Path | None = None,
    *,
    quiet: bool = False,
    mode: str = "all",
) -> dict[str, Any]:
    root = (repo_root or DEFAULT_ROOT).resolve()
    checks: dict[str, dict[str, Any]] = {}
    if mode in ("legacy", "all"):
        checks["static_prefixes"] = verify_static_prefixes(root, quiet=quiet)
        checks["compiler_cache_alignment"] = verify_compiler_cache_alignment(root, quiet=quiet)
        checks["deterministic_e2e"] = verify_deterministic_e2e(root, quiet=quiet)
        checks["live_cache_probes"] = verify_live_cache_probes(root, quiet=quiet)
    if mode in ("whole-run", "all"):
        checks["whole_run_fast_cache"] = verify_whole_run_fast_cache(root, quiet=quiet)
    if mode in ("partial-section-cache", "all"):
        checks["partial_section_cache"] = verify_partial_section_cache(root, quiet=quiet)
    all_ok = bool(checks) and all(bool(v.get("passed")) for v in checks.values())
    return {"status": "PASS" if all_ok else "FAIL", "mode": mode, **checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify pipeline latency and live multi-tier caching.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT, help="Repository root to inspect")
    parser.add_argument(
        "--mode",
        choices=("legacy", "whole-run", "partial-section-cache", "all"),
        default="all",
        help="Verification subset to execute",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report on stdout")
    args = parser.parse_args(argv)

    if not args.json:
        print("=" * 80)
        print("PIPELINE PERFORMANCE, LATENCY & LIVE MULTI-TIER CACHING VERIFICATION")
        print("=" * 80)

    report = run_verification(args.repo_root.resolve(), quiet=args.json, mode=args.mode)
    all_ok = report["status"] == "PASS"

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n" + "=" * 80)
        print(f"FINAL OUTCOME: {'ALL GATES PASSED (100%)' if all_ok else 'VERIFICATION FAILED'}")
        print("=" * 80)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
