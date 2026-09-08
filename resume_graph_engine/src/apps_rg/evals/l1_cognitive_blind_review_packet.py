"""Blinded human-review material for completed Apps RG L1 paired runs.

This module prepares two distinct artifacts: a reviewer-visible packet with
opaque variant IDs and a sealed arm mapping.  It creates neither human labels
nor a promotion decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_outcome_protocol import (
    load_l1_cognitive_outcome_protocol,
    validate_l1_cognitive_paired_shadow_receipt,
)
from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    load_l1_cognitive_shadow_run_binding,
)
from apps_rg.evals.owner_solo.final_resume_output_review import (
    REVIEW_UNIT_SECTION,
    load_final_resume_output_bundle,
)
from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
    validate_l1_cognitive_treatment_execution_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_blind_review_packet.v2"
)
L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_blind_review_mapping.v1"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"


class L1CognitiveBlindReviewPacketError(ValueError):
    """Raised when an output cannot safely enter blinded human review."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _opaque_id(*, nonce: str, kind: str, source_id: str) -> str:
    return (
        f"{kind}-"
        + hashlib.sha256(f"{nonce}:{kind}:{source_id}".encode("utf-8")).hexdigest()[:20]
    )


def _require_nonce(value: str) -> str:
    nonce = str(value or "").strip().lower()
    if len(nonce) != 64 or any(char not in "0123456789abcdef" for char in nonce):
        raise L1CognitiveBlindReviewPacketError(
            "blind review nonce must be 64 hex characters"
        )
    return nonce


def _mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise L1CognitiveBlindReviewPacketError(f"{field} must be a mapping")
    return dict(value)


def _read_execution_digest(root: Path, *, arm: str) -> str:
    path = root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveBlindReviewPacketError(
            f"{arm} treatment execution receipt is unreadable"
        ) from exc
    if not isinstance(payload, Mapping) or payload.get("status") != "PASS":
        raise L1CognitiveBlindReviewPacketError(
            f"{arm} treatment execution receipt is not PASS"
        )
    try:
        validate_l1_cognitive_treatment_execution_receipt(payload)
    except ValueError as exc:
        raise L1CognitiveBlindReviewPacketError(
            f"{arm} treatment execution receipt is invalid"
        ) from exc
    digest = str(payload.get("receipt_digest") or "")
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise L1CognitiveBlindReviewPacketError(
            f"{arm} treatment execution receipt digest is invalid"
        )
    return digest


def _run_roots_for_pair(
    run_roots: Mapping[str, Mapping[str, Path | str]], pair_id: str
) -> tuple[Path, Path]:
    roots = _mapping(run_roots.get(pair_id), field=f"run_roots[{pair_id}]")
    control = Path(str(roots.get("control") or "")).resolve()
    candidate = Path(str(roots.get("candidate") or "")).resolve()
    if not control.is_dir() or not candidate.is_dir():
        raise L1CognitiveBlindReviewPacketError(
            f"paired review roots for {pair_id} must exist"
        )
    return control, candidate


def _verify_pair_provenance(
    *, pair: Mapping[str, Any], control_root: Path, candidate_root: Path, pair_id: str
) -> None:
    """Ensure reviewer-visible outputs come from the frozen paired experiment."""

    try:
        control_binding = load_l1_cognitive_shadow_run_binding(control_root)
        candidate_binding = load_l1_cognitive_shadow_run_binding(candidate_root)
    except ValueError as exc:
        raise L1CognitiveBlindReviewPacketError(
            f"{pair_id} shadow run provenance is invalid"
        ) from exc
    if control_binding != candidate_binding:
        raise L1CognitiveBlindReviewPacketError(
            f"{pair_id} runs do not share one frozen input/configuration binding"
        )
    if (
        pair.get("frozen_input_digest") != control_binding.get("frozen_input_digest")
        or pair.get("provider_model_config_digest")
        != control_binding.get("provider_model_config_digest")
        or pair.get("tool_config_digest") != control_binding.get("tool_config_digest")
    ):
        raise L1CognitiveBlindReviewPacketError(
            f"{pair_id} receipt does not match the run-local provenance binding"
        )


