"""C0-owned reconciliation receipt for an apps_rg L1 v2 obligation ledger.

The receipt proves that C0 considered every advisory L1 obligation.  It does
not let L1 assert evidence support: C0 records conservative dispositions and
only C0-derived FEC evidence references are eligible for the receipt.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    verify_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr

L1_EVIDENCE_OBLIGATION_RECEIPT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_evidence_obligation_receipt.v1"
)
L1_EVIDENCE_OBLIGATION_RECEIPT_AUTHORITY: Final[str] = "C0_EVIDENCE_RECONCILIATION_ONLY"
L1_EVIDENCE_OBLIGATION_RECEIPT_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT", "NOT_APPLICABLE"}
)
_CONTRADICTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"CONTRADICTED", "CONFLICTED", "FAIL"}
)


class L1EvidenceObligationReceiptError(ValueError):
    """Raised when a C0 obligation reconciliation receipt is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return a stable receipt digest excluding only the self digest field."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _value(item: Any, field: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _required_string(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise L1EvidenceObligationReceiptError(f"{field} is required")
    return text


def _is_c0_candidate_evidence(item: Any) -> bool:
    """Reject U0 JD and non-proof context before C0 dispositioning."""

    source = str(_value(item, "source")).strip().lower()
    source_type = (
        str(_value(item, "source_type", _value(item, "source_class"))).strip().lower()
    )
    authority = str(_value(item, "authority_class")).strip().lower()
    owner = str(_value(item, "source_owner_or_authority")).strip().lower()
    if source_type == "app_payload_inline":
        return False
    if source in {"jd_payload", "job_description", "job_description_text"}:
        return False
    if "jd_targeting" in owner or "non_proof" in authority:
        return False
    return True


