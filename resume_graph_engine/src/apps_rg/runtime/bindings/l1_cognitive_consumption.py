"""Safe downstream projections for the Apps RG L1 v3 cognitive plan.

The L1 cognitive plan is advisory.  Consumers may use it to preserve distinct
requirement coverage and escalate uncertainty, but cannot turn it into route,
evidence, model, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any, Final

from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    L1CognitivePlanError,
    validate_l1_cognitive_plan_v3,
    validate_l1_cognitive_revision_v3,
)


L1_COGNITIVE_CONSUMER_ADVISORY_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_consumer_advisory.v5"
)
L1_COGNITIVE_REVISION_ADVISORY_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_revision_advisory.v2"
)
_AUTHORITY_CLASS: Final[str] = "PLANNING_ADVISORY_ONLY"
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_C0_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset(
    {"C0_CONTRADICTED", "C0_INSUFFICIENT"}
)
_TARGET_UNIT_SECTION_FAMILIES: Final[dict[str, frozenset[str]]] = {
    "experience_block": frozenset(
        {
            "unify_bullets",
            "ibm_bullets",
            "unify_narrative",
            "ibm_narrative",
        }
    ),
    "executive_summary": frozenset({"executive_summary"}),
    "headline": frozenset({"headline"}),
    "competencies": frozenset({"competencies"}),
}


class L1CognitiveConsumptionError(ValueError):
    """Raised when an L1 v3 plan cannot be consumed safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def cognitive_consumer_advisory_digest(advisory: Mapping[str, Any]) -> str:
    """Return the canonical advisory digest excluding its self digest."""

    body = dict(advisory)
    body.pop("advisory_digest", None)
    return _sha256(body)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_sequence(value: Any, *, field: str) -> list[dict[str, Any]]:
    """Return a validated mapping sequence without accepting text-like values."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise L1CognitiveConsumptionError(f"L1 v3 {field} is invalid")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise L1CognitiveConsumptionError(f"L1 v3 {field} contains an invalid row")
        rows.append(dict(row))
    return rows


def _atomic_requirement_slots(
    cognitive: Mapping[str, Any],
    *,
    requirement_ids: set[str] | None = None,
    observed_outcomes: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Project exact atomic planning identity without exposing raw target prose.

    The original v1 advisory reduced the plan to aggregate requirement counts.  That
    made a provider-visible instruction impossible to distinguish from a generic
    "cover N things" prompt.  These slots retain the atom, constraint, deliberation,
    and (when known) outcome identity while preserving the existing targeting-text
    boundary: C0 and the already-authorized JD prompt remain the only source of
    candidate-facing text and evidence authority.
    """

    graph = _mapping(cognitive.get("atomic_requirement_graph"))
    requirements = _mapping_sequence(
        graph.get("requirements"), field="requirement graph"
    )
    relations = _mapping_sequence(graph.get("relations"), field="requirement relations")
    alternatives = _mapping(cognitive.get("alternative_plan_ledger"))
    decisions = _mapping_sequence(
        alternatives.get("decisions"), field="alternative ledger"
    )
    decision_by_requirement = {
        str(row.get("requirement_id") or ""): row for row in decisions
    }
    if "" in decision_by_requirement:
        raise L1CognitiveConsumptionError(
            "L1 v3 alternative decision identity is invalid"
        )
    feasibility = _mapping(cognitive.get("feasibility_graph"))
    options = _mapping_sequence(feasibility.get("options"), field="feasibility options")
    option_by_id = {str(row.get("option_id") or ""): row for row in options}
    if "" in option_by_id or len(option_by_id) != len(options):
        raise L1CognitiveConsumptionError(
            "L1 v3 feasibility option identity is invalid"
        )
    relation_context_by_requirement: dict[str, list[dict[str, str]]] = {}
    for relation in relations:
        from_requirement_id = str(relation.get("from_requirement_id") or "").strip()
        to_requirement_id = str(relation.get("to_requirement_id") or "").strip()
        relation_type = str(relation.get("relation") or "").strip()
        relation_scope = str(relation.get("relation_scope") or "").strip()
        if not all(
            (from_requirement_id, to_requirement_id, relation_type, relation_scope)
        ):
            raise L1CognitiveConsumptionError("L1 v3 relation context is invalid")
        relation_context_by_requirement.setdefault(from_requirement_id, []).append(
            {
                "direction": "OUTGOING",
                "relation": relation_type,
                "relation_scope": relation_scope,
                "related_requirement_id": to_requirement_id,
            }
        )
        relation_context_by_requirement.setdefault(to_requirement_id, []).append(
            {
                "direction": "INCOMING",
                "relation": relation_type,
                "relation_scope": relation_scope,
                "related_requirement_id": from_requirement_id,
            }
        )

    slots: list[dict[str, Any]] = []
    for requirement in requirements:
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        if not requirement_id:
            raise L1CognitiveConsumptionError("L1 v3 requirement identity is invalid")
        if requirement_ids is not None and requirement_id not in requirement_ids:
            continue
        decision = decision_by_requirement.get(requirement_id)
        if decision is None:
            raise L1CognitiveConsumptionError(
                "L1 v3 requirement has no alternative-plan decision"
            )
        primary_option = option_by_id.get(str(decision.get("primary_option_id") or ""))
        if primary_option is None:
            raise L1CognitiveConsumptionError(
                "L1 v3 primary feasibility option is invalid"
            )
        span = _mapping(requirement.get("source_span"))
        span_digest = str(span.get("span_digest") or "").strip()
        if not span_digest.startswith("sha256:"):
            raise L1CognitiveConsumptionError(
                "L1 v3 requirement span identity is invalid"
            )
        qualifiers = _mapping_sequence(
            requirement.get("qualifiers"), field="qualifiers"
        )
        normalized_qualifiers: list[dict[str, Any]] = []
        for qualifier in qualifiers:
            kind = str(qualifier.get("kind") or "").strip()
            if not kind:
                raise L1CognitiveConsumptionError("L1 v3 qualifier identity is invalid")
            normalized_qualifiers.append(
                {"kind": kind, "value": qualifier.get("value")}
            )
        target_unit_ids = sorted(
            {
                str(value).strip()
                for value in requirement.get("target_unit_ids") or ()
                if str(value).strip()
            }
        )
        slot: dict[str, Any] = {
            "requirement_id": requirement_id,
            "parent_requirement_id": str(
                requirement.get("parent_requirement_id") or ""
            ).strip(),
            "ordinal": int(requirement.get("ordinal") or 0),
            "source_span_digest": span_digest,
            "requirement_type": str(requirement.get("requirement_type") or "").strip(),
            "classification_rule_id": str(
                requirement.get("classification_rule_id") or ""
            ).strip(),
            "criticality": str(requirement.get("criticality") or "").strip(),
            "modality": str(requirement.get("modality") or "").strip(),
            "qualifiers": normalized_qualifiers,
            "target_unit_ids": target_unit_ids,
            "coverage_status": str(requirement.get("coverage_status") or "").strip(),
            "decomposition_mode": str(
                requirement.get("decomposition_mode") or ""
            ).strip(),
            "inherited_predicate_class": str(
                requirement.get("inherited_predicate_class") or ""
            ).strip(),
            "qualifier_scope": str(requirement.get("qualifier_scope") or "").strip(),
            "relation_context": sorted(
                relation_context_by_requirement.get(requirement_id, []),
                key=lambda row: (
                    row["direction"],
                    row["relation"],
                    row["related_requirement_id"],
                ),
            ),
            "planned_decision": str(decision.get("decision") or "").strip(),
            "decision_id": str(decision.get("decision_id") or "").strip(),
            "alternative_option_id": str(
                decision.get("alternative_option_id") or ""
            ).strip(),
            "decision_risk": str(decision.get("risk") or "").strip(),
            "selected_option_kind": str(
                primary_option.get("option_kind") or ""
            ).strip(),
            "selected_feasibility_status": str(
                primary_option.get("feasibility_status") or ""
            ).strip(),
            "selected_precondition_codes": list(
                primary_option.get("precondition_codes") or ()
            ),
            "counterevidence_risk_codes": list(
                primary_option.get("counterevidence_risk_codes") or ()
            ),
            "raw_targeting_text_omitted": True,
        }
        required_fields = (
            "parent_requirement_id",
            "requirement_type",
            "classification_rule_id",
            "criticality",
            "modality",
            "coverage_status",
            "decomposition_mode",
            "inherited_predicate_class",
            "qualifier_scope",
            "planned_decision",
            "decision_id",
            "decision_risk",
            "selected_option_kind",
            "selected_feasibility_status",
        )
        if slot["ordinal"] < 1 or any(
            not str(slot[field]) for field in required_fields
        ):
            raise L1CognitiveConsumptionError("L1 v3 requirement slot is incomplete")
        if not all(
            isinstance(value, str) and value
            for value in slot["selected_precondition_codes"]
        ):
            raise L1CognitiveConsumptionError(
                "L1 v3 requirement preconditions are invalid"
            )
        if observed_outcomes is not None:
            outcome_code = str(observed_outcomes.get(requirement_id) or "").strip()
            if not outcome_code:
                raise L1CognitiveConsumptionError(
                    "L1 v3 revision outcome identity is invalid"
                )
            slot["observed_outcome_code"] = outcome_code
            slot["required_output_disposition"] = (
                "REQUIRE_GAP_NOTE"
                if outcome_code in _C0_FAILURE_OUTCOMES
                else "COVERAGE_OR_GAP"
            )
            slot["required_gap_tag"] = (
                f"L1_COGNITIVE_GAP:{requirement_id}:{outcome_code}"
                if outcome_code in _C0_FAILURE_OUTCOMES
                else ""
            )
        slots.append(slot)
    return sorted(slots, key=lambda row: str(row["requirement_id"]))


