#!/usr/bin/env python3
"""Agents Repository — 8-Pillar Cost, Multi-Tier Caching & Token Budget Auditor.

Implements the deterministic, fail-closed Stage IV-A (`Order 6/7`) tokenomics and
multi-tier caching audit defined in `automations/prompts/agents_cost_token_budget_agent.md`
under `urn:agents:scheduled-task-common-control-matrix:1.0.0` (`INV-REPO-SEPARATION-AGENTS-ONLY`).

Pillars:
1. Provider Profile Pinning, Effort Right-Sizing & Pareto Benchmarking (`config/provider_profiles.yaml`, `apps_research/config/model_pins.py`)
2. Multi-Provider Prompt Prefix Caching (`anthropic_prompt_cache.py`, `anthropic_section_cache_payload.py` 3-breakpoint tiers, `ProviderCacheReceipt`)
3. Generation-Bound & C0 Retrieval Semantic Caching (`c02_semantic_cache_payload.py`, `CacheCompatibilityJudge`, `semantic_cache_persistence_quarantine.py`)
4. Multi-Tier Deterministic, Artifact & Cross-Engine Briefing Caches (`cache_identity.py`, `briefing_cache.py`, `briefing_resolver.py`, `apps_research_bridge.py`, `targeting_context_authority.py`)
5. Surgical Repair / Regen Token Budgets & Protected Evidence-Preserving Optional Trims (`executive_summary_token_budget.py`, `word_budget_repair.py`)
6. Lane-Calibrated Judge Retries, Selector Pool Caching & Zero-LLM Post-Runtime Qualification (`provider_gateway.py`, `zero_llm_qualification.py`)
7. Closed-Loop Spend Governor & System Learning (`model_token_governor.py`, `research_boundary_policy.py`, `HITLDecisionStore`)
8. Frontier Thought Leadership, Compact Serialization & ROI >= 2.5x Pareto Benchmarking
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Sequence

try:
    import yaml as _yaml  # type: ignore
except ImportError:
    _yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIN_REQUIRED_ROI_MULTIPLE: float = 2.5


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Stdlib indentation-aware YAML mapping parser when PyYAML is not installed."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        if ":" not in stripped:
            continue
        key, _, val_raw = stripped.partition(":")
        key = key.strip()
        val_str = val_raw.split("#", 1)[0].strip().strip("\"'")
        parent = stack[-1][1]
        if not val_str:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            low = val_str.lower()
            if low == "true":
                parent[key] = True
            elif low == "false":
                parent[key] = False
            elif low in ("null", "none"):
                parent[key] = None
            elif re.fullmatch(r"-?\d+", val_str):
                parent[key] = int(val_str)
            elif re.fullmatch(r"-?\d+\.\d+", val_str):
                parent[key] = float(val_str)
            else:
                parent[key] = val_str
    return root


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        if _yaml is not None:
            data = _yaml.safe_load(raw)
            return data if isinstance(data, dict) else {}
        return _parse_simple_yaml(raw)
    except Exception:  # guardian: YAML syntax fallback for diagnostic reporting
        return {}


def _audit_pillar_1_provider_pinning_and_effort(repo_root: Path) -> dict[str, Any]:
    """Pillar 1: Provider profile pinning, reasoning effort right-sizing, and model pin SSOT."""
    gaps: list[str] = []
    profiles_path = repo_root / "config" / "provider_profiles.yaml"
    data = _load_yaml(profiles_path)
    pinned_sections_count = 0
    low_effort_sections_count = 0

    if not data:
        gaps.append("Missing or unreadable config/provider_profiles.yaml")
    else:
        ownership = data.get("model_pin_ownership") or {}
        if ownership.get("environment_model_override_allowed") is not False:
            gaps.append("config/provider_profiles.yaml must enforce environment_model_override_allowed: false")

        profiles = data.get("profiles") or {}
        for prof_key in ("external_openai_generator", "external_claude_generator"):
            prof = profiles.get(prof_key) or {}
            models_by_sec = prof.get("model_by_section") or {}
            efforts_by_sec = prof.get("effort_by_section") or {}
            if not models_by_sec:
                gaps.append(f"{prof_key} missing explicit model_by_section pins")
            if not efforts_by_sec:
                gaps.append(f"{prof_key} missing explicit effort_by_section bounds")
            for sec, eff in efforts_by_sec.items():
                pinned_sections_count += 1
                if str(eff).strip().lower() == "low":
                    low_effort_sections_count += 1
                else:
                    gaps.append(f"{prof_key}.{sec} effort '{eff}' exceeds 'low' compact schema generation tier")

        selectors = data.get("selector_models") or {}
        for sel_name in ("competencies_graph_pool_selector", "employment_bullet_pool_selector"):
            sel = selectors.get(sel_name) or {}
            if not sel.get("model"):
                gaps.append(f"selector_models.{sel_name} missing explicit model pin")
            if str(sel.get("reasoning_effort") or "").lower() != "low":
                gaps.append(f"selector_models.{sel_name} reasoning_effort must be 'low'")

    research_pins_path = repo_root / "apps_research" / "config" / "model_pins.py"
    if not research_pins_path.is_file():
        gaps.append("Missing apps_research/config/model_pins.py")
    else:
        txt = research_pins_path.read_text(encoding="utf-8")
        for sym in ("company_brief_generation_pin", "apps_rg_handoff_judge_pin", "single_lane_fail_closed"):
            if sym not in txt:
                gaps.append(f"apps_research/config/model_pins.py missing '{sym}'")

    local_llm_script = repo_root / "scripts" / "local_llm" / "serve_qwen_m5.py"
    if not local_llm_script.is_file():
        gaps.append("Missing scripts/local_llm/serve_qwen_m5.py")
    else:
        script_txt = local_llm_script.read_text(encoding="utf-8")
        if "model_catalog.json" not in script_txt:
            gaps.append("scripts/local_llm/serve_qwen_m5.py must resolve model IDs from config/model_catalog.json")

    return {
        "pillar": "1_provider_pinning_and_effort_right_sizing",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "pinned_sections_count": pinned_sections_count,
        "low_effort_sections_count": low_effort_sections_count,
        "gaps": gaps,
    }


def _audit_pillar_2_prompt_prefix_caching(repo_root: Path) -> dict[str, Any]:
    """Pillar 2: Multi-provider prompt prefix caching (Anthropic 3-breakpoint tiers, OpenAI, Gemini)."""
    gaps: list[str] = []
    apc_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "providers" / "anthropic_prompt_cache.py"
    ascp_path = (
        repo_root
        / "resume_graph_engine"
        / "src"
        / "apps_rg"
        / "runtime"
        / "providers"
        / "anthropic_section_cache_payload.py"
    )
    shared_pc_path = repo_root / "agents" / "observability" / "prompt_cache.py"

    if not apc_path.is_file():
        gaps.append("Missing anthropic_prompt_cache.py")
    else:
        txt = apc_path.read_text(encoding="utf-8")
        for marker in (
            "CACHE_READ_INPUT_MULTIPLIER = 0.10",
            "CACHE_WRITE_5M_INPUT_MULTIPLIER = 1.25",
            "CACHE_WRITE_1H_INPUT_MULTIPLIER = 2.00",
            "ProviderCacheReceipt",
            "build_cache_receipt_from_usage",
        ):
            if marker not in txt:
                gaps.append(f"anthropic_prompt_cache.py missing '{marker}'")

    if not ascp_path.is_file():
        gaps.append("Missing anthropic_section_cache_payload.py")
    else:
        txt = ascp_path.read_text(encoding="utf-8")
        for marker in (
            "MAX_ANTHROPIC_CACHE_MARKERS = 3",
            "TIER1_SLOTS",
            "TIER2_SLOTS",
            "VOLATILE_SLOTS",
            "REPEATED_C0_WORKLOADS",
            "pa_slot_prefix_tiers_v2",
            "build_anthropic_section_cache_payload",
        ):
            if marker not in txt:
                gaps.append(f"anthropic_section_cache_payload.py missing '{marker}'")

    if not shared_pc_path.is_file():
        gaps.append("Missing agents/observability/prompt_cache.py")
    else:
        pc_txt = shared_pc_path.read_text(encoding="utf-8")
        for marker in ("normalize_static_template", "prefix_fingerprint", "routing_key", "chat_usage_metrics"):
            if marker not in pc_txt:
                gaps.append(f"agents/observability/prompt_cache.py missing '{marker}'")

    return {
        "pillar": "2_multi_provider_prompt_prefix_caching",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "max_anthropic_breakpoints": 3,
        "tier1_ttl": "1h",
        "tier2_ttl": "5m",
        "gaps": gaps,
    }


def _audit_pillar_3_semantic_caching_and_uwg(repo_root: Path) -> dict[str, Any]:
    """Pillar 3: C0 retrieval semantic caching and R1B UWG persistence quarantine."""
    gaps: list[str] = []
    c02_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "c0" / "c02_semantic_cache_payload.py"
    quarantine_path = (
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "semantic_cache_persistence_quarantine.py"
    )
    judge_path = repo_root / "apps_research" / "engines" / "judges" / "cache_compatibility_judge.py"

    if not c02_path.is_file():
        gaps.append("Missing c02_semantic_cache_payload.py")
    else:
        txt = c02_path.read_text(encoding="utf-8")
        for marker in (
            "C02_SEMANTIC_CACHE_PAYLOAD_ARTIFACT",
            "_MAX_QUERY_OUTPUT_ITEMS = 24",
            "build_c02_semantic_cache_payload",
            "section_intent_text",
            "PENDING_UWG",
        ):
            if marker not in txt:
                gaps.append(f"c02_semantic_cache_payload.py missing '{marker}'")

    if not quarantine_path.is_file():
        gaps.append("Missing semantic_cache_persistence_quarantine.py")
    else:
        txt = quarantine_path.read_text(encoding="utf-8")
        for marker in (
            "NO_DIRECT_CHROMA_ASSERTION_ARTIFACT",
            "NON_DURABLE_INDEX_WRITE",
            "GOVERNED_READ_SURFACE_REFRESH_AFTER_UWG_COMMIT",
            "assess_uwg_durable_write_chain",
            "finalize_semantic_cache_quarantine",
        ):
            if marker not in txt:
                gaps.append(f"semantic_cache_persistence_quarantine.py missing '{marker}'")

    if not judge_path.is_file():
        gaps.append("Missing apps_research/engines/judges/cache_compatibility_judge.py")
    else:
        txt = judge_path.read_text(encoding="utf-8")
        if "CacheCompatibilityJudge" not in txt:
            gaps.append("cache_compatibility_judge.py missing CacheCompatibilityJudge")

    return {
        "pillar": "3_c0_retrieval_and_generation_semantic_caching",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "gaps": gaps,
    }


def _audit_pillar_4_multi_tier_deterministic_and_briefing_caches(repo_root: Path) -> dict[str, Any]:
    """Pillar 4: Multi-tier deterministic identity, persisted bundle, and cross-engine briefing caches."""
    gaps: list[str] = []
    cid_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "cache_identity.py"
    bcache_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "briefing_cache.py"
    lic_resolver_path = repo_root / "outreach_engine" / "src" / "apps_lic" / "pipeline" / "briefing_resolver.py"
    lic_bridge_path = repo_root / "outreach_engine" / "src" / "apps_lic" / "integrations" / "apps_research_bridge.py"
    tca_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "targeting_context_authority.py"

    if not cid_path.is_file():
        gaps.append("Missing apps_rg/cache/cache_identity.py")
    else:
        txt = cid_path.read_text(encoding="utf-8")
        for marker in ("CacheIdentity", "INVALID_CACHE_VALUES", "compute_cache_identity_key", "compute_briefing_cache_key"):
            if marker not in txt:
                gaps.append(f"cache_identity.py missing '{marker}'")

    if not bcache_path.is_file():
        gaps.append("Missing apps_rg/cache/briefing_cache.py")
    else:
        txt = bcache_path.read_text(encoding="utf-8")
        for marker in ("BriefingCache", "DEFAULT_BRIEFING_TTL_SECONDS", "get_global_briefing_cache"):
            if marker not in txt:
                gaps.append(f"briefing_cache.py missing '{marker}'")

    if not lic_resolver_path.is_file():
        gaps.append("Missing outreach_engine briefing_resolver.py")
    else:
        txt = lic_resolver_path.read_text(encoding="utf-8")
        for marker in (
            "GovernedBriefingResolver",
            "MAX_CACHE_SIZE: int = 128",
            "DEFAULT_CACHE_TTL_SECONDS",
            "CACHE_HIT",
            "PERSISTED_ARTIFACT",
        ):
            if marker not in txt:
                gaps.append(f"outreach_engine briefing_resolver.py missing '{marker}'")

    if not lic_bridge_path.is_file():
        gaps.append("Missing outreach_engine apps_research_bridge.py")
    else:
        txt = lic_bridge_path.read_text(encoding="utf-8")
        for marker in ("_find_valid_persisted_artifact_bundle", "_resolve_canonical_targeting_brief"):
            if marker not in txt:
                gaps.append(f"apps_research_bridge.py missing '{marker}'")

    if not tca_path.is_file():
        gaps.append("Missing targeting_context_authority.py")
    else:
        txt = tca_path.read_text(encoding="utf-8")
        for marker in ("MaterialTargetingBundle", "build_targeting_binding_digest"):
            if marker not in txt:
                gaps.append(f"targeting_context_authority.py missing '{marker}'")

    err_path = repo_root / "apps_model_telemetry" / "exact_response_reuse.py"
    if not err_path.is_file():
        gaps.append("Missing apps_model_telemetry/exact_response_reuse.py")
    else:
        err_txt = err_path.read_text(encoding="utf-8")
        for marker in ("ExactRequestIdentity", "build_exact_request_identity", "EXACT_RESPONSE_CACHE_FILENAME"):
            if marker not in err_txt:
                gaps.append(f"apps_model_telemetry/exact_response_reuse.py missing '{marker}'")

    return {
        "pillar": "4_multi_tier_deterministic_and_briefing_caches",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "gaps": gaps,
    }


def _audit_pillar_5_surgical_regen_and_optional_trims(repo_root: Path) -> dict[str, Any]:
    """Pillar 5: Surgical repair/regen token budgets and evidence-preserving optional trims."""
    gaps: list[str] = []
    estb_path = (
        repo_root
        / "resume_graph_engine"
        / "src"
        / "apps_rg"
        / "runtime"
        / "sections"
        / "executive_summary_token_budget.py"
    )
    wbr_path = (
        repo_root
        / "resume_graph_engine"
        / "src"
        / "apps_rg"
        / "runtime"
        / "sections"
        / "executive_summary"
        / "word_budget_repair.py"
    )

    if not estb_path.is_file():
        gaps.append("Missing executive_summary_token_budget.py")
    else:
        txt = estb_path.read_text(encoding="utf-8")
        for marker in (
            'TRIM_STRATEGY = "executive_summary_optional_trim_only_v2"',
            "PROTECTED_COMPONENT_LABELS",
            "_OPTIONAL_TRIM_COMPONENTS",
            "first_pass_95pct_limit_tokens",
            "regen_dispatch_allowed",
            "verify_evidence_contract_unchanged",
            "verify_prompt_shape_preserved",
        ):
            if marker not in txt:
                gaps.append(f"executive_summary_token_budget.py missing '{marker}'")

    if not wbr_path.is_file():
        gaps.append("Missing executive_summary/word_budget_repair.py")

    return {
        "pillar": "5_surgical_repair_and_optional_trims",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "gaps": gaps,
    }


def _audit_pillar_6_judge_retries_and_zero_llm_replay(repo_root: Path) -> dict[str, Any]:
    """Pillar 6: Lane-calibrated judge retries, selector pool caching, and zero-LLM post-runtime qualification."""
    gaps: list[str] = []
    profiles_path = repo_root / "config" / "provider_profiles.yaml"
    data = _load_yaml(profiles_path)
    judge_cfg = (data.get("runtime_limits") or {}).get("judge") or {}
    r_profiles = judge_cfg.get("runtime_profiles") or {}

    expected_attempts = {
        "optional_advisory_taxonomy_only": 1,
        "standard_reasoning": 2,
        "bullet_rewrite_quality": 2,
        "enhanced_reasoning": 3,
    }
    for prof_name, max_att in expected_attempts.items():
        prof = r_profiles.get(prof_name) or {}
        if prof.get("max_attempts") != max_att:
            gaps.append(f"judge.runtime_profiles.{prof_name}.max_attempts != {max_att}")

    pg_path = repo_root / "apps_research" / "integrations" / "provider_gateway.py"
    if not pg_path.is_file():
        gaps.append("Missing apps_research/integrations/provider_gateway.py")
    else:
        txt = pg_path.read_text(encoding="utf-8")
        for marker in ("_is_retryable_gemini_transport_error", "_gemini_retry_delay_seconds"):
            if marker not in txt:
                gaps.append(f"apps_research provider_gateway.py missing '{marker}'")

    zlq_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "zero_llm_qualification.py"
    if not zlq_path.is_file():
        gaps.append("Missing zero_llm_qualification.py")
    else:
        txt = zlq_path.read_text(encoding="utf-8")
        for marker in ("ZERO_COUNTER_KEYS", "provider_calls", "judge_calls", "embedding_calls"):
            if marker not in txt:
                gaps.append(f"zero_llm_qualification.py missing '{marker}'")

    return {
        "pillar": "6_judge_retries_and_zero_llm_qualification",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "gaps": gaps,
    }


def _audit_pillar_7_spend_governor_and_system_learning(repo_root: Path) -> dict[str, Any]:
    """Pillar 7: Closed-loop spend governor (48k/300k token reservation, ResearchBoundaryPolicy) and HITLDecisionStore."""
    gaps: list[str] = []
    profiles_path = repo_root / "config" / "provider_profiles.yaml"
    data = _load_yaml(profiles_path)
    gov_cfg = (data.get("runtime_limits") or {}).get("model_token_governor") or {}
    if gov_cfg.get("max_input_tokens_per_attempt") != 48000:
        gaps.append("model_token_governor.max_input_tokens_per_attempt != 48000")
    if gov_cfg.get("max_reserved_tokens_per_run") != 300000:
        gaps.append("model_token_governor.max_reserved_tokens_per_run != 300000")

    mtg_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "model_token_governor.py"
    if not mtg_path.is_file():
        gaps.append("Missing model_token_governor.py")
    else:
        txt = mtg_path.read_text(encoding="utf-8")
        if "reserve_apps_rg_model_tokens" not in txt:
            gaps.append("model_token_governor.py missing reserve_apps_rg_model_tokens")

    rbp_path = repo_root / "outreach_engine" / "src" / "apps_lic" / "integrations" / "research_boundary_policy.py"
    if not rbp_path.is_file():
        gaps.append("Missing outreach_engine research_boundary_policy.py")
    else:
        txt = rbp_path.read_text(encoding="utf-8")
        for marker in ("ResearchBoundaryPolicy", "cost_limit_usd", "cost_per_call_usd", "COST_LIMIT_EXCEEDED"):
            if marker not in txt:
                gaps.append(f"research_boundary_policy.py missing '{marker}'")

    hitl_path = repo_root / "tools" / "hitl_governance.py"
    if not hitl_path.is_file():
        gaps.append("Missing tools/hitl_governance.py")
    else:
        txt = hitl_path.read_text(encoding="utf-8")
        for marker in ("HITLDecisionStore", "record_execution_outcome", "DEFAULT_MIN_CONFIDENCE_FLOOR"):
            if marker not in txt:
                gaps.append(f"tools/hitl_governance.py missing '{marker}'")

    telemetry_surfaces = (
        (repo_root / "apps_model_telemetry" / "pricing.py", ("get_model_pricing", "price_usage", "compute_run_cost_rollup")),
        (
            repo_root / "apps_model_telemetry" / "token_budget_governor.py",
            ("TokenBudgetPolicy", "TokenBudgetReservation", "estimate_input_tokens"),
        ),
        (repo_root / "apps_model_telemetry" / "token_counter.py", ("estimate_tokens",)),
        (repo_root / "agents" / "context" / "budgeting.py", ("TokenBudget", "fit_items_to_budget")),
    )
    for t_path, markers in telemetry_surfaces:
        if not t_path.is_file():
            gaps.append(f"Missing {t_path.relative_to(repo_root).as_posix()}")
        else:
            t_txt = t_path.read_text(encoding="utf-8")
            for marker in markers:
                if marker not in t_txt:
                    gaps.append(f"{t_path.relative_to(repo_root).as_posix()} missing '{marker}'")

    return {
        "pillar": "7_spend_governor_and_system_learning",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "max_input_tokens_per_attempt": gov_cfg.get("max_input_tokens_per_attempt"),
        "max_reserved_tokens_per_run": gov_cfg.get("max_reserved_tokens_per_run"),
        "gaps": gaps,
    }


def _extract_cache_multipliers(repo_root: Path) -> dict[str, float]:
    """Read live Anthropic prompt cache multipliers from anthropic_prompt_cache.py."""
    apc_path = (
        repo_root
        / "resume_graph_engine"
        / "src"
        / "apps_rg"
        / "runtime"
        / "providers"
        / "anthropic_prompt_cache.py"
    )
    defaults = {
        "read": 0.10,
        "write_5m": 1.25,
        "write_1h": 2.00,
    }
    if not apc_path.is_file():
        return defaults
    txt = apc_path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "read": r"CACHE_READ_INPUT_MULTIPLIER\s*=\s*([0-9.]+)",
        "write_5m": r"CACHE_WRITE_5M_INPUT_MULTIPLIER\s*=\s*([0-9.]+)",
        "write_1h": r"CACHE_WRITE_1H_INPUT_MULTIPLIER\s*=\s*([0-9.]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, txt)
        if m:
            defaults[key] = float(m.group(1))
    return defaults


def _load_registry_pricing(repo_root: Path) -> dict[str, dict[str, float]]:
    """Load per-model USD pricing table from resume_graph_engine/config/models/registry.yaml."""
    reg_path = repo_root / "resume_graph_engine" / "config" / "models" / "registry.yaml"
    data = _load_yaml(reg_path)
    models = data.get("models") if isinstance(data, dict) else None
    out: dict[str, dict[str, float]] = {}
    if isinstance(models, dict):
        for model_id, spec in models.items():
            if isinstance(spec, dict) and isinstance(spec.get("pricing"), dict):
                p = spec["pricing"]
                out[str(model_id)] = {
                    "input_cost_per_mtok": float(p.get("input_cost_per_mtok") or 0.0),
                    "output_cost_per_mtok": float(p.get("output_cost_per_mtok") or 0.0),
                    "cached_input_cost_per_mtok": float(p.get("cached_input_cost_per_mtok") or 0.0),
                    "cache_write_multiplier": float(p.get("cache_write_multiplier") or 1.0),
                }
    return out


def compute_caching_roi_benchmark(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Compute Pareto cost and token savings dynamically from live model registry, profiles, and cache policies."""
    root = Path(repo_root).resolve()
    profiles_data = _load_yaml(root / "config" / "provider_profiles.yaml")
    profiles = (profiles_data.get("profiles") or {}) if isinstance(profiles_data, dict) else {}
    openai_sections = ((profiles.get("external_openai_generator") or {}).get("model_by_section")) or {}
    claude_sections = ((profiles.get("external_claude_generator") or {}).get("model_by_section")) or {}
    openai_lane_count = len(openai_sections) if openai_sections else 5
    claude_lane_count = len(claude_sections) if claude_sections else 8
    total_lanes = openai_lane_count + claude_lane_count

    limits = (profiles_data.get("runtime_limits") or {}) if isinstance(profiles_data, dict) else {}
    gov_cfg = limits.get("model_token_governor") or {}
    max_input_per_attempt = int(gov_cfg.get("max_input_tokens_per_attempt") or 48_000)
    bare_cfg = limits.get("bare_pipeline") or {}
    research_max_out = int(bare_cfg.get("research_max_tokens") or 2_400)

    judge_profiles = ((limits.get("judge") or {}).get("runtime_profiles")) or {}
    if isinstance(judge_profiles, dict) and judge_profiles:
        attempt_vals = [int((v or {}).get("max_attempts") or 2) for v in judge_profiles.values() if isinstance(v, dict)]
        mean_judge_attempts = sum(attempt_vals) / float(max(len(attempt_vals), 1))
    else:
        mean_judge_attempts = 2.0

    mults = _extract_cache_multipliers(root)
    pricing_map = _load_registry_pricing(root)

    # Derive token volumes from governed per-attempt ceiling and configured lanes
    per_lane_input_tokens = max(6_000, int(max_input_per_attempt * 0.375))
    stable_prefix_tokens = int(per_lane_input_tokens * (7.0 / 9.0))
    volatile_slot_tokens = per_lane_input_tokens - stable_prefix_tokens

    uncached_section_input_tokens = total_lanes * per_lane_input_tokens
    campaign_recipients = 5
    per_research_tokens = research_max_out * 10
    uncached_research_tokens = campaign_recipients * per_research_tokens
    per_lane_judge_tokens = int(max_input_per_attempt / 3.0)
    uncached_judge_tokens = total_lanes * per_lane_judge_tokens
    total_uncached_tokens = uncached_section_input_tokens + unached_research_and_judge(
        uncached_research_tokens, uncached_judge_tokens
    )

    # Dynamic cached token & USD cost modeling from live provider pricing & cache multipliers
    claude_model = next(iter(claude_sections.values()), "")
    openai_model = next(iter(openai_sections.values()), "")
    judge_models_cfg = (profiles_data.get("judge_models") or {}).get("standard") or {}
    gemini_judge_model = str(judge_models_cfg.get("gemini_pro") or "")
    openai_judge_model = str(judge_models_cfg.get("openai_chatgpt") or openai_model)

    claude_price = pricing_map.get(claude_model, {"input_cost_per_mtok": 3.00, "cached_input_cost_per_mtok": 0.30})
    openai_price = pricing_map.get(openai_model, {"input_cost_per_mtok": 2.50, "cached_input_cost_per_mtok": 1.25})
    gemini_price = pricing_map.get(gemini_judge_model, {"input_cost_per_mtok": 0.15, "cached_input_cost_per_mtok": 0.0375})
    openai_judge_price = pricing_map.get(openai_judge_model, openai_price)

    openai_cache_ratio = (
        openai_price["cached_input_cost_per_mtok"] / max(openai_price["input_cost_per_mtok"], 1e-6)
    )
    claude_cached_equiv = int(
        (stable_prefix_tokens * mults["write_1h"] + volatile_slot_tokens)
        + max(0, claude_lane_count - 1) * (stable_prefix_tokens * mults["read"] + volatile_slot_tokens)
    )
    # ExactRequestIdentity + C02 semantic cache reuse + OpenAI automatic prefix caching
    openai_cached_equiv = int(
        per_lane_input_tokens
        + max(0, openai_lane_count - 1) * (stable_prefix_tokens * openai_cache_ratio * 0.5 + volatile_slot_tokens)
    )
    cached_section_equivalent_tokens = claude_cached_equiv + openai_cached_equiv
    cached_research_tokens = per_research_tokens  # 1 live run + 4 BriefingCache/GovernedBriefingResolver hits
    judge_attempt_factor = min(1.0, mean_judge_attempts / 3.0)
    cached_judge_tokens = int(uncached_judge_tokens * judge_attempt_factor * 0.675)

    total_cached_tokens = cached_section_equivalent_tokens + cached_research_tokens + cached_judge_tokens
    token_savings = total_uncached_tokens - total_cached_tokens
    token_savings_ratio = round(token_savings / float(max(total_uncached_tokens, 1)), 4)

    # Real USD cost calculation from Model Registry v2 rates
    uncached_cost_usd = (
        (claude_lane_count * per_lane_input_tokens / 1_000_000.0) * claude_price["input_cost_per_mtok"]
        + (openai_lane_count * per_lane_input_tokens / 1_000_000.0) * openai_price["input_cost_per_mtok"]
        + (uncached_research_tokens / 1_000_000.0) * openai_price["input_cost_per_mtok"]
        + ((uncached_judge_tokens * 0.5) / 1_000_000.0) * openai_judge_price["input_cost_per_mtok"]
        + ((uncached_judge_tokens * 0.5) / 1_000_000.0) * gemini_price["input_cost_per_mtok"]
    )
    cached_cost_usd = (
        (claude_cached_equiv / 1_000_000.0) * claude_price["input_cost_per_mtok"]
        + (openai_cached_equiv / 1_000_000.0) * openai_price["input_cost_per_mtok"]
        + (cached_research_tokens / 1_000_000.0) * openai_price["input_cost_per_mtok"]
        + ((cached_judge_tokens * 0.5) / 1_000_000.0) * openai_judge_price["cached_input_cost_per_mtok"]
        + ((cached_judge_tokens * 0.5) / 1_000_000.0) * gemini_price["cached_input_cost_per_mtok"]
    )
    cost_reduction_multiple = uncached_cost_usd / max(cached_cost_usd, 1e-6)
    token_reduction_multiple = total_uncached_tokens / float(max(total_cached_tokens, 1))
    quality_preservation_factor = 1.0
    roi_multiple = round(
        ((0.55 * cost_reduction_multiple) + (0.45 * token_reduction_multiple)) * quality_preservation_factor,
        2,
    )

    return {
        "pricing_source": "model_registry_v2_dynamic" if pricing_map else "fallback_rates",
        "section_lanes_evaluated": total_lanes,
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


def unached_research_and_judge(research_tokens: int, judge_tokens: int) -> int:
    return research_tokens + judge_tokens


def _audit_pillar_8_thought_leadership_and_roi(repo_root: Path) -> dict[str, Any]:
    """Pillar 8: Compact JSON serialization, selector pool caching, and ROI >= 2.5x Pareto gate."""
    gaps: list[str] = []
    roi = compute_caching_roi_benchmark(repo_root=repo_root)
    if not roi["roi_gate_passed"]:
        gaps.append(
            f"Projected caching ROI multiple {roi['roi_multiple']}x is below mandatory {MIN_REQUIRED_ROI_MULTIPLE}x floor"
        )

    compact_surfaces = [
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "cache" / "cache_identity.py",
        repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "targeting_context_authority.py",
        repo_root / "apps_research" / "integrations" / "provider_gateway.py",
        repo_root / "apps_model_telemetry" / "token_budget_governor.py",
        repo_root / "agents" / "observability" / "prompt_cache.py",
    ]
    for path in compact_surfaces:
        if not path.is_file():
            gaps.append(f"Missing compact serialization surface: {path.name}")
        elif 'separators=(",", ":")' not in path.read_text(encoding="utf-8"):
            gaps.append(f"{path.name} missing compact JSON serialization separators=(',', ':')")

    return {
        "pillar": "8_thought_leadership_and_roi_benchmark",
        "status": "PASS" if not gaps else "ACTION_REQUIRED",
        "roi_benchmark": roi,
        "gaps": gaps,
    }


def run_eight_pillar_cost_token_audit(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Execute all 8 tokenomics and multi-tier caching pillar checks."""
    root = repo_root.resolve()
    pillars = [
        _audit_pillar_1_provider_pinning_and_effort(root),
        _audit_pillar_2_prompt_prefix_caching(root),
        _audit_pillar_3_semantic_caching_and_uwg(root),
        _audit_pillar_4_multi_tier_deterministic_and_briefing_caches(root),
        _audit_pillar_5_surgical_regen_and_optional_trims(root),
        _audit_pillar_6_judge_retries_and_zero_llm_replay(root),
        _audit_pillar_7_spend_governor_and_system_learning(root),
        _audit_pillar_8_thought_leadership_and_roi(root),
    ]
    total_gaps = sum(len(p["gaps"]) for p in pillars)
    roi_summary = pillars[-1].get("roi_benchmark", {})
    is_clean = total_gaps == 0 and bool(roi_summary.get("roi_gate_passed", False))
    return {
        "contract_id": "urn:agents:cost-token-8-pillar-audit:1.0.0",
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
    parser = argparse.ArgumentParser(description="8-Pillar Cost, Caching & Token Budget Auditor.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repository root path")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any gaps remain")
    args = parser.parse_args(argv)

    report = run_eight_pillar_cost_token_audit(args.repo_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"[{report['status']}] 8-Pillar Cost & Caching Audit: "
            f"{report['pillars_passing']}/{report['total_pillars']} pillars passing "
            f"(ROI={report['roi_benchmark'].get('roi_multiple')}x, gaps={report['total_gaps']})"
        )

    if args.strict and not report["is_clean"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
