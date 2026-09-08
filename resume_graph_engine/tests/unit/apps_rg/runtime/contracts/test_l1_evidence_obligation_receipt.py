"""Tests for the C0-owned L1 v2 obligation reconciliation sidecar."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    L1EvidenceObligationReceiptError,
    build_l1_evidence_obligation_receipt,
    receipt_digest,
    validate_l1_evidence_obligation_receipt,
    write_l1_evidence_obligation_receipt,
)


def _payload() -> dict[str, Any]:
    return {
        "non_product_certified": True,
        "target_company": "Acme Corp",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": (
            "Requirements\n"
            "- Must have 10+ years of AI platform leadership.\n"
            "- Bachelor's degree in Computer Science."
        ),
        "source_resume_text": "Built governed AI infrastructure.",
        "generation_mode": "strategic_tailor",
        "task_spec": {
            "generation_mode": "strategic_tailor",
            "task_class": "resume_generation",
        },
        "query_spec": {"jd_hash": "a" * 64, "resume_hash": "b" * 64},
        "support_expectation": {},
        "output_expectation": {},
        "profile_manifest": {
            "l1_planning_profile_ref": l1_planning_profile_ref(),
            "l1_planning_profile_digest": l1_planning_profile_digest(
                allow_missing=False
            ),
            "manifest_digest": "f" * 64,
        },
    }


def _capsule() -> Mapping[str, Any]:
    return build_apps_rg_l1_planning_capsule_v2(
        app_payload=_payload(),
        request_id="req-w2",
        run_id="run-w2",
        trace_id="trace-w2",
        replay_key="replay-w2",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _receipt(
    capsule: Mapping[str, Any], evidence_items: tuple[Any, ...] = ()
) -> dict[str, Any]:
    return build_l1_evidence_obligation_receipt(
        capsule=capsule,
        request_id="req-w2",
        run_id="run-w2",
        trace_id="trace-w2",
        final_evidence_digest="sha256:" + "c" * 64,
        evidence_items=evidence_items,
    )


def _mutable(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def test_receipt_has_exact_coverage_and_never_promotes_jd_targeting() -> None:
    capsule = _capsule()
    receipt = _receipt(
        capsule,
        (
            {
                "source": "retrieval_result",
                "source_type": "fact_vectors",
                "content_digest": "sha256:" + "1" * 64,
            },
            {
                "source": "jd_payload",
                "source_type": "app_payload_inline",
                "content_digest": "sha256:" + "2" * 64,
                "l1_obligation_ids": ["not-an-obligation"],
                "l1_obligation_disposition": "SUPPORTED",
            },
        ),
    )

    ledger = capsule["evidence_obligation_ledger"]
    assert receipt["coverage"]["planned_obligation_count"] == len(ledger["obligations"])
    assert receipt["coverage"]["observed_disposition_count"] == len(
        ledger["obligations"]
    )
    assert all(
        entry["support_disposition"] == "INSUFFICIENT" and entry["evidence_refs"] == []
        for entry in receipt["obligation_dispositions"]
    )
    assert receipt["coverage"]["jd_targeting_used_as_candidate_evidence"] is False
    assert "Bachelor's degree in Computer Science" not in json.dumps(receipt)
    validate_l1_evidence_obligation_receipt(receipt, capsule=capsule)


def test_receipt_dispositions_require_evidence_bound_to_each_obligation() -> None:
    capsule = _capsule()
    obligations = capsule["evidence_obligation_ledger"]["obligations"]
    supported_id = obligations[0]["obligation_id"]
    contradicted_id = obligations[1]["obligation_id"]

    receipt = _receipt(
        capsule,
        (
            {
                "source": "retrieval_result",
                "source_type": "fact_vectors",
                "content_digest": "sha256:" + "3" * 64,
                "l1_obligation_ids": [supported_id],
                "l1_obligation_disposition": "SUPPORTED",
            },
            {
                "source": "retrieval_result",
                "source_type": "fact_vectors",
                "content_digest": "sha256:" + "4" * 64,
                "l1_obligation_ids": [contradicted_id],
                "contradiction_status": "CONTRADICTED",
            },
        ),
    )

    by_id = {
        entry["obligation_id"]: entry for entry in receipt["obligation_dispositions"]
    }
    assert by_id[supported_id]["support_disposition"] == "SUPPORTED"
    assert by_id[contradicted_id]["support_disposition"] == "CONTRADICTED"
    assert by_id[supported_id]["evidence_refs"]
    assert by_id[contradicted_id]["evidence_refs"]


@pytest.mark.parametrize("mode", ["missing", "unplanned", "roles"])
def test_receipt_validator_rejects_invalid_obligation_coverage(mode: str) -> None:
    capsule = _capsule()
    tampered = _mutable(_receipt(capsule))
    entries = tampered["obligation_dispositions"]
    if mode == "missing":
        entries.pop()
    elif mode == "unplanned":
        extra = dict(entries[0])
        extra["obligation_id"] = "obl:unplanned"
        entries.append(extra)
    else:
        entries[0]["source_roles"] = ["candidate_support"]
    tampered["receipt_digest"] = receipt_digest(tampered)

    with pytest.raises(L1EvidenceObligationReceiptError):
        validate_l1_evidence_obligation_receipt(tampered, capsule=capsule)


def test_receipt_records_explicit_requirement_bound_not_applicable() -> None:
    capsule = _capsule()
    obligation_id = capsule["evidence_obligation_ledger"]["obligations"][0][
        "obligation_id"
    ]
    receipt = _receipt(
        capsule,
        (
            {
                "source": "retrieval_result",
                "source_type": "fact_vectors",
                "content_digest": "sha256:" + "5" * 64,
                "l1_obligation_ids": [obligation_id],
                "l1_obligation_disposition": "NOT_APPLICABLE",
            },
        ),
    )

    entry = next(
        row
        for row in receipt["obligation_dispositions"]
        if row["obligation_id"] == obligation_id
    )
    assert entry["support_disposition"] == "NOT_APPLICABLE"
    assert entry["reason_code"] == "C0_REQUIREMENT_BOUND_EVIDENCE_NOT_APPLICABLE"


def test_receipt_writer_uses_the_explicit_caller_owned_path(tmp_path: Path) -> None:
    capsule = _capsule()
    receipt = _receipt(capsule)
    path = write_l1_evidence_obligation_receipt(
        output_path=tmp_path / "l1_evidence_obligation_receipt.json",
        receipt=receipt,
        capsule=capsule,
    )

    assert path == tmp_path / "l1_evidence_obligation_receipt.json"
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["receipt_digest"] == receipt["receipt_digest"]
    validate_l1_evidence_obligation_receipt(persisted, capsule=capsule)