def _slots_for_section(
    slots: Sequence[Mapping[str, Any]], *, section_id: str
) -> tuple[dict[str, Any], ...]:
    """Return atom slots that are deliberately targeted at one section family."""

    normalized_section_id = str(section_id or "").strip()
    result: list[dict[str, Any]] = []
    for slot in slots:
        targets = tuple(str(value) for value in slot.get("target_unit_ids") or ())
        if not normalized_section_id or any(
            normalized_section_id
            in _TARGET_UNIT_SECTION_FAMILIES.get(target, frozenset())
            for target in targets
        ):
            result.append(dict(slot))
    return tuple(sorted(result, key=lambda row: str(row["requirement_id"])))


def _format_qualifiers(slot: Mapping[str, Any]) -> str:
    rows = _mapping_sequence(slot.get("qualifiers"), field="slot qualifiers")
    if not rows:
        return "none"
    return ", ".join(f"{str(row['kind'])}={row.get('value')}" for row in rows)


def _format_relation_context(slot: Mapping[str, Any]) -> str:
    rows = _mapping_sequence(
        slot.get("relation_context"), field="slot relation context"
    )
    if not rows:
        return "none"
    rendered: list[str] = []
    for row in rows:
        direction = str(row.get("direction") or "").strip()
        relation = str(row.get("relation") or "").strip()
        relation_scope = str(row.get("relation_scope") or "").strip()
        related_id = str(row.get("related_requirement_id") or "").strip()
        if not all((direction, relation, relation_scope, related_id)):
            raise L1CognitiveConsumptionError("L1 v3 slot relation context is invalid")
        rendered.append(f"{direction}:{relation}:{relation_scope}:{related_id}")
    return ",".join(rendered)


