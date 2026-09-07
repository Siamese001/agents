"""Record local-branch acceptance of a completed zero-LLM RCA evidence chain."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ACCEPTANCE_FILENAME = "single_run_w6_local_evidence_acceptance.json"
SCHEMA_VERSION = "apps_rg.single_run_rca_w6.v1"
_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_ZERO_COUNTERS = ("provider_calls", "model_calls", "judge_calls", "embedding_calls", "network_attempts", "subprocess_attempts")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value, payload


def _binding(path: Path, payload: bytes) -> dict[str, Any]:
    parsed = json.loads(payload.decode("utf-8"))
    return {
        "artifact_ref": path.name,
        "byte_length": len(payload),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "semantic_digest": str(parsed.get("semantic_digest", "")),
    }


def emit_single_run_w6_local_acceptance(
    *,
    w5_closeout_path: Path,
    branch_name: str,
    pre_acceptance_head: str,
    verified_commit_ids: list[str],
    output_dir: Path,
) -> dict[str, Any]:
    """Record local-only evidence acceptance after caller-proven Git ancestry."""

    closeout_path = w5_closeout_path.resolve(strict=True)
    closeout, closeout_bytes = _read(closeout_path)
    primary = closeout.get("zero_llm_runtime", {}).get("primary_guard_counters")
    finalization = closeout.get("zero_llm_runtime", {}).get("finalization_guard_counters")
    commits = sorted(set(verified_commit_ids))
    if (
        closeout.get("status") != "PASS"
        or closeout.get("scope_complete") is not True
        or closeout.get("w6_authorized") is not True
        or closeout.get("w6_contract") != "EVIDENCE_ACCEPTANCE_ONLY"
        or closeout.get("terminal_state") != "BLOCKED_NON_PRODUCT"
        or closeout.get("production_authority_granted") is not False
        or closeout.get("publication_allowed") is not False
        or not isinstance(primary, dict)
        or not isinstance(finalization, dict)
        or any(primary.get(key) != 0 or finalization.get(key) != 0 for key in _ZERO_COUNTERS)
        or not branch_name.strip()
        or not _SHA.fullmatch(pre_acceptance_head)
        or len(commits) != 6
        or any(not _SHA.fullmatch(commit) for commit in commits)
    ):
        raise ValueError("W6 local evidence acceptance prerequisites are not satisfied")
    acceptance: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "wave": "W6",
        "status": "PASS",
        "scope_complete": True,
        "scope": "LOCAL_SINGLE_RUN_RCA_EVIDENCE_ACCEPTANCE",
        "source_run_id": closeout["source_run_id"],
        "source_manifest_sha256": closeout["source_manifest_sha256"],
        "w5_closeout": _binding(closeout_path, closeout_bytes),
        "local_branch": {
            "name": branch_name,
            "pre_acceptance_head": pre_acceptance_head,
            "verified_ancestor_commits": commits,
        },
        "acceptance_status": "LOCAL_EVIDENCE_ACCEPTED",
        "accepted_scope": ["single_run_rca", "zero_llm_closeout", "branch_local_evidence_record"],
        "excluded_scope": ["remote_publication", "product_authorization", "publication_authorization", "live_model_pin_qualification", "human_calibration"],
        "production_authority_granted": False,
        "publication_allowed": False,
        "zero_llm_preserved": True,
    }
    acceptance["semantic_digest"] = _digest(acceptance)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ACCEPTANCE_FILENAME
    path.write_text(json.dumps(acceptance, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {**acceptance, "acceptance_path": path.as_posix()}


__all__ = ["ACCEPTANCE_FILENAME", "SCHEMA_VERSION", "emit_single_run_w6_local_acceptance"]