def _visible_variant(bundle: Mapping[str, Any], *, variant_id: str) -> dict[str, Any]:
    candidates = bundle.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise L1CognitiveBlindReviewPacketError(
            "final output review candidates are invalid"
        )
    units: list[dict[str, Any]] = []
    for raw in candidates:
        row = _mapping(raw, field="final output review candidate")
        units.append(
            {
                "unit_id": str(row.get("unit_ref") or ""),
                "display_label": str(row.get("display_label") or ""),
                "final_text": str(row.get("final_text") or ""),
                "final_text_sha256": str(row.get("final_text_sha256") or ""),
            }
        )
    if len(units) != 6 or any(not row["final_text"] for row in units):
        raise L1CognitiveBlindReviewPacketError(
            "blinded review requires six complete final-resume section units"
        )
    return {"variant_id": variant_id, "sections": units}


def _output_digest(bundle: Mapping[str, Any]) -> str:
    source = _mapping(bundle.get("source"), field="final output review source")
    raw = str(source.get("final_resume_sha256") or "")
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw.lower()):
        raise L1CognitiveBlindReviewPacketError("final resume output digest is invalid")
    return "sha256:" + raw.lower()


def _packet_digest(packet: Mapping[str, Any]) -> str:
    body = dict(packet)
    body.pop("packet_digest", None)
    return _sha256(body)


def _mapping_digest(mapping: Mapping[str, Any]) -> str:
    body = dict(mapping)
    body.pop("mapping_digest", None)
    return _sha256(body)


