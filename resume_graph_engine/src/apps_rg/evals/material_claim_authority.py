"""W3 independent material-span reconciliation and human-truth readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


INVENTORY_VERSION = "apps_rg.material_claim_inventory.v1"
HUMAN_TRUTH_MANIFEST_VERSION = "apps_rg.w3_human_truth_manifest.v1"
SUMMARY_VERSION = "apps_rg.w3_material_claim_authority_summary.v1"
DEFAULT_HUMAN_TRUTH_MANIFEST = Path(__file__).with_name("w3_human_truth_manifest.v1.json")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])(?:\s+|$)")


@dataclass(frozen=True)
class MaterialSpan:
    span_id: str
    text: str
    start: int
    end: int


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def extract_material_spans(output_text: str) -> list[MaterialSpan]:
    """Extract every non-empty rendered sentence/bullet as a material candidate.

    The extractor intentionally over-includes. A later human truth lane may
    decide semantic materiality, but a system-omitted rendered assertion may
    never disappear before that decision.
    """
    spans: list[MaterialSpan] = []
    offset = 0
    for line in output_text.replace("\r\n", "\n").replace("\r", "\n").splitlines(True):
        line_start = offset
        text_without_newline = line.rstrip("\n")
        for match in _SENTENCE_BREAK.finditer(text_without_newline):
            candidate = text_without_newline[offset - line_start : match.start()]
            start = line_start + (offset - line_start)
            offset = line_start + match.end()
            stripped = candidate.strip(" \t•-–")
            if stripped:
                relative = candidate.index(stripped)
                span_start = start + relative
                span_end = span_start + len(stripped)
                spans.append(
                    MaterialSpan(
                        span_id=canonical_digest(
                            {"start": span_start, "end": span_end, "text": stripped}
                        ),
                        text=stripped,
                        start=span_start,
                        end=span_end,
                    )
                )
        tail_start = offset - line_start
        tail = text_without_newline[tail_start:]
        stripped = tail.strip(" \t•-–")
        if stripped:
            relative = tail.index(stripped)
            span_start = line_start + tail_start + relative
            span_end = span_start + len(stripped)
            spans.append(
                MaterialSpan(
                    span_id=canonical_digest(
                        {"start": span_start, "end": span_end, "text": stripped}
                    ),
                    text=stripped,
                    start=span_start,
                    end=span_end,
                )
            )
        offset = line_start + len(line)
    return spans


def reconcile_material_claim_inventory(inventory: Any) -> dict[str, Any]:
    """Reconcile rendered material candidates with system-provided claim records."""
    reasons: set[str] = set()
    if not isinstance(inventory, Mapping):
        reasons.add("MATERIAL_CLAIM_INVENTORY_NOT_OBJECT")
        inventory = {}
    if inventory.get("schema_version") != INVENTORY_VERSION:
        reasons.add("MATERIAL_CLAIM_INVENTORY_SCHEMA_INVALID")
    output_text = inventory.get("output_text")
    if not isinstance(output_text, str) or not output_text.strip():
        reasons.add("RENDERED_OUTPUT_MISSING")
        output_text = ""
    claims = inventory.get("claims")
    if not isinstance(claims, list):
        reasons.add("SYSTEM_CLAIM_INVENTORY_INVALID")
        claims = []
    spans = extract_material_spans(output_text)
    claims_by_location: dict[tuple[int, int], Mapping[str, Any]] = {}
    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            reasons.add("SYSTEM_CLAIM_ROW_INVALID")
            continue
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id or claim_id in claim_ids:
            reasons.add("SYSTEM_CLAIM_ID_DUPLICATE_OR_INVALID")
        claim_ids.add(claim_id)
        start, end = claim.get("output_start"), claim.get("output_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            reasons.add("SYSTEM_CLAIM_OUTPUT_LOCATOR_INVALID")
            continue
        location = (start, end)
        if location in claims_by_location:
            reasons.add("SYSTEM_CLAIM_OUTPUT_LOCATOR_DUPLICATE")
            continue
        claims_by_location[location] = claim
        if any(not str(claim.get(field) or "") for field in ("source_id", "source_excerpt_digest", "graph_path_id")):
            reasons.add("CLAIM_EVIDENCE_BINDING_INCOMPLETE")
        if claim.get("materiality") != "MATERIAL":
            reasons.add("SYSTEM_CLAIM_MATERIALITY_INVALID")
        if output_text[start:end] != claim.get("claim_text"):
            reasons.add("SYSTEM_CLAIM_TEXT_LOCATOR_MISMATCH")
    reconciled: list[dict[str, Any]] = []
    expected_locations = {(span.start, span.end) for span in spans}
    for span in spans:
        claim = claims_by_location.get((span.start, span.end))
        if claim is None:
            reasons.add("MATERIAL_SPAN_UNINVENTORIED")
            reconciled.append({"span_id": span.span_id, "status": "MISSING"})
        else:
            reconciled.append(
                {
                    "span_id": span.span_id,
                    "claim_id": str(claim.get("claim_id") or ""),
                    "status": "RECONCILED",
                }
            )
    if set(claims_by_location) - expected_locations:
        reasons.add("SYSTEM_CLAIM_NOT_A_RENDERED_MATERIAL_SPAN")
    status = "PASS" if not reasons else "FAIL"
    result: dict[str, Any] = {
        "schema_version": "apps_rg.material_claim_reconciliation.v1",
        "status": status,
        "material_span_count": len(spans),
        "system_claim_count": len(claims_by_location),
        "reconciled_spans": reconciled,
        "failure_codes": sorted(reasons),
        "authority": {
            "independent_extractor": "rendered_sentence_and_bullet_v1",
            "human_qualification": False,
            "release_authorizing": False,
        },
    }
    result["record_digest"] = canonical_digest(result)
    return result


def _review_readiness(value: Any, name: str) -> tuple[str, list[str]]:
    if not isinstance(value, Mapping):
        return "UNKNOWN", [f"{name}_REVIEW_MANIFEST_MISSING"]
    if value.get("synthetic_grades_created") is not False:
        return "BLOCKED", [f"{name}_SYNTHETIC_GRADES_FORBIDDEN"]
    status = value.get("status")
    required_primary = value.get("required_primary_reviews_per_item")
    required_adjudication = value.get("required_adjudications_per_item")
    if required_primary != 2 or required_adjudication != 1:
        return "BLOCKED", [f"{name}_REVIEW_QUORUM_CONTRACT_INVALID"]
    observed_primary = value.get("observed_primary_reviews")
    observed_adjudications = value.get("observed_adjudications")
    if status == "PENDING":
        if observed_primary != 0 or observed_adjudations_not_zero(observed_adjudications):
            return "BLOCKED", [f"{name}_PENDING_COUNTS_INVALID"]
        return "UNKNOWN", [f"{name}_HUMAN_REVIEWS_PENDING"]
    if status != "COMPLETE":
        return "BLOCKED", [f"{name}_REVIEW_STATUS_INVALID"]
    if not isinstance(observed_primary, int) or observed_primary < 2:
        return "UNKNOWN", [f"{name}_PRIMARY_REVIEW_QUORUM_INCOMPLETE"]
    if not isinstance(observed_adjudications, int) or observed_adjudications < 1:
        return "UNKNOWN", [f"{name}_ADJUDICATION_QUORUM_INCOMPLETE"]
    if not str(value.get("external_authority_receipt_sha256") or "") or not str(value.get("completed_receipt_digest") or ""):
        return "UNKNOWN", [f"{name}_EXTERNAL_AUTHORITY_RECEIPT_MISSING"]
    return "PASS", []


def observed_adjudations_not_zero(value: Any) -> bool:
    return not isinstance(value, int) or value != 0


def build_w3_authority_summary(
    human_truth_manifest_path: Path = DEFAULT_HUMAN_TRUTH_MANIFEST,
    inventory: Any | None = None,
) -> dict[str, Any]:
    """Combine human-truth readiness with independent claim reconciliation."""
    try:
        manifest = json.loads(human_truth_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifest = {}
        blocking = {"W3_HUMAN_TRUTH_MANIFEST_UNREADABLE"}
    else:
        blocking = set()
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != HUMAN_TRUTH_MANIFEST_VERSION:
        blocking.add("W3_HUMAN_TRUTH_MANIFEST_SCHEMA_INVALID")
    qrel_status, qrel_reasons = _review_readiness(
        manifest.get("qrel_review") if isinstance(manifest, Mapping) else None,
        "QREL",
    )
    proof_status, proof_reasons = _review_readiness(
        manifest.get("proof_review") if isinstance(manifest, Mapping) else None,
        "PROOF",
    )
    reconciliation = (
        reconcile_material_claim_inventory(inventory)
        if inventory is not None
        else None
    )
    not_measured = set(qrel_reasons + proof_reasons)
    if reconciliation is None:
        not_measured.add("MATERIAL_CLAIM_INVENTORY_NOT_SUPPLIED")
    elif reconciliation["status"] != "PASS":
        blocking.update(reconciliation["failure_codes"])
    if qrel_status == "BLOCKED" or proof_status == "BLOCKED":
        blocking.update(qrel_reasons + proof_reasons)
    status = "BLOCKED" if blocking else "NOT_MEASURED" if not_measured else "PASS"
    result: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "manifest_id": str(manifest.get("manifest_id") or human_truth_manifest_path.stem)
        if isinstance(manifest, Mapping)
        else human_truth_manifest_path.stem,
        "status": status,
        "human_truth": {"qrel": qrel_status, "proof": proof_status},
        "material_claim_reconciliation": reconciliation,
        "authority": {
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(blocking),
        "not_measured_reasons": sorted(not_measured),
    }
    result["record_digest"] = canonical_digest(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG W3 human-truth readiness")
    parser.add_argument("--human-truth-manifest", type=Path, default=DEFAULT_HUMAN_TRUTH_MANIFEST)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8")) if args.inventory else None
    result = build_w3_authority_summary(args.human_truth_manifest, inventory)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