def cognitive_revision_gap_requirements(
    advisory: Mapping[str, Any] | None,
    *,
    section_id: str = "",
) -> tuple[dict[str, str], ...]:
    """Return source-bound C0 failure tags a section result must retain.

    This is deliberately narrow: it observes the safe disposition required by an
    already-authoritative C0 failure.  It does not judge prose, create evidence,
    select a route, or authorize a retry.
    """

    if advisory is None or advisory.get("revision_status") != "PROPOSED":
        return ()
    slots = _slots_for_section(
        _mapping_sequence(
            advisory.get("affected_requirement_slots"),
            field="revision advisory requirement slots",
        ),
        section_id=section_id,
    )
    requirements: list[dict[str, str]] = []
    for slot in slots:
        requirement_id = str(slot.get("requirement_id") or "").strip()
        outcome_code = str(slot.get("observed_outcome_code") or "").strip()
        disposition = str(slot.get("required_output_disposition") or "").strip()
        gap_tag = str(slot.get("required_gap_tag") or "").strip()
        if not requirement_id or outcome_code not in _C0_FAILURE_OUTCOMES:
            raise L1CognitiveConsumptionError(
                "L1 v3 revision advisory outcome identity is invalid"
            )
        if disposition != "REQUIRE_GAP_NOTE" or not gap_tag:
            raise L1CognitiveConsumptionError(
                "L1 v3 revision advisory gap disposition is invalid"
            )
        requirements.append(
            {
                "requirement_id": requirement_id,
                "outcome_code": outcome_code,
                "gap_tag": gap_tag,
                "change_log_tag": f"L1_COGNITIVE_ATOM:{requirement_id}:GAP",
            }
        )
    return tuple(sorted(requirements, key=lambda row: row["requirement_id"]))


