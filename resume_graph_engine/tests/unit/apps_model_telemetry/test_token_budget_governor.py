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
