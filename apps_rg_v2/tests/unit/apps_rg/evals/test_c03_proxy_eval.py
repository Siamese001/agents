from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from apps_rg.evals.c03_proxy_eval import (
    build_proxy_report,
    emit_proxy_artifacts,
    validate_proxy_report,
    validate_proxy_summary,
)
from apps_rg.evals.c03_human_eval import _io as io_helpers
from apps_rg.evals.receipt_validation import CANONICAL_PROFILE, validate_artifact

PROFILE = CANONICAL_PROFILE


@pytest.fixture
def test_only_blocker(tmp_path: Path) -> Path:
    path = tmp_path / "w6-blocker.test-only.json"
    path.write_text(
        json.dumps(
            {
                "controlled_prelabel_freeze": {
                    "source_commit_sha": "0" * 40,
                    "packet_id": "TEST_ONLY_NON_AUTHORITATIVE_PACKET",
                    "source_freeze_receipt_digest": "1" * 64,
                    "packet_manifest_sha256": "2" * 64,
                    "packet_manifest_digest": "3" * 64,
                    "case_count": 6,
                    "claim_item_count": 282,
                    "retrieval_query_count": 84,
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_proxy_is_explicitly_non_authoritative_and_deterministic(
    test_only_blocker: Path,
) -> None:
    first = build_proxy_report(profile_path=PROFILE, blocker_path=test_only_blocker)
    second = build_proxy_report(profile_path=PROFILE, blocker_path=test_only_blocker)
    assert first == second
    assert first["evidence_class"] == "PROVISIONAL_MODEL_PROXY"
    assert first["authority"]["official_w6_status"] == "UNKNOWN"
    assert first["authority"]["release_gate_eligible"] is False
    assert first["authority"]["promotion_eligible"] is False
    assert first["authority"]["active_threshold"] is None


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX mode contract")
def test_proxy_outputs_are_private_and_official_checker_rejects_summary(
    tmp_path: Path,
    test_only_blocker: Path,
) -> None:
    report_path = tmp_path / "controlled" / "full.json"
    summary_path = tmp_path / "controlled" / "summary.json"
    _, summary = emit_proxy_artifacts(
        profile_path=PROFILE,
        blocker_path=test_only_blocker,
        report_path=report_path,
        summary_path=summary_path,
    )
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(summary_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(report_path.parent.stat().st_mode) == 0o700
    assert summary["official_status"] == "UNKNOWN"
    assert validate_artifact(summary_path)


def test_report_and_summary_tampering_is_rejected(
    tmp_path: Path,
    test_only_blocker: Path,
    emulated_posix_private_paths: None,
) -> None:
    report_path = tmp_path / "controlled" / "full.json"
    summary_path = tmp_path / "controlled" / "summary.json"
    report, summary = emit_proxy_artifacts(
        profile_path=PROFILE,
        blocker_path=test_only_blocker,
        report_path=report_path,
        summary_path=summary_path,
    )
    report["authority"]["promotion_eligible"] = True
    with pytest.raises(ValueError):
        validate_proxy_report(report)
    summary["official_status"] = "PASS"
    with pytest.raises(ValueError):
        validate_proxy_summary(summary)


def test_closed_schema_rejects_provenance_override(test_only_blocker: Path) -> None:
    report = build_proxy_report(profile_path=PROFILE, blocker_path=test_only_blocker)
    report["source"]["operator_override"] = "forged"
    # The record digest covers nested provenance, so even a nested extra field
    # cannot survive validation.
    with pytest.raises(ValueError):
        validate_proxy_report(report)


def test_proxy_output_fails_closed_without_owner_security(
    tmp_path: Path,
    test_only_blocker: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "controlled" / "full.json"
    summary_path = tmp_path / "controlled" / "summary.json"
    monkeypatch.delattr(io_helpers.os, "getuid", raising=False)

    with pytest.raises(ValueError, match="PLATFORM_SECURITY_UNSUPPORTED"):
        emit_proxy_artifacts(
            profile_path=PROFILE,
            blocker_path=test_only_blocker,
            report_path=report_path,
            summary_path=summary_path,
        )

    assert not report_path.exists()
    assert not summary_path.exists()
