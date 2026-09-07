"""W3 blinded packet for the owner-solo full-resume retrieval review.

W2 freezes the complete BGE-M3 ranking for every target and resume section.
This module turns that private ranking into one owner-visible packet.  The
packet keeps the review unit intact: a reviewer grades the usefulness of a
*graph-evidence cluster* as source material for the shown job and resume
section.  It does not ask the reviewer to grade an individual graph node or
invent final résumé prose.

The complete ranking, graph identities, model identity, and calibration /
holdout partition remain in the sealed mapping beneath ``.runtime``.  The
owner-visible files contain only opaque references, the full job context, the
human-readable resume section, and the complete source-backed cluster text.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    ranking_identity_sha256,
)
from apps_rg.evals.c03_human_eval._safety import unsafe_reviewer_keys
from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    EXPECTED_SECTION_IDS,
    RESULT_LABEL,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1c import (
    validate_combined_registry,
)
from apps_rg.evals.owner_solo.c03_full_resume_qrel_w2 import (
    RECEIPT_STATUS as W2_RECEIPT_STATUS,
    RECEIPT_SCHEMA_VERSION as W2_RECEIPT_SCHEMA_VERSION,
    RANKING_SCHEMA_VERSION,
    RANKING_STATUS,
    QUERY_MANIFEST_SCHEMA_VERSION,
    QUERY_MANIFEST_STATUS,
    validate_frozen_ranking_artifact,
    validate_w2_query_manifest,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)


PACKET_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w3_packet.v1"
CONTRACT_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w3_contract.v1"
REVIEW_ITEM_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_qrel_w3_review_item.v1"
)
SEALED_MAPPING_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_qrel_w3_sealed_mapping.v1"
)
REVIEWER_MANIFEST_SCHEMA_VERSION = (
    "apps_rg.owner_solo_full_resume_qrel_w3_reviewer_manifest.v1"
)
RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_w3_receipt.v1"

PACKET_STATUS = "FROZEN_UNLABELED_OWNER_SOLO_BLINDED_PACKET"
RECEIPT_STATUS = "W3_BLINDED_PACKET_READY_FOR_OWNER_REVIEW"
RUNTIME_DIR = Path(".runtime/c03-owner-solo-qrel/w3")
DEFAULT_PACKET_DIR = RUNTIME_DIR / "prelabel_packet"
OWNER_COHORT = "owner_solo"
CONTRACT_PATH = Path("src/apps_rg/evals/owner_solo/c03_full_resume_qrel_w3_contract.v1.json")

_NONCE_RE = re.compile(r"[0-9a-f]{64}")
_OPAQUE_ITEM_RE = re.compile(r"item-[0-9a-f]{24}")
_OPAQUE_CANDIDATE_RE = re.compile(r"candidate-[0-9a-f]{24}")
_PINNED_MODEL = {
    "model_id": "BAAI/bge-m3",
    "revision": "5617a9f61b028005a4858fdac845db406aefb181",
    "artifact_sha256": (
        "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263"
    ),
    "dimension": 1024,
    "normalization": "l2",
}
_SECTION_TITLES = {
    "headline": "Headline",
    "executive_summary": "Executive Summary",
    "competencies": "Core Competencies",
    "unify_bullets": "Unify Consulting — Experience Bullets",
    "unify_narrative": "Unify Consulting — Role Narrative",
    "ibm_bullets": "IBM — Experience Bullets",
    "ibm_narrative": "IBM — Role Narrative",
    "ey_bullets": "EY — Experience Bullets",
    "ey_narrative": "EY — Role Narrative",
    "insurtech_bullets": "InsurTech — Experience Bullets",
    "insurtech_narrative": "InsurTech — Role Narrative",
}
_VISIBLE_ITEM_KEYS = {
    "schema_version",
    "item_ref",
    "target_context",
    "resume_section",
    "section_prompt",
    "candidate_count",
    "candidates",
}
_VISIBLE_CANDIDATE_KEYS = {"candidate_ref", "evidence_cluster_text"}


class FullResumeQrelW3Error(ValueError):
    """Raised when a full-resume W3 blinded packet is invalid or unavailable."""


def validate_w3_review_contract(contract: Mapping[str, Any]) -> None:
    """Validate W3's owner-solo packet boundary without touching W7/W9."""

    issues: list[str] = []
    unsigned = dict(contract)
    digest = unsigned.pop("contract_sha256", None)
    if (
        contract.get("schema_version") != CONTRACT_SCHEMA_VERSION
        or contract.get("wave") != "W3"
        or contract.get("status") != "FROZEN"
        or contract.get("result_label") != RESULT_LABEL
        or not isinstance(digest, str)
        or canonical_sha256(unsigned) != digest
    ):
        issues.append("SCHEMA_OR_DIGEST")
    review_packet = contract.get("review_packet") or {}
    expected_counts = {
        "query_count": 6,
        "section_count": 11,
        "query_section_item_count": 66,
        "candidate_judgment_count": 600,
        "logical_retrieval_unit": "graph_evidence_cluster",
    }
    if any(review_packet.get(key) != value for key, value in expected_counts.items()):
        issues.append("REVIEW_PACKET_COUNTS")
    required_true = (
        ("review_packet", "full_finite_candidate_universe_required"),
        ("review_packet", "partial_top_k_judging_forbidden"),
        ("review_packet", "one_blinded_owner_packet_required"),
        ("blinding", "opaque_item_and_candidate_references_required"),
        ("blinding", "target_context_and_complete_cluster_text_required"),
        ("blinding", "ranks_scores_splits_cluster_ids_and_model_choice_forbidden"),
        ("blinding", "sealed_mapping_runtime_only"),
        ("authority_boundary", "existing_two_reviewer_contract_unchanged"),
        ("authority_boundary", "existing_independent_adjudication_contract_unchanged"),
    )
    for section, key in required_true:
        if (contract.get(section) or {}).get(key) is not True:
            issues.append(f"{section}.{key}")
    required_false = (
        ("authority_boundary", "human_labels_created_by_w3"),
        ("authority_boundary", "metrics_computable_by_w3"),
        ("authority_boundary", "authoritative_release_qualification_satisfied"),
        ("authority_boundary", "activation_manifest_created"),
        ("authority_boundary", "production_promotion_authorized"),
    )
    for section, key in required_false:
        if (contract.get(section) or {}).get(key) is not False:
            issues.append(f"{section}.{key}")
    if issues:
        raise FullResumeQrelW3Error(
            f"Invalid W3 review contract: {sorted(set(issues))}"
        )


