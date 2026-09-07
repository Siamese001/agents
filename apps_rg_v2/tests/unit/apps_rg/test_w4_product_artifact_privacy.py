"""Wave 4 product diagnostic redaction regressions."""

from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.product_artifact_privacy import (
    REDACTION_RECEIPT,
    redact_product_diagnostics,
)


def test_product_diagnostic_redaction_removes_raw_prompt_and_provider_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "compiled_prompt.txt").write_text("resume: Alice Example", encoding="utf-8")
    (tmp_path / "raw_model_output.txt").write_text("candidate output", encoding="utf-8")
    (tmp_path / "provider_request.json").write_text(
        json.dumps({"model": "model-1", "messages": [{"content": "secret JD"}]}),
        encoding="utf-8",
    )
    (tmp_path / "provider_response.json").write_text(
        json.dumps({"model": "model-1", "raw_response": {"text": "secret response"}}),
        encoding="utf-8",
    )

    receipt_path = redact_product_diagnostics(tmp_path)

    assert receipt_path == tmp_path / REDACTION_RECEIPT
    assert "Alice Example" not in (tmp_path / "compiled_prompt.txt").read_text(encoding="utf-8")
    assert "candidate output" not in (tmp_path / "raw_model_output.txt").read_text(encoding="utf-8")
    request = json.loads((tmp_path / "provider_request.json").read_text(encoding="utf-8"))
    response = json.loads((tmp_path / "provider_response.json").read_text(encoding="utf-8"))
    assert request["model"] == "model-1"
    assert request["messages"]["redacted"] is True
    assert response["model"] == "model-1"
    assert response["raw_response"]["redacted"] is True
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["redacted_count"] == 4
    assert all("original_sha256" in row for row in receipt["redactions"])


def test_product_diagnostic_redaction_preserves_non_diagnostic_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "canonical_claim_ledger_v2.json"
    original = '{"claim_id":"c1","text":"allowed proof"}\n'
    evidence.write_text(original, encoding="utf-8")

    redact_product_diagnostics(tmp_path)

    assert evidence.read_text(encoding="utf-8") == original
