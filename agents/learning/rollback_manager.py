"""Post-apply canary evaluator (LP5) and lock-protected bidirectional automatic rollback engine."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from agents.learning.merkle_seal import seal_learning_stages
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file
from apps_eval.contracts.schemas import AppliedChangeReceipt, utc_now_iso

_ROLLBACK_LOCK = threading.Lock()


def _unset_nested_key(data: dict[str, Any], dotted_key: str) -> None:
    parts = dotted_key.split(".")
    cur: Any = data
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _set_nested_key_plain(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cur = data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def execute_bidirectional_rollback(
    *,
    receipt: AppliedChangeReceipt,
    ledger_store: SqliteLearningLedgerStore,
    reason: str = "post_apply_canary_regression",
    lock_days: int = 7,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Atomically restore previous state, unset absent_keys, verify exact pre-apply SHA-256, and lock key."""
    with _ROLLBACK_LOCK:
        handle_path = Path(receipt.rollback_handle_path).resolve()
        if not handle_path.is_file():
            raise FileNotFoundError(f"Rollback handle missing: {handle_path}")
        handle = json.loads(handle_path.read_text(encoding="utf-8"))
        if handle.get("status") == "EXECUTED":
            return {
                "status": "ALREADY_ROLLED_BACK",
                "proposal_id": receipt.proposal_id,
                "restored_sha256": handle.get("restored_file_sha256", ""),
            }

        target_path = Path(handle["resolved_target_path"]).resolve()
        pre_raw_text = handle.get("pre_apply_raw_text")
        if isinstance(pre_raw_text, str):
            # Exact byte restoration guarantees pre_apply_file_sha256 == restored_file_sha256 even for YAML comments.
            tmp = target_path.with_suffix(target_path.suffix + ".rb.tmp")
            tmp.write_text(pre_raw_text, encoding="utf-8")
            os.replace(tmp, target_path)
        else:
            fmt = str(handle.get("format") or "yaml")
            raw = target_path.read_text(encoding="utf-8")
            data = dict(json.loads(raw) if fmt == "json" else (yaml.safe_load(raw) or {}))
            for absent in reversed(list(handle.get("absent_keys") or [])):
                _unset_nested_key(data, str(absent))
            for k, v in (handle.get("previous_state_snapshot") or {}).items():
                _set_nested_key_plain(data, str(k), v)
            tmp = target_path.with_suffix(target_path.suffix + ".rb.tmp")
            tmp.write_text(
                (json.dumps(data, indent=2, sort_keys=True) + "\n") if fmt == "json" else yaml.safe_dump(data, sort_keys=False),
                encoding="utf-8",
            )
            os.replace(tmp, target_path)

        restored_sha = sha256_file(target_path)
        exact_match = restored_sha == str(handle.get("pre_apply_file_sha256") or "")

        handle["status"] = "EXECUTED"
        handle["executed_at_utc"] = utc_now_iso()
        handle["rollback_reason"] = reason
        handle["restored_file_sha256"] = restored_sha
        handle["exact_pre_apply_sha_match"] = exact_match
        tmp_h = handle_path.with_suffix(".json.tmp")
        tmp_h.write_text(json.dumps(handle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_h, handle_path)

        ledger_store.update_change_status(
            receipt.proposal_id,
            status="ROLLED_BACK",
            canary_status="ROLLED_BACK",
        )
        locked_until = ledger_store.set_rollback_lock(
            target_path=receipt.target_path,
            target_key=str(handle.get("target_key") or ""),
            proposal_id=receipt.proposal_id,
            lock_days=lock_days,
            reason=reason,
            now_utc=now_utc,
        )
        return {
            "status": "ROLLED_BACK",
            "proposal_id": receipt.proposal_id,
            "restored_sha256": restored_sha,
            "exact_pre_apply_sha_match": exact_match,
            "locked_until_utc": locked_until,
            "reason": reason,
        }


def evaluate_post_apply_canary_and_seal(
    *,
    receipt: AppliedChangeReceipt,
    canary_metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    ledger_store: SqliteLearningLedgerStore,
    seals_dir: Path,
    run_id: str = "flywheel-run",
    max_quality_drop: float = 0.01,
    max_latency_ms: float = 30000.0,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate LP5 post-apply canary; auto-rollback on any regression or seal LP0..LP5 Merkle chain on pass."""
    regressions: list[str] = []
    q_before = float(baseline_metrics.get("quality_score", 0.0))
    q_after = float(canary_metrics.get("quality_score", 0.0))
    if q_after < (q_before - max_quality_drop):
        regressions.append(f"CANARY_QUALITY_DROP:{q_before:.4f}->{q_after:.4f}")

    if int(canary_metrics.get("veto_defects", 0)) > 0:
        regressions.append(f"CANARY_VETO_DEFECTS:{canary_metrics['veto_defects']}")

    if float(canary_metrics.get("latency_ms", 0.0)) > max_latency_ms:
        regressions.append(f"CANARY_LATENCY_SLA_BREACH:{canary_metrics['latency_ms']}>{max_latency_ms}")

    if canary_metrics.get("pinned_regressions_passed") is False:
        regressions.append("CANARY_PINNED_REGRESSION_FAILED")

    base_events = [
        {"stage": "LP0", "proposal_id": receipt.proposal_id, "event": "cluster_detected"},
        {"stage": "LP1", "proposal_id": receipt.proposal_id, "proposal_digest": receipt.proposal_digest},
        {"stage": "LP2", "proposal_id": receipt.proposal_id, "holdout_verdict_digest": receipt.holdout_verdict_digest},
        {"stage": "LP3", "proposal_id": receipt.proposal_id, "approval_origin": receipt.approval_origin},
        {"stage": "LP4", "proposal_id": receipt.proposal_id, "commit_id": receipt.commit_id, "post_sha": receipt.post_apply_file_sha256},
    ]

    if regressions:
        rb = execute_bidirectional_rollback(
            receipt=receipt,
            ledger_store=ledger_store,
            reason=";".join(regressions),
            now_utc=now_utc,
        )
        lp5 = {"stage": "LP5", "proposal_id": receipt.proposal_id, "outcome": "ROLLED_BACK", "regressions": regressions}
        seal = seal_learning_stages(
            proposal_id=receipt.proposal_id,
            run_id=run_id,
            stage_events=[*base_events, lp5],
            terminal_outcome="ROLLED_BACK",
            output_dir=seals_dir,
        )
        ledger_store.record_stage_seal(
            seal_id=seal["seal_id"],
            proposal_id=receipt.proposal_id,
            merkle_root=seal["merkle_root"],
            stages=seal["stages_sealed"],
            terminal_outcome="ROLLED_BACK",
        )
        return {
            "status": "ROLLED_BACK",
            "canary_passed": False,
            "regressions": regressions,
            "rollback": rb,
            "merkle_seal": seal,
        }

    lp5 = {"stage": "LP5", "proposal_id": receipt.proposal_id, "outcome": "PASS", "quality_after": q_after}
    seal = seal_learning_stages(
        proposal_id=receipt.proposal_id,
        run_id=run_id,
        stage_events=[*base_events, lp5],
        terminal_outcome="PASS",
        output_dir=seals_dir,
    )
    ledger_store.update_change_status(
        receipt.proposal_id,
        status="APPLIED",
        canary_status="PASSED",
        merkle_seal_root=seal["merkle_root"],
    )
    ledger_store.record_stage_seal(
        seal_id=seal["seal_id"],
        proposal_id=receipt.proposal_id,
        merkle_root=seal["merkle_root"],
        stages=seal["stages_sealed"],
        terminal_outcome="PASS",
    )
    return {
        "status": "APPLIED_AND_SEALED",
        "canary_passed": True,
        "regressions": [],
        "merkle_seal": seal,
    }
