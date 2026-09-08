"""W1 fail-closed convergence catalog for Apps RG evaluation receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CATALOG_VERSION = "apps_rg.receipt_catalog.v1"
SUMMARY_VERSION = "apps_rg.receipt_catalog_summary.v1"
DEFAULT_CATALOG_PATH = Path(__file__).with_name("receipt_catalog_manifest.v1.json")
REQUIRED_RECEIPT_KINDS = (
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "P1",
    "P2",
    "unsupported_material_claim_count",
    "critical_binding_error_count",
    "critical_run_divergence_count",
)
AUTHORITY_TIERS = (
    "technical_validation",
    "human_qualified",
    "release_authorized",
    "production_authorized",
)
_TIER_RANK = {tier: rank for rank, tier in enumerate(AUTHORITY_TIERS)}


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("catalog and receipt files must contain JSON objects")
    return value


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _catalog_errors(catalog: Any) -> list[str]:
    if not isinstance(catalog, Mapping):
        return ["CATALOG_NOT_OBJECT"]
    errors: list[str] = []
    if catalog.get("schema_version") != CATALOG_VERSION:
        errors.append("CATALOG_SCHEMA_INVALID")
    if not isinstance(catalog.get("catalog_id"), str) or not catalog["catalog_id"]:
        errors.append("CATALOG_ID_INVALID")
    required = catalog.get("required_receipt_kinds")
    if not isinstance(required, list) or tuple(required) != REQUIRED_RECEIPT_KINDS:
        errors.append("CATALOG_REQUIRED_RECEIPT_SET_INVALID")
    if catalog.get("minimum_authority_tier") not in AUTHORITY_TIERS:
        errors.append("CATALOG_MINIMUM_AUTHORITY_INVALID")
    if not isinstance(catalog.get("entries"), list):
        errors.append("CATALOG_ENTRIES_INVALID")
    return errors


def _entry_errors(entry: Any) -> list[str]:
    if not isinstance(entry, Mapping):
        return ["RECEIPT_ENTRY_NOT_OBJECT"]
    required = (
        "entry_id",
        "receipt_kind",
        "path",
        "expected_file_sha256",
        "input_digest",
        "evaluator_version",
        "data_split",
        "runtime_configuration_digest",
        "authority_tier",
    )
    errors = [
        f"RECEIPT_ENTRY_{field.upper()}_MISSING"
        for field in required
        if not str(entry.get(field) or "").strip()
    ]
    kind = entry.get("receipt_kind")
    tier = entry.get("authority_tier")
    if kind not in {*REQUIRED_RECEIPT_KINDS, "apps_eval_regression"}:
        errors.append("RECEIPT_KIND_INVALID")
    if not _valid_sha256(entry.get("expected_file_sha256")):
        errors.append("RECEIPT_FILE_SHA256_INVALID")
    if entry.get("data_split") not in {"calibration", "holdout"}:
        errors.append("RECEIPT_DATA_SPLIT_INVALID")
    if kind == "apps_eval_regression":
        if tier != "regression_diagnostic":
            errors.append("REGRESSION_AUTHORITY_INVALID")
    elif tier not in AUTHORITY_TIERS:
        errors.append("RECEIPT_AUTHORITY_INVALID")
    return errors


def _payload_authority_errors(payload: Mapping[str, Any], tier: str) -> list[str]:
    if tier not in AUTHORITY_TIERS:
        return ["RECEIPT_AUTHORITY_INVALID"]
    authority = payload.get("authority")
    if not isinstance(authority, Mapping):
        return ["RECEIPT_PAYLOAD_AUTHORITY_MISSING"]
    required_field = {
        "technical_validation": "technical_validation",
        "human_qualified": "human_qualified",
        "release_authorized": "release_authorized",
        "production_authorized": "production_authorized",
    }[tier]
    if authority.get(required_field) is not True:
        return ["RECEIPT_PAYLOAD_AUTHORITY_INSUFFICIENT"]
    return []


def _read_entry(entry: Mapping[str, Any], *, catalog_root: Path) -> dict[str, Any]:
    result = {
        "entry_id": str(entry.get("entry_id") or ""),
        "receipt_kind": str(entry.get("receipt_kind") or ""),
        "input_digest": str(entry.get("input_digest") or ""),
        "evaluator_version": str(entry.get("evaluator_version") or ""),
        "data_split": str(entry.get("data_split") or ""),
        "runtime_configuration_digest": str(
            entry.get("runtime_configuration_digest") or ""
        ),
        "authority_tier": str(entry.get("authority_tier") or ""),
        "status": "UNKNOWN",
        "reasons": [],
    }
    errors = _entry_errors(entry)
    if errors:
        result["reasons"] = errors
        return result
    catalog_root = catalog_root.resolve()
    path = (catalog_root / str(entry["path"])).resolve()
    try:
        path.relative_to(catalog_root)
    except ValueError:
        result["reasons"] = ["RECEIPT_PATH_OUTSIDE_CATALOG_FORBIDDEN"]
        return result
    if path.is_symlink():
        result["reasons"] = ["RECEIPT_SYMLINK_FORBIDDEN"]
        return result
    try:
        payload = _load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        result["reasons"] = ["RECEIPT_FILE_UNREADABLE"]
        return result
    if file_sha256(path) != entry["expected_file_sha256"]:
        result["reasons"] = ["RECEIPT_FILE_STALE_OR_TAMPERED"]
        return result
    expected_schema = entry.get("expected_schema_version")
    if expected_schema and payload.get("schema_version") != expected_schema:
        result["reasons"] = ["RECEIPT_SCHEMA_INCOMPATIBLE"]
        return result
    expected_digest = entry.get("expected_record_digest")
    if expected_digest and payload.get("record_digest") != expected_digest:
        result["reasons"] = ["RECEIPT_RECORD_DIGEST_STALE_OR_INCOMPATIBLE"]
        return result
    if entry["receipt_kind"] == "apps_eval_regression":
        if payload.get("schema_version") != "apps_eval.completed_eval.v3":
            result["reasons"] = ["REGRESSION_RECORD_SCHEMA_INVALID"]
            return result
        scorecard = payload.get("scorecard")
        regression = payload.get("regression")
        if not isinstance(scorecard, Mapping) or not isinstance(regression, Mapping):
            result["reasons"] = ["REGRESSION_RECORD_SHAPE_INVALID"]
            return result
        result["status"] = (
            "PASS"
            if scorecard.get("verdict") == "pass"
            and regression.get("verdict") in {"pass", "not_compared"}
            else "FAIL"
        )
        return result
    authority_errors = _payload_authority_errors(
        payload, str(entry.get("authority_tier") or "")
    )
    if authority_errors:
        result["reasons"] = authority_errors
        return result
    status = payload.get("status")
    if status not in {"PASS", "FAIL", "UNKNOWN", "NOT_MEASURED"}:
        result["reasons"] = ["AUTHORITATIVE_RECEIPT_STATUS_INVALID"]
        return result
    result["status"] = status
    return result


def build_qualification_summary(catalog_path: Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    """Summarize the tracked catalog without granting release authority."""
    try:
        catalog = _load_json(catalog_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        catalog = {}
        catalog_errors = ["CATALOG_UNREADABLE"]
    else:
        catalog_errors = _catalog_errors(catalog)
    catalog_id = str(catalog.get("catalog_id") or catalog_path.stem)
    entries = catalog.get("entries") if isinstance(catalog.get("entries"), list) else []
    results = [
        _read_entry(entry, catalog_root=catalog_path.parent)
        for entry in entries
        if isinstance(entry, Mapping)
    ]
    results.extend(
        {
            "entry_id": "",
            "receipt_kind": "",
            "input_digest": "",
            "evaluator_version": "",
            "data_split": "",
            "runtime_configuration_digest": "",
            "authority_tier": "",
            "status": "UNKNOWN",
            "reasons": ["RECEIPT_ENTRY_NOT_OBJECT"],
        }
        for entry in entries
        if not isinstance(entry, Mapping)
    )
    blocking_reasons = set(catalog_errors)
    not_measured_reasons: set[str] = set()
    failure_reasons: set[str] = set()
    entry_ids: set[str] = set()
    identity_keys: set[tuple[str, str, str, str, str, str]] = set()
    authoritative = [result for result in results if result["receipt_kind"] != "apps_eval_regression"]
    diagnostics = [result for result in results if result["receipt_kind"] == "apps_eval_regression"]
    for result in results:
        entry_id = result["entry_id"]
        if not entry_id or entry_id in entry_ids:
            blocking_reasons.add("RECEIPT_ENTRY_ID_DUPLICATE_OR_INVALID")
        entry_ids.add(entry_id)
        if result["receipt_kind"] == "apps_eval_regression":
            continue
        identity = (
            result["receipt_kind"],
            result["input_digest"],
            result["evaluator_version"],
            result["data_split"],
            result["runtime_configuration_digest"],
            result["authority_tier"],
        )
        if identity in identity_keys:
            blocking_reasons.add("AUTHORITATIVE_RECEIPT_DUPLICATE")
        identity_keys.add(identity)
        for reason in result["reasons"]:
            blocking_reasons.add(reason)
    required = list(catalog.get("required_receipt_kinds") or REQUIRED_RECEIPT_KINDS)
    results_by_kind: dict[str, list[dict[str, Any]]] = {}
    for result in authoritative:
        results_by_kind.setdefault(result["receipt_kind"], []).append(result)
    for kind in required:
        matching = results_by_kind.get(kind, [])
        if not matching:
            not_measured_reasons.add(f"AUTHORITATIVE_RECEIPT_MISSING_{kind}")
            continue
        if len(matching) != 1:
            blocking_reasons.add(f"AUTHORITATIVE_RECEIPT_KIND_DUPLICATE_{kind}")
            continue
        result = matching[0]
        if result["status"] == "FAIL":
            failure_reasons.add(f"AUTHORITATIVE_RECEIPT_FAILED_{kind}")
        elif result["status"] in {"UNKNOWN", "NOT_MEASURED"}:
            not_measured_reasons.add(f"AUTHORITATIVE_RECEIPT_NOT_MEASURED_{kind}")
    required_results = [results_by_kind[kind][0] for kind in required if len(results_by_kind.get(kind, [])) == 1]
    if required_results:
        expected_scope = {
            field: required_results[0][field]
            for field in ("input_digest", "data_split", "runtime_configuration_digest")
        }
        for result in required_results[1:]:
            if any(result[field] != expected_scope[field] for field in expected_scope):
                blocking_reasons.add("AUTHORITATIVE_RECEIPT_SCOPE_INCOMPATIBLE")
        if expected_scope["data_split"] != "holdout":
            blocking_reasons.add("AUTHORITATIVE_HOLDOUT_REQUIRED")
    minimum_tier = str(catalog.get("minimum_authority_tier") or "")
    for result in required_results:
        tier = result["authority_tier"]
        if tier not in _TIER_RANK or _TIER_RANK[tier] < _TIER_RANK.get(minimum_tier, 99):
            blocking_reasons.add("AUTHORITATIVE_RECEIPT_AUTHORITY_INSUFFICIENT")
    if blocking_reasons:
        status = "BLOCKED"
    elif failure_reasons:
        status = "FAIL"
    elif not_measured_reasons:
        status = "NOT_MEASURED"
    else:
        status = "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "catalog_id": catalog_id,
        "status": status,
        "authority": {
            "minimum_receipt_tier": minimum_tier,
            "release_authorizing": False,
            "production_authorizing": False,
            "apps_eval_role": "regression_diagnostic_only",
        },
        "authoritative_receipts": authoritative,
        "regression_diagnostics": diagnostics,
        "blocking_reasons": sorted(blocking_reasons),
        "failure_reasons": sorted(failure_reasons),
        "not_measured_reasons": sorted(not_measured_reasons),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Apps RG W1 receipt catalog")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    summary = build_qualification_summary(args.catalog)
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
    print(encoded, end="")
    return 0 if summary["status"] == "PASS" else 2
