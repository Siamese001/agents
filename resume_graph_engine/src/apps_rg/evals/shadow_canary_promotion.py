"""W8 identity-bound shadow/canary monitoring and promotion authority gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


MANIFEST_VERSION = "apps_rg.shadow_canary_promotion.v1"
SUMMARY_VERSION = "apps_rg.shadow_canary_promotion_summary.v1"
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("shadow_canary_promotion.v1.json")
IDENTITY_FIELDS = ("w7_receipt_digest", "scope_digest", "source_commit", "provider_model_pins_digest", "graph_digest")
SLO_FIELDS = ("minimum_request_count", "minimum_observation_window_seconds", "candidate_error_rate_delta_max", "candidate_p95_latency_ratio_max", "cost_per_completed_resume_max", "stage_failure_rate_max", "p1_proxy_delta_min", "p2_proxy_delta_min", "distribution_drift_max", "reviewer_disagreement_max")
ZERO_GUARDRAILS = ("pii_leak_count", "authority_bypass_count", "protected_holdout_leak_count")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def _identity_issues(expected: Any, observed: Any) -> tuple[set[str], set[str]]:
    blocking: set[str] = set()
    stale: set[str] = set()
    if not isinstance(expected, Mapping) or not isinstance(observed, Mapping) or any(not str(expected.get(key) or "") for key in IDENTITY_FIELDS):
        return {"P8_QUALIFICATION_IDENTITY_INVALID"}, stale
    for key in IDENTITY_FIELDS:
        if expected.get(key) != observed.get(key):
            stale.add(f"P8_IDENTITY_DRIFT_{key.upper()}")
    return blocking, stale


def _monitoring_issues(slo: Any, observation: Any) -> tuple[set[str], set[str], set[str]]:
    blocking: set[str] = set()
    failures: set[str] = set()
    not_measured: set[str] = set()
    if not isinstance(slo, Mapping) or set(slo) != set(SLO_FIELDS):
        return {"P8_SLO_SCHEMA_INVALID"}, failures, not_measured
    if any(value is None for value in slo.values()):
        not_measured.add("P8_SLOS_NOT_PREREGISTERED")
        return blocking, failures, not_measured
    if any(not _number(value) or float(value) < 0 for value in slo.values()):
        return {"P8_SLO_VALUES_INVALID"}, failures, not_measured
    required = ("request_count", "elapsed_window_seconds", "candidate_error_rate", "baseline_error_rate", "candidate_p95_latency_ms", "baseline_p95_latency_ms", "cost_per_completed_resume", "stage_failure_rate", "p1_proxy_delta", "p2_proxy_delta", "source_distribution_drift", "target_distribution_drift", "query_distribution_drift", "reviewer_disagreement", "guardrails", "slices")
    if not isinstance(observation, Mapping) or any(key not in observation for key in required):
        return {"P8_OBSERVATION_INCOMPLETE"}, failures, not_measured
    numeric = required[:14]
    if any(not _number(observation.get(key)) or float(observation[key]) < 0 for key in numeric if key not in {"p1_proxy_delta", "p2_proxy_delta"}) or any(not _number(observation.get(key)) for key in ("p1_proxy_delta", "p2_proxy_delta")):
        return {"P8_OBSERVATION_METRICS_INVALID"}, failures, not_measured
    if float(observation["request_count"]) < float(slo["minimum_request_count"]) or float(observation["elapsed_window_seconds"]) < float(slo["minimum_observation_window_seconds"]):
        not_measured.add("P8_OBSERVATION_WINDOW_INCOMPLETE")
    if float(observation["candidate_error_rate"]) - float(observation["baseline_error_rate"]) > float(slo["candidate_error_rate_delta_max"]):
        failures.add("P8_ERROR_RATE_SLO_FAILED")
    baseline_latency = float(observation["baseline_p95_latency_ms"])
    ratio = float("inf") if baseline_latency <= 0 else float(observation["candidate_p95_latency_ms"]) / baseline_latency
    if ratio > float(slo["candidate_p95_latency_ratio_max"]):
        failures.add("P8_P95_LATENCY_SLO_FAILED")
    if float(observation["cost_per_completed_resume"]) > float(slo["cost_per_completed_resume_max"]):
        failures.add("P8_COST_SLO_FAILED")
    if float(observation["stage_failure_rate"]) > float(slo["stage_failure_rate_max"]):
        failures.add("P8_STAGE_FAILURE_SLO_FAILED")
    if float(observation["p1_proxy_delta"]) < float(slo["p1_proxy_delta_min"]):
        failures.add("P8_P1_PROXY_SLO_FAILED")
    if float(observation["p2_proxy_delta"]) < float(slo["p2_proxy_delta_min"]):
        failures.add("P8_P2_PROXY_SLO_FAILED")
    if any(float(observation[key]) > float(slo["distribution_drift_max"]) for key in ("source_distribution_drift", "target_distribution_drift", "query_distribution_drift")):
        failures.add("P8_DISTRIBUTION_DRIFT_FAILED")
    if float(observation["reviewer_disagreement"]) > float(slo["reviewer_disagreement_max"]):
        failures.add("P8_REVIEWER_DISAGREEMENT_FAILED")
    guardrails = observation["guardrails"]
    if not isinstance(guardrails, Mapping) or any(guardrails.get(key) != 0 for key in ZERO_GUARDRAILS):
        failures.add("P8_CRITICAL_GUARDRAIL_FAILED")
    slices = observation["slices"]
    if not isinstance(slices, list) or not slices:
        blocking.add("P8_SLICE_OBSERVATIONS_REQUIRED")
    elif any(not isinstance(row, Mapping) or not str(row.get("slice_id") or "") or row.get("status") != "PASS" for row in slices):
        failures.add("P8_SLICE_GUARDRAIL_FAILED")
    return blocking, failures, not_measured


def _promotion_issues(authority: Any, identity: Mapping[str, Any]) -> set[str]:
    if not isinstance(authority, Mapping) or authority.get("status") == "NOT_SUPPLIED":
        return {"P8_HUMAN_PROMOTION_AUTHORITY_MISSING"}
    issues: set[str] = set()
    if authority.get("status") != "AUTHORIZED" or not str(authority.get("authorized_by") or "").startswith("human-promotion-authority://"):
        issues.add("P8_HUMAN_PROMOTION_AUTHORITY_INVALID")
    if not str(authority.get("authority_receipt_digest") or "") or authority.get("w7_receipt_digest") != identity.get("w7_receipt_digest") or authority.get("scope_digest") != identity.get("scope_digest") or authority.get("production_authorized") is not True:
        issues.add("P8_PROMOTION_AUTHORITY_BINDING_INVALID")
    return issues


def validate_shadow_canary_promotion(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = _read(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        manifest, blocking = {}, {"P8_MANIFEST_UNREADABLE"}
    else:
        blocking = set()
    failures: set[str] = set()
    stale: set[str] = set()
    not_measured: set[str] = set()
    authority_issues: set[str] = set()
    if manifest.get("schema_version") != MANIFEST_VERSION or not str(manifest.get("monitor_id") or ""):
        blocking.add("P8_MANIFEST_SCHEMA_INVALID")
    state = manifest.get("status")
    if state == "PENDING":
        not_measured.update({"P8_SHADOW_CANARY_NOT_RUN", "P8_PROMOTION_AUTHORITY_NOT_SUPPLIED"})
    elif state == "COMPLETE":
        identity = manifest.get("qualification_identity")
        identity_blocking, stale = _identity_issues(identity, manifest.get("observed_identity"))
        blocking.update(identity_blocking)
        monitor_blocking, monitor_failures, monitor_missing = _monitoring_issues(manifest.get("slo"), manifest.get("observation"))
        blocking.update(monitor_blocking)
        failures.update(monitor_failures)
        not_measured.update(monitor_missing)
        rehearsal = manifest.get("rollback_rehearsal")
        if not isinstance(rehearsal, Mapping) or rehearsal.get("status") != "PASS" or not str(rehearsal.get("incident_artifact_digest") or ""):
            failures.add("P8_ROLLBACK_NOT_REHEARSED")
        if isinstance(identity, Mapping):
            authority_issues = _promotion_issues(manifest.get("promotion_authority"), identity)
    else:
        blocking.add("P8_STATUS_INVALID")
    technical_pass = not blocking and not stale and not failures and not not_measured and state == "COMPLETE"
    status = "BLOCKED" if blocking else "STALE_SCOPE" if stale else "FAIL" if failures else "NOT_MEASURED" if not_measured else "PROMOTION_AUTHORIZED" if technical_pass and not authority_issues else "TECHNICALLY_QUALIFIED_NOT_AUTHORIZED"
    summary: dict[str, Any] = {"schema_version": SUMMARY_VERSION, "monitor_id": str(manifest.get("monitor_id") or path.stem), "status": status, "technical_qualification": technical_pass, "authority": {"technical_validation": True, "human_qualified": False, "release_authorizing": False, "production_authorizing": status == "PROMOTION_AUTHORIZED"}, "blocking_reasons": sorted(blocking), "stale_scope_reasons": sorted(stale), "failure_reasons": sorted(failures), "not_measured_reasons": sorted(not_measured), "promotion_authority_reasons": sorted(authority_issues)}
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W8 shadow/canary and promotion evidence")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    result = validate_shadow_canary_promotion(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PROMOTION_AUTHORIZED" else 2
