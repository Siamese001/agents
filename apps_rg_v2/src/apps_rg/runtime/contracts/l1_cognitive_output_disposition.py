"""Apps RG-local enforcement of L1 cognitive output dispositions.

L1 planning is advisory. It cannot create evidence, rewrite a provider result,
or authorize execution. This module gives three narrow planning safety outcomes
a real, auditable downstream effect: a C0-declared atom gap must survive in L2
diagnostics; an unresolved hard user-goal constraint must stop Apps RG
finalization; and a critical requirement that L1 could not safely map cannot
silently disappear into a completed artifact. The gate does not synthesize
generated content or resolve the user's constraint.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    L1CognitiveConsumptionError,
    validate_l1_cognitive_consumer_advisory_from_cognitive_plan,
    cognitive_revision_advisory_digest,
    cognitive_revision_gap_requirements,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_OUTPUT_DISPOSITION_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_output_disposition.v3"
)
L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT: Final[str] = (
    sr.FILENAME_L1_COGNITIVE_OUTPUT_DISPOSITION
)
L1_COGNITIVE_OUTPUT_PROJECTION_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_output_projection.v1"
)
L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT: Final[str] = (
    sr.FILENAME_L1_COGNITIVE_OUTPUT_PROJECTION
)
L1_COGNITIVE_OUTPUT_PROJECTION_ID: Final[str] = "l2_l1_cognitive_c0_outcome_projection"
L1_COGNITIVE_OUTPUT_GATE_ID: Final[str] = "x3_l1_cognitive_output_disposition"
L1_COGNITIVE_OUTPUT_BLOCK_X3_CODE: Final[str] = "X3_BLOCK_L1_COGNITIVE_OUTPUT"
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_AUTHORITY_CLASS: Final[str] = "APPS_RG_LOCAL_SAFETY_GATE_ONLY"
_STATUSES: Final[frozenset[str]] = frozenset(
    {"NOT_APPLICABLE", "PASS", "BLOCKED", "WARNING"}
)
_ASSERTIONS: Final[dict[str, bool]] = {
    "does_not_create_evidence": True,
    "does_not_modify_generated_output": True,
    "does_not_retry": True,
    "does_not_select_route": True,
    "does_not_authorize_promotion": True,
    "blocks_apps_rg_finalization_only": True,
    "blocks_unresolved_hard_goal_constraints": True,
    "blocks_unresolved_critical_l1_requirements": True,
}
_PROJECTION_ASSERTIONS: Final[dict[str, bool]] = {
    "does_not_modify_provider_response": True,
    "does_not_modify_display_content": True,
    "does_not_modify_claim_ledger": True,
    "does_not_create_evidence": True,
    "does_not_retry": True,
    "does_not_select_route": True,
    "does_not_authorize_promotion": True,
    "projects_only_c0_gap_dispositions": True,
}
_PROJECTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"NOT_APPLICABLE", "APPLIED", "BLOCKED"}
)
_PROJECTION_SOURCE: Final[str] = "apps_rg_l1_cognitive_c0_outcome_projection"


class L1CognitiveOutputDispositionError(ValueError):
    """Raised when a persisted L1 cognitive output disposition is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__
    return (dict(raw), "") if isinstance(raw, Mapping) else (None, "not_mapping")


