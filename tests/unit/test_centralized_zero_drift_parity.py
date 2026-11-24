"""Unit tests for centralized 4-way policy parity and 5-way workspace parity integration in `agents` (Wave 3)."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from tools.audit_governance_harmonization import audit_governance_harmonization

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_MCP = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
if str(_CORE_MCP) not in sys.path:
    sys.path.insert(0, str(_CORE_MCP))


def test_agents_four_way_governance_harmonization_passes() -> None:
    report = audit_governance_harmonization(_REPO_ROOT)
    assert report["status"] == "PASS", report["findings"]
    assert report["critical_count"] == 0


def test_centralized_judge_receipt_tamper_fails_closed(tmp_path: Path) -> None:
    from policy_ssot_parity_engine import check_centralized_studio_and_judge_parity

    (tmp_path / "artifacts" / "eval_harness").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "eval_harness" / "ide_judge_drift_receipt.json").write_text(
        json.dumps({"passed": True, "artifact_sha256": "f" * 64}),
        encoding="utf-8",
    )
    findings = check_centralized_studio_and_judge_parity(tmp_path)
    assert any(f["category"] == "judge_sha256_tamper" for f in findings)
