"""W6 source-bound Apps Research-to-Exit operational evaluation ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence


MANIFEST_VERSION = "apps_rg.e2e_operational_manifest.v1"
SUMMARY_VERSION = "apps_rg.e2e_operational_summary.v1"
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("e2e_operational_manifest.v1.json")
REPO_ROOT = Path(__file__).resolve().parents[3]
LANE_CONTRACT_PATH = REPO_ROOT / "src/apps_eval/registries/apps_rg_lane_contract.json"
STAGES = ("apps_research", "U0", "L1", "L0", "C0", "PA", "L2", "X2", "X1D", "X3", "EXIT")
ATTEMPT_STATUSES = ("COMPLETE", "FAILED", "ABSTAINED")
SLO_FIELDS = (
    "completion_rate_min",
    "latency_p95_ms_max",
    "cost_per_completed_resume_max",
    "provider_error_rate_max",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_lanes() -> tuple[str, ...]:
    contract = json.loads(LANE_CONTRACT_PATH.read_text(encoding="utf-8"))
    lanes = contract.get("generated_lanes") if isinstance(contract, Mapping) else None
    if not isinstance(lanes, list) or not lanes or any(not isinstance(lane, str) for lane in lanes):
        raise ValueError("runtime lane contract is invalid")
    return tuple(lanes)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("operational manifest must be a JSON object")
    return value


def _attempt_result(attempt: Any, lanes: tuple[str, ...]) -> tuple[dict[str, Any], set[str], set[str]]:
    blocking: set[str] = set()
    failures: set[str] = set()
    if not isinstance(attempt, Mapping):
        return {"attempt_id": "", "status": "BLOCKED"}, {"P2_ATTEMPT_INVALID"}, failures
    attempt_id = str(attempt.get("attempt_id") or "")
    status = attempt.get("status")
    result = {"attempt_id": attempt_id, "status": status}
    if not attempt_id or not str(attempt.get("input_digest") or ""):
        blocking.add("P2_ATTEMPT_IDENTITY_INVALID")
    handoff = attempt.get("apps_research_to_u0")
    if not isinstance(handoff, Mapping) or not (
        handoff.get("observed") is True
        and handoff.get("valid") is True
        and handoff.get("status") == "PASS"
        and str(handoff.get("receipt_digest") or "")
    ):
        blocking.add("P2_APPS_RESEARCH_TO_U0_HANDOFF_INVALID")
    runtime = attempt.get("runtime")
    if not isinstance(runtime, Mapping) or not all(
        str(runtime.get(field) or "") for field in ("provider", "model", "configuration_digest")
    ) or runtime.get("cache_mode") not in {"COLD", "WARM"}:
        blocking.add("P2_RUNTIME_IDENTITY_INVALID")
    stage_ledger = attempt.get("stage_ledger")
    if not isinstance(stage_ledger, list) or any(not isinstance(stage, str) for stage in stage_ledger):
        blocking.add("P2_STAGE_LEDGER_INVALID")
        stage_ledger = []
    operation = attempt.get("operational")
    if not isinstance(operation, Mapping) or any(
        not _number(operation.get(field)) or float(operation[field]) < 0
        for field in ("latency_ms", "token_count", "provider_cost", "retry_count", "provider_error_count")
    ):
        blocking.add("P2_OPERATIONAL_METRICS_INVALID")
    guardrails = attempt.get("guardrails")
    if not isinstance(guardrails, Mapping) or any(
        not isinstance(guardrails.get(field), int) or guardrails[field] < 0
        for field in ("pii_leak_count", "authority_bypass_count")
    ) or guardrails.get("counterfactual_status") not in {"PASS", "FAIL"}:
        blocking.add("P2_GUARDRAIL_RECORD_INVALID")
    elif guardrails["pii_leak_count"]:
        failures.add("P2_CRITICAL_PII_LEAK")
    elif guardrails["authority_bypass_count"]:
        failures.add("P2_CRITICAL_AUTHORITY_BYPASS")
    elif guardrails["counterfactual_status"] == "FAIL":
        failures.add("P2_COUNTERFACTUAL_FAIRNESS_FAILED")
    document = attempt.get("document")
    if not isinstance(document, Mapping):
        blocking.add("P2_DOCUMENT_RECORD_INVALID")
        document = {}
    lane_rows = attempt.get("lanes")
    if not isinstance(lane_rows, list):
        blocking.add("P2_LANE_RECORD_INVALID")
        lane_rows = []
    failed_stage = attempt.get("failed_stage")
    failure_code = attempt.get("failure_code")
    abstained_stage = attempt.get("abstained_stage")
    abstention_code = attempt.get("abstention_code")
    if status == "COMPLETE":
        if tuple(stage_ledger) != STAGES:
            blocking.add("P2_COMPLETE_STAGE_LINEAGE_INVALID")
        if tuple(
            row.get("lane_id") if isinstance(row, Mapping) else None for row in lane_rows
        ) != lanes or any(
            not isinstance(row, Mapping) or row.get("status") != "COMPLETE" or not str(row.get("artifact_digest") or "")
            for row in lane_rows
        ):
            blocking.add("P2_COMPLETE_LANE_COVERAGE_INVALID")
        if failed_stage not in (None, "") or failure_code not in (None, "") or abstained_stage not in (None, "") or abstention_code not in (None, ""):
            blocking.add("P2_COMPLETE_TERMINAL_FIELDS_INVALID")
        if document.get("status") != "COMPLETE":
            blocking.add("P2_DOCUMENT_RECORD_INVALID")
        elif not all(str(document.get(field) or "") for field in (
            "pdf_sha256", "docx_sha256", "source_text_digest", "parsed_pdf_text_digest", "parsed_docx_text_digest"
        )) or not isinstance(document.get("overflow_count"), int) or document["overflow_count"] < 0:
            blocking.add("P2_DOCUMENT_RECORD_INVALID")
        elif document.get("section_order_verified") is not True:
            failures.add("P2_DOCUMENT_SECTION_ORDER_FAILED")
        elif document["overflow_count"] != 0:
            failures.add("P2_DOCUMENT_OVERFLOW")
        elif document["source_text_digest"] != document["parsed_pdf_text_digest"] or document["source_text_digest"] != document["parsed_docx_text_digest"]:
            failures.add("P2_DOCUMENT_ROUNDTRIP_TEXT_MISMATCH")
    elif status == "FAILED":
        if not isinstance(failed_stage, str) or failed_stage not in STAGES or not str(attempt.get("failure_code") or ""):
            blocking.add("P2_FAILED_ATTEMPT_CAUSE_INVALID")
        elif tuple(stage_ledger) != STAGES[: STAGES.index(failed_stage) + 1]:
            blocking.add("P2_FAILED_STAGE_LINEAGE_INVALID")
        if abstained_stage not in (None, "") or abstention_code not in (None, ""):
            blocking.add("P2_FAILED_ATTEMPT_ABSTENTION_FIELDS_INVALID")
        if lane_rows:
            blocking.add("P2_INCOMPLETE_ATTEMPT_LANES_MUST_BE_EMPTY")
        if document.get("status") != "NOT_PRODUCED":
            blocking.add("P2_INCOMPLETE_DOCUMENT_RECORD_INVALID")
    elif status == "ABSTAINED":
        if not isinstance(abstained_stage, str) or abstained_stage not in STAGES or not str(abstention_code or ""):
            blocking.add("P2_ABSTAINED_ATTEMPT_CAUSE_INVALID")
        elif tuple(stage_ledger) != STAGES[: STAGES.index(abstained_stage) + 1]:
            blocking.add("P2_ABSTAINED_STAGE_LINEAGE_INVALID")
        if failed_stage not in (None, "") or failure_code not in (None, ""):
            blocking.add("P2_ABSTAINED_ATTEMPT_FAILURE_FIELDS_INVALID")
        if lane_rows:
            blocking.add("P2_INCOMPLETE_ATTEMPT_LANES_MUST_BE_EMPTY")
        if document.get("status") != "NOT_PRODUCED":
            blocking.add("P2_INCOMPLETE_DOCUMENT_RECORD_INVALID")
    else:
        blocking.add("P2_ATTEMPT_STATUS_INVALID")
    result["status"] = "BLOCKED" if blocking else "FAIL" if failures else str(status)
    return result, blocking, failures


def validate_e2e_operational_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    try:
        manifest = _load_manifest(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        manifest = {}
        blocking = {"P2_OPERATIONAL_MANIFEST_UNREADABLE"}
    else:
        blocking: set[str] = set()
    failures: set[str] = set()
    not_measured: set[str] = set()
    if manifest.get("schema_version") != MANIFEST_VERSION or not str(manifest.get("evaluation_id") or ""):
        blocking.add("P2_OPERATIONAL_MANIFEST_SCHEMA_INVALID")
    try:
        lanes = runtime_lanes()
    except (OSError, ValueError, json.JSONDecodeError):
        lanes = ()
        blocking.add("P2_RUNTIME_LANE_CONTRACT_UNREADABLE")
    if tuple(manifest.get("required_lanes") or ()) != lanes:
        blocking.add("P2_ALL_RUNTIME_LANES_REQUIRED")
    slo = manifest.get("slo")
    if not isinstance(slo, Mapping) or set(slo) != set(SLO_FIELDS):
        blocking.add("P2_SLO_SCHEMA_INVALID")
        slo = {}
    elif any(value is None for value in slo.values()):
        not_measured.add("P2_SLOS_NOT_PREREGISTERED")
    elif any(not _number(value) or float(value) < 0 for value in slo.values()):
        blocking.add("P2_SLO_VALUES_INVALID")
    attempts = manifest.get("attempts")
    if not isinstance(attempts, list):
        blocking.add("P2_ATTEMPTS_INVALID")
        attempts = []
    if not attempts:
        not_measured.add("P2_NO_SOURCE_BOUND_E2E_ATTEMPTS")
    attempt_results: list[dict[str, Any]] = []
    complete = 0
    failed = 0
    abstained = 0
    latencies: list[float] = []
    costs: list[float] = []
    token_counts: list[float] = []
    retry_counts: list[float] = []
    provider_errors = 0.0
    cache_modes: list[str] = []
    failed_stage_counts: dict[str, int] = {}
    abstained_stage_counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    for attempt in attempts:
        result, attempt_blocking, attempt_failures = _attempt_result(attempt, lanes)
        attempt_results.append(result)
        blocking.update(attempt_blocking)
        failures.update(attempt_failures)
        attempt_id = result["attempt_id"]
        if not attempt_id or attempt_id in seen_ids:
            blocking.add("P2_ATTEMPT_IDENTITY_DUPLICATE")
        seen_ids.add(attempt_id)
        if isinstance(attempt, Mapping):
            if attempt.get("status") == "COMPLETE":
                complete += 1
            elif attempt.get("status") == "FAILED":
                failed += 1
                failed_stage = attempt.get("failed_stage")
                if isinstance(failed_stage, str) and failed_stage:
                    failed_stage_counts[failed_stage] = (
                        failed_stage_counts.get(failed_stage, 0) + 1
                    )
            elif attempt.get("status") == "ABSTAINED":
                abstained += 1
                abstained_stage = attempt.get("abstained_stage")
                if isinstance(abstained_stage, str) and abstained_stage:
                    abstained_stage_counts[abstained_stage] = (
                        abstained_stage_counts.get(abstained_stage, 0) + 1
                    )
            operation = attempt.get("operational")
            runtime = attempt.get("runtime")
            if isinstance(operation, Mapping) and all(
                _number(operation.get(field))
                for field in (
                    "latency_ms",
                    "token_count",
                    "provider_cost",
                    "retry_count",
                    "provider_error_count",
                )
            ):
                latencies.append(float(operation["latency_ms"]))
                token_counts.append(float(operation["token_count"]))
                costs.append(float(operation["provider_cost"]))
                retry_counts.append(float(operation["retry_count"]))
                provider_errors += float(operation["provider_error_count"])
            if isinstance(runtime, Mapping) and runtime.get("cache_mode") in {"COLD", "WARM"}:
                cache_modes.append(str(runtime["cache_mode"]))
    total = len(attempts)
    if total != complete + failed + abstained:
        blocking.add("P2_ATTEMPT_DENOMINATOR_CONSERVATION_FAILED")
    completion_rate = complete / total if total else None
    metrics: dict[str, Any] = {
        "eligible_attempt_count": total,
        "attempt_count": total,
        "complete_attempt_count": complete,
        "failed_attempt_count": failed,
        "abstained_attempt_count": abstained,
        "completion_rate": completion_rate,
        "latency_p50_ms": median(latencies) if latencies else None,
        "latency_p95_ms": _percentile_95(latencies) if latencies else None,
        "token_count_total": sum(token_counts) if token_counts else None,
        "token_count_per_attempt": sum(token_counts) / total
        if token_counts and total
        else None,
        "cost_per_completed_resume": sum(costs) / complete if complete else None,
        "retry_count_total": sum(retry_counts) if retry_counts else None,
        "retry_count_per_attempt": sum(retry_counts) / total
        if retry_counts and total
        else None,
        "provider_error_rate": provider_errors / total if total else None,
        "cold_attempt_count": cache_modes.count("COLD"),
        "warm_attempt_count": cache_modes.count("WARM"),
        "failed_stage_distribution": dict(sorted(failed_stage_counts.items())),
        "abstained_stage_distribution": dict(sorted(abstained_stage_counts.items())),
    }
    if total and (metrics["cold_attempt_count"] < 3 or metrics["warm_attempt_count"] < 3):
        not_measured.add("P2_COLD_WARM_COVERAGE_INSUFFICIENT")
    if total and not blocking and not any(value is None for value in slo.values()):
        if completion_rate is None or completion_rate < float(slo["completion_rate_min"]):
            failures.add("P2_COMPLETION_RATE_SLO_FAILED")
        if metrics["latency_p95_ms"] is None or metrics["latency_p95_ms"] > float(slo["latency_p95_ms_max"]):
            failures.add("P2_LATENCY_P95_SLO_FAILED")
        if metrics["cost_per_completed_resume"] is None or metrics["cost_per_completed_resume"] > float(slo["cost_per_completed_resume_max"]):
            failures.add("P2_COST_PER_COMPLETED_RESUME_SLO_FAILED")
        if metrics["provider_error_rate"] is None or metrics["provider_error_rate"] > float(slo["provider_error_rate_max"]):
            failures.add("P2_PROVIDER_ERROR_RATE_SLO_FAILED")
    status = "BLOCKED" if blocking else "FAIL" if failures else "NOT_MEASURED" if not_measured else "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "evaluation_id": str(manifest.get("evaluation_id") or path.stem),
        "status": status,
        "required_lanes": list(lanes),
        "attempt_results": attempt_results,
        "operational_metrics": metrics,
        "authority": {"technical_validation": True, "human_qualified": False, "release_authorizing": False, "production_authorizing": False},
        "blocking_reasons": sorted(blocking),
        "failure_reasons": sorted(failures),
        "not_measured_reasons": sorted(not_measured),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W6 source-bound operational evidence")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    summary = validate_e2e_operational_manifest(args.manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 2