def _string_leaves(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        rows: list[str] = []
        for child in value.values():
            rows.extend(_string_leaves(child))
        return tuple(rows)
    if isinstance(value, (list, tuple)):
        rows = []
        for child in value:
            rows.extend(_string_leaves(child))
        return tuple(rows)
    return ()


def _relative_ref(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def l1_cognitive_output_disposition_digest(disposition: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding the disposition's self digest."""

    body = dict(disposition)
    body.pop("disposition_digest", None)
    return _sha256_json(body)


def l1_cognitive_output_projection_digest(projection: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding an L2 projection's self digest."""

    body = dict(projection)
    body.pop("projection_digest", None)
    return _sha256_json(body)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _projection_requirement_rows(
    requirements: tuple[dict[str, str], ...],
) -> list[dict[str, str]]:
    return [
        {
            "requirement_id": row["requirement_id"],
            "outcome_code": row["outcome_code"],
            "gap_tag": row["gap_tag"],
            "change_log_tag": row["change_log_tag"],
        }
        for row in requirements
    ]


def _gap_note_projection_entry(row: Mapping[str, str]) -> dict[str, Any]:
    """Return a non-display diagnostic record, never candidate-written content."""

    return {
        "kind": "L1_COGNITIVE_C0_OUTCOME_GAP",
        "tag": row["gap_tag"],
        "requirement_id": row["requirement_id"],
        "outcome_code": row["outcome_code"],
        "required_output_disposition": "REQUIRE_GAP_NOTE",
        "visibility": "NON_DISPLAY",
        "source": _PROJECTION_SOURCE,
    }


def _change_log_projection_entry(row: Mapping[str, str]) -> dict[str, Any]:
    """Return the matching app-owned audit record for one C0 gap."""

    return {
        "operation": "l1_cognitive_c0_outcome_gap_projection",
        "tag": row["change_log_tag"],
        "requirement_id": row["requirement_id"],
        "outcome_code": row["outcome_code"],
        "source": _PROJECTION_SOURCE,
    }


def _contains_mapping(entries: list[Any], expected: Mapping[str, Any]) -> bool:
    return any(
        isinstance(row, Mapping)
        and all(row.get(key) == value for key, value in expected.items())
        for row in entries
    )


def _projection_base(
    *, section_id: str, advisory_source: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": L1_COGNITIVE_OUTPUT_PROJECTION_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "section_id": str(section_id),
        "projection_id": L1_COGNITIVE_OUTPUT_PROJECTION_ID,
        "revision_advisory": dict(advisory_source),
        "source_binding": {},
        "l2_output": {
            "ref": "l2_output.json",
            "pre_projection_digest": "",
            "post_projection_digest": "",
            "readable": False,
        },
        "outcome_requirements": [],
        "added_gap_note_count": 0,
        "added_change_log_count": 0,
        "errors": [],
        "assertions": dict(_PROJECTION_ASSERTIONS),
        "status": "NOT_APPLICABLE",
        "reason_code": "NO_L1_COGNITIVE_REVISION_ADVISORY",
        "projection_digest": "",
    }


def apply_l1_cognitive_output_projection(
    *, artifact_dir: Path, section_id: str, runtime_payload: dict[str, Any]
) -> dict[str, Any]:
    """Project a C0 gap into L2 diagnostics without changing provider content.

    Provider output cannot be relied on to preserve non-display audit tags.  Apps
    RG therefore owns this narrow post-parse projection: it appends only
    source-bound C0 failure diagnostics to ``gap_notes`` and ``change_log``.
    It never edits provider responses, display content, claim ledgers, evidence,
    routes, retries, or promotion state.
    """

    root = Path(artifact_dir).resolve()
    advisory, advisory_errors, advisory_source = _load_advisory(
        artifact_dir=root,
        runtime_payload=runtime_payload,
    )
    projection = _projection_base(
        section_id=section_id,
        advisory_source=advisory_source,
    )
    if advisory is None:
        projection["projection_digest"] = l1_cognitive_output_projection_digest(
            projection
        )
        _write_json(root / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT, projection)
        runtime_payload.update(
            {
                "l1_cognitive_output_projection_ref": L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
                "l1_cognitive_output_projection_digest": projection[
                    "projection_digest"
                ],
                "l1_cognitive_output_projection_status": projection["status"],
            }
        )
        return projection

    try:
        requirements = cognitive_revision_gap_requirements(
            advisory, section_id=section_id
        )
    except L1CognitiveConsumptionError as exc:
        projection.update(
            {
                "status": "BLOCKED",
                "reason_code": "C0_REVISION_ADVISORY_INVALID",
                "errors": sorted(advisory_errors + [str(exc)]),
            }
        )
    else:
        projection["outcome_requirements"] = _projection_requirement_rows(requirements)
        if not requirements:
            projection.update(
                {
                    "reason_code": "NO_C0_FAILURE_REQUIREMENTS_FOR_SECTION",
                    "errors": sorted(advisory_errors),
                }
            )
            if advisory_errors:
                projection.update(
                    {
                        "status": "BLOCKED",
                        "reason_code": "C0_REVISION_ADVISORY_INVALID",
                    }
                )
        else:
            source_binding, binding_errors = _source_binding_observation(
                artifact_dir=root,
                section_id=section_id,
                advisory=advisory,
            )
            projection["source_binding"] = source_binding
            output_path = root / "l2_output.json"
            output, output_error = _read_json(output_path)
            if output is None:
                projection.update(
                    {
                        "status": "BLOCKED",
                        "reason_code": "C0_OUTCOME_OUTPUT_UNREADABLE",
                        "errors": sorted(
                            advisory_errors
                            + binding_errors
                            + [f"l2_output.json:unreadable:{output_error}"]
                        ),
                    }
                )
            else:
                projection["l2_output"] = {
                    "ref": _relative_ref(root, output_path),
                    "pre_projection_digest": _file_digest(output_path),
                    "post_projection_digest": "",
                    "readable": True,
                }
                gap_notes = output.get("gap_notes", [])
                change_log = output.get("change_log", [])
                shape_errors: list[str] = []
                if not isinstance(gap_notes, list):
                    shape_errors.append("l2_output.json:gap_notes_not_array")
                if not isinstance(change_log, list):
                    shape_errors.append("l2_output.json:change_log_not_array")
                errors = sorted(advisory_errors + binding_errors + shape_errors)
                if errors:
                    projection.update(
                        {
                            "status": "BLOCKED",
                            "reason_code": "C0_OUTCOME_SOURCE_OR_DIAGNOSTIC_INVALID",
                            "errors": errors,
                        }
                    )
                else:
                    projected_gap_notes = list(gap_notes)
                    projected_change_log = list(change_log)
                    added_gap_note_count = 0
                    added_change_log_count = 0
                    for requirement in requirements:
                        gap_entry = _gap_note_projection_entry(requirement)
                        if not _contains_mapping(projected_gap_notes, gap_entry):
                            projected_gap_notes.append(gap_entry)
                            added_gap_note_count += 1
                        change_entry = _change_log_projection_entry(requirement)
                        if not _contains_mapping(projected_change_log, change_entry):
                            projected_change_log.append(change_entry)
                            added_change_log_count += 1
                    projected_output = dict(output)
                    projected_output["gap_notes"] = projected_gap_notes
                    projected_output["change_log"] = projected_change_log
                    _write_json(output_path, projected_output)
                    projection["l2_output"]["post_projection_digest"] = _file_digest(
                        output_path
                    )
                    projection.update(
                        {
                            "status": "APPLIED",
                            "reason_code": "C0_OUTCOME_GAP_DIAGNOSTICS_PROJECTED",
                            "added_gap_note_count": added_gap_note_count,
                            "added_change_log_count": added_change_log_count,
                            "errors": [],
                        }
                    )

    projection["projection_digest"] = l1_cognitive_output_projection_digest(projection)
    validate_l1_cognitive_output_projection(projection)
    _write_json(root / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT, projection)
    runtime_payload.update(
        {
            "l1_cognitive_output_projection_ref": L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
            "l1_cognitive_output_projection_digest": projection["projection_digest"],
            "l1_cognitive_output_projection_status": projection["status"],
        }
    )
    return projection


def validate_l1_cognitive_output_projection(projection: Mapping[str, Any]) -> None:
    """Validate an Apps RG-owned C0-to-L2 diagnostic projection."""

    if (
        projection.get("schema_version")
        != L1_COGNITIVE_OUTPUT_PROJECTION_SCHEMA_VERSION
    ):
        raise L1CognitiveOutputDispositionError("output projection schema is invalid")
    if (
        projection.get("authority_class") != _AUTHORITY_CLASS
        or projection.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveOutputDispositionError("output projection scope is invalid")
    if projection.get("projection_id") != L1_COGNITIVE_OUTPUT_PROJECTION_ID:
        raise L1CognitiveOutputDispositionError("output projection identity is invalid")
    if projection.get("status") not in _PROJECTION_STATUSES:
        raise L1CognitiveOutputDispositionError("output projection status is invalid")
    if projection.get("assertions") != _PROJECTION_ASSERTIONS:
        raise L1CognitiveOutputDispositionError(
            "output projection authority assertions are invalid"
        )
    if not isinstance(projection.get("errors"), list):
        raise L1CognitiveOutputDispositionError("output projection errors are invalid")
    if not isinstance(projection.get("revision_advisory"), Mapping):
        raise L1CognitiveOutputDispositionError("output projection advisory is invalid")
    if not isinstance(projection.get("l2_output"), Mapping):
        raise L1CognitiveOutputDispositionError(
            "output projection L2 binding is invalid"
        )
    if not isinstance(projection.get("outcome_requirements"), list):
        raise L1CognitiveOutputDispositionError(
            "output projection requirements are invalid"
        )
    if projection.get("status") == "APPLIED":
        l2_output = projection.get("l2_output")
        if not isinstance(l2_output, Mapping) or not str(
            l2_output.get("post_projection_digest") or ""
        ).startswith("sha256:"):
            raise L1CognitiveOutputDispositionError(
                "applied output projection lacks L2 digest"
            )
        if projection.get("errors"):
            raise L1CognitiveOutputDispositionError(
                "applied output projection has errors"
            )
    if projection.get("projection_digest") != l1_cognitive_output_projection_digest(
        projection
    ):
        raise L1CognitiveOutputDispositionError("output projection digest is invalid")


def _projection_observation(
    *,
    artifact_dir: Path,
    section_id: str,
    advisory: Mapping[str, Any],
    requirements: tuple[dict[str, str], ...],
    output_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    """Verify the gap tags are app-owned and bound to the sealed L2 result."""

    path = artifact_dir / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
    projection, projection_error = _read_json(path)
    observation: dict[str, Any] = {
        "ref": L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
        "present": projection is not None,
        "digest": "",
        "status": "",
        "advisory_digest_matches": False,
        "section_id_matches": False,
        "l2_output_digest_matches": False,
        "requirements_match": False,
    }
    if projection is None:
        return observation, [
            f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:unreadable:{projection_error}"
        ]
    try:
        validate_l1_cognitive_output_projection(projection)
    except L1CognitiveOutputDispositionError as exc:
        return observation, [f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:invalid:{exc}"]
    observation["digest"] = str(projection.get("projection_digest") or "")
    observation["status"] = str(projection.get("status") or "")
    observation["advisory_digest_matches"] = str(
        (projection.get("revision_advisory") or {}).get("revision_advisory_digest")
        or ""
    ) == str(advisory.get("advisory_digest") or "")
    observation["section_id_matches"] = (
        str(projection.get("section_id") or "") == section_id
    )
    observation["l2_output_digest_matches"] = str(
        (projection.get("l2_output") or {}).get("post_projection_digest") or ""
    ) == _file_digest(output_path)
    observed_requirements = projection.get("outcome_requirements")
    observation["requirements_match"] = (
        observed_requirements == _projection_requirement_rows(requirements)
    )
    errors: list[str] = []
    if observation["status"] != "APPLIED":
        errors.append(
            f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:unexpected_status:"
            f"{observation['status']}"
        )
    if not observation["advisory_digest_matches"]:
        errors.append(
            f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:revision_advisory_digest_mismatch"
        )
    if not observation["section_id_matches"]:
        errors.append(f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:section_id_mismatch")
    if not observation["l2_output_digest_matches"]:
        errors.append(
            f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:l2_output_digest_mismatch"
        )
    if not observation["requirements_match"]:
        errors.append(
            f"{L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT}:requirements_mismatch"
        )
    return observation, errors


def _goal_constraint_observation(
    *, artifact_dir: Path, runtime_payload: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Verify L1 states that must block Apps RG finalization.

    The source plan and advisory remain app-local.  A plan is not trusted just
    because it is present: the advisory must validate against the exact plan,
    and a persisted plan (when present) must agree with its runtime copy.  The
    advisory's critical escalation list is then checked against the atomic
    requirement graph, so an unresolved critical atom cannot become a
    prompt-only warning.
    """

    plan_path = artifact_dir / sr.FILENAME_L1_COGNITIVE_PLAN
    artifact_plan, artifact_error = _read_json(plan_path)
    raw_runtime_plan = runtime_payload.get("l1_cognitive_v3_plan")
    raw_advisory = runtime_payload.get("l1_cognitive_advisory")
    runtime_plan = (
        dict(raw_runtime_plan) if isinstance(raw_runtime_plan, Mapping) else None
    )
    advisory = dict(raw_advisory) if isinstance(raw_advisory, Mapping) else None
    observation: dict[str, Any] = {
        "plan_ref": sr.FILENAME_L1_COGNITIVE_PLAN,
        "plan_artifact_present": artifact_plan is not None,
        "plan_source": (
            "runtime_payload_and_artifact"
            if runtime_plan is not None and artifact_plan is not None
            else "runtime_payload"
            if runtime_plan is not None
            else "artifact"
            if artifact_plan is not None
            else "none"
        ),
        "advisory_source": "runtime_payload" if advisory is not None else "none",
        "plan_digest": "",
        "advisory_digest": "",
        "valid": False,
        "blocked": False,
        "blocking_constraint_ids": [],
        "unresolved_critical_requirement_ids": [],
    }
    if runtime_plan is None and artifact_plan is None and advisory is None:
        return observation, []

    errors: list[str] = []
    if artifact_plan is None and plan_path.is_file():
        errors.append(f"{sr.FILENAME_L1_COGNITIVE_PLAN}:unreadable:{artifact_error}")
    if runtime_plan is None and artifact_plan is None:
        errors.append("goal_constraint_plan_missing")
    if advisory is None:
        errors.append("goal_constraint_advisory_missing")
    plan = runtime_plan or artifact_plan
    if plan is None or advisory is None:
        return observation, sorted(errors)

    runtime_digest = str(runtime_plan.get("plan_digest") or "") if runtime_plan else ""
    artifact_digest = (
        str(artifact_plan.get("plan_digest") or "") if artifact_plan else ""
    )
    if runtime_digest and artifact_digest and runtime_digest != artifact_digest:
        errors.append("goal_constraint_runtime_artifact_plan_digest_mismatch")
    observation["plan_digest"] = str(plan.get("plan_digest") or "")
    observation["advisory_digest"] = str(advisory.get("advisory_digest") or "")
    try:
        validate_l1_cognitive_consumer_advisory_from_cognitive_plan(
            advisory,
            cognitive_plan=plan,
        )
    except L1CognitiveConsumptionError as exc:
        errors.append(f"goal_constraint_binding_invalid:{exc}")
        return observation, sorted(errors)

    goal_frame = plan.get("goal_constraint_frame")
    blocking_ids = (
        sorted(str(value) for value in goal_frame.get("blocking_constraint_ids") or ())
        if isinstance(goal_frame, Mapping)
        else []
    )
    if not isinstance(goal_frame, Mapping) or not all(blocking_ids):
        errors.append("goal_constraint_frame_blocking_state_invalid")
        return observation, sorted(errors)
    advisory_blocked = advisory.get("goal_constraint_blocked")
    if not isinstance(advisory_blocked, bool) or advisory_blocked != bool(blocking_ids):
        errors.append("goal_constraint_advisory_blocking_state_invalid")
        return observation, sorted(errors)

    graph = plan.get("atomic_requirement_graph")
    requirements = graph.get("requirements") if isinstance(graph, Mapping) else None
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        errors.append("critical_requirement_graph_invalid")
        return observation, sorted(errors)
    unresolved_ids: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            errors.append("critical_requirement_graph_row_invalid")
            return observation, sorted(errors)
        if (
            requirement.get("criticality") == "CRITICAL"
            and requirement.get("coverage_status") != "MAPPED"
        ):
            requirement_id = requirement.get("requirement_id")
            if not isinstance(requirement_id, str) or not requirement_id.strip():
                errors.append("critical_requirement_id_invalid")
                return observation, sorted(errors)
            unresolved_ids.append(requirement_id)
    unresolved_ids.sort()
    if len(set(unresolved_ids)) != len(unresolved_ids):
        errors.append("critical_requirement_ids_not_unique")
        return observation, sorted(errors)

    advisory_ids = advisory.get("unresolved_critical_requirement_ids")
    if (
        not isinstance(advisory_ids, list)
        or any(not isinstance(value, str) or not value.strip() for value in advisory_ids)
        or advisory_ids != sorted(advisory_ids)
        or len(set(advisory_ids)) != len(advisory_ids)
        or advisory_ids != unresolved_ids
    ):
        errors.append("critical_requirement_advisory_state_invalid")
        return observation, sorted(errors)
    observation.update(
        {
            "valid": not errors,
            "blocked": advisory_blocked,
            "blocking_constraint_ids": blocking_ids,
            "unresolved_critical_requirement_ids": unresolved_ids,
        }
    )
    return observation, sorted(errors)


def _load_advisory(
    *, artifact_dir: Path, runtime_payload: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
    """Resolve and cross-check the revision advisory without trusting one surface."""

    path = artifact_dir / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY
    from_payload = runtime_payload.get("l1_cognitive_revision_advisory")
    payload_advisory = dict(from_payload) if isinstance(from_payload, Mapping) else None
    artifact_advisory, artifact_error = _read_json(path)
    source: dict[str, Any] = {
        "revision_advisory_ref": sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY,
        "revision_advisory_artifact_present": artifact_advisory is not None,
        "revision_advisory_source": (
            "runtime_payload_and_artifact"
            if payload_advisory is not None and artifact_advisory is not None
            else "runtime_payload"
            if payload_advisory is not None
            else "artifact"
            if artifact_advisory is not None
            else "none"
        ),
    }
    if payload_advisory is None and artifact_advisory is None:
        return None, [], source

    advisory = payload_advisory or artifact_advisory
    assert advisory is not None
    errors: list[str] = []
    if artifact_advisory is None:
        errors.append(
            f"{sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY}:unreadable:{artifact_error}"
        )
    elif payload_advisory is not None and (
        str(payload_advisory.get("advisory_digest") or "")
        != str(artifact_advisory.get("advisory_digest") or "")
    ):
        errors.append("revision_advisory_runtime_artifact_digest_mismatch")

    advisory_digest = str(advisory.get("advisory_digest") or "")
    source["revision_advisory_digest"] = advisory_digest
    if advisory.get("app_scope") != _APP_SCOPE:
        errors.append("revision_advisory_app_scope_invalid")
    if advisory.get("authority_class") != "PLANNING_ADVISORY_ONLY":
        errors.append("revision_advisory_authority_invalid")
    if not advisory_digest or advisory_digest != cognitive_revision_advisory_digest(
        advisory
    ):
        errors.append("revision_advisory_digest_invalid")
    return advisory, errors, source


def _source_binding_observation(
    *, artifact_dir: Path, section_id: str, advisory: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Verify that the emitted L2 surface was actually bound to the C0 revision."""

    errors: list[str] = []
    compiled_path = artifact_dir / "compiled_prompt_artifact.json"
    compiled, compiled_error = _read_json(compiled_path)
    observation: dict[str, Any] = {
        "compiled_prompt_artifact_ref": "compiled_prompt_artifact.json",
        "compiled_prompt_artifact_digest": "",
        "compiled_prompt_matches_revision_advisory": False,
        "revision_ref_matches": False,
        "revision_advisory_ref_matches": False,
        "revision_advisory_digest_matches": False,
        "revision_outcome_ref_matches": False,
        "c0_outcome_digest_matches": False,
    }
    if compiled is None:
        return observation, [
            f"compiled_prompt_artifact.json:unreadable:{compiled_error}"
        ]

    observation["compiled_prompt_artifact_digest"] = _file_digest(compiled_path)
    if str(compiled.get("section_id") or "") != section_id:
        errors.append("compiled_prompt_section_id_mismatch")
    revision_ref_matches = (
        str(compiled.get("l1_cognitive_revision_ref") or "")
        == sr.FILENAME_L1_COGNITIVE_REVISION
    )
    advisory_ref_matches = (
        str(compiled.get("l1_cognitive_revision_advisory_ref") or "")
        == sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY
    )
    advisory_digest_matches = str(
        compiled.get("l1_cognitive_revision_advisory_digest") or ""
    ) == str(advisory.get("advisory_digest") or "")
    outcome_ref_matches = (
        str(compiled.get("l1_cognitive_revision_outcome_ref") or "")
        == sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT
    )
    observation.update(
        {
            "revision_ref_matches": revision_ref_matches,
            "revision_advisory_ref_matches": advisory_ref_matches,
            "revision_advisory_digest_matches": advisory_digest_matches,
            "revision_outcome_ref_matches": outcome_ref_matches,
        }
    )
    if not revision_ref_matches:
        errors.append("compiled_prompt_revision_ref_mismatch")
    if not advisory_ref_matches:
        errors.append("compiled_prompt_revision_advisory_ref_mismatch")
    if not advisory_digest_matches:
        errors.append("compiled_prompt_revision_advisory_digest_mismatch")
    if not outcome_ref_matches:
        errors.append("compiled_prompt_revision_outcome_ref_mismatch")

    revision_path = artifact_dir / sr.FILENAME_L1_COGNITIVE_REVISION
    revision, revision_error = _read_json(revision_path)
    if revision is None or str(revision.get("revision_digest") or "") != str(
        advisory.get("revision_digest") or ""
    ):
        errors.append(
            "revision_artifact_unbound"
            if revision is not None
            else f"{sr.FILENAME_L1_COGNITIVE_REVISION}:unreadable:{revision_error}"
        )

    outcome_path = artifact_dir / sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT
    outcome, outcome_error = _read_json(outcome_path)
    outcome_digest_matches = outcome is not None and str(
        outcome.get("receipt_digest") or ""
    ) == str(advisory.get("c0_outcome_receipt_digest") or "")
    observation["c0_outcome_digest_matches"] = outcome_digest_matches
    if not outcome_digest_matches:
        errors.append(
            "c0_outcome_artifact_unbound"
            if outcome is not None
            else f"{sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT}:unreadable:{outcome_error}"
        )
    observation["compiled_prompt_matches_revision_advisory"] = not errors
    return observation, errors


def build_l1_cognitive_output_disposition(
    *, artifact_dir: Path, section_id: str, runtime_payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a deterministic, Apps RG-local output gate disposition.

    A candidate remains eligible only when the exact C0 failure disposition that
    reached its compiled prompt also survives in its L2 diagnostics.  This is a
    release safety check, not a generated-text edit or a quality score.
    """

    root = Path(artifact_dir).resolve()
    goal_constraint, goal_constraint_errors = _goal_constraint_observation(
        artifact_dir=root,
        runtime_payload=runtime_payload,
    )
    advisory, advisory_errors, advisory_source = _load_advisory(
        artifact_dir=root,
        runtime_payload=runtime_payload,
    )
    base: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_OUTPUT_DISPOSITION_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "section_id": str(section_id),
        "gate_id": L1_COGNITIVE_OUTPUT_GATE_ID,
        "goal_constraint": goal_constraint,
        "revision_advisory": advisory_source,
        "l2_output": {
            "ref": "l2_output.json",
            "digest": "",
            "readable": False,
        },
        "source_binding": {},
        "outcome_projection": {
            "ref": L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
            "present": False,
            "digest": "",
            "status": "",
            "advisory_digest_matches": False,
            "section_id_matches": False,
            "l2_output_digest_matches": False,
            "requirements_match": False,
        },
        "outcome_requirements": [],
        "errors": [],
        "assertions": dict(_ASSERTIONS),
        "status": "NOT_APPLICABLE",
        "reason_code": "NO_L1_COGNITIVE_REVISION_ADVISORY",
        "blocks_finalization": False,
        "disposition_digest": "",
    }
    if goal_constraint_errors:
        base.update(
            {
                "status": "BLOCKED",
                "reason_code": "GOAL_CONSTRAINT_BINDING_INVALID",
                "blocks_finalization": True,
                "errors": goal_constraint_errors,
            }
        )
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base
    if goal_constraint["blocked"] is True:
        base.update(
            {
                "status": "BLOCKED",
                "reason_code": "UNRESOLVED_HARD_GOAL_CONSTRAINTS",
                "blocks_finalization": True,
                "errors": [
                    "unresolved_hard_goal_constraint:" + constraint_id
                    for constraint_id in goal_constraint["blocking_constraint_ids"]
                ],
            }
        )
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base
    unresolved_critical_ids = goal_constraint["unresolved_critical_requirement_ids"]
    if unresolved_critical_ids:
        soften = os.environ.get(
            "APPS_RG_L1_SOFTEN_CRITICAL_GATES", "true"
        ).strip().lower() in ("true", "1", "yes")
        if soften:
            base.update(
                {
                    "status": "WARNING",
                    "reason_code": "UNRESOLVED_CRITICAL_L1_REQUIREMENTS_ADVISORY",
                    "blocks_finalization": False,
                    "errors": [
                        "unresolved_critical_l1_requirement_advisory:" + requirement_id
                        for requirement_id in unresolved_critical_ids
                    ],
                }
            )
        else:
            base.update(
                {
                    "status": "BLOCKED",
                    "reason_code": "UNRESOLVED_CRITICAL_L1_REQUIREMENTS",
                    "blocks_finalization": True,
                    "errors": [
                        "unresolved_critical_l1_requirement:" + requirement_id
                        for requirement_id in unresolved_critical_ids
                    ],
                }
            )
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base
    if advisory is None:
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base

    try:
        requirements = cognitive_revision_gap_requirements(
            advisory, section_id=section_id
        )
    except L1CognitiveConsumptionError as exc:
        base.update(
            {
                "status": "BLOCKED",
                "reason_code": "C0_REVISION_ADVISORY_INVALID",
                "blocks_finalization": True,
                "errors": sorted(advisory_errors + [str(exc)]),
            }
        )
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base

    if not requirements:
        base.update(
            {
                "reason_code": "NO_C0_FAILURE_REQUIREMENTS_FOR_SECTION",
                "errors": sorted(advisory_errors),
            }
        )
        if advisory_errors:
            base.update(
                {
                    "status": "BLOCKED",
                    "reason_code": "C0_REVISION_ADVISORY_INVALID",
                    "blocks_finalization": True,
                }
            )
        base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
        return base

    source_binding, binding_errors = _source_binding_observation(
        artifact_dir=root,
        section_id=section_id,
        advisory=advisory,
    )
    base["source_binding"] = source_binding
    output_path = root / "l2_output.json"
    output, output_error = _read_json(output_path)
    if output is not None:
        base["l2_output"] = {
            "ref": _relative_ref(root, output_path),
            "digest": _file_digest(output_path),
            "readable": True,
        }
    else:
        base["l2_output"] = {
            "ref": _relative_ref(root, output_path),
            "digest": "",
            "readable": False,
        }

    projection_observation: dict[str, Any] = dict(base["outcome_projection"])
    projection_errors: list[str] = []
    if output is not None:
        projection_observation, projection_errors = _projection_observation(
            artifact_dir=root,
            section_id=section_id,
            advisory=advisory,
            requirements=requirements,
            output_path=output_path,
        )
    base["outcome_projection"] = projection_observation
    gap_strings = _string_leaves(output.get("gap_notes")) if output is not None else ()
    change_strings = (
        _string_leaves(output.get("change_log")) if output is not None else ()
    )
    outcome_requirements: list[dict[str, Any]] = []
    for requirement in requirements:
        gap_tag = requirement["gap_tag"]
        change_log_tag = requirement["change_log_tag"]
        outcome_requirements.append(
            {
                **requirement,
                "l2_output_reported_gap_tag": any(
                    gap_tag in value for value in gap_strings
                ),
                "l2_output_reported_change_log_tag": any(
                    change_log_tag in value for value in change_strings
                ),
            }
        )
    base["outcome_requirements"] = outcome_requirements
    output_errors = (
        [f"l2_output.json:unreadable:{output_error}"] if output is None else []
    )
    retention_errors = [
        f"l2_output.json:missing_required_gap_tag:{row['gap_tag']}"
        for row in outcome_requirements
        if not row["l2_output_reported_gap_tag"]
    ] + [
        f"l2_output.json:missing_required_change_log_tag:{row['change_log_tag']}"
        for row in outcome_requirements
        if not row["l2_output_reported_change_log_tag"]
    ]
    errors = sorted(
        advisory_errors
        + binding_errors
        + output_errors
        + projection_errors
        + retention_errors
    )
    if binding_errors or advisory_errors:
        reason_code = "C0_OUTCOME_SOURCE_BINDING_INVALID"
    elif output_errors:
        reason_code = "C0_OUTCOME_OUTPUT_UNREADABLE"
    elif projection_errors:
        reason_code = "C0_OUTCOME_PROJECTION_INVALID"
    elif retention_errors:
        reason_code = "C0_OUTCOME_DISPOSITION_UNRETAINED"
    else:
        reason_code = "C0_OUTCOME_DISPOSITION_RETAINED"
    base.update(
        {
            "status": "PASS" if not errors else "BLOCKED",
            "reason_code": reason_code,
            "blocks_finalization": bool(errors),
            "errors": errors,
        }
    )
    base["disposition_digest"] = l1_cognitive_output_disposition_digest(base)
    return base


def validate_l1_cognitive_output_disposition(disposition: Mapping[str, Any]) -> None:
    """Validate the narrow Apps RG-local gate claim before an X3 mirror uses it."""

    if (
        disposition.get("schema_version")
        != L1_COGNITIVE_OUTPUT_DISPOSITION_SCHEMA_VERSION
    ):
        raise L1CognitiveOutputDispositionError("output disposition schema is invalid")
    if (
        disposition.get("authority_class") != _AUTHORITY_CLASS
        or disposition.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveOutputDispositionError("output disposition scope is invalid")
    if disposition.get("status") not in _STATUSES:
        raise L1CognitiveOutputDispositionError("output disposition status is invalid")
    goal_constraint = disposition.get("goal_constraint")
    if (
        not isinstance(goal_constraint, Mapping)
        or not isinstance(goal_constraint.get("valid"), bool)
        or not isinstance(goal_constraint.get("blocked"), bool)
        or not isinstance(goal_constraint.get("blocking_constraint_ids"), list)
        or not isinstance(
            goal_constraint.get("unresolved_critical_requirement_ids"), list
        )
    ):
        raise L1CognitiveOutputDispositionError(
            "goal constraint observation is invalid"
        )
    if goal_constraint.get("valid") is True and goal_constraint.get("blocked") is True:
        if (
            disposition.get("status") != "BLOCKED"
            or disposition.get("reason_code") != "UNRESOLVED_HARD_GOAL_CONSTRAINTS"
            or disposition.get("blocks_finalization") is not True
            or not goal_constraint.get("blocking_constraint_ids")
        ):
            raise L1CognitiveOutputDispositionError(
                "blocked goal constraint disposition is incoherent"
            )
    unresolved_critical_ids = goal_constraint[
        "unresolved_critical_requirement_ids"
    ]
    if (
        any(
            not isinstance(requirement_id, str) or not requirement_id.strip()
            for requirement_id in unresolved_critical_ids
        )
        or unresolved_critical_ids != sorted(unresolved_critical_ids)
        or len(set(unresolved_critical_ids)) != len(unresolved_critical_ids)
    ):
        raise L1CognitiveOutputDispositionError(
            "unresolved critical requirement observation is invalid"
        )
    if (
        goal_constraint.get("valid") is True
        and goal_constraint.get("blocked") is not True
        and unresolved_critical_ids
        and (
            disposition.get("status") not in {"BLOCKED", "WARNING"}
            or disposition.get("reason_code")
            not in {
                "UNRESOLVED_CRITICAL_L1_REQUIREMENTS",
                "UNRESOLVED_CRITICAL_L1_REQUIREMENTS_ADVISORY",
            }
            or (
                disposition.get("status") == "BLOCKED"
                and disposition.get("blocks_finalization") is not True
            )
            or (
                disposition.get("status") == "WARNING"
                and disposition.get("blocks_finalization") is not False
            )
        )
    ):
        raise L1CognitiveOutputDispositionError(
            "unresolved critical L1 requirement disposition is incoherent"
        )
    if not isinstance(disposition.get("blocks_finalization"), bool):
        raise L1CognitiveOutputDispositionError(
            "output disposition block state is invalid"
        )
    if (
        disposition.get("status") == "BLOCKED"
        and disposition.get("blocks_finalization") is not True
    ):
        raise L1CognitiveOutputDispositionError("blocked output disposition must block")
    if (
        disposition.get("status") != "BLOCKED"
        and disposition.get("blocks_finalization") is not False
    ):
        raise L1CognitiveOutputDispositionError(
            "non-blocked output disposition cannot block"
        )
    if disposition.get("assertions") != _ASSERTIONS:
        raise L1CognitiveOutputDispositionError(
            "output disposition authority assertions are invalid"
        )
    if disposition.get("disposition_digest") != l1_cognitive_output_disposition_digest(
        disposition
    ):
        raise L1CognitiveOutputDispositionError("output disposition digest is invalid")


def emit_l1_cognitive_output_disposition(
    *, artifact_dir: Path, section_id: str, runtime_payload: dict[str, Any]
) -> dict[str, Any]:
    """Persist the gate decision before L2 sealing and expose only its local state."""

    root = Path(artifact_dir)
    disposition = build_l1_cognitive_output_disposition(
        artifact_dir=root,
        section_id=section_id,
        runtime_payload=runtime_payload,
    )
    validate_l1_cognitive_output_disposition(disposition)
    path = root / L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT
    path.write_text(
        json.dumps(disposition, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runtime_payload.update(
        {
            "l1_cognitive_output_disposition_ref": L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT,
            "l1_cognitive_output_disposition_digest": disposition["disposition_digest"],
            "l1_cognitive_output_disposition_status": disposition["status"],
            "l1_cognitive_output_blocks_finalization": disposition[
                "blocks_finalization"
            ],
        }
    )
    return disposition


def load_l1_cognitive_output_disposition(artifact_dir: Path) -> dict[str, Any] | None:
    """Load a validated gate artifact, failing closed for a malformed persisted gate."""

    path = Path(artifact_dir) / L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT
    if not path.is_file():
        return None
    disposition, error = _read_json(path)
    if disposition is None:
        raise L1CognitiveOutputDispositionError(
            f"output disposition unreadable:{error}"
        )
    validate_l1_cognitive_output_disposition(disposition)
    return disposition


def load_l1_cognitive_output_projection(artifact_dir: Path) -> dict[str, Any] | None:
    """Load a validated app-owned C0-to-L2 projection, if one was emitted."""

    path = Path(artifact_dir) / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
    if not path.is_file():
        return None
    projection, error = _read_json(path)
    if projection is None:
        raise L1CognitiveOutputDispositionError(f"output projection unreadable:{error}")
    validate_l1_cognitive_output_projection(projection)
    return projection


def _x3_mirror_was_authorized(x3_doc: Mapping[str, Any]) -> bool:
    """Return whether the persisted Apps RG mirror was previously permitting exit."""

    code = str(x3_doc.get("x3_code") or "").strip()
    if code.startswith("X3_BLOCK") or x3_doc.get("l1_cognitive_output_blocked") is True:
        return False
    return (
        x3_doc.get("pass") is True
        or x3_doc.get("pass_") is True
        or code in {"X3_ALLOW", "X3_REVIEW", "X3_REVIEW_JUDGE_SOFT_FAIL"}
    )


def apply_l1_cognitive_output_disposition_to_x3_mirror(
    artifact_dir: Path,
) -> dict[str, Any] | None:
    """Apply the local L1 safety disposition to the persisted Apps RG X3 mirror.

    This function only reads and writes Apps RG artifacts. It does not import or
    invoke an external exit evaluator, alter generated output, or replace an
    independent X3 failure. If the local safety disposition blocks finalization,
    an otherwise authorized mirror becomes an explicit local block before the
    existing handoff can observe it.
    """

    root = Path(artifact_dir)
    disposition = load_l1_cognitive_output_disposition(root)
    if disposition is None:
        return None
    x3_path = root / "x3_disposition.json"
    x3_doc, _error = _read_json(x3_path)
    if x3_doc is None:
        return None

    blocks = disposition.get("blocks_finalization") is True
    was_authorized = _x3_mirror_was_authorized(x3_doc)
    x3_doc.update(
        {
            "l1_cognitive_output_disposition_ref": L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT,
            "l1_cognitive_output_disposition_digest": str(
                disposition.get("disposition_digest") or ""
            ),
            "l1_cognitive_output_gate_id": L1_COGNITIVE_OUTPUT_GATE_ID,
            "l1_cognitive_output_status": str(disposition.get("status") or ""),
            "l1_cognitive_output_reason_code": str(
                disposition.get("reason_code") or ""
            ),
            "l1_cognitive_output_blocked": blocks,
        }
    )
    if blocks:
        existing_gates = x3_doc.get("blocked_by_gates")
        blocked_by_gates = (
            [str(item) for item in existing_gates if str(item).strip()]
            if isinstance(existing_gates, list)
            else []
        )
        prior_single_gate = str(x3_doc.get("blocked_by_gate") or "").strip()
        if prior_single_gate:
            blocked_by_gates.append(prior_single_gate)
        blocked_by_gates.append(L1_COGNITIVE_OUTPUT_GATE_ID)
        x3_doc["blocked_by_gates"] = sorted(set(blocked_by_gates))
        if was_authorized:
            x3_doc.setdefault(
                "l1_cognitive_output_original_x3_code",
                str(x3_doc.get("x3_code") or ""),
            )
            if "pass" in x3_doc:
                x3_doc.setdefault(
                    "l1_cognitive_output_original_pass", bool(x3_doc.get("pass"))
                )
            if "pass_" in x3_doc:
                x3_doc.setdefault(
                    "l1_cognitive_output_original_pass_",
                    bool(x3_doc.get("pass_")),
                )
            x3_doc["x3_code"] = L1_COGNITIVE_OUTPUT_BLOCK_X3_CODE
            x3_doc["pass"] = False
            x3_doc["pass_"] = False
        x3_doc["terminal_class"] = "failure"
    _write_json(x3_path, x3_doc)
    return x3_doc


__all__ = [
    "L1_COGNITIVE_OUTPUT_BLOCK_X3_CODE",
    "L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT",
    "L1_COGNITIVE_OUTPUT_DISPOSITION_SCHEMA_VERSION",
    "L1_COGNITIVE_OUTPUT_GATE_ID",
    "L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT",
    "L1_COGNITIVE_OUTPUT_PROJECTION_ID",
    "L1_COGNITIVE_OUTPUT_PROJECTION_SCHEMA_VERSION",
    "L1CognitiveOutputDispositionError",
    "apply_l1_cognitive_output_disposition_to_x3_mirror",
    "apply_l1_cognitive_output_projection",
    "build_l1_cognitive_output_disposition",
    "emit_l1_cognitive_output_disposition",
    "l1_cognitive_output_disposition_digest",
    "l1_cognitive_output_projection_digest",
    "load_l1_cognitive_output_disposition",
    "load_l1_cognitive_output_projection",
    "validate_l1_cognitive_output_projection",
    "validate_l1_cognitive_output_disposition",
]
