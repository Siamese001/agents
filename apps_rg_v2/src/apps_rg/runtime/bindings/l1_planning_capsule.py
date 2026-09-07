"""Deterministic, integrity-bound apps_rg L1 planning capsule.

This module is planning-only. It reads app-owned planning priors and U0
projections, then emits immutable advisory structure for downstream stages.
It never routes, retrieves evidence, assembles prompts, calls providers, or
writes run state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.bindings.u0_profile_manifest import repo_root
from apps_rg.runtime.reasoning.section_reasoning_intensity import (
    control_semantics_for_requested_controls,
    profile_to_requested_kw,
    section_reasoning_profile,
)

_FULL_RESUME_GENERATION_MODES = frozenset(
    {"strategic_tailor", "tailor_existing", "generate_scratch"}
)
_SECTION_MODES = frozenset({"section_regen", "healing_fact_check"})
_SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_ROUTE_AUTHORITY_KEYS = frozenset(
    {"route_id", "route_family", "execution_form", "selected_route_reason", "route_digest"}
)
_CANONICAL_PROFILE_REF = "apps_rg/profiles/rg_planning_profile.yaml"
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_JD_OBLIGATION_PLAN_SCHEMA = "apps_rg.jd_obligation_plan.v1"
_JD_OBLIGATION_ESCALATION = "HITL_OR_UPSTREAM_EVIDENCE_REVIEW_REQUIRED"
_JD_OBLIGATION_SOURCE_KINDS = frozenset(
    {"RESPONSIBILITY", "REQUIREMENT", "PREFERRED_QUALIFICATION", "JD_STATEMENT"}
)
_JD_OBLIGATION_CRITICALITIES = frozenset({"CRITICAL", "HIGH", "STANDARD"})
_JD_OBLIGATION_COVERAGE_STATUSES = frozenset({"MAPPED", "ESCALATED", "UNMAPPED"})
_JD_SECTION_MARKERS: tuple[tuple[str, str], ...] = (
    ("responsibilit", "RESPONSIBILITY"),
    ("you may be a good fit", "REQUIREMENT"),
    ("qualifications", "REQUIREMENT"),
    ("requirements", "REQUIREMENT"),
    ("strong candidates", "PREFERRED_QUALIFICATION"),
)
_JD_CRITICAL_TERMS_RE = re.compile(
    r"\b(?:must|required|minimum|\d+\+?\s+years?|track record|deep "
    r"understanding|exceptional|lead(?:ing)?|manage|hire|own)\b",
    re.IGNORECASE,
)
_JD_EXPLICIT_REQUIREMENT_RE = re.compile(
    r"\b(?:must|required|minimum|\d+\+?\s+years?|bachelor(?:'s)? degree|"
    r"master(?:'s)? degree|ph\.d\.)\b",
    re.IGNORECASE,
)
_REQUIRED_VALIDATION_ASSERTIONS = frozenset(
    {
        "no_route_selection",
        "no_evidence_retrieval",
        "no_prompt_assembly",
        "no_model_call",
        "no_tool_call",
        "no_l4_write",
        "profile_ref_digest_bound",
    }
)


class PlanningProfileIntegrityError(ValueError):
    """Raised when an L1 planning profile ref or digest is not trustworthy."""


class PlanningCapsuleIntegrityError(ValueError):
    """Raised when a planning capsule is malformed, mutable, or digest-invalid."""


class FrozenDict(dict):
    """JSON-compatible recursively frozen dictionary."""

    __slots__ = ()

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("planning capsule mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __copy__(self) -> FrozenDict:
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenDict:
        return self


class FrozenList(list):
    """JSON-compatible recursively frozen list."""

    __slots__ = ()

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("planning capsule sequences are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable

    def __copy__(self) -> FrozenList:
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> FrozenList:
        return self


def _freeze(value: Any) -> Any:
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, Mapping):
        return FrozenDict((key, _freeze(item)) for key, item in value.items())
    if isinstance(value, list):
        return FrozenList(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_capsule_digest(capsule_without_digest: Mapping[str, Any]) -> str:
    """Return stable SHA-256 over a capsule, excluding only its own digest field."""

    body = dict(capsule_without_digest)
    body.pop("capsule_digest", None)
    return f"sha256:{hashlib.sha256(_canonical_json(body).encode('utf-8')).hexdigest()}"


def verify_planning_profile_ref_digest(
    planning_profile_ref: str,
    planning_profile_digest: str,
) -> tuple[dict[str, Any], str, str]:
    """Resolve an approved profile and bind the exact loaded bytes to its digest.

    Only files beneath ``apps_rg/profiles`` are eligible. Symlink/path traversal
    escapes fail closed after path resolution.
    """

    root = repo_root().resolve()
    approved_root = resolve_apps_rg_path(root, "profiles").resolve()
    raw_ref = str(planning_profile_ref or _CANONICAL_PROFILE_REF).strip()
    candidate = Path(raw_ref)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif candidate.parts and candidate.parts[0] == "apps_rg":
        resolved = resolve_apps_rg_path(root, *candidate.parts[1:]).resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        profile_relative = resolved.relative_to(approved_root)
        normalized_ref = (Path("apps_rg/profiles") / profile_relative).as_posix()
    except ValueError as exc:
        raise PlanningProfileIntegrityError(
            f"L1 planning profile ref must remain under apps_rg/profiles: {raw_ref!r}"
        ) from exc
    if not resolved.is_file():
        raise PlanningProfileIntegrityError(f"L1 planning profile not found: {normalized_ref}")

    declared_digest = str(planning_profile_digest or "").strip().lower()
    if not _SHA256_HEX_RE.fullmatch(declared_digest):
        raise PlanningProfileIntegrityError(
            "L1 planning profile digest must be a lowercase 64-character SHA-256 hex string"
        )

    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise PlanningProfileIntegrityError(
            f"L1 planning profile unreadable: {normalized_ref}: {exc}"
        ) from exc
    computed_digest = hashlib.sha256(raw).hexdigest()
    if computed_digest != declared_digest:
        raise PlanningProfileIntegrityError(
            "L1 planning profile ref/digest mismatch: "
            f"ref={normalized_ref!r} declared={declared_digest!r} computed={computed_digest!r}"
        )

    try:
        parsed = yaml.safe_load(raw.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PlanningProfileIntegrityError(
            f"L1 planning profile is not valid UTF-8 YAML: {normalized_ref}"
        ) from exc
    if not isinstance(parsed, dict):
        raise PlanningProfileIntegrityError(
            f"L1 planning profile must be a mapping: {normalized_ref}"
        )
    if parsed.get("authority_class") != "PLANNING_PRIOR_ONLY":
        raise PlanningProfileIntegrityError(
            f"L1 planning profile authority_class must be PLANNING_PRIOR_ONLY: {normalized_ref}"
        )
    return parsed, normalized_ref, computed_digest


def _rule_applies(rule: Mapping[str, Any], generation_mode: str) -> bool:
    included = rule.get("applicable_modes") or rule.get("modes")
    if included:
        if not isinstance(included, Sequence) or isinstance(included, (str, bytes)):
            return False
        if generation_mode not in {str(item) for item in included}:
            return False
    excluded = rule.get("excluded_modes") or ()
    if isinstance(excluded, Sequence) and not isinstance(excluded, (str, bytes)):
        if generation_mode in {str(item) for item in excluded}:
            return False
    return True


def stable_ambiguity_register(
    *,
    app_payload: Mapping[str, Any],
    ambiguity_rules: Sequence[Mapping[str, Any]],
    request_id: str,
    planning_profile_digest: str,
    generation_mode: str = "",
) -> dict[str, Any]:
    """Build a deterministic, mode-aware ambiguity register."""

    entries: list[dict[str, Any]] = []
    for rule in ambiguity_rules:
        if not isinstance(rule, Mapping) or not _rule_applies(rule, generation_mode):
            continue
        field = str(rule.get("field") or "").strip()
        code = str(rule.get("code") or "").strip()
        if not field or not code or not _field_is_missing(app_payload, field):
            continue
        if field == "target_role" and not _field_value(app_payload, "target_company"):
            continue
        if field == "target_company" and not _field_value(app_payload, "target_role"):
            continue
        entries.append(
            {
                "code": code,
                "field": field,
                "severity": str(rule.get("severity") or "low"),
                "blocks_progress": bool(rule.get("blocks_progress", False)),
                "note": _ambiguity_note(code),
            }
        )

    max_severity = "none"
    for entry in entries:
        severity = str(entry.get("severity") or "none")
        if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(max_severity, 0):
            max_severity = severity
    blocks_progress = any(bool(entry.get("blocks_progress")) for entry in entries)
    digest_body = {
        "request_id": request_id,
        "generation_mode": generation_mode,
        "planning_profile_digest": planning_profile_digest,
        "entries": entries,
        "max_severity": max_severity,
        "blocks_progress": blocks_progress,
    }
    register_digest = _sha256_json_prefixed(digest_body)
    register_id = f"amb-{register_digest.removeprefix('sha256:')[:16]}"
    if blocks_progress:
        hitl_hint = "required"
    elif _SEVERITY_RANK.get(max_severity, 0) >= _SEVERITY_RANK["high"]:
        hitl_hint = "review"
    elif entries:
        hitl_hint = "optional"
    else:
        hitl_hint = "none"
    return {
        "schema_version": "apps_rg_ambiguity_register_v2",
        "register_id": register_id,
        "register_digest": register_digest,
        "generation_mode": generation_mode or "unknown",
        "max_severity": max_severity,
        "blocks_progress": blocks_progress,
        "hitl_hint": hitl_hint,
        "entries": entries,
    }


def build_apps_rg_l1_planning_capsule(
    *,
    app_payload: Mapping[str, Any],
    request_id: str,
    run_id: str,
    trace_id: str,
    replay_key: str,
    planning_profile_ref: str,
    planning_profile_digest: str,
) -> FrozenDict:
    """Build an immutable, verified apps_rg L1 planning capsule."""

    profile, verified_ref, verified_digest = verify_planning_profile_ref_digest(
        planning_profile_ref,
        planning_profile_digest,
    )
    generation_mode = _generation_mode(app_payload)
    mode_profile = _mode_profile(profile, generation_mode)
    work_units = _work_units_for_mode(profile, app_payload, generation_mode)
    jd_obligation_plan = _jd_obligation_plan(app_payload, work_units)
    ambiguity_register = stable_ambiguity_register(
        app_payload=app_payload,
        ambiguity_rules=profile.get("ambiguity_rules") or (),
        request_id=request_id,
        planning_profile_digest=verified_digest,
        generation_mode=generation_mode,
    )
    planning_status = "BLOCKED" if ambiguity_register["blocks_progress"] else "READY"
    route_feature_hints = _route_feature_hints(
        mode_profile,
        generation_mode,
        ambiguity_register=ambiguity_register,
    )
    completion_criteria = list(mode_profile.get("completion_criteria") or ())
    if not completion_criteria:
        completion_criteria = ["validated_request_shape_preserved", "no_route_authority_claims"]

    capsule: dict[str, Any] = {
        "schema_version": "apps_rg_l1_planning_capsule.v1",
        "authority_class": "PLANNING_ADVISORY_ONLY",
        "planning_status": planning_status,
        "request_id": request_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "replay_key": replay_key,
        "planning_prior_refs": [
            {
                "ref": verified_ref,
                "digest": verified_digest,
                "authority_class": "PLANNING_PRIOR_ONLY",
            }
        ],
        "intent_frame": _intent_frame(app_payload, generation_mode, mode_profile),
        "ambiguity_register": ambiguity_register,
        "completion_criteria": completion_criteria,
        "work_units": work_units,
        "dependency_sketch": _dependency_sketch(work_units),
        "jd_obligation_plan": jd_obligation_plan,
        "evidence_plan": _evidence_plan(work_units, jd_obligation_plan),
        "prompt_plan": _prompt_plan(work_units),
        "cognition_plan": _cognition_plan(work_units),
        "route_feature_hints": route_feature_hints,
        "validation": {
            "no_route_selection": True,
            "no_evidence_retrieval": True,
            "no_prompt_assembly": True,
            "no_model_call": True,
            "no_tool_call": True,
            "no_l4_write": True,
            "profile_ref_digest_bound": True,
        },
    }
    capsule["capsule_digest"] = stable_capsule_digest(capsule)
    verify_apps_rg_l1_planning_capsule(
        capsule,
        expected_profile_ref=verified_ref,
        expected_profile_digest=verified_digest,
    )
    return _freeze(capsule)


def verify_apps_rg_l1_planning_capsule(
    capsule: Mapping[str, Any],
    *,
    expected_capsule_digest: str = "",
    expected_profile_ref: str = "",
    expected_profile_digest: str = "",
) -> FrozenDict:
    """Fail closed unless a capsule is complete, internally coherent, and digest-valid."""

    if not isinstance(capsule, Mapping):
        raise PlanningCapsuleIntegrityError("L1 planning capsule must be a mapping")
    if capsule.get("schema_version") != "apps_rg_l1_planning_capsule.v1":
        raise PlanningCapsuleIntegrityError("unsupported L1 planning capsule schema_version")
    if capsule.get("authority_class") != "PLANNING_ADVISORY_ONLY":
        raise PlanningCapsuleIntegrityError("L1 planning capsule authority_class is invalid")
    _validate_no_route_authority_keys(capsule)

    declared_digest = str(capsule.get("capsule_digest") or "").strip()
    computed_digest = stable_capsule_digest(capsule)
    if not declared_digest or declared_digest != computed_digest:
        raise PlanningCapsuleIntegrityError(
            f"L1 planning capsule digest mismatch: declared={declared_digest!r} computed={computed_digest!r}"
        )
    if expected_capsule_digest and declared_digest != expected_capsule_digest:
        raise PlanningCapsuleIntegrityError(
            "L1 planning capsule ref does not match the embedded capsule digest"
        )

    prior_refs = capsule.get("planning_prior_refs")
    if (
        not isinstance(prior_refs, Sequence)
        or isinstance(prior_refs, (str, bytes))
        or len(prior_refs) != 1
    ):
        raise PlanningCapsuleIntegrityError(
            "L1 planning capsule must bind exactly one planning prior"
        )
    prior = prior_refs[0]
    if not isinstance(prior, Mapping):
        raise PlanningCapsuleIntegrityError("L1 planning prior binding must be a mapping")
    profile_ref = str(prior.get("ref") or "").strip()
    profile_digest = str(prior.get("digest") or "").strip()
    if prior.get("authority_class") != "PLANNING_PRIOR_ONLY":
        raise PlanningCapsuleIntegrityError("planning prior authority_class is invalid")
    try:
        _profile, verified_profile_ref, verified_profile_digest = (
            verify_planning_profile_ref_digest(profile_ref, profile_digest)
        )
    except PlanningProfileIntegrityError as exc:
        raise PlanningCapsuleIntegrityError(
            f"planning prior ref/digest verification failed: {exc}"
        ) from exc
    if profile_ref != verified_profile_ref or profile_digest != verified_profile_digest:
        raise PlanningCapsuleIntegrityError(
            "planning prior binding is not in canonical normalized form"
        )
    if expected_profile_ref and profile_ref != expected_profile_ref:
        raise PlanningCapsuleIntegrityError("planning profile ref does not match expected ref")
    if expected_profile_digest and profile_digest != expected_profile_digest:
        raise PlanningCapsuleIntegrityError("planning profile digest does not match expected digest")

    ambiguity = capsule.get("ambiguity_register")
    if not isinstance(ambiguity, Mapping):
        raise PlanningCapsuleIntegrityError("ambiguity_register is required")
    planning_status = str(capsule.get("planning_status") or "")
    expected_status = "BLOCKED" if bool(ambiguity.get("blocks_progress")) else "READY"
    if planning_status != expected_status:
        raise PlanningCapsuleIntegrityError(
            f"planning_status={planning_status!r} conflicts with ambiguity register"
        )

    work_units = capsule.get("work_units")
    if not isinstance(work_units, Sequence) or isinstance(work_units, (str, bytes)):
        raise PlanningCapsuleIntegrityError("work_units are required")
    unit_ids = {
        str(unit.get("unit_id") or "").strip()
        for unit in work_units
        if isinstance(unit, Mapping) and str(unit.get("unit_id") or "").strip()
    }
    if not unit_ids:
        raise PlanningCapsuleIntegrityError("work_units must contain unit_id values")
    jd_obligation_plan = capsule.get("jd_obligation_plan")
    _verify_jd_obligation_plan(jd_obligation_plan, unit_ids=unit_ids)
    _verify_evidence_plan_jd_coverage(
        capsule.get("evidence_plan"),
        unit_ids=unit_ids,
        jd_obligation_plan=jd_obligation_plan,
    )

    validation = capsule.get("validation")
    if not isinstance(validation, Mapping):
        raise PlanningCapsuleIntegrityError("validation assertions are required")
    missing_assertions = _REQUIRED_VALIDATION_ASSERTIONS - set(validation)
    false_assertions = sorted(
        key for key in _REQUIRED_VALIDATION_ASSERTIONS if validation.get(key) is not True
    )
    if missing_assertions or false_assertions:
        raise PlanningCapsuleIntegrityError(
            "L1 planning capsule validation assertions are incomplete: "
            f"missing={sorted(missing_assertions)} false={false_assertions}"
        )

    receipt = {
        "schema_version": "apps_rg_l1_capsule_verification.v1",
        "verified": True,
        "capsule_digest": declared_digest,
        "planning_profile_ref": profile_ref,
        "planning_profile_digest": profile_digest,
        "planning_status": planning_status,
    }
    return _freeze(receipt)


def extract_verified_planning_capsule(
    plan: Any,
    *,
    required: bool = True,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Extract and verify the capsule carried by an L1 plan contract."""

    task_spec = getattr(plan, "task_spec", None) or {}
    if not isinstance(task_spec, Mapping):
        raise PlanningCapsuleIntegrityError("L1 plan task_spec must be a mapping")
    capsule = task_spec.get("apps_rg_planning_capsule")
    capsule_ref = str(task_spec.get("apps_rg_planning_capsule_ref") or "").strip()
    if capsule is None:
        if required:
            raise PlanningCapsuleIntegrityError("L1 plan is missing apps_rg planning capsule")
        return {}, {}
    if not isinstance(capsule, Mapping):
        raise PlanningCapsuleIntegrityError(
            "embedded apps_rg planning capsule must be a mapping"
        )
    receipt = verify_apps_rg_l1_planning_capsule(
        capsule,
        expected_capsule_digest=capsule_ref,
    )
    return capsule, receipt