def _item_metadata(item: Any) -> Mapping[str, Any]:
    metadata = _value(item, "metadata", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _item_obligation_ids(item: Any) -> frozenset[str]:
    metadata = _item_metadata(item)
    raw_ids = _value(item, "l1_obligation_ids", metadata.get("l1_obligation_ids"))
    if not isinstance(raw_ids, Sequence) or isinstance(raw_ids, (str, bytes)):
        return frozenset()
    return frozenset(str(value).strip() for value in raw_ids if str(value).strip())


def _item_disposition(item: Any) -> str:
    metadata = _item_metadata(item)
    disposition = (
        str(
            _value(
                item,
                "l1_obligation_disposition",
                metadata.get("l1_obligation_disposition"),
            )
        )
        .strip()
        .upper()
    )
    return disposition if disposition in _DISPOSITIONS else ""


def _c0_evidence_refs(
    evidence_items: Sequence[Any], *, obligation_id: str
) -> tuple[list[str], bool, bool, bool]:
    refs: list[str] = []
    contradiction_reported = False
    support_reported = False
    not_applicable_reported = False
    for index, item in enumerate(evidence_items):
        if not _is_c0_candidate_evidence(
            item
        ) or obligation_id not in _item_obligation_ids(item):
            continue
        evidence_identity = {
            "index": index,
            "evidence_id": str(_value(item, "evidence_id", _value(item, "source", ""))),
            "content_digest": str(_value(item, "content_digest", "")),
        }
        refs.append(
            "fec-item:"
            + str(index)
            + ":"
            + _sha256(evidence_identity).removeprefix("sha256:")[:16]
        )
        status = str(_value(item, "contradiction_status")).strip().upper()
        contradiction_reported = (
            contradiction_reported or status in _CONTRADICTION_STATUSES
        )
        support_reported = support_reported or _item_disposition(item) == "SUPPORTED"
        not_applicable_reported = (
            not_applicable_reported or _item_disposition(item) == "NOT_APPLICABLE"
        )
    return refs, contradiction_reported, support_reported, not_applicable_reported


def _entry_for_obligation(
    obligation: Mapping[str, Any],
    *,
    evidence_refs: Sequence[str],
    contradiction_reported: bool,
    support_reported: bool,
    not_applicable_reported: bool,
) -> dict[str, Any]:
    if contradiction_reported:
        disposition = "CONTRADICTED"
        contradiction_scan_status = "CONTRADICTION_REPORTED"
        reason_code = "C0_EVIDENCE_ITEM_REPORTED_CONTRADICTION"
    elif support_reported:
        disposition = "SUPPORTED"
        contradiction_scan_status = "SCANNED_NO_REPORTED_CONTRADICTION"
        reason_code = "C0_REQUIREMENT_BOUND_EVIDENCE_SUPPORTED"
    elif not_applicable_reported:
        disposition = "NOT_APPLICABLE"
        contradiction_scan_status = "SCANNED_NO_REPORTED_CONTRADICTION"
        reason_code = "C0_REQUIREMENT_BOUND_EVIDENCE_NOT_APPLICABLE"
    elif evidence_refs:
        # Candidate retrieval alone is not a requirement-level support claim.
        disposition = "INSUFFICIENT"
        contradiction_scan_status = "SCANNED_NO_REPORTED_CONTRADICTION"
        reason_code = "C0_CANDIDATE_EVIDENCE_NOT_REQUIREMENT_BOUND"
    else:
        disposition = "INSUFFICIENT"
        contradiction_scan_status = "NO_CANDIDATE_EVIDENCE"
        reason_code = "NO_C0_CANDIDATE_EVIDENCE_FOR_OBLIGATION"
    return {
        "obligation_id": _required_string(
            obligation.get("obligation_id"), field="obligation.obligation_id"
        ),
        "requirement_id": _required_string(
            obligation.get("requirement_id"), field="obligation.requirement_id"
        ),
        "target_unit_id": _required_string(
            obligation.get("target_unit_id"), field="obligation.target_unit_id"
        ),
        "source_roles": list(obligation.get("source_roles") or ()),
        "candidate_evidence_roles": [
            "candidate_support",
            "candidate_counterevidence",
        ],
        "evidence_refs": list(evidence_refs),
        "support_disposition": disposition,
        "contradiction_scan_status": contradiction_scan_status,
        "reason_code": reason_code,
        "c0_is_evidence_authority": True,
        "jd_targeting_is_not_candidate_evidence": True,
    }


def build_l1_evidence_obligation_receipt(
    *,
    capsule: Mapping[str, Any],
    request_id: str,
    run_id: str,
    trace_id: str,
    final_evidence_digest: str,
    evidence_items: Sequence[Any],
) -> dict[str, Any]:
    """Build an exact-coverage C0 disposition sidecar from verified v2 intent."""

    try:
        verification = verify_apps_rg_l1_planning_capsule_v2(capsule)
    except L1PlanningV2IntegrityError as exc:
        raise L1EvidenceObligationReceiptError(
            f"v2 L1 capsule is invalid: {exc}"
        ) from exc
    identity = {
        "request_id": _required_string(request_id, field="request_id"),
        "run_id": _required_string(run_id, field="run_id"),
        "trace_id": _required_string(trace_id, field="trace_id"),
    }
    for field, value in identity.items():
        if str(capsule.get(field) or "") != value:
            raise L1EvidenceObligationReceiptError(
                f"v2 L1 capsule identity mismatch for {field}"
            )
    evidence_digest = _required_string(
        final_evidence_digest, field="final_evidence_digest"
    )
    ledger = capsule.get("evidence_obligation_ledger")
    if not isinstance(ledger, Mapping):
        raise L1EvidenceObligationReceiptError(
            "v2 evidence-obligation ledger is required"
        )
    obligations = ledger.get("obligations")
    if not isinstance(obligations, Sequence) or isinstance(obligations, (str, bytes)):
        raise L1EvidenceObligationReceiptError("v2 evidence obligations are invalid")
    entries: list[dict[str, Any]] = []
    for obligation in obligations:
        if not isinstance(obligation, Mapping):
            continue
        (
            evidence_refs,
            contradiction_reported,
            support_reported,
            not_applicable_reported,
        ) = _c0_evidence_refs(
            evidence_items,
            obligation_id=_required_string(
                obligation.get("obligation_id"), field="obligation.obligation_id"
            ),
        )
        entries.append(
            _entry_for_obligation(
                obligation,
                evidence_refs=evidence_refs,
                contradiction_reported=contradiction_reported,
                support_reported=support_reported,
                not_applicable_reported=not_applicable_reported,
            )
        )
    if len(entries) != len(obligations):
        raise L1EvidenceObligationReceiptError(
            "v2 evidence obligation entry is invalid"
        )
    entries.sort(key=lambda entry: entry["obligation_id"])
    disposition_counts = {
        disposition: sum(
            1 for entry in entries if entry["support_disposition"] == disposition
        )
        for disposition in sorted(_DISPOSITIONS)
    }
    receipt = {
        "schema_version": L1_EVIDENCE_OBLIGATION_RECEIPT_SCHEMA_VERSION,
        "authority_class": L1_EVIDENCE_OBLIGATION_RECEIPT_AUTHORITY,
        "app_scope": L1_EVIDENCE_OBLIGATION_RECEIPT_APP_SCOPE,
        "identity": identity,
        "l1_v2": {
            "capsule_digest": str(verification["capsule_digest"]),
            "evidence_obligation_ledger_digest": str(ledger.get("ledger_digest") or ""),
        },
        "c0": {
            "final_evidence_digest": evidence_digest,
            "evidence_item_count": len(evidence_items),
        },
        "obligation_dispositions": entries,
        "coverage": {
            "planned_obligation_count": len(obligations),
            "observed_disposition_count": len(entries),
            "disposition_counts": disposition_counts,
            "all_obligations_disposed": True,
            "no_unplanned_obligations": True,
            "jd_targeting_used_as_candidate_evidence": False,
        },
        "validation": {
            "c0_is_only_evidence_authority": True,
            "exact_l1_obligation_coverage": True,
            "no_added_l1_obligation": True,
            "jd_targeting_not_candidate_evidence": True,
            "evidence_refs_are_fec_item_scoped": True,
        },
    }
    receipt["receipt_digest"] = receipt_digest(receipt)
    validate_l1_evidence_obligation_receipt(receipt, capsule=capsule)
    return receipt


def validate_l1_evidence_obligation_receipt(
    receipt: Mapping[str, Any], *, capsule: Mapping[str, Any]
) -> None:
    """Fail closed unless C0 has exactly reconciled verified L1 v2 intent."""

    if not isinstance(receipt, Mapping):
        raise L1EvidenceObligationReceiptError("receipt must be a mapping")
    if receipt.get("schema_version") != L1_EVIDENCE_OBLIGATION_RECEIPT_SCHEMA_VERSION:
        raise L1EvidenceObligationReceiptError("receipt schema_version is invalid")
    if receipt.get("authority_class") != L1_EVIDENCE_OBLIGATION_RECEIPT_AUTHORITY:
        raise L1EvidenceObligationReceiptError("receipt authority_class is invalid")
    if receipt.get("app_scope") != L1_EVIDENCE_OBLIGATION_RECEIPT_APP_SCOPE:
        raise L1EvidenceObligationReceiptError("receipt app_scope is invalid")
    if receipt.get("receipt_digest") != receipt_digest(receipt):
        raise L1EvidenceObligationReceiptError("receipt digest mismatch")
    try:
        verification = verify_apps_rg_l1_planning_capsule_v2(capsule)
    except L1PlanningV2IntegrityError as exc:
        raise L1EvidenceObligationReceiptError("v2 L1 capsule is invalid") from exc
    identity = receipt.get("identity")
    if not isinstance(identity, Mapping):
        raise L1EvidenceObligationReceiptError("receipt identity is invalid")
    for field in ("request_id", "run_id", "trace_id"):
        if str(identity.get(field) or "") != str(capsule.get(field) or ""):
            raise L1EvidenceObligationReceiptError("receipt identity is not L1-bound")
    l1_v2 = receipt.get("l1_v2")
    ledger = capsule.get("evidence_obligation_ledger")
    if not isinstance(l1_v2, Mapping) or not isinstance(ledger, Mapping):
        raise L1EvidenceObligationReceiptError("receipt L1 v2 binding is invalid")
    if l1_v2.get("capsule_digest") != verification["capsule_digest"]:
        raise L1EvidenceObligationReceiptError("receipt capsule digest is invalid")
    if l1_v2.get("evidence_obligation_ledger_digest") != ledger.get("ledger_digest"):
        raise L1EvidenceObligationReceiptError(
            "receipt obligation ledger digest is invalid"
        )
    obligations = ledger.get("obligations")
    entries = receipt.get("obligation_dispositions")
    if not isinstance(obligations, Sequence) or not isinstance(entries, Sequence):
        raise L1EvidenceObligationReceiptError("receipt obligation coverage is invalid")
    expected = {
        str(obligation.get("obligation_id") or ""): (
            str(obligation.get("requirement_id") or ""),
            str(obligation.get("target_unit_id") or ""),
            tuple(str(role) for role in (obligation.get("source_roles") or ())),
        )
        for obligation in obligations
        if isinstance(obligation, Mapping)
    }
    observed: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise L1EvidenceObligationReceiptError(
                "receipt disposition entry is invalid"
            )
        obligation_id = str(entry.get("obligation_id") or "")
        if obligation_id in observed or obligation_id not in expected:
            raise L1EvidenceObligationReceiptError(
                "receipt has unplanned or duplicate obligation"
            )
        observed[obligation_id] = (
            str(entry.get("requirement_id") or ""),
            str(entry.get("target_unit_id") or ""),
            tuple(str(role) for role in (entry.get("source_roles") or ())),
        )
        if observed[obligation_id] != expected[obligation_id]:
            raise L1EvidenceObligationReceiptError(
                "receipt obligation identity is invalid"
            )
        if entry.get("support_disposition") not in _DISPOSITIONS:
            raise L1EvidenceObligationReceiptError(
                "receipt support disposition is invalid"
            )
        if entry.get("c0_is_evidence_authority") is not True:
            raise L1EvidenceObligationReceiptError(
                "receipt C0 authority assertion is invalid"
            )
        if entry.get("jd_targeting_is_not_candidate_evidence") is not True:
            raise L1EvidenceObligationReceiptError(
                "receipt JD targeting assertion is invalid"
            )
        roles = entry.get("candidate_evidence_roles")
        refs = entry.get("evidence_refs")
        if roles != ["candidate_support", "candidate_counterevidence"]:
            raise L1EvidenceObligationReceiptError(
                "receipt candidate evidence roles are invalid"
            )
        if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
            raise L1EvidenceObligationReceiptError("receipt evidence refs are invalid")
        if any(
            not str(ref).startswith("fec-item:") or Path(str(ref)).is_absolute()
            for ref in refs
        ):
            raise L1EvidenceObligationReceiptError("receipt evidence refs are invalid")
    if observed != expected:
        raise L1EvidenceObligationReceiptError(
            "receipt does not cover every L1 obligation"
        )
    coverage = receipt.get("coverage")
    if not isinstance(coverage, Mapping) or any(
        coverage.get(key) is not True
        for key in ("all_obligations_disposed", "no_unplanned_obligations")
    ):
        raise L1EvidenceObligationReceiptError(
            "receipt coverage assertions are invalid"
        )
    if coverage.get("planned_obligation_count") != len(expected) or coverage.get(
        "observed_disposition_count"
    ) != len(observed):
        raise L1EvidenceObligationReceiptError("receipt coverage counts are invalid")
    if coverage.get("jd_targeting_used_as_candidate_evidence") is not False:
        raise L1EvidenceObligationReceiptError(
            "receipt converted JD targeting into evidence"
        )
    validation = receipt.get("validation")
    required = {
        "c0_is_only_evidence_authority",
        "exact_l1_obligation_coverage",
        "no_added_l1_obligation",
        "jd_targeting_not_candidate_evidence",
        "evidence_refs_are_fec_item_scoped",
    }
    if not isinstance(validation, Mapping) or any(
        validation.get(key) is not True for key in required
    ):
        raise L1EvidenceObligationReceiptError(
            "receipt validation assertions are invalid"
        )


def write_l1_evidence_obligation_receipt(
    *, output_path: Path, receipt: Mapping[str, Any], capsule: Mapping[str, Any]
) -> Path:
    """Validate and write a receipt at one explicit, caller-owned path."""

    validate_l1_evidence_obligation_receipt(receipt, capsule=capsule)
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


def emit_l1_evidence_obligation_receipt(
    *, artifact_dir: Path, receipt: Mapping[str, Any], capsule: Mapping[str, Any]
) -> Path:
    """Write the canonical W2 receipt beneath one artifact directory."""

    return write_l1_evidence_obligation_receipt(
        output_path=Path(artifact_dir) / sr.FILENAME_L1_EVIDENCE_OBLIGATION_RECEIPT,
        receipt=receipt,
        capsule=capsule,
    )


__all__ = [
    "L1_EVIDENCE_OBLIGATION_RECEIPT_APP_SCOPE",
    "L1_EVIDENCE_OBLIGATION_RECEIPT_AUTHORITY",
    "L1_EVIDENCE_OBLIGATION_RECEIPT_SCHEMA_VERSION",
    "L1EvidenceObligationReceiptError",
    "build_l1_evidence_obligation_receipt",
    "emit_l1_evidence_obligation_receipt",
    "receipt_digest",
    "validate_l1_evidence_obligation_receipt",
    "write_l1_evidence_obligation_receipt",
]