def build_l1_cognitive_blind_review_material(
    *,
    paired_receipt: Mapping[str, Any],
    run_roots: Mapping[str, Mapping[str, Path | str]],
    repo_root: Path,
    nonce: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a blind packet and separately sealed arm map for completed pairs."""

    nonce_value = _require_nonce(nonce)
    protocol = load_l1_cognitive_outcome_protocol()
    pairs = paired_receipt.get("pairs")
    if not isinstance(pairs, Sequence) or isinstance(pairs, (str, bytes)):
        raise L1CognitiveBlindReviewPacketError("paired receipt has no pairs")
    validate_l1_cognitive_paired_shadow_receipt(
        paired_receipt,
        protocol=protocol,
        pairs=pairs,
    )
    review_pairs: list[dict[str, Any]] = []
    sealed_pairs: list[dict[str, Any]] = []
    for raw_pair in pairs:
        pair = _mapping(raw_pair, field="paired receipt pair")
        pair_id = str(pair.get("pair_id") or "")
        control_root, candidate_root = _run_roots_for_pair(run_roots, pair_id)
        control = _mapping(pair.get("control"), field=f"{pair_id}.control")
        candidate = _mapping(pair.get("candidate"), field=f"{pair_id}.candidate")
        _verify_pair_provenance(
            pair=pair,
            control_root=control_root,
            candidate_root=candidate_root,
            pair_id=pair_id,
        )
        if (
            control.get("completion_status") != "PASS"
            or candidate.get("completion_status") != "PASS"
        ):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} must have completed control and candidate attempts"
            )
        if control.get(
            "l1_cognitive_treatment_execution_digest"
        ) != _read_execution_digest(control_root, arm="control"):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} control execution receipt does not match pair"
            )
        if candidate.get(
            "l1_cognitive_treatment_execution_digest"
        ) != _read_execution_digest(candidate_root, arm="candidate"):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} candidate execution receipt does not match pair"
            )
        control_bundle = load_final_resume_output_bundle(
            control_root, repo_root=Path(repo_root), review_unit=REVIEW_UNIT_SECTION
        )
        candidate_bundle = load_final_resume_output_bundle(
            candidate_root, repo_root=Path(repo_root), review_unit=REVIEW_UNIT_SECTION
        )
        if control_bundle.get("target") != candidate_bundle.get("target"):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} runs do not share the same frozen target"
            )
        if control.get("output_digest") != _output_digest(control_bundle):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} control output digest does not match final resume"
            )
        if candidate.get("output_digest") != _output_digest(candidate_bundle):
            raise L1CognitiveBlindReviewPacketError(
                f"{pair_id} candidate output digest does not match final resume"
            )
        blind_pair_id = _opaque_id(nonce=nonce_value, kind="pair", source_id=pair_id)
        variant_rows = [
            (
                "control",
                _visible_variant(
                    control_bundle,
                    variant_id=_opaque_id(
                        nonce=nonce_value,
                        kind="variant",
                        source_id=f"{pair_id}:control",
                    ),
                ),
            ),
            (
                "candidate",
                _visible_variant(
                    candidate_bundle,
                    variant_id=_opaque_id(
                        nonce=nonce_value,
                        kind="variant",
                        source_id=f"{pair_id}:candidate",
                    ),
                ),
            ),
        ]
        variant_rows.sort(key=lambda row: str(row[1]["variant_id"]))
        review_pairs.append(
            {
                "blind_pair_id": blind_pair_id,
                "target": control_bundle["target"],
                "variants": [row[1] for row in variant_rows],
            }
        )
        sealed_pairs.append(
            {
                "blind_pair_id": blind_pair_id,
                "source_pair_id": pair_id,
                "variants": [
                    {
                        "variant_id": row[1]["variant_id"],
                        "arm": row[0],
                        "run_ref": str(pair[row[0]]["run_ref"]),
                        "output_digest": str(pair[row[0]]["output_digest"]),
                    }
                    for row in variant_rows
                ],
            }
        )
    packet: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "status": "PENDING_HUMAN_REVIEW",
        "paired_receipt_digest": str(paired_receipt["receipt_digest"]),
        "reviewer_instructions": {
            "primary_reviewers_required_per_pair": 2,
            "adjudicator_required_per_pair": 1,
            "rubric": [
                "Select the variant that better supports an accurate, decision-ready résumé.",
                "Flag unsupported material claims and critical requirement omissions.",
                "Do not infer variant provenance; evaluate only the supplied final output.",
            ],
            "no_automatic_promotion": True,
        },
        "pairs": review_pairs,
        "authority": {
            "human_labels_present": False,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "packet_digest": "",
    }
    packet["packet_digest"] = _packet_digest(packet)
    sealed: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "distribution": "SEALED_DO_NOT_SEND_TO_REVIEWERS",
        "paired_receipt_digest": str(paired_receipt.get("receipt_digest") or ""),
        "pairs": sealed_pairs,
        "mapping_digest": "",
    }
    sealed["mapping_digest"] = _mapping_digest(sealed)
    return packet, sealed


def write_l1_cognitive_blind_review_material(
    *,
    packet_path: Path,
    sealed_mapping_path: Path,
    packet: Mapping[str, Any],
    sealed_mapping: Mapping[str, Any],
) -> tuple[Path, Path]:
    """Write separately routed review material after basic integrity checks."""

    if (
        packet.get("schema_version") != L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION
        or packet.get("app_scope") != _APP_SCOPE
        or packet.get("status") != "PENDING_HUMAN_REVIEW"
    ):
        raise L1CognitiveBlindReviewPacketError("blind review packet schema is invalid")
    paired_digest = str(packet.get("paired_receipt_digest") or "")
    if (
        not paired_digest.startswith("sha256:")
        or len(paired_digest) != len("sha256:") + 64
    ):
        raise L1CognitiveBlindReviewPacketError(
            "blind review packet paired receipt binding is invalid"
        )
    if packet.get("packet_digest") != _packet_digest(packet):
        raise L1CognitiveBlindReviewPacketError("blind review packet digest is invalid")
    if (
        sealed_mapping.get("schema_version")
        != L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION
        or sealed_mapping.get("app_scope") != _APP_SCOPE
    ):
        raise L1CognitiveBlindReviewPacketError(
            "blind review mapping schema is invalid"
        )
    if sealed_mapping.get("paired_receipt_digest") != paired_digest:
        raise L1CognitiveBlindReviewPacketError(
            "blind review mapping paired receipt binding is invalid"
        )
    if sealed_mapping.get("mapping_digest") != _mapping_digest(sealed_mapping):
        raise L1CognitiveBlindReviewPacketError(
            "blind review mapping digest is invalid"
        )
    if sealed_mapping.get("distribution") != "SEALED_DO_NOT_SEND_TO_REVIEWERS":
        raise L1CognitiveBlindReviewPacketError(
            "blind review mapping distribution is invalid"
        )
    packet_out = Path(packet_path)
    mapping_out = Path(sealed_mapping_path)
    sr.write_stage_receipt(packet_out, packet)
    sr.write_stage_receipt(mapping_out, sealed_mapping)
    return packet_out, mapping_out


__all__ = [
    "L1CognitiveBlindReviewPacketError",
    "L1_COGNITIVE_BLIND_REVIEW_MAPPING_SCHEMA_VERSION",
    "L1_COGNITIVE_BLIND_REVIEW_PACKET_SCHEMA_VERSION",
    "build_l1_cognitive_blind_review_material",
    "write_l1_cognitive_blind_review_material",
]