def _mode_profile(profile: Mapping[str, Any], generation_mode: str) -> Mapping[str, Any]:
    modes = profile.get("generation_modes")
    if not isinstance(modes, Mapping):
        return {}
    row = modes.get(generation_mode)
    return row if isinstance(row, Mapping) else {}


def _generation_mode(app_payload: Mapping[str, Any]) -> str:
    task_spec = (
        app_payload.get("task_spec")
        if isinstance(app_payload.get("task_spec"), Mapping)
        else {}
    )
    return str(
        task_spec.get("generation_mode") or app_payload.get("generation_mode") or ""
    ).strip()


def _intent_frame(
    app_payload: Mapping[str, Any],
    generation_mode: str,
    mode_profile: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "task_class": "resume_generation",
        "generation_mode": generation_mode or "unknown",
        "deliverable": str(mode_profile.get("deliverable") or "resume_planning_request"),
        "target_company": _field_value(app_payload, "target_company"),
        "target_role": _field_value(app_payload, "target_role"),
        "target_level": _field_value(app_payload, "target_level"),
        "assumptions": _intent_assumptions(app_payload),
        "excluded_authority_claims": [
            "route_selection",
            "evidence_retrieval",
            "prompt_assembly",
            "model_execution",
            "tool_execution",
            "l4_write",
        ],
    }


