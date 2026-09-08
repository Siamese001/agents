from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.e2e_operational_evaluation import (
    MANIFEST_VERSION,
    STAGES,
    runtime_lanes,
    validate_e2e_operational_manifest,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "e2e_operational_manifest.v1.schema.json"


def _attempt(identifier: str, cache_mode: str, status: str = "COMPLETE") -> dict[str, object]:
    complete = status == "COMPLETE"
    failed = status == "FAILED"
    abstained = status == "ABSTAINED"
    terminal_stage = "U0"
    return {
        "attempt_id": identifier,
        "input_digest": f"sha256:input-{identifier}",
        "apps_research_to_u0": {"observed": True, "valid": True, "status": "PASS", "receipt_digest": f"sha256:handoff-{identifier}"},
        "runtime": {"provider": "provider", "model": "model", "configuration_digest": "sha256:runtime", "cache_mode": cache_mode},
        "status": status,
        "stage_ledger": list(STAGES if complete else STAGES[: STAGES.index(terminal_stage) + 1]),
        "failed_stage": terminal_stage if failed else None,
        "failure_code": "U0_PROVIDER_TIMEOUT" if failed else None,
        "abstained_stage": terminal_stage if abstained else None,
        "abstention_code": "U0_INSUFFICIENT_EVIDENCE" if abstained else None,
        "lanes": [{"lane_id": lane, "status": "COMPLETE", "artifact_digest": f"sha256:{identifier}-{lane}"} for lane in runtime_lanes()] if complete else [],
        "operational": {"latency_ms": 100.0, "token_count": 1000, "provider_cost": 0.1, "retry_count": 0, "provider_error_count": 0},
        "document": {
            "status": "COMPLETE" if complete else "NOT_PRODUCED",
            "pdf_sha256": "sha256:pdf" if complete else "",
            "docx_sha256": "sha256:docx" if complete else "",
            "source_text_digest": "sha256:text" if complete else "",
            "parsed_pdf_text_digest": "sha256:text" if complete else "",
            "parsed_docx_text_digest": "sha256:text" if complete else "",
            "section_order_verified": complete,
            "overflow_count": 0,
        },
        "guardrails": {"pii_leak_count": 0, "counterfactual_status": "PASS", "authority_bypass_count": 0},
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": MANIFEST_VERSION,
        "evaluation_id": "w6-test",
        "required_lanes": list(runtime_lanes()),
        "slo": {"completion_rate_min": 0.8, "latency_p95_ms_max": 500, "cost_per_completed_resume_max": 1, "provider_error_rate_max": 0.5},
        "attempts": [
            _attempt("cold-1", "COLD"), _attempt("cold-2", "COLD"), _attempt("cold-3", "COLD"),
            _attempt("warm-1", "WARM"), _attempt("warm-2", "WARM"), _attempt("warm-3", "WARM"),
        ],
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_schema_and_tracked_manifest_are_not_measured() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_manifest())
    result = validate_e2e_operational_manifest()
    assert result["status"] == "NOT_MEASURED"
    assert "P2_NO_SOURCE_BOUND_E2E_ATTEMPTS" in result["not_measured_reasons"]
    assert result["authority"]["production_authorizing"] is False


def test_complete_source_bound_attempts_pass_technical_operational_contract(tmp_path: Path) -> None:
    path = tmp_path / "w6.json"
    _write(path, _manifest())
    result = validate_e2e_operational_manifest(path)
    assert result["status"] == "PASS"
    assert result["operational_metrics"]["completion_rate"] == 1.0
    assert result["operational_metrics"]["token_count_total"] == 6000.0
    assert result["operational_metrics"]["retry_count_total"] == 0.0
    assert result["authority"]["release_authorizing"] is False


def test_failed_attempts_are_retained_in_completion_denominator(tmp_path: Path) -> None:
    manifest = _manifest()
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempts.append(_attempt("warm-failed", "WARM", "FAILED"))
    path = tmp_path / "failed.json"
    _write(path, manifest)
    result = validate_e2e_operational_manifest(path)
    assert result["status"] == "PASS"
    assert result["operational_metrics"]["attempt_count"] == 7
    assert result["operational_metrics"]["failed_attempt_count"] == 1
    assert result["operational_metrics"]["completion_rate"] == 6 / 7
    assert result["operational_metrics"]["failed_stage_distribution"] == {"U0": 1}


def test_abstained_attempts_are_retained_in_completion_denominator(tmp_path: Path) -> None:
    manifest = _manifest()
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    attempts.append(_attempt("warm-abstained", "WARM", "ABSTAINED"))
    path = tmp_path / "abstained.json"
    _write(path, manifest)

    result = validate_e2e_operational_manifest(path)

    assert result["status"] == "PASS"
    assert result["operational_metrics"]["eligible_attempt_count"] == 7
    assert result["operational_metrics"]["abstained_attempt_count"] == 1
    assert result["operational_metrics"]["completion_rate"] == 6 / 7
    assert result["operational_metrics"]["abstained_stage_distribution"] == {
        "U0": 1
    }


def test_abstained_attempt_requires_explicit_terminal_cause(tmp_path: Path) -> None:
    manifest = _manifest()
    attempts = manifest["attempts"]
    assert isinstance(attempts, list)
    abstained = _attempt("warm-abstained", "WARM", "ABSTAINED")
    abstained["abstention_code"] = None
    attempts.append(abstained)
    path = tmp_path / "invalid-abstained.json"
    _write(path, manifest)

    result = validate_e2e_operational_manifest(path)

    assert result["status"] == "BLOCKED"
    assert "P2_ABSTAINED_ATTEMPT_CAUSE_INVALID" in result["blocking_reasons"]


def test_invalid_handoff_and_critical_document_or_privacy_fail_closed(tmp_path: Path) -> None:
    invalid = _manifest()
    attempts = invalid["attempts"]
    assert isinstance(attempts, list) and isinstance(attempts[0], dict)
    handoff = attempts[0]["apps_research_to_u0"]
    assert isinstance(handoff, dict)
    handoff["valid"] = False
    invalid_path = tmp_path / "invalid.json"
    _write(invalid_path, invalid)
    blocked = validate_e2e_operational_manifest(invalid_path)
    assert blocked["status"] == "BLOCKED"
    assert "P2_APPS_RESEARCH_TO_U0_HANDOFF_INVALID" in blocked["blocking_reasons"]

    privacy = _manifest()
    privacy_attempts = privacy["attempts"]
    assert isinstance(privacy_attempts, list) and isinstance(privacy_attempts[0], dict)
    guardrails = privacy_attempts[0]["guardrails"]
    assert isinstance(guardrails, dict)
    guardrails["pii_leak_count"] = 1
    privacy_path = tmp_path / "privacy.json"
    _write(privacy_path, privacy)
    failed = validate_e2e_operational_manifest(privacy_path)
    assert failed["status"] == "FAIL"
    assert "P2_CRITICAL_PII_LEAK" in failed["failure_reasons"]

    document = _manifest()
    document_attempts = document["attempts"]
    assert isinstance(document_attempts, list) and isinstance(document_attempts[0], dict)
    record = document_attempts[0]["document"]
    assert isinstance(record, dict)
    record["parsed_pdf_text_digest"] = "sha256:changed"
    document_path = tmp_path / "document.json"
    _write(document_path, document)
    doc_failed = validate_e2e_operational_manifest(document_path)
    assert doc_failed["status"] == "FAIL"
    assert "P2_DOCUMENT_ROUNDTRIP_TEXT_MISMATCH" in doc_failed["failure_reasons"]
