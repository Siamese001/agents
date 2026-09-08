"""Executable producer/verifier compatibility-gap registry for complete E2E runs."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


CONTRACT_RELPATH = Path("config/contracts/e2e_compatibility_gap_registry.v1.json")
RECEIPT_FILENAME = "e2e_compatibility_gap_registry.json"
RECEIPT_SCHEMA_VERSION = "apps_rg.e2e_compatibility_gap_registry.v1"
_CONTRACT_SCHEMA_VERSION = "apps_rg.e2e_compatibility_gap_registry_contract.v1"


class CompatibilityGapRegistryError(RuntimeError):
    """The executable registry or its receipt violated its fail-closed contract."""


@dataclass(frozen=True, slots=True)
class CompatibilityProbeResult:
    probe_id: str
    passed: bool
    errors: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


Probe = Callable[[Path], CompatibilityProbeResult]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompatibilityGapRegistryError(
            f"JSON_UNREADABLE:{path.name}:{type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise CompatibilityGapRegistryError(f"JSON_NOT_OBJECT:{path.name}")
    return value


def _contract(repo_root: Path) -> tuple[list[dict[str, str]], str]:
    path = Path(repo_root).resolve() / CONTRACT_RELPATH
    value = _load_json(path)
    if value.get("schema_version") != _CONTRACT_SCHEMA_VERSION:
        raise CompatibilityGapRegistryError("CONTRACT_SCHEMA_INVALID")
    policy = value.get("policy")
    required_policy = {
        "every_failed_probe_requires_open_gap": True,
        "every_open_gap_requires_failed_probe": True,
        "empty_open_gaps_requires_all_probes_pass": True,
        "diagnostic_receipt_authorizes_product": False,
    }
    if policy != required_policy:
        raise CompatibilityGapRegistryError("CONTRACT_POLICY_INVALID")
    probes = value.get("probes")
    if not isinstance(probes, list) or not probes:
        raise CompatibilityGapRegistryError("CONTRACT_PROBES_MISSING")
    normalized: list[dict[str, str]] = []
    for row in probes:
        if not isinstance(row, Mapping):
            raise CompatibilityGapRegistryError("CONTRACT_PROBE_INVALID")
        normalized.append(
            {
                "probe_id": str(row.get("probe_id") or ""),
                "producer": str(row.get("producer") or ""),
                "verifier": str(row.get("verifier") or ""),
            }
        )
    ids = [row["probe_id"] for row in normalized]
    if any(not all(row.values()) for row in normalized) or len(ids) != len(set(ids)):
        raise CompatibilityGapRegistryError("CONTRACT_PROBE_IDENTITY_INVALID")
    return normalized, _digest(value)


def _app_runtime_independence_probe(root: Path) -> CompatibilityProbeResult:
    from apps_rg.runtime.standalone_dependency_posture import (
        APP_RUNTIME_INDEPENDENT,
        APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME,
        validate_app_runtime_independence_receipt,
    )

    path = root / APP_RUNTIME_INDEPENDENCE_RECEIPT_FILENAME
    try:
        receipt = _load_json(path)
        validate_app_runtime_independence_receipt(receipt)
        errors = () if receipt.get("status") == APP_RUNTIME_INDEPENDENT else (
            f"runtime_status:{receipt.get('status') or 'MISSING'}",
        )
    except Exception as exc:  # fail-closed diagnostic boundary
        errors = (f"{type(exc).__name__}:{exc}",)
    return CompatibilityProbeResult(
        "APP_RUNTIME_INDEPENDENCE", not errors, errors, (path.name,)
    )


def _research_handoff_probe(root: Path) -> CompatibilityProbeResult:
    preferred = (
        root
        / "e2e_authority_sources"
        / "apps_research"
        / "apps_research_handoff_validation_receipt.json"
    )
    candidates = [preferred] if preferred.is_file() else sorted(
        root.rglob("apps_research_handoff_validation_receipt.json")
    )
    errors: list[str] = []
    if not candidates:
        errors.append("handoff_validation_receipt_missing")
    else:
        try:
            receipt = _load_json(candidates[0])
            if receipt.get("status") != "PASS" or receipt.get("failure_reasons") not in ([], None):
                errors.append("handoff_validation_not_pass")
            identity = receipt.get("identity")
            if not isinstance(identity, Mapping) or receipt.get("identity_sha256") != _digest(identity):
                errors.append("handoff_identity_digest_mismatch")
            validations = receipt.get("artifact_validations")
            if not isinstance(validations, Sequence) or isinstance(validations, (str, bytes)):
                errors.append("handoff_artifact_validations_missing")
            elif any(
                not isinstance(row, Mapping)
                or row.get("status") != "PASS"
                or row.get("actual_sha256") != row.get("expected_sha256")
                for row in validations
            ):
                errors.append("handoff_artifact_validation_failed")
        except CompatibilityGapRegistryError as exc:
            errors.append(str(exc))
    refs = tuple(path.relative_to(root).as_posix() for path in candidates[:1])
    return CompatibilityProbeResult(
        "APPS_RESEARCH_HANDOFF_CONSUMER_RECEIPT", not errors, tuple(errors), refs
    )


def _core_authority_probe(root: Path) -> CompatibilityProbeResult:
    from apps_rg.runtime.orchestration.core_runtime_authority import (
        CORE_RUNTIME_AUTHORITY_ARTIFACT,
        verify_core_runtime_authority,
    )

    paths = sorted(root.rglob(CORE_RUNTIME_AUTHORITY_ARTIFACT))
    errors: list[str] = []
    if not paths:
        errors.append("core_runtime_authority_missing")
    for path in paths:
        report = verify_core_runtime_authority(path.parent)
        errors.extend(
            f"{path.relative_to(root).as_posix()}:{error}" for error in report.errors
        )
    return CompatibilityProbeResult(
        "CORE_RUNTIME_AUTHORITY",
        not errors,
        tuple(errors),
        tuple(path.relative_to(root).as_posix() for path in paths),
    )


def _stage_ledger_probe(root: Path) -> CompatibilityProbeResult:
    from apps_rg.runtime.e2e_stage_ledger import (
        E2E_STAGE_LEDGER_FILENAME,
        verify_e2e_stage_ledger,
    )

    path = root / E2E_STAGE_LEDGER_FILENAME
    report = verify_e2e_stage_ledger(path)
    errors = tuple(report.errors)
    if not report.valid:
        errors = errors or ("stage_ledger_invalid",)
    if not report.sealed:
        errors += ("stage_ledger_not_sealed",)
    return CompatibilityProbeResult(
        "RECEIPT_DERIVED_STAGE_LEDGER", not errors, errors, (path.name,)
    )


def _mandatory_output_probe(root: Path) -> CompatibilityProbeResult:
    from apps_rg.runtime.mandatory_run_outputs import (
        MANDATORY_RUN_OUTPUT_JSON,
        validate_mandatory_output_bundle,
    )

    path = root / MANDATORY_RUN_OUTPUT_JSON
    try:
        document = _load_json(path)
        report = validate_mandatory_output_bundle(root, document)
        errors = tuple(str(error) for error in report.get("errors") or [])
        if report.get("pass") is not True and not errors:
            errors = ("mandatory_output_bundle_invalid",)
    except CompatibilityGapRegistryError as exc:
        errors = (str(exc),)
    return CompatibilityProbeResult(
        "MANDATORY_OUTPUT_BUNDLE", not errors, errors, (path.name,)
    )


def _terminal_manifest_probe(root: Path) -> CompatibilityProbeResult:
    from apps_rg.runtime.terminal_manifest import (
        TERMINAL_MANIFEST_FILENAME,
        verify_terminal_manifest,
    )

    path = root / TERMINAL_MANIFEST_FILENAME
    report = verify_terminal_manifest(path)
    errors = tuple(report.errors)
    if not report.valid and not errors:
        errors = ("terminal_manifest_invalid",)
    return CompatibilityProbeResult(
        "TERMINAL_MANIFEST_AND_CLOSEOUT", not errors, errors, (path.name,)
    )


def default_probes() -> dict[str, Probe]:
    return {
        "APP_RUNTIME_INDEPENDENCE": _app_runtime_independence_probe,
        "APPS_RESEARCH_HANDOFF_CONSUMER_RECEIPT": _research_handoff_probe,
        "CORE_RUNTIME_AUTHORITY": _core_authority_probe,
        "RECEIPT_DERIVED_STAGE_LEDGER": _stage_ledger_probe,
        "MANDATORY_OUTPUT_BUNDLE": _mandatory_output_probe,
        "TERMINAL_MANIFEST_AND_CLOSEOUT": _terminal_manifest_probe,
    }


def validate_compatibility_gap_registry(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise CompatibilityGapRegistryError("RECEIPT_SCHEMA_INVALID")
    body = dict(receipt)
    observed_digest = body.pop("registry_digest", None)
    if observed_digest != _digest(body):
        raise CompatibilityGapRegistryError("RECEIPT_DIGEST_MISMATCH")
    probes = receipt.get("probe_results")
    gaps = receipt.get("open_gaps")
    if not isinstance(probes, list) or not isinstance(gaps, list):
        raise CompatibilityGapRegistryError("RECEIPT_RESULTS_INVALID")
    failed_ids = {
        str(row.get("probe_id") or "")
        for row in probes
        if isinstance(row, Mapping) and row.get("status") != "PASS"
    }
    gap_ids = {
        str(row.get("probe_id") or "") for row in gaps if isinstance(row, Mapping)
    }
    if failed_ids != gap_ids:
        raise CompatibilityGapRegistryError("FAILED_PROBE_GAP_SET_MISMATCH")
    if receipt.get("status") != ("PASS" if not failed_ids else "BLOCKED_COMPATIBILITY_GAPS"):
        raise CompatibilityGapRegistryError("RECEIPT_STATUS_CONTRADICTS_GAPS")
    if receipt.get("product_authorized") is not False:
        raise CompatibilityGapRegistryError("DIAGNOSTIC_REGISTRY_CANNOT_AUTHORIZE_PRODUCT")


def evaluate_compatibility_gap_registry(
    *,
    artifact_dir: Path,
    repo_root: Path,
    probes: Mapping[str, Probe] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    root = Path(artifact_dir).resolve()
    specs, contract_digest = _contract(Path(repo_root))
    executable = dict(probes or default_probes())
    expected_ids = [row["probe_id"] for row in specs]
    if set(executable) != set(expected_ids):
        raise CompatibilityGapRegistryError("EXECUTABLE_PROBE_SET_MISMATCH")
    results: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for spec in specs:
        probe_id = spec["probe_id"]
        try:
            result = executable[probe_id](root)
            if result.probe_id != probe_id:
                raise CompatibilityGapRegistryError("PROBE_ID_MISMATCH")
        except Exception as exc:  # a crashing verifier is itself an open compatibility gap
            result = CompatibilityProbeResult(
                probe_id,
                False,
                (f"verifier_exception:{type(exc).__name__}:{exc}",),
            )
        errors = list(result.errors)
        if not result.passed and not errors:
            errors = ["verifier_failed_without_detail"]
        status = "PASS" if result.passed and not errors else "FAIL"
        row = {
            **spec,
            "status": status,
            "errors": errors,
            "evidence_refs": list(result.evidence_refs),
        }
        results.append(row)
        if status != "PASS":
            gaps.append(
                {
                    "gap_id": f"COMPAT-{probe_id}",
                    "probe_id": probe_id,
                    "producer": spec["producer"],
                    "verifier": spec["verifier"],
                    "errors": errors,
                }
            )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_ref": CONTRACT_RELPATH.as_posix(),
        "contract_digest": contract_digest,
        "artifact_dir": str(root),
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not gaps else "BLOCKED_COMPATIBILITY_GAPS",
        "product_authorized": False,
        "probe_results": results,
        "open_gaps": gaps,
        "summary": {
            "probe_count": len(results),
            "passed_probe_count": sum(row["status"] == "PASS" for row in results),
            "failed_probe_count": len(gaps),
            "open_gap_count": len(gaps),
        },
    }
    receipt["registry_digest"] = _digest(receipt)
    validate_compatibility_gap_registry(receipt)
    return receipt


def write_compatibility_gap_registry(
    *, artifact_dir: Path, receipt: Mapping[str, Any]
) -> Path:
    validate_compatibility_gap_registry(receipt)
    root = Path(artifact_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / RECEIPT_FILENAME
    temporary = root / f".{RECEIPT_FILENAME}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(json.dumps(dict(receipt), indent=2, sort_keys=True).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


__all__ = [
    "CompatibilityGapRegistryError",
    "CompatibilityProbeResult",
    "CONTRACT_RELPATH",
    "RECEIPT_FILENAME",
    "default_probes",
    "evaluate_compatibility_gap_registry",
    "validate_compatibility_gap_registry",
    "write_compatibility_gap_registry",
]
