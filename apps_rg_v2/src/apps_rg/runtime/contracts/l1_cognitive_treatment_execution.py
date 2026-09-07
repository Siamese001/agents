"""App-local observation receipt for one L1 cognitive experiment attempt.

This contract reads artifacts already emitted by Apps RG.  It never dispatches
work or treats a planned advisory as proof of provider-visible consumption.
The candidate arm passes only when at least one compiled PA artifact records
the matching plan, C0 outcome, bounded revision, revision advisory, matching
provider-request prompt hash, an Apps RG-owned C0-to-L2 diagnostic projection,
and an output disposition proving that the required C0-gap disposition survived
its L2 diagnostic output.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    build_l1_cognitive_consumer_advisory,
    cognitive_revision_gap_requirements,
    extract_l1_cognitive_plan,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    treatment_from_task_spec,
)
from apps_rg.runtime.contracts.l1_cognitive_output_disposition import (
    L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT,
    L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
    validate_l1_cognitive_output_disposition,
    validate_l1_cognitive_output_projection,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_TREATMENT_EXECUTION_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_treatment_execution.v4"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_AUTHORITY: Final[str] = "TECHNICAL_EXECUTION_OBSERVATION_ONLY"


class L1CognitiveTreatmentExecutionError(ValueError):
    """Raised when an execution receipt cannot be validated."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def treatment_execution_digest(receipt: Mapping[str, Any]) -> str:
    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__
    return (dict(raw), "") if isinstance(raw, Mapping) else (None, "not_mapping")


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_ref(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _string_leaves(value: Any) -> tuple[str, ...]:
    """Return textual leaves from a diagnostic field without normalizing meaning."""

    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        rows: list[str] = []
        for item in value.values():
            rows.extend(_string_leaves(item))
        return tuple(rows)
    if isinstance(value, (list, tuple)):
        rows = []
        for item in value:
            rows.extend(_string_leaves(item))
        return tuple(rows)
    return ()


def _revision_output_observation(
    *,
    root: Path,
    local: Path,
    section_id: str,
    revision_advisory: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Observe the output and deterministic gate for C0-directed dispositions."""

    requirements = cognitive_revision_gap_requirements(
        revision_advisory,
        section_id=section_id,
    )
    if not requirements:
        return {
            "applicable": False,
            "observed": True,
            "required_gap_tags": [],
        "required_change_log_tags": [],
        "output_projection_ref": "",
        "output_disposition_ref": "",
        }, []

    output_path = local / "l2_output.json"
    output, output_error = _read_json(output_path)
    required_gap_tags = [row["gap_tag"] for row in requirements]
    required_change_log_tags = [row["change_log_tag"] for row in requirements]
    record: dict[str, Any] = {
        "applicable": True,
        "l2_output_ref": _relative_ref(root, output_path),
        "required_gap_tags": required_gap_tags,
        "required_change_log_tags": required_change_log_tags,
        "observed_gap_tags": [],
        "observed_change_log_tags": [],
        "output_projection_ref": _relative_ref(
            root, local / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
        ),
        "output_projection_status": "",
        "output_projection_advisory_digest_matches": False,
        "output_projection_l2_output_digest_matches": False,
        "output_projection_requirements_match": False,
        "output_disposition_ref": _relative_ref(
            root, local / L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT
        ),
        "output_disposition_status": "",
        "output_disposition_reason_code": "",
        "output_disposition_blocks_finalization": None,
        "observed": False,
    }
    if output is None:
        return record, [f"{record['l2_output_ref']}:unreadable:{output_error}"]

    gap_strings = _string_leaves(output.get("gap_notes"))
    change_strings = _string_leaves(output.get("change_log"))
    observed_gap_tags = [
        tag for tag in required_gap_tags if any(tag in value for value in gap_strings)
    ]
    observed_change_log_tags = [
        tag
        for tag in required_change_log_tags
        if any(tag in value for value in change_strings)
    ]
    record["observed_gap_tags"] = observed_gap_tags
    record["observed_change_log_tags"] = observed_change_log_tags
    errors: list[str] = []
    for tag in sorted(set(required_gap_tags) - set(observed_gap_tags)):
        errors.append(f"{record['l2_output_ref']}:missing_required_gap_tag:{tag}")
    for tag in sorted(set(required_change_log_tags) - set(observed_change_log_tags)):
        errors.append(
            f"{record['l2_output_ref']}:missing_required_change_log_tag:{tag}"
        )
    projection_path = local / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
    projection, projection_error = _read_json(projection_path)
    if projection is None:
        errors.append(
            f"{record['output_projection_ref']}:unreadable:{projection_error}"
        )
    else:
        try:
            validate_l1_cognitive_output_projection(projection)
        except ValueError as exc:
            errors.append(f"{record['output_projection_ref']}:invalid:{exc}")
        else:
            record["output_projection_status"] = str(projection.get("status") or "")
            projection_advisory = projection.get("revision_advisory")
            advisory_matches = isinstance(projection_advisory, Mapping) and str(
                projection_advisory.get("revision_advisory_digest") or ""
            ) == str(revision_advisory.get("advisory_digest") or "")
            record["output_projection_advisory_digest_matches"] = advisory_matches
            output_digest_matches = str(
                (projection.get("l2_output") or {}).get("post_projection_digest")
                or ""
            ) == _file_digest(output_path)
            record["output_projection_l2_output_digest_matches"] = output_digest_matches
            expected_projection_requirements = [
                {
                    "requirement_id": row["requirement_id"],
                    "outcome_code": row["outcome_code"],
                    "gap_tag": row["gap_tag"],
                    "change_log_tag": row["change_log_tag"],
                }
                for row in requirements
            ]
            requirements_match = (
                projection.get("outcome_requirements")
                == expected_projection_requirements
            )
            record["output_projection_requirements_match"] = requirements_match
            if projection.get("status") != "APPLIED":
                errors.append(
                    f"{record['output_projection_ref']}:unexpected_status:"
                    f"{record['output_projection_status']}"
                )
            if not advisory_matches:
                errors.append(
                    f"{record['output_projection_ref']}:revision_advisory_digest_mismatch"
                )
            if not output_digest_matches:
                errors.append(
                    f"{record['output_projection_ref']}:l2_output_digest_mismatch"
                )
            if not requirements_match:
                errors.append(
                    f"{record['output_projection_ref']}:requirements_mismatch"
                )
    disposition_path = local / L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT
    disposition, disposition_error = _read_json(disposition_path)
    if disposition is None:
        errors.append(
            f"{record['output_disposition_ref']}:unreadable:{disposition_error}"
        )
    else:
        try:
            validate_l1_cognitive_output_disposition(disposition)
        except ValueError as exc:
            errors.append(f"{record['output_disposition_ref']}:invalid:{exc}")
        else:
            record["output_disposition_status"] = str(disposition.get("status") or "")
            record["output_disposition_reason_code"] = str(
                disposition.get("reason_code") or ""
            )
            record["output_disposition_blocks_finalization"] = bool(
                disposition.get("blocks_finalization")
            )
            disposition_advisory = disposition.get("revision_advisory")
            if not isinstance(disposition_advisory, Mapping) or str(
                disposition_advisory.get("revision_advisory_digest") or ""
            ) != str(revision_advisory.get("advisory_digest") or ""):
                errors.append(
                    f"{record['output_disposition_ref']}:revision_advisory_digest_mismatch"
                )
            output_digest = str((disposition.get("l2_output") or {}).get("digest") or "")
            if output_digest != _file_digest(output_path):
                errors.append(
                    f"{record['output_disposition_ref']}:l2_output_digest_mismatch"
                )
            if disposition.get("blocks_finalization") is True:
                errors.append(
                    f"{record['output_disposition_ref']}:blocks_finalization:"
                    f"{record['output_disposition_reason_code']}"
                )
            elif disposition.get("status") != "PASS":
                errors.append(
                    f"{record['output_disposition_ref']}:unexpected_status:"
                    f"{record['output_disposition_status']}"
                )
    record["observed"] = not errors
    return record, errors


def _candidate_record(
    *, root: Path, artifact_path: Path, plan_digest: str, advisory_digest: str
) -> tuple[dict[str, Any], list[str]]:
    artifact, artifact_error = _read_json(artifact_path)
    ref = _relative_ref(root, artifact_path)
    errors: list[str] = []
    if artifact is None:
        return {
            "compiled_prompt_artifact_ref": ref,
            "compiled_prompt_artifact_digest": _file_digest(artifact_path),
            "section_id": "",
            "observed": False,
        }, [f"{ref}:unreadable:{artifact_error}"]
    section_id = str(artifact.get("section_id") or "").strip()
    required = {
        "l1_cognitive_plan_digest": plan_digest,
        "l1_cognitive_advisory_digest": advisory_digest,
        "l1_cognitive_revision_ref": sr.FILENAME_L1_COGNITIVE_REVISION,
        "l1_cognitive_revision_advisory_ref": sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY,
        "l1_cognitive_revision_outcome_ref": sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT,
    }
    for field, expected in required.items():
        if str(artifact.get(field) or "") != expected:
            errors.append(f"{ref}:{field}_mismatch")
    local = artifact_path.parent
    linked: dict[str, tuple[str, str]] = {
        "c0_outcome": (
            sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT,
            "l1_cognitive_c0_outcome_receipt_digest",
        ),
        "revision": (sr.FILENAME_L1_COGNITIVE_REVISION, "l1_cognitive_revision_digest"),
        "revision_advisory": (
            sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY,
            "l1_cognitive_revision_advisory_digest",
        ),
    }
    linked_digests: dict[str, str] = {}
    linked_payloads: dict[str, dict[str, Any]] = {}
    for label, (filename, field) in linked.items():
        local_path = local / filename
        payload, local_error = _read_json(local_path)
        if payload is None:
            errors.append(f"{ref}:{label}_unreadable:{local_error}")
            continue
        digest_key = "receipt_digest" if label == "c0_outcome" else "revision_digest" if label == "revision" else "advisory_digest"
        digest = str(payload.get(digest_key) or "")
        linked_payloads[label] = payload
        linked_digests[label] = digest
        if not digest or str(artifact.get(field) or "") != digest:
            errors.append(f"{ref}:{label}_digest_mismatch")
    provider_request_path = local / "provider_request.json"
    provider_request, provider_request_error = _read_json(provider_request_path)
    expected_prompt_hash = str(artifact.get("dispatch_sha256_prompt16") or "").strip()
    provider_request_observation: dict[str, Any] = {
        "provider_request_ref": _relative_ref(root, provider_request_path),
        "compiled_prompt_hash": expected_prompt_hash,
        "provider_prompt_hash": "",
        "observed": False,
    }
    if provider_request is None:
        errors.append(
            f"{provider_request_observation['provider_request_ref']}:unreadable:{provider_request_error}"
        )
    else:
        provider_prompt_hash = str(provider_request.get("prompt_hash") or "").strip()
        provider_request_observation["provider_prompt_hash"] = provider_prompt_hash
        if not expected_prompt_hash:
            errors.append(f"{ref}:dispatch_sha256_prompt16_missing")
        elif provider_prompt_hash != expected_prompt_hash:
            errors.append(
                f"{provider_request_observation['provider_request_ref']}:prompt_hash_mismatch"
            )
        else:
            provider_request_observation["observed"] = True

    revision_observation: dict[str, Any] = {
        "applicable": False,
        "observed": False,
        "required_gap_tags": [],
        "required_change_log_tags": [],
    }
    revision_advisory = linked_payloads.get("revision_advisory")
    if revision_advisory is not None:
        observation, observation_errors = _revision_output_observation(
            root=root,
            local=local,
            section_id=section_id,
            revision_advisory=revision_advisory,
        )
        revision_observation = observation
        errors.extend(observation_errors)
    else:
        errors.append(f"{ref}:revision_advisory_unavailable_for_output_observation")

    return {
        "compiled_prompt_artifact_ref": ref,
        "compiled_prompt_artifact_digest": _file_digest(artifact_path),
        "section_id": section_id,
        "observed": not errors,
        "linked_digests": linked_digests,
        "provider_request_observation": provider_request_observation,
        "revision_output_observation": revision_observation,
    }, errors


def build_l1_cognitive_treatment_execution_receipt(
    *, run_root: Path, l1_plan: Any
) -> dict[str, Any]:
    """Observe one complete Apps RG attempt without invoking any pipeline stage."""

    root = Path(run_root).resolve()
    task_spec = getattr(l1_plan, "task_spec", None)
    if not isinstance(task_spec, Mapping):
        raise L1CognitiveTreatmentExecutionError("l1 plan task_spec is unavailable")
    treatment = treatment_from_task_spec(task_spec)
    arm = str(treatment["arm"])
    prompt_paths = sorted(root.rglob("compiled_prompt_artifact.json")) if root.is_dir() else []
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    plan = extract_l1_cognitive_plan(l1_plan, required=False)

    if arm == L1_COGNITIVE_V2_CONTROL_ARM:
        if plan is not None:
            errors.append("control_arm_contains_v3_plan")
        for path in prompt_paths:
            artifact, artifact_error = _read_json(path)
            ref = _relative_ref(root, path)
            if artifact is None:
                errors.append(f"{ref}:unreadable:{artifact_error}")
                continue
            observed_fields = sorted(
                key for key in artifact if key.startswith("l1_cognitive_") and artifact[key]
            )
            records.append(
                {
                    "compiled_prompt_artifact_ref": ref,
                    "compiled_prompt_artifact_digest": _file_digest(path),
                    "section_id": str(artifact.get("section_id") or ""),
                    "observed_l1_cognitive_fields": observed_fields,
                }
            )
            if observed_fields:
                errors.append(f"{ref}:control_prompt_contains_v3_fields")
    elif arm == L1_COGNITIVE_V3_CANDIDATE_ARM:
        if plan is None:
            errors.append("candidate_arm_missing_v3_plan")
        else:
            advisory = build_l1_cognitive_consumer_advisory(l1_plan)
            advisory_digest = str((advisory or {}).get("advisory_digest") or "")
            plan_digest = str(plan.get("plan_digest") or "")
            if not advisory_digest or not plan_digest:
                errors.append("candidate_arm_missing_source_bound_advisory")
            for path in prompt_paths:
                artifact, _artifact_error = _read_json(path)
                if artifact is None or not artifact.get("l1_cognitive_plan_digest"):
                    continue
                record, record_errors = _candidate_record(
                    root=root,
                    artifact_path=path,
                    plan_digest=plan_digest,
                    advisory_digest=advisory_digest,
                )
                records.append(record)
                errors.extend(record_errors)
            if not records:
                errors.append("candidate_arm_has_no_observed_c0_to_pa_consumption")
    else:  # treatment validation makes this defensive-only.
        errors.append("unknown_treatment_arm")

    if not prompt_paths:
        errors.append("no_compiled_prompt_artifacts_observed")
    v2_capsule = task_spec.get("apps_rg_planning_v2_capsule")
    v2_capsule_digest = (
        str(v2_capsule.get("capsule_digest") or "")
        if isinstance(v2_capsule, Mapping)
        else ""
    )
    plan_digest = str(plan.get("plan_digest") or "") if plan is not None else ""
    advisory = build_l1_cognitive_consumer_advisory(l1_plan) if plan is not None else None
    advisory_digest = str((advisory or {}).get("advisory_digest") or "")
    observed_c0_outcomes = sorted(
        str((row.get("linked_digests") or {}).get("c0_outcome") or "")
        for row in records
        if isinstance(row.get("linked_digests"), Mapping)
    )
    observed_revisions = sorted(
        str((row.get("linked_digests") or {}).get("revision") or "")
        for row in records
        if isinstance(row.get("linked_digests"), Mapping)
    )
    receipt: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_TREATMENT_EXECUTION_SCHEMA_VERSION,
        "authority_class": _AUTHORITY,
        "app_scope": _APP_SCOPE,
        "treatment": {
            "arm": arm,
            "treatment_digest": str(treatment["treatment_digest"]),
            "assignment_origin": str(treatment["assignment_origin"]),
        },
        "lineage": {
            "l1_v2_capsule_digest": v2_capsule_digest,
            "l1_cognitive_plan_digest": plan_digest,
            "l1_cognitive_advisory_digest": advisory_digest,
            "c0_outcome_set_digest": _sha256(observed_c0_outcomes),
            "l1_cognitive_revision_set_digest": _sha256(observed_revisions),
        },
        "status": "PASS" if not errors else "BLOCKED",
        "records": records,
        "summary": {
            "compiled_prompt_artifact_count": len(prompt_paths),
            "observed_consumption_count": sum(
                1 for row in records if row.get("observed") is True
            ),
            "error_count": len(errors),
            "all_observed_records_source_bound": not errors,
        },
        "errors": sorted(errors),
        "authority": {
            "does_not_dispatch": True,
            "does_not_score_resume_quality": True,
            "does_not_authorize_promotion": True,
            "human_qualified": False,
        },
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = treatment_execution_digest(receipt)
    return receipt


def validate_l1_cognitive_treatment_execution_receipt(
    receipt: Mapping[str, Any]
) -> None:
    """Validate the emitted receipt's narrow observation claims."""

    if receipt.get("schema_version") != L1_COGNITIVE_TREATMENT_EXECUTION_SCHEMA_VERSION:
        raise L1CognitiveTreatmentExecutionError("execution receipt schema is invalid")
    if receipt.get("authority_class") != _AUTHORITY or receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveTreatmentExecutionError("execution receipt scope is invalid")
    if receipt.get("status") not in {"PASS", "BLOCKED"}:
        raise L1CognitiveTreatmentExecutionError("execution receipt status is invalid")
    treatment = receipt.get("treatment")
    lineage = receipt.get("lineage")
    if not isinstance(treatment, Mapping) or not isinstance(lineage, Mapping):
        raise L1CognitiveTreatmentExecutionError("execution receipt lineage is invalid")
    arm = str(treatment.get("arm") or "")
    v2_digest = str(lineage.get("l1_v2_capsule_digest") or "")
    if not v2_digest.startswith("sha256:"):
        raise L1CognitiveTreatmentExecutionError("execution receipt v2 lineage is invalid")
    plan_digest = str(lineage.get("l1_cognitive_plan_digest") or "")
    advisory_digest = str(lineage.get("l1_cognitive_advisory_digest") or "")
    if arm == L1_COGNITIVE_V2_CONTROL_ARM and (plan_digest or advisory_digest):
        raise L1CognitiveTreatmentExecutionError(
            "control execution receipt cannot carry v3 lineage"
        )
    if arm == L1_COGNITIVE_V3_CANDIDATE_ARM and (
        not plan_digest.startswith("sha256:")
        or not advisory_digest.startswith("sha256:")
    ):
        raise L1CognitiveTreatmentExecutionError(
            "candidate execution receipt lacks v3 lineage"
        )
    for field in ("c0_outcome_set_digest", "l1_cognitive_revision_set_digest"):
        if not str(lineage.get(field) or "").startswith("sha256:"):
            raise L1CognitiveTreatmentExecutionError(
                f"execution receipt {field} is invalid"
            )
    if receipt.get("receipt_digest") != treatment_execution_digest(receipt):
        raise L1CognitiveTreatmentExecutionError("execution receipt digest mismatch")
    if not isinstance(receipt.get("records"), list) or not isinstance(receipt.get("errors"), list):
        raise L1CognitiveTreatmentExecutionError("execution receipt observations are invalid")
    if receipt.get("authority") != {
        "does_not_dispatch": True,
        "does_not_score_resume_quality": True,
        "does_not_authorize_promotion": True,
        "human_qualified": False,
    }:
        raise L1CognitiveTreatmentExecutionError("execution receipt authority is invalid")


def emit_l1_cognitive_treatment_execution_receipt(
    *, run_root: Path, l1_plan: Any
) -> Path:
    """Observe and persist the attempt under its Apps RG-owned run root."""

    root = Path(run_root).resolve()
    receipt = build_l1_cognitive_treatment_execution_receipt(
        run_root=root,
        l1_plan=l1_plan,
    )
    validate_l1_cognitive_treatment_execution_receipt(receipt)
    path = root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1CognitiveTreatmentExecutionError",
    "L1_COGNITIVE_TREATMENT_EXECUTION_SCHEMA_VERSION",
    "build_l1_cognitive_treatment_execution_receipt",
    "emit_l1_cognitive_treatment_execution_receipt",
    "treatment_execution_digest",
    "validate_l1_cognitive_treatment_execution_receipt",
]
