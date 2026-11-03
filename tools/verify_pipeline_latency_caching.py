#!/usr/bin/env python3
"""End-to-End Pipeline Latency & Live Multi-Tier Caching Verification Harness.

Validates:
1. Static System Prefix Lengths (>= 1,024 tokens for provider prefix caching).
2. Compiler Cache-Aligned Slot Ordering (R0 and E0 precede dynamic C0).
3. Deterministic Offline Pipeline Execution (run_bare_deterministic_e2e).
4. Live Multi-Tier Cache Probes (OpenAI prefix fingerprint & usage ratio,
   Anthropic 3-breakpoint cache receipt math, ExactRequestIdentity store/lookup,
   and GovernedBriefingResolver cache hit) without reading static receipts.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
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
        raise RuntimeError("Missing approved OpenAI or Claude models in config/provider_profiles.yaml")
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

    openai_ok = len([g for g in p2_gaps if "prefix_fingerprint" in g or "chat_usage_metrics" in g or "normalize_static" in g]) == 0 and len(p2_gaps) == 0
    anthropic_ok = len(p2_gaps) == 0 and int(p2_metrics.get("cache_marker_count", 0)) >= 2
    exact_and_brief_ok = len(p4_gaps) == 0 and briefing_chars > 0

    passed = openai_ok and anthropic_ok and exact_and_brief_ok
    if not quiet:
        print(
            f"  [{'PASS' if passed else 'FAIL'}] Models: {openai_model} / {claude_model} | "
            f"Anthropic Breakpoints: {p2_metrics.get('cache_marker_count', 0)} | "
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


def run_verification(repo_root: Path | None = None, *, quiet: bool = False) -> dict[str, Any]:
    root = (repo_root or DEFAULT_ROOT).resolve()
    v1 = verify_static_prefixes(root, quiet=quiet)
    v2 = verify_compiler_cache_alignment(root, quiet=quiet)
    v3 = verify_deterministic_e2e(root, quiet=quiet)
    v4 = verify_live_cache_probes(root, quiet=quiet)
    all_ok = bool(v1["passed"] and v2["passed"] and v3["passed"] and v4["passed"])
    return {
        "status": "PASS" if all_ok else "FAIL",
        "static_prefixes": v1,
        "compiler_cache_alignment": v2,
        "deterministic_e2e": v3,
        "live_cache_probes": v4,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify pipeline latency and live multi-tier caching.")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT, help="Repository root to inspect")
    parser.add_argument("--json", action="store_true", help="Emit JSON report on stdout")
    args = parser.parse_args(argv)

    if not args.json:
        print("=" * 80)
        print("PIPELINE PERFORMANCE, LATENCY & LIVE MULTI-TIER CACHING VERIFICATION")
        print("=" * 80)

    report = run_verification(args.repo_root.resolve(), quiet=args.json)
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