def _intent_assumptions(app_payload: Mapping[str, Any]) -> list[str]:
    assumptions: list[str] = []
    if not _field_value(app_payload, "target_level"):
        assumptions.append("target_level_may_be_inferred_downstream")
    if not _field_value(app_payload, "target_company"):
        assumptions.append("target_company_may_be_absent")
    return assumptions


def _work_units_for_mode(
    profile: Mapping[str, Any],
    app_payload: Mapping[str, Any],
    generation_mode: str,
) -> list[dict[str, Any]]:
    profiles = profile.get("work_unit_profiles")
    work_unit_profiles = profiles if isinstance(profiles, Mapping) else {}
    if generation_mode in _FULL_RESUME_GENERATION_MODES:
        return [
            _work_unit_from_profile(str(unit_id), row)
            for unit_id, row in work_unit_profiles.items()
            if isinstance(row, Mapping)
        ]
    if generation_mode in _SECTION_MODES:
        section_id = _requested_section_id(app_payload)
        if section_id:
            row = _section_profile(section_id, work_unit_profiles)
            return [_work_unit_from_profile(section_id, row)]
        generic_id = (
            "healing_section"
            if generation_mode == "healing_fact_check"
            else "requested_section"
        )
        return [
            _generic_work_unit(
                generic_id,
                healing=generation_mode == "healing_fact_check",
            )
        ]
    return [_generic_work_unit("request_planning_review", healing=False)]


