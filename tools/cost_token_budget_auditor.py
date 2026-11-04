#!/usr/bin/env python3
"""Agents Repository — 8-Pillar Behavioral Cost, Cache & Token Budget Auditor.

Executes live module probes across all 8 cost, cache, quarantine, trimming,
zero-LLM replay, and spend-governor pillars with zero source-substring checks.
Fails closed on configuration parse errors, behavioral drift, or ROI < 2.5x.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.cost_token_budget_governor_probes import (  # noqa: E402
    run_pillar_5_live_probes,
    run_pillar_6_live_probes,
    run_pillar_7_live_probes,
)
from tools.cost_token_budget_probes import (  # noqa: E402
    load_repo_module,
    load_yaml_strict,
    run_pillar_2_live_probes,
    run_pillar_3_live_probes,
    run_pillar_4_live_probes,
    verify_ast_compact_json_surface,
)

MIN_REQUIRED_ROI_MULTIPLE: float = 2.5


def _load_registry_pricing(repo_root: Path) -> tuple[dict[str, dict[str, float]], str | None]:
    """Strictly load per-model USD pricing from resume_graph_engine/config/models/registry.yaml."""
    reg_path = repo_root / "resume_graph_engine" / "config" / "models" / "registry.yaml"
    data, err = load_yaml_strict(reg_path)
    if err:
        return {}, err
    models = data.get("models")
    out: dict[str, dict[str, float]] = {}
    if isinstance(models, dict):
        for model_id, spec in models.items():
            if not isinstance(spec, dict) or not isinstance(spec.get("pricing"), dict):
                continue
            p = spec["pricing"]
            entry = {
                "input_cost_per_mtok": float(p.get("input_cost_per_mtok") or 0.0),
                "output_cost_per_mtok": float(p.get("output_cost_per_mtok") or 0.0),
                "cached_input_cost_per_mtok": float(p.get("cached_input_cost_per_mtok") or 0.0),
                "cache_write_multiplier": float(p.get("cache_write_multiplier") or 1.0),
            }
            out[str(model_id)] = entry
            snap = str(spec.get("snapshot_id") or "").strip()
            if snap:
                out[snap] = entry
    return out, None


def _verify_local_llm_catalog_ast(script_path: Path, catalog_path: Path) -> list[str]:
    """Verify via AST and JSON parsing that serve_qwen_m5.py resolves valid model_catalog.json."""
    gaps: list[str] = []
    if not catalog_path.is_file():
        gaps.append("Missing config/model_catalog.json")
    else:
        try:
            cat_doc = json.loads(catalog_path.read_text(encoding="utf-8"))
            if not isinstance(cat_doc, dict) or not cat_doc:
                gaps.append("config/model_catalog.json must be a non-empty JSON object")
        except Exception as exc:  # guardian: allow-broad-exception -- report malformed model catalog
            gaps.append(f"Malformed config/model_catalog.json: {exc}")

    if not script_path.is_file():
        gaps.append("Missing scripts/local_llm/serve_qwen_m5.py")
        return gaps

    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    except SyntaxError as exc:
        return gaps + [f"SyntaxError in scripts/local_llm/serve_qwen_m5.py: {exc}"]

    references_catalog = any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.endswith("model_catalog.json")
        for n in ast.walk(tree)
    )
    uses_json_loader = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"load", "loads"}
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "json"
        for n in ast.walk(tree)
    )
    if not (references_catalog and uses_json_loader):
        gaps.append("scripts/local_llm/serve_qwen_m5.py must parse config/model_catalog.json via json.load/loads")
    return gaps


def _audit_pillar_1_provider_pinning_and_effort(
    repo_root: Path,
    profiles_data: dict[str, Any],
    profiles_err: str | None,
    pricing_map: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Pillar 1: Provider profile pinning, effort right-sizing, and live model_pins resolver execution."""
    gaps: list[str] = []
    pinned_sections_count = 0
    low_effort_sections_count = 0

    if profiles_err or not profiles_data:
        gaps.append(profiles_err or "Missing or unreadable config/provider_profiles.yaml")
    else:
        ownership = profiles_data.get("model_pin_ownership") or {}
        if ownership.get("environment_model_override_allowed") is not False:
            gaps.append("config/provider_profiles.yaml must enforce environment_model_override_allowed: false")

        profiles = profiles_data.get("profiles") or {}
        for prof_key in ("external_openai_generator", "external_claude_generator"):
            prof = profiles.get(prof_key) or {}
            models_by_sec = prof.get("model_by_section") or {}
            efforts_by_sec = prof.get("effort_by_section") or {}
            if not models_by_sec:
                gaps.append(f"{prof_key} missing explicit model_by_section pins")
            if not efforts_by_sec:
                gaps.append(f"{prof_key} missing explicit effort_by_section bounds")
            for sec, model_id in models_by_sec.items():
                if pricing_map and str(model_id) not in pricing_map:
                    gaps.append(f"{prof_key}.{sec} pins unpriced/unknown model '{model_id}'")
            for sec, eff in efforts_by_sec.items():
                pinned_sections_count += 1
                if str(eff).strip().lower() == "low":
                    low_effort_sections_count += 1
                else:
                    gaps.append(f"{prof_key}.{sec} effort '{eff}' exceeds 'low' compact schema generation tier")

        selectors = profiles_data.get("selector_models") or {}
        for sel_name in ("competencies_graph_pool_selector", "employment_bullet_pool_selector"):
            sel = selectors.get(sel_name) or {}
            sel_model = str(sel.get("model") or "").strip()
            if not sel_model:
                gaps.append(f"selector_models.{sel_name} missing explicit model pin")
            elif pricing_map and sel_model not in pricing_map:
                gaps.append(f"selector_models.{sel_name} pins unpriced model '{sel_model}'")
            if str(sel.get("reasoning_effort") or "").lower() != "low":
                gaps.append(f"selector_models.{sel_name} reasoning_effort must be 'low'")

    outreach_profiles, outreach_err = load_yaml_strict(repo_root / "outreach_engine" / "config" / "provider_profiles.yaml")
    if outreach_err or not outreach_profiles:
        gaps.append(outreach_err or "Missing outreach_engine/config/provider_profiles.yaml")
    else:
        for role_name, role_cfg in (outreach_profiles.get("profiles") or {}).items():
            if not isinstance(role_cfg, dict):
                continue
            rmodel = str(role_cfg.get("model") or "").strip()
            if not rmodel or (pricing_map and rmodel not in pricing_map):
                gaps.append(f"outreach_engine.{role_name} pins unpriced or legacy model '{rmodel}'")
            if role_name == "rubric_judge_panel" and rmodel != "claude-haiku-4-5-20251001":
                gaps.append(f"outreach_engine.rubric_judge_panel should be right-sized to 'claude-haiku-4-5-20251001', got '{rmodel}'")

    reg_data, reg_err = load_yaml_strict(repo_root / "resume_graph_engine" / "config" / "models" / "registry.yaml")
    if not reg_err and isinstance(reg_data, dict):
        roles_map = reg_data.get("roles") or {}
        voice_repair = roles_map.get("repair.executive_voice") or {}
        if str(voice_repair.get("model") or "") != "claude-haiku-4-5-20251001":
            gaps.append("roles.repair.executive_voice must be right-sized to claude-haiku-4-5-20251001")
        std_oa = ((roles_map.get("proof_judge.standard.openai_chatgpt") or {}).get("params") or {})
        if str(std_oa.get("reasoning_effort") or "") != "low":
            gaps.append("roles.proof_judge.standard.openai_chatgpt reasoning_effort must be right-sized to 'low'")

    pins_mod, pin_err = load_repo_module(repo_root, "apps_research/config/model_pins.py")
    if pin_err or pins_mod is None:
        gaps.append(pin_err or "Missing apps_research/config/model_pins.py")
    else:
        try:
            gen_pin = pins_mod.company_brief_generation_pin()
            judge_pin = pins_mod.apps_rg_handoff_judge_pin()
            if gen_pin.provider != "external_openai" or not gen_pin.model:
                gaps.append(f"company_brief_generation_pin invalid: {gen_pin}")
            if judge_pin.provider != "google_gemini" or judge_pin.reasoning_effort != "high":
                gaps.append(f"apps_rg_handoff_judge_pin invalid: {judge_pin}")
        except Exception as exc:  # guardian: allow-broad-exception -- report pin resolver failure
            gaps.append(f"apps_research/config/model_pins.py execution failed: {type(exc).__name__}: {exc}")

    gaps.extend(
        _verify_local_llm_catalog_ast(
            repo_root / "scripts" / "local_llm" / "serve_qwen_m5.py",
            repo_root / "config" / "model_catalog.json",
        )
    )

    return {
        "pillar": "1_provider_pinning_and_effort_right_sizing",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "pinned_sections_count": pinned_sections_count,
        "low_effort_sections_count": low_effort_sections_count,
        "gaps": gaps,
    }


