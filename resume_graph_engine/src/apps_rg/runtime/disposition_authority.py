"""Normalized disposition authority labels for apps_rg runtime receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

DISPOSITION_AUTHORITY_SPINE = "spine"
DISPOSITION_AUTHORITY_LANE = "lane"
DISPOSITION_AUTHORITY_BINDING_HELPER = "binding_helper"

LANE_X3_ARTIFACT = "x3_disposition.json"
EXIT_DISPOSITION_RECEIPT_ARTIFACT = "exit_disposition_receipt.json"
CORE_X3_DISPOSITION_RECEIPT_ARTIFACT = "x3_disposition_receipt.json"
CORE_RUNTIME_AUTHORITY_ARTIFACT = "apps_rg_core_runtime_authority.json"

_VALID_AUTHORITIES = frozenset(
    {
        DISPOSITION_AUTHORITY_SPINE,
        DISPOSITION_AUTHORITY_LANE,
        DISPOSITION_AUTHORITY_BINDING_HELPER,
    }
)


def lane_x3_disposition_overlay() -> dict[str, Any]:
    """Fields merged into section lane ``x3_disposition.json`` payloads."""
    return {
        "disposition_authority": DISPOSITION_AUTHORITY_LANE,
        "section_x3_authoritative": False,
        "section_x3_mirror_only": True,
        "spine_x3_claimed": False,
    }


def apply_lane_x3_authority_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return payload with lane disposition authority labels (does not mutate input)."""
    out = dict(payload)
    out.update(lane_x3_disposition_overlay())
    return out


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _x3_code_from_doc(doc: Mapping[str, Any]) -> str | None:
    for key in ("x3_code", "final_x3_code", "apps_rg_package_x3_disposition"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    nested = doc.get("x3_disposition")
    if isinstance(nested, Mapping):
        code = nested.get("x3_code")
        if isinstance(code, str) and code.strip():
            return code.strip()
    return None


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _core_x3_code(doc: Mapping[str, Any]) -> str | None:
    payload = doc.get("payload")
    payload = payload if isinstance(payload, Mapping) else doc
    code = payload.get("x3_disposition") or payload.get("x3_code")
    return str(code).strip() if str(code or "").strip() else None


def _validated_core_authority_code(doc: Mapping[str, Any]) -> str | None:
    body = dict(doc)
    stored = str(body.pop("deterministic_digest", "") or "")
    if not stored or stored != _canonical_digest(body):
        return None
    normalized = doc.get("normalized_contract")
    if not isinstance(normalized, Mapping) or normalized.get("valid") is not True:
        return None
    x3 = normalized.get("x3")
    if not isinstance(x3, Mapping):
        return None
    code = str(x3.get("x3_disposition") or "").strip()
    return code or None


def resolve_lane_x3_from_artifact_refs(
    *,
    artifact_refs: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """Resolve only producer-owned core X3 as lane authorization authority.

    The app ``exit_disposition_receipt.json`` and ``x3_disposition.json`` are
    retained as mirrors for diagnostics.  Neither may supply ``x3_code`` when
    the producer-owned core receipt is missing or invalid.
    """
    core_authority_rel = str(
        artifact_refs.get(CORE_RUNTIME_AUTHORITY_ARTIFACT) or ""
    ).strip()
    core_receipt_rel = str(
        artifact_refs.get(CORE_X3_DISPOSITION_RECEIPT_ARTIFACT) or ""
    ).strip()
    receipt_rel = str(
        artifact_refs.get(EXIT_DISPOSITION_RECEIPT_ARTIFACT) or ""
    ).strip()
    mirror_rel = str(artifact_refs.get(LANE_X3_ARTIFACT) or "").strip()

    core_authority_path = (
        (repo_root / core_authority_rel).resolve() if core_authority_rel else None
    )
    core_receipt_path = (
        (repo_root / core_receipt_rel).resolve() if core_receipt_rel else None
    )
    receipt_path = (repo_root / receipt_rel).resolve() if receipt_rel else None
    mirror_path = (repo_root / mirror_rel).resolve() if mirror_rel else None

    mirror_doc = (
        _load_json(mirror_path)
        if mirror_path is not None and mirror_path.is_file()
        else {}
    )
    exit_mirror_doc = (
        _load_json(receipt_path)
        if receipt_path is not None and receipt_path.is_file()
        else {}
    )
    mirror_code = _x3_code_from_doc(mirror_doc) or _x3_code_from_doc(exit_mirror_doc)

    if core_authority_path is not None and core_authority_path.is_file():
        doc = _load_json(core_authority_path)
        code = _validated_core_authority_code(doc)
        if code:
            return {
                "x3_code": code,
                "mirror_x3_code": mirror_code,
                "disposition_authority": DISPOSITION_AUTHORITY_SPINE,
                "authoritative_artifact": CORE_RUNTIME_AUTHORITY_ARTIFACT,
                "section_x3_mirror_only": False,
                "spine_x3_claimed": True,
                "canonical_exit_claimed": True,
                "outcome_authorized": doc.get("outcome_authorized") is True,
            }

    if core_receipt_path is not None and core_receipt_path.is_file():
        doc = _load_json(core_receipt_path)
        payload = doc.get("payload")
        payload = dict(payload) if isinstance(payload, Mapping) else {}
        code = _core_x3_code(doc)
        valid = bool(
            code
            and doc.get("producer_component")
            == "apps_rg.runtime.entrypoints.integrated_single_action_spine_run"
            and doc.get("artifact_hash") == _canonical_digest(payload)
        )
        if valid:
            return {
                "x3_code": code,
                "mirror_x3_code": mirror_code,
                "disposition_authority": DISPOSITION_AUTHORITY_SPINE,
                "authoritative_artifact": CORE_X3_DISPOSITION_RECEIPT_ARTIFACT,
                "section_x3_mirror_only": False,
                "spine_x3_claimed": True,
                "canonical_exit_claimed": True,
                "outcome_authorized": code == "X3D_ALLOW_FINISH",
            }

    return {
        "x3_code": None,
        "mirror_x3_code": mirror_code,
        "disposition_authority": DISPOSITION_AUTHORITY_LANE,
        "authoritative_artifact": None,
        "section_x3_mirror_only": True,
        "spine_x3_claimed": False,
        "canonical_exit_claimed": False,
        "outcome_authorized": False,
    }
