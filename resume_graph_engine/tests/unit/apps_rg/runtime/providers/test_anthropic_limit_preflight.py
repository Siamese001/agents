from __future__ import annotations

import hashlib
import json

from apps_rg.l2_recipe import modular_resume_generation as modular
from apps_rg.runtime.providers.anthropic_limit_preflight import (
    ANTHROPIC_LIMIT_PREFLIGHT_ENV,
    ANTHROPIC_LIMIT_PREFLIGHT_OPENAI_BACKUP_SOURCE,
    ANTHROPIC_LIMIT_PREFLIGHT_RECEIPT_ENV,
    resolve_anthropic_limit_preflight_route,
    route_whole_run_provider_for_known_anthropic_limit,
)
from apps_rg.runtime.section_cli_defaults import (
    CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_CLAUDE,
    CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_OPENAI,
)
from apps_rg.runtime.section_model_limits import (
    resolve_section_generation_effort,
    resolve_section_generation_model,
    resolve_selector_provider_model,
    resolve_selector_reasoning_effort,
)
from apps_rg.runtime.providers import load_provider_profiles_config


def test_known_anthropic_limit_env_routes_claude_whole_run_lane_to_openai(monkeypatch) -> None:
    monkeypatch.setenv(ANTHROPIC_LIMIT_PREFLIGHT_ENV, "provider_throttling_failure")
    monkeypatch.delenv(ANTHROPIC_LIMIT_PREFLIGHT_RECEIPT_ENV, raising=False)

    provider, source = modular._resolve_phase1_lane_provider_for_section("", "competencies")

    assert provider == "external_openai"
    assert source == ANTHROPIC_LIMIT_PREFLIGHT_OPENAI_BACKUP_SOURCE


def test_known_anthropic_limit_does_not_relabel_openai_default_lane(monkeypatch) -> None:
    monkeypatch.setenv(ANTHROPIC_LIMIT_PREFLIGHT_ENV, "usage limit exceeded")

    provider, source = modular._resolve_phase1_lane_provider_for_section("", "unify_narrative")
    _provider, _source, route = route_whole_run_provider_for_known_anthropic_limit(
        provider,
        source,
        section_id="unify_narrative",
    )

    assert provider == "external_openai"
    assert source == CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_OPENAI
    assert route.active is True
    assert route.primary_attempt_skipped is False
    assert route.evidence["route_applied"] is False


def test_false_anthropic_limit_env_keeps_claude_default(monkeypatch) -> None:
    monkeypatch.setenv(ANTHROPIC_LIMIT_PREFLIGHT_ENV, "0")

    provider, source = modular._resolve_phase1_lane_provider_for_section("", "headline")

    assert provider == "external_claude"
    assert source == CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_CLAUDE


def test_known_anthropic_limit_receipt_routes_and_audits_digest(tmp_path, monkeypatch) -> None:
    payload = {
        "known_anthropic_limit": True,
        "reason_category": "provider_throttling_failure",
        "exact_provider_error": "External provider HTTP 429: rate_limit_error",
    }
    raw = json.dumps(payload, indent=2, sort_keys=True)
    receipt = tmp_path / "anthropic_limit_preflight.json"
    receipt.write_text(raw, encoding="utf-8")
    monkeypatch.delenv(ANTHROPIC_LIMIT_PREFLIGHT_ENV, raising=False)
    monkeypatch.setenv(ANTHROPIC_LIMIT_PREFLIGHT_RECEIPT_ENV, str(receipt))

    route = resolve_anthropic_limit_preflight_route()
    provider, source = modular._resolve_phase1_lane_provider_for_section("", "ibm_bullets")

    assert route.active is True
    assert route.primary_attempt_skipped is True
    assert route.receipt_path == str(receipt)
    assert route.receipt_sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert provider == "external_openai"
    assert source == ANTHROPIC_LIMIT_PREFLIGHT_OPENAI_BACKUP_SOURCE


def test_known_limit_routes_generator_and_selector_to_complete_backup_identity(
    monkeypatch,
) -> None:
    monkeypatch.setenv(ANTHROPIC_LIMIT_PREFLIGHT_ENV, "credit balance too low")
    config = load_provider_profiles_config()
    openai = config["profiles"]["external_openai_generator"]
    selector = config["selector_models"]["competencies_graph_pool_selector"]
    backup_selector = selector["anthropic_limit_backup"]

    provider, _source = modular._resolve_phase1_lane_provider_for_section(
        "", "competencies"
    )

    assert provider == "external_openai"
    assert resolve_section_generation_model(
        "competencies", provider_profile=provider
    ) == openai["anthropic_limit_backup_model_by_section"]["competencies"]
    assert resolve_section_generation_effort(
        "competencies", provider_profile=provider
    ) == openai["anthropic_limit_backup_effort_by_section"]["competencies"]
    selector_provider, selector_model, selector_source = (
        resolve_selector_provider_model("competencies_graph_pool_selector")
    )
    assert selector_provider == backup_selector["provider_key"]
    assert selector_model == backup_selector["model"]
    assert selector_source.endswith("anthropic_limit_backup.model")
    assert resolve_selector_reasoning_effort(
        "competencies_graph_pool_selector"
    ) == backup_selector["reasoning_effort"]