def compute_caching_roi_benchmark(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Compute Pareto cost and token savings from live executed cache receipts, briefing hits, and pricing."""
    root = Path(repo_root).resolve()
    profiles_data, _ = load_yaml_strict(root / "config" / "provider_profiles.yaml")
    pricing_map, _ = _load_registry_pricing(root)

    profiles = (profiles_data.get("profiles") or {}) if isinstance(profiles_data, dict) else {}
    openai_sections = ((profiles.get("external_openai_generator") or {}).get("model_by_section")) or {}
    claude_sections = ((profiles.get("external_claude_generator") or {}).get("model_by_section")) or {}
    openai_lanes = len(openai_sections)
    claude_lanes = len(claude_sections)
    total_lanes = openai_lanes + claude_lanes
    if total_lanes == 0 or not pricing_map:
        return {
            "pricing_source": "missing_configuration",
            "section_lanes_evaluated": 0,
            "total_uncached_equivalent_tokens": 0,
            "total_cached_equivalent_tokens": 0,
            "token_savings_equivalent": 0,
            "token_savings_pct": 0.0,
            "uncached_input_cost_usd": 0.0,
            "cached_input_cost_usd": 0.0,
            "input_cost_savings_usd": 0.0,
            "cost_reduction_multiple": 0.0,
            "quality_preservation_factor": 0.0,
            "roi_multiple": 0.0,
            "min_required_roi_multiple": MIN_REQUIRED_ROI_MULTIPLE,
            "roi_gate_passed": False,
        }

    claude_model = str(next(iter(claude_sections.values())))
    openai_model = str(next(iter(openai_sections.values())))
    judge_cfg = ((profiles_data.get("judge_models") or {}).get("standard")) or {}
    gemini_judge_model = str(judge_cfg.get("gemini_pro") or openai_model)
    openai_judge_model = str(judge_cfg.get("openai_chatgpt") or openai_model)

    tc_mod, tc_err = load_repo_module(root, "apps_model_telemetry/token_counter.py")
    apc_mod, apc_err = load_repo_module(
        root,
        "resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py",
    )
    prc_mod, prc_err = load_repo_module(root, "apps_model_telemetry/pricing.py")
    bcache_mod, bc_err = load_repo_module(root, "resume_graph_engine/src/apps_rg/cache/briefing_cache.py")
    p5_gaps, p5_metrics = run_pillar_5_live_probes(root)

    if any((tc_err, apc_err, prc_err, bc_err)) or not all((tc_mod, apc_mod, prc_mod, bcache_mod)):
        return {
            "pricing_source": "module_load_failed",
            "section_lanes_evaluated": total_lanes,
            "total_uncached_equivalent_tokens": 0,
            "total_cached_equivalent_tokens": 0,
            "token_savings_equivalent": 0,
            "token_savings_pct": 0.0,
            "uncached_input_cost_usd": 0.0,
            "cached_input_cost_usd": 0.0,
            "input_cost_savings_usd": 0.0,
            "cost_reduction_multiple": 0.0,
            "quality_preservation_factor": 0.0,
            "roi_multiple": 0.0,
            "min_required_roi_multiple": MIN_REQUIRED_ROI_MULTIPLE,
            "roi_gate_passed": False,
        }

    # Measure real token lengths from repository targeting and claim-eligibility files
    targeting_dir = root / "resume_graph_engine" / "src" / "apps_rg" / "config" / "targeting"
    brief_files = sorted(targeting_dir.glob("*_briefing.md"))[:6] if targeting_dir.is_dir() else []
    jd_files = sorted(targeting_dir.glob("*_jd.txt"))[:6] if targeting_dir.is_dir() else []
    claims_file = root / "resume_graph_engine" / "src" / "apps_rg" / "config" / "fact_inventory" / "commercial_claim_eligibility.yaml"

    brief_corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in brief_files) or ("Briefing context. " * 250)
    jd_corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in jd_files[:2]) or ("JD context. " * 250)
    claims_corpus = claims_file.read_text(encoding="utf-8", errors="replace") if claims_file.is_file() else ("Fact atom. " * 800)

    stable_prefix_tokens = int(tc_mod.estimate_tokens(claims_corpus + "\n" + brief_corpus))
    volatile_tail_tokens = int(tc_mod.estimate_tokens(jd_corpus))
    per_lane_tokens = stable_prefix_tokens + volatile_tail_tokens

    # 1. Execute Anthropic cache receipts across configured Claude lanes (1 write + N-1 reads)
    claude_price_usd = pricing_map[claude_model]["input_cost_per_mtok"]
    claude_uncached_tokens = 0
    claude_cached_equiv_tokens = 0
    claude_uncached_usd = 0.0
    claude_cached_usd = 0.0
    for idx in range(claude_lanes):
        usage = (
            {"input_tokens": volatile_tail_tokens, "cache_creation_input_tokens": stable_prefix_tokens, "cache_read_input_tokens": 0}
            if idx == 0
            else {"input_tokens": volatile_tail_tokens, "cache_creation_input_tokens": 0, "cache_read_input_tokens": stable_prefix_tokens}
        )
        rec = apc_mod.build_cache_receipt_from_usage(
            seed={"cache_enabled": True, "active_cache_ttls": ["1h"], "input_usd_per_million": claude_price_usd},
            provider="external_claude",
            model=claude_model,
            section_id=f"lane_{idx}",
            usage=usage,
        )
        claude_uncached_tokens += int(rec.get("estimated_uncached_input_tokens") or 0)
        claude_cached_equiv_tokens += int(rec.get("estimated_cached_input_tokens") or 0)
        claude_uncached_usd += float(rec.get("estimated_input_cost_without_cache_usd") or 0.0)
        claude_cached_usd += float(rec.get("estimated_input_cost_with_cache_usd") or 0.0)

    # 2. Execute OpenAI pricing across configured OpenAI lanes (1 cold + N-1 prefix-cached)
    openai_uncached_tokens = openai_lanes * per_lane_tokens
    openai_cached_equiv_tokens = per_lane_tokens
    openai_uncached_usd = 0.0
    openai_cached_usd = 0.0
    oa_in_rate = pricing_map[openai_model]["input_cost_per_mtok"]
    oa_cache_rate = pricing_map[openai_model]["cached_input_cost_per_mtok"]
    oa_ratio = oa_cache_rate / max(oa_in_rate, 1e-6)
    for idx in range(openai_lanes):
        u_cost, _, _ = prc_mod.price_usage(openai_model, {"prompt_tokens": per_lane_tokens, "cached_tokens": 0}, provider="external_openai")
        c_tokens = 0 if idx == 0 else stable_prefix_tokens
        c_cost, _, _ = prc_mod.price_usage(openai_model, {"prompt_tokens": per_lane_tokens, "cached_tokens": c_tokens}, provider="external_openai")
        openai_uncached_usd += float(u_cost or 0.0)
        openai_cached_usd += float(c_cost or 0.0)
        if idx > 0:
            openai_cached_equiv_tokens += int(volatile_tail_tokens + stable_prefix_tokens * oa_ratio)

    # 3. Execute live BriefingCache replay across multi-recipient / multi-section lookups
    per_research_tokens = int(tc_mod.estimate_tokens(brief_corpus)) * 3
    research_lookups = max(6, len(brief_files) or 6)
    research_misses = 0
    with tempfile.TemporaryDirectory() as tmp:
        bcache = bcache_mod.BriefingCache(cache_dir=Path(tmp))
        bkey = bcache_mod.compute_briefing_cache_key(
            company_name="TargetEnterprise",
            jd_hash="jd_bench_01",
            target_role="SVP AI",
            model_pin=openai_model,
        )
        for _ in range(research_lookups):
            if bcache.get(bkey) is None:
                research_misses += 1
                bcache.put(
                    bkey,
                    bcache_mod.CachedBriefing(
                        company_name="TargetEnterprise",
                        target_role="SVP AI",
                        briefing_text=brief_corpus,
                        digest="bench",
                        source="BENCH",
                        created_at=time.time(),
                    ),
                )
    uncached_research_tokens = research_lookups * per_research_tokens
    cached_research_tokens = research_misses * per_research_tokens
    u_res_usd, _, _ = prc_mod.price_usage(openai_model, {"prompt_tokens": uncached_research_tokens}, provider="external_openai")
    c_res_usd, _, _ = prc_mod.price_usage(openai_model, {"prompt_tokens": cached_research_tokens}, provider="external_openai")

    # 4. Judge retry calibration + prefix reuse via configured runtime_profiles
    judge_profiles = (((profiles_data.get("runtime_limits") or {}).get("judge") or {}).get("runtime_profiles")) or {}
    attempt_vals = [int((v or {}).get("max_attempts") or 2) for v in judge_profiles.values() if isinstance(v, dict)]
    mean_attempts = (sum(attempt_vals) / float(len(attempt_vals))) if attempt_vals else 2.0
    uncached_judge_tokens = total_lanes * per_lane_tokens * 3  # uncalibrated 3-attempt full re-judge baseline
    cached_judge_lanes = int(total_lanes * mean_attempts)
    u_j_oa, _, _ = prc_mod.price_usage(openai_judge_model, {"prompt_tokens": uncached_judge_tokens // 2}, provider="external_openai")
    u_j_gm, _, _ = prc_mod.price_usage(gemini_judge_model, {"prompt_tokens": uncached_judge_tokens // 2}, provider="google_gemini")
    c_j_oa, _, _ = prc_mod.price_usage(
        openai_judge_model,
        {"prompt_tokens": (cached_judge_lanes * per_lane_tokens) // 2, "cached_tokens": (cached_judge_lanes * stable_prefix_tokens) // 2},
        provider="external_openai",
    )
    c_j_gm, _, _ = prc_mod.price_usage(
        gemini_judge_model,
        {"prompt_tokens": (cached_judge_lanes * per_lane_tokens) // 2, "cached_tokens": (cached_judge_lanes * stable_prefix_tokens) // 2},
        provider="google_gemini",
    )
    gm_ratio = pricing_map[gemini_judge_model]["cached_input_cost_per_mtok"] / max(pricing_map[gemini_judge_model]["input_cost_per_mtok"], 1e-6)
    avg_j_cache_ratio = 0.5 * (oa_ratio + gm_ratio)
    cached_judge_tokens = int(cached_judge_lanes * (volatile_tail_tokens + stable_prefix_tokens * avg_j_cache_ratio))

    total_uncached_tokens = claude_uncached_tokens + openai_uncached_tokens + uncached_research_tokens + uncached_judge_tokens
    total_cached_tokens = claude_cached_equiv_tokens + openai_cached_equiv_tokens + cached_research_tokens + cached_judge_tokens
    token_savings = total_uncached_tokens - total_cached_tokens
    token_savings_ratio = round(token_savings / float(max(total_uncached_tokens, 1)), 4)

    uncached_cost_usd = claude_uncached_usd + openai_uncached_usd + float(u_res_usd or 0.0) + float(u_j_oa or 0.0) + float(u_j_gm or 0.0)
    cached_cost_usd = claude_cached_usd + openai_cached_usd + float(c_res_usd or 0.0) + float(c_j_oa or 0.0) + float(c_j_gm or 0.0)

    cost_reduction_multiple = uncached_cost_usd / max(cached_cost_usd, 1e-6)
    token_reduction_multiple = total_uncached_tokens / float(max(total_cached_tokens, 1))
    quality_preservation_factor = 1.0 if (not p5_gaps and bool(p5_metrics.get("quality_preserved"))) else 0.0
    roi_multiple = round(
        ((0.55 * cost_reduction_multiple) + (0.45 * token_reduction_multiple)) * quality_preservation_factor,
        2,
    )

    return {
        "pricing_source": "model_registry_v2_measured_live",
        "section_lanes_evaluated": total_lanes,
        "briefing_cache_hits_verified": research_lookups - research_misses,
        "total_uncached_equivalent_tokens": total_uncached_tokens,
        "total_cached_equivalent_tokens": total_cached_tokens,
        "token_savings_equivalent": token_savings,
        "token_savings_pct": round(token_savings_ratio * 100.0, 2),
        "uncached_input_cost_usd": round(uncached_cost_usd, 6),
        "cached_input_cost_usd": round(cached_cost_usd, 6),
        "input_cost_savings_usd": round(uncached_cost_usd - cached_cost_usd, 6),
        "cost_reduction_multiple": round(cost_reduction_multiple, 2),
        "quality_preservation_factor": quality_preservation_factor,
        "roi_multiple": roi_multiple,
        "min_required_roi_multiple": MIN_REQUIRED_ROI_MULTIPLE,
        "roi_gate_passed": roi_multiple >= MIN_REQUIRED_ROI_MULTIPLE,
    }


def _audit_pillar_8_thought_leadership_and_roi(repo_root: Path) -> dict[str, Any]:
    """Pillar 8: AST-verified compact JSON serialization + live canonical checks + ROI >= 2.5x."""
    gaps: list[str] = []
    roi = compute_caching_roi_benchmark(repo_root=repo_root)
    if not roi["roi_gate_passed"]:
        gaps.append(
            f"Measured caching ROI multiple {roi['roi_multiple']}x is below mandatory {MIN_REQUIRED_ROI_MULTIPLE}x floor"
        )

    compact_surfaces = (
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "cache_identity.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "briefing_cache.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "r1b_ingest.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "r1b_semantic_chunk_builder.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "targeting_context_authority.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "providers" / "external_provider.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "providers" / "anthropic_cache_live_probe.py",
        repo_root / "outreach_engine" / "src" / "apps_lic" / "integrations" / "apps_research_bridge.py",
        repo_root / "apps_research" / "integrations" / "provider_gateway.py",
        repo_root / "apps_model_telemetry" / "token_budget_governor.py",
        repo_root / "agents" / "observability" / "prompt_cache.py",
    )
    for path in compact_surfaces:
        gaps.extend(verify_ast_compact_json_surface(path))

    spc, err = load_repo_module(repo_root, "agents/observability/prompt_cache.py")
    if err or spc is None:
        gaps.append(err or "Missing agents/observability/prompt_cache.py")
    else:
        rendered = spc.json_text({"z": [1, 2], "a": "ok"})
        if rendered != '{"a":"ok","z":[1,2]}':
            gaps.append(f"prompt_cache.json_text produced non-compact output: {rendered}")

    prof_doc, _ = load_yaml_strict(repo_root / "config" / "provider_profiles.yaml")
    argon_policy = (prof_doc.get("ide_argon4_routing_policy") or {}) if isinstance(prof_doc, dict) else {}
    if not argon_policy.get("interactive_ide_enabled") or not argon_policy.get("thinking_separation_guaranteed"):
        gaps.append("config/provider_profiles.yaml missing active ide_argon4_routing_policy with thinking_separation_guaranteed")
    if not argon_policy.get("high_reasoning_roles") or not argon_policy.get("medium_reasoning_roles"):
        gaps.append("ide_argon4_routing_policy must declare high_reasoning_roles and medium_reasoning_roles")
    if not str(argon_policy.get("frontier_external_retention_defense") or "").strip():
        gaps.append("ide_argon4_routing_policy missing frontier_external_retention_defense rationalization")

    return {
        "pillar": "8_thought_leadership_and_roi_benchmark",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "ide_argon4_routing_verified": bool(argon_policy.get("interactive_ide_enabled")),
        "roi_benchmark": roi,
        "gaps": gaps,
    }


def run_eight_pillar_cost_token_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Execute all 8 behavioral tokenomics and multi-tier caching pillar probes."""
    root = Path(repo_root).resolve()
    profiles_data, profiles_err = load_yaml_strict(root / "config" / "provider_profiles.yaml")
    pricing_map, _ = _load_registry_pricing(root)

    profiles = (profiles_data.get("profiles") or {}) if isinstance(profiles_data, dict) else {}
    claude_sections = ((profiles.get("external_claude_generator") or {}).get("model_by_section")) or {}
    openai_sections = ((profiles.get("external_openai_generator") or {}).get("model_by_section")) or {}
    claude_model = str(next(iter(claude_sections.values()), "claude-sonnet-4-6"))
    openai_model = str(next(iter(openai_sections.values()), "gpt-5.4-mini"))

    p1 = _audit_pillar_1_provider_pinning_and_effort(root, profiles_data, profiles_err, pricing_map)
    p2_gaps, p2_metrics = run_pillar_2_live_probes(root, claude_model=claude_model, openai_model=openai_model)
    p2 = {
        "pillar": "2_multi_provider_prompt_prefix_caching",
        "status": "PASS" if not p2_gaps else "ACTION_REQUIRED",
        "max_anthropic_breakpoints": 3,
        "tier1_ttl": "1h",
        "tier2_ttl": "5m",
        "live_metrics": p2_metrics,
        "gaps": p2_gaps,
    }
    p3_gaps = run_pillar_3_live_probes(root)
    p3 = {
        "pillar": "3_c0_retrieval_and_generation_semantic_caching",
        "status": "PASS" if not p3_gaps else "ACTION_REQUIRED",
        "gaps": p3_gaps,
    }
    p4_gaps, brief_chars = run_pillar_4_live_probes(root, model_pin=openai_model)
    p4 = {
        "pillar": "4_multi_tier_deterministic_and_briefing_caches",
        "status": "PASS" if not p4_gaps else "ACTION_REQUIRED",
        "verified_briefing_chars": brief_chars,
        "gaps": p4_gaps,
    }
    p5_gaps, p5_metrics = run_pillar_5_live_probes(root)
    p5 = {
        "pillar": "5_surgical_repair_and_optional_trims",
        "status": "PASS" if not p5_gaps else "ACTION_REQUIRED",
        "live_metrics": p5_metrics,
        "gaps": p5_gaps,
    }
    p6_gaps = run_pillar_6_live_probes(root, profiles_data)
    p6 = {
        "pillar": "6_judge_retries_and_zero_llm_qualification",
        "status": "PASS" if not p6_gaps else "ACTION_REQUIRED",
        "gaps": p6_gaps,
    }
    p7_gaps = run_pillar_7_live_probes(root, profiles_data, priced_model=openai_model)
    gov_cfg = ((profiles_data.get("runtime_limits") or {}).get("model_token_governor")) or {}
    p7 = {
        "pillar": "7_spend_governor_and_system_learning",
        "status": "PASS" if not p7_gaps else "ACTION_REQUIRED",
        "max_input_tokens_per_attempt": gov_cfg.get("max_input_tokens_per_attempt"),
        "max_reserved_tokens_per_run": gov_cfg.get("max_reserved_tokens_per_run"),
        "gaps": p7_gaps,
    }
    p8 = _audit_pillar_8_thought_leadership_and_roi(root)

    pillars = [p1, p2, p3, p4, p5, p6, p7, p8]
    total_gaps = sum(len(p["gaps"]) for p in pillars)
    roi_summary = p8.get("roi_benchmark", {})
    is_clean = total_gaps == 0 and bool(roi_summary.get("roi_gate_passed", False))
    return {
        "contract_id": "urn:agents:cost-token-8-pillar-audit:2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "status": "PASS" if is_clean else "ACTION_REQUIRED",
        "is_clean": is_clean,
        "total_pillars": len(pillars),
        "pillars_passing": sum(1 for p in pillars if p["status"] == "PASS"),
        "total_gaps": total_gaps,
        "roi_benchmark": roi_summary,
        "pillars": pillars,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="8-Pillar Behavioral Cost, Cache & Token Budget Auditor.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--strict", action="store_true", help="Compatibility flag (auditor fails closed by default)")
    parser.add_argument("--allow-gaps", action="store_true", help="Exit 0 even when gaps are present (reporting mode)")
    args = parser.parse_args(argv)

    report = run_eight_pillar_cost_token_audit(args.repo_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] 8-Pillar Behavioral Cost & Cache Audit: "
            f"{report['pillars_passing']}/{report['total_pillars']} pillars passing "
            f"(ROI={report['roi_benchmark'].get('roi_multiple')}x, gaps={report['total_gaps']})"
        )

    if not report["is_clean"] and not args.allow_gaps:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
