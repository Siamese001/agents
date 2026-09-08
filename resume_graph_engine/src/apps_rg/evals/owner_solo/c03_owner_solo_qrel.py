"""Fail-closed, blinded, non-authoritative owner-solo C0.3 QREL workflow.

The owner-solo lane is intentionally separate from W9.  It can create a
provisional owner-directed QREL artifact after explicit human grades, but it
never produces the authoritative ``FROZEN_HUMAN_ADJUDICATED`` status, an
activation manifest, or production authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps_rg.evals.c03_graph_evidence_cluster_qualification import (
    ranking_identity_sha256,
)
from apps_rg.evals.c03_graph_evidence_cluster_review_packet import (
    PACKET_SCHEMA_VERSION,
    W8_RECEIPT_PATH,
    validate_prelabel_packet_content,
)
from apps_rg.evals.c03_human_eval._safety import unsafe_reviewer_keys
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)

CONTRACT_PATH = Path("src/apps_rg/evals/owner_solo/owner_solo_qrel_contract.v1.json")
CONTRACT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_lane_contract.v1"
POLICY_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_exception.v1"
EXECUTION_MANIFEST_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_execution_manifest.v1"
EVENT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_review_event.v1"
QREL_SCHEMA_VERSION = "apps_rg.owner_solo_graph_evidence_cluster_qrels.v1"
FINALIZATION_RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_finalization_receipt.v1"
PROGRESS_RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_progress_receipt.v1"
PACKET_RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_packet_receipt.v1"
METRICS_RECEIPT_SCHEMA_VERSION = "apps_rg.owner_solo_qrel_metrics_receipt.v1"
RESULT_LABEL = "OWNER_SOLO_PROVISIONAL"
FINAL_QREL_STATUS = "FROZEN_OWNER_SOLO_PROVISIONAL"
RUNTIME_ROOT = Path(".runtime/c03-owner-solo-qrel")
QUERY_MANIFEST_PATH = Path("src/apps_rg/evals/c03_graph_evidence_cluster_queries.v1.json")
REGISTRY_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_registry.v1.json"
)
W6_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave6_cluster_vector_generation_receipt.json"
)
W7_RECEIPT_PATH = Path(
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave7_semantic_qualification_receipt.json"
)


class OwnerSoloQrelError(ValueError):
    """Raised when owner-solo input, authority, or state is invalid."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _is_git_sha(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OwnerSoloQrelError(f"JSON unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise OwnerSoloQrelError(f"JSON must be an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OwnerSoloQrelError(f"JSONL unavailable: {path}") from exc
    result: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OwnerSoloQrelError(f"Malformed JSONL at {path}:{number}") from exc
        if not isinstance(value, dict):
            raise OwnerSoloQrelError(f"JSONL object required at {path}:{number}")
        result.append(value)
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise OwnerSoloQrelError(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _digest_matches(value: Mapping[str, Any], field: str) -> bool:
    supplied = value.get(field)
    unsigned = dict(value)
    unsigned.pop(field, None)
    return _is_sha256(supplied) and canonical_sha256(unsigned) == supplied


def _runtime_path(repo_root: Path, path: Path | str, label: str) -> Path:
    candidate = Path(path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (repo_root / candidate).resolve()
    )
    runtime = (repo_root / ".runtime").resolve()
    try:
        resolved.relative_to(runtime)
    except ValueError as exc:
        raise OwnerSoloQrelError(f"{label} must remain under ignored .runtime") from exc
    return resolved


def _write_json(path: Path, value: Mapping[str, Any], *, create_once: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if create_once:
        try:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        except FileExistsError as exc:
            raise OwnerSoloQrelError(f"Create-once artifact already exists: {path}") from exc
        return
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_owner_solo_contract(repo_root: Path | str) -> dict[str, Any]:
    return _read_json(Path(repo_root).resolve() / CONTRACT_PATH)


def validate_owner_solo_contract(contract: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("CONTRACT_SCHEMA_VERSION")
    if contract.get("lane") != RESULT_LABEL or contract.get("status") != "FROZEN":
        issues.append("CONTRACT_LANE_OR_STATUS")
    authoritative = contract.get("authoritative_lane")
    if not isinstance(authoritative, Mapping) or any(
        authoritative.get(field) is not True
        for field in (
            "existing_two_reviewer_contract_unchanged",
            "existing_independent_adjudication_contract_unchanged",
            "authoritative_release_qualification_may_not_be_satisfied",
        )
    ):
        issues.append("CONTRACT_AUTHORITATIVE_BOUNDARY")
    controls = contract.get("mandatory_controls")
    if not isinstance(controls, Mapping) or any(
        controls.get(field) is not True
        for field in (
            "full_finite_candidate_universe_required",
            "rank_score_split_and_identity_blinding_required_during_scoring",
            "explicit_integer_grade_required",
            "nonempty_human_rationale_required",
            "append_only_correction_ledger_required",
            "calibration_holdout_separation_required",
            "unknown_or_malformed_judgments_fail_closed",
        )
    ):
        issues.append("CONTRACT_MANDATORY_CONTROLS")
    denominator = contract.get("denominator")
    expected = {
        "query_count": 6,
        "calibration_query_count": 3,
        "holdout_query_count": 3,
        "section_count": 8,
        "query_section_case_count": 48,
        "candidate_judgment_count": 456,
        "relevant_grade_floor": 2,
        "partial_top_k_judging_forbidden": True,
    }
    if not isinstance(denominator, Mapping) or any(
        denominator.get(field) != value for field, value in expected.items()
    ):
        issues.append("CONTRACT_DENOMINATOR")
    publication = contract.get("publication_boundary")
    if not isinstance(publication, Mapping) or publication.get("status_after_finalization") != FINAL_QREL_STATUS or any(
        publication.get(field) is not False
        for field in (
            "independent_qrel_authority",
            "inter_rater_reliability_claim",
            "release_qualification",
            "activation_manifest_created",
            "production_promotion_authorized",
        )
    ):
        issues.append("CONTRACT_PUBLICATION_BOUNDARY")
    return sorted(set(issues))


def validate_owner_solo_exception_policy(policy: Mapping[str, Any]) -> list[str]:
    """Validate the owner-issued exception without treating it as release authority."""
    issues: list[str] = []
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        issues.append("POLICY_SCHEMA_VERSION")
    if policy.get("status") != "OWNER_APPROVED_EXCEPTION":
        issues.append("POLICY_STATUS")
    if not _digest_matches(policy, "record_digest"):
        issues.append("POLICY_DIGEST")
    owner = policy.get("owner_reviewer")
    if not isinstance(owner, Mapping) or not str(owner.get("identity_ref") or "").startswith("human-reviewer://") or owner.get("roles") != ["primary_reviewer", "self_adjudicator"] or owner.get("human_only") is not True:
        issues.append("POLICY_OWNER")
    exception = policy.get("exception")
    if not isinstance(exception, Mapping) or exception.get("independent_second_reviewer_required") is not False or exception.get("independent_adjudicator_required") is not False:
        issues.append("POLICY_EXPLICIT_WAIVER")
    elif not {"inter_rater_agreement", "independent_disagreement_resolution", "three_distinct_human_authority"}.issubset(set(exception.get("waived_controls") or [])) or not {"full_finite_candidate_universe", "rank_and_score_blinding", "explicit_integer_grade_0_1_2_3", "nonempty_human_rationale", "calibration_holdout_separation", "immutable_query_registry_projection_and_ranking_bindings", "unknown_is_not_pass"}.issubset(set(exception.get("controls_not_waived") or [])):
        issues.append("POLICY_CONTROL_BOUNDARY")
    boundary = policy.get("authority_boundary")
    required_may_not = {
        "independent QREL authority",
        "inter-rater reliability claims",
        "release-quality qualification under the existing authoritative contract",
        "production promotion",
    }
    if not isinstance(boundary, Mapping) or boundary.get("required_result_label") != RESULT_LABEL or not required_may_not.issubset(set(boundary.get("may_not_support") or [])):
        issues.append("POLICY_AUTHORITY_BOUNDARY")
    binding = policy.get("repository_binding")
    required_binding = {
        "repository",
        "source_commit",
        "query_manifest_sha256",
        "registry_sha256",
        "projection_generation_sha256",
        "projection_file_sha256",
        "ranking_identity_sha256",
        "w6_receipt_sha256",
        "w7_receipt_sha256",
        "w8_receipt_sha256",
        "w8_packet_manifest_sha256",
    }
    if not isinstance(binding, Mapping) or set(binding) != required_binding:
        issues.append("POLICY_REPOSITORY_BINDING_FIELDS")
    elif binding.get("repository") != "Siamese001/apps_rg_v2" or not _is_git_sha(binding.get("source_commit")) or any(
        not _is_sha256(binding.get(field))
        for field in required_binding - {"repository", "source_commit"}
    ):
        issues.append("POLICY_REPOSITORY_BINDING_VALUES")
    return sorted(set(issues))


def validate_owner_solo_execution_manifest(manifest: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if manifest.get("schema_version") != EXECUTION_MANIFEST_SCHEMA_VERSION:
        issues.append("EXECUTION_MANIFEST_SCHEMA_VERSION")
    if manifest.get("status") != "BLOCKED_PENDING_W8_PACKET_EXPORT":
        issues.append("EXECUTION_MANIFEST_STATUS")
    if not _digest_matches(manifest, "record_digest"):
        issues.append("EXECUTION_MANIFEST_DIGEST")
    runtime = manifest.get("runtime_binding")
    expected_runtime = {
        "model_id": "BAAI/bge-m3",
        "model_revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "model_artifact_sha256": "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263",
        "dimension": 1024,
        "normalization": "l2",
        "logical_retrieval_unit": "graph_evidence_cluster",
        "active_cluster_count": 38,
        "network_allowed": False,
        "fallback_allowed": False,
    }
    if not isinstance(runtime, Mapping) or any(
        runtime.get(field) != value for field, value in expected_runtime.items()
    ):
        issues.append("EXECUTION_MANIFEST_RUNTIME_BINDING")
    denominator = manifest.get("evaluation_denominator")
    expected_denominator = {
        "query_count": 6,
        "calibration_query_count": 3,
        "holdout_query_count": 3,
        "section_count": 8,
        "query_section_case_count": 48,
        "candidate_judgment_count": 456,
        "relevant_grade_floor": 2,
        "full_candidate_universe_required": True,
        "partial_top_k_judging_forbidden": True,
    }
    if not isinstance(denominator, Mapping) or any(
        denominator.get(field) != value for field, value in expected_denominator.items()
    ):
        issues.append("EXECUTION_MANIFEST_DENOMINATOR")
    seed = manifest.get("seed_label_set")
    if not isinstance(seed, Mapping) or seed.get("explicit_grade_count") != 50 or seed.get("qrel_status") != "UNBOUND_DEVELOPMENT_SEED_NOT_FORMAL_QRELS":
        issues.append("EXECUTION_MANIFEST_SEED_BOUNDARY")
    return sorted(set(issues))


def _git_commit_is_available(repo_root: Path, commit: str) -> bool:
    try:
        present = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return present.returncode == 0 and ancestor.returncode == 0


def _repository_bindings(repo_root: Path) -> dict[str, Any]:
    query_manifest = _read_json(repo_root / QUERY_MANIFEST_PATH)
    registry = _read_json(repo_root / REGISTRY_PATH)
    w6 = _read_json(repo_root / W6_RECEIPT_PATH)
    w7 = _read_json(repo_root / W7_RECEIPT_PATH)
    w8 = _read_json(repo_root / W8_RECEIPT_PATH)
    generation_path = repo_root / str((w6.get("generation") or {}).get("manifest_path") or "")
    generation = _read_json(generation_path)
    model = generation.get("model") or {}
    projection = generation.get("projection") or {}
    return {
        "query_manifest": query_manifest,
        "registry": registry,
        "w6": w6,
        "w7": w7,
        "w8": w8,
        "generation": generation,
        "binding": {
            "query_manifest_sha256": query_manifest.get("query_manifest_sha256"),
            "registry_sha256": registry.get("registry_sha256"),
            "projection_generation_sha256": projection.get("generation_sha256"),
            "projection_file_sha256": projection.get("file_sha256"),
            "ranking_identity_sha256": (w8.get("source_baseline") or {}).get("ranking_identity_sha256"),
            "w6_receipt_sha256": w6.get("receipt_sha256"),
            "w7_receipt_sha256": w7.get("receipt_sha256"),
            "w8_receipt_sha256": w8.get("receipt_sha256"),
            "w8_packet_manifest_sha256": (w8.get("controlled_packet") or {}).get("packet_manifest_sha256"),
            "model_id": model.get("model_id"),
            "model_revision": model.get("revision"),
            "model_artifact_sha256": model.get("artifact_sha256"),
            "dimension": model.get("dimension"),
            "normalization": model.get("normalization"),
            "logical_retrieval_unit": generation.get("logical_retrieval_unit"),
            "active_cluster_count": projection.get("active_cluster_count", projection.get("vector_count")),
        },
    }


def _binding_issues(
    policy: Mapping[str, Any],
    execution: Mapping[str, Any],
    repository: Mapping[str, Any],
    repo_root: Path,
) -> list[str]:
    issues: list[str] = []
    policy_binding = policy.get("repository_binding") or {}
    execution_binding = execution.get("repository_binding") or {}
    expected = repository["binding"]
    for field in (
        "query_manifest_sha256",
        "registry_sha256",
        "projection_generation_sha256",
        "projection_file_sha256",
        "ranking_identity_sha256",
        "w6_receipt_sha256",
        "w7_receipt_sha256",
        "w8_receipt_sha256",
        "w8_packet_manifest_sha256",
    ):
        if policy_binding.get(field) != expected.get(field):
            issues.append(f"POLICY_BINDING:{field}")
        if execution_binding.get(field) != expected.get(field):
            issues.append(f"EXECUTION_BINDING:{field}")
    runtime = execution.get("runtime_binding") or {}
    for field in (
        "model_id",
        "model_revision",
        "model_artifact_sha256",
        "dimension",
        "normalization",
        "logical_retrieval_unit",
        "active_cluster_count",
    ):
        if runtime.get(field) != expected.get(field):
            issues.append(f"RUNTIME_BINDING:{field}")
    source_commit = str(policy_binding.get("source_commit") or "")
    if source_commit != execution_binding.get("source_commit") or not _git_commit_is_available(repo_root, source_commit):
        issues.append("SOURCE_COMMIT")
    return sorted(set(issues))


def _packet_content(
    packet_dir: Path,
    *,
    query_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_path = packet_dir / "packet_manifest.v1.json"
    manifest = _read_json(manifest_path)
    w8 = expected["w8"]
    controlled = w8.get("controlled_packet") or {}
    issues: list[str] = []
    if _file_sha256(manifest_path) != controlled.get("packet_manifest_file_sha256"):
        issues.append("PACKET_MANIFEST_FILE_DIGEST")
    if not _digest_matches(manifest, "manifest_sha256"):
        issues.append("PACKET_MANIFEST_DIGEST")
    if manifest.get("manifest_sha256") != expected["binding"].get("w8_packet_manifest_sha256"):
        issues.append("PACKET_MANIFEST_AUTHORITY_BINDING")
    if manifest.get("schema_version") != "apps_rg.c03_graph_evidence_cluster_packet_manifest.v1" or manifest.get("status") != "FROZEN_UNLABELED_PRELABEL":
        issues.append("PACKET_MANIFEST_SCHEMA_OR_STATUS")
    expected_packet_bindings = {
        "wave7_receipt_sha256": expected["binding"].get("w7_receipt_sha256"),
        "query_manifest_sha256": expected["binding"].get("query_manifest_sha256"),
        "registry_sha256": expected["binding"].get("registry_sha256"),
        "projection_generation_sha256": expected["binding"].get("projection_generation_sha256"),
    }
    if manifest.get("authority_bindings") != expected_packet_bindings:
        issues.append("PACKET_AUTHORITY_BINDINGS")
    if manifest.get("ranking_identity_sha256") != expected["binding"].get("ranking_identity_sha256"):
        issues.append("PACKET_RANKING_IDENTITY")
    if manifest.get("query_section_count_per_cohort") != 48 or manifest.get("candidate_judgment_count_per_cohort") != 456:
        issues.append("PACKET_DENOMINATOR")
    if manifest.get("sealed_mapping_distribution_forbidden") is not True:
        issues.append("PACKET_SEALED_MAPPING_BOUNDARY")
    cohorts: dict[str, list[dict[str, Any]]] = {}
    cohort_metadata: dict[str, dict[str, str]] = {}
    for cohort in ("reviewer_a", "reviewer_b"):
        cohort_dir = packet_dir / cohort
        reviewer_manifest_path = cohort_dir / "reviewer_manifest.v1.json"
        reviewer_manifest = _read_json(reviewer_manifest_path)
        packet_cohort = (manifest.get("cohorts") or {}).get(cohort) or {}
        if _file_sha256(reviewer_manifest_path) != packet_cohort.get("manifest_file_sha256"):
            issues.append(f"{cohort}:MANIFEST_FILE_DIGEST")
        if not _digest_matches(reviewer_manifest, "manifest_sha256") or reviewer_manifest.get("manifest_sha256") != packet_cohort.get("manifest_sha256"):
            issues.append(f"{cohort}:MANIFEST_DIGEST")
        if reviewer_manifest.get("reviewer_cohort") != cohort or reviewer_manifest.get("query_section_count") != 48 or reviewer_manifest.get("candidate_judgment_count") != 456:
            issues.append(f"{cohort}:MANIFEST_DENOMINATOR")
        for field in ("model_ranks_or_scores_present", "graph_ids_present", "labels_present", "other_cohort_outputs_present"):
            if reviewer_manifest.get(field) is not False:
                issues.append(f"{cohort}:MANIFEST_LEAKAGE_FLAG:{field}")
        items_path = cohort_dir / "review_items.jsonl"
        review_items_file_sha256 = _file_sha256(items_path)
        if review_items_file_sha256 != (reviewer_manifest.get("files") or {}).get("review_items.jsonl"):
            issues.append(f"{cohort}:REVIEW_ITEMS_DIGEST")
        cohorts[cohort] = _read_jsonl(items_path)
        cohort_metadata[cohort] = {
            "reviewer_manifest_sha256": str(
                reviewer_manifest.get("manifest_sha256") or ""
            ),
            "reviewer_manifest_file_sha256": _file_sha256(reviewer_manifest_path),
            "review_items_file_sha256": review_items_file_sha256,
        }
    sealed_path = packet_dir / "sealed_internal" / "identity_and_rank_mapping.v1.json"
    if _file_sha256(sealed_path) != manifest.get("sealed_mapping_file_sha256"):
        issues.append("SEALED_MAPPING_FILE_DIGEST")
    sealed = _read_json(sealed_path)
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": manifest.get("status"),
        "authority_bindings": manifest.get("authority_bindings"),
        "ranking_identity_sha256": manifest.get("ranking_identity_sha256"),
        "blinding_nonce_commitment": manifest.get("blinding_nonce_commitment"),
        "cohorts": cohorts,
        "sealed_mapping": sealed,
    }
    try:
        validate_prelabel_packet_content(
            packet,
            query_manifest=query_manifest,
            registry=registry,
        )
    except ValueError as exc:
        issues.append(f"PACKET_CONTENT:{exc}")
    for item in cohorts["reviewer_a"]:
        if unsafe_reviewer_keys(item):
            issues.append(f"REVIEWER_A_LEAKAGE_KEYS:{item.get('item_ref')}")
    if issues:
        raise OwnerSoloQrelError("Owner-solo packet invalid: " + "; ".join(sorted(set(issues))))
    return {
        "packet_manifest": manifest,
        "packet_manifest_file_sha256": _file_sha256(manifest_path),
        "reviewer_a_items": cohorts["reviewer_a"],
        "cohort_metadata": cohort_metadata,
        "sealed_mapping": sealed,
        "sealed_mapping_file_sha256": _file_sha256(sealed_path),
    }


def load_owner_solo_context(
    *,
    repo_root: Path | str,
    exception_policy_path: Path | str,
    execution_manifest_path: Path | str,
    packet_dir: Path | str,
    runtime_dir: Path | str = RUNTIME_ROOT,
) -> dict[str, Any]:
    """Validate all non-human inputs before showing or accepting a judgment."""
    root = Path(repo_root).resolve()
    runtime = _runtime_path(root, runtime_dir, "owner-solo runtime directory")
    policy_path = _runtime_path(root, exception_policy_path, "exception policy")
    execution_path = _runtime_path(root, execution_manifest_path, "execution manifest")
    frozen_packet_dir = _runtime_path(root, packet_dir, "W8 packet directory")
    contract = load_owner_solo_contract(root)
    issues = validate_owner_solo_contract(contract)
    policy = _read_json(policy_path)
    execution = _read_json(execution_path)
    issues.extend(validate_owner_solo_exception_policy(policy))
    issues.extend(validate_owner_solo_execution_manifest(execution))
    repository = _repository_bindings(root)
    issues.extend(_binding_issues(policy, execution, repository, root))
    if issues:
        raise OwnerSoloQrelError("Owner-solo authority invalid: " + "; ".join(sorted(set(issues))))
    packet = _packet_content(
        frozen_packet_dir,
        query_manifest=repository["query_manifest"],
        registry=repository["registry"],
        expected=repository,
    )
    return {
        "repo_root": root,
        "runtime_dir": runtime,
        "contract": contract,
        "policy": policy,
        "execution": execution,
        "repository": repository,
        "packet": packet,
    }


def _visible_candidates(context: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    visible: dict[tuple[str, str], dict[str, Any]] = {}
    for item in context["packet"]["reviewer_a_items"]:
        item_ref = str(item.get("item_ref") or "")
        for candidate in item.get("candidates") or []:
            candidate_ref = str(candidate.get("candidate_ref") or "")
            key = (item_ref, candidate_ref)
            if not item_ref or not candidate_ref or key in visible:
                raise OwnerSoloQrelError("Reviewer A visible packet contains invalid references")
            visible[key] = {
                "item_ref": item_ref,
                "candidate_ref": candidate_ref,
                "target_context": str(item.get("target_context") or ""),
                "resume_section": str(item.get("resume_section") or ""),
                "evidence_cluster_text": str(candidate.get("evidence_cluster_text") or ""),
            }
    if len(visible) != 456:
        raise OwnerSoloQrelError("Reviewer A visible denominator is not 456")
    return visible


def _ledger_path(context: Mapping[str, Any]) -> Path:
    return Path(context["runtime_dir"]) / "returns" / "owner_solo_events.jsonl"


def _load_ledger(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = _ledger_path(context)
    return [] if not path.exists() else _read_jsonl(path)


def _ledger_file_sha256(context: Mapping[str, Any]) -> str | None:
    path = _ledger_path(context)
    return _file_sha256(path) if path.is_file() else None


def _final_qrel_path(context: Mapping[str, Any]) -> Path:
    return Path(context["runtime_dir"]) / "finalized" / "owner_solo_qrels.v1.json"


def _ensure_not_finalized(context: Mapping[str, Any]) -> None:
    if _final_qrel_path(context).exists():
        raise OwnerSoloQrelError(
            "Owner-solo QRELs are frozen; append a new review only in a new review run"
        )


def _event_issues(
    events: Sequence[Mapping[str, Any]],
    visible: Mapping[tuple[str, str], Mapping[str, Any]],
    owner_identity: str,
) -> tuple[list[str], dict[tuple[str, str], dict[str, Any]], int]:
    issues: list[str] = []
    active: dict[tuple[str, str], dict[str, Any]] = {}
    seen_ids: set[str] = set()
    corrections = 0
    expected_fields = {
        "schema_version",
        "event_id",
        "event_type",
        "item_ref",
        "candidate_ref",
        "relevance_grade",
        "rationale",
        "owner_identity_ref",
        "recorded_at",
        "prior_event_id",
        "event_digest",
    }
    for index, event in enumerate(events):
        prefix = f"EVENT:{index}"
        if set(event) != expected_fields:
            issues.append(f"{prefix}:FIELDS")
        if event.get("schema_version") != EVENT_SCHEMA_VERSION:
            issues.append(f"{prefix}:SCHEMA")
        event_id = str(event.get("event_id") or "")
        if not re.fullmatch(r"event-[0-9a-f]{32}", event_id) or event_id in seen_ids:
            issues.append(f"{prefix}:ID")
        seen_ids.add(event_id)
        if not _digest_matches(event, "event_digest"):
            issues.append(f"{prefix}:DIGEST")
        key = (str(event.get("item_ref") or ""), str(event.get("candidate_ref") or ""))
        if key not in visible:
            issues.append(f"{prefix}:VISIBLE_REFERENCE")
        grade = event.get("relevance_grade")
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
            issues.append(f"{prefix}:GRADE")
        if not str(event.get("rationale") or "").strip():
            issues.append(f"{prefix}:RATIONALE")
        if event.get("owner_identity_ref") != owner_identity:
            issues.append(f"{prefix}:OWNER")
        try:
            parsed = datetime.fromisoformat(str(event.get("recorded_at") or "").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            issues.append(f"{prefix}:TIMESTAMP")
        event_type = event.get("event_type")
        previous = active.get(key)
        if event_type == "RECORD":
            if event.get("prior_event_id") is not None or previous is not None:
                issues.append(f"{prefix}:DUPLICATE_RECORD")
            else:
                active[key] = dict(event)
        elif event_type == "CORRECTION":
            corrections += 1
            if previous is None or event.get("prior_event_id") != previous.get("event_id"):
                issues.append(f"{prefix}:CORRECTION_CHAIN")
            else:
                active[key] = dict(event)
        else:
            issues.append(f"{prefix}:TYPE")
    return sorted(set(issues)), active, corrections


def _append_event(context: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    path = _ledger_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _new_event(
    *,
    event_type: str,
    item_ref: str,
    candidate_ref: str,
    grade: int,
    rationale: str,
    owner_identity: str,
    prior_event_id: str | None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": f"event-{uuid.uuid4().hex}",
        "event_type": event_type,
        "item_ref": item_ref,
        "candidate_ref": candidate_ref,
        "relevance_grade": grade,
        "rationale": rationale,
        "owner_identity_ref": owner_identity,
        "recorded_at": _utc_now(),
        "prior_event_id": prior_event_id,
    }
    event["event_digest"] = canonical_sha256(event)
    return event


def _strict_grade(grade: object) -> int:
    if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
        raise OwnerSoloQrelError("Grade must be one explicit integer: 0, 1, 2, or 3")
    return grade


def _owner_identity(context: Mapping[str, Any]) -> str:
    identity = str((context["policy"].get("owner_reviewer") or {}).get("identity_ref") or "")
    if not identity.startswith("human-reviewer://"):
        raise OwnerSoloQrelError("Owner-solo policy has no valid human owner identity")
    return identity


def packet_validation_receipt(
    context: Mapping[str, Any], *, write: bool = True
) -> dict[str, Any]:
    """Record the successful W8 validation without showing it to a reviewer."""
    packet = context["packet"]
    manifest = packet["packet_manifest"]
    visible = _visible_candidates(context)
    sealed = _sealed_lookup(context)
    reviewer_a = packet["cohort_metadata"]["reviewer_a"]
    receipt: dict[str, Any] = {
        "schema_version": PACKET_RECEIPT_SCHEMA_VERSION,
        "status": "PASS_VALIDATED_BLINDED_W8_PACKET",
        "result_label": RESULT_LABEL,
        "packet_manifest_file_sha256": packet["packet_manifest_file_sha256"],
        "packet_manifest_sha256": manifest["manifest_sha256"],
        "canonical_packet_manifest_digest_valid": True,
        "reviewer_a_manifest_sha256": reviewer_a["reviewer_manifest_sha256"],
        "reviewer_a_manifest_file_sha256": reviewer_a[
            "reviewer_manifest_file_sha256"
        ],
        "reviewer_a_review_items_file_sha256": reviewer_a[
            "review_items_file_sha256"
        ],
        "sealed_mapping_file_sha256": packet["sealed_mapping_file_sha256"],
        "ranking_identity_sha256": manifest["ranking_identity_sha256"],
        "query_manifest_sha256": context["repository"]["binding"][
            "query_manifest_sha256"
        ],
        "registry_sha256": context["repository"]["binding"]["registry_sha256"],
        "projection_generation_sha256": context["repository"]["binding"][
            "projection_generation_sha256"
        ],
        "reviewer_a_item_count": len(packet["reviewer_a_items"]),
        "reviewer_a_candidate_judgment_count": len(visible),
        "sealed_mapping_candidate_judgment_count": len(sealed),
        "reviewer_visible_rank_score_split_identity_leakage": False,
        "reviewer_a_only_for_owner_scoring": True,
        "human_labels_present": False,
        "independent_qrel_authority": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    if write:
        _write_json(
            Path(context["runtime_dir"]) / "packet_validation_receipt.v1.json",
            receipt,
            create_once=False,
        )
    return receipt


def _progress_receipt(context: Mapping[str, Any]) -> dict[str, Any]:
    visible = _visible_candidates(context)
    events = _load_ledger(context)
    issues, active, corrections = _event_issues(events, visible, _owner_identity(context))
    completed = len(active)
    status = (
        "BLOCKED_INVALID_OWNER_SOLO_LEDGER"
        if issues
        else "READY_TO_FINALIZE_OWNER_SOLO_PROVISIONAL"
        if completed == len(visible)
        else "IN_PROGRESS_OWNER_SOLO_PROVISIONAL"
        if completed
        else "READY_FOR_OWNER_SOLO_HUMAN_REVIEW"
    )
    receipt: dict[str, Any] = {
        "schema_version": PROGRESS_RECEIPT_SCHEMA_VERSION,
        "result_label": RESULT_LABEL,
        "status": status,
        "completed_judgment_count": completed,
        "remaining_judgment_count": len(visible) - completed,
        "malformed_or_duplicate_count": len(issues),
        "correction_count": corrections,
        "packet_manifest_sha256": context["packet"]["packet_manifest"]["manifest_sha256"],
        "policy_digest": context["policy"]["record_digest"],
        "last_event_digest": events[-1]["event_digest"] if events else None,
        "append_only_ledger_file_sha256": _ledger_file_sha256(context),
        "independent_reviewer_present": False,
        "independent_adjudicator_present": False,
        "inter_rater_reliability_available": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
        "ledger_issues": issues,
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    return receipt


def status_receipt(context: Mapping[str, Any], *, write: bool = True) -> dict[str, Any]:
    packet_receipt = packet_validation_receipt(context, write=write)
    receipt = _progress_receipt(context)
    receipt["packet_validation_receipt_digest"] = packet_receipt["receipt_digest"]
    receipt["receipt_digest"] = canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    if write:
        _write_json(Path(context["runtime_dir"]) / "progress_receipt.v1.json", receipt, create_once=False)
    return receipt


def next_blinded_candidate(context: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return exactly reviewer-visible fields for the next ungraded candidate."""
    visible = _visible_candidates(context)
    events = _load_ledger(context)
    issues, active, _corrections = _event_issues(events, visible, _owner_identity(context))
    if issues:
        raise OwnerSoloQrelError("Cannot continue with invalid ledger: " + "; ".join(issues))
    for key, candidate in visible.items():
        if key not in active:
            return {
                "item_ref": candidate["item_ref"],
                "target_context": candidate["target_context"],
                "resume_section": candidate["resume_section"],
                "candidate_ref": candidate["candidate_ref"],
                "evidence_cluster_text": candidate["evidence_cluster_text"],
                "completed_count": len(active),
                "total_count": len(visible),
            }
    return None


def record_judgment(
    context: Mapping[str, Any],
    *,
    item_ref: str,
    candidate_ref: str,
    grade: int,
    rationale: str,
) -> dict[str, Any]:
    """Append one explicit human grade. Existing grades require ``correct``."""
    _ensure_not_finalized(context)
    grade = _strict_grade(grade)
    if not rationale.strip():
        raise OwnerSoloQrelError("Human rationale must be nonempty")
    visible = _visible_candidates(context)
    key = (item_ref, candidate_ref)
    if key not in visible:
        raise OwnerSoloQrelError("Unknown opaque item/candidate reference")
    events = _load_ledger(context)
    issues, active, _corrections = _event_issues(events, visible, _owner_identity(context))
    if issues:
        raise OwnerSoloQrelError("Cannot record into invalid ledger: " + "; ".join(issues))
    if key in active:
        raise OwnerSoloQrelError("Candidate already has an active grade; use correct")
    event = _new_event(
        event_type="RECORD",
        item_ref=item_ref,
        candidate_ref=candidate_ref,
        grade=grade,
        rationale=rationale,
        owner_identity=_owner_identity(context),
        prior_event_id=None,
    )
    _append_event(context, event)
    return {"event": event, "progress": status_receipt(context, write=True)}


def correct_judgment(
    context: Mapping[str, Any],
    *,
    item_ref: str,
    candidate_ref: str,
    grade: int,
    rationale: str,
) -> dict[str, Any]:
    """Append a correction event; never overwrite a prior human return."""
    _ensure_not_finalized(context)
    grade = _strict_grade(grade)
    if not rationale.strip():
        raise OwnerSoloQrelError("Human rationale must be nonempty")
    visible = _visible_candidates(context)
    key = (item_ref, candidate_ref)
    if key not in visible:
        raise OwnerSoloQrelError("Unknown opaque item/candidate reference")
    events = _load_ledger(context)
    issues, active, _corrections = _event_issues(events, visible, _owner_identity(context))
    if issues:
        raise OwnerSoloQrelError("Cannot correct invalid ledger: " + "; ".join(issues))
    prior = active.get(key)
    if prior is None:
        raise OwnerSoloQrelError("Candidate has no prior active grade; use record")
    event = _new_event(
        event_type="CORRECTION",
        item_ref=item_ref,
        candidate_ref=candidate_ref,
        grade=grade,
        rationale=rationale,
        owner_identity=_owner_identity(context),
        prior_event_id=str(prior["event_id"]),
    )
    _append_event(context, event)
    return {"event": event, "progress": status_receipt(context, write=True)}


def _sealed_lookup(context: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    sealed = (context["packet"]["sealed_mapping"].get("cohorts") or {}).get("reviewer_a") or []
    for item in sealed:
        item_ref = str(item.get("item_ref") or "")
        for candidate in item.get("candidates") or []:
            key = (item_ref, str(candidate.get("candidate_ref") or ""))
            if key in lookup or not item_ref or not key[1]:
                raise OwnerSoloQrelError("Invalid sealed mapping conservation")
            lookup[key] = {
                "query_id": str(item.get("query_id") or ""),
                "section_id": str(item.get("section_id") or ""),
                "cluster_id": str(candidate.get("cluster_id") or ""),
                "frozen_rank": candidate.get("frozen_rank"),
            }
    if len(lookup) != 456:
        raise OwnerSoloQrelError("Sealed mapping denominator is not 456")
    return lookup


def finalize_owner_solo_qrels(context: Mapping[str, Any]) -> dict[str, Any]:
    """Create a private, provisional QREL artifact only after 456 human grades."""
    visible = _visible_candidates(context)
    events = _load_ledger(context)
    issues, active, corrections = _event_issues(events, visible, _owner_identity(context))
    if issues:
        raise OwnerSoloQrelError("Cannot finalize invalid ledger: " + "; ".join(issues))
    if len(active) != 456:
        raise OwnerSoloQrelError(
            f"Cannot finalize before 456 active explicit grades; observed {len(active)}"
        )
    mapping = _sealed_lookup(context)
    if set(active) != set(mapping):
        raise OwnerSoloQrelError("Visible-to-sealed candidate conservation failed")
    judgments = [
        {
            "query_id": mapped["query_id"],
            "section_id": mapped["section_id"],
            "cluster_id": mapped["cluster_id"],
            "relevance_grade": event["relevance_grade"],
            "human_rationale": event["rationale"],
            "owner_identity_ref": event["owner_identity_ref"],
            "event_id": event["event_id"],
            "event_digest": event["event_digest"],
        }
        for key, event in active.items()
        for mapped in [mapping[key]]
    ]
    judgments.sort(key=lambda row: (row["query_id"], row["section_id"], row["cluster_id"]))
    keys = {(row["query_id"], row["section_id"], row["cluster_id"]) for row in judgments}
    if len(judgments) != 456 or len(keys) != 456:
        raise OwnerSoloQrelError("Final QREL denominator is not exactly 456 unique keys")
    binding = context["repository"]["binding"]
    qrels: dict[str, Any] = {
        "schema_version": QREL_SCHEMA_VERSION,
        "status": FINAL_QREL_STATUS,
        "result_label": RESULT_LABEL,
        "source_authority": {
            "source_commit": context["policy"]["repository_binding"]["source_commit"],
            "query_manifest_sha256": binding["query_manifest_sha256"],
            "registry_sha256": binding["registry_sha256"],
            "projection_generation_sha256": binding["projection_generation_sha256"],
            "ranking_identity_sha256": binding["ranking_identity_sha256"],
            "w8_packet_manifest_sha256": binding["w8_packet_manifest_sha256"],
            "w8_packet_manifest_file_sha256": context["packet"][
                "packet_manifest_file_sha256"
            ],
            "sealed_mapping_file_sha256": context["packet"]["packet_manifest"][
                "sealed_mapping_file_sha256"
            ],
            "owner_solo_policy_digest": context["policy"]["record_digest"],
            "append_only_ledger_file_sha256": _ledger_file_sha256(context),
            "append_only_ledger_event_count": len(events),
            "append_only_ledger_last_event_digest": events[-1]["event_digest"],
        },
        "human_review_authority": {
            "reviewer_count": 1,
            "owner_identity_ref": _owner_identity(context),
            "independent_reviewer_present": False,
            "independent_adjudicator_present": False,
            "inter_rater_reliability_available": False,
            "adjudication_mode": "OWNER_SELF_ADJUDICATION_WAIVED_BY_EXCEPTION",
        },
        "judgment_count": 456,
        "relevant_grade_floor": 2,
        "judgments": judgments,
        "non_release_authorizing": True,
        "independent_qrel_authority": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }
    qrels["qrel_digest"] = canonical_sha256(qrels)
    receipt: dict[str, Any] = {
        "schema_version": FINALIZATION_RECEIPT_SCHEMA_VERSION,
        "status": "OWNER_SOLO_PROVISIONAL_QRELS_COMPLETE",
        "result_label": RESULT_LABEL,
        "qrel_digest": qrels["qrel_digest"],
        "judgment_count": 456,
        "correction_count": corrections,
        "packet_manifest_sha256": binding["w8_packet_manifest_sha256"],
        "policy_digest": context["policy"]["record_digest"],
        "append_only_ledger_file_sha256": _ledger_file_sha256(context),
        "independent_qrel_authority": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    final_dir = _final_qrel_path(context).parent
    _write_json(_final_qrel_path(context), qrels, create_once=True)
    _write_json(final_dir / "owner_solo_finalization_receipt.v1.json", receipt, create_once=True)
    status_receipt(context, write=True)
    return {"qrels": qrels, "receipt": receipt}


def _aggregate_pair_metrics(
    pair_rows: Sequence[dict[str, Any]],
) -> dict[str, float | int]:
    recalls = [float(row["recall_at_10"]) for row in pair_rows]
    ndcgs = [float(row["ndcg_at_10"]) for row in pair_rows]
    rrs = [float(row["mrr"]) for row in pair_rows]
    relevant = sum(int(row["relevant_count"]) for row in pair_rows)
    hits = sum(int(row["relevant_hits_at_10"]) for row in pair_rows)
    return {
        "query_section_count": len(pair_rows),
        "macro_recall_at_10": math.fsum(recalls) / len(recalls),
        "pooled_recall_at_10": hits / relevant if relevant else 0.0,
        "macro_ndcg_at_10": math.fsum(ndcgs) / len(ndcgs),
        "macro_mrr": math.fsum(rrs) / len(rrs),
    }


def compute_owner_solo_metrics(context: Mapping[str, Any]) -> dict[str, Any]:
    """Compute diagnostics after private finalization; never release qualification."""
    qrel_path = _final_qrel_path(context)
    qrels = _read_json(qrel_path)
    if qrels.get("schema_version") != QREL_SCHEMA_VERSION or qrels.get("status") != FINAL_QREL_STATUS or qrels.get("result_label") != RESULT_LABEL or qrels.get("non_release_authorizing") is not True:
        raise OwnerSoloQrelError("Owner-solo QREL artifact is not provisional-only")
    if not _digest_matches(qrels, "qrel_digest") or qrels.get("judgment_count") != 456:
        raise OwnerSoloQrelError("Owner-solo QREL artifact digest or denominator invalid")
    binding = context["repository"]["binding"]
    expected_source = {
        "source_commit": context["policy"]["repository_binding"]["source_commit"],
        "query_manifest_sha256": binding["query_manifest_sha256"],
        "registry_sha256": binding["registry_sha256"],
        "projection_generation_sha256": binding["projection_generation_sha256"],
        "ranking_identity_sha256": binding["ranking_identity_sha256"],
        "w8_packet_manifest_sha256": binding["w8_packet_manifest_sha256"],
        "w8_packet_manifest_file_sha256": context["packet"][
            "packet_manifest_file_sha256"
        ],
        "sealed_mapping_file_sha256": context["packet"]["packet_manifest"][
            "sealed_mapping_file_sha256"
        ],
        "owner_solo_policy_digest": context["policy"]["record_digest"],
    }
    source = qrels.get("source_authority") or {}
    if any(source.get(field) != value for field, value in expected_source.items()):
        raise OwnerSoloQrelError("Owner-solo QREL source binding mismatch")
    if (
        source.get("append_only_ledger_file_sha256") != _ledger_file_sha256(context)
        or source.get("append_only_ledger_event_count") != len(_load_ledger(context))
    ):
        raise OwnerSoloQrelError("Owner-solo QREL append-only ledger binding mismatch")
    labels: dict[tuple[str, str, str], int] = {}
    for row in qrels.get("judgments") or []:
        key = (str(row.get("query_id") or ""), str(row.get("section_id") or ""), str(row.get("cluster_id") or ""))
        grade = row.get("relevance_grade")
        if key in labels or not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
            raise OwnerSoloQrelError("Owner-solo QREL contains invalid labels")
        labels[key] = grade
    ranking_by_pair: dict[str, list[str]] = {}
    mapping = _sealed_lookup(context)
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (item_ref, _candidate_ref), value in mapping.items():
        by_item[item_ref].append(value)
    for values in by_item.values():
        query_id = values[0]["query_id"]
        section_id = values[0]["section_id"]
        pair = f"{query_id}|{section_id}"
        ranking_by_pair[pair] = [
            str(row["cluster_id"])
            for row in sorted(values, key=lambda row: int(row["frozen_rank"]))
        ]
    if ranking_identity_sha256(ranking_by_pair) != binding["ranking_identity_sha256"]:
        raise OwnerSoloQrelError("Frozen ranking identity mismatch during metric computation")
    query_info = {
        str(row["query_id"]): {
            "split": str(row["split"]),
            "target_profile_id": str(row["target_profile_id"]),
        }
        for row in context["repository"]["query_manifest"]["queries"]
    }
    pair_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for pair, ranking in sorted(ranking_by_pair.items()):
        query_id, section_id = pair.split("|", 1)
        relevance = {cluster_id: labels[(query_id, section_id, cluster_id)] for cluster_id in ranking}
        relevant = {cluster_id for cluster_id, grade in relevance.items() if grade >= 2}
        if not relevant:
            failures.append(f"NO_RELEVANT_CLUSTER:{pair}")
            continue
        hits = relevant & set(ranking[:10])
        actual_dcg = math.fsum(
            (2.0 ** relevance[cluster_id] - 1.0) / math.log2(rank + 1.0)
            for rank, cluster_id in enumerate(ranking[:10], start=1)
        )
        ideal_dcg = math.fsum(
            (2.0**grade - 1.0) / math.log2(rank + 1.0)
            for rank, grade in enumerate(sorted(relevance.values(), reverse=True)[:10], start=1)
        )
        first = next((rank for rank, cluster_id in enumerate(ranking, start=1) if cluster_id in relevant), None)
        pair_rows.append(
            {
                "query_id": query_id,
                "section_id": section_id,
                "target_profile_id": query_info[query_id]["target_profile_id"],
                "split": query_info[query_id]["split"],
                "relevant_count": len(relevant),
                "relevant_hits_at_10": len(hits),
                "recall_at_10": len(hits) / len(relevant),
                "ndcg_at_10": actual_dcg / ideal_dcg if ideal_dcg else 0.0,
                "mrr": 1.0 / first if first else 0.0,
            }
        )
    if failures:
        return {
            "schema_version": METRICS_RECEIPT_SCHEMA_VERSION,
            "status": "BLOCKED_METRIC_DENOMINATOR",
            "result_label": RESULT_LABEL,
            "failures": failures,
            "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        }
    scopes = {
        "calibration": [row for row in pair_rows if row["split"] == "CALIBRATION"],
        "holdout": [row for row in pair_rows if row["split"] == "HOLDOUT"],
        "combined_diagnostic": pair_rows,
    }
    profile_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    section_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pair_rows:
        profile_rows[row["target_profile_id"]].append(row)
        section_rows[row["section_id"]].append(row)
    grades = Counter(labels.values())
    top_ten_grade_counts = Counter(
        labels[(query_id, section_id, cluster_id)]
        for pair, ranking in ranking_by_pair.items()
        for query_id, section_id in [tuple(pair.split("|", 1))]
        for cluster_id in ranking[:10]
    )
    receipt: dict[str, Any] = {
        "schema_version": METRICS_RECEIPT_SCHEMA_VERSION,
        "status": RESULT_LABEL,
        "metric_label": "OWNER_SOLO_PROVISIONAL — NOT INDEPENDENT RELEASE EVIDENCE",
        "relevant_grade_floor": 2,
        "query_level": pair_rows,
        "aggregate": {name: _aggregate_pair_metrics(rows) for name, rows in scopes.items()},
        "by_target_profile": {name: _aggregate_pair_metrics(rows) for name, rows in sorted(profile_rows.items())},
        "by_resume_section": {name: _aggregate_pair_metrics(rows) for name, rows in sorted(section_rows.items())},
        "by_relevance_grade": {
            str(grade): {
                "judgment_count": grades[grade],
                "top_10_count": top_ten_grade_counts[grade],
                "top_10_rate": top_ten_grade_counts[grade] / grades[grade] if grades[grade] else 0.0,
            }
            for grade in range(4)
        },
        "hard_negative_slice": {
            "status": "NOT_AVAILABLE_FROM_FROZEN_CLUSTER_PACKET",
            "reason": "No hard-negative coverage tags are present in the W8 reviewer A packet.",
        },
        "policy_restricted_slice": {
            "status": "NOT_AVAILABLE_FROM_FROZEN_CLUSTER_PACKET",
            "reason": "No policy-restricted coverage tags are present in the W8 reviewer A packet.",
        },
        "holdout_tuning_prohibited": True,
        "independent_qrel_authority": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }
    receipt["receipt_digest"] = canonical_sha256(receipt)
    _write_json(Path(context["runtime_dir"]) / "finalized" / "owner_solo_metrics.v1.json", receipt, create_once=False)
    return receipt


def evaluate_owner_solo_non_retrieval_gates(context: Mapping[str, Any]) -> dict[str, Any]:
    """Report available structural gates without substituting runtime evidence."""
    packet = context["packet"]["packet_manifest"]
    checks = {
        "authority_bypass": "PASS_PACKET_BINDINGS_VALIDATED",
        "lifecycle_violation": "PASS_FROZEN_UNLABELED_PACKET",
        "policy_leakage": "PASS_REVIEWER_A_BLINDING_VALIDATED",
        "wrong_section_projection": "PASS_SEALED_DENOMINATOR_VALIDATED",
        "wrong_employer_projection": "NOT_MEASURED_NO_OWNER_SOLO_RUNTIME_RUN",
        "unsupported_claim_projection": "NOT_MEASURED_NO_OWNER_SOLO_RUNTIME_RUN",
        "duplicate_or_orphan_cluster_projection": "PASS_SEALED_CONSERVATION_VALIDATED",
        "bounded_k_compliance": "PASS_FROZEN_RANK_CONSERVATION_VALIDATED",
        "deterministic_ranking": "PASS_FROZEN_RANKING_IDENTITY_VALIDATED",
        "deterministic_rehydration": "PASS_SEALED_MAPPING_CONSERVATION_VALIDATED",
        "cold_warm_latency": "NOT_MEASURED_NO_OWNER_SOLO_RUNTIME_RUN",
        "timeout_and_error_rate": "NOT_MEASURED_NO_OWNER_SOLO_RUNTIME_RUN",
        "missing_or_invalid_manifest_handling": "PASS_FAIL_CLOSED_VALIDATOR",
    }
    return {
        "schema_version": "apps_rg.owner_solo_qrel_non_retrieval_gate_receipt.v1",
        "status": RESULT_LABEL,
        "packet_manifest_sha256": packet["manifest_sha256"],
        "checks": checks,
        "independent_qrel_authority": False,
        "release_qualification": "BLOCKED_UNDER_EXISTING_TWO_REVIEWER_CONTRACT",
        "activation_manifest_created": False,
        "production_promotion_authorized": False,
    }


__all__ = [
    "CONTRACT_PATH",
    "EVENT_SCHEMA_VERSION",
    "FINAL_QREL_STATUS",
    "OwnerSoloQrelError",
    "PACKET_RECEIPT_SCHEMA_VERSION",
    "RESULT_LABEL",
    "compute_owner_solo_metrics",
    "correct_judgment",
    "evaluate_owner_solo_non_retrieval_gates",
    "finalize_owner_solo_qrels",
    "load_owner_solo_context",
    "load_owner_solo_contract",
    "next_blinded_candidate",
    "packet_validation_receipt",
    "record_judgment",
    "status_receipt",
    "validate_owner_solo_contract",
    "validate_owner_solo_exception_policy",
    "validate_owner_solo_execution_manifest",
]
