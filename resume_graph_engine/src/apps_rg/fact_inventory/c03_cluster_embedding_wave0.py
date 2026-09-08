"""Deterministic Wave 0 freeze for C0.3 graph-evidence cluster embeddings.

Wave 0 records the current authority and its known semantic defects.  It does
not repair the graph, retire the legacy projection, or generate embeddings.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    collect_canonical_graph_issues,
)

WAVE0_SCHEMA_VERSION = "apps_rg.c03_cluster_embedding_wave0_receipt.v1"
WAVE0_COMPLETION_MARKER = "C03_CLUSTER_EMBEDDING_WAVE0_BASELINE_FROZEN"
CONTRACT_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/c03_graph_evidence_cluster_contract.v1.json"
)
GRAPH_RELATIVE_PATH = Path(
    "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
)
BASE_RESUME_RELATIVE_PATH = Path(
    "src/apps_rg/resume/base/amit_ayer_base_resume_v1.json"
)
CANDIDATE_FACT_LEDGER_RELATIVE_PATH = Path(
    "artifacts/apps_rg/fact_inventory/"
    "master_candidate_skills_fact_ledger_20260518T1100Z.json"
)
LEGACY_ARTIFACT_DIR = Path("artifacts/apps_rg/c03/graph_skill_embeddings")
LEGACY_ACTIVE_MANIFEST = LEGACY_ARTIFACT_DIR / "graph_skill_embedding_manifest.json"
LEGACY_ACTIVATION_MANIFEST = (
    LEGACY_ARTIFACT_DIR / "graph_skill_embedding_activation_manifest.json"
)
EMBEDDING_RUNTIME_CONTRACT = Path(
    "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
)
ROLE_EPISODE_BUNDLE_PATHS = (
    Path("src/apps_rg/fact_inventory/ey_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/ibm_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/insurtech_role_episode_bundles.json"),
    Path("src/apps_rg/fact_inventory/unify_role_episode_bundles.json"),
)

_SEMANTIC_SENTINELS = frozenset(
    {
        "",
        "[",
        "]",
        "{",
        "}",
        "[]",
        "{}",
        "null",
        "none",
        "n/a",
        "tbd",
        "todo",
        "unknown",
    }
)
_SCAFFOLD_DESCRIPTION = re.compile(
    r"^C0\.3 graph-skill granularity node for ", re.IGNORECASE
)


class ClusterEmbeddingWave0Error(RuntimeError):
    """Raised when the Wave 0 freeze cannot be constructed or verified."""


def canonical_sha256(value: Any) -> str:
    """Return a stable digest for JSON-compatible data."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClusterEmbeddingWave0Error(f"missing or malformed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ClusterEmbeddingWave0Error(f"JSON authority must be an object: {path}")
    return value


def validate_cluster_contract(contract: Mapping[str, Any]) -> None:
    """Validate the frozen target contract before it can bind a receipt."""

    if contract.get("schema_version") != (
        "apps_rg.c03_graph_evidence_cluster_contract.v1"
    ):
        raise ClusterEmbeddingWave0Error("cluster contract schema version is invalid")
    if contract.get("status") != "FROZEN":
        raise ClusterEmbeddingWave0Error("cluster contract is not frozen")
    invariants = contract.get("authority_invariants")
    if not isinstance(invariants, Mapping):
        raise ClusterEmbeddingWave0Error("cluster authority invariants are missing")
    expected_invariants = {
        "graph_ids_are_only_claim_authority": True,
        "embedding_similarity_is_claim_authority": False,
        "retrieval_may_narrow_but_not_add_evidence": True,
        "exact_graph_rehydration_required": True,
        "legacy_one_vector_per_skill_is_promotable": False,
        "replacement_generation_requires_legacy_artifact_retirement": True,
    }
    for field, expected in expected_invariants.items():
        if invariants.get(field) is not expected:
            raise ClusterEmbeddingWave0Error(
                f"cluster authority invariant is invalid: {field}"
            )
    cluster = contract.get("cluster_contract")
    if not isinstance(cluster, Mapping) or cluster.get("logical_retrieval_unit") != (
        "graph_evidence_cluster"
    ):
        raise ClusterEmbeddingWave0Error("cluster logical retrieval unit is invalid")
    vector_policy = cluster.get("vector_policy")
    if (
        not isinstance(vector_policy, Mapping)
        or vector_policy.get("per_node_vector_default_forbidden") is not True
    ):
        raise ClusterEmbeddingWave0Error("per-node vector default is not forbidden")
    activation = contract.get("activation_contract")
    if not isinstance(activation, Mapping):
        raise ClusterEmbeddingWave0Error("cluster activation contract is missing")
    if (
        activation.get("default_enabled") is not False
        or activation.get("missing_or_invalid_manifest_behavior") != "FAIL_CLOSED"
        or activation.get("release_authorizing_required") is not True
    ):
        raise ClusterEmbeddingWave0Error(
            "cluster activation contract is not fail closed"
        )


