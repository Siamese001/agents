"""Independent post-evaluation assurance for Apps RG.

This intentionally does not import the Apps Eval adapter, normalizer, or
verdict calculator.  It reopens the frozen Apps RG input manifest and compares
the emitted scorecard rows with those exact bytes and identities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.evaluation_manifest import (
    CANDIDATE_EVALUATION_MANIFEST,
    validate_candidate_evaluation_manifest,
)


L6_EVALUATION_AUDIT = "l6_evaluation_audit.v2.json"
L6_EVALUATION_AUDIT_SCHEMA = "apps_rg.l6_evaluation_audit.v2"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normal_digest(value: Any) -> str:
    return str(value or "").strip().removeprefix("sha256:")


def _contained(root: Path, ref: str) -> Path | None:
    raw = str(ref or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve()
            candidate.relative_to(root.resolve())
        except (OSError, ValueError):
            return None
        return candidate
    if ".." in candidate.parts:
        return None
    resolved = (root.resolve() / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _verify_eval_package_seal(eval_root: Path | None, record_id: str) -> list[str]:
    """Independently verify the package bytes that Apps Eval claims to seal."""

    if eval_root is None:
        return ["eval_package_root_missing"]
    seal_path = eval_root / "apps_rg_eval_package_seal.json"
    seal = _read_json(seal_path)
    if not seal:
        return ["eval_package_seal_unreadable"]
    if str(seal.get("record_id") or "") != record_id:
        return ["eval_package_seal_record_id_mismatch"]
    artifacts = seal.get("artifacts")
    if not isinstance(artifacts, list):
        return ["eval_package_seal_artifacts_missing"]
    required_roles = {
        "eval_record",
        "scorecard_rows",
        "component_scorecards",
        "coverage_matrix",
        "regression_summary",
    }
    observed_roles: set[str] = set()
    errors: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            errors.append("eval_package_seal_artifact_invalid")
            continue
        role = str(artifact.get("artifact_role") or artifact.get("role") or "")
        if role:
            observed_roles.add(role)
        path = _contained(eval_root, str(artifact.get("artifact_ref") or ""))
        if path is None or not path.is_file():
            errors.append(f"eval_package_seal_artifact_missing:{role}")
            continue
        if _normal_digest(artifact.get("sha256")) != _sha256_file(path):
            errors.append(f"eval_package_seal_digest_mismatch:{role}")
        try:
            length = int(artifact.get("byte_length"))
        except (TypeError, ValueError):
            length = -1
        if length != path.stat().st_size:
            errors.append(f"eval_package_seal_length_mismatch:{role}")
    for role in sorted(required_roles - observed_roles):
        errors.append(f"eval_package_seal_required_role_missing:{role}")
    return sorted(set(errors))


def _rows(eval_record: Any) -> list[dict[str, Any]]:
    scorecard = getattr(eval_record, "scorecard", None)
    raw = getattr(scorecard, "scorecard_rows", []) if scorecard is not None else []
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _eval_root(eval_record: Any) -> Path | None:
    paths = getattr(eval_record, "artifact_paths", {})
    raw = str(paths.get("eval_record") or "") if isinstance(paths, Mapping) else ""
    path = Path(raw) if raw else None
    return path.parent.resolve() if path is not None and path.is_file() else None


def _row_is_eval_owned(row: Mapping[str, Any], eval_root: Path | None) -> bool:
    if eval_root is None:
        return False
    for value in (row.get("artifact_ref"), row.get("evidence_ref")):
        raw = str(value or "").strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            continue
        try:
            path.resolve().relative_to(eval_root)
        except (OSError, ValueError):
            continue
        return True
    return False


def run_l6_evaluation_audit(
    *,
    artifact_dir: Path | str,
    eval_record: Any,
) -> dict[str, Any]:
    """Recompute source bindings for the emitted required scorecard rows."""

    root = Path(artifact_dir).resolve()
    manifest, manifest_errors = validate_candidate_evaluation_manifest(root)
    bindings = manifest.get("artifact_bindings")
    bindings = bindings if isinstance(bindings, list) else []
    binding_by_key: dict[tuple[str, str], Mapping[str, Any]] = {
        (str(row.get("lane_id") or ""), str(row.get("role") or "")): row
        for row in bindings
        if isinstance(row, Mapping) and row.get("missing") is not True
    }
    eval_root = _eval_root(eval_record)
    rows = [row for row in _rows(eval_record) if row.get("required", True)]
    row_errors: list[dict[str, Any]] = []
    bound_count = 0
    for row in rows:
        lane_id = str(row.get("lane_id") or "")
        role = str(row.get("artifact_role") or "")
        # This admission row is derived from the frozen source snapshot rather
        # than one source file.  Its opaque snapshot digest is intentionally
        # not a file hash.  Rebind its product identity to the independently
        # validated candidate manifest instead of pretending it names the
        # runtime-identity envelope.
        if not lane_id and role == "source_identity":
            product_identity = manifest.get("product_identity")
            product_identity = (
                product_identity if isinstance(product_identity, Mapping) else {}
            )
            errors = [
                f"l6_identity_mismatch:{key}"
                for key in ("parent_run_id", "child_run_id")
                if str(row.get(key) or "")
                != str(product_identity.get(key) or "")
            ]
            if errors:
                row_errors.append(
                    {
                        "row_id": str(row.get("row_id") or ""),
                        "reason": errors,
                        "lane_id": lane_id,
                        "artifact_role": role,
                    }
                )
            else:
                bound_count += 1
            continue
        binding = binding_by_key.get((lane_id, role))
        if binding is None:
            if _row_is_eval_owned(row, eval_root):
                bound_count += 1
                continue
            row_errors.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "reason": "l6_manifest_binding_missing",
                    "lane_id": lane_id,
                    "artifact_role": role,
                }
            )
            continue
        expected_ref = str(binding.get("artifact_ref") or "")
        expected_digest = str(binding.get("sha256") or "")
        expected_identity = binding.get("identity")
        expected_identity = (
            dict(expected_identity) if isinstance(expected_identity, Mapping) else {}
        )
        errors: list[str] = []
        row_ref = str(row.get("evidence_ref") or "")
        row_digest = str(row.get("evidence_digest") or "")
        if row_ref != expected_ref:
            errors.append("l6_evidence_ref_mismatch")
        if _normal_digest(row_digest) != _normal_digest(expected_digest):
            errors.append("l6_evidence_digest_mismatch")
        for key in (
            "parent_run_id",
            "child_run_id",
            "section_attempt_id",
            "runtime_exhaust_bundle_id",
        ):
            if lane_id or key in {"parent_run_id", "child_run_id"}:
                if str(row.get(key) or "") != str(expected_identity.get(key) or ""):
                    errors.append(f"l6_identity_mismatch:{key}")
        source_path = _contained(root, expected_ref)
        if source_path is None or not source_path.is_file():
            errors.append("l6_source_missing")
        elif _sha256_file(source_path) != expected_digest:
            errors.append("l6_source_digest_mismatch")
        if errors:
            row_errors.append(
                {
                    "row_id": str(row.get("row_id") or ""),
                    "reason": sorted(set(errors)),
                    "lane_id": lane_id,
                    "artifact_role": role,
                }
            )
        else:
            bound_count += 1
    eval_seal = eval_root / "apps_rg_eval_package_seal.json" if eval_root else None
    eval_package_seal_errors = _verify_eval_package_seal(
        eval_root, str(getattr(eval_record, "record_id", "") or "")
    )
    checks = {
        "candidate_manifest_valid": not manifest_errors,
        "candidate_manifest_present": (root / CANDIDATE_EVALUATION_MANIFEST).is_file(),
        "eval_record_present": eval_root is not None,
        "eval_package_seal_present": eval_seal is not None and eval_seal.is_file(),
        "eval_package_seal_valid": not eval_package_seal_errors,
        "required_rows_present": bool(rows),
        "all_required_rows_bound": bool(rows) and not row_errors,
    }
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    payload: dict[str, Any] = {
        "schema_version": L6_EVALUATION_AUDIT_SCHEMA,
        "eval_record_id": str(getattr(eval_record, "record_id", "") or ""),
        "candidate_evaluation_manifest_ref": CANDIDATE_EVALUATION_MANIFEST,
        "candidate_evaluation_manifest_sha256": str(
            manifest.get("manifest_sha256") or ""
        ),
        "apps_eval_scorecard_ref": str(
            getattr(eval_record, "artifact_paths", {}).get("scorecard_rows") or ""
        ),
        "required_row_count": len(rows),
        "bound_row_count": bound_count,
        "row_errors": row_errors,
        "manifest_errors": manifest_errors,
        "eval_package_seal_errors": eval_package_seal_errors,
        "checks": checks,
        "l6_integrity_status": "PASS" if not failed_checks else "FAIL",
        "grain_parity_status": "PASS" if not failed_checks else "FAIL",
        "apps_eval_rows_bound": bool(rows) and not row_errors,
        "independent_observations": True,
        "evidence_class": "APPS_EVAL_BOUND_PROOF" if not failed_checks else "EVALUATION_INVALID",
    }
    output = root / L6_EVALUATION_AUDIT
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    payload["artifact_ref"] = output.name
    payload["artifact_sha256"] = _sha256_file(output)
    return payload


def derive_evaluation_decision(
    *,
    eval_record: Any,
    l6_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify substantive product findings separately from invalid evaluation."""

    all_rows = _rows(eval_record)
    rows = [row for row in all_rows if row.get("required", True)]
    advisory_rows = [row for row in all_rows if not row.get("required", True)]
    invalid_prefixes = ("evidence.", "coverage.", "admission.", "dependency.")
    invalid_rows = [
        row
        for row in rows
        if str(row.get("failure_mode") or "").startswith(invalid_prefixes)
    ]
    product_rows = [
        row
        for row in rows
        if str(row.get("verdict") or "") not in {"PASS", "NOT_APPLICABLE"}
        and row not in invalid_rows
    ]
    coverage = dict(getattr(getattr(eval_record, "scorecard", None), "coverage_summary", {}) or {})
    execution_complete = getattr(eval_record, "eval_execution_complete", False) is True
    l6_integrity_pass = l6_audit.get("l6_integrity_status") == "PASS"
    coverage_complete = coverage.get("coverage_complete") is True
    package_seal_pass = l6_audit.get("checks", {}).get("eval_package_seal_present") is True

    evaluation_validity = (
        "PASS"
        if execution_complete
        and coverage_complete
        and not invalid_rows
        and l6_integrity_pass
        else "INVALID"
    )
    deterministic_product_status = "PASS" if not product_rows else "FAIL"

    # Governed precedence (Wave 5): EVALUATION_ERROR (4) > EVALUATION_INVALID (3) > PRODUCT_FAIL (2) > PASS (0)
    if not execution_complete:
        evaluation_status = "EVALUATION_ERROR"
        decisive_reason = "evaluator_execution_incomplete_or_failed"
    elif evaluation_validity != "PASS":
        evaluation_status = "EVALUATION_INVALID"
        if invalid_rows:
            decisive_reason = f"invalid_rows_detected:{invalid_rows[0].get('failure_mode', 'unknown')}"
        elif not l6_integrity_pass:
            decisive_reason = "l6_integrity_audit_failed"
        elif not coverage_complete:
            decisive_reason = "evaluation_coverage_incomplete"
        else:
            decisive_reason = "evaluation_validity_gate_failed"
    elif deterministic_product_status != "PASS":
        evaluation_status = "PRODUCT_FAIL"
        decisive_reason = f"deterministic_product_gate_failure:{product_rows[0].get('failure_mode', 'unknown')}"
    else:
        evaluation_status = "PASS"
        decisive_reason = "all_required_evaluation_gates_passed"

    pipeline_complete = (evaluation_status == "PASS")

    return {
        "execution_status": "PASS" if execution_complete else "ERROR",
        "package_integrity_status": "PASS" if package_seal_pass else "INVALID",
        "evaluation_validity": evaluation_validity,
        "deterministic_product_status": deterministic_product_status,
        "semantic_factuality_status": "PENDING_CALIBRATION",
        "quality_advisory_status": "PENDING_CALIBRATION",
        "l6_integrity_status": str(l6_audit.get("l6_integrity_status") or "INVALID"),
        "invalid_row_count": len(invalid_rows),
        "product_failure_row_count": len(product_rows),
        "advisory_row_count": len(advisory_rows),
        "evaluation_status": evaluation_status,
        "decisive_reason": decisive_reason,
        "pipeline_complete": pipeline_complete,
    }


__all__ = [
    "L6_EVALUATION_AUDIT",
    "L6_EVALUATION_AUDIT_SCHEMA",
    "derive_evaluation_decision",
    "run_l6_evaluation_audit",
]
