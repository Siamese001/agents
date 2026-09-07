"""W0 validation for the owner-solo, full-resume C0.3 QREL scope.

This module deliberately freezes scope only.  It does not create a ranking,
packet, human grade, QREL, retrieval metric, activation manifest, or release
authority.  The existing W8/W9 authoritative contract remains untouched.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (
    canonical_sha256,
)


SCOPE_PATH = Path(
    "src/apps_rg/evals/owner_solo/c03_full_resume_qrel_scope.v1.json"
)
SCHEMA_VERSION = "apps_rg.owner_solo_full_resume_qrel_scope.v1"
SCOPE_STATUS = "FROZEN_OWNER_SOLO_PROVISIONAL_SCOPE"
RESULT_LABEL = "OWNER_SOLO_PROVISIONAL"

EXPECTED_SECTION_IDS = (
    "headline",
    "executive_summary",
    "competencies",
    "unify_bullets",
    "unify_narrative",
    "ibm_bullets",
    "ibm_narrative",
    "ey_bullets",
    "ey_narrative",
    "insurtech_bullets",
    "insurtech_narrative",
)
EXPECTED_SPLITS = {"CALIBRATION": 3, "HOLDOUT": 3}


class FullResumeQrelScopeError(ValueError):
    """Raised when the frozen W0 full-resume scope is not trustworthy."""


def _is_sha256(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def _is_git_sha(value: object) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", str(value or "")))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullResumeQrelScopeError(f"JSON unavailable: {path}") from exc
    if not isinstance(result, dict):
        raise FullResumeQrelScopeError(f"JSON object required: {path}")
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FullResumeQrelScopeError(f"File unavailable: {path}") from exc
    return digest.hexdigest()


def _head_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value if _is_git_sha(value) else None


def load_full_resume_scope(repo_root: Path | str) -> dict[str, Any]:
    """Load the repository-owned W0 scope manifest."""

    return _read_json(Path(repo_root).resolve() / SCOPE_PATH)


def validate_full_resume_scope(
    scope: Mapping[str, Any], repo_root: Path | str
) -> list[str]:
    """Return all fail-closed W0 validation issues, without writing artifacts."""

    root = Path(repo_root).resolve()
    issues: list[str] = []
    if scope.get("schema_version") != SCHEMA_VERSION:
        issues.append("SCHEMA_VERSION")
    if scope.get("status") != SCOPE_STATUS:
        issues.append("SCOPE_STATUS")
    if scope.get("result_label") != RESULT_LABEL:
        issues.append("RESULT_LABEL")

    unsigned = dict(scope)
    digest = unsigned.pop("scope_manifest_sha256", None)
    if not _is_sha256(digest) or canonical_sha256(unsigned) != digest:
        issues.append("SCOPE_DIGEST")

    authoritative = scope.get("authoritative_lane_boundary")
    required_authoritative = (
        "existing_two_reviewer_contract_unchanged",
        "existing_independent_adjudication_contract_unchanged",
        "authoritative_release_qualification_not_satisfied",
    )
    if not isinstance(authoritative, Mapping) or any(
        authoritative.get(field) is not True for field in required_authoritative
    ):
        issues.append("AUTHORITATIVE_BOUNDARY")

    unit = scope.get("review_unit")
    if not isinstance(unit, Mapping) or unit.get("logical_retrieval_unit") != "graph_evidence_cluster" or unit.get("judgment_question") != "Is this graph-evidence cluster appropriate source material for this target job and resume section?":
        issues.append("REVIEW_UNIT")

    sections = scope.get("resume_sections")
    if not isinstance(sections, list) or tuple(
        entry.get("section_id") for entry in sections if isinstance(entry, Mapping)
    ) != EXPECTED_SECTION_IDS:
        issues.append("RESUME_SECTIONS")
    elif any(entry.get("c0_retrieval_qrel_required") is not True for entry in sections):
        issues.append("SECTION_C0_REQUIREMENT")

    targets = scope.get("targets")
    if not isinstance(targets, list) or len(targets) != 6:
        issues.append("TARGET_COUNT")
    else:
        splits = Counter(str(target.get("split") or "") for target in targets)
        query_ids = [str(target.get("query_id") or "") for target in targets]
        if splits != EXPECTED_SPLITS or len(set(query_ids)) != len(query_ids) or not all(query_ids):
            issues.append("TARGET_SPLIT_OR_IDENTITY")
        for target in targets:
            if not isinstance(target, Mapping):
                issues.append("TARGET_SHAPE")
                continue
            for path_field, digest_field in (
                ("jd_path", "jd_sha256"),
                ("brief_path", "brief_sha256"),
            ):
                relative = target.get(path_field)
                expected_digest = target.get(digest_field)
                path = root / str(relative or "")
                if not isinstance(relative, str) or not _is_sha256(expected_digest):
                    issues.append(f"TARGET_{path_field.upper()}_BINDING")
                elif not path.is_file() or _file_sha256(path) != expected_digest:
                    source_name = "JD" if path_field == "jd_path" else "BRIEF"
                    issues.append(f"TARGET_{source_name}_DIGEST")

    denominator = scope.get("planned_denominator")
    expected_denominator = {
        "query_count": 6,
        "calibration_query_count": 3,
        "holdout_query_count": 3,
        "section_count": 11,
        "query_section_case_count": 66,
        "candidate_judgment_count": None,
        "candidate_judgment_count_freezes_in_w1": True,
        "full_finite_candidate_universe_required": True,
        "partial_top_k_judging_forbidden": True,
        "relevant_grade_floor": 2,
    }
    if not isinstance(denominator, Mapping) or any(
        denominator.get(field) != value
        for field, value in expected_denominator.items()
    ):
        issues.append("PLANNED_DENOMINATOR")

    w1 = scope.get("w1_prerequisites")
    required_w1 = (
        "all_66_query_section_rankings_frozen_before_human_review",
        "all_candidate_universes_enumerated_before_human_review",
        "headline_and_ibm_c0_paths_must_be_validated",
        "blinded_owner_reviewer_packet_required",
        "no_human_grade_created_by_w0",
    )
    if not isinstance(w1, Mapping) or any(w1.get(field) is not True for field in required_w1):
        issues.append("W1_PREREQUISITES")

    binding = scope.get("repository_binding")
    if not isinstance(binding, Mapping) or binding.get("repository") != "Siamese001/apps_rg_v2" or not _is_git_sha(binding.get("source_commit")):
        issues.append("REPOSITORY_BINDING")
    else:
        head = _head_commit(root)
        if head != binding.get("source_commit"):
            issues.append("SOURCE_COMMIT")
        treatment = binding.get("section_treatment_profile")
        if not isinstance(treatment, Mapping):
            issues.append("SECTION_PROFILE_BINDING")
        else:
            path = root / str(treatment.get("path") or "")
            if not _is_sha256(treatment.get("sha256")) or not path.is_file() or _file_sha256(path) != treatment.get("sha256"):
                issues.append("SECTION_PROFILE_DIGEST")

    return sorted(set(issues))


def scope_status(repo_root: Path | str) -> dict[str, Any]:
    """Provide a compact, non-mutating W0 readiness receipt."""

    root = Path(repo_root).resolve()
    scope = load_full_resume_scope(root)
    issues = validate_full_resume_scope(scope, root)
    denominator = scope.get("planned_denominator") or {}
    return {
        "schema_version": "apps_rg.owner_solo_full_resume_qrel_scope_status.v1",
        "status": "W0_FROZEN_READY_FOR_W1" if not issues else "W0_BLOCKED",
        "scope_status": scope.get("status"),
        "query_count": denominator.get("query_count"),
        "section_count": denominator.get("section_count"),
        "query_section_case_count": denominator.get("query_section_case_count"),
        "candidate_judgment_count": denominator.get("candidate_judgment_count"),
        "next_required_action": "W1_FREEZE_FULL_CANDIDATE_UNIVERSES_AND_RANKINGS",
        "human_qrels_created": False,
        "release_authorizing": False,
        "issues": issues,
    }
