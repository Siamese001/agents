from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.shadow_canary_promotion import (
    IDENTITY_FIELDS,
    MANIFEST_VERSION,
    ZERO_GUARDRAILS,
    validate_shadow_canary_promotion,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict[str, object]:
    identity = {field: f"sha256:{field}" for field in IDENTITY_FIELDS}
    identity["source_commit"] = "commit"
    return {
        "schema_version": MANIFEST_VERSION, "monitor_id": "w8-test", "status": "COMPLETE",
        "qualification_identity": identity, "observed_identity": dict(identity),
        "slo": {"minimum_request_count": 10, "minimum_observation_window_seconds": 60, "candidate_error_rate_delta_max": 0.01, "candidate_p95_latency_ratio_max": 1.2, "cost_per_completed_resume_max": 1, "stage_failure_rate_max": 0.1, "p1_proxy_delta_min": 0, "p2_proxy_delta_min": 0, "distribution_drift_max": 0.2, "reviewer_disagreement_max": 0.2},
        "observation": {"request_count": 10, "elapsed_window_seconds": 60, "candidate_error_rate": 0.01, "baseline_error_rate": 0.01, "candidate_p95_latency_ms": 100, "baseline_p95_latency_ms": 100, "cost_per_completed_resume": 0.1, "stage_failure_rate": 0.01, "p1_proxy_delta": 0.01, "p2_proxy_delta": 0.01, "source_distribution_drift": 0.01, "target_distribution_drift": 0.01, "query_distribution_drift": 0.01, "reviewer_disagreement": 0.01, "guardrails": {field: 0 for field in ZERO_GUARDRAILS}, "slices": [{"slice_id": "protected-risk", "status": "PASS"}]},
        "rollback_rehearsal": {"status": "PASS", "incident_artifact_digest": "sha256:incident"},
        "promotion_authority": {"status": "NOT_SUPPLIED"},
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_schema_and_pending_manifest_are_not_measured() -> None:
    schema = json.loads((EVALS_ROOT / "schemas" / "shadow_canary_promotion.v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(json.loads((EVALS_ROOT / "shadow_canary_promotion.v1.json").read_text(encoding="utf-8")))
    assert validate_shadow_canary_promotion()["status"] == "NOT_MEASURED"


def test_complete_monitoring_requires_separate_human_promotion_authority(tmp_path: Path) -> None:
    path = tmp_path / "w8.json"
    _write(path, _manifest())
    result = validate_shadow_canary_promotion(path)
    assert result["status"] == "TECHNICALLY_QUALIFIED_NOT_AUTHORIZED"
    assert "P8_HUMAN_PROMOTION_AUTHORITY_MISSING" in result["promotion_authority_reasons"]
    assert result["authority"]["production_authorizing"] is False


def test_identity_drift_and_guardrail_breach_fail_closed(tmp_path: Path) -> None:
    stale = _manifest()
    observed = stale["observed_identity"]
    assert isinstance(observed, dict)
    observed["graph_digest"] = "sha256:changed"
    path = tmp_path / "stale.json"
    _write(path, stale)
    stale_result = validate_shadow_canary_promotion(path)
    assert stale_result["status"] == "STALE_SCOPE"
    assert "P8_IDENTITY_DRIFT_GRAPH_DIGEST" in stale_result["stale_scope_reasons"]

    failed = _manifest()
    observation = failed["observation"]
    assert isinstance(observation, dict)
    guardrails = observation["guardrails"]
    assert isinstance(guardrails, dict)
    guardrails["pii_leak_count"] = 1
    failed_path = tmp_path / "failed.json"
    _write(failed_path, failed)
    failed_result = validate_shadow_canary_promotion(failed_path)
    assert failed_result["status"] == "FAIL"
    assert "P8_CRITICAL_GUARDRAIL_FAILED" in failed_result["failure_reasons"]
