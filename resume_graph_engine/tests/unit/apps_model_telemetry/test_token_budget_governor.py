from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_model_telemetry.token_budget_governor import (
    RESERVATION_FILENAME,
    TokenBudgetPolicy,
    _filesystem_path,
    reserve_token_budget,
)


POLICY = TokenBudgetPolicy(
    chars_per_token_estimate=4,
    safety_multiplier=1.0,
    max_input_tokens_per_attempt=10,
    max_reserved_tokens_per_run=30,
)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_reservation_is_append_only_and_blocks_before_run_capacity_is_exceeded(tmp_path: Path) -> None:
    first = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="first",
        prompt_text="abcd" * 5,
        max_output_tokens=5,
        policy=POLICY,
        stage="L2.test",
    )
    second = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="second",
        prompt_text="abcd" * 5,
        max_output_tokens=5,
        policy=POLICY,
        stage="L2.test",
    )

    assert first.allowed is True
    assert first.reserved_total_tokens == 10
    assert second.allowed is True
    assert second.prior_reserved_total_tokens == 10

    blocked = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="third",
        prompt_text="abcd" * 5,
        max_output_tokens=15,
        policy=POLICY,
        stage="L2.test",
    )
    assert blocked.allowed is False
    assert blocked.reason == "RUN_RESERVED_TOKEN_CAP_EXCEEDED"
    rows = _rows(tmp_path / RESERVATION_FILENAME)
    assert [row["decision"] for row in rows] == ["RESERVED", "RESERVED", "BLOCKED"]
    assert all(row["event_digest"] for row in rows)


def test_input_cap_blocks_without_sending_or_storing_prompt_text(tmp_path: Path) -> None:
    blocked = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="openai",
        model="gpt-test",
        request_digest="digest",
        prompt_text="secret prompt body" * 10,
        max_output_tokens=1,
        policy=POLICY,
        stage="L2.test",
    )

    assert blocked.allowed is False
    assert blocked.reason == "INPUT_ATTEMPT_CAP_EXCEEDED"
    rendered = (tmp_path / RESERVATION_FILENAME).read_text(encoding="utf-8")
    assert "secret prompt body" not in rendered


def test_malformed_prior_ledger_fails_closed(tmp_path: Path) -> None:
    (tmp_path / RESERVATION_FILENAME).write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed token reservation ledger"):
        reserve_token_budget(
            artifact_dir=tmp_path,
            provider="openai",
            model="gpt-test",
            request_digest="digest",
            prompt_text="small",
            max_output_tokens=1,
            policy=POLICY,
            stage="L2.test",
        )


def test_reservation_ledger_supports_long_windows_run_path(tmp_path: Path) -> None:
    base = tmp_path
    while len(str((base / RESERVATION_FILENAME).resolve(strict=False))) <= 260:
        base = base / f"deep_segment_{len(base.parts):02d}"
    policy = TokenBudgetPolicy(
        chars_per_token_estimate=4,
        safety_multiplier=1.0,
        max_input_tokens_per_attempt=100,
        max_reserved_tokens_per_run=200,
    )

    reservation = reserve_token_budget(
        artifact_dir=base,
        provider="gemini",
        model="gemini-test",
        request_digest="long-path",
        prompt_text="short prompt",
        max_output_tokens=10,
        policy=policy,
        stage="X1D",
        run_id="run-long",
    )

    assert reservation.allowed is True
    assert _filesystem_path(base / RESERVATION_FILENAME).is_file()


def test_stage_caps_enforcement(tmp_path: Path) -> None:
    policy = TokenBudgetPolicy(
        chars_per_token_estimate=4,
        safety_multiplier=1.0,
        max_input_tokens_per_attempt=100,
        max_reserved_tokens_per_run=1000,
        stage_caps={"stage_a": 20, "stage_b": 50},
    )
    res1 = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="d1",
        prompt_text="abcd" * 2,  # 2 tokens
        max_output_tokens=10,    # total 12
        policy=policy,
        stage="stage_a",
    )
    assert res1.allowed is True

    # Next call on stage_a with 12 tokens would exceed stage_a cap of 20 (12+12=24 > 20)
    res2 = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="d2",
        prompt_text="abcd" * 2,
        max_output_tokens=10,
        policy=policy,
        stage="stage_a",
    )
    assert res2.allowed is False
    assert res2.reason == "STAGE_RESERVED_TOKEN_CAP_EXCEEDED"

    # But stage_b with 30 tokens is allowed (0+32 <= 50)
    res3 = reserve_token_budget(
        artifact_dir=tmp_path,
        provider="gemini",
        model="gemini-test",
        request_digest="d3",
        prompt_text="abcd" * 2,
        max_output_tokens=30,
        policy=policy,
        stage="stage_b",
    )
    assert res3.allowed is True


def test_reconcile_token_reservation(tmp_path: Path) -> None:
    from apps_model_telemetry.external_model_usage import append_external_model_usage
    from apps_model_telemetry.token_budget_governor import reconcile_token_reservation

    reserve_token_budget(
        artifact_dir=tmp_path,
        provider="openai",
        model="gpt-test",
        request_digest="d1",
        prompt_text="abcd" * 5,  # 5 tokens
        max_output_tokens=20,    # 25 tokens reserved
        policy=POLICY,
        stage="L2.gen",
    )
    append_external_model_usage(
        artifact_dir=tmp_path,
        provider="openai",
        model="gpt-test",
        request_digest="d1",
        outcome="SUCCESS",
        provider_status="OK",
        usage={"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        stage="L2.gen",
    )

    reconciled = reconcile_token_reservation(artifact_dir=tmp_path, run_id="run-test")
    assert reconciled["total_reserved_tokens"] == 25
    assert reconciled["total_actual_tokens"] == 15
    assert reconciled["unconsumed_reserved_tokens"] == 10
    assert reconciled["stage_reserved_tokens"]["L2.gen"] == 25
    assert reconciled["stage_actual_tokens"]["L2.gen"] == 15


def test_unbound_fails_closed_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("PYTEST_VERSION", raising=False)
    monkeypatch.setattr(sys, "modules", {k: v for k, v in sys.modules.items() if k != "pytest"})

    res = reserve_token_budget(
        artifact_dir=None,
        provider="gemini",
        model="gemini-test",
        request_digest="d1",
        prompt_text="test",
        max_output_tokens=10,
        policy=POLICY,
        stage="L2.test",
    )
    assert res.allowed is False
    assert res.reason == "UNBOUND_RUN_ARTIFACT_BLOCKED"
