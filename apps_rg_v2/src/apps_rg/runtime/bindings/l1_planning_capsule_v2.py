"""Deterministic, advisory-only L1 v2 decision-model capsule for apps_rg.

V2 is deliberately parallel to the v1 capsule.  It turns U0's validated job
description into source-span-bound planning requirements and downstream
obligations, but never reads candidate evidence, chooses a route, schedules
work, assembles a prompt, calls a provider, or writes run state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.bindings.l1_planning_capsule import (
    FrozenDict,
    PlanningProfileIntegrityError,
    _freeze,
    verify_planning_profile_ref_digest,
)
from apps_rg.runtime.bindings.u0_profile_manifest import repo_root

L1_V2_CAPSULE_SCHEMA_VERSION = "apps_rg_l1_planning_capsule.v2"
L1_V2_TAXONOMY_SCHEMA_VERSION = "apps_rg.l1_requirement_taxonomy.v1"
L1_V2_TAXONOMY_REF = "apps_rg/profiles/rg_l1_requirement_taxonomy.v1.json"

_FULL_RESUME_MODES = frozenset(
    {"strategic_tailor", "tailor_existing", "generate_scratch"}
)
_SECTION_MODES = frozenset({"section_regen", "healing_fact_check"})
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPLICIT_REQUIREMENT_RE = re.compile(
    r"\b(?:must|required|minimum|at least|preferred|nice to have|bonus|"
    r"\d+\+?\s+years?|bachelor(?:'s)? degree|master(?:'s)? degree|ph\.d\.)\b",
    re.IGNORECASE,
)
_COMPOUND_RE = re.compile(r"\b(?:and|or)\b|;", re.IGNORECASE)
_YEARS_RE = re.compile(r"\b(?P<years>\d+)\+?\s+years?\b", re.IGNORECASE)
_FORBIDDEN_AUTHORITY_KEYS = frozenset(
    {
        "route_id",
        "route_family",
        "execution_form",
        "selected_route_reason",
        "route_digest",
        "evidence_items",
        "evidence_refs",
        "provider",
        "model",
        "tool_call",
        "write_path",
    }
)
_VALID_COVERAGE_STATUSES = frozenset({"MAPPED", "ESCALATED", "UNMAPPED"})
_VALID_PLANNING_STATUSES = frozenset({"READY", "BLOCKED"})
_VALID_WORK_DAG_RELATIONS = frozenset(
    {
        "REQUIRES_INPUT",
        "REQUIRES_TARGETING",
        "REQUIRES_EVIDENCE",
        "REQUIRES_VALIDATION",
        "MERGE_AFTER",
    }
)
_VALID_WORK_DAG_NODE_TYPES = frozenset(
    {"U0_INPUT", "REQUIREMENT", "WORK_UNIT", "VALIDATION", "MERGE"}
)


class L1PlanningV2IntegrityError(ValueError):
    """Raised when a v2 decision-model capsule is not trustworthy."""


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256(payload: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    )


def stable_l1_v2_capsule_digest(capsule: Mapping[str, Any]) -> str:
    """Return the canonical v2 digest, excluding only ``capsule_digest``."""

    body = dict(capsule)
    body.pop("capsule_digest", None)
    return _sha256(body)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    return value


def _load_taxonomy() -> tuple[dict[str, Any], str, str]:
    """Load the app-owned requirement taxonomy and bind its exact bytes."""

    root = repo_root()
    path = resolve_apps_rg_path(root, "profiles", Path(L1_V2_TAXONOMY_REF).name)
    if not path.is_file():
        raise L1PlanningV2IntegrityError(
            f"L1 v2 taxonomy is missing: {L1_V2_TAXONOMY_REF}"
        )
    try:
        raw = path.read_bytes()
        taxonomy = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy is unreadable") from exc
    if not isinstance(taxonomy, dict):
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy must be a mapping")
    if taxonomy.get("schema_version") != L1_V2_TAXONOMY_SCHEMA_VERSION:
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy schema_version is invalid")
    if taxonomy.get("authority_class") != "PLANNING_PRIOR_ONLY":
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy authority is invalid")
    types = taxonomy.get("requirement_types")
    rules = taxonomy.get("rules")
    markers = taxonomy.get("section_markers")
    if not isinstance(types, list) or "UNKNOWN" not in types:
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy requirement_types are invalid")
    if not isinstance(rules, list) or not isinstance(markers, list):
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy rules are invalid")
    for rule in rules:
        if not isinstance(rule, Mapping):
            raise L1PlanningV2IntegrityError("L1 v2 taxonomy rule is invalid")
        patterns = rule.get("patterns")
        if (
            not str(rule.get("rule_id") or "").strip()
            or str(rule.get("requirement_type") or "") not in types
            or not isinstance(patterns, list)
            or not patterns
        ):
            raise L1PlanningV2IntegrityError("L1 v2 taxonomy rule shape is invalid")
        try:
            for pattern in patterns:
                re.compile(str(pattern), re.IGNORECASE)
        except re.error as exc:
            raise L1PlanningV2IntegrityError("L1 v2 taxonomy regex is invalid") from exc
    return taxonomy, L1_V2_TAXONOMY_REF, hashlib.sha256(raw).hexdigest()


def _generation_mode(app_payload: Mapping[str, Any]) -> str:
    task_spec = app_payload.get("task_spec")
    task = task_spec if isinstance(task_spec, Mapping) else {}
    return str(
        task.get("generation_mode") or app_payload.get("generation_mode") or ""
    ).strip()


def _requested_section_id(app_payload: Mapping[str, Any]) -> str:
    task_spec = app_payload.get("task_spec")
    task = task_spec if isinstance(task_spec, Mapping) else {}
    constraints_value = app_payload.get("user_constraints")
    constraints = constraints_value if isinstance(constraints_value, Mapping) else {}
    direct = (
        app_payload.get("section_id")
        or task.get("section_id")
        or constraints.get("section_id")
    )
    if direct:
        return str(direct).strip()
    sections = constraints.get("sections")
    if (
        isinstance(sections, Sequence)
        and not isinstance(sections, (str, bytes))
        and sections
    ):
        return str(sections[0]).strip()
    return ""


def _work_unit_ids(
    profile: Mapping[str, Any], app_payload: Mapping[str, Any], generation_mode: str
) -> list[str]:
    raw_profiles = profile.get("work_unit_profiles")
    profiles = raw_profiles if isinstance(raw_profiles, Mapping) else {}
    if generation_mode in _FULL_RESUME_MODES:
        return [
            str(unit_id)
            for unit_id, row in profiles.items()
            if isinstance(row, Mapping)
        ]
    if generation_mode in _SECTION_MODES:
        requested = _requested_section_id(app_payload).lower()
        aliases = {
            "experience": "experience_block",
            "skills": "skills_block",
            "education": "education_block",
            "certifications": "certifications_block",
        }
        for candidate in (requested, aliases.get(requested, ""), f"{requested}_block"):
            if candidate and candidate in profiles:
                return [candidate]
        return [
            "healing_section"
            if generation_mode == "healing_fact_check"
            else "requested_section"
        ]
    return ["request_planning_review"]


def _inline_jd_text(app_payload: Mapping[str, Any]) -> tuple[str, str]:
    jd_payload_value = app_payload.get("jd_payload")
    jd_payload = jd_payload_value if isinstance(jd_payload_value, Mapping) else {}
    candidates = (
        ("job_description_text", app_payload.get("job_description_text")),
        ("jd_text", app_payload.get("jd_text")),
        ("jd_payload.jd_text", jd_payload.get("jd_text")),
        ("jd_payload.text", jd_payload.get("text")),
        ("jd_payload.content", jd_payload.get("content")),
    )
    for source_field, value in candidates:
        text = str(value or "").strip()
        if text:
            return text, source_field
    return "", ""


def _declared_jd_hash(app_payload: Mapping[str, Any], jd_text: str) -> str:
    jd_payload_value = app_payload.get("jd_payload")
    jd_payload = jd_payload_value if isinstance(jd_payload_value, Mapping) else {}
    query_value = app_payload.get("query_spec")
    query = query_value if isinstance(query_value, Mapping) else {}
    for value in (
        app_payload.get("jd_hash"),
        jd_payload.get("hash"),
        jd_payload.get("jd_hash"),
        query.get("jd_hash"),
    ):
        digest = str(value or "").strip().lower().removeprefix("sha256:")
        if _SHA256_HEX_RE.fullmatch(digest):
            return digest
    return hashlib.sha256(jd_text.encode("utf-8")).hexdigest() if jd_text else ""


def _source_kind_for_header(line: str, taxonomy: Mapping[str, Any]) -> str:
    normalized = line.lower().rstrip(":")
    for marker in taxonomy.get("section_markers") or ():
        if not isinstance(marker, Mapping):
            continue
        if str(marker.get("contains") or "").lower() in normalized:
            return str(marker.get("source_kind") or "JD_STATEMENT")
    return ""


def _statement_rows(jd_text: str, taxonomy: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_kind = "JD_STATEMENT"
    offset = 0
    ordinal = 0
    for line_number, raw_line in enumerate(jd_text.splitlines(keepends=True), start=1):
        content = raw_line.rstrip("\r\n")
        stripped = content.strip()
        line_start = offset
        line_end = offset + len(content)
        offset += len(raw_line)
        if not stripped:
            continue
        header_kind = _source_kind_for_header(stripped, taxonomy)
        if header_kind and not re.match(r"^(?:[-*\u2022]+|\d+[.)])\s*", stripped):
            source_kind = header_kind
            continue
        text = re.sub(r"^(?:[-*\u2022]+|\d+[.)])\s*", "", stripped).strip()
        is_bullet = text != stripped
        if not is_bullet and not _EXPLICIT_REQUIREMENT_RE.search(text):
            continue
        ordinal += 1
        rows.append(
            {
                "source_kind": source_kind,
                "text": text,
                "ordinal": ordinal,
                "start_line": line_number,
                "end_line": line_number,
                "start_offset": line_start,
                "end_offset": line_end,
            }
        )
    if not rows and jd_text:
        rows.append(
            {
                "source_kind": "JD_STATEMENT",
                "text": " ".join(jd_text.split()),
                "ordinal": 1,
                "start_line": 1,
                "end_line": len(jd_text.splitlines()) or 1,
                "start_offset": 0,
                "end_offset": len(jd_text),
            }
        )
    return rows


def _classify_requirement(
    *, text: str, source_kind: str, taxonomy: Mapping[str, Any]
) -> tuple[str, str, str, str]:
    if source_kind == "PREFERRED_QUALIFICATION":
        return "PREFERRED_QUALIFICATION", "", "HIGH", "section_preferred"
    if source_kind == "RESPONSIBILITY":
        return "RESPONSIBILITY", "experience_block", "HIGH", "section_responsibility"
    matches: list[Mapping[str, Any]] = []
    for rule in taxonomy.get("rules") or ():
        if not isinstance(rule, Mapping):
            continue
        patterns = rule.get("patterns") or ()
        if any(re.search(str(pattern), text, re.IGNORECASE) for pattern in patterns):
            matches.append(rule)
    if not matches:
        return "UNKNOWN", "", "LOW", "unknown"
    chosen = sorted(
        matches,
        key=lambda rule: (-int(rule.get("rank") or 0), str(rule.get("rule_id") or "")),
    )[0]
    return (
        str(chosen.get("requirement_type") or "UNKNOWN"),
        str(chosen.get("target_unit_id") or ""),
        str(chosen.get("confidence") or "LOW"),
        str(chosen.get("rule_id") or ""),
    )


def _criticality(text: str, source_kind: str, requirement_type: str) -> str:
    if source_kind == "PREFERRED_QUALIFICATION":
        return "STANDARD"
    if source_kind == "RESPONSIBILITY":
        return "HIGH"
    if _EXPLICIT_REQUIREMENT_RE.search(text) or requirement_type == "UNKNOWN":
        return "CRITICAL"
    return "STANDARD"


def _modality(text: str, source_kind: str) -> str:
    lowered = text.lower()
    if source_kind == "PREFERRED_QUALIFICATION" or any(
        marker in lowered for marker in ("preferred", "nice to have", "bonus")
    ):
        return "PREFERRED"
    if any(marker in lowered for marker in ("must", "required", "minimum", "at least")):
        return "MUST"
    return "NEUTRAL"


def _qualifiers(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    years = _YEARS_RE.search(text)
    if years:
        rows.append({"kind": "MINIMUM_YEARS", "value": int(years.group("years"))})
    if re.search(r"\b(?:remote|hybrid|onsite|on-site)\b", text, re.IGNORECASE):
        rows.append({"kind": "LOCATION", "value": "PRESENT"})
    if re.search(
        r"\b(?:senior|director|vice president|vp|executive)\b", text, re.IGNORECASE
    ):
        rows.append({"kind": "SENIORITY", "value": "PRESENT"})
    return rows


def _requirements(
    *,
    jd_text: str,
    source_field: str,
    jd_hash: str,
    taxonomy: Mapping[str, Any],
    work_unit_ids: Sequence[str],
) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for row in _statement_rows(jd_text, taxonomy):
        text = str(row["text"])
        requirement_type, target_unit_id, confidence, rule_id = _classify_requirement(
            text=text, source_kind=str(row["source_kind"]), taxonomy=taxonomy
        )
        compound = bool(_COMPOUND_RE.search(text))
        target_unit_ids = [target_unit_id] if target_unit_id in work_unit_ids else []
        criticality = _criticality(text, str(row["source_kind"]), requirement_type)
        if criticality == "CRITICAL" and (
            requirement_type == "UNKNOWN" or compound or not target_unit_ids
        ):
            coverage_status = "ESCALATED"
            escalation_reason = "HITL_OR_UPSTREAM_REQUIREMENT_REVIEW_REQUIRED"
            target_unit_ids = []
        elif target_unit_ids:
            coverage_status = "MAPPED"
            escalation_reason = ""
        else:
            coverage_status = "UNMAPPED"
            escalation_reason = ""
        normalized_text = " ".join(text.lower().split())
        text_digest = _sha256({"text": normalized_text})
        span = {
            "source_field": source_field,
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "text_digest": text_digest,
        }
        span["span_digest"] = _sha256({"jd_hash": jd_hash, **span})
        requirement_id = (
            "l1req-"
            + _sha256(
                {"jd_hash": jd_hash, "span_digest": span["span_digest"]}
            ).removeprefix("sha256:")[:16]
        )
        requirements.append(
            {
                "requirement_id": requirement_id,
                "ordinal": row["ordinal"],
                "source_kind": row["source_kind"],
                "source_span": span,
                "requirement_type": requirement_type,
                "classification_rule_id": rule_id,
                "extraction_confidence": confidence,
                "criticality": criticality,
                "modality": _modality(text, str(row["source_kind"])),
                "qualifiers": _qualifiers(text),
                "compound": compound,
                "target_unit_ids": target_unit_ids,
                "coverage_status": coverage_status,
                "escalation_reason": escalation_reason,
                "normalized_requirement_digest": text_digest,
            }
        )
    return requirements


def _decision(
    *,
    code: str,
    severity: str,
    blocking_policy: str,
    requirement_ids: Sequence[str],
    resolver: str,
    resolution_evidence_shape: Sequence[str],
) -> dict[str, Any]:
    body = {
        "code": code,
        "severity": severity,
        "blocking_policy": blocking_policy,
        "affected_requirement_ids": list(requirement_ids),
        "permitted_resolver": resolver,
        "resolution_evidence_shape": list(resolution_evidence_shape),
        "status": "OPEN",
    }
    digest = _sha256(body)
    return {
        "decision_id": "l1dec-" + digest.removeprefix("sha256:")[:16],
        **body,
        "decision_digest": digest,
    }


def _decision_ledger(
    requirements: Sequence[Mapping[str, Any]], *, jd_available: bool
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    if not jd_available:
        decisions.append(
            _decision(
                code="JD_TEXT_NOT_AVAILABLE_FOR_V2",
                severity="HIGH",
                blocking_policy="BLOCK",
                requirement_ids=(),
                resolver="U0",
                resolution_evidence_shape=("validated_jd_text_digest",),
            )
        )
    duplicate_groups: dict[str, list[str]] = {}
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        if requirement.get("requirement_type") == "UNKNOWN":
            decisions.append(
                _decision(
                    code="UNKNOWN_REQUIREMENT_TYPE",
                    severity="HIGH"
                    if requirement.get("criticality") == "CRITICAL"
                    else "MEDIUM",
                    blocking_policy="REVIEW",
                    requirement_ids=(requirement_id,),
                    resolver="HUMAN",
                    resolution_evidence_shape=("requirement_type_decision",),
                )
            )
        if requirement.get("compound") is True:
            decisions.append(
                _decision(
                    code="COMPOUND_REQUIREMENT",
                    severity="HIGH"
                    if requirement.get("criticality") == "CRITICAL"
                    else "MEDIUM",
                    blocking_policy="REVIEW",
                    requirement_ids=(requirement_id,),
                    resolver="HUMAN",
                    resolution_evidence_shape=("segmentation_decision",),
                )
            )
        if requirement.get("coverage_status") == "ESCALATED":
            decisions.append(
                _decision(
                    code="CRITICAL_TARGETING_ESCALATION",
                    severity="HIGH",
                    blocking_policy="REVIEW",
                    requirement_ids=(requirement_id,),
                    resolver="HUMAN",
                    resolution_evidence_shape=("target_unit_decision",),
                )
            )
        digest = str(requirement.get("normalized_requirement_digest") or "")
        duplicate_groups.setdefault(digest, []).append(requirement_id)
    for ids in duplicate_groups.values():
        if len(ids) > 1:
            decisions.append(
                _decision(
                    code="DUPLICATE_REQUIREMENT",
                    severity="MEDIUM",
                    blocking_policy="REVIEW",
                    requirement_ids=tuple(sorted(ids)),
                    resolver="U0",
                    resolution_evidence_shape=("deduplication_decision",),
                )
            )
    decisions.sort(key=lambda row: str(row["decision_id"]))
    body = {
        "schema_version": "apps_rg.l1_decision_ledger.v2",
        "authority_class": "L1_ADVISORY_ONLY",
        "decisions": decisions,
    }
    body["ledger_digest"] = _sha256(body)
    return body


def _evidence_obligation_ledger(
    requirements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    obligations: list[dict[str, Any]] = []
    for requirement in requirements:
        if requirement.get("coverage_status") != "MAPPED":
            continue
        requirement_id = str(requirement["requirement_id"])
        unit_id = str(requirement["target_unit_ids"][0])
        body = {
            "requirement_id": requirement_id,
            "target_unit_id": unit_id,
            "source_roles": [
                "candidate_support",
                "candidate_counterevidence",
                "JD_targeting",
            ],
            "required_source_classes": ["source_resume", "candidate_profile"],
            "optional_source_classes": ["approved_research_brief"],
            "contradiction_scan_required": True,
            "targeting_only": True,
            "authority_class": "C0_MUST_DECIDE_EVIDENCE",
        }
        obligation_digest = _sha256(body)
        obligations.append(
            {
                "obligation_id": "l1obl-"
                + obligation_digest.removeprefix("sha256:")[:16],
                **body,
                "obligation_digest": obligation_digest,
            }
        )
    obligations.sort(key=lambda row: str(row["obligation_id"]))
    ledger = {
        "schema_version": "apps_rg.l1_evidence_obligation_ledger.v2",
        "authority_class": "L1_RETRIEVAL_INTENT_ADVISORY_ONLY",
        "obligations": obligations,
    }
    ledger["ledger_digest"] = _sha256(ledger)
    return ledger


def _work_dag(
    *, work_unit_ids: Sequence[str], requirements: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    nodes: list[dict[str, str]] = [
        {"node_id": "u0:validated_jd", "node_type": "U0_INPUT"},
        {"node_id": "u0:validated_resume", "node_type": "U0_INPUT"},
    ]
    edges: list[dict[str, str]] = []
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        node_id = f"requirement:{requirement_id}"
        nodes.append({"node_id": node_id, "node_type": "REQUIREMENT"})
        edges.append(
            {"from": "u0:validated_jd", "to": node_id, "relation": "REQUIRES_INPUT"}
        )
        for unit_id in requirement.get("target_unit_ids") or ():
            edges.append(
                {
                    "from": node_id,
                    "to": f"unit:{unit_id}",
                    "relation": "REQUIRES_TARGETING",
                }
            )
    for unit_id in work_unit_ids:
        unit_node = f"unit:{unit_id}"
        validation_node = f"validation:{unit_id}"
        nodes.extend(
            [
                {"node_id": unit_node, "node_type": "WORK_UNIT"},
                {"node_id": validation_node, "node_type": "VALIDATION"},
            ]
        )
        edges.extend(
            [
                {
                    "from": "u0:validated_resume",
                    "to": unit_node,
                    "relation": "REQUIRES_EVIDENCE",
                },
                {
                    "from": unit_node,
                    "to": validation_node,
                    "relation": "REQUIRES_VALIDATION",
                },
            ]
        )
    if len(work_unit_ids) > 1:
        merge_node = "merge:final_resume"
        nodes.append({"node_id": merge_node, "node_type": "MERGE"})
        edges.extend(
            {
                "from": f"validation:{unit_id}",
                "to": merge_node,
                "relation": "MERGE_AFTER",
            }
            for unit_id in work_unit_ids
        )
    nodes.sort(key=lambda row: row["node_id"])
    edges.sort(key=lambda row: (row["from"], row["to"], row["relation"]))
    dag = {
        "schema_version": "apps_rg.l1_work_dag.v2",
        "authority_class": "L1_SCHEDULING_ADVISORY_ONLY",
        "nodes": nodes,
        "edges": edges,
    }
    dag["dag_digest"] = _sha256(dag)
    return dag


def build_apps_rg_l1_planning_capsule_v2(
    *,
    app_payload: Mapping[str, Any],
    request_id: str,
    run_id: str,
    trace_id: str,
    replay_key: str,
    planning_profile_ref: str,
    planning_profile_digest: str,
) -> FrozenDict:
    """Build an immutable v2 decision-model capsule from U0 payload fields only."""

    profile, verified_profile_ref, verified_profile_digest = (
        verify_planning_profile_ref_digest(
            planning_profile_ref, planning_profile_digest
        )
    )
    taxonomy, taxonomy_ref, taxonomy_digest = _load_taxonomy()
    generation_mode = _generation_mode(app_payload)
    work_unit_ids = _work_unit_ids(profile, app_payload, generation_mode)
    jd_text, source_field = _inline_jd_text(app_payload)
    jd_hash = _declared_jd_hash(app_payload, jd_text)
    requirements = _requirements(
        jd_text=jd_text,
        source_field=source_field or "job_description_text",
        jd_hash=jd_hash,
        taxonomy=taxonomy,
        work_unit_ids=work_unit_ids,
    )
    decision_ledger = _decision_ledger(requirements, jd_available=bool(jd_text))
    planning_status = (
        "BLOCKED"
        if any(
            row["blocking_policy"] == "BLOCK" for row in decision_ledger["decisions"]
        )
        else "READY"
    )
    source_binding = {
        "source_class": "U0_VALIDATED_JD_PAYLOAD",
        "jd_hash": jd_hash,
        "inline_jd_available": bool(jd_text),
        "inline_jd_digest": _sha256({"jd_text": jd_text}) if jd_text else "",
    }
    capsule: dict[str, Any] = {
        "schema_version": L1_V2_CAPSULE_SCHEMA_VERSION,
        "authority_class": "PLANNING_ADVISORY_ONLY",
        "planning_status": planning_status,
        "request_id": request_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "replay_key": replay_key,
        "planning_prior_refs": [
            {
                "ref": verified_profile_ref,
                "digest": verified_profile_digest,
                "authority_class": "PLANNING_PRIOR_ONLY",
            },
            {
                "ref": taxonomy_ref,
                "digest": taxonomy_digest,
                "authority_class": "PLANNING_PRIOR_ONLY",
            },
        ],
        "source_binding": source_binding,
        "work_unit_ids": work_unit_ids,
        "requirements": requirements,
        "decision_ledger": decision_ledger,
        "evidence_obligation_ledger": _evidence_obligation_ledger(requirements),
        "work_dag": _work_dag(work_unit_ids=work_unit_ids, requirements=requirements),
        "validation": {
            "u0_payload_only": True,
            "no_route_selection": True,
            "no_evidence_retrieval": True,
            "no_prompt_assembly": True,
            "no_model_call": True,
            "no_tool_call": True,
            "no_l4_write": True,
            "no_candidate_evidence_claim": True,
            "profile_and_taxonomy_digest_bound": True,
        },
    }
    capsule["capsule_digest"] = stable_l1_v2_capsule_digest(capsule)
    verify_apps_rg_l1_planning_capsule_v2(capsule)
    return _freeze(capsule)


def _require_digest(value: Any, *, field: str) -> str:
    digest = str(value or "")
    if not digest.startswith("sha256:") or not _SHA256_HEX_RE.fullmatch(digest[7:]):
        raise L1PlanningV2IntegrityError(f"{field} must be a SHA-256 digest")
    return digest


def _verify_no_authority_keys(payload: Any) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in _FORBIDDEN_AUTHORITY_KEYS:
                raise L1PlanningV2IntegrityError(
                    f"L1 v2 capsule contains forbidden authority key: {key}"
                )
            _verify_no_authority_keys(value)
    elif isinstance(payload, Sequence) and not isinstance(
        payload, (str, bytes, bytearray)
    ):
        for item in payload:
            _verify_no_authority_keys(item)


def _verify_requirements(capsule: Mapping[str, Any]) -> set[str]:
    requirements = capsule.get("requirements")
    work_unit_ids = capsule.get("work_unit_ids")
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        raise L1PlanningV2IntegrityError("v2 requirements are required")
    if not isinstance(work_unit_ids, Sequence) or isinstance(
        work_unit_ids, (str, bytes)
    ):
        raise L1PlanningV2IntegrityError("v2 work_unit_ids are required")
    units = {str(item) for item in work_unit_ids}
    if not units or len(units) != len(work_unit_ids):
        raise L1PlanningV2IntegrityError("v2 work_unit_ids must be unique and nonempty")
    requirement_ids: set[str] = set()
    duplicate_groups: dict[str, list[str]] = {}
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            raise L1PlanningV2IntegrityError("v2 requirement is invalid")
        requirement_id = str(requirement.get("requirement_id") or "")
        if not requirement_id or requirement_id in requirement_ids:
            raise L1PlanningV2IntegrityError("v2 requirement IDs must be unique")
        requirement_ids.add(requirement_id)
        span = requirement.get("source_span")
        if not isinstance(span, Mapping):
            raise L1PlanningV2IntegrityError("v2 requirement source_span is required")
        for field in (
            "source_field",
            "start_line",
            "end_line",
            "start_offset",
            "end_offset",
        ):
            if field not in span:
                raise L1PlanningV2IntegrityError(
                    "v2 requirement source_span is incomplete"
                )
        if int(span["start_line"]) > int(span["end_line"]) or int(
            span["start_offset"]
        ) > int(span["end_offset"]):
            raise L1PlanningV2IntegrityError("v2 requirement source_span is invalid")
        _require_digest(span.get("text_digest"), field="source_span.text_digest")
        _require_digest(span.get("span_digest"), field="source_span.span_digest")
        if requirement.get("coverage_status") not in _VALID_COVERAGE_STATUSES:
            raise L1PlanningV2IntegrityError(
                "v2 requirement coverage_status is invalid"
            )
        target_unit_ids = requirement.get("target_unit_ids")
        if not isinstance(target_unit_ids, Sequence) or isinstance(
            target_unit_ids, (str, bytes)
        ):
            raise L1PlanningV2IntegrityError(
                "v2 requirement target_unit_ids are invalid"
            )
        targets = [str(item) for item in target_unit_ids]
        if (
            len(targets) > 1
            or len(set(targets)) != len(targets)
            or not set(targets).issubset(units)
        ):
            raise L1PlanningV2IntegrityError(
                "v2 requirement target units are not precise"
            )
        critical = requirement.get("criticality") == "CRITICAL"
        compound = requirement.get("compound") is True
        unknown = requirement.get("requirement_type") == "UNKNOWN"
        coverage_status = str(requirement.get("coverage_status"))
        if coverage_status == "MAPPED" and (
            not targets or requirement.get("escalation_reason")
        ):
            raise L1PlanningV2IntegrityError("mapped v2 requirement is inconsistent")
        if coverage_status == "ESCALATED" and (
            targets
            or requirement.get("escalation_reason")
            != "HITL_OR_UPSTREAM_REQUIREMENT_REVIEW_REQUIRED"
        ):
            raise L1PlanningV2IntegrityError("escalated v2 requirement is inconsistent")
        if coverage_status == "UNMAPPED" and (
            targets or requirement.get("escalation_reason")
        ):
            raise L1PlanningV2IntegrityError("unmapped v2 requirement is inconsistent")
        if (
            critical
            and (unknown or compound or not targets)
            and coverage_status != "ESCALATED"
        ):
            raise L1PlanningV2IntegrityError(
                "critical unknown or compound requirement must be escalated"
            )
        normalized_digest = _require_digest(
            requirement.get("normalized_requirement_digest"),
            field="normalized_requirement_digest",
        )
        duplicate_groups.setdefault(normalized_digest, []).append(requirement_id)
    return requirement_ids


def _verify_decision_ledger(
    ledger: Any, *, requirement_ids: set[str], planning_status: str
) -> None:
    if (
        not isinstance(ledger, Mapping)
        or ledger.get("schema_version") != "apps_rg.l1_decision_ledger.v2"
    ):
        raise L1PlanningV2IntegrityError("v2 decision ledger is invalid")
    decisions = ledger.get("decisions")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        raise L1PlanningV2IntegrityError("v2 decision ledger decisions are invalid")
    body = dict(ledger)
    declared_digest = body.pop("ledger_digest", "")
    if declared_digest != _sha256(body):
        raise L1PlanningV2IntegrityError("v2 decision ledger digest mismatch")
    decision_ids: set[str] = set()
    has_block = False
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise L1PlanningV2IntegrityError("v2 decision is invalid")
        decision_id = str(decision.get("decision_id") or "")
        if not decision_id or decision_id in decision_ids:
            raise L1PlanningV2IntegrityError("v2 decision IDs must be unique")
        decision_ids.add(decision_id)
        if decision.get("blocking_policy") not in {"BLOCK", "REVIEW"}:
            raise L1PlanningV2IntegrityError("v2 decision blocking_policy is invalid")
        has_block = has_block or decision.get("blocking_policy") == "BLOCK"
        affected = decision.get("affected_requirement_ids")
        if not isinstance(affected, Sequence) or isinstance(affected, (str, bytes)):
            raise L1PlanningV2IntegrityError(
                "v2 decision affected requirements are invalid"
            )
        if not set(str(item) for item in affected).issubset(requirement_ids):
            raise L1PlanningV2IntegrityError(
                "v2 decision references an unknown requirement"
            )
        body = dict(decision)
        declared = body.pop("decision_digest", "")
        body.pop("decision_id", None)
        if declared != _sha256(body):
            raise L1PlanningV2IntegrityError("v2 decision digest mismatch")
    if planning_status != ("BLOCKED" if has_block else "READY"):
        raise L1PlanningV2IntegrityError(
            "v2 planning_status conflicts with decision ledger"
        )


def _verify_evidence_obligation_ledger(
    ledger: Any, *, capsule: Mapping[str, Any]
) -> None:
    if (
        not isinstance(ledger, Mapping)
        or ledger.get("schema_version") != "apps_rg.l1_evidence_obligation_ledger.v2"
    ):
        raise L1PlanningV2IntegrityError("v2 evidence-obligation ledger is invalid")
    body = dict(ledger)
    declared_digest = body.pop("ledger_digest", "")
    if declared_digest != _sha256(body):
        raise L1PlanningV2IntegrityError(
            "v2 evidence-obligation ledger digest mismatch"
        )
    obligations = ledger.get("obligations")
    if not isinstance(obligations, Sequence) or isinstance(obligations, (str, bytes)):
        raise L1PlanningV2IntegrityError("v2 evidence obligations are invalid")
    expected = {
        str(requirement["requirement_id"]): str(requirement["target_unit_ids"][0])
        for requirement in capsule["requirements"]
        if requirement["coverage_status"] == "MAPPED"
    }
    observed: dict[str, str] = {}
    for obligation in obligations:
        if not isinstance(obligation, Mapping):
            raise L1PlanningV2IntegrityError("v2 evidence obligation is invalid")
        requirement_id = str(obligation.get("requirement_id") or "")
        target_unit_id = str(obligation.get("target_unit_id") or "")
        if requirement_id in observed or requirement_id not in expected:
            raise L1PlanningV2IntegrityError(
                "v2 evidence obligation coverage is invalid"
            )
        observed[requirement_id] = target_unit_id
        if target_unit_id != expected[requirement_id]:
            raise L1PlanningV2IntegrityError("v2 evidence obligation target is invalid")
        if obligation.get("authority_class") != "C0_MUST_DECIDE_EVIDENCE":
            raise L1PlanningV2IntegrityError(
                "v2 evidence obligation authority is invalid"
            )
        if obligation.get("targeting_only") is not True:
            raise L1PlanningV2IntegrityError(
                "v2 evidence obligation targeting posture is invalid"
            )
        if obligation.get("source_roles") != [
            "candidate_support",
            "candidate_counterevidence",
            "JD_targeting",
        ]:
            raise L1PlanningV2IntegrityError(
                "v2 evidence obligation source roles are invalid"
            )
        item = dict(obligation)
        declared = item.pop("obligation_digest", "")
        item.pop("obligation_id", None)
        if declared != _sha256(item):
            raise L1PlanningV2IntegrityError("v2 evidence obligation digest mismatch")
    if observed != expected:
        raise L1PlanningV2IntegrityError(
            "v2 evidence obligation coverage is incomplete"
        )


def _verify_work_dag(dag: Any) -> None:
    if (
        not isinstance(dag, Mapping)
        or dag.get("schema_version") != "apps_rg.l1_work_dag.v2"
    ):
        raise L1PlanningV2IntegrityError("v2 work DAG is invalid")
    body = dict(dag)
    declared_digest = body.pop("dag_digest", "")
    if declared_digest != _sha256(body):
        raise L1PlanningV2IntegrityError("v2 work DAG digest mismatch")
    nodes = dag.get("nodes")
    edges = dag.get("edges")
    if not isinstance(nodes, Sequence) or not isinstance(edges, Sequence):
        raise L1PlanningV2IntegrityError("v2 work DAG nodes and edges are required")
    node_ids = [
        str(row.get("node_id") or "") for row in nodes if isinstance(row, Mapping)
    ]
    if (
        not node_ids
        or len(node_ids) != len(nodes)
        or len(set(node_ids)) != len(node_ids)
    ):
        raise L1PlanningV2IntegrityError("v2 work DAG node IDs are invalid")
    node_types = {
        str(row.get("node_id") or ""): str(row.get("node_type") or "")
        for row in nodes
        if isinstance(row, Mapping)
    }
    if (
        len(node_types) != len(nodes)
        or any(node_type not in _VALID_WORK_DAG_NODE_TYPES for node_type in node_types.values())
    ):
        raise L1PlanningV2IntegrityError("v2 work DAG node types are invalid")
    inbound = {node_id: 0 for node_id in node_ids}
    outbound = {node_id: 0 for node_id in node_ids}
    adjacency = {node_id: [] for node_id in node_ids}
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise L1PlanningV2IntegrityError("v2 work DAG edge is invalid")
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        relation = str(edge.get("relation") or "")
        key = (source, target, relation)
        endpoint_is_valid = False
        if source in node_types and target in node_types:
            endpoint_is_valid = (
                (
                    relation == "REQUIRES_INPUT"
                    and source == "u0:validated_jd"
                    and node_types[target] == "REQUIREMENT"
                )
                or (
                    relation == "REQUIRES_TARGETING"
                    and node_types[source] == "REQUIREMENT"
                    and node_types[target] == "WORK_UNIT"
                )
                or (
                    relation == "REQUIRES_EVIDENCE"
                    and source == "u0:validated_resume"
                    and node_types[target] == "WORK_UNIT"
                )
                or (
                    relation == "REQUIRES_VALIDATION"
                    and node_types[source] == "WORK_UNIT"
                    and node_types[target] == "VALIDATION"
                    and target == f"validation:{source.removeprefix('unit:')}"
                )
                or (
                    relation == "MERGE_AFTER"
                    and node_types[source] == "VALIDATION"
                    and target == "merge:final_resume"
                    and node_types[target] == "MERGE"
                )
            )
        if (
            source not in adjacency
            or target not in adjacency
            or source == target
            or key in seen_edges
            or relation not in _VALID_WORK_DAG_RELATIONS
            or not endpoint_is_valid
        ):
            raise L1PlanningV2IntegrityError("v2 work DAG edge is invalid")
        seen_edges.add(key)
        adjacency[source].append(target)
        inbound[target] += 1
        outbound[source] += 1
    roots = {"u0:validated_jd", "u0:validated_resume"}
    terminals = {
        node_id
        for node_id in node_ids
        if node_id.startswith("validation:")
        or node_id.startswith("merge:")
        or (node_id.startswith("requirement:") and outbound[node_id] == 0)
    }
    for node_id in node_ids:
        if node_id not in roots and inbound[node_id] == 0:
            raise L1PlanningV2IntegrityError(
                f"v2 work DAG has orphaned node: {node_id}"
            )
        if node_id not in roots and node_id not in terminals and outbound[node_id] == 0:
            raise L1PlanningV2IntegrityError(
                f"v2 work DAG has orphaned node: {node_id}"
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in visiting:
            raise L1PlanningV2IntegrityError("v2 work DAG must be acyclic")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in adjacency[node_id]:
            walk(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        walk(node_id)


def verify_apps_rg_l1_planning_capsule_v2(
    capsule: Mapping[str, Any], *, expected_capsule_digest: str = ""
) -> FrozenDict:
    """Fail closed unless a v2 capsule and every internal ledger are coherent."""

    if not isinstance(capsule, Mapping):
        raise L1PlanningV2IntegrityError("L1 v2 capsule must be a mapping")
    if capsule.get("schema_version") != L1_V2_CAPSULE_SCHEMA_VERSION:
        raise L1PlanningV2IntegrityError("L1 v2 capsule schema_version is invalid")
    if capsule.get("authority_class") != "PLANNING_ADVISORY_ONLY":
        raise L1PlanningV2IntegrityError("L1 v2 capsule authority is invalid")
    _verify_no_authority_keys(capsule)
    declared_digest = _require_digest(
        capsule.get("capsule_digest"), field="capsule_digest"
    )
    if declared_digest != stable_l1_v2_capsule_digest(capsule):
        raise L1PlanningV2IntegrityError("L1 v2 capsule digest mismatch")
    if expected_capsule_digest and declared_digest != expected_capsule_digest:
        raise L1PlanningV2IntegrityError(
            "L1 v2 capsule ref does not match embedded digest"
        )
    planning_status = str(capsule.get("planning_status") or "")
    if planning_status not in _VALID_PLANNING_STATUSES:
        raise L1PlanningV2IntegrityError("L1 v2 planning_status is invalid")
    priors = capsule.get("planning_prior_refs")
    if (
        not isinstance(priors, Sequence)
        or isinstance(priors, (str, bytes))
        or len(priors) != 2
    ):
        raise L1PlanningV2IntegrityError(
            "L1 v2 capsule must bind profile and taxonomy priors"
        )
    profile_ref = (
        str(priors[0].get("ref") or "") if isinstance(priors[0], Mapping) else ""
    )
    profile_digest = (
        str(priors[0].get("digest") or "") if isinstance(priors[0], Mapping) else ""
    )
    try:
        _profile, verified_profile_ref, verified_profile_digest = (
            verify_planning_profile_ref_digest(profile_ref, profile_digest)
        )
    except PlanningProfileIntegrityError as exc:
        raise L1PlanningV2IntegrityError("L1 v2 profile prior is invalid") from exc
    if profile_ref != verified_profile_ref or profile_digest != verified_profile_digest:
        raise L1PlanningV2IntegrityError("L1 v2 profile prior is not canonical")
    _taxonomy, taxonomy_ref, taxonomy_digest = _load_taxonomy()
    if (
        not isinstance(priors[1], Mapping)
        or priors[1].get("ref") != taxonomy_ref
        or priors[1].get("digest") != taxonomy_digest
    ):
        raise L1PlanningV2IntegrityError("L1 v2 taxonomy prior is invalid")
    source_binding = capsule.get("source_binding")
    if (
        not isinstance(source_binding, Mapping)
        or source_binding.get("source_class") != "U0_VALIDATED_JD_PAYLOAD"
    ):
        raise L1PlanningV2IntegrityError("L1 v2 source binding is invalid")
    jd_hash = str(source_binding.get("jd_hash") or "")
    if jd_hash and not _SHA256_HEX_RE.fullmatch(jd_hash):
        raise L1PlanningV2IntegrityError("L1 v2 source binding jd_hash is invalid")
    requirement_ids = _verify_requirements(capsule)
    _verify_decision_ledger(
        capsule.get("decision_ledger"),
        requirement_ids=requirement_ids,
        planning_status=planning_status,
    )
    _verify_evidence_obligation_ledger(
        capsule.get("evidence_obligation_ledger"), capsule=capsule
    )
    _verify_work_dag(capsule.get("work_dag"))
    validation = capsule.get("validation")
    required_assertions = {
        "u0_payload_only",
        "no_route_selection",
        "no_evidence_retrieval",
        "no_prompt_assembly",
        "no_model_call",
        "no_tool_call",
        "no_l4_write",
        "no_candidate_evidence_claim",
        "profile_and_taxonomy_digest_bound",
    }
    if not isinstance(validation, Mapping) or any(
        validation.get(key) is not True for key in required_assertions
    ):
        raise L1PlanningV2IntegrityError("L1 v2 validation assertions are incomplete")
    return _freeze(
        {
            "schema_version": "apps_rg_l1_capsule_verification.v2",
            "verified": True,
            "capsule_digest": declared_digest,
            "planning_status": planning_status,
            "decision_ledger_digest": capsule["decision_ledger"]["ledger_digest"],
            "evidence_obligation_ledger_digest": capsule["evidence_obligation_ledger"][
                "ledger_digest"
            ],
            "work_dag_digest": capsule["work_dag"]["dag_digest"],
        }
    )


def extract_verified_planning_capsule_v2(
    plan: Any, *, required: bool = False
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Extract and verify an optional v2 capsule carried beside the v1 projection."""

    task_spec = getattr(plan, "task_spec", None) or {}
    if not isinstance(task_spec, Mapping):
        raise L1PlanningV2IntegrityError("L1 plan task_spec must be a mapping")
    capsule = task_spec.get("apps_rg_planning_v2_capsule")
    capsule_ref = str(task_spec.get("apps_rg_planning_v2_capsule_ref") or "").strip()
    if capsule is None:
        if required:
            raise L1PlanningV2IntegrityError("L1 plan is missing v2 planning capsule")
        return {}, {}
    if not isinstance(capsule, Mapping):
        raise L1PlanningV2IntegrityError("embedded L1 v2 capsule must be a mapping")
    return capsule, verify_apps_rg_l1_planning_capsule_v2(
        capsule, expected_capsule_digest=capsule_ref
    )


__all__ = [
    "L1PlanningV2IntegrityError",
    "L1_V2_CAPSULE_SCHEMA_VERSION",
    "L1_V2_TAXONOMY_REF",
    "build_apps_rg_l1_planning_capsule_v2",
    "extract_verified_planning_capsule_v2",
    "stable_l1_v2_capsule_digest",
    "verify_apps_rg_l1_planning_capsule_v2",
]