def _work_unit_from_profile(unit_id: str, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "unit_type": str(row.get("unit_type") or "section"),
        "criticality": str(row.get("criticality") or "T2_QUALITY_SECTION"),
        "support_target": str(row.get("support_target") or "source_backed_claims"),
        "variance_class": str(row.get("variance_class") or "evidence_support"),
        "required_inputs": ["jd_hash", "resume_hash"],
        "required_slots": [str(slot) for slot in (row.get("required_slots") or ())],
        "output_contract_ref": f"apps_rg::output_contract::{unit_id}",
        "quality_floor_ref": (
            f"apps_rg::quality_floor::{row.get('criticality') or 'T2_QUALITY_SECTION'}"
        ),
    }


def _generic_work_unit(unit_id: str, *, healing: bool) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "unit_type": "fact_check_section" if healing else "section",
        "criticality": "T2_QUALITY_SECTION",
        "support_target": "source_backed_claims_only",
        "variance_class": "deterministic_guard" if healing else "evidence_support",
        "required_inputs": ["jd_hash", "resume_hash"],
        "required_slots": ["S0", "D0", "I0", "C0", "U0", "R0"],
        "output_contract_ref": f"apps_rg::output_contract::{unit_id}",
        "quality_floor_ref": "apps_rg::quality_floor::T2_QUALITY_SECTION",
    }


def _requested_section_id(app_payload: Mapping[str, Any]) -> str:
    direct = str(app_payload.get("section_id") or "").strip()
    if direct:
        return direct
    task_spec = (
        app_payload.get("task_spec")
        if isinstance(app_payload.get("task_spec"), Mapping)
        else {}
    )
    if task_spec.get("section_id"):
        return str(task_spec["section_id"]).strip()
    constraints = (
        app_payload.get("user_constraints")
        if isinstance(app_payload.get("user_constraints"), Mapping)
        else {}
    )
    if constraints.get("section_id"):
        return str(constraints["section_id"]).strip()
    sections = constraints.get("sections")
    if (
        isinstance(sections, Sequence)
        and not isinstance(sections, (str, bytes))
        and sections
    ):
        return str(sections[0]).strip()
    return ""