def _verified_cognitive_plan(cognitive: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(cognitive, Mapping):
        raise L1CognitiveConsumptionError("L1 v3 cognitive plan is invalid")
    plan = dict(cognitive)
    try:
        validate_l1_cognitive_plan_v3(plan)
    except L1CognitivePlanError as exc:
        raise L1CognitiveConsumptionError("L1 v3 cognitive plan is invalid") from exc
    return plan


def extract_l1_cognitive_plan(
    plan: Any, *, required: bool = False
) -> dict[str, Any] | None:
    """Extract and verify the optional v3 cognitive plan from an L1 contract."""

    task_spec = _mapping(getattr(plan, "task_spec", None))
    raw = task_spec.get("apps_rg_cognitive_v3_plan")
    if raw is None:
        if required:
            raise L1CognitiveConsumptionError("L1 v3 cognitive plan is required")
        return None
    if not isinstance(raw, Mapping):
        raise L1CognitiveConsumptionError("L1 v3 cognitive plan is invalid")
    cognitive = dict(raw)
    expected_ref = str(task_spec.get("apps_rg_cognitive_v3_plan_ref") or "").strip()
    if expected_ref != str(cognitive.get("plan_digest") or ""):
        raise L1CognitiveConsumptionError("L1 v3 cognitive plan reference is invalid")
    return _verified_cognitive_plan(cognitive)


def build_l1_cognitive_consumer_advisory(plan: Any) -> dict[str, Any] | None:
    """Project verified cognitive intent into authority-safe downstream facts."""

    cognitive = extract_l1_cognitive_plan(plan)
    if cognitive is None:
        return None
    advisory = build_l1_cognitive_consumer_advisory_from_cognitive_plan(cognitive)
    validate_l1_cognitive_consumer_advisory(advisory, plan=plan)
    return advisory


def validate_l1_cognitive_consumer_advisory(
    advisory: Mapping[str, Any], *, plan: Any
) -> None:
    """Fail closed unless a consumer advisory exactly derives from L1 v3."""

    if not isinstance(advisory, Mapping):
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory is invalid")
    if advisory.get("schema_version") != L1_COGNITIVE_CONSUMER_ADVISORY_SCHEMA_VERSION:
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory schema is invalid")
    if (
        advisory.get("authority_class") != _AUTHORITY_CLASS
        or advisory.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveConsumptionError(
            "L1 v3 consumer advisory authority is invalid"
        )
    if advisory.get("advisory_digest") != cognitive_consumer_advisory_digest(advisory):
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory digest is invalid")
    cognitive = extract_l1_cognitive_plan(plan, required=True)
    validate_l1_cognitive_consumer_advisory_from_cognitive_plan(
        advisory,
        cognitive_plan=cognitive,
    )


def validate_l1_cognitive_consumer_advisory_from_cognitive_plan(
    advisory: Mapping[str, Any],
    *,
    cognitive_plan: Mapping[str, Any],
) -> None:
    """Verify a PA projection against the exact safe L1 v3 source plan."""

    cognitive = _verified_cognitive_plan(cognitive_plan)
    if not isinstance(advisory, Mapping):
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory is invalid")
    if advisory.get("schema_version") != L1_COGNITIVE_CONSUMER_ADVISORY_SCHEMA_VERSION:
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory schema is invalid")
    if (
        advisory.get("authority_class") != _AUTHORITY_CLASS
        or advisory.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveConsumptionError(
            "L1 v3 consumer advisory authority is invalid"
        )
    if advisory.get("advisory_digest") != cognitive_consumer_advisory_digest(advisory):
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory digest is invalid")
    if advisory.get("cognitive_plan_digest") != cognitive["plan_digest"]:
        raise L1CognitiveConsumptionError(
            "L1 v3 consumer advisory plan binding is invalid"
        )
    expected = build_l1_cognitive_consumer_advisory_unchecked(cognitive)
    if dict(advisory) != expected:
        raise L1CognitiveConsumptionError("L1 v3 consumer advisory does not match plan")


def build_l1_cognitive_consumer_advisory_from_cognitive_plan(
    cognitive_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a projection from the source plan retained by a section runtime."""

    return build_l1_cognitive_consumer_advisory_unchecked(
        _verified_cognitive_plan(cognitive_plan)
    )


def _goal_constraint_advisory(
    cognitive: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, int, int]:
    """Project only L1's explicit safe constraint decisions into PA facts.

    The goal frame deliberately retains no raw constraint value.  This bridge
    therefore consumes the alternative ledger rather than recreating intent:
    only ``PROJECT_SAFE_DIRECTIVE`` rows can become provider-visible planning
    context, and unresolved hard constraints remain an escalation.
    """

    goal_frame = _mapping(cognitive.get("goal_constraint_frame"))
    slots = _mapping_sequence(
        goal_frame.get("constraint_slots"), field="goal constraint slots"
    )
    alternatives = _mapping(cognitive.get("alternative_plan_ledger"))
    decisions = _mapping_sequence(
        alternatives.get("constraint_decisions"),
        field="goal constraint decisions",
    )
    decision_by_constraint_id = {
        str(row.get("constraint_id") or "").strip(): row for row in decisions
    }
    if "" in decision_by_constraint_id or len(decision_by_constraint_id) != len(
        decisions
    ):
        raise L1CognitiveConsumptionError(
            "L1 v3 goal constraint decision identity is invalid"
        )

    directives: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    deferred_preference_count = 0
    conflict_deferred_preference_count = 0
    for slot in slots:
        constraint_id = str(slot.get("constraint_id") or "").strip()
        decision = decision_by_constraint_id.get(constraint_id)
        if not constraint_id or decision is None:
            raise L1CognitiveConsumptionError(
                "L1 v3 goal constraint decision is unbound"
            )
        primary_action = str(decision.get("primary_action") or "").strip()
        status = str(slot.get("interpretation_status") or "").strip()
        if primary_action == "PROJECT_SAFE_DIRECTIVE":
            if status != "ACTIONABLE":
                raise L1CognitiveConsumptionError(
                    "L1 v3 projected constraint is not actionable"
                )
            directive_code = str(slot.get("directive_code") or "").strip()
            if not directive_code:
                raise L1CognitiveConsumptionError(
                    "L1 v3 projected constraint lacks a safe directive"
                )
            numeric_limit = slot.get("numeric_limit")
            directives.append(
                {
                    "constraint_id": constraint_id,
                    "constraint_decision_id": str(
                        decision.get("constraint_decision_id") or ""
                    ).strip(),
                    "semantic_kind": str(slot.get("semantic_kind") or "").strip(),
                    "polarity": str(slot.get("polarity") or "").strip(),
                    "scope": str(slot.get("scope") or "").strip(),
                    "directive_code": directive_code,
                    "numeric_limit": (
                        dict(numeric_limit)
                        if isinstance(numeric_limit, Mapping)
                        else None
                    ),
                }
            )
        elif primary_action == "ESCALATE_TO_U0":
            escalations.append(
                {
                    "constraint_id": constraint_id,
                    "constraint_decision_id": str(
                        decision.get("constraint_decision_id") or ""
                    ).strip(),
                    "semantic_kind": str(slot.get("semantic_kind") or "").strip(),
                    "classification": str(slot.get("classification") or "").strip(),
                    "interpretation_status": status,
                    "risk": str(decision.get("risk") or "").strip(),
                }
            )
        elif primary_action in {
            "OMIT_CONFLICTING_PREFERENCE",
            "OMIT_UNSAFE_PREFERENCE_VALUE",
        }:
            deferred_preference_count += 1
            if primary_action == "OMIT_CONFLICTING_PREFERENCE":
                conflict_deferred_preference_count += 1
        elif primary_action != "RETAIN_UPSTREAM_SCOPE":
            raise L1CognitiveConsumptionError("L1 v3 goal constraint action is invalid")

    if set(decision_by_constraint_id) != {
        str(slot.get("constraint_id") or "").strip() for slot in slots
    }:
        raise L1CognitiveConsumptionError(
            "L1 v3 goal constraint decisions are incomplete"
        )
    blocking_ids = goal_frame.get("blocking_constraint_ids")
    if not isinstance(blocking_ids, Sequence) or isinstance(blocking_ids, (str, bytes)):
        raise L1CognitiveConsumptionError(
            "L1 v3 goal constraint blocking state is invalid"
        )
    return (
        sorted(directives, key=lambda row: row["constraint_id"]),
        sorted(escalations, key=lambda row: row["constraint_id"]),
        bool(blocking_ids),
        deferred_preference_count,
        conflict_deferred_preference_count,
    )


def build_l1_cognitive_consumer_advisory_unchecked(
    cognitive: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the canonical advisory body after the source plan is verified."""

    graph = _mapping(cognitive.get("atomic_requirement_graph"))
    requirements = _mapping_sequence(
        graph.get("requirements"), field="requirement graph"
    )
    mapped_slots = _atomic_requirement_slots(cognitive)
    mapped_slots = [
        slot for slot in mapped_slots if slot["coverage_status"] == "MAPPED"
    ]
    mapped = [row for row in requirements if row.get("coverage_status") == "MAPPED"]
    if {str(row["requirement_id"]) for row in mapped} != {
        str(slot["requirement_id"]) for slot in mapped_slots
    }:
        raise L1CognitiveConsumptionError(
            "L1 v3 mapped requirement slots do not match the source plan"
        )
    unresolved_critical_ids = sorted(
        str(row.get("requirement_id") or "")
        for row in requirements
        if row.get("coverage_status") != "MAPPED"
        and row.get("criticality") == "CRITICAL"
    )
    target_unit_ids = sorted(
        {
            str(unit_id)
            for row in mapped
            for unit_id in (row.get("target_unit_ids") or ())
            if str(unit_id).strip()
        }
    )
    mapped_requirement_type_counts: dict[str, int] = {}
    mapped_requirement_type_counts_by_target_unit: dict[str, dict[str, int]] = {}
    for row in mapped:
        requirement_type = str(row.get("requirement_type") or "").strip()
        if not requirement_type:
            raise L1CognitiveConsumptionError("L1 v3 requirement type is invalid")
        mapped_requirement_type_counts[requirement_type] = (
            mapped_requirement_type_counts.get(requirement_type, 0) + 1
        )
        for unit_id in row.get("target_unit_ids") or ():
            normalized_unit_id = str(unit_id).strip()
            if not normalized_unit_id:
                continue
            per_unit = mapped_requirement_type_counts_by_target_unit.setdefault(
                normalized_unit_id,
                {},
            )
            per_unit[requirement_type] = per_unit.get(requirement_type, 0) + 1
    (
        constraint_directives,
        constraint_escalations,
        goal_constraint_blocked,
        deferred_preference_count,
        conflict_deferred_preference_count,
    ) = _goal_constraint_advisory(cognitive)
    advisory = {
        "schema_version": L1_COGNITIVE_CONSUMER_ADVISORY_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "cognitive_plan_digest": str(cognitive["plan_digest"]),
        "planning_status": str(cognitive["planning_status"]),
        "mapped_requirement_count": len(mapped),
        "mapped_target_unit_ids": target_unit_ids,
        "mapped_requirement_type_counts": dict(
            sorted(mapped_requirement_type_counts.items())
        ),
        "mapped_requirement_type_counts_by_target_unit": {
            unit_id: dict(sorted(type_counts.items()))
            for unit_id, type_counts in sorted(
                mapped_requirement_type_counts_by_target_unit.items()
            )
        },
        "mapped_requirement_slots": mapped_slots,
        "unresolved_critical_requirement_ids": unresolved_critical_ids,
        "constraint_directives": constraint_directives,
        "constraint_escalations": constraint_escalations,
        "goal_constraint_blocked": goal_constraint_blocked,
        "deferred_preference_constraint_count": deferred_preference_count,
        "conflict_deferred_preference_constraint_count": conflict_deferred_preference_count,
        "critique_ledger_digest": str(
            _mapping(cognitive.get("critique_ledger")).get("ledger_digest") or ""
        ),
        "assertions": {
            "does_not_select_route": True,
            "does_not_create_evidence": True,
            "does_not_grant_prompt_authority": True,
            "does_not_grant_execution_authority": True,
            "raw_targeting_text_omitted": True,
            "atomic_requirement_identity_preserved": True,
            "goal_constraints_causally_consumed": True,
            "unsafe_constraint_text_omitted": True,
        },
    }
    advisory["advisory_digest"] = cognitive_consumer_advisory_digest(advisory)
    return advisory


def cognitive_revision_advisory_digest(advisory: Mapping[str, Any]) -> str:
    """Return the canonical revision-advisory digest excluding its self digest."""

    body = dict(advisory)
    body.pop("advisory_digest", None)
    return _sha256(body)


def _revision_target_unit_ids(
    cognitive_plan: Mapping[str, Any], revision: Mapping[str, Any]
) -> tuple[list[str], dict[str, int], dict[str, dict[str, int]]]:
    graph = _mapping(cognitive_plan.get("atomic_requirement_graph"))
    requirements = graph.get("requirements")
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        raise L1CognitiveConsumptionError("L1 v3 requirement graph is invalid")
    by_id = {
        str(row.get("requirement_id") or ""): row
        for row in requirements
        if isinstance(row, Mapping)
    }
    scope = revision.get("revision_scope_requirement_ids")
    if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)):
        raise L1CognitiveConsumptionError("L1 v3 revision scope is invalid")
    target_unit_ids: set[str] = set()
    type_counts: dict[str, int] = {}
    type_counts_by_target_unit: dict[str, dict[str, int]] = {}
    for requirement_id in scope:
        row = by_id.get(str(requirement_id) or "")
        if row is None:
            raise L1CognitiveConsumptionError("L1 v3 revision exceeds plan scope")
        requirement_type = str(row.get("requirement_type") or "").strip()
        if not requirement_type:
            raise L1CognitiveConsumptionError(
                "L1 v3 revision requirement type is invalid"
            )
        type_counts[requirement_type] = type_counts.get(requirement_type, 0) + 1
        for unit_id in row.get("target_unit_ids") or ():
            normalized_unit_id = str(unit_id).strip()
            if not normalized_unit_id:
                continue
            target_unit_ids.add(normalized_unit_id)
            per_unit = type_counts_by_target_unit.setdefault(normalized_unit_id, {})
            per_unit[requirement_type] = per_unit.get(requirement_type, 0) + 1
    return (
        sorted(target_unit_ids),
        dict(sorted(type_counts.items())),
        {
            unit_id: dict(sorted(per_unit.items()))
            for unit_id, per_unit in sorted(type_counts_by_target_unit.items())
        },
    )


def _revision_requirement_slots(
    cognitive_plan: Mapping[str, Any], revision: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Bind each bounded revision action back to one exact planning atom."""

    changes = _mapping_sequence(revision.get("changes"), field="revision changes")
    observed_outcomes = {
        str(change.get("requirement_id") or "").strip(): str(
            change.get("observed_outcome_code") or ""
        ).strip()
        for change in changes
    }
    if "" in observed_outcomes or any(
        not value for value in observed_outcomes.values()
    ):
        raise L1CognitiveConsumptionError("L1 v3 revision change identity is invalid")
    scope = {
        str(requirement_id).strip()
        for requirement_id in revision.get("revision_scope_requirement_ids") or ()
        if str(requirement_id).strip()
    }
    if scope != set(observed_outcomes):
        raise L1CognitiveConsumptionError("L1 v3 revision scope is invalid")
    return _atomic_requirement_slots(
        cognitive_plan,
        requirement_ids=scope,
        observed_outcomes=observed_outcomes,
    )


def build_l1_cognitive_revision_advisory(
    *,
    cognitive_plan: Mapping[str, Any],
    revision: Mapping[str, Any],
    c0_outcome_receipt_digest: str,
) -> dict[str, Any]:
    """Project one C0-bound L1 revision into PA-safe escalation directions.

    The revision itself must already have been built from the verified C0
    outcome receipt.  This projection deliberately exposes only semantic
    scope/counts: it cannot add target text, evidence, claims, or a retry.
    """

    cognitive = _verified_cognitive_plan(cognitive_plan)
    try:
        validate_l1_cognitive_revision_v3(revision, plan=cognitive)
    except L1CognitivePlanError as exc:
        raise L1CognitiveConsumptionError(
            "L1 v3 cognitive revision is invalid"
        ) from exc
    outcome_digest = str(c0_outcome_receipt_digest or "").strip()
    if not outcome_digest.startswith("sha256:") or len(outcome_digest) != 71:
        raise L1CognitiveConsumptionError("L1 v3 C0 outcome digest is invalid")
    if revision.get("c0_outcome_receipt_digest") != outcome_digest:
        raise L1CognitiveConsumptionError(
            "L1 v3 revision C0 outcome binding is invalid"
        )
    target_unit_ids, type_counts, type_counts_by_target_unit = (
        _revision_target_unit_ids(cognitive, revision)
    )
    affected_slots = _revision_requirement_slots(cognitive, revision)
    advisory = {
        "schema_version": L1_COGNITIVE_REVISION_ADVISORY_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "cognitive_plan_digest": str(cognitive["plan_digest"]),
        "revision_digest": str(revision["revision_digest"]),
        "c0_outcome_receipt_digest": outcome_digest,
        "revision_status": str(revision["status"]),
        "affected_requirement_count": len(revision["revision_scope_requirement_ids"]),
        "affected_target_unit_ids": target_unit_ids,
        "affected_requirement_type_counts": type_counts,
        "affected_requirement_type_counts_by_target_unit": type_counts_by_target_unit,
        "affected_requirement_slots": affected_slots,
        "assertions": {
            "does_not_select_route": True,
            "does_not_create_evidence": True,
            "does_not_grant_prompt_authority": True,
            "does_not_grant_execution_authority": True,
            "does_not_authorize_retry": True,
            "raw_targeting_text_omitted": True,
            "atomic_requirement_identity_preserved": True,
        },
    }
    advisory["advisory_digest"] = cognitive_revision_advisory_digest(advisory)
    validate_l1_cognitive_revision_advisory(
        advisory,
        cognitive_plan=cognitive,
        revision=revision,
    )
    return advisory


def validate_l1_cognitive_revision_advisory(
    advisory: Mapping[str, Any],
    *,
    cognitive_plan: Mapping[str, Any],
    revision: Mapping[str, Any],
) -> None:
    """Fail closed unless a PA revision projection matches its L1 sources."""

    cognitive = _verified_cognitive_plan(cognitive_plan)
    try:
        validate_l1_cognitive_revision_v3(revision, plan=cognitive)
    except L1CognitivePlanError as exc:
        raise L1CognitiveConsumptionError(
            "L1 v3 cognitive revision is invalid"
        ) from exc
    if not isinstance(advisory, Mapping):
        raise L1CognitiveConsumptionError("L1 v3 revision advisory is invalid")
    if advisory.get("schema_version") != L1_COGNITIVE_REVISION_ADVISORY_SCHEMA_VERSION:
        raise L1CognitiveConsumptionError("L1 v3 revision advisory schema is invalid")
    if (
        advisory.get("authority_class") != _AUTHORITY_CLASS
        or advisory.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveConsumptionError(
            "L1 v3 revision advisory authority is invalid"
        )
    if advisory.get("advisory_digest") != cognitive_revision_advisory_digest(advisory):
        raise L1CognitiveConsumptionError("L1 v3 revision advisory digest is invalid")
    outcome_digest = str(advisory.get("c0_outcome_receipt_digest") or "").strip()
    if not outcome_digest.startswith("sha256:") or len(outcome_digest) != 71:
        raise L1CognitiveConsumptionError("L1 v3 C0 outcome digest is invalid")
    if revision.get("c0_outcome_receipt_digest") != outcome_digest:
        raise L1CognitiveConsumptionError(
            "L1 v3 revision C0 outcome binding is invalid"
        )
    expected = build_l1_cognitive_revision_advisory_unchecked(
        cognitive_plan=cognitive,
        revision=revision,
        c0_outcome_receipt_digest=outcome_digest,
    )
    if dict(advisory) != expected:
        raise L1CognitiveConsumptionError(
            "L1 v3 revision advisory does not match sources"
        )


def build_l1_cognitive_revision_advisory_unchecked(
    *,
    cognitive_plan: Mapping[str, Any],
    revision: Mapping[str, Any],
    c0_outcome_receipt_digest: str,
) -> dict[str, Any]:
    """Build the expected revision advisory after all inputs are validated."""

    target_unit_ids, type_counts, type_counts_by_target_unit = (
        _revision_target_unit_ids(cognitive_plan, revision)
    )
    affected_slots = _revision_requirement_slots(cognitive_plan, revision)
    advisory = {
        "schema_version": L1_COGNITIVE_REVISION_ADVISORY_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "cognitive_plan_digest": str(cognitive_plan["plan_digest"]),
        "revision_digest": str(revision["revision_digest"]),
        "c0_outcome_receipt_digest": c0_outcome_receipt_digest,
        "revision_status": str(revision["status"]),
        "affected_requirement_count": len(revision["revision_scope_requirement_ids"]),
        "affected_target_unit_ids": target_unit_ids,
        "affected_requirement_type_counts": type_counts,
        "affected_requirement_type_counts_by_target_unit": type_counts_by_target_unit,
        "affected_requirement_slots": affected_slots,
        "assertions": {
            "does_not_select_route": True,
            "does_not_create_evidence": True,
            "does_not_grant_prompt_authority": True,
            "does_not_grant_execution_authority": True,
            "does_not_authorize_retry": True,
            "raw_targeting_text_omitted": True,
            "atomic_requirement_identity_preserved": True,
        },
    }
    advisory["advisory_digest"] = cognitive_revision_advisory_digest(advisory)
    return advisory


def cognitive_revision_advisory_prompt_lines(
    advisory: Mapping[str, Any] | None,
    *,
    section_id: str = "",
) -> tuple[str, ...]:
    """Return atom-specific C0-outcome directions for an affected section."""

    if advisory is None or advisory["revision_status"] != "PROPOSED":
        return ()
    slots = _slots_for_section(
        _mapping_sequence(
            advisory.get("affected_requirement_slots"),
            field="revision advisory requirement slots",
        ),
        section_id=section_id,
    )
    if not slots:
        return ()
    gap_requirements = {
        row["requirement_id"]: row
        for row in cognitive_revision_gap_requirements(advisory, section_id=section_id)
    }
    lines = [
        "L1 cognitive C0 revision: process every listed atomic outcome below; "
        "these are source-bound planning constraints, not candidate evidence.",
    ]
    for slot in slots:
        outcome_code = str(slot.get("observed_outcome_code") or "")
        requirement_id = str(slot.get("requirement_id") or "")
        required = gap_requirements.get(requirement_id)
        if outcome_code not in _C0_FAILURE_OUTCOMES or required is None:
            raise L1CognitiveConsumptionError(
                "L1 v3 revision advisory lacks a required C0 gap disposition"
            )
        lines.append(
            "L1 cognitive C0 atom: "
            f"id={requirement_id}; outcome={outcome_code}; "
            f"type={slot['requirement_type']}; modality={slot['modality']}; "
            f"criticality={slot['criticality']}; qualifiers={_format_qualifiers(slot)}; "
            f"required_gap_tag={required['gap_tag']}."
        )
    debloat = os.environ.get("APPS_RG_L1_PROMPT_DEBLOAT", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    if debloat:
        lines.append(
            "L1 cognitive C0 revision safety: do not compensate for a C0 gap with an "
            "unsupported candidate claim or present the atom as satisfied."
        )
    else:
        lines.extend(
            (
                "L1 cognitive C0 revision action: add every required_gap_tag above as a "
                "separate non-display string in gap_notes, and add the matching "
                "L1_COGNITIVE_ATOM:<id>:GAP audit string in change_log.",
                "L1 cognitive C0 revision safety: do not compensate for a C0 gap with an "
                "unsupported candidate claim or present the atom as satisfied.",
            )
        )
    return tuple(lines)


def cognitive_advisory_prompt_lines(
    advisory: Mapping[str, Any] | None,
    *,
    section_id: str = "",
) -> tuple[str, ...]:
    """Return PA-authored safe directives derived from the advisory projection.

    Atomic requirement directives are emitted only for a section family
    selected by the L1 target unit.  Whole-output goal constraints are emitted
    for every section because they govern the artifact rather than one atom.
    """

    if advisory is None:
        return ()
    constraint_directives = _mapping_sequence(
        advisory.get("constraint_directives"), field="constraint directives"
    )
    constraint_escalations = _mapping_sequence(
        advisory.get("constraint_escalations"), field="constraint escalations"
    )
    goal_constraint_blocked = advisory.get("goal_constraint_blocked")
    deferred_preference_count = advisory.get("deferred_preference_constraint_count")
    conflict_deferred_preference_count = advisory.get(
        "conflict_deferred_preference_constraint_count"
    )
    if (
        not isinstance(goal_constraint_blocked, bool)
        or not isinstance(deferred_preference_count, int)
        or deferred_preference_count < 0
        or not isinstance(conflict_deferred_preference_count, int)
        or conflict_deferred_preference_count < 0
        or conflict_deferred_preference_count > deferred_preference_count
    ):
        raise L1CognitiveConsumptionError("L1 v3 goal constraint advisory is invalid")

    lines: list[str] = []
    if constraint_directives:
        lines.append(
            "L1 cognitive goal constraints: preserve every closed-vocabulary "
            "directive below. These are source-bound artifact constraints, not "
            "candidate evidence; raw user constraint keys and values are deliberately "
            "omitted."
        )
    for directive in constraint_directives:
        if set(directive) != {
            "constraint_id",
            "constraint_decision_id",
            "semantic_kind",
            "polarity",
            "scope",
            "directive_code",
            "numeric_limit",
        }:
            raise L1CognitiveConsumptionError(
                "L1 v3 constraint directive shape is invalid"
            )
        constraint_id = str(directive.get("constraint_id") or "").strip()
        decision_id = str(directive.get("constraint_decision_id") or "").strip()
        semantic_kind = str(directive.get("semantic_kind") or "").strip()
        polarity = str(directive.get("polarity") or "").strip()
        scope = str(directive.get("scope") or "").strip()
        directive_code = str(directive.get("directive_code") or "").strip()
        if not all(
            (
                constraint_id,
                decision_id,
                semantic_kind,
                polarity,
                scope,
                directive_code,
            )
        ):
            raise L1CognitiveConsumptionError("L1 v3 constraint directive is invalid")
        numeric_limit = directive.get("numeric_limit")
        numeric_suffix = ""
        if numeric_limit is not None:
            if not isinstance(numeric_limit, Mapping) or set(numeric_limit) != {
                "comparison",
                "quantity",
                "unit",
            }:
                raise L1CognitiveConsumptionError(
                    "L1 v3 constraint numeric limit is invalid"
                )
            comparison = str(numeric_limit.get("comparison") or "").strip()
            quantity = numeric_limit.get("quantity")
            unit = str(numeric_limit.get("unit") or "").strip()
            if (
                comparison not in {"EXACT", "MAXIMUM", "MINIMUM"}
                or not isinstance(quantity, int)
                or quantity < 0
                or not unit
            ):
                raise L1CognitiveConsumptionError(
                    "L1 v3 constraint numeric limit is incoherent"
                )
            numeric_suffix = f"; numeric_limit={comparison}:{quantity}:{unit}"
        lines.append(
            "L1 cognitive goal constraint: "
            f"id={constraint_id}; kind={semantic_kind}; action={polarity}; "
            f"scope={scope}; directive={directive_code}; "
            f"decision_ref={decision_id}{numeric_suffix}."
        )

    if constraint_escalations:
        for escalation in constraint_escalations:
            if set(escalation) != {
                "constraint_id",
                "constraint_decision_id",
                "semantic_kind",
                "classification",
                "interpretation_status",
                "risk",
            }:
                raise L1CognitiveConsumptionError(
                    "L1 v3 constraint escalation shape is invalid"
                )
            if not all(
                str(escalation.get(field) or "").strip()
                for field in (
                    "constraint_id",
                    "constraint_decision_id",
                    "semantic_kind",
                    "classification",
                    "interpretation_status",
                    "risk",
                )
            ):
                raise L1CognitiveConsumptionError(
                    "L1 v3 constraint escalation is invalid"
                )
        lines.append(
            "L1 cognitive goal gate: unresolved hard or conflicting constraint(s) "
            "require governed U0 resolution before treating the user goal as "
            "satisfied; do not substitute an invented interpretation."
        )
        for escalation in constraint_escalations:
            lines.append(
                "L1 cognitive goal escalation: "
                f"id={escalation['constraint_id']}; "
                f"kind={escalation['semantic_kind']}; "
                f"classification={escalation['classification']}; "
                f"status={escalation['interpretation_status']}; "
                f"risk={escalation['risk']}; "
                f"decision_ref={escalation['constraint_decision_id']}."
            )
    if goal_constraint_blocked and not constraint_escalations:
        raise L1CognitiveConsumptionError(
            "L1 v3 blocking goal constraint lacks an escalation"
        )

    slots = _slots_for_section(
        _mapping_sequence(
            advisory.get("mapped_requirement_slots"),
            field="advisory requirement slots",
        ),
        section_id=section_id,
    )
    if not lines and not slots:
        return ()
    debloat = os.environ.get("APPS_RG_L1_PROMPT_DEBLOAT", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )
    if debloat:
        if slots:
            lines.append(
                "L1 target requirements: preserve source-grounded alignment for listed "
                "requirements below; C0 remains the sole evidence authority."
            )
        for slot in slots:
            qual = _format_qualifiers(slot)
            qual_str = f"; qualifiers={qual}" if qual else ""
            lines.append(
                f"L1 target requirement: id={slot['requirement_id']}; type={slot['requirement_type']}; "
                f"modality={slot['modality']}; criticality={slot['criticality']}{qual_str}."
            )
    else:
        if slots:
            lines.append(
                "L1 cognitive atomic coverage: make one distinct source-grounded content "
                "decision for every listed atom. The atom ledger is planning context only; "
                "C0 remains the sole evidence authority."
            )
        for slot in slots:
            lines.append(
                "L1 cognitive atom: "
                f"id={slot['requirement_id']}; type={slot['requirement_type']}; "
                f"modality={slot['modality']}; criticality={slot['criticality']}; "
                f"qualifiers={_format_qualifiers(slot)}; "
                f"qualifier_scope={slot['qualifier_scope']}; "
                f"decomposition={slot['decomposition_mode']}; "
                f"relations={_format_relation_context(slot)}; "
                f"planned_decision={slot['planned_decision']}; "
                f"feasibility={slot['selected_feasibility_status']}; "
                f"preconditions={','.join(slot['selected_precondition_codes'])}; "
                f"alternative={'available' if slot['alternative_option_id'] else 'none'}; "
                f"risk={slot['decision_risk']}; "
                f"covered_audit_tag=L1_COGNITIVE_ATOM:{slot['requirement_id']}:COVERED."
            )
        if slots:
            lines.extend(
                (
                    "L1 cognitive audit action: add one non-display change_log string per "
                    "listed atom: L1_COGNITIVE_ATOM:<id>:COVERED only when a distinct "
                    "allowed-source output element covers it, otherwise "
                    "L1_COGNITIVE_ATOM:<id>:GAP.",
                    "L1 cognitive distinctness: do not reuse one generic output element to "
                    "represent multiple atoms; record a gap rather than inventing support.",
                    "L1 cognitive scope guard: preserve each atom's qualifier scope; a "
                    "SHARED_PARENT qualifier applies to every linked atom, but one atom's "
                    "coverage never proves another atom.",
                    "L1 cognitive relation guard: OR, NOT, and EXCEPTION requirements stay "
                    "escalated until their named resolver handles the relation; never turn "
                    "them into generic conjunctive coverage.",
                )
            )
    lines.append(
        "L1 cognitive safety: C0 remains the evidence authority; do not turn "
        "planning intent into a candidate claim."
    )
    unresolved = list(advisory["unresolved_critical_requirement_ids"])
    if unresolved:
        lines.append(
            "L1 cognitive escalation: preserve governed escalation for "
            f"{len(unresolved)} unresolved critical requirement(s); do not silently "
            "claim they were satisfied."
        )
    if deferred_preference_count:
        if conflict_deferred_preference_count:
            lines.append(
                "L1 cognitive precedence: "
                f"{conflict_deferred_preference_count} non-binding preference(s) conflicted "
                "with a hard constraint or another preference and were withheld; an "
                "explicit hard user constraint always takes precedence."
            )
        lines.append(
            "L1 cognitive preference note: "
            f"{deferred_preference_count} unsafe preference value(s) were withheld; "
            "a governed U0 clarification is required if any is mandatory."
        )
    return tuple(lines)


__all__ = [
    "L1CognitiveConsumptionError",
    "L1_COGNITIVE_CONSUMER_ADVISORY_SCHEMA_VERSION",
    "L1_COGNITIVE_REVISION_ADVISORY_SCHEMA_VERSION",
    "build_l1_cognitive_consumer_advisory",
    "build_l1_cognitive_consumer_advisory_from_cognitive_plan",
    "build_l1_cognitive_revision_advisory",
    "cognitive_advisory_prompt_lines",
    "cognitive_consumer_advisory_digest",
    "cognitive_revision_gap_requirements",
    "cognitive_revision_advisory_digest",
    "cognitive_revision_advisory_prompt_lines",
    "extract_l1_cognitive_plan",
    "validate_l1_cognitive_consumer_advisory",
    "validate_l1_cognitive_consumer_advisory_from_cognitive_plan",
    "validate_l1_cognitive_revision_advisory",
]