def _relative_record(repo_root: Path, relative_path: Path) -> dict[str, Any]:
    path = repo_root / relative_path
    if not path.is_file():
        raise ClusterEmbeddingWave0Error(f"required Wave 0 input is missing: {path}")
    record: dict[str, Any] = {
        "path": relative_path.as_posix(),
        "file_sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }
    if path.suffix.lower() == ".json":
        record["canonical_sha256"] = canonical_sha256(_load_json_object(path))
    return record


def _profile_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = list(graph.get("graph_nodes") or [])
    edges = list(graph.get("graph_edges") or [])
    rows = list(graph.get("skill_rows") or [])
    node_by_id = {str(node.get("node_id") or ""): node for node in nodes}
    row_by_id = {str(row.get("skill_id") or ""): row for row in rows}

    malformed_nodes = [
        str(node.get("node_id") or "")
        for node in nodes
        if str(node.get("description") or "").strip().lower() in _SEMANTIC_SENTINELS
    ]
    scaffold_nodes = [
        str(node.get("node_id") or "")
        for node in nodes
        if _SCAFFOLD_DESCRIPTION.search(str(node.get("description") or "").strip())
    ]

    parity_fields = (
        "node_type",
        "activation_status",
        "support_level",
        "visibility_rule",
        "evidence_risk",
        "projection_behavior",
        "external_claim_policy",
        "retrieval_eligible",
    )
    parity_mismatch_counts: dict[str, int] = {}
    parity_mismatch_samples: dict[str, list[str]] = {}
    for field in parity_fields:
        offenders = [
            skill_id
            for skill_id, row in row_by_id.items()
            if node_by_id.get(skill_id, {}).get(field) != row.get(field)
        ]
        parity_mismatch_counts[field] = len(offenders)
        parity_mismatch_samples[field] = sorted(offenders)[:12]

    section_edges: dict[str, set[str]] = defaultdict(set)
    edge_pairs: set[tuple[str, str]] = set()
    for edge in edges:
        source = str(edge.get("source_node_id") or "")
        target = str(edge.get("target_node_id") or "")
        edge_pairs.add((source, target))
        if edge.get("edge_type") == "skill_allowed_in_section":
            section_edges[source].add(target)

    section_drift_rows: list[str] = []
    missing_section_edges: list[str] = []
    extra_section_edges: list[str] = []
    for skill_id, row in row_by_id.items():
        expected = {f"section_{value}" for value in row.get("allowed_sections") or []}
        actual = section_edges.get(skill_id, set())
        if expected != actual:
            section_drift_rows.append(skill_id)
        missing_section_edges.extend(
            f"{skill_id}->{value}" for value in expected - actual
        )
        extra_section_edges.extend(
            f"{skill_id}->{value}" for value in actual - expected
        )

    broken_hop_rows: list[str] = []
    fact_missing_hop_rows: list[str] = []
    for skill_id, row in row_by_id.items():
        path = [str(value) for value in row.get("graph_hop_path") or []]
        if any(
            (source, target) not in edge_pairs for source, target in zip(path, path[1:])
        ):
            broken_hop_rows.append(skill_id)
        if "fact_missing" in path:
            fact_missing_hop_rows.append(skill_id)

    draft_node_ids = {
        str(node.get("node_id") or "")
        for node in nodes
        if str(node.get("activation_status") or "") == "DRAFT"
    }
    validated_edges_touching_draft = [
        str(edge.get("edge_id") or "")
        for edge in edges
        if str(edge.get("validation_status") or "") in {"validated", "ACTIVE_CONFIRMED"}
        and (
            str(edge.get("source_node_id") or "") in draft_node_ids
            or str(edge.get("target_node_id") or "") in draft_node_ids
        )
    ]

    rationales = Counter(str(edge.get("rationale") or "").strip() for edge in edges)
    reused_rationale_edge_count = sum(
        count for count in rationales.values() if count > 1
    )
    eligible_skill_ids = {
        str(row.get("skill_id") or "")
        for row in rows
        if row.get("retrieval_eligible") is True
    }

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "skill_row_count": len(rows),
        "retrieval_eligible_skill_count": len(eligible_skill_ids),
        "non_retrieval_skill_count": len(rows) - len(eligible_skill_ids),
        "node_type_counts": dict(
            sorted(Counter(str(node.get("node_type") or "") for node in nodes).items())
        ),
        "edge_type_counts": dict(
            sorted(Counter(str(edge.get("edge_type") or "") for edge in edges).items())
        ),
        "activation_status_counts": dict(
            sorted(
                Counter(
                    str(node.get("activation_status") or "") for node in nodes
                ).items()
            )
        ),
        "registered_shape_issue_count": len(
            collect_canonical_graph_issues(dict(graph))
        ),
        "registered_shape_issues": collect_canonical_graph_issues(dict(graph)),
        "semantic_hardening": {
            "status": "BLOCKED",
            "malformed_description_count": len(malformed_nodes),
            "malformed_description_samples": sorted(malformed_nodes)[:12],
            "scaffold_description_count": len(scaffold_nodes),
            "scaffold_description_samples": sorted(scaffold_nodes)[:12],
        },
        "authority_reconciliation": {
            "status": "BLOCKED",
            "field_mismatch_counts": parity_mismatch_counts,
            "field_mismatch_samples": parity_mismatch_samples,
            "section_drift_row_count": len(section_drift_rows),
            "missing_section_edge_count": len(missing_section_edges),
            "extra_section_edge_count": len(extra_section_edges),
            "skill_without_section_edge_count": sum(
                not section_edges.get(skill_id) for skill_id in row_by_id
            ),
        },
        "path_and_lifecycle_hardening": {
            "status": "BLOCKED",
            "non_traversable_graph_hop_row_count": len(broken_hop_rows),
            "fact_missing_hop_row_count": len(fact_missing_hop_rows),
            "validated_edge_touching_draft_count": len(validated_edges_touching_draft),
        },
        "edge_assertion_hardening": {
            "status": "BLOCKED",
            "unique_rationale_count": len(rationales),
            "reused_rationale_edge_count": reused_rationale_edge_count,
            "most_reused_rationales": [
                {"rationale": rationale, "edge_count": count}
                for rationale, count in rationales.most_common(12)
            ],
        },
    }


