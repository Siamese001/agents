"""Governed W8 prelabel packets for C0.3 cluster semantic review."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_human_eval._safety import unsafe_reviewer_keys
from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    ranking_identity_sha256,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path(
    "src/apps_rg/evals/c03_graph_evidence_cluster_review_packet_contract.v1.json"
)
ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_evidence_cluster_embeddings")
W8_RECEIPT_PATH = ARTIFACT_DIR / "wave8_prelabel_review_packet_receipt.json"

CONTRACT_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_review_packet_contract.v1"
)
PACKET_SCHEMA_VERSION = "apps_rg.c03_graph_evidence_cluster_review_packet.v1"
REVIEW_ITEM_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_review_item.v1"
)
SEALED_MAPPING_SCHEMA_VERSION = (
    "apps_rg.c03_graph_evidence_cluster_review_mapping.v1"
)
RECEIPT_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_w8_receipt.v1"
W8_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_W8_PRELABEL_PACKET_READY"

COHORTS = ("reviewer_a", "reviewer_b")
_NONCE_RE = re.compile(r"[0-9a-f]{64}")


class ClusterReviewPacketError(ValueError):
    """Raised when a W8 packet violates its frozen prelabel contract."""


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _is_git_sha(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))


def validate_review_packet_contract(contract: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("schema_version")
    if contract.get("wave") != "W8" or contract.get("status") != "FROZEN":
        issues.append("wave_or_status")
    packet = contract.get("review_packet") or {}
    expected_counts = {
        "query_count": 6,
        "section_count": 8,
        "query_section_count_per_cohort": 48,
        "candidate_judgment_count_per_cohort": 456,
        "reviewer_cohort_count": 2,
        "total_reviewer_judgment_slots": 912,
    }
    for field, value in expected_counts.items():
        if packet.get(field) != value:
            issues.append(f"review_packet.{field}")
    required_true = (
        ("source_authority", "wave7_receipt_required"),
        ("source_authority", "frozen_ranking_identity_required"),
        ("review_packet", "full_candidate_denominator_required"),
        ("review_packet", "independent_candidate_order_per_cohort_required"),
        ("blinding", "secret_nonce_file_required"),
        ("blinding", "opaque_query_and_candidate_ids_required"),
        ("blinding", "ranks_scores_and_model_selections_forbidden"),
        ("blinding", "graph_ids_forbidden_in_reviewer_payloads"),
        ("label_authority", "two_distinct_human_reviewers_still_required"),
        ("label_authority", "distinct_human_adjudicator_still_required"),
        ("publication_boundary", "full_packet_runtime_only"),
        ("publication_boundary", "sealed_mapping_never_distributed"),
        ("activation_boundary", "qualification_is_not_activation"),
    )
    for section, field in required_true:
        if (contract.get(section) or {}).get(field) is not True:
            issues.append(f"{section}.{field}")
    required_false = (
        ("label_authority", "labels_created_by_wave8"),
        ("label_authority", "human_review_authority_created_by_wave8"),
        ("publication_boundary", "reviewer_payloads_committed"),
        ("activation_boundary", "semantic_retrieval_qualified"),
        ("activation_boundary", "activation_manifest_created"),
        ("activation_boundary", "production_promotion_authorized"),
    )
    for section, field in required_false:
        if (contract.get(section) or {}).get(field) is not False:
            issues.append(f"{section}.{field}")
    if issues:
        raise ClusterReviewPacketError(
            f"Invalid W8 review-packet contract: {sorted(set(issues))}"
        )


def blinding_nonce_commitment(nonce: str) -> str:
    value = str(nonce or "").strip()
    if not _NONCE_RE.fullmatch(value):
        raise ClusterReviewPacketError(
            "blinding nonce must contain exactly 64 lowercase hex characters"
        )
    return hashlib.sha256(
        b"apps_rg.c03.cluster_review_packet.nonce.v1\x00" + bytes.fromhex(value)
    ).hexdigest()


def _blind_digest(nonce: str, purpose: str, *parts: str) -> str:
    commitment = blinding_nonce_commitment(nonce)
    del commitment
    message = json.dumps(
        {"purpose": purpose, "parts": list(parts)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(bytes.fromhex(nonce), message, hashlib.sha256).hexdigest()


def _query_texts(
    query_manifest: Mapping[str, Any], repository_root: Path | str
) -> dict[str, str]:
    root = Path(repository_root).resolve()
    result: dict[str, str] = {}
    for query in query_manifest.get("queries") or []:
        query_id = str(query["query_id"])
        jd = (root / str(query["jd_path"])).read_text(encoding="utf-8").strip()
        brief = (root / str(query["brief_path"])).read_text(encoding="utf-8").strip()
        result[query_id] = f"Target role description:\n{jd}\n\nApplication brief:\n{brief}"
    return result


def build_prelabel_packet_content(
    *,
    query_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    rankings: Mapping[str, Sequence[str]],
    ranking_identity_sha256: str,
    authority_bindings: Mapping[str, str],
    blinding_nonce: str,
    repository_root: Path | str,
) -> dict[str, Any]:
    """Build two blinded cohorts and the non-distributable join mapping."""

    nonce_commitment = blinding_nonce_commitment(blinding_nonce)
    texts = _query_texts(query_manifest, repository_root)
    clusters = {
        str(row["cluster_id"]): str(row["canonical_embedding_text"])
        for row in registry.get("clusters") or []
    }
    cohort_items: dict[str, list[dict[str, Any]]] = {cohort: [] for cohort in COHORTS}
    sealed_cohorts: dict[str, list[dict[str, Any]]] = {
        cohort: [] for cohort in COHORTS
    }
    for cohort in COHORTS:
        for pair in sorted(rankings):
            query_id, section_id = pair.split("|", 1)
            item_ref = "item-" + _blind_digest(
                blinding_nonce, f"item:{cohort}", query_id, section_id
            )[:24]
            query_ref = "query-" + _blind_digest(
                blinding_nonce, f"query:{cohort}", query_id
            )[:24]
            candidate_rows: list[tuple[str, str, str, int]] = []
            for rank, cluster_id in enumerate(rankings[pair], start=1):
                candidate_ref = "candidate-" + _blind_digest(
                    blinding_nonce,
                    f"candidate:{cohort}",
                    query_id,
                    section_id,
                    str(cluster_id),
                )[:24]
                order_key = _blind_digest(
                    blinding_nonce,
                    f"candidate-order:{cohort}",
                    query_id,
                    section_id,
                    str(cluster_id),
                )
                candidate_rows.append(
                    (order_key, candidate_ref, str(cluster_id), rank)
                )
            candidate_rows.sort(key=lambda row: row[0])
            cohort_items[cohort].append(
                {
                    "schema_version": REVIEW_ITEM_SCHEMA_VERSION,
                    "item_ref": item_ref,
                    "query_ref": query_ref,
                    "target_context": texts[query_id],
                    "resume_section": section_id,
                    "candidate_count": len(candidate_rows),
                    "candidates": [
                        {
                            "candidate_ref": candidate_ref,
                            "evidence_cluster_text": clusters[cluster_id],
                        }
                        for _, candidate_ref, cluster_id, _ in candidate_rows
                    ],
                }
            )
            sealed_cohorts[cohort].append(
                {
                    "item_ref": item_ref,
                    "query_ref": query_ref,
                    "query_id": query_id,
                    "section_id": section_id,
                    "candidates": [
                        {
                            "candidate_ref": candidate_ref,
                            "cluster_id": cluster_id,
                            "frozen_rank": rank,
                        }
                        for _, candidate_ref, cluster_id, rank in candidate_rows
                    ],
                }
            )
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": "FROZEN_UNLABELED_PRELABEL",
        "authority_bindings": dict(authority_bindings),
        "ranking_identity_sha256": ranking_identity_sha256,
        "blinding_nonce_commitment": nonce_commitment,
        "cohorts": cohort_items,
        "sealed_mapping": {
            "schema_version": SEALED_MAPPING_SCHEMA_VERSION,
            "distribution_forbidden": True,
            "ranking_identity_sha256": ranking_identity_sha256,
            "cohorts": sealed_cohorts,
        },
    }
    validate_prelabel_packet_content(
        packet, query_manifest=query_manifest, registry=registry
    )
    return packet


def validate_prelabel_packet_content(
    packet: Mapping[str, Any],
    *,
    query_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> None:
    issues: list[str] = []
    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        issues.append("schema_version")
    if packet.get("status") != "FROZEN_UNLABELED_PRELABEL":
        issues.append("status")
    if not _is_sha256(packet.get("ranking_identity_sha256")):
        issues.append("ranking_identity_sha256")
    if not _is_sha256(packet.get("blinding_nonce_commitment")):
        issues.append("blinding_nonce_commitment")
    bindings = packet.get("authority_bindings") or {}
    expected_binding_fields = {
        "wave7_receipt_sha256",
        "query_manifest_sha256",
        "registry_sha256",
        "projection_generation_sha256",
    }
    if set(bindings) != expected_binding_fields or any(
        not _is_sha256(value) for value in bindings.values()
    ):
        issues.append("authority_bindings")
    query_ids = {
        str(row["query_id"]) for row in query_manifest.get("queries") or []
    }
    section_ids = {str(value) for value in query_manifest.get("section_ids") or []}
    cluster_ids = {
        str(row["cluster_id"]) for row in registry.get("clusters") or []
    }
    expected_by_pair: dict[tuple[str, str], set[str]] = {
        (query_id, section_id): {
            str(row["cluster_id"])
            for row in registry.get("clusters") or []
            if section_id in {str(value) for value in row.get("allowed_sections") or []}
        }
        for query_id in query_ids
        for section_id in section_ids
    }
    cohorts = packet.get("cohorts") or {}
    sealed_mapping = packet.get("sealed_mapping") or {}
    if sealed_mapping.get("schema_version") != SEALED_MAPPING_SCHEMA_VERSION:
        issues.append("sealed_mapping.schema_version")
    if sealed_mapping.get("ranking_identity_sha256") != packet.get(
        "ranking_identity_sha256"
    ):
        issues.append("sealed_mapping.ranking_identity_sha256")
    sealed = sealed_mapping.get("cohorts") or {}
    orders_by_cohort: dict[str, dict[tuple[str, str], list[str]]] = {}
    rankings_by_cohort: dict[str, dict[str, list[str]]] = {}
    for cohort in COHORTS:
        items = cohorts.get(cohort) or []
        mappings = sealed.get(cohort) or []
        if len(items) != 48 or len(mappings) != 48:
            issues.append(f"{cohort}.item_count")
            continue
        if sum(int(row.get("candidate_count") or 0) for row in items) != 456:
            issues.append(f"{cohort}.candidate_count")
        mapping_by_item = {str(row.get("item_ref")): row for row in mappings}
        if len(mapping_by_item) != len(mappings):
            issues.append(f"{cohort}.duplicate_mapping_item_ref")
        orders_by_cohort[cohort] = {}
        rankings_by_cohort[cohort] = {}
        for item in items:
            item_ref = str(item.get("item_ref") or "")
            if unsafe_reviewer_keys(item):
                issues.append(f"{cohort}.unsafe_keys:{item_ref}")
            serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if any(value in serialized for value in query_ids | cluster_ids):
                issues.append(f"{cohort}.authority_id_leak:{item_ref}")
            mapping = mapping_by_item.get(item_ref)
            if mapping is None:
                issues.append(f"{cohort}.missing_mapping:{item_ref}")
                continue
            visible_refs = [
                str(row.get("candidate_ref")) for row in item.get("candidates") or []
            ]
            if item.get("candidate_count") != len(visible_refs):
                issues.append(f"{cohort}.declared_candidate_count:{item_ref}")
            mapped_refs = [
                str(row.get("candidate_ref"))
                for row in mapping.get("candidates") or []
            ]
            if visible_refs != mapped_refs or len(visible_refs) != len(set(visible_refs)):
                issues.append(f"{cohort}.candidate_conservation:{item_ref}")
            mapped_clusters = [
                str(row.get("cluster_id"))
                for row in mapping.get("candidates") or []
            ]
            if not set(mapped_clusters).issubset(cluster_ids):
                issues.append(f"{cohort}.orphan_cluster:{item_ref}")
            pair = (str(mapping.get("query_id")), str(mapping.get("section_id")))
            if pair not in expected_by_pair:
                issues.append(f"{cohort}.orphan_pair:{item_ref}")
            elif set(mapped_clusters) != expected_by_pair[pair] or len(
                mapped_clusters
            ) != len(set(mapped_clusters)):
                issues.append(f"{cohort}.finite_denominator:{item_ref}")
            ranks = [row.get("frozen_rank") for row in mapping.get("candidates") or []]
            valid_ranks = all(
                isinstance(rank, int) and not isinstance(rank, bool) for rank in ranks
            )
            if not valid_ranks or sorted(ranks) != list(range(1, len(ranks) + 1)):
                issues.append(f"{cohort}.frozen_rank_conservation:{item_ref}")
            else:
                rankings_by_cohort[cohort][f"{pair[0]}|{pair[1]}"] = [
                    str(row["cluster_id"])
                    for row in sorted(
                        mapping.get("candidates") or [],
                        key=lambda row: int(row["frozen_rank"]),
                    )
                ]
            if mapping.get("query_ref") != item.get("query_ref"):
                issues.append(f"{cohort}.query_ref:{item_ref}")
            if pair in orders_by_cohort[cohort]:
                issues.append(f"{cohort}.duplicate_pair:{pair}")
            orders_by_cohort[cohort][pair] = mapped_clusters
        if set(orders_by_cohort[cohort]) != set(expected_by_pair):
            issues.append(f"{cohort}.pair_denominator")
        if ranking_identity_sha256(rankings_by_cohort[cohort]) != packet.get(
            "ranking_identity_sha256"
        ):
            issues.append(f"{cohort}.ranking_identity_sha256")
    shared_pairs = set(orders_by_cohort.get("reviewer_a", {})) & set(
        orders_by_cohort.get("reviewer_b", {})
    )
    if not shared_pairs or all(
        orders_by_cohort["reviewer_a"][pair]
        == orders_by_cohort["reviewer_b"][pair]
        for pair in shared_pairs
    ):
        issues.append("independent_candidate_order")
    if (packet.get("sealed_mapping") or {}).get("distribution_forbidden") is not True:
        issues.append("sealed_mapping.distribution_forbidden")
    if issues:
        raise ClusterReviewPacketError(
            f"Invalid W8 prelabel packet: {sorted(set(issues))}"
        )


def build_w8_receipt(
    *,
    contract: Mapping[str, Any],
    w7_receipt: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    packet_manifest_file_sha256: str,
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W8",
        "status": "PASS_PRELABEL_PACKET_READY",
        "completion_marker": W8_COMPLETION_MARKER,
        "source_baseline": {
            "commit": source_commit,
            "tree": source_tree,
            "wave7_receipt_sha256": w7_receipt["receipt_sha256"],
            "query_manifest_sha256": w7_receipt["query_manifest"][
                "query_manifest_sha256"
            ],
            "wave4_registry_sha256": w7_receipt["source_baseline"][
                "wave4_registry_sha256"
            ],
            "projection_generation_sha256": w7_receipt["source_baseline"][
                "projection_generation_sha256"
            ],
            "ranking_identity_sha256": w7_receipt["diagnostic_proof"][
                "ranking_identity_sha256"
            ],
        },
        "contract": {
            "path": CONTRACT_PATH.as_posix(),
            "canonical_sha256": canonical_sha256(contract),
        },
        "controlled_packet": {
            "packet_manifest_sha256": packet_manifest["manifest_sha256"],
            "packet_manifest_file_sha256": packet_manifest_file_sha256,
            "reviewer_cohort_manifest_sha256": {
                cohort: packet_manifest["cohorts"][cohort]["manifest_sha256"]
                for cohort in COHORTS
            },
            "query_section_count_per_cohort": 48,
            "candidate_judgment_count_per_cohort": 456,
            "reviewer_cohort_count": 2,
            "total_reviewer_judgment_slots": 912,
            "sealed_mapping_present": True,
            "sealed_mapping_distributed": False,
        },
        "label_authority": {
            "human_labels_present": False,
            "synthetic_labels_created": False,
            "reviewer_assignments_authorized": False,
            "human_review_authority_receipt_present": False,
            "adjudication_present": False,
        },
        "scope": {
            "blinded_full_denominator_packet_ready": True,
            "semantic_retrieval_qualified": False,
            "cluster_embedding_activation_created": False,
            "production_promotion_authorized": False,
        },
        "wave_exit_gates": {
            "prelabel_packet": "PASS_W8",
            "two_independent_human_reviews": "OPEN_912_REVIEWER_JUDGMENT_SLOTS",
            "human_adjudication": "OPEN_456_ADJUDICATIONS",
            "semantic_retrieval_qualification": "BLOCKED_QREL_AUTHORITY",
            "release_activation": "BLOCKED_UNTIL_QUALIFIED",
            "production_promotion": "NOT_AUTHORIZED",
        },
        "next_action": (
            "Obtain evaluation-owner authority for two distinct human reviewers, "
            "distribute each cohort separately, collect complete reviews and 456 "
            "distinct-human adjudications, then rerun W7."
        ),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_w8_receipt(receipt)
    return receipt


def validate_w8_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        issues.append("schema_version")
    if receipt.get("wave_id") != "C03_CLUSTER_EMBEDDING_W8":
        issues.append("wave_id")
    if receipt.get("status") != "PASS_PRELABEL_PACKET_READY":
        issues.append("status")
    if receipt.get("completion_marker") != W8_COMPLETION_MARKER:
        issues.append("completion_marker")
    for field in ("commit", "tree"):
        if not _is_git_sha((receipt.get("source_baseline") or {}).get(field)):
            issues.append(f"source_baseline.{field}")
    for field in (
        "wave7_receipt_sha256",
        "query_manifest_sha256",
        "wave4_registry_sha256",
        "projection_generation_sha256",
        "ranking_identity_sha256",
    ):
        if not _is_sha256((receipt.get("source_baseline") or {}).get(field)):
            issues.append(f"source_baseline.{field}")
    controlled = receipt.get("controlled_packet") or {}
    for field, value in {
        "query_section_count_per_cohort": 48,
        "candidate_judgment_count_per_cohort": 456,
        "reviewer_cohort_count": 2,
        "total_reviewer_judgment_slots": 912,
        "sealed_mapping_present": True,
        "sealed_mapping_distributed": False,
    }.items():
        if controlled.get(field) != value:
            issues.append(f"controlled_packet.{field}")
    for field in ("packet_manifest_sha256", "packet_manifest_file_sha256"):
        if not _is_sha256(controlled.get(field)):
            issues.append(f"controlled_packet.{field}")
    cohort_digests = controlled.get("reviewer_cohort_manifest_sha256") or {}
    if set(cohort_digests) != set(COHORTS) or any(
        not _is_sha256(value) for value in cohort_digests.values()
    ):
        issues.append("controlled_packet.reviewer_cohort_manifest_sha256")
    expected_label_authority = {
        "human_labels_present": False,
        "synthetic_labels_created": False,
        "reviewer_assignments_authorized": False,
        "human_review_authority_receipt_present": False,
        "adjudication_present": False,
    }
    if receipt.get("label_authority") != expected_label_authority:
        issues.append("label_authority")
    contract = receipt.get("contract") or {}
    if contract.get("path") != CONTRACT_PATH.as_posix() or not _is_sha256(
        contract.get("canonical_sha256")
    ):
        issues.append("contract")
    scope = receipt.get("scope") or {}
    if scope.get("blinded_full_denominator_packet_ready") is not True:
        issues.append("scope.packet_ready")
    for field in (
        "semantic_retrieval_qualified",
        "cluster_embedding_activation_created",
        "production_promotion_authorized",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    gates = receipt.get("wave_exit_gates") or {}
    expected_gates = {
        "prelabel_packet": "PASS_W8",
        "two_independent_human_reviews": "OPEN_912_REVIEWER_JUDGMENT_SLOTS",
        "human_adjudication": "OPEN_456_ADJUDICATIONS",
        "semantic_retrieval_qualification": "BLOCKED_QREL_AUTHORITY",
        "release_activation": "BLOCKED_UNTIL_QUALIFIED",
        "production_promotion": "NOT_AUTHORIZED",
    }
    if gates != expected_gates:
        issues.append("wave_exit_gates")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise ClusterReviewPacketError(
            f"Invalid W8 receipt: {sorted(set(issues))}"
        )


__all__ = [
    "COHORTS",
    "CONTRACT_PATH",
    "PACKET_SCHEMA_VERSION",
    "RECEIPT_SCHEMA_VERSION",
    "W8_RECEIPT_PATH",
    "ClusterReviewPacketError",
    "blinding_nonce_commitment",
    "build_prelabel_packet_content",
    "build_w8_receipt",
    "validate_prelabel_packet_content",
    "validate_review_packet_contract",
    "validate_w8_receipt",
]
