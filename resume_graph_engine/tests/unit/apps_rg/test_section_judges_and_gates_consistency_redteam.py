"""Adversarial Red-Team Test Suite for Resume Sections, Judges, and Deterministic Gates.

Adversarially attacks and validates the integrity of:
1. Vector 1: Zero Orphaned / Phantom Sections in runtime policies, manifests, and defaults.
2. Vector 2: 100% Exact Parity across all 4 section authority registries and Wave DAG hierarchy.
3. Vector 3: Calibrated Cross-Provider Proof Judges (No Self-Judging, strictly calibrated panel sizes).
4. Vector 4: Monotonic Runtime Profile Reasoning Tiers (optional <= standard <= enhanced <= extreme).
5. Vector 5: Production Mode Fails Closed on Mock Judges (APPS_RG_PRODUCTION_RUN=1 rejection).
6. Vector 6: Complete Deterministic X2 Gates for every active generated section.
7. Vector 7: Locked Sections Isolation (early_career, education, certifications ungenerated and invariant).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import pytest
import yaml

from apps_rg.repository_layout import resolve_apps_rg_path
import apps_rg.runtime.internal.generated_lane_rollup as glr
from apps_rg.runtime.section_execution_plan import (
    BULLET_LANES,
    GENERATED_CONTENT_LANES,
    NARRATIVE_LANES,
    SECTION_EXECUTION_POLICIES,
)
from apps_rg.runtime.section_cli_defaults import (
    _SECTION_DEFAULT_PROVIDER,
    _SECTION_DEFAULT_X1D_JUDGES,
    default_lane_provider_for_section,
    resolve_cli_x1d_judges,
)
from apps_rg.runtime.spine.section_cli_runners import SECTION_LANE_RUNNERS
from apps_rg.runtime.section_model_limits import (
    selector_role_for_section,
    SectionModelSSOTError,
)
from apps_rg.runtime.orchestration.section_lane_concurrency import (
    load_section_dag_manifest,
    assert_section_dag_wave_order,
    build_phase1_waves,
)
from apps_rg.runtime.section_judge_policy import (
    get_section_judge_policy,
    _SECTION_POLICIES,
)
from apps_rg.runtime.sections.section_product_shape_ssot import (
    section_product_shape,
    product_shape_gate_ids_for_lane,
    RETIRED_EXEC_SUMMARY_X2_GATE_IDS,
)
from apps_rg.runtime.judges.competencies_x1d import (
    run_competencies_judges,
    _is_test_environment as comp_is_test_env,
)
from apps_rg.runtime.judges.x1d_panel_bridge import (
    _is_test_environment as bridge_is_test_env,
)

# Canonical 11 active generated sections
CANONICAL_11_ACTIVE_LANES: frozenset[str] = frozenset(
    {
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "executive_summary",
        "headline",
    }
)

LOCKED_DETERMINISTIC_SECTIONS: frozenset[str] = frozenset(
    {
        "early_career",
        "education",
        "certifications",
    }
)

DEPRECATED_ORPHANED_SECTIONS: frozenset[str] = frozenset(
    {
        "ey_bullets",
        "ey_narrative",
        "marketing_bullets",
        "strategy_narrative",
        "consulting_bullets",
    }
)


# ==============================================================================
# Vector 1: Zero Orphaned or Phantom Sections
# ==============================================================================
class TestVector1ZeroOrphanedSections:
    """Adversarially probe that deprecated/phantom lanes never pollute registries."""

    def test_zero_orphaned_lanes_in_registries(self) -> None:
        for orphan in DEPRECATED_ORPHANED_SECTIONS:
            assert orphan not in glr.GENERATED_LANES, f"Orphan {orphan} found in GENERATED_LANES"
            assert orphan not in GENERATED_CONTENT_LANES, f"Orphan {orphan} found in GENERATED_CONTENT_LANES"
            assert orphan not in BULLET_LANES, f"Orphan {orphan} found in BULLET_LANES"
            assert orphan not in NARRATIVE_LANES, f"Orphan {orphan} found in NARRATIVE_LANES"
            assert orphan not in SECTION_EXECUTION_POLICIES, f"Orphan {orphan} in SECTION_EXECUTION_POLICIES"
            assert orphan not in _SECTION_DEFAULT_PROVIDER, f"Orphan {orphan} in _SECTION_DEFAULT_PROVIDER"
            assert orphan not in _SECTION_DEFAULT_X1D_JUDGES, f"Orphan {orphan} in _SECTION_DEFAULT_X1D_JUDGES"
            assert orphan not in SECTION_LANE_RUNNERS, f"Orphan {orphan} in SECTION_LANE_RUNNERS"
            assert orphan not in _SECTION_POLICIES, f"Orphan {orphan} in _SECTION_POLICIES"

    def test_selector_role_raises_for_orphaned_lanes(self) -> None:
        for orphan in DEPRECATED_ORPHANED_SECTIONS:
            with pytest.raises(SectionModelSSOTError):
                selector_role_for_section(orphan)

    def test_workflow_manifest_has_no_orphaned_lanes(self) -> None:
        manifest = load_section_dag_manifest()
        all_manifest_lanes = {lane for wave in manifest.get("phase1_waves", []) for lane in wave.get("lanes", [])}
        for orphan in DEPRECATED_ORPHANED_SECTIONS:
            assert orphan not in all_manifest_lanes, f"Orphan {orphan} found in workflow manifest DAG"


# ==============================================================================
# Vector 2: 100% Exact Parity Across All 4 Section Authority Registries
# ==============================================================================
class TestVector2RegistryParityAndWaveDAG:
    """Adversarially probe that all section authority registries are in 100% parity."""

    def test_four_authority_registries_exact_parity(self) -> None:
        manifest = load_section_dag_manifest()
        manifest_lanes = {lane["id"] for lane in manifest.get("lanes", [])}

        glr_lanes = set(glr.GENERATED_LANES)
        content_lanes = set(GENERATED_CONTENT_LANES)
        policy_lanes = set(_SECTION_POLICIES.keys())
        provider_lanes = set(_SECTION_DEFAULT_PROVIDER.keys())
        runners_lanes = set(SECTION_LANE_RUNNERS.keys())

        assert glr_lanes == CANONICAL_11_ACTIVE_LANES, "glr.GENERATED_LANES mismatch"
        assert content_lanes == CANONICAL_11_ACTIVE_LANES, "GENERATED_CONTENT_LANES mismatch"
        assert policy_lanes == CANONICAL_11_ACTIVE_LANES | {"final_aggregate_resume"}, "_SECTION_POLICIES mismatch"
        assert manifest_lanes == CANONICAL_11_ACTIVE_LANES, "Manifest DAG lanes mismatch"
        assert provider_lanes == CANONICAL_11_ACTIVE_LANES, "_SECTION_DEFAULT_PROVIDER mismatch"
        assert runners_lanes == CANONICAL_11_ACTIVE_LANES, "SECTION_LANE_RUNNERS mismatch"

    def test_wave_dag_hierarchy_invariants(self) -> None:
        waves = build_phase1_waves()
        manifest = load_section_dag_manifest()

        # Structural order validation raises if cycle or backwards dependency exists
        assert_section_dag_wave_order(manifest)

        lane_wave = {lane: w.wave_id for w in waves for lane in w.lanes}

        # Bullets and competencies are Wave 0
        assert lane_wave["competencies"] == 0
        assert lane_wave["slalom_bullets"] == 0
        assert lane_wave["unify_bullets"] == 0
        assert lane_wave["ibm_bullets"] == 0
        assert lane_wave["insurtech_bullets"] == 0

        # Narratives are Wave 1
        assert lane_wave["slalom_narrative"] == 1
        assert lane_wave["unify_narrative"] == 1
        assert lane_wave["ibm_narrative"] == 1
        assert lane_wave["insurtech_narrative"] == 1

        # Executive summary is Wave 2 (after all bullets and narratives)
        assert lane_wave["executive_summary"] == 2

        # Headline is Wave 3 (runs last)
        assert lane_wave["headline"] == 3


# ==============================================================================
# Vector 3: Calibrated Cross-Provider Proof Judges (No Self-Judging)
# ==============================================================================
class TestVector3CrossProviderProofJudges:
    """Adversarially probe that judges are non-empty, cross-provider, and strictly calibrated."""

    def test_every_generated_section_has_calibrated_cross_provider_judges(self) -> None:
        for lane in CANONICAL_11_ACTIVE_LANES:
            policy = get_section_judge_policy(lane)
            gen_provider = default_lane_provider_for_section(lane)

            # Judge list cannot be empty
            assert len(policy.required_judge_providers) > 0, f"Section {lane} has empty proof judges"

            # Cross-provider enforcement: Generator model family MUST NOT judge itself
            for judge in policy.required_judge_providers:
                assert judge in {"gemini_pro", "openai_chatgpt"}, f"Invalid proof judge {judge} for {lane}"
                if "claude" in gen_provider:
                    assert "claude" not in judge, f"Self-judging detected in {lane}: {gen_provider} vs {judge}"
                if "openai" in gen_provider:
                    # Narratives (external_openai) must use gemini_pro as sole judge (no self-judging)
                    assert judge == "gemini_pro", f"OpenAI generator self-judging in {lane}: {judge}"

    def test_calibrated_panel_sizes(self) -> None:
        dual_panel_sections = {"competencies", "executive_summary", "headline"}
        single_judge_sections = {
            "slalom_bullets",
            "unify_bullets",
            "ibm_bullets",
            "insurtech_bullets",
            "slalom_narrative",
            "unify_narrative",
            "ibm_narrative",
            "insurtech_narrative",
        }

        for lane in dual_panel_sections:
            policy = get_section_judge_policy(lane)
            assert len(policy.required_judge_providers) == 2, f"{lane} must have exactly 2 proof judges"
            assert set(policy.required_judge_providers) == {"gemini_pro", "openai_chatgpt"}

        for lane in single_judge_sections:
            policy = get_section_judge_policy(lane)
            assert len(policy.required_judge_providers) == 1, f"{lane} must have exactly 1 proof judge"
            assert policy.required_judge_providers == ("gemini_pro",)


# ==============================================================================
# Vector 4: Runtime Profile Reasoning Tier Monotonicity
# ==============================================================================
class TestVector4RuntimeProfileMonotonicity:
    """Adversarially probe provider profiles for reasoning tier order inversion."""

    def test_provider_profiles_thinking_level_monotonicity(self) -> None:
        profiles_path = resolve_apps_rg_path(
            Path(__file__).resolve().parents[3],
            "config",
            "provider_profiles.yaml",
        )
        data = yaml.safe_load(profiles_path.read_text(encoding="utf-8"))
        judge_cfg = data.get("runtime_limits", {}).get("judge", {})
        profiles = judge_cfg.get("runtime_profiles", {})

        tier_order = {
            "none": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
        }

        opt_level = tier_order[profiles["optional_advisory_taxonomy_only"]["gemini_thinking_level"]]
        std_level = tier_order[profiles["standard_reasoning"]["gemini_thinking_level"]]
        enh_level = tier_order[profiles["enhanced_reasoning"]["gemini_thinking_level"]]
        proof_level = tier_order[judge_cfg["gemini_proof_thinking_level"]]

        # Strict monotonicity across reasoning tiers
        assert opt_level <= std_level, "optional_advisory > standard_reasoning"
        assert std_level <= enh_level, "standard_reasoning > enhanced_reasoning"
        assert enh_level <= proof_level, "enhanced_reasoning > gemini_proof_thinking_level"

        # Exact expected tier calibration
        assert profiles["optional_advisory_taxonomy_only"]["gemini_thinking_level"] == "low"
        assert profiles["standard_reasoning"]["gemini_thinking_level"] == "low"
        assert profiles["enhanced_reasoning"]["gemini_thinking_level"] == "medium"
        assert judge_cfg["gemini_proof_thinking_level"] == "high"

        # Bullet rewrite quality must match standard reasoning
        assert profiles["bullet_rewrite_quality"]["gemini_thinking_level"] == "low"


# ==============================================================================
# Vector 5: Production Mode Fails Closed on Mock Judges
# ==============================================================================
class TestVector5ProductionModeMockJudgeRejection:
    """Adversarially probe that mock judges fail closed when production is active."""

    def test_production_mode_fails_closed_on_mock_judges(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")

        # In production mode, test environment detection MUST be false
        assert comp_is_test_env() is False
        assert bridge_is_test_env() is False

        # Calling run_competencies_judges with mode='mocked' in production MUST raise RuntimeError
        with pytest.raises(RuntimeError, match="MOCK_JUDGE_FORBIDDEN"):
            run_competencies_judges(
                competencies=[],
                claim_ledger=[],
                judge_keys=["gemini_pro"],
                mode="mocked",
            )


# ==============================================================================
# Vector 6: Deterministic X2 Gate Completeness
# ==============================================================================
class TestVector6DeterministicX2Gates:
    """Adversarially probe that every active section has complete, valid X2 gates."""

    def test_every_generated_section_has_deterministic_x2_gates(self) -> None:
        for lane in CANONICAL_11_ACTIVE_LANES:
            shape = section_product_shape(lane)
            assert shape.section_id == lane, f"Shape section_id mismatch: {shape.section_id} vs {lane}"

            # Gate list must be non-empty
            assert len(shape.required_gate_ids) > 0, f"Section {lane} has empty required_gate_ids"

            # All gate IDs must start with x2_
            for gid in shape.required_gate_ids:
                assert gid.startswith("x2_"), f"Gate {gid} in {lane} does not start with 'x2_'"
                assert gid not in RETIRED_EXEC_SUMMARY_X2_GATE_IDS, f"Retired gate {gid} found in {lane}"

            # Product shape gate IDs by lane must be non-empty
            ps_gates = product_shape_gate_ids_for_lane(lane)
            assert len(ps_gates) > 0, f"Empty product shape gates for {lane}"


# ==============================================================================
# Vector 7: Locked Sections Isolation and Assembly Invariance
# ==============================================================================
class TestVector7LockedSectionsIsolation:
    """Adversarially probe that locked sections are invariant and ungenerated."""

    def test_locked_sections_never_routed_to_generators(self) -> None:
        manifest = load_section_dag_manifest()
        manifest_lanes = {lane for wave in manifest.get("phase1_waves", []) for lane in wave.get("lanes", [])}

        for locked in LOCKED_DETERMINISTIC_SECTIONS:
            assert locked not in glr.GENERATED_LANES, f"Locked section {locked} found in GENERATED_LANES"
            assert locked not in GENERATED_CONTENT_LANES, f"Locked section {locked} found in GENERATED_CONTENT_LANES"
            assert locked not in _SECTION_DEFAULT_PROVIDER, f"Locked section {locked} found in _SECTION_DEFAULT_PROVIDER"
            assert locked not in _SECTION_DEFAULT_X1D_JUDGES, f"Locked section {locked} in _SECTION_DEFAULT_X1D_JUDGES"
            assert locked not in SECTION_LANE_RUNNERS, f"Locked section {locked} in SECTION_LANE_RUNNERS"
            assert locked not in manifest_lanes, f"Locked section {locked} in Phase 1 DAG manifest"
            assert locked not in _SECTION_POLICIES, f"Locked section {locked} in _SECTION_POLICIES"