def load_w3_review_contract(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    contract = _read_json(_resolve_repository_path(root, CONTRACT_PATH))
    validate_w3_review_contract(contract)
    return contract


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelW3Error(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise FullResumeQrelW3Error(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FullResumeQrelW3Error(f"JSONL unavailable: {path}")
    rows: list[dict[str, Any]] = []
    try:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise FullResumeQrelW3Error(
                    f"JSON object required at {path}:{line_no}"
                )
            rows.append(value)
    except json.JSONDecodeError as exc:
        raise FullResumeQrelW3Error(f"Malformed JSONL: {path}") from exc
    return rows


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelW3Error(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _resolve_repository_path(root: Path, value: Path | str) -> Path:
    candidate = Path(value)
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise FullResumeQrelW3Error(f"Path escapes repository root: {value}") from exc
    return path


def _repository_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise FullResumeQrelW3Error(f"Path escapes repository root: {path}") from exc


def _immutable_bytes(path: Path, data: bytes) -> str:
    """Write a byte-exact runtime artifact once, or reject a collision."""

    if path.exists():
        if path.read_bytes() != data:
            raise FullResumeQrelW3Error(f"Immutable artifact collision: {path}")
        return hashlib.sha256(data).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.staging-{os.getpid()}")
    try:
        staging.write_bytes(data)
        os.replace(staging, path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return hashlib.sha256(data).hexdigest()


def _immutable_json(path: Path, payload: Mapping[str, Any]) -> str:
    return _immutable_bytes(
        path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return (
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        )
    ).encode("utf-8")


def blinding_nonce_commitment(nonce: str) -> str:
    value = str(nonce or "").strip()
    if not _NONCE_RE.fullmatch(value):
        raise FullResumeQrelW3Error(
            "W3 blinding nonce must contain exactly 64 lowercase hex characters"
        )
    return hashlib.sha256(
        b"apps_rg.owner_solo.full_resume_qrel.w3.nonce.v1\x00" + bytes.fromhex(value)
    ).hexdigest()


def _blind_digest(nonce: str, purpose: str, *parts: str) -> str:
    # Validate the nonce before using it as an HMAC key.
    blinding_nonce_commitment(nonce)
    message = json.dumps(
        {"purpose": purpose, "parts": list(parts)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(bytes.fromhex(nonce), message, hashlib.sha256).hexdigest()


def _section_title(section_id: str) -> str:
    try:
        return _SECTION_TITLES[section_id]
    except KeyError as exc:
        raise FullResumeQrelW3Error(f"Unsupported W3 resume section: {section_id}") from exc


def _section_prompt(section_id: str) -> str:
    return (
        f"How useful is this complete source-backed evidence cluster for the "
        f"{_section_title(section_id)} section of this target résumé?"
    )


def _target_context(root: Path, query: Mapping[str, Any]) -> str:
    jd_path = _resolve_repository_path(root, str(query.get("jd_path") or ""))
    brief_path = _resolve_repository_path(root, str(query.get("brief_path") or ""))
    try:
        jd = jd_path.read_text(encoding="utf-8").strip()
        brief = brief_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FullResumeQrelW3Error("W3 target context source is unavailable") from exc
    if not jd or not brief:
        raise FullResumeQrelW3Error("W3 target context source is empty")
    if _file_sha256(jd_path) != str(query.get("jd_sha256") or ""):
        raise FullResumeQrelW3Error("W3 target job description binding drifted")
    if _file_sha256(brief_path) != str(query.get("brief_sha256") or ""):
        raise FullResumeQrelW3Error("W3 target brief binding drifted")
    return f"Target job description:\n{jd}\n\nApplication brief:\n{brief}"


def _expected_bindings(
    query_manifest: Mapping[str, Any], ranking_artifact: Mapping[str, Any]
) -> dict[str, str]:
    source = ranking_artifact.get("source_authority") or {}
    expected = {
        "scope_manifest_sha256": str(source.get("scope_manifest_sha256") or ""),
        "query_manifest_sha256": str(query_manifest.get("query_manifest_sha256") or ""),
        "combined_registry_sha256": str(source.get("combined_registry_sha256") or ""),
        "projection_generation_sha256": str(
            source.get("projection_generation_sha256") or ""
        ),
        "ranking_artifact_sha256": str(
            ranking_artifact.get("ranking_artifact_sha256") or ""
        ),
        "ranking_identity_sha256": str(
            ranking_artifact.get("ranking_identity_sha256") or ""
        ),
    }
    if not all(_is_sha256(value) for value in expected.values()):
        raise FullResumeQrelW3Error("W3 source bindings are malformed")
    return expected


def _ranking_rows(
    ranking_artifact: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    rows = ranking_artifact.get("rankings")
    if not isinstance(rows, list):
        raise FullResumeQrelW3Error("W3 ranking rows are unavailable")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FullResumeQrelW3Error("W3 ranking row is malformed")
        key = (str(row.get("query_id") or ""), str(row.get("section_id") or ""))
        if not all(key) or key in result:
            raise FullResumeQrelW3Error("W3 ranking row identity is invalid")
        result[key] = row
    return result


def build_w3_packet_content(
    *,
    repo_root: Path | str,
    query_manifest: Mapping[str, Any],
    combined_registry: Mapping[str, Any],
    ranking_artifact: Mapping[str, Any],
    blinding_nonce: str,
) -> dict[str, Any]:
    """Build one blinded owner packet from a validated W2 finite universe."""

    root = Path(repo_root).resolve()
    nonce_commitment = blinding_nonce_commitment(blinding_nonce)
    bindings = _expected_bindings(query_manifest, ranking_artifact)
    queries = {
        str(row.get("query_id") or ""): row
        for row in query_manifest.get("queries") or []
        if isinstance(row, Mapping)
    }
    clusters = {
        str(row.get("cluster_id") or ""): str(
            row.get("canonical_embedding_text") or ""
        )
        for row in combined_registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    rankings = _ranking_rows(ranking_artifact)
    items_with_order: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    for (query_id, section_id), ranking in sorted(rankings.items()):
        query = queries.get(query_id)
        if query is None or section_id not in EXPECTED_SECTION_IDS:
            raise FullResumeQrelW3Error("W3 ranking is outside frozen scope")
        item_ref = "item-" + _blind_digest(
            blinding_nonce, "owner-item", query_id, section_id
        )[:24]
        candidate_rows: list[tuple[str, str, str, int]] = []
        candidates = ranking.get("candidates")
        if not isinstance(candidates, list):
            raise FullResumeQrelW3Error("W3 ranking candidate list is unavailable")
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise FullResumeQrelW3Error("W3 ranking candidate is malformed")
            cluster_id = str(candidate.get("cluster_id") or "")
            frozen_rank = candidate.get("frozen_rank")
            text = clusters.get(cluster_id)
            if not cluster_id or not text or not isinstance(frozen_rank, int):
                raise FullResumeQrelW3Error("W3 cluster source binding is invalid")
            candidate_ref = "candidate-" + _blind_digest(
                blinding_nonce, "owner-candidate", query_id, section_id, cluster_id
            )[:24]
            blind_order = _blind_digest(
                blinding_nonce, "owner-candidate-order", query_id, section_id, cluster_id
            )
            candidate_rows.append((blind_order, candidate_ref, cluster_id, frozen_rank))
        candidate_rows.sort(key=lambda row: row[0])
        item = {
            "schema_version": REVIEW_ITEM_SCHEMA_VERSION,
            "item_ref": item_ref,
            "target_context": _target_context(root, query),
            "resume_section": _section_title(section_id),
            "section_prompt": _section_prompt(section_id),
            "candidate_count": len(candidate_rows),
            "candidates": [
                {
                    "candidate_ref": candidate_ref,
                    "evidence_cluster_text": clusters[cluster_id],
                }
                for _, candidate_ref, cluster_id, _ in candidate_rows
            ],
        }
        sealed = {
            "item_ref": item_ref,
            "query_id": query_id,
            "section_id": section_id,
            "candidates": [
                {
                    "candidate_ref": candidate_ref,
                    "cluster_id": cluster_id,
                    "frozen_rank": frozen_rank,
                }
                for _, candidate_ref, cluster_id, frozen_rank in candidate_rows
            ],
        }
        item_order = _blind_digest(
            blinding_nonce, "owner-item-order", query_id, section_id
        )
        items_with_order.append((item_order, item, sealed))

    items_with_order.sort(key=lambda row: row[0])
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "result_label": RESULT_LABEL,
        "authority_bindings": bindings,
        "blinding": {
            "nonce_commitment": nonce_commitment,
            "opaque_query_and_candidate_references": True,
            "ranks_scores_splits_cluster_ids_and_model_choice_forbidden": True,
        },
        "reviewer": {
            "cohort": OWNER_COHORT,
            "item_count": len(items_with_order),
            "candidate_judgment_count": sum(
                int(item["candidate_count"]) for _, item, _ in items_with_order
            ),
            "logical_retrieval_unit": "graph_evidence_cluster",
        },
        "reviewer_items": [item for _, item, _ in items_with_order],
        "sealed_mapping": {
            "schema_version": SEALED_MAPPING_SCHEMA_VERSION,
            "distribution_forbidden": True,
            "ranking_identity_sha256": bindings["ranking_identity_sha256"],
            "items": [sealed for _, _, sealed in items_with_order],
        },
        "scope_guards": {
            "human_qrels_created": False,
            "metrics_computable": False,
            "authoritative_release_qualification_satisfied": False,
            "activation_manifest_created": False,
            "production_promotion_authorized": False,
        },
    }
    validate_w3_packet_content(
        packet,
        repo_root=root,
        query_manifest=query_manifest,
        combined_registry=combined_registry,
        ranking_artifact=ranking_artifact,
    )
    return packet


def validate_w3_packet_content(
    packet: Mapping[str, Any],
    *,
    repo_root: Path | str,
    query_manifest: Mapping[str, Any],
    combined_registry: Mapping[str, Any],
    ranking_artifact: Mapping[str, Any],
) -> None:
    """Fail closed on a bad binding, incomplete denominator, or reviewer leak."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if (
        packet.get("schema_version") != PACKET_SCHEMA_VERSION
        or packet.get("status") != PACKET_STATUS
        or packet.get("result_label") != RESULT_LABEL
    ):
        issues.append("SCHEMA_OR_STATUS")
    try:
        expected_bindings = _expected_bindings(query_manifest, ranking_artifact)
    except FullResumeQrelW3Error:
        expected_bindings = {}
        issues.append("SOURCE_BINDINGS")
    if packet.get("authority_bindings") != expected_bindings:
        issues.append("SOURCE_BINDINGS")
    blinding = packet.get("blinding") or {}
    if (
        not _is_sha256(blinding.get("nonce_commitment"))
        or blinding.get("opaque_query_and_candidate_references") is not True
        or blinding.get("ranks_scores_splits_cluster_ids_and_model_choice_forbidden")
        is not True
    ):
        issues.append("BLINDING_CONTRACT")
    if (packet.get("scope_guards") or {}) != {
        "human_qrels_created": False,
        "metrics_computable": False,
        "authoritative_release_qualification_satisfied": False,
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }:
        issues.append("SCOPE_GUARDS")

    queries = {
        str(row.get("query_id") or ""): row
        for row in query_manifest.get("queries") or []
        if isinstance(row, Mapping)
    }
    clusters = {
        str(row.get("cluster_id") or ""): str(
            row.get("canonical_embedding_text") or ""
        )
        for row in combined_registry.get("clusters") or []
        if isinstance(row, Mapping)
    }
    expected_rankings = _ranking_rows(ranking_artifact)
    expected_pairs = set(expected_rankings)
    expected_cluster_ids_by_pair = {
        pair: {
            str(candidate.get("cluster_id") or "")
            for candidate in (row.get("candidates") or [])
            if isinstance(candidate, Mapping)
        }
        for pair, row in expected_rankings.items()
    }

    reviewer = packet.get("reviewer") or {}
    items = packet.get("reviewer_items")
    sealed_mapping = packet.get("sealed_mapping") or {}
    sealed_items = sealed_mapping.get("items")
    if (
        reviewer.get("cohort") != OWNER_COHORT
        or reviewer.get("logical_retrieval_unit") != "graph_evidence_cluster"
        or not isinstance(items, list)
        or not isinstance(sealed_items, list)
        or sealed_mapping.get("schema_version") != SEALED_MAPPING_SCHEMA_VERSION
        or sealed_mapping.get("distribution_forbidden") is not True
        or sealed_mapping.get("ranking_identity_sha256")
        != ranking_artifact.get("ranking_identity_sha256")
    ):
        issues.append("PACKET_SHAPE")
        items = []
        sealed_items = []
    if len(items) != 66 or len(sealed_items) != 66:
        issues.append("ITEM_DENOMINATOR")
    if reviewer.get("item_count") != 66:
        issues.append("DECLARED_ITEM_DENOMINATOR")
    if reviewer.get("candidate_judgment_count") != 600:
        issues.append("DECLARED_CANDIDATE_DENOMINATOR")

    sealed_by_item = {
        str(row.get("item_ref") or ""): row
        for row in sealed_items
        if isinstance(row, Mapping)
    }
    if len(sealed_by_item) != len(sealed_items):
        issues.append("SEALED_ITEM_REFS")
    visible_item_refs: set[str] = set()
    observed_pairs: set[tuple[str, str]] = set()
    observed_rankings: dict[str, list[str]] = {}
    candidate_count = 0
    forbidden_values = set(queries) | set(clusters) | {
        str(query.get("target_profile_id") or "") for query in queries.values()
    }
    forbidden_values.discard("")
    for item in items:
        if not isinstance(item, Mapping):
            issues.append("VISIBLE_ITEM_SHAPE")
            continue
        item_ref = str(item.get("item_ref") or "")
        if set(item) != _VISIBLE_ITEM_KEYS or not _OPAQUE_ITEM_RE.fullmatch(item_ref):
            issues.append(f"VISIBLE_ITEM_KEYS:{item_ref or 'missing'}")
        if item_ref in visible_item_refs:
            issues.append(f"DUPLICATE_ITEM_REF:{item_ref}")
        visible_item_refs.add(item_ref)
        if unsafe_reviewer_keys(item):
            issues.append(f"UNSAFE_VISIBLE_KEYS:{item_ref}")
        serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if any(value in serialized for value in forbidden_values):
            issues.append(f"AUTHORITY_ID_LEAK:{item_ref}")
        sealed = sealed_by_item.get(item_ref)
        if sealed is None:
            issues.append(f"MISSING_SEALED_ITEM:{item_ref}")
            continue
        query_id = str(sealed.get("query_id") or "")
        section_id = str(sealed.get("section_id") or "")
        pair = (query_id, section_id)
        if pair not in expected_pairs or pair in observed_pairs:
            issues.append(f"SEALED_PAIR:{item_ref}")
            continue
        observed_pairs.add(pair)
        query = queries.get(query_id)
        if query is None:
            issues.append(f"SEALED_QUERY:{item_ref}")
            continue
        try:
            expected_context = _target_context(root, query)
        except FullResumeQrelW3Error:
            expected_context = ""
            issues.append(f"TARGET_CONTEXT_BINDING:{item_ref}")
        if (
            item.get("target_context") != expected_context
            or item.get("resume_section") != _section_title(section_id)
            or item.get("section_prompt") != _section_prompt(section_id)
        ):
            issues.append(f"VISIBLE_CONTEXT_BINDING:{item_ref}")
        visible_candidates = item.get("candidates")
        sealed_candidates = sealed.get("candidates")
        if (
            not isinstance(visible_candidates, list)
            or not isinstance(sealed_candidates, list)
            or item.get("candidate_count") != len(visible_candidates)
            or len(visible_candidates) != len(sealed_candidates)
        ):
            issues.append(f"CANDIDATE_SHAPE:{item_ref}")
            continue
        visible_refs: list[str] = []
        clusters_by_visible_order: list[str] = []
        ranks: list[object] = []
        for visible, sealed_candidate in zip(visible_candidates, sealed_candidates, strict=True):
            if not isinstance(visible, Mapping) or not isinstance(sealed_candidate, Mapping):
                issues.append(f"CANDIDATE_ROW_SHAPE:{item_ref}")
                continue
            candidate_ref = str(visible.get("candidate_ref") or "")
            cluster_id = str(sealed_candidate.get("cluster_id") or "")
            if set(visible) != _VISIBLE_CANDIDATE_KEYS or not _OPAQUE_CANDIDATE_RE.fullmatch(
                candidate_ref
            ):
                issues.append(f"VISIBLE_CANDIDATE_KEYS:{item_ref}")
            if candidate_ref != str(sealed_candidate.get("candidate_ref") or ""):
                issues.append(f"CANDIDATE_REFERENCE_BINDING:{item_ref}")
            if visible.get("evidence_cluster_text") != clusters.get(cluster_id):
                issues.append(f"EVIDENCE_TEXT_BINDING:{item_ref}")
            visible_refs.append(candidate_ref)
            clusters_by_visible_order.append(cluster_id)
            ranks.append(sealed_candidate.get("frozen_rank"))
        if len(visible_refs) != len(set(visible_refs)):
            issues.append(f"DUPLICATE_CANDIDATE_REF:{item_ref}")
        if set(clusters_by_visible_order) != expected_cluster_ids_by_pair[pair]:
            issues.append(f"FINITE_UNIVERSE:{item_ref}")
        if not all(isinstance(rank, int) and not isinstance(rank, bool) for rank in ranks) or sorted(
            ranks
        ) != list(range(1, len(ranks) + 1)):
            issues.append(f"RANK_CONSERVATION:{item_ref}")
        else:
            observed_rankings[f"{query_id}|{section_id}"] = [
                str(row.get("cluster_id") or "")
                for row in sorted(sealed_candidates, key=lambda row: int(row["frozen_rank"]))
            ]
        candidate_count += len(visible_candidates)
    if visible_item_refs != set(sealed_by_item):
        issues.append("VISIBLE_SEALED_ITEM_PARITY")
    if observed_pairs != expected_pairs:
        issues.append("PAIR_DENOMINATOR")
    if candidate_count != 600:
        issues.append("CANDIDATE_DENOMINATOR")
    if ranking_identity_sha256(observed_rankings) != ranking_artifact.get(
        "ranking_identity_sha256"
    ):
        issues.append("RANKING_IDENTITY")
    if issues:
        raise FullResumeQrelW3Error(
            f"Invalid W3 blinded packet: {sorted(set(issues))}"
        )


def _validate_w2_receipt(receipt: Mapping[str, Any]) -> None:
    unsigned = dict(receipt)
    digest = unsigned.pop("receipt_sha256", None)
    if (
        receipt.get("schema_version") != W2_RECEIPT_SCHEMA_VERSION
        or receipt.get("status") != W2_RECEIPT_STATUS
        or receipt.get("result_label") != RESULT_LABEL
        or not isinstance(digest, str)
        or canonical_sha256(unsigned) != digest
    ):
        raise FullResumeQrelW3Error("W2 receipt is invalid")
    if (receipt.get("reviewer_visibility") or {}) != {
        "ranks_or_scores_distributed": False,
        "sealed_mapping_visible_to_reviewer": False,
    }:
        raise FullResumeQrelW3Error("W2 reviewer-visibility boundary drifted")
    if (receipt.get("scope_guards") or {}).get("human_qrels_created") is not False:
        raise FullResumeQrelW3Error("W2 receipt unexpectedly contains human QRELs")


def _w2_receipt_path(root: Path, supplied: Path | str | None) -> Path:
    if supplied is not None:
        path = _resolve_repository_path(root, supplied)
        if not path.is_file():
            raise FullResumeQrelW3Error(f"W2 receipt is missing: {path}")
        return path
    candidates = sorted(
        (root / ".runtime/c03-owner-solo-qrel/w2").glob("w2_ranking_receipt.*.json")
    )
    if len(candidates) != 1:
        raise FullResumeQrelW3Error(
            "exactly one W2 receipt is required; pass --w2-receipt explicitly"
        )
    return candidates[0]


def load_w3_source_context(
    repo_root: Path | str, *, w2_receipt_path: Path | str | None = None
) -> dict[str, Any]:
    """Load and revalidate W2, W1C, and the combined registry without a model run."""

    root = Path(repo_root).resolve()
    contract = load_w3_review_contract(root)
    receipt_path = _w2_receipt_path(root, w2_receipt_path)
    receipt = _read_json(receipt_path)
    _validate_w2_receipt(receipt)

    query_record = receipt.get("query_manifest") or {}
    ranking_record = receipt.get("rankings") or {}
    query_path = _resolve_repository_path(root, str(query_record.get("path") or ""))
    ranking_path = _resolve_repository_path(root, str(ranking_record.get("path") or ""))
    if (
        not query_path.is_file()
        or _file_sha256(query_path) != query_record.get("file_sha256")
        or not ranking_path.is_file()
        or _file_sha256(ranking_path) != ranking_record.get("file_sha256")
    ):
        raise FullResumeQrelW3Error("W2 receipt file binding failed")
    query_manifest = _read_json(query_path)
    ranking_artifact = _read_json(ranking_path)
    if (
        query_manifest.get("schema_version") != QUERY_MANIFEST_SCHEMA_VERSION
        or query_manifest.get("status") != QUERY_MANIFEST_STATUS
        or validate_w2_query_manifest(query_manifest, root)
    ):
        raise FullResumeQrelW3Error("W2 query manifest is invalid")
    if (
        query_manifest.get("query_manifest_sha256")
        != query_record.get("query_manifest_sha256")
        or ranking_artifact.get("ranking_artifact_sha256")
        != ranking_record.get("ranking_artifact_sha256")
        or ranking_artifact.get("ranking_identity_sha256")
        != ranking_record.get("ranking_identity_sha256")
    ):
        raise FullResumeQrelW3Error("W2 receipt identity binding failed")
    if (
        ranking_artifact.get("schema_version") != RANKING_SCHEMA_VERSION
        or ranking_artifact.get("status") != RANKING_STATUS
    ):
        raise FullResumeQrelW3Error("W2 frozen ranking status is invalid")

    source = ranking_artifact.get("source_authority") or {}
    w1c_receipt_path = _resolve_repository_path(
        root, str(source.get("w1c_receipt_path") or "")
    )
    w1c_receipt = _read_json(w1c_receipt_path)
    w1c_unsigned = dict(w1c_receipt)
    w1c_digest = w1c_unsigned.pop("receipt_sha256", None)
    if (
        not isinstance(w1c_digest, str)
        or canonical_sha256(w1c_unsigned) != w1c_digest
        or w1c_digest != source.get("w1c_receipt_sha256")
    ):
        raise FullResumeQrelW3Error("W1C receipt binding failed")
    combined_record = w1c_receipt.get("combined_registry") or {}
    combined_path = _resolve_repository_path(root, str(combined_record.get("path") or ""))
    if (
        not combined_path.is_file()
        or _file_sha256(combined_path) != combined_record.get("file_sha256")
    ):
        raise FullResumeQrelW3Error("W1C combined registry file binding failed")
    combined_registry = _read_json(combined_path)
    combined_issues = validate_combined_registry(combined_registry, root)
    if combined_issues:
        raise FullResumeQrelW3Error(
            f"W1C combined registry is invalid: {combined_issues}"
        )
    if (
        combined_registry.get("combined_registry_sha256")
        != combined_record.get("combined_registry_sha256")
        or combined_registry.get("combined_registry_sha256")
        != source.get("combined_registry_sha256")
    ):
        raise FullResumeQrelW3Error("W1C combined registry digest binding failed")
    projection = w1c_receipt.get("projection") or {}
    w1c_context = {
        "combined": combined_registry,
        "receipt_path": w1c_receipt_path,
        "receipt": w1c_receipt,
        "projection": projection,
    }
    ranking_issues = validate_frozen_ranking_artifact(
        ranking_artifact,
        query_manifest=query_manifest,
        w1c_context=w1c_context,
        model_manifest=_PINNED_MODEL,
        repo_root=root,
    )
    if ranking_issues:
        raise FullResumeQrelW3Error(
            f"W2 frozen ranking is invalid: {ranking_issues}"
        )
    return {
        "root": root,
        "contract": contract,
        "w2_receipt_path": receipt_path,
        "w2_receipt": receipt,
        "query_manifest_path": query_path,
        "query_manifest": query_manifest,
        "ranking_path": ranking_path,
        "ranking_artifact": ranking_artifact,
        "w1c_receipt_path": w1c_receipt_path,
        "w1c_receipt": w1c_receipt,
        "combined_registry_path": combined_path,
        "combined_registry": combined_registry,
    }


def _packet_manifest(
    content: Mapping[str, Any],
    *,
    review_items_file_sha256: str,
    sealed_mapping_file_sha256: str,
    reviewer_manifest_file_sha256: str,
    reviewer_manifest_sha256: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "result_label": RESULT_LABEL,
        "authority_bindings": dict(content["authority_bindings"]),
        "blinding": dict(content["blinding"]),
        "reviewer": dict(content["reviewer"]),
        "sealed_mapping": {
            "schema_version": SEALED_MAPPING_SCHEMA_VERSION,
            "distribution_forbidden": True,
            "ranking_identity_sha256": content["authority_bindings"][
                "ranking_identity_sha256"
            ],
        },
        "files": {
            "review_items_file_sha256": review_items_file_sha256,
            "sealed_mapping_file_sha256": sealed_mapping_file_sha256,
            "reviewer_manifest_file_sha256": reviewer_manifest_file_sha256,
            "reviewer_manifest_sha256": reviewer_manifest_sha256,
        },
        "scope_guards": dict(content["scope_guards"]),
    }
    payload["packet_manifest_sha256"] = canonical_sha256(payload)
    return payload


def _reviewer_manifest(
    content: Mapping[str, Any], *, review_items_file_sha256: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": REVIEWER_MANIFEST_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "cohort": OWNER_COHORT,
        "review_item_count": int(content["reviewer"]["item_count"]),
        "candidate_judgment_count": int(
            content["reviewer"]["candidate_judgment_count"]
        ),
        "review_items_file_sha256": review_items_file_sha256,
        "reviewer_visible_only": True,
        "ranks_scores_splits_cluster_ids_and_model_choice_present": False,
        "human_grades_present": False,
        "reviewer_manifest_sha256": "",
    }
    payload["reviewer_manifest_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "reviewer_manifest_sha256"}
    )
    return payload


def _receipt(
    *,
    context: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    packet_manifest_file_sha256: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": RECEIPT_STATUS,
        "result_label": RESULT_LABEL,
        "source": {
            "w2_receipt_sha256": context["w2_receipt"]["receipt_sha256"],
            "query_manifest_sha256": context["query_manifest"]["query_manifest_sha256"],
            "ranking_artifact_sha256": context["ranking_artifact"]["ranking_artifact_sha256"],
            "ranking_identity_sha256": context["ranking_artifact"][
                "ranking_identity_sha256"
            ],
            "combined_registry_sha256": context["combined_registry"][
                "combined_registry_sha256"
            ],
        },
        "packet": {
            "packet_manifest_sha256": packet_manifest["packet_manifest_sha256"],
            "packet_manifest_file_sha256": packet_manifest_file_sha256,
            "review_item_count": packet_manifest["reviewer"]["item_count"],
            "candidate_judgment_count": packet_manifest["reviewer"][
                "candidate_judgment_count"
            ],
            "reviewer_visible_rank_score_split_cluster_or_model_leakage": False,
            "sealed_mapping_distributed": False,
        },
        "review_progress": {
            "completed_human_judgment_count": 0,
            "remaining_human_judgment_count": 600,
            "human_grades_created": False,
        },
        "scope_guards": {
            "metrics_computable": False,
            "authoritative_release_qualification_satisfied": False,
            "activation_manifest_created": False,
            "production_promotion_authorized": False,
        },
        "next_action": "W3_START_BLINDED_OWNER_REVIEW_UI",
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return payload


def _validate_w3_receipt(
    receipt: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    packet_manifest_file_sha256: str,
) -> None:
    """Validate the static W3 readiness receipt without reading a human ledger."""

    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    expected = _receipt(
        context=context,
        packet_manifest=packet_manifest,
        packet_manifest_file_sha256=packet_manifest_file_sha256,
    )
    if (
        not isinstance(supplied, str)
        or canonical_sha256(unsigned) != supplied
        or receipt != expected
    ):
        raise FullResumeQrelW3Error("W3 packet receipt is invalid")


def _validate_reviewer_manifest(
    manifest: Mapping[str, Any], *, items_file_sha256: str
) -> None:
    unsigned = dict(manifest)
    supplied = unsigned.pop("reviewer_manifest_sha256", None)
    expected = {
        "schema_version": REVIEWER_MANIFEST_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "cohort": OWNER_COHORT,
        "review_item_count": 66,
        "candidate_judgment_count": 600,
        "review_items_file_sha256": items_file_sha256,
        "reviewer_visible_only": True,
        "ranks_scores_splits_cluster_ids_and_model_choice_present": False,
        "human_grades_present": False,
    }
    if unsigned != expected or not isinstance(supplied, str) or canonical_sha256(unsigned) != supplied:
        raise FullResumeQrelW3Error("W3 reviewer manifest is invalid")


def _validate_packet_manifest(manifest: Mapping[str, Any]) -> None:
    unsigned = dict(manifest)
    supplied = unsigned.pop("packet_manifest_sha256", None)
    if (
        manifest.get("schema_version") != PACKET_SCHEMA_VERSION
        or manifest.get("status") != PACKET_STATUS
        or manifest.get("result_label") != RESULT_LABEL
        or not isinstance(supplied, str)
        or canonical_sha256(unsigned) != supplied
    ):
        raise FullResumeQrelW3Error("W3 packet manifest is invalid")


def _packet_paths(packet_dir: Path, packet_manifest_sha256: str | None = None) -> dict[str, Path]:
    if packet_manifest_sha256 is None:
        manifests = sorted(packet_dir.glob("packet_manifest.*.json"))
        if len(manifests) != 1:
            raise FullResumeQrelW3Error("exactly one W3 packet manifest is required")
        packet_manifest = manifests[0]
    else:
        packet_manifest = packet_dir / f"packet_manifest.{packet_manifest_sha256}.json"
    reviewer_dir = packet_dir / OWNER_COHORT
    reviewer_manifests = sorted(reviewer_dir.glob("reviewer_manifest.*.json"))
    if len(reviewer_manifests) != 1:
        raise FullResumeQrelW3Error("exactly one W3 reviewer manifest is required")
    return {
        "packet_manifest": packet_manifest,
        "review_items": reviewer_dir / "review_items.jsonl",
        "reviewer_manifest": reviewer_manifests[0],
        "sealed_mapping": packet_dir
        / "sealed_internal"
        / "identity_and_rank_mapping.v1.json",
        "nonce": packet_dir / "sealed_internal" / "blinding_nonce.v1.txt",
    }


def validate_w3_packet_on_disk(
    repo_root: Path | str,
    *,
    packet_dir: Path | str | None = None,
    w2_receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    """Re-read all packet files and prove reviewer-visible blinding end to end."""

    context = load_w3_source_context(repo_root, w2_receipt_path=w2_receipt_path)
    root = context["root"]
    directory = _resolve_repository_path(root, packet_dir or DEFAULT_PACKET_DIR)
    paths = _packet_paths(directory)
    manifest = _read_json(paths["packet_manifest"])
    _validate_packet_manifest(manifest)
    if manifest.get("authority_bindings") != _expected_bindings(
        context["query_manifest"], context["ranking_artifact"]
    ):
        raise FullResumeQrelW3Error("W3 packet source binding drifted")
    expected_visible_files = {
        "review_items.jsonl",
        paths["reviewer_manifest"].name,
    }
    observed_visible_files = {
        path.name for path in (directory / OWNER_COHORT).iterdir() if path.is_file()
    }
    if observed_visible_files != expected_visible_files:
        raise FullResumeQrelW3Error("W3 reviewer directory contains an unexpected file")
    files = manifest.get("files") or {}
    if (
        _file_sha256(paths["packet_manifest"])
        != manifest.get("packet_manifest_file_sha256", _file_sha256(paths["packet_manifest"]))
    ):
        # The optional field is not used in the immutable canonical digest.  This
        # branch only protects a malformed hand-edited manifest.
        raise FullResumeQrelW3Error("W3 packet manifest file digest is invalid")
    if (
        _file_sha256(paths["review_items"])
        != files.get("review_items_file_sha256")
        or _file_sha256(paths["sealed_mapping"])
        != files.get("sealed_mapping_file_sha256")
        or _file_sha256(paths["reviewer_manifest"])
        != files.get("reviewer_manifest_file_sha256")
    ):
        raise FullResumeQrelW3Error("W3 packet file digest binding failed")
    reviewer_manifest = _read_json(paths["reviewer_manifest"])
    _validate_reviewer_manifest(
        reviewer_manifest, items_file_sha256=_file_sha256(paths["review_items"])
    )
    if reviewer_manifest.get("reviewer_manifest_sha256") != files.get(
        "reviewer_manifest_sha256"
    ):
        raise FullResumeQrelW3Error("W3 reviewer manifest digest binding failed")
    nonce = paths["nonce"].read_text(encoding="utf-8").strip()
    if blinding_nonce_commitment(nonce) != (manifest.get("blinding") or {}).get(
        "nonce_commitment"
    ):
        raise FullResumeQrelW3Error("W3 blinding nonce commitment failed")
    items = _read_jsonl(paths["review_items"])
    sealed = _read_json(paths["sealed_mapping"])
    content = {
        "schema_version": manifest["schema_version"],
        "status": manifest["status"],
        "result_label": manifest["result_label"],
        "authority_bindings": manifest["authority_bindings"],
        "blinding": manifest["blinding"],
        "reviewer": manifest["reviewer"],
        "reviewer_items": items,
        "sealed_mapping": sealed,
        "scope_guards": manifest["scope_guards"],
    }
    validate_w3_packet_content(
        content,
        repo_root=root,
        query_manifest=context["query_manifest"],
        combined_registry=context["combined_registry"],
        ranking_artifact=context["ranking_artifact"],
    )
    return {
        "status": RECEIPT_STATUS,
        "packet_manifest_sha256": manifest["packet_manifest_sha256"],
        "packet_manifest_file_sha256": _file_sha256(paths["packet_manifest"]),
        "reviewer_item_count": len(items),
        "candidate_judgment_count": sum(
            int(item["candidate_count"]) for item in items
        ),
        "reviewer_visible_rank_score_split_cluster_or_model_leakage": False,
        "human_grades_present": False,
        "paths": {key: _repository_path(root, value) for key, value in paths.items()},
    }


def validate_w3_readiness_receipt(
    repo_root: Path | str,
    *,
    packet_dir: Path | str | None = None,
    w2_receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate the W3 packet *and* its immutable zero-return readiness receipt."""

    context = load_w3_source_context(repo_root, w2_receipt_path=w2_receipt_path)
    root = context["root"]
    directory = _resolve_repository_path(root, packet_dir or DEFAULT_PACKET_DIR)
    validation = validate_w3_packet_on_disk(
        root, packet_dir=directory, w2_receipt_path=w2_receipt_path
    )
    manifest_path = directory / f"packet_manifest.{validation['packet_manifest_sha256']}.json"
    packet_manifest = _read_json(manifest_path)
    matching_receipts: list[tuple[Path, dict[str, Any]]] = []
    for candidate in sorted(directory.parent.glob("w3_packet_receipt.*.json")):
        receipt_candidate = _read_json(candidate)
        if (receipt_candidate.get("packet") or {}).get("packet_manifest_sha256") == validation[
            "packet_manifest_sha256"
        ]:
            matching_receipts.append((candidate, receipt_candidate))
    if len(matching_receipts) != 1:
        raise FullResumeQrelW3Error("W3 packet readiness receipt is missing or ambiguous")
    receipt_path, receipt = matching_receipts[0]
    _validate_w3_receipt(
        receipt,
        context=context,
        packet_manifest=packet_manifest,
        packet_manifest_file_sha256=_file_sha256(manifest_path),
    )
    return {
        **validation,
        "readiness_receipt_sha256": receipt["receipt_sha256"],
        "readiness_receipt_path": _repository_path(root, receipt_path),
    }


def materialize_w3_packet(
    repo_root: Path | str,
    *,
    packet_dir: Path | str | None = None,
    w2_receipt_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Path]]:
    """Create the immutable W3 packet, or revalidate an identical prior packet."""

    context = load_w3_source_context(repo_root, w2_receipt_path=w2_receipt_path)
    root = context["root"]
    directory = _resolve_repository_path(root, packet_dir or DEFAULT_PACKET_DIR)
    if directory.exists() and any(directory.iterdir()):
        validation = validate_w3_packet_on_disk(
            root, packet_dir=directory, w2_receipt_path=w2_receipt_path
        )
        manifest = _read_json(directory / f"packet_manifest.{validation['packet_manifest_sha256']}.json")
        if manifest.get("authority_bindings") != _expected_bindings(
            context["query_manifest"], context["ranking_artifact"]
        ):
            raise FullResumeQrelW3Error("Existing W3 packet is bound to another W2 ranking")
        manifest_path = directory / f"packet_manifest.{validation['packet_manifest_sha256']}.json"
        packet_manifest = _read_json(manifest_path)
        matching_receipts: list[tuple[Path, dict[str, Any]]] = []
        for candidate in sorted(directory.parent.glob("w3_packet_receipt.*.json")):
            receipt_candidate = _read_json(candidate)
            if (receipt_candidate.get("packet") or {}).get(
                "packet_manifest_sha256"
            ) == validation["packet_manifest_sha256"]:
                matching_receipts.append((candidate, receipt_candidate))
        if len(matching_receipts) != 1:
            raise FullResumeQrelW3Error("Existing W3 packet receipt is missing or ambiguous")
        receipt_path, receipt = matching_receipts[0]
        _validate_w3_receipt(
            receipt,
            context=context,
            packet_manifest=packet_manifest,
            packet_manifest_file_sha256=_file_sha256(manifest_path),
        )
        return receipt, {
            key: _resolve_repository_path(root, value)
            for key, value in validation["paths"].items()
        }

    nonce_path = directory / "sealed_internal" / "blinding_nonce.v1.txt"
    nonce = os.urandom(32).hex()
    _immutable_bytes(nonce_path, (nonce + "\n").encode("ascii"))
    content = build_w3_packet_content(
        repo_root=root,
        query_manifest=context["query_manifest"],
        combined_registry=context["combined_registry"],
        ranking_artifact=context["ranking_artifact"],
        blinding_nonce=nonce,
    )
    review_items_path = directory / OWNER_COHORT / "review_items.jsonl"
    sealed_path = directory / "sealed_internal" / "identity_and_rank_mapping.v1.json"
    review_items_sha = _immutable_bytes(
        review_items_path, _jsonl_bytes(content["reviewer_items"])
    )
    sealed_sha = _immutable_json(sealed_path, content["sealed_mapping"])
    reviewer_manifest = _reviewer_manifest(
        content, review_items_file_sha256=review_items_sha
    )
    reviewer_manifest_path = (
        directory
        / OWNER_COHORT
        / f"reviewer_manifest.{reviewer_manifest['reviewer_manifest_sha256']}.json"
    )
    reviewer_manifest_file_sha = _immutable_json(
        reviewer_manifest_path, reviewer_manifest
    )
    manifest = _packet_manifest(
        content,
        review_items_file_sha256=review_items_sha,
        sealed_mapping_file_sha256=sealed_sha,
        reviewer_manifest_file_sha256=reviewer_manifest_file_sha,
        reviewer_manifest_sha256=reviewer_manifest["reviewer_manifest_sha256"],
    )
    manifest_path = directory / f"packet_manifest.{manifest['packet_manifest_sha256']}.json"
    manifest_file_sha = _immutable_json(manifest_path, manifest)
    receipt = _receipt(
        context=context,
        packet_manifest=manifest,
        packet_manifest_file_sha256=manifest_file_sha,
    )
    receipt_path = directory.parent / f"w3_packet_receipt.{receipt['receipt_sha256']}.json"
    _immutable_json(receipt_path, receipt)
    validation = validate_w3_packet_on_disk(
        root, packet_dir=directory, w2_receipt_path=w2_receipt_path
    )
    if validation["packet_manifest_sha256"] != manifest["packet_manifest_sha256"]:
        raise FullResumeQrelW3Error("W3 packet validation returned another packet")
    _validate_w3_receipt(
        receipt,
        context=context,
        packet_manifest=manifest,
        packet_manifest_file_sha256=manifest_file_sha,
    )
    return receipt, {
        "packet_dir": directory,
        "packet_manifest": manifest_path,
        "review_items": review_items_path,
        "reviewer_manifest": reviewer_manifest_path,
        "sealed_mapping": sealed_path,
        "receipt": receipt_path,
    }


__all__ = [
    "DEFAULT_PACKET_DIR",
    "CONTRACT_PATH",
    "OWNER_COHORT",
    "PACKET_STATUS",
    "RECEIPT_STATUS",
    "RUNTIME_DIR",
    "FullResumeQrelW3Error",
    "blinding_nonce_commitment",
    "build_w3_packet_content",
    "load_w3_review_contract",
    "load_w3_source_context",
    "materialize_w3_packet",
    "validate_w3_packet_content",
    "validate_w3_packet_on_disk",
    "validate_w3_readiness_receipt",
    "validate_w3_review_contract",
]
