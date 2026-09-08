"""Tests for Apps RG-local assembly of captured L1 paired cohorts."""

from __future__ import annotations

import copy
import hashlib

import pytest

from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
)
from apps_rg.evals.l1_cognitive_paired_cohort import (
    L1CognitivePairedCohortError,
    L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION,
    assemble_l1_cognitive_paired_cohort,
    validate_l1_cognitive_paired_cohort_manifest,
)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pair(index: int) -> dict[str, object]:
    token = f"{index:03d}"
    return {
        "pair_id": f"pair-{token}",
        "frozen_input_digest": _digest(f"input-{token}"),
        "provider_model_config_digest": _digest("provider-config"),
        "tool_config_digest": _digest("tool-config"),
        "control": {
            "run_ref": f"control-{token}",
            "run_id": f"control-{token}",
            "l1_v2_capsule_digest": _digest(f"control-capsule-{token}"),
            "l1_cognitive_treatment_execution_digest": _digest(
                f"control-execution-{token}"
            ),
            "compiled_prompt_digest": _digest(f"control-prompt-{token}"),
            "output_digest": _digest(f"control-output-{token}"),
            "completion_status": "PASS",
        },
        "candidate": {
            "run_ref": f"candidate-{token}",
            "run_id": f"candidate-{token}",
            "l1_cognitive_plan_digest": _digest(f"candidate-plan-{token}"),
            "l1_cognitive_advisory_digest": _digest(f"candidate-advisory-{token}"),
            "c0_outcome_set_digest": _digest(f"c0-{token}"),
            "l1_cognitive_revision_set_digest": _digest(f"candidate-revision-{token}"),
            "l1_cognitive_treatment_execution_digest": _digest(
                f"candidate-execution-{token}"
            ),
            "compiled_prompt_digest": _digest(f"candidate-prompt-{token}"),
            "output_digest": _digest(f"candidate-output-{token}"),
            "completion_status": "PASS",
        },
    }


def _source_receipts() -> list[dict[str, object]]:
    protocol = load_l1_cognitive_outcome_protocol()
    return [
        build_l1_cognitive_paired_shadow_receipt(protocol=protocol, pairs=[_pair(i)])
        for i in range(1, 4)
    ]


def test_assemble_paired_cohort_preserves_each_one_pair_capture() -> None:
    protocol = load_l1_cognitive_outcome_protocol()
    combined, manifest = assemble_l1_cognitive_paired_cohort(
        protocol=protocol,
        source_paired_receipts=_source_receipts(),
    )

    assert manifest["schema_version"] == (
        L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION
    )
    assert manifest["pair_ids"] == ["pair-001", "pair-002", "pair-003"]
    assert combined["summary"]["attempt_count"] == 3
    assert combined["summary"]["completed_pair_count"] == 3
    validate_l1_cognitive_paired_cohort_manifest(
        manifest,
        paired_receipt=combined,
        protocol=protocol,
    )


def test_paired_cohort_rejects_duplicate_or_substituted_capture_evidence() -> None:
    protocol = load_l1_cognitive_outcome_protocol()
    sources = _source_receipts()
    with pytest.raises(L1CognitivePairedCohortError, match="digests must be unique"):
        assemble_l1_cognitive_paired_cohort(
            protocol=protocol,
            source_paired_receipts=[sources[0], sources[0]],
        )

    combined, manifest = assemble_l1_cognitive_paired_cohort(
        protocol=protocol,
        source_paired_receipts=sources,
    )
    substituted = copy.deepcopy(combined)
    pairs = substituted["pairs"]
    assert isinstance(pairs, list)
    pairs[0]["candidate"]["output_digest"] = _digest("substituted-output")
    with pytest.raises(L1CognitivePairedCohortError, match="does not match"):
        validate_l1_cognitive_paired_cohort_manifest(
            manifest,
            paired_receipt=substituted,
            protocol=protocol,
        )