def _profile_role_episode_bundles(
    repo_root: Path,
    graph: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    bundles: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    by_file: dict[str, int] = {}
    for relative_path in ROLE_EPISODE_BUNDLE_PATHS:
        payload = _load_json_object(repo_root / relative_path)
        raw_bundles = payload.get("bundles")
        if not isinstance(raw_bundles, list):
            raise ClusterEmbeddingWave0Error(
                f"role-episode bundle list is missing: {relative_path}"
            )
        normalized = [dict(value) for value in raw_bundles if isinstance(value, dict)]
        if len(normalized) != len(raw_bundles):
            raise ClusterEmbeddingWave0Error(
                f"role-episode bundle contains non-object rows: {relative_path}"
            )
        bundles.extend(normalized)
        by_file[relative_path.name] = len(normalized)
        source_records.append(_relative_record(repo_root, relative_path))

    rows = list(graph.get("skill_rows") or [])
    eligible = {
        str(row.get("skill_id") or "")
        for row in rows
        if row.get("retrieval_eligible") is True
    }
    bundle_skills = {
        str(skill_id)
        for bundle in bundles
        for skill_id in bundle.get("graph_skill_node_ids") or []
    }
    factless = [
        str(bundle.get("role_episode_bundle_id") or "")
        for bundle in bundles
        if not bundle.get("linked_source_fact_ids")
    ]
    profile = {
        "status": "CANDIDATES_ONLY",
        "bundle_count": len(bundles),
        "bundle_count_by_file": dict(sorted(by_file.items())),
        "fact_backed_bundle_count": len(bundles) - len(factless),
        "factless_bundle_count": len(factless),
        "factless_bundle_ids": sorted(factless),
        "unique_bundle_skill_count": len(bundle_skills),
        "eligible_skill_covered_count": len(eligible & bundle_skills),
        "eligible_skill_not_bundled_count": len(eligible - bundle_skills),
        "bundled_skill_not_eligible_count": len(bundle_skills - eligible),
        "cluster_registry_materialized": False,
    }
    return profile, source_records


def _profile_legacy_artifacts(repo_root: Path) -> dict[str, Any]:
    artifact_dir = repo_root / LEGACY_ARTIFACT_DIR
    if not artifact_dir.is_dir():
        raise ClusterEmbeddingWave0Error(
            f"legacy embedding artifact directory is missing: {artifact_dir}"
        )
    artifact_records = [
        _relative_record(repo_root, path.relative_to(repo_root))
        for path in sorted(artifact_dir.iterdir(), key=lambda value: value.name)
        if path.is_file()
    ]
    generation = _load_json_object(repo_root / LEGACY_ACTIVE_MANIFEST)
    activation = _load_json_object(repo_root / LEGACY_ACTIVATION_MANIFEST)
    corpus_ref = generation.get("assertion_corpus") or {}
    corpus_path = artifact_dir / str(corpus_ref.get("path") or "")
    corpus = _load_json_object(corpus_path)
    assertions = list(corpus.get("assertions") or [])
    malformed_assertions = [
        str(assertion.get("assertion_id") or "")
        for assertion in assertions
        if str((assertion.get("semantic_card") or {}).get("description") or "").strip()
        == "["
    ]
    per_skill_vectors = [
        str(assertion.get("assertion_id") or "")
        for assertion in assertions
        if assertion.get("assertion_id") == assertion.get("skill_id")
    ]
    return {
        "status": "ACTIVE_LEGACY_NOT_ACCEPTABLE_FOR_CLUSTER_PROMOTION",
        "artifact_directory": LEGACY_ARTIFACT_DIR.as_posix(),
        "artifact_count": len(artifact_records),
        "artifacts": artifact_records,
        "active_generation_manifest_sha256": str(
            generation.get("manifest_sha256") or ""
        ),
        "active_activation_status": str(activation.get("status") or ""),
        "model_baseline": {
            "model_id": str((generation.get("model") or {}).get("model_id") or ""),
            "revision": str((generation.get("model") or {}).get("revision") or ""),
            "artifact_sha256": str(
                (generation.get("model") or {}).get("artifact_sha256") or ""
            ),
            "dimension": (generation.get("model") or {}).get("dimension"),
            "normalization": str(
                (generation.get("model") or {}).get("normalization") or ""
            ),
        },
        "assertion_count": len(assertions),
        "malformed_assertion_description_count": len(malformed_assertions),
        "malformed_assertion_samples": sorted(malformed_assertions)[:12],
        "assertion_id_equals_skill_id_count": len(per_skill_vectors),
        "logical_retrieval_unit": "skill",
        "retirement_authorized_in_wave0": False,
        "replacement_generation_authorized_in_wave0": False,
    }


def build_wave0_receipt(
    repo_root: Path | str,
    *,
    source_commit: str,
    source_tree: str,
    source_ref: str = "origin/main",
) -> dict[str, Any]:
    """Build the immutable Wave 0 baseline receipt without writing files."""

    root = Path(repo_root).resolve()
    if not source_commit.strip() or not source_tree.strip():
        raise ClusterEmbeddingWave0Error("source commit and tree are required")

    contract = _load_json_object(root / CONTRACT_RELATIVE_PATH)
    validate_cluster_contract(contract)
    graph = _load_json_object(root / GRAPH_RELATIVE_PATH)
    graph_profile = _profile_graph(graph)
    bundle_profile, bundle_records = _profile_role_episode_bundles(root, graph)
    legacy_profile = _profile_legacy_artifacts(root)

    source_inputs = {
        "cluster_contract": _relative_record(root, CONTRACT_RELATIVE_PATH),
        "canonical_graph": _relative_record(root, GRAPH_RELATIVE_PATH),
        "candidate_fact_ledger": _relative_record(
            root, CANDIDATE_FACT_LEDGER_RELATIVE_PATH
        ),
        "base_resume": _relative_record(root, BASE_RESUME_RELATIVE_PATH),
        "role_episode_bundles": bundle_records,
        "embedding_runtime_contract": _relative_record(
            root, EMBEDDING_RUNTIME_CONTRACT
        ),
    }

    receipt: dict[str, Any] = {
        "schema_version": WAVE0_SCHEMA_VERSION,
        "wave_id": "C03_CLUSTER_EMBEDDING_W0",
        "status": "PASS",
        "completion_marker": WAVE0_COMPLETION_MARKER,
        "scope": {
            "repository": "apps_rg_v2",
            "baseline_freeze_only": True,
            "graph_mutated": False,
            "legacy_artifacts_deleted": False,
            "replacement_vectors_generated": False,
            "production_promotion_authorized": False,
        },
        "source_baseline": {
            "ref": source_ref,
            "commit": source_commit,
            "tree": source_tree,
        },
        "contract": {
            "schema_version": contract.get("schema_version"),
            "contract_id": contract.get("contract_id"),
            "file_sha256": source_inputs["cluster_contract"]["file_sha256"],
            "canonical_sha256": source_inputs["cluster_contract"]["canonical_sha256"],
        },
        "source_inputs": source_inputs,
        "graph_profile": graph_profile,
        "role_episode_cluster_candidates": bundle_profile,
        "legacy_embedding_artifacts": legacy_profile,
        "future_cluster_activation": {
            "status": "FAIL_CLOSED_NOT_ACTIVE",
            "required_env": contract["activation_contract"]["required_env"],
            "active_manifest_path": contract["activation_contract"][
                "active_manifest_path"
            ],
            "valid_release_authorizing_manifest_present": False,
        },
        "wave_exit_gates": {
            "baseline_authority_pinned": "PASS",
            "legacy_artifact_inventory_complete": "PASS",
            "target_contract_frozen": "PASS",
            "node_semantic_hardening": "OPEN_W1",
            "edge_assertion_hardening": "OPEN_W2",
            "authority_reconciliation": "OPEN_W3",
            "cluster_registry_materialization": "OPEN_W4",
            "legacy_artifact_retirement": "OPEN_W5",
            "cluster_embedding_generation": "OPEN_W6",
            "release_authorizing_qualification": "OPEN_W8",
        },
        "open_gates": [
            "Repair malformed and scaffold node semantics.",
            "Replace rationale-only edge validation with exact assertion bases.",
            "Reconcile graph-node, skill-row, section, path, policy, and lifecycle authority.",
            "Materialize and validate role-episode and capability-evidence clusters.",
            "Retire all digest-bound legacy skill-level embedding artifacts before replacement generation.",
            "Generate and qualify a bounded top-k cluster projection before activation.",
        ],
        "next_wave": "C03_CLUSTER_EMBEDDING_W1_NODE_HARDENING",
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_wave0_receipt(receipt)
    return receipt


def validate_wave0_receipt(receipt: Mapping[str, Any]) -> None:
    """Validate the immutable receipt's internal Wave 0 truth claims."""

    if receipt.get("schema_version") != WAVE0_SCHEMA_VERSION:
        raise ClusterEmbeddingWave0Error("Wave 0 receipt schema version is invalid")
    if receipt.get("status") != "PASS":
        raise ClusterEmbeddingWave0Error("Wave 0 baseline freeze did not pass")
    if receipt.get("completion_marker") != WAVE0_COMPLETION_MARKER:
        raise ClusterEmbeddingWave0Error("Wave 0 completion marker is invalid")
    source = receipt.get("source_baseline")
    if not isinstance(source, Mapping) or not all(
        str(source.get(field) or "").strip() for field in ("ref", "commit", "tree")
    ):
        raise ClusterEmbeddingWave0Error("Wave 0 source baseline is incomplete")
    scope = receipt.get("scope")
    if not isinstance(scope, Mapping):
        raise ClusterEmbeddingWave0Error("Wave 0 scope is missing")
    expected_scope = {
        "baseline_freeze_only": True,
        "graph_mutated": False,
        "legacy_artifacts_deleted": False,
        "replacement_vectors_generated": False,
        "production_promotion_authorized": False,
    }
    for field, expected in expected_scope.items():
        if scope.get(field) is not expected:
            raise ClusterEmbeddingWave0Error(
                f"Wave 0 scope claim is invalid: {field} must be {expected}"
            )
    activation = receipt.get("future_cluster_activation")
    if not isinstance(activation, Mapping) or activation.get("status") != (
        "FAIL_CLOSED_NOT_ACTIVE"
    ):
        raise ClusterEmbeddingWave0Error("future cluster activation is not fail closed")
    if activation.get("valid_release_authorizing_manifest_present") is not False:
        raise ClusterEmbeddingWave0Error(
            "Wave 0 cannot claim a release-authorizing cluster manifest"
        )
    legacy = receipt.get("legacy_embedding_artifacts")
    if (
        not isinstance(legacy, Mapping)
        or legacy.get("retirement_authorized_in_wave0") is not False
    ):
        raise ClusterEmbeddingWave0Error("Wave 0 legacy retirement boundary is invalid")
    graph_profile = receipt.get("graph_profile")
    if not isinstance(graph_profile, Mapping):
        raise ClusterEmbeddingWave0Error("Wave 0 graph profile is missing")
    for gate in (
        "semantic_hardening",
        "authority_reconciliation",
        "path_and_lifecycle_hardening",
        "edge_assertion_hardening",
    ):
        value = graph_profile.get(gate)
        if not isinstance(value, Mapping) or value.get("status") != "BLOCKED":
            raise ClusterEmbeddingWave0Error(
                f"Wave 0 must preserve the known blocked graph gate: {gate}"
            )
    unsigned = dict(receipt)
    recorded = str(unsigned.pop("receipt_sha256", "") or "")
    observed = canonical_sha256(unsigned)
    if not recorded or recorded != observed:
        raise ClusterEmbeddingWave0Error(
            f"Wave 0 receipt digest mismatch: expected {observed}, observed {recorded or '<missing>'}"
        )


__all__ = [
    "ClusterEmbeddingWave0Error",
    "WAVE0_COMPLETION_MARKER",
    "WAVE0_SCHEMA_VERSION",
    "build_wave0_receipt",
    "canonical_sha256",
    "file_sha256",
    "validate_cluster_contract",
    "validate_wave0_receipt",
]
