"""Atomic Compare-and-Swap (CAS) commit engine with absent-key tracking and rollback handles."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from agents.learning.eligibility import validate_learning_approval_origin
from agents.learning.policy_router import evaluate_auto_apply_policy
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file, stable_id
from apps_eval.contracts.schemas import (
    AppliedChangeReceipt,
    HoldoutReplayVerdict,
    ImprovementProposal,
    utc_now_iso,
)


class CommitPreconditionError(RuntimeError):
    """Raised when CAS, duplicate-apply, policy, or approval preconditions fail closed."""


def _get_nested_key(data: Mapping[str, Any], dotted_key: str) -> tuple[bool, Any]:
    cur: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _set_nested_key(data: dict[str, Any], dotted_key: str, value: Any) -> list[str]:
    """Set dotted_key in nested dict and return list of newly created dotted keys (absent_keys)."""
    parts = dotted_key.split(".")
    cur = data
    absent: list[str] = []
    prefix: list[str] = []
    for part in parts[:-1]:
        prefix.append(part)
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
            absent.append(".".join(prefix))
        cur = cur[part]
    leaf = parts[-1]
    if leaf not in cur:
        absent.append(dotted_key)
    cur[leaf] = value
    return absent


def _values_match_cas(live: Any, expected: Any) -> bool:
    if isinstance(live, (int, float)) and isinstance(expected, (int, float)) and not isinstance(live, bool):
        return math.isclose(float(live), float(expected), rel_tol=0.0, abs_tol=1e-6)
    return live == expected


def _load_structured_file(path: Path) -> tuple[str, dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return "json", dict(json.loads(raw) or {})
    return "yaml", dict(yaml.safe_load(raw) or {})


def _atomic_write_structured(path: Path, fmt: str, data: Mapping[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    if fmt == "json":
        text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    else:
        text = yaml.safe_dump(dict(data), sort_keys=False)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def apply_proposal_atomically(
    *,
    proposal: ImprovementProposal,
    holdout_verdict: HoldoutReplayVerdict,
    repo_root: Path,
    ledger_store: SqliteLearningLedgerStore,
    rollback_dir: Path,
    target_file_override: Path | None = None,
    approval_receipt: Mapping[str, Any] | None = None,
    confidence_margin: float = 0.30,
    now_utc: datetime | None = None,
) -> AppliedChangeReceipt:
    """Validate policy, approval, CAS, snapshot pre-state + absent_keys, and commit atomically."""
    if ledger_store.has_active_apply(proposal.proposal_id):
        raise CommitPreconditionError(f"DUPLICATE_APPLY_BLOCKED:{proposal.proposal_id}")

    decision = evaluate_auto_apply_policy(
        proposal=proposal,
        holdout_verdict=holdout_verdict,
        repo_root=repo_root,
        ledger_store=ledger_store,
        confidence_margin=confidence_margin,
        now_utc=now_utc,
    )

    if decision.requires_pr:
        raise CommitPreconditionError(f"TIER_C_PR_ONLY_CANNOT_AUTO_APPLY:{decision.blocking_reasons}")

    approval_id: str | None = None
    if decision.auto_apply_permitted:
        approval_origin = "POLICY_TIER_A_AUTO"
    elif decision.requires_hitl:
        if approval_receipt is None:
            raise CommitPreconditionError(f"HITL_APPROVAL_REQUIRED:{decision.blocking_reasons}")
        ok_origin, origin_msg = validate_learning_approval_origin(approval_receipt)
        if not ok_origin:
            raise CommitPreconditionError(origin_msg)
        if str(approval_receipt.get("proposal_digest") or "") != proposal.canonical_digest:
            raise CommitPreconditionError("APPROVAL_PROPOSAL_DIGEST_MISMATCH")
        approval_id = str(approval_receipt.get("approval_receipt_id") or "")
        approval_origin = "HUMAN_HITL_APPROVED"
    else:
        raise CommitPreconditionError(f"POLICY_DENIED:{decision.blocking_reasons}")

    target_path = (
        Path(target_file_override).resolve()
        if target_file_override is not None
        else (Path(repo_root).resolve() / proposal.target_path).resolve()
    )
    if not target_path.is_file():
        raise CommitPreconditionError(f"TARGET_FILE_MISSING:{target_path}")

    pre_bytes = target_path.read_bytes()
    pre_sha = sha256_file(target_path)
    fmt, data = _load_structured_file(target_path)

    key = str(proposal.target_key or "")
    if not key:
        raise CommitPreconditionError("MISSING_TARGET_KEY_FOR_STRUCTURED_COMMIT")

    existed, live_val = _get_nested_key(data, key)
    if proposal.expected_current_value is not None:
        if not existed or not _values_match_cas(live_val, proposal.expected_current_value):
            raise CommitPreconditionError(
                f"CAS_CONFLICT:{key}:expected={proposal.expected_current_value!r},live={live_val!r}"
            )

    previous_snapshot = {key: live_val} if existed else {}
    absent_keys = _set_nested_key(data, key, proposal.proposed_value_or_patch)

    rollback_root = Path(rollback_dir).resolve()
    rollback_root.mkdir(parents=True, exist_ok=True)
    rollback_handle_path = rollback_root / f"{proposal.proposal_id}_rollback.json"
    commit_id = stable_id("cmt", proposal.proposal_id, pre_sha, utc_now_iso(), length=16)

    rollback_handle = {
        "schema_version": "agents.rollback_handle.v1",
        "commit_id": commit_id,
        "proposal_id": proposal.proposal_id,
        "target_path": proposal.target_path,
        "resolved_target_path": target_path.as_posix(),
        "target_key": key,
        "format": fmt,
        "previous_state_snapshot": previous_snapshot,
        "absent_keys": absent_keys,
        "pre_apply_file_sha256": pre_sha,
        "pre_apply_raw_text": pre_bytes.decode("utf-8"),
        "status": "PENDING_ROLLBACK",
        "created_at_utc": utc_now_iso(),
    }
    tmp_rb = rollback_handle_path.with_suffix(".json.tmp")
    tmp_rb.write_text(json.dumps(rollback_handle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_rb, rollback_handle_path)

    # Atomic commit with inline exception rollback.
    try:
        _atomic_write_structured(target_path, fmt, data)
    except OSError:
        tmp_restore = target_path.with_suffix(target_path.suffix + ".restore.tmp")
        tmp_restore.write_bytes(pre_bytes)
        os.replace(tmp_restore, target_path)
        raise

    post_sha = sha256_file(target_path)
    receipt = AppliedChangeReceipt(
        commit_id=commit_id,
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal.canonical_digest,
        holdout_verdict_digest=holdout_verdict.canonical_digest,
        autonomy_tier=decision.effective_tier,
        approval_receipt_id=approval_id,
        approval_origin=approval_origin,  # type: ignore[arg-type]
        target_path=proposal.target_path,
        previous_state_snapshot=previous_snapshot,
        absent_keys=absent_keys,
        applied_state={key: proposal.proposed_value_or_patch},
        pre_apply_file_sha256=pre_sha,
        post_apply_file_sha256=post_sha,
        rollback_handle_path=rollback_handle_path.as_posix(),
        canary_status="PENDING",
        merkle_seal_root="",
        stages_sealed=["LP0", "LP1", "LP2", "LP3", "LP4"],
        status="APPLIED",
    )
    ledger_store.record_applied_change(
        commit_id=receipt.commit_id,
        proposal_id=receipt.proposal_id,
        proposal_digest=receipt.proposal_digest,
        target_path=receipt.target_path,
        target_key=key,
        autonomy_tier=receipt.autonomy_tier,
        status=receipt.status,
        canary_status=receipt.canary_status,
        rollback_handle_path=receipt.rollback_handle_path,
        merkle_seal_root="",
        receipt_dict=receipt.to_dict(),
        applied_at_utc=(now_utc.isoformat().replace("+00:00", "Z") if now_utc is not None else None),
    )
    return receipt
