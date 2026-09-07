"""Assemble Apps RG-local paired captures into one auditable cohort.

The capture operation emits one immutable technical receipt per matched control
and candidate pair.  A protected-holdout decision, however, must be based on
the complete sealed cohort rather than a hand-selected subset.  This module
only joins already-valid capture receipts; it neither invokes a runtime nor
creates human evidence or outcome judgments.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    paired_shadow_receipt_digest,
    validate_l1_cognitive_paired_shadow_receipt,
)


L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_paired_cohort_manifest.v1"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_AUTHORITY_CLASS: Final[str] = "TECHNICAL_PAIRED_COHORT_ASSEMBLY_ONLY"


class L1CognitivePairedCohortError(ValueError):
    """Raised when a paired cohort cannot be re-derived from captures."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def paired_cohort_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Return the stable digest excluding the manifest self-reference."""

    body = dict(manifest)
    body.pop("cohort_digest", None)
    return _sha256(body)


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitivePairedCohortError(f"{label} is invalid")
    return dict(value)


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise L1CognitivePairedCohortError(f"{label} is invalid")
    return list(value)


def _digest(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized.startswith("sha256:") or len(normalized) != len("sha256:") + 64:
        raise L1CognitivePairedCohortError(f"{label} is invalid")
    return normalized


def _source_receipts_and_pairs(
    source_paired_receipts: Sequence[Mapping[str, Any]],
    *,
    protocol: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate one-pair capture receipts and return their deterministic union."""

    source_rows = _sequence(
        source_paired_receipts, label="source paired capture receipts"
    )
    source_receipts: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    source_digests: set[str] = set()
    pair_ids: set[str] = set()
    for raw_source in source_rows:
        source = _mapping(raw_source, label="source paired capture receipt")
        source_pairs = _sequence(
            source.get("pairs"), label="source paired capture receipt pairs"
        )
        try:
            validate_l1_cognitive_paired_shadow_receipt(
                source,
                protocol=protocol,
                pairs=source_pairs,
            )
        except ValueError as exc:
            raise L1CognitivePairedCohortError(
                "source paired capture receipt is invalid"
            ) from exc
        if (
            source.get("summary", {}).get("attempt_count") != 1
            or len(source_pairs) != 1
        ):
            raise L1CognitivePairedCohortError(
                "each cohort source must be a single captured pair"
            )
        source_digest = _digest(
            source.get("receipt_digest"), label="source paired capture receipt digest"
        )
        if source_digest in source_digests:
            raise L1CognitivePairedCohortError(
                "source paired capture receipt digests must be unique"
            )
        source_digests.add(source_digest)
        pair = _mapping(source_pairs[0], label="source paired capture pair")
        pair_id = str(pair.get("pair_id") or "").strip()
        if not pair_id or pair_id in pair_ids:
            raise L1CognitivePairedCohortError(
                "cohort source pair identities must be unique"
            )
        pair_ids.add(pair_id)
        source_receipts.append(source)
        pairs.append(pair)
    return (
        sorted(source_receipts, key=lambda source: str(source["receipt_digest"])),
        sorted(pairs, key=lambda pair: str(pair["pair_id"])),
    )


def _manifest_body(
    *,
    protocol: Mapping[str, Any],
    source_receipts: Sequence[Mapping[str, Any]],
    paired_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION,
        "authority_class": _AUTHORITY_CLASS,
        "app_scope": _APP_SCOPE,
        "protocol_digest": _sha256(protocol),
        "source_paired_receipts": [dict(source) for source in source_receipts],
        "combined_paired_receipt_digest": str(paired_receipt["receipt_digest"]),
        "pair_ids": [
            str(pair["pair_id"])
            for pair in paired_receipt.get("pairs", [])
            if isinstance(pair, Mapping)
        ],
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
            "automatic_promotion": False,
        },
    }


def assemble_l1_cognitive_paired_cohort(
    *,
    protocol: Mapping[str, Any],
    source_paired_receipts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Join captured one-pair receipts without losing their source provenance."""

    source_receipts, pairs = _source_receipts_and_pairs(
        source_paired_receipts,
        protocol=protocol,
    )
    paired_receipt = build_l1_cognitive_paired_shadow_receipt(
        protocol=protocol,
        pairs=pairs,
    )
    manifest = _manifest_body(
        protocol=protocol,
        source_receipts=source_receipts,
        paired_receipt=paired_receipt,
    )
    manifest["cohort_digest"] = paired_cohort_manifest_digest(manifest)
    validate_l1_cognitive_paired_cohort_manifest(
        manifest,
        paired_receipt=paired_receipt,
        protocol=protocol,
    )
    return paired_receipt, manifest


def validate_l1_cognitive_paired_cohort_manifest(
    manifest: Mapping[str, Any],
    *,
    paired_receipt: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> None:
    """Fail closed unless the combined receipt is exactly the captured union."""

    value = _mapping(manifest, label="paired cohort manifest")
    required = {
        "schema_version",
        "authority_class",
        "app_scope",
        "protocol_digest",
        "source_paired_receipts",
        "combined_paired_receipt_digest",
        "pair_ids",
        "authority",
        "cohort_digest",
    }
    if set(value) != required:
        raise L1CognitivePairedCohortError("paired cohort manifest fields are invalid")
    if (
        value.get("schema_version")
        != L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION
    ):
        raise L1CognitivePairedCohortError("paired cohort manifest schema is invalid")
    if (
        value.get("authority_class") != _AUTHORITY_CLASS
        or value.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitivePairedCohortError("paired cohort manifest scope is invalid")
    if value.get("protocol_digest") != _sha256(protocol):
        raise L1CognitivePairedCohortError("paired cohort manifest protocol is invalid")
    if value.get("authority") != {
        "technical_validation": True,
        "human_qualified": False,
        "release_authorizing": False,
        "production_authorizing": False,
        "automatic_promotion": False,
    }:
        raise L1CognitivePairedCohortError(
            "paired cohort manifest authority is invalid"
        )
    source_receipts, pairs = _source_receipts_and_pairs(
        _sequence(
            value.get("source_paired_receipts"),
            label="paired cohort manifest sources",
        ),
        protocol=protocol,
    )
    expected_paired = build_l1_cognitive_paired_shadow_receipt(
        protocol=protocol,
        pairs=pairs,
    )
    if dict(paired_receipt) != expected_paired:
        raise L1CognitivePairedCohortError(
            "combined paired receipt does not match captured sources"
        )
    if value.get("combined_paired_receipt_digest") != paired_shadow_receipt_digest(
        paired_receipt
    ):
        raise L1CognitivePairedCohortError(
            "paired cohort manifest combined receipt binding is invalid"
        )
    expected = _manifest_body(
        protocol=protocol,
        source_receipts=source_receipts,
        paired_receipt=expected_paired,
    )
    actual = dict(value)
    actual.pop("cohort_digest", None)
    if actual != expected:
        raise L1CognitivePairedCohortError(
            "paired cohort manifest does not match captured sources"
        )
    if value.get("cohort_digest") != paired_cohort_manifest_digest(value):
        raise L1CognitivePairedCohortError("paired cohort manifest digest is invalid")


__all__ = [
    "L1CognitivePairedCohortError",
    "L1_COGNITIVE_PAIRED_COHORT_MANIFEST_SCHEMA_VERSION",
    "assemble_l1_cognitive_paired_cohort",
    "paired_cohort_manifest_digest",
    "validate_l1_cognitive_paired_cohort_manifest",
]