def _section_profile(section_id: str, profiles: Mapping[str, Any]) -> Mapping[str, Any]:
    key = section_id.strip().lower()
    aliases = {
        "experience": "experience_block",
        "skills": "skills_block",
        "education": "education_block",
        "certifications": "certifications_block",
    }
    for candidate in (key, aliases.get(key, ""), f"{key}_block"):
        if candidate and isinstance(profiles.get(candidate), Mapping):
            return profiles[candidate]
    return _generic_work_unit(key or "requested_section", healing=False)


def _dependency_sketch(work_units: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for unit in work_units:
        unit_id = str(unit.get("unit_id") or "")
        if unit_id:
            rows.append({"from": "role_analysis", "to": unit_id, "relation": "SUPPORTS"})
            rows.append(
                {"from": "source_resume_facts", "to": unit_id, "relation": "GROUNDS"}
            )
    return rows


def _jd_obligation_plan(
    app_payload: Mapping[str, Any],
    work_units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive a deterministic, target-only JD obligation plan for L1.

    The JD names what the output should address; it never proves that the
    candidate has satisfied an obligation.  Evidence collection and claim
    decisions remain downstream C0/L2 responsibilities.
    """

    jd_text = _inline_jd_text(app_payload)
    jd_hash = _declared_jd_hash(app_payload, jd_text)
    unit_ids = tuple(
        str(unit.get("unit_id") or "").strip()
        for unit in work_units
        if str(unit.get("unit_id") or "").strip()
    )
    obligations: list[dict[str, Any]] = []
    for source_kind, text in _extract_jd_obligation_texts(jd_text):
        mapped_unit_ids = _jd_obligation_unit_ids(text, unit_ids)
        criticality = _jd_obligation_criticality(text, source_kind)
        escalation_reason = ""
        if mapped_unit_ids:
            coverage_status = "MAPPED"
        elif criticality == "CRITICAL":
            coverage_status = "ESCALATED"
            escalation_reason = _JD_OBLIGATION_ESCALATION
        else:
            coverage_status = "UNMAPPED"
        obligation_id = _jd_obligation_id(
            jd_hash=jd_hash,
            source_kind=source_kind,
            text=text,
        )
        obligations.append(
            {
                "obligation_id": obligation_id,
                "source_kind": source_kind,
                "obligation_text": text,
                "criticality": criticality,
                "mapped_unit_ids": list(mapped_unit_ids),
                "coverage_status": coverage_status,
                "escalation_reason": escalation_reason,
            }
        )

    critical_obligations = [
        obligation
        for obligation in obligations
        if obligation["criticality"] == "CRITICAL"
    ]
    critical_mapped_count = sum(
        1
        for obligation in critical_obligations
        if obligation["coverage_status"] == "MAPPED"
    )
    critical_escalated_count = sum(
        1
        for obligation in critical_obligations
        if obligation["coverage_status"] == "ESCALATED"
    )
    source_binding = {
        "source_class": "U0_VALIDATED_JD_PAYLOAD",
        "jd_hash": jd_hash,
        "inline_text_present": bool(jd_text),
        "inline_text_digest": _sha256_json_prefixed({"jd_text": jd_text})
        if jd_text
        else "",
    }
    plan: dict[str, Any] = {
        "schema_version": _JD_OBLIGATION_PLAN_SCHEMA,
        "authority_class": "L1_TARGETING_ADVISORY_ONLY",
        "source_binding": source_binding,
        "extraction_status": "EXTRACTED" if jd_text else "NO_INLINE_JD_TEXT",
        "obligations": obligations,
        "coverage": {
            "obligation_count": len(obligations),
            "critical_count": len(critical_obligations),
            "critical_mapped_count": critical_mapped_count,
            "critical_escalated_count": critical_escalated_count,
            "all_critical_obligations_resolved": (
                critical_mapped_count + critical_escalated_count
                == len(critical_obligations)
            ),
        },
        "validation": {
            "jd_is_targeting_input_not_candidate_evidence": True,
            "no_evidence_retrieval": True,
            "no_claim_generation": True,
            "no_execution_path_selection": True,
        },
    }
    plan["obligation_plan_digest"] = _stable_jd_obligation_plan_digest(plan)
    return plan


def _inline_jd_text(app_payload: Mapping[str, Any]) -> str:
    jd_payload = (
        app_payload.get("jd_payload")
        if isinstance(app_payload.get("jd_payload"), Mapping)
        else {}
    )
    for value in (
        app_payload.get("job_description_text"),
        app_payload.get("jd_text"),
        jd_payload.get("jd_text"),
        jd_payload.get("text"),
        jd_payload.get("content"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _declared_jd_hash(app_payload: Mapping[str, Any], jd_text: str) -> str:
    jd_payload = (
        app_payload.get("jd_payload")
        if isinstance(app_payload.get("jd_payload"), Mapping)
        else {}
    )
    query_spec = (
        app_payload.get("query_spec")
        if isinstance(app_payload.get("query_spec"), Mapping)
        else {}
    )
    for value in (
        app_payload.get("jd_hash"),
        jd_payload.get("hash"),
        jd_payload.get("jd_hash"),
        query_spec.get("jd_hash"),
    ):
        digest = str(value or "").strip().lower().removeprefix("sha256:")
        if _SHA256_HEX_RE.fullmatch(digest):
            return digest
    return hashlib.sha256(f"text:{jd_text}".encode("utf-8")).hexdigest() if jd_text else ""


def _extract_jd_obligation_texts(jd_text: str) -> list[tuple[str, str]]:
    """Extract explicit bullet and requirement statements without inference."""

    if not jd_text:
        return []
    rows: list[tuple[str, str]] = []
    section_kind = "JD_STATEMENT"
    for raw_line in jd_text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        header_kind = _jd_section_kind(line)
        if header_kind:
            section_kind = header_kind
            continue
        bullet_text = re.sub(r"^(?:[-*•]+|\d+[.)])\s*", "", line).strip()
        if bullet_text != line:
            rows.append((section_kind, bullet_text))
        elif _JD_EXPLICIT_REQUIREMENT_RE.search(line):
            rows.append(("REQUIREMENT", line))

    if not rows and jd_text.strip():
        normalized = " ".join(jd_text.split())
        rows.append(("JD_STATEMENT", normalized))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source_kind, text in rows:
        key = (source_kind, text)
        if key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def _jd_section_kind(line: str) -> str:
    normalized = line.lower().rstrip(":")
    for marker, source_kind in _JD_SECTION_MARKERS:
        if marker in normalized:
            return source_kind
    return ""


def _jd_obligation_criticality(text: str, source_kind: str) -> str:
    if source_kind == "PREFERRED_QUALIFICATION":
        return "STANDARD"
    if source_kind == "REQUIREMENT" or _JD_CRITICAL_TERMS_RE.search(text):
        return "CRITICAL"
    if source_kind == "RESPONSIBILITY":
        return "HIGH"
    return "STANDARD"


def _jd_obligation_id(*, jd_hash: str, source_kind: str, text: str) -> str:
    digest = _sha256_json_prefixed(
        {"jd_hash": jd_hash, "source_kind": source_kind, "obligation_text": text}
    )
    return f"jdob-{digest.removeprefix('sha256:')[:16]}"


def _jd_obligation_unit_ids(text: str, available_unit_ids: Sequence[str]) -> tuple[str, ...]:
    """Map only explicit JD terms to L1 work units; unknowns remain unresolved."""

    normalized = text.lower()
    candidates: list[str] = []

    def add(*unit_ids: str) -> None:
        for unit_id in unit_ids:
            if unit_id in available_unit_ids and unit_id not in candidates:
                candidates.append(unit_id)

    if re.search(r"\b(?:lead|manage|mentor|hire|coach|executive|c-suite|team)\b", normalized):
        add("executive_summary", "headline", "experience_block")
    if re.search(
        r"\b(?:partner|partnership|gsi|cloud|gtm|pre-sales|presales|customer|revenue|deal)\b",
        normalized,
    ):
        add("headline", "executive_summary", "experience_block")
    if re.search(
        r"\b(?:technical|architect|ai|genai|llm|api|engineering|solution|deployment|"
        r"prompt|evaluation|integration)\b",
        normalized,
    ):
        add("experience_block", "competencies", "skills_block")
    if re.search(r"\b(?:communication|teaching|thought leadership)\b", normalized):
        add("headline", "executive_summary", "experience_block")
    if re.search(r"\b(?:bachelor|master|ph\.d|degree|coursework|education)\b", normalized):
        add("education_block")
    if re.search(r"\b(?:certification|certified)\b", normalized):
        add("certifications_block")
    if re.search(r"\b(?:years?|track record|experience)\b", normalized):
        add("experience_block")
    return tuple(candidates)


def _stable_jd_obligation_plan_digest(plan: Mapping[str, Any]) -> str:
    body = dict(plan)
    body.pop("obligation_plan_digest", None)
    return _sha256_json_prefixed(body)


def _evidence_plan(
    work_units: Sequence[Mapping[str, Any]],
    jd_obligation_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    obligation_ids_by_unit: dict[str, list[str]] = {}
    obligations = jd_obligation_plan.get("obligations")
    if isinstance(obligations, Sequence) and not isinstance(obligations, (str, bytes)):
        for obligation in obligations:
            if not isinstance(obligation, Mapping):
                continue
            obligation_id = str(obligation.get("obligation_id") or "").strip()
            for unit_id in obligation.get("mapped_unit_ids") or ():
                normalized_unit_id = str(unit_id or "").strip()
                if obligation_id and normalized_unit_id:
                    obligation_ids_by_unit.setdefault(normalized_unit_id, []).append(
                        obligation_id
                    )
    return [
        {
            "unit_id": str(unit.get("unit_id") or ""),
            "support_target": str(unit.get("support_target") or ""),
            "query_intent": f"collect_support_for_{unit.get('unit_id') or 'unit'}",
            "allowed_source_classes": [
                "source_resume",
                "job_description",
                "approved_research_brief",
                "candidate_profile",
            ],
            "contradiction_scan_expected": True,
            "authority_class": "C0_EXECUTES_RETRIEVAL",
            "jd_obligation_ids": obligation_ids_by_unit.get(
                str(unit.get("unit_id") or ""), []
            ),
            "jd_obligation_targeting_only": True,
        }
        for unit in work_units
    ]


def _verify_jd_obligation_plan(
    jd_obligation_plan: Any,
    *,
    unit_ids: set[str],
) -> None:
    if not isinstance(jd_obligation_plan, Mapping):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan is required")
    if jd_obligation_plan.get("schema_version") != _JD_OBLIGATION_PLAN_SCHEMA:
        raise PlanningCapsuleIntegrityError("jd_obligation_plan schema_version is invalid")
    if jd_obligation_plan.get("authority_class") != "L1_TARGETING_ADVISORY_ONLY":
        raise PlanningCapsuleIntegrityError("jd_obligation_plan authority_class is invalid")
    declared_digest = str(jd_obligation_plan.get("obligation_plan_digest") or "")
    if declared_digest != _stable_jd_obligation_plan_digest(jd_obligation_plan):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan digest mismatch")
    source_binding = jd_obligation_plan.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan source_binding is required")
    if source_binding.get("source_class") != "U0_VALIDATED_JD_PAYLOAD":
        raise PlanningCapsuleIntegrityError("jd_obligation_plan source binding is invalid")
    jd_hash = str(source_binding.get("jd_hash") or "")
    if jd_hash and not _SHA256_HEX_RE.fullmatch(jd_hash):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan jd_hash is invalid")
    obligations = jd_obligation_plan.get("obligations")
    if not isinstance(obligations, Sequence) or isinstance(obligations, (str, bytes)):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan obligations are required")
    observed_ids: set[str] = set()
    critical_mapped = 0
    critical_escalated = 0
    for obligation in obligations:
        if not isinstance(obligation, Mapping):
            raise PlanningCapsuleIntegrityError("jd obligation must be a mapping")
        obligation_id = str(obligation.get("obligation_id") or "").strip()
        source_kind = str(obligation.get("source_kind") or "").strip()
        text = str(obligation.get("obligation_text") or "").strip()
        criticality = str(obligation.get("criticality") or "").strip()
        coverage_status = str(obligation.get("coverage_status") or "").strip()
        mapped_unit_ids = obligation.get("mapped_unit_ids")
        if not obligation_id or obligation_id in observed_ids:
            raise PlanningCapsuleIntegrityError("jd obligation ids must be present and unique")
        observed_ids.add(obligation_id)
        if not text or source_kind not in _JD_OBLIGATION_SOURCE_KINDS:
            raise PlanningCapsuleIntegrityError("jd obligation source content is invalid")
        if criticality not in _JD_OBLIGATION_CRITICALITIES:
            raise PlanningCapsuleIntegrityError("jd obligation criticality is invalid")
        if coverage_status not in _JD_OBLIGATION_COVERAGE_STATUSES:
            raise PlanningCapsuleIntegrityError("jd obligation coverage_status is invalid")
        if not isinstance(mapped_unit_ids, Sequence) or isinstance(mapped_unit_ids, (str, bytes)):
            raise PlanningCapsuleIntegrityError("jd obligation mapped_unit_ids is invalid")
        mapped = tuple(str(unit_id or "").strip() for unit_id in mapped_unit_ids)
        if len(set(mapped)) != len(mapped) or not set(mapped).issubset(unit_ids):
            raise PlanningCapsuleIntegrityError("jd obligation maps an unknown or duplicate unit")
        escalation_reason = str(obligation.get("escalation_reason") or "").strip()
        if coverage_status == "MAPPED" and (not mapped or escalation_reason):
            raise PlanningCapsuleIntegrityError("mapped jd obligation must have only unit mappings")
        if coverage_status == "ESCALATED" and (
            mapped or escalation_reason != _JD_OBLIGATION_ESCALATION
        ):
            raise PlanningCapsuleIntegrityError("escalated jd obligation is invalid")
        if coverage_status == "UNMAPPED" and (mapped or escalation_reason):
            raise PlanningCapsuleIntegrityError("unmapped jd obligation is invalid")
        if criticality == "CRITICAL":
            if coverage_status not in {"MAPPED", "ESCALATED"}:
                raise PlanningCapsuleIntegrityError(
                    "critical jd obligation must be mapped or escalated"
                )
            critical_mapped += coverage_status == "MAPPED"
            critical_escalated += coverage_status == "ESCALATED"

    coverage = jd_obligation_plan.get("coverage")
    if not isinstance(coverage, Mapping):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan coverage is required")
    critical_count = critical_mapped + critical_escalated
    expected_coverage = {
        "obligation_count": len(obligations),
        "critical_count": critical_count,
        "critical_mapped_count": critical_mapped,
        "critical_escalated_count": critical_escalated,
        "all_critical_obligations_resolved": True,
    }
    if any(coverage.get(key) != value for key, value in expected_coverage.items()):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan coverage is inconsistent")
    validation = jd_obligation_plan.get("validation")
    if not isinstance(validation, Mapping) or any(
        validation.get(key) is not True
        for key in (
            "jd_is_targeting_input_not_candidate_evidence",
            "no_evidence_retrieval",
            "no_claim_generation",
            "no_execution_path_selection",
        )
    ):
        raise PlanningCapsuleIntegrityError("jd_obligation_plan validation is incomplete")


def _verify_evidence_plan_jd_coverage(
    evidence_plan: Any,
    *,
    unit_ids: set[str],
    jd_obligation_plan: Mapping[str, Any],
) -> None:
    if not isinstance(evidence_plan, Sequence) or isinstance(evidence_plan, (str, bytes)):
        raise PlanningCapsuleIntegrityError("evidence_plan is required")
    expected: dict[str, set[str]] = {unit_id: set() for unit_id in unit_ids}
    for obligation in jd_obligation_plan["obligations"]:
        for unit_id in obligation["mapped_unit_ids"]:
            expected[str(unit_id)].add(str(obligation["obligation_id"]))
    observed: dict[str, set[str]] = {}
    for row in evidence_plan:
        if not isinstance(row, Mapping):
            raise PlanningCapsuleIntegrityError("evidence_plan row is invalid")
        unit_id = str(row.get("unit_id") or "").strip()
        obligation_ids = row.get("jd_obligation_ids")
        if unit_id not in unit_ids or unit_id in observed:
            raise PlanningCapsuleIntegrityError("evidence_plan unit coverage is invalid")
        if not isinstance(obligation_ids, Sequence) or isinstance(obligation_ids, (str, bytes)):
            raise PlanningCapsuleIntegrityError("evidence_plan jd_obligation_ids is invalid")
        observed[unit_id] = {str(obligation_id) for obligation_id in obligation_ids}
        if row.get("jd_obligation_targeting_only") is not True:
            raise PlanningCapsuleIntegrityError("evidence_plan JD targeting assertion is invalid")
    if observed != expected:
        raise PlanningCapsuleIntegrityError("evidence_plan JD obligation coverage is inconsistent")


def _prompt_plan(work_units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "unit_id": str(unit.get("unit_id") or ""),
            "required_slots": list(unit.get("required_slots") or ()),
            "provenance_slots_required": True,
            "prompt_bom_refs": ["apps_rg/prompt_assembly/prompt_bom.yaml"],
            "authority_class": "PA_ASSEMBLES_PROMPT",
        }
        for unit in work_units
    ]


def _reasoning_lane_for_unit(unit_id: str) -> str:
    return {
        "education_block": "education",
        "certifications_block": "certifications",
        "skills_block": "competencies",
    }.get(unit_id, unit_id)


def _cognition_plan(work_units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in work_units:
        unit_id = str(unit.get("unit_id") or "")
        profile = section_reasoning_profile(_reasoning_lane_for_unit(unit_id))
        requested = profile_to_requested_kw(profile)
        rows.append(
            {
                "unit_id": unit_id,
                "tier": profile.tier.value,
                "variance_class": str(unit.get("variance_class") or ""),
                "requested_controls": requested,
                "control_semantics": control_semantics_for_requested_controls(requested),
                "self_consistency_intent": float(profile.self_consistency_samples),
                "reflexion_intent": float(profile.reflexion_loops),
                "controls_applied": False,
                "execution_provability": "ADVISORY_ONLY_UNTIL_L2_RECEIPT",
                "singleton_transport_policy": (
                    "do_not_mark_applied_without_runner_receipt"
                ),
                "authority_class": "L2_OR_L3_MUST_PROVE_EXECUTION",
            }
        )
    return rows


def _route_feature_hints(
    mode_profile: Mapping[str, Any],
    generation_mode: str,
    *,
    ambiguity_register: Mapping[str, Any],
) -> dict[str, Any]:
    raw = mode_profile.get("route_feature_hints")
    hints = dict(raw) if isinstance(raw, Mapping) else {}
    if not hints:
        hints = {
            "multi_work_unit": generation_mode in _FULL_RESUME_GENERATION_MODES,
            "merge_needed": generation_mode in _FULL_RESUME_GENERATION_MODES,
            "candidate_selection_needed": generation_mode
            in _FULL_RESUME_GENERATION_MODES,
            "grounding_needed": generation_mode in _FULL_RESUME_GENERATION_MODES
            or generation_mode in _SECTION_MODES,
        }
    if ambiguity_register.get("blocks_progress"):
        hitl_risk = "required"
    elif ambiguity_register.get("hitl_hint") == "review":
        hitl_risk = "medium"
    elif ambiguity_register.get("entries"):
        hitl_risk = "low"
    else:
        hitl_risk = "none"
    hints["authority_class"] = "ADVISORY_ONLY"
    hints["hitl_risk_hint"] = hitl_risk
    return hints


def _field_is_missing(app_payload: Mapping[str, Any], field: str) -> bool:
    return not bool(_field_value(app_payload, field).strip())


def _field_value(app_payload: Mapping[str, Any], field: str) -> str:
    if field in {"target_company", "target_role", "target_level"}:
        query_spec = (
            app_payload.get("query_spec")
            if isinstance(app_payload.get("query_spec"), Mapping)
            else {}
        )
        target = (
            query_spec.get("target")
            if isinstance(query_spec.get("target"), Mapping)
            else {}
        )
        target_key = field.removeprefix("target_")
        return str(app_payload.get(field) or target.get(target_key) or "").strip()
    if field == "job_description_text":
        jd_payload = (
            app_payload.get("jd_payload")
            if isinstance(app_payload.get("jd_payload"), Mapping)
            else {}
        )
        return str(
            app_payload.get("job_description_text")
            or app_payload.get("jd_text")
            or jd_payload.get("jd_text")
            or jd_payload.get("text")
            or app_payload.get("job_description_ref")
            or jd_payload.get("ref")
            or ""
        ).strip()
    if field == "source_resume_text":
        resume_payload = (
            app_payload.get("resume_payload")
            if isinstance(app_payload.get("resume_payload"), Mapping)
            else {}
        )
        return str(
            app_payload.get("source_resume_text")
            or app_payload.get("resume_text")
            or resume_payload.get("resume_text")
            or resume_payload.get("text")
            or app_payload.get("source_resume_ref")
            or resume_payload.get("ref")
            or ""
        ).strip()
    return str(app_payload.get(field) or "").strip()


def _ambiguity_note(code: str) -> str:
    return {
        "TARGET_ROLE_MISSING": "Company provided without explicit role title",
        "TARGET_COMPANY_MISSING": "Role provided without company name",
        "TARGET_LEVEL_UNSPECIFIED": "Default downstream level policy may apply",
        "JOB_DESCRIPTION_EMPTY": "Grounding and tailoring cannot be proven without JD text",
        "SOURCE_RESUME_EMPTY": "Resume body missing at U0 handoff",
    }.get(code, "Planning signal missing")


def _sha256_json_prefixed(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()}"


def _validate_no_route_authority_keys(payload: Any) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in _ROUTE_AUTHORITY_KEYS:
                raise PlanningCapsuleIntegrityError(
                    f"L1 planning capsule contains route-authority key: {key}"
                )
            _validate_no_route_authority_keys(value)
    elif isinstance(payload, Sequence) and not isinstance(
        payload,
        (str, bytes, bytearray),
    ):
        for value in payload:
            _validate_no_route_authority_keys(value)


__all__ = [
    "FrozenDict",
    "FrozenList",
    "PlanningCapsuleIntegrityError",
    "PlanningProfileIntegrityError",
    "build_apps_rg_l1_planning_capsule",
    "extract_verified_planning_capsule",
    "stable_ambiguity_register",
    "stable_capsule_digest",
    "verify_apps_rg_l1_planning_capsule",
    "verify_planning_profile_ref_digest",
]
