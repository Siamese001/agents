"""Paired v2-control/v3-treatment protocol for L1 cognitive outcome evidence.

This module records technical execution evidence only.  It makes every paired
attempt auditable, including failures, but never turns a runner receipt into a
human utility decision, a protected-holdout result, or a promotion decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_OUTCOME_PROTOCOL_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_outcome_protocol.v4"
)
L1_COGNITIVE_PAIRED_SHADOW_RECEIPT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_paired_shadow_receipt.v1"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_PROTOCOL_PATH: Final[Path] = (
    Path(__file__).resolve().parent
    / "contracts"
    / "l1_cognitive_outcome_protocol.v4.yaml"
)
_TREATMENT_STATUSES: Final[frozenset[str]] = frozenset({"PASS", "FAIL", "BLOCKED"})
_HUMAN_JUDGMENT_KEYS: Final[frozenset[str]] = frozenset(
    {"grade", "label", "score", "verdict", "adjudication", "approval"}
)


class L1CognitiveOutcomeProtocolError(ValueError):
    """Raised when paired outcome evidence is incomplete or untrustworthy."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def paired_shadow_receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable digest excluding the receipt's self-reference."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitiveOutcomeProtocolError(f"{field} must be a mapping")
    return dict(value)


def _required_string(value: Any, *, field: str, digest: bool = False) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitiveOutcomeProtocolError(f"{field} is required")
    if digest and (
        not normalized.startswith("sha256:") or len(normalized) != len("sha256:") + 64
    ):
        raise L1CognitiveOutcomeProtocolError(f"{field} must be a SHA-256 digest")
    return normalized


def _safe_ref(value: Any, *, field: str) -> str:
    ref = _required_string(value, field=field).replace("\\", "/")
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        raise L1CognitiveOutcomeProtocolError(f"{field} must be a relative reference")
    return ref


