"""Unit tests for Wave 3: Sealing Mock Judges & Candidate Selectors in apps_rg."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from apps_rg.runtime.judges.competencies_x1d import run_competencies_judges
from apps_rg.runtime.judges.x1d_panel_bridge import run_grade_only_judges_via_core_panel
from apps_rg.runtime.judges.bullet_pool_claude_selector import run_claude_bullet_pool_selection
from apps_rg.runtime.reasoning.bullet_lane_self_consistency import SelfConsistencyPath


def test_competencies_judge_rejects_mocked_in_production(monkeypatch):
    """Verify run_competencies_judges fails closed when mode='mocked' in production."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    with pytest.raises(RuntimeError, match="MOCK_JUDGE_FORBIDDEN"):
        run_competencies_judges(
            competencies=[{"competency": "Strategic Leadership"}],
            claim_ledger=[],
            judge_keys=["openai_chatgpt"],
            mode="mocked",
        )


def test_x1d_panel_bridge_rejects_mocked_in_production(monkeypatch):
    """Verify run_grade_only_judges_via_core_panel fails closed when mode='mocked' in production."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    with pytest.raises(RuntimeError, match="MOCK_PANEL_FORBIDDEN"):
        run_grade_only_judges_via_core_panel(
            judge_keys=["openai_chatgpt"],
            judge_packet={},
            user_prompt="Sample prompt",
            input_hash="1234567812345678",
            section_id="headline",
            mode="mocked",
            artifact_base=None,
            judge_packet_ref=None,
            contract_hash=None,
        )


def test_bullet_selector_rejects_single_path_bypass_in_production(monkeypatch):
    """Verify run_claude_bullet_pool_selection rejects single path bypass flag in production."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    monkeypatch.setenv("APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS", "1")
    dummy_path = SelfConsistencyPath(
        path_index=0,
        temperature=0.0,
        runtime_generation_status="OK",
        raw_output='{"bullets": [{"bullet_id": "b1", "text": "Achieved growth"}]}',
        parsed={"bullets": [{"bullet_id": "b1", "text": "Achieved growth"}]},
        parse_error="",
        provider_result=None,
    )
    with pytest.raises(RuntimeError, match="LIVE_SELECTOR_ENFORCEMENT.*APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS"):
        run_claude_bullet_pool_selection(
            section_id="experience",
            slot_kind="bullets",
            paths=[dummy_path],
            required_bullet_ids=("b1",),
        )


def test_bullet_selector_rejects_mocked_in_production(monkeypatch):
    """Verify run_claude_bullet_pool_selection rejects mode='mocked' in production."""
    monkeypatch.setenv("APPS_RG_PRODUCTION_RUN", "1")
    dummy_path = SelfConsistencyPath(
        path_index=0,
        temperature=0.0,
        runtime_generation_status="OK",
        raw_output='{"bullets": [{"bullet_id": "b1", "text": "Achieved growth"}]}',
        parsed={"bullets": [{"bullet_id": "b1", "text": "Achieved growth"}]},
        parse_error="",
        provider_result=None,
    )
    with pytest.raises(RuntimeError, match="LIVE_SELECTOR_ENFORCEMENT.*mode='mocked'"):
        run_claude_bullet_pool_selection(
            section_id="experience",
            slot_kind="bullets",
            paths=[dummy_path],
            required_bullet_ids=("b1",),
            mode="mocked",
        )


def test_competencies_judge_permits_mocked_in_test_environment(monkeypatch):
    """Verify test environments without APPS_RG_PRODUCTION_RUN allow mocked mode."""
    monkeypatch.delenv("APPS_RG_PRODUCTION_RUN", raising=False)
    outputs = run_competencies_judges(
        competencies=[{"competency": "Strategic Leadership"}],
        claim_ledger=[],
        judge_keys=["openai_chatgpt"],
        mode="mocked",
    )
    assert len(outputs) == 1
    assert outputs[0].evaluator_mode == "MOCKED"
    assert outputs[0].provider_status == "MOCKED"
