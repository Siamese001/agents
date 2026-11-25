"""Unit tests for Outreach Engine keyless IDE CLI proof-judge wiring, failover, and fail-closed blocks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps_lic.judges import ide_cli_judge as lic_ide
from apps_lic.judges.evaluator import GradeOnlyJudgePacket, evaluate_x1d_judge_quorum
from infrastructure.sdks_mcps.agy_cli_transport import (
    AgyQuotaExhaustedError,
    AgyResult,
    AgyTransportError,
    clear_agy_quota_cooldowns,
)


def _sample_packet() -> GradeOnlyJudgePacket:
    return GradeOnlyJudgePacket(
        run_id="run_ide_001",
        mission_id="mission_truist_001",
        touches=(
            {
                "touch_number": 1,
                "subject": "AI governance architecture note",
                "body": "Delivered 22% faster release cycles across regulated platforms [fact_id:f1]. Open to comparing notes Thursday?",
                "cited_fact_ids": ["f1"],
            },
        ),
        allocated_fact_ids_by_touch={1: ["f1"]},
        x2_passed=True,
        drafter_model_id="claude-sonnet-5-5-high",
        drafter_family="anthropic",
    )


def test_x1d_ide_cli_dual_quorum_passes_with_real_receipts(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_agy_quota_cooldowns()
    calls: list[str] = []
    efforts: list[str | None] = []
    monkeypatch.setattr(lic_ide, "ide_cli_ready", lambda b=None: (True, ""))

    def fake_run_agy(prompt: str, *, model: str, json_schema=None, effort=None, timeout_s=240, agy_bin=None) -> AgyResult:
        calls.append(model)
        efforts.append(effort)
        payload = {
            "cold_read_takeaway": "Grounded peer-level sequence with clean low-friction CTA.",
            "checks": {
                "pct_and_fact_grounding": {"verdict": "YES", "evidence_span": ""},
                "disjoint_cross_touch_facts": {"verdict": "YES", "evidence_span": ""},
                "peer_altitude_without_spam": {"verdict": "YES", "evidence_span": ""},
                "calibrated_sequence_friction": {"verdict": "YES", "evidence_span": ""},
            },
            "failure_tags": [],
        }
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response=json.dumps(payload),
            structured_output=payload,
            usage={"total_tokens": 512},
            duration_seconds=2.1,
            conversation_id=f"conv_{model}",
        )

    monkeypatch.setattr(lic_ide, "run_agy", fake_run_agy)
    report = evaluate_x1d_judge_quorum(_sample_packet(), transport="ide_cli", agy_bin="/fake/agy")
    assert report.quorum_passed is True
    assert report.recommended_x3_disposition == "X3D_ALLOW_FINISH"
    assert len(calls) == 2
    assert calls[0] != calls[1]
    assert efforts == ["high", "high"]
    assert all(v.transport == "ide_cli" for v in report.votes)
    assert all(v.evaluator_mode == "MODEL_BACKED" for v in report.votes)
    assert all(v.llm_judge_executed is True for v in report.votes)
    assert all(v.conversation_id and v.usage.get("total_tokens", 0) > 0 for v in report.votes)


def test_x1d_ide_cli_fails_closed_when_cli_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lic_ide, "ide_cli_ready", lambda b=None: (False, "AGY_CLI_BIN not set"))
    report = evaluate_x1d_judge_quorum(_sample_packet(), transport="ide_cli")
    assert report.quorum_passed is False
    assert report.recommended_x3_disposition == "X3E_SAFE_ABSTAIN"
    assert "X1D_IDE_CLI_PROVIDER_BLOCKED" in report.reason_codes
    assert all(v.evaluator_mode == "BLOCKED_PROVIDER_UNAVAILABLE" for v in report.votes)


def test_x1d_ide_cli_routes_429_quota_to_backup_model(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_agy_quota_cooldowns()
    attempted: list[str] = []
    monkeypatch.setattr(lic_ide, "ide_cli_ready", lambda b=None: (True, ""))

    def fake_run_agy(prompt: str, *, model: str, json_schema=None, timeout_s=240, agy_bin=None) -> AgyResult:
        attempted.append(model)
        if model == "gemini-4-argon-medium":
            raise AgyQuotaExhaustedError("429 RESOURCE_EXHAUSTED resets in 2m")
        payload = {
            "cold_read_takeaway": "Passed via failover pin.",
            "checks": {
                "pct_and_fact_grounding": {"verdict": "YES", "evidence_span": ""},
                "disjoint_cross_touch_facts": {"verdict": "YES", "evidence_span": ""},
                "peer_altitude_without_spam": {"verdict": "YES", "evidence_span": ""},
                "calibrated_sequence_friction": {"verdict": "YES", "evidence_span": ""},
            },
            "failure_tags": [],
        }
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response=json.dumps(payload),
            structured_output=payload,
            usage={"total_tokens": 300},
            duration_seconds=1.5,
            conversation_id=f"conv_backup_{model}",
        )

    monkeypatch.setattr(lic_ide, "run_agy", fake_run_agy)
    res = lic_ide.call_outreach_x1d_ide_cli_judge(
        packet_dict=_sample_packet().to_dict(),
        rubric={"rubric_id": "lic_x1d_v1"},
        slot="primary",
        drafter_family="anthropic",
        agy_bin="/fake/agy",
    )
    assert res.provider_blocked is False
    assert res.passed is True
    assert res.model_reported == "gemini-4-neon-medium"
    assert res.quota_failover_attempts == ("gemini-4-argon-medium", "gemini-4-neon-medium")
    clear_agy_quota_cooldowns()


def test_x1d_ide_cli_blocks_on_non_quota_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_agy_quota_cooldowns()
    monkeypatch.setattr(lic_ide, "ide_cli_ready", lambda b=None: (True, ""))

    def fake_run_agy(*args: Any, **kwargs: Any) -> AgyResult:
        raise AgyTransportError("agy timed out after 240s")

    monkeypatch.setattr(lic_ide, "run_agy", fake_run_agy)
    res = lic_ide.call_outreach_x1d_ide_cli_judge(
        packet_dict=_sample_packet().to_dict(),
        rubric={"rubric_id": "lic_x1d_v1"},
        slot="secondary",
        drafter_family="anthropic",
        agy_bin="/fake/agy",
    )
    assert res.provider_blocked is True
    assert res.passed is False
    assert res.evaluator_mode == "BLOCKED_PROVIDER_UNAVAILABLE"