def _contains_human_judgment(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _HUMAN_JUDGMENT_KEYS or _contains_human_judgment(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_human_judgment(item) for item in value)
    return False


def protocol_path() -> Path:
    """Return the tracked paired-experiment protocol path."""

    return _PROTOCOL_PATH


def _validate_protocol(protocol: Mapping[str, Any]) -> None:
    if protocol.get("schema_version") != L1_COGNITIVE_OUTCOME_PROTOCOL_SCHEMA_VERSION:
        raise L1CognitiveOutcomeProtocolError("outcome protocol schema is invalid")
    if protocol.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveOutcomeProtocolError("outcome protocol scope is invalid")
    if protocol.get("experiment_id") != "apps_rg_l1_cognitive_v3_vs_v2":
        raise L1CognitiveOutcomeProtocolError("outcome protocol experiment is invalid")
    control = _mapping(protocol.get("control"), field="control")
    candidate = _mapping(protocol.get("candidate"), field="candidate")
    if control.get("treatment_id") != "l1_v2_control":
        raise L1CognitiveOutcomeProtocolError("control treatment is invalid")
    if candidate.get("treatment_id") != "l1_cognitive_v3":
        raise L1CognitiveOutcomeProtocolError("candidate treatment is invalid")
    if control.get("required_lineage") != [
        "apps_rg_planning_v2_capsule",
        "apps_rg_l1_cognitive_treatment_execution",
    ]:
        raise L1CognitiveOutcomeProtocolError("control lineage is invalid")
    if candidate.get("required_lineage") != [
        "apps_rg_cognitive_v3_plan",
        "apps_rg_l1_cognitive_consumer_advisory",
        "apps_rg_l1_cognitive_c0_outcome",
        "apps_rg_l1_cognitive_revision",
        "apps_rg_l1_cognitive_treatment_execution",
    ]:
        raise L1CognitiveOutcomeProtocolError("candidate lineage is invalid")
    paired = _mapping(protocol.get("paired_execution"), field="paired_execution")
    if any(
        paired.get(field) is not True
        for field in (
            "frozen_input_required",
            "provider_model_configuration_matched",
            "tool_configuration_matched",
            "candidate_c0_outcome_before_pa_required",
            "run_bound_input_configuration_required",
            "preserve_all_attempts_in_denominator",
            "automatic_promotion_forbidden",
        )
    ):
        raise L1CognitiveOutcomeProtocolError("paired execution controls are invalid")
    if protocol.get("outcomes") != {
        "P1": "blind_finished_resume_utility_delta",
        "P2": "grounded_decision_ready_completion_rate",
    }:
        raise L1CognitiveOutcomeProtocolError("paired outcome definitions are invalid")
    if protocol.get("guardrails") != [
        "unsupported_material_claim_count",
        "critical_binding_error_count",
        "critical_run_divergence_count",
    ]:
        raise L1CognitiveOutcomeProtocolError(
            "paired guardrail definitions are invalid"
        )
    review = _mapping(protocol.get("human_review"), field="human_review")
    if review != {
        "blinded": True,
        "independent_primary_reviewers_per_pair": 2,
        "independent_adjudicators_per_pair": 1,
        "human_labels_may_not_be_generated": True,
        "variant_assessment_fields": [
            "finished_resume_utility_score",
            "grounded_decision_ready",
            "unsupported_material_claim_count",
        ],
        "adjudicated_measurements_required": True,
    }:
        raise L1CognitiveOutcomeProtocolError("paired human review protocol is invalid")
    capability_review = _mapping(
        protocol.get("capability_review"), field="capability_review"
    )
    if capability_review != {
        "source_bound": True,
        "independent_primary_reviewers_per_pair": 2,
        "independent_adjudicators_per_pair": 1,
        "score_range": [0, 2],
        "dimensions": [
            "goal_constraint_fidelity",
            "atomic_requirement_fidelity",
            "feasibility_plan_coherence",
            "critique_quality",
            "revision_quality",
        ],
        "complete_protected_holdout_cohort_required": True,
        "opaque_case_bindings_external_human_attestation_required": True,
        "human_labels_may_not_be_generated": True,
    }:
        raise L1CognitiveOutcomeProtocolError("cognitive capability review is invalid")
    if protocol.get("protected_holdout_commitment_ref") != (
        "apps_rg/evals/fixtures/l1_v2_protected_holdout_commitment.v1.json"
    ):
        raise L1CognitiveOutcomeProtocolError("paired holdout commitment is invalid")


def load_l1_cognitive_outcome_protocol(path: Path | None = None) -> dict[str, Any]:
    """Load the versioned, non-promoting L1 outcome experiment protocol."""

    source = Path(path or _PROTOCOL_PATH)
    try:
        loaded = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise L1CognitiveOutcomeProtocolError("outcome protocol is unreadable") from exc
    protocol = _mapping(loaded, field="outcome protocol")
    _validate_protocol(protocol)
    return protocol


def _normalize_arm(value: Any, *, arm: str) -> dict[str, Any]:
    row = _mapping(value, field=f"{arm} arm")
    required = {
        "run_ref": _safe_ref(row.get("run_ref"), field=f"{arm}.run_ref"),
        "run_id": _required_string(row.get("run_id"), field=f"{arm}.run_id"),
        "compiled_prompt_digest": _required_string(
            row.get("compiled_prompt_digest"),
            field=f"{arm}.compiled_prompt_digest",
            digest=True,
        ),
        "output_digest": _required_string(
            row.get("output_digest"), field=f"{arm}.output_digest", digest=True
        ),
        "completion_status": _required_string(
            row.get("completion_status"), field=f"{arm}.completion_status"
        ),
    }
    required["l1_cognitive_treatment_execution_digest"] = _required_string(
        row.get("l1_cognitive_treatment_execution_digest"),
        field=f"{arm}.l1_cognitive_treatment_execution_digest",
        digest=True,
    )
    if required["completion_status"] not in _TREATMENT_STATUSES:
        raise L1CognitiveOutcomeProtocolError(f"{arm}.completion_status is invalid")
    if arm == "control":
        required["l1_v2_capsule_digest"] = _required_string(
            row.get("l1_v2_capsule_digest"),
            field="control.l1_v2_capsule_digest",
            digest=True,
        )
    else:
        required["l1_cognitive_plan_digest"] = _required_string(
            row.get("l1_cognitive_plan_digest"),
            field="candidate.l1_cognitive_plan_digest",
            digest=True,
        )
        required["l1_cognitive_advisory_digest"] = _required_string(
            row.get("l1_cognitive_advisory_digest"),
            field="candidate.l1_cognitive_advisory_digest",
            digest=True,
        )
        required["c0_outcome_set_digest"] = _required_string(
            row.get("c0_outcome_set_digest"),
            field="candidate.c0_outcome_set_digest",
            digest=True,
        )
        required["l1_cognitive_revision_set_digest"] = _required_string(
            row.get("l1_cognitive_revision_set_digest"),
            field="candidate.l1_cognitive_revision_set_digest",
            digest=True,
        )
    return required


def _normalized_pairs(pairs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)) or not pairs:
        raise L1CognitiveOutcomeProtocolError("paired shadow attempts are required")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in pairs:
        row = _mapping(raw, field="paired shadow attempt")
        if _contains_human_judgment(row):
            raise L1CognitiveOutcomeProtocolError(
                "paired shadow receipt cannot carry human judgment"
            )
        pair_id = _required_string(row.get("pair_id"), field="pair_id")
        if pair_id in seen:
            raise L1CognitiveOutcomeProtocolError(
                "paired shadow pair IDs must be unique"
            )
        seen.add(pair_id)
        control = _normalize_arm(row.get("control"), arm="control")
        candidate = _normalize_arm(row.get("candidate"), arm="candidate")
        out.append(
            {
                "pair_id": pair_id,
                "frozen_input_digest": _required_string(
                    row.get("frozen_input_digest"),
                    field="frozen_input_digest",
                    digest=True,
                ),
                "provider_model_config_digest": _required_string(
                    row.get("provider_model_config_digest"),
                    field="provider_model_config_digest",
                    digest=True,
                ),
                "tool_config_digest": _required_string(
                    row.get("tool_config_digest"),
                    field="tool_config_digest",
                    digest=True,
                ),
                "control": control,
                "candidate": candidate,
            }
        )
    return sorted(out, key=lambda row: str(row["pair_id"]))


