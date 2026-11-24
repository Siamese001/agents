"""Ephemeral isolated git worktree promoter for git-tracked Tier A and approved Tier B flywheel commits.

Guarantees that primary `repo_root` (`main`) never accumulates dirty uncommitted tracked diffs:
1. Detects whether `proposal.target_path` is git-tracked via `git -C <repo_root> ls-files --error-unmatch`.
2. When tracked (and no sandbox `target_file_override` is active):
   - Spawns an ephemeral worktree `.worktrees/flywheel_apply_<short_id>` on branch `chore/flywheel-apply-<short_id>`.
   - Applies the CAS update inside the worktree via `apply_proposal_atomically(..., target_file_override=wt_target)`.
   - Evaluates the `LP5` post-apply canary inside the worktree.
   - If canary fails: rolls back, records the 7-day anti-oscillation lock in `learning_ledger.sqlite`,
     and removes the ephemeral worktree + branch in `finally:`, leaving `main` 100% untouched.
   - If canary passes: commits only `proposal.target_path` on the worktree branch, promotes onto `main`
     under `GOVERNED_PR_MERGE=1`, updates the rollback handle `resolved_target_path` to `repo_root / target_path`
     (with `git_promoted: True` so subsequent rollback commits via worktree cleanly), and prunes the ephemeral
     worktree + branch in `finally:`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from agents.learning.commit_engine import apply_proposal_atomically
from agents.learning.rollback_manager import evaluate_post_apply_canary_and_seal
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import sha256_file, stable_id
from apps_eval.contracts.schemas import (
    AppliedChangeReceipt,
    HoldoutReplayVerdict,
    ImprovementProposal,
    utc_now_iso,
)


def is_git_tracked_target(repo_root: Path, rel_path: str) -> bool:
    """Return True if `rel_path` is tracked by git in `repo_root` and `repo_root` has a valid HEAD commit."""
    root = Path(repo_root).resolve()
    if not (root / ".git").exists():
        return False
    try:
        head_proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=5,
        )
        if head_proc.returncode != 0:
            return False
        ls_proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", str(rel_path)],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=5,
        )
        return ls_proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _cleanup_ephemeral_worktree(repo_root: Path, wt_dir: Path, branch_name: str) -> None:
    """Force-remove ephemeral worktree directory, prune git worktrees, and delete ephemeral branch."""
    root = Path(repo_root).resolve()
    try:
        subprocess.run(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(wt_dir)],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    if wt_dir.exists():
        shutil.rmtree(wt_dir, ignore_errors=True)
    try:
        subprocess.run(
            ["git", "-C", str(root), "worktree", "prune"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(root), "branch", "-D", branch_name],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def promote_single_file_worktree_branch(
    *,
    repo_root: Path,
    wt_dir: Path,
    branch_name: str,
    rel_target_path: str,
    commit_message: str,
) -> str:
    """Commit `rel_target_path` inside `wt_dir` and fast-forward / governed-merge onto `repo_root` current branch."""
    from infrastructure.config.env_loader import temporary_env_override

    root = Path(repo_root).resolve()
    git_id_flags = [
        "-c",
        "user.name=Agents Flywheel",
        "-c",
        "user.email=flywheel@agents.local",
    ]
    with temporary_env_override({"GOVERNED_PR_MERGE": "1"}):
        add_proc = subprocess.run(
            ["git", "-C", str(wt_dir), *git_id_flags, "add", "--", rel_target_path],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=15,
        )
        if add_proc.returncode != 0:
            raise RuntimeError(f"Failed staging {rel_target_path} in ephemeral worktree: {add_proc.stderr}")

        commit_proc = subprocess.run(
            ["git", "-C", str(wt_dir), *git_id_flags, "commit", "--no-verify", "-m", commit_message],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=20,
        )
        if commit_proc.returncode != 0:
            raise RuntimeError(f"Failed committing {rel_target_path} in ephemeral worktree: {commit_proc.stderr}")

        merge_proc = subprocess.run(
            ["git", "-C", str(root), *git_id_flags, "merge", "--ff-only", branch_name],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=20,
        )
        if merge_proc.returncode != 0:
            merge_proc = subprocess.run(
                ["git", "-C", str(root), *git_id_flags, "merge", "--no-edit", branch_name],
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=20,
            )
            if merge_proc.returncode != 0:
                raise RuntimeError(f"Failed promoting ephemeral worktree branch {branch_name}: {merge_proc.stderr}")

    sha_proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=5,
    )
    return sha_proc.stdout.strip()


def apply_and_verify_with_worktree_isolation(
    *,
    proposal: ImprovementProposal,
    holdout_verdict: HoldoutReplayVerdict,
    repo_root: Path,
    ledger_store: SqliteLearningLedgerStore,
    rollback_dir: Path,
    seals_dir: Path,
    canary_metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    target_file_override: Path | None = None,
    approval_receipt: Mapping[str, Any] | None = None,
    confidence_margin: float = 0.30,
    run_id: str = "flywheel-run",
    now_utc: datetime | None = None,
) -> tuple[AppliedChangeReceipt, dict[str, Any]]:
    """Apply proposal and evaluate LP5 canary, using an ephemeral worktree when target is git-tracked."""
    root = Path(repo_root).resolve()
    use_worktree = target_file_override is None and is_git_tracked_target(root, proposal.target_path)

    if not use_worktree:
        applied = apply_proposal_atomically(
            proposal=proposal,
            holdout_verdict=holdout_verdict,
            repo_root=root,
            ledger_store=ledger_store,
            rollback_dir=rollback_dir,
            target_file_override=target_file_override,
            approval_receipt=approval_receipt,
            confidence_margin=confidence_margin,
            now_utc=now_utc,
        )
        canary = evaluate_post_apply_canary_and_seal(
            receipt=applied,
            canary_metrics=canary_metrics,
            baseline_metrics=baseline_metrics,
            ledger_store=ledger_store,
            seals_dir=seals_dir,
            run_id=run_id,
            now_utc=now_utc,
        )
        return applied, canary

    short_id = stable_id("wt", proposal.proposal_id, utc_now_iso(), length=10)
    wt_dir = root / ".worktrees" / f"flywheel_{short_id}"
    branch_name = f"chore/flywheel-apply-{short_id}"
    wt_dir.parent.mkdir(parents=True, exist_ok=True)

    add_wt = subprocess.run(
        ["git", "-C", str(root), "worktree", "add", "-b", branch_name, str(wt_dir), "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=20,
    )
    if add_wt.returncode != 0:
        raise RuntimeError(f"Failed creating ephemeral flywheel worktree at {wt_dir}: {add_wt.stderr}")

    try:
        wt_target = (wt_dir / proposal.target_path).resolve()
        applied = apply_proposal_atomically(
            proposal=proposal,
            holdout_verdict=holdout_verdict,
            repo_root=root,
            ledger_store=ledger_store,
            rollback_dir=rollback_dir,
            target_file_override=wt_target,
            approval_receipt=approval_receipt,
            confidence_margin=confidence_margin,
            now_utc=now_utc,
        )
        canary = evaluate_post_apply_canary_and_seal(
            receipt=applied,
            canary_metrics=canary_metrics,
            baseline_metrics=baseline_metrics,
            ledger_store=ledger_store,
            seals_dir=seals_dir,
            run_id=run_id,
            now_utc=now_utc,
        )
        if canary["canary_passed"]:
            commit_msg = (
                f"chore(flywheel): apply {proposal.autonomy_tier} {proposal.proposal_id} "
                f"on {proposal.target_path}"
            )
            promoted_sha = promote_single_file_worktree_branch(
                repo_root=root,
                wt_dir=wt_dir,
                branch_name=branch_name,
                rel_target_path=proposal.target_path,
                commit_message=commit_msg,
            )
            # Re-point rollback handle to the primary repo target_path and mark git_promoted=True
            handle_path = Path(applied.rollback_handle_path).resolve()
            if handle_path.is_file():
                handle = json.loads(handle_path.read_text(encoding="utf-8"))
                handle["resolved_target_path"] = (root / proposal.target_path).resolve().as_posix()
                handle["git_promoted"] = True
                handle["promoted_git_sha"] = promoted_sha
                handle["repo_root"] = root.as_posix()
                tmp_h = handle_path.with_suffix(".json.tmp")
                tmp_h.write_text(json.dumps(handle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                os.replace(tmp_h, handle_path)
        return applied, canary
    finally:
        _cleanup_ephemeral_worktree(root, wt_dir, branch_name)


def commit_rollback_in_ephemeral_worktree(
    *,
    repo_root: Path,
    rel_target_path: str,
    restored_text: str,
    proposal_id: str,
) -> str:
    """Restore `rel_target_path` inside an ephemeral worktree and promote the rollback commit cleanly."""
    root = Path(repo_root).resolve()
    short_id = stable_id("wtrb", proposal_id, utc_now_iso(), length=10)
    wt_dir = root / ".worktrees" / f"flywheel_rb_{short_id}"
    branch_name = f"chore/flywheel-rollback-{short_id}"
    wt_dir.parent.mkdir(parents=True, exist_ok=True)

    add_wt = subprocess.run(
        ["git", "-C", str(root), "worktree", "add", "-b", branch_name, str(wt_dir), "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=20,
    )
    if add_wt.returncode != 0:
        raise RuntimeError(f"Failed creating ephemeral rollback worktree: {add_wt.stderr}")
    try:
        wt_target = (wt_dir / rel_target_path).resolve()
        tmp = wt_target.with_suffix(wt_target.suffix + ".rb.tmp")
        tmp.write_text(restored_text, encoding="utf-8")
        os.replace(tmp, wt_target)
        return promote_single_file_worktree_branch(
            repo_root=root,
            wt_dir=wt_dir,
            branch_name=branch_name,
            rel_target_path=rel_target_path,
            commit_message=f"revert(flywheel): rollback {proposal_id} on {rel_target_path}",
        )
    finally:
        _cleanup_ephemeral_worktree(root, wt_dir, branch_name)