def _receipt_body(
    protocol: Mapping[str, Any], pairs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    _validate_protocol(protocol)
    normalized = _normalized_pairs(pairs)
    completed = sum(
        1
        for row in normalized
        if row["control"]["completion_status"] == "PASS"
        and row["candidate"]["completion_status"] == "PASS"
    )
    return {
        "schema_version": L1_COGNITIVE_PAIRED_SHADOW_RECEIPT_SCHEMA_VERSION,
        "authority_class": "TECHNICAL_PAIRED_EXECUTION_ONLY",
        "app_scope": _APP_SCOPE,
        "experiment": {
            "experiment_id": str(protocol["experiment_id"]),
            "protocol_digest": _sha256(protocol),
            "control_treatment_id": str(protocol["control"]["treatment_id"]),
            "candidate_treatment_id": str(protocol["candidate"]["treatment_id"]),
        },
        "pairs": normalized,
        "summary": {
            "attempt_count": len(normalized),
            "completed_pair_count": completed,
            "all_attempts_preserved": True,
            "candidate_c0_outcome_before_pa_required": True,
            "run_bound_input_configuration_required": True,
        },
        "outcomes": {
            "P1": {
                "status": "NOT_MEASURED",
                "reason_codes": ["BLINDED_HUMAN_REVIEW_REQUIRED"],
            },
            "P2": {
                "status": "NOT_MEASURED",
                "reason_codes": ["FROZEN_DENOMINATOR_AND_HUMAN_REVIEW_REQUIRED"],
            },
        },
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
            "automatic_promotion": False,
        },
    }


def build_l1_cognitive_paired_shadow_receipt(
    *, protocol: Mapping[str, Any], pairs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Record source-bound paired attempts while preserving human outcome gates."""

    receipt = _receipt_body(protocol, pairs)
    receipt["receipt_digest"] = paired_shadow_receipt_digest(receipt)
    validate_l1_cognitive_paired_shadow_receipt(
        receipt,
        protocol=protocol,
        pairs=pairs,
    )
    return receipt


def validate_l1_cognitive_paired_shadow_receipt(
    receipt: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed unless a technical receipt exactly records the supplied pairs."""

    if not isinstance(receipt, Mapping):
        raise L1CognitiveOutcomeProtocolError("paired shadow receipt is invalid")
    if (
        receipt.get("schema_version")
        != L1_COGNITIVE_PAIRED_SHADOW_RECEIPT_SCHEMA_VERSION
    ):
        raise L1CognitiveOutcomeProtocolError("paired shadow receipt schema is invalid")
    if receipt.get("authority_class") != "TECHNICAL_PAIRED_EXECUTION_ONLY":
        raise L1CognitiveOutcomeProtocolError(
            "paired shadow receipt authority is invalid"
        )
    if receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitiveOutcomeProtocolError("paired shadow receipt scope is invalid")
    if receipt.get("receipt_digest") != paired_shadow_receipt_digest(receipt):
        raise L1CognitiveOutcomeProtocolError("paired shadow receipt digest is invalid")
    if _contains_human_judgment(receipt):
        raise L1CognitiveOutcomeProtocolError(
            "paired shadow receipt cannot carry human judgment"
        )
    expected = _receipt_body(protocol, pairs)
    actual = dict(receipt)
    actual.pop("receipt_digest", None)
    if actual != expected:
        raise L1CognitiveOutcomeProtocolError(
            "paired shadow receipt does not match supplied attempts"
        )


def write_l1_cognitive_paired_shadow_receipt(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    protocol: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
) -> Path:
    """Validate and write a technical receipt at one caller-owned path."""

    validate_l1_cognitive_paired_shadow_receipt(
        receipt,
        protocol=protocol,
        pairs=pairs,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1CognitiveOutcomeProtocolError",
    "L1_COGNITIVE_OUTCOME_PROTOCOL_SCHEMA_VERSION",
    "L1_COGNITIVE_PAIRED_SHADOW_RECEIPT_SCHEMA_VERSION",
    "build_l1_cognitive_paired_shadow_receipt",
    "load_l1_cognitive_outcome_protocol",
    "paired_shadow_receipt_digest",
    "protocol_path",
    "validate_l1_cognitive_paired_shadow_receipt",
    "write_l1_cognitive_paired_shadow_receipt",
]
