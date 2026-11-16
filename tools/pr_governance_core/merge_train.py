"""Wave merge-train assembly and shard-ready qualification commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from .common import (
    ROOT,
    check_merge_conflict,
    resolve_python,
    run_git,
    sanitized_git_env,
    slugify_branch,
)
from .lint_file_budgets_bridge import clamp_ratchet_if_available
from .worktree import _inspect_worktree_dirty, resolve_branch_worktree


def _resolve_root(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "repo_root", None)
    return Path(explicit).resolve() if explicit else ROOT


def _resolve_wt_path(repo_root: Path, branch: str) -> Path:
    info = resolve_branch_worktree(repo_root, branch)
    if isinstance(info, dict) and info.get("path"):
        return Path(str(info["path"])).resolve()
    return repo_root


def _changed_files_against_main(branch: str, cwd: Path) -> list[str]:
    out = run_git(["diff", "--name-only", f"main...{branch}"], check=False, cwd=cwd)
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def cmd_shard_ready(args: argparse.Namespace) -> int:
    """Qualify a worker shard branch with fast per-shard checks and emit a SHA-bound shard receipt."""
    branch = str(args.branch).strip()
    repo_root = _resolve_root(args)
    target_cwd = _resolve_wt_path(repo_root, branch)

    dirty_res = _inspect_worktree_dirty(target_cwd, ignore_review_artifacts=True)
    if dirty_res.dirty:
        print(f"❌ Shard worktree for '{branch}' has uncommitted changes ({dirty_res.summary}).")
        return 1

    head_sha = run_git(["rev-parse", branch], check=False, cwd=repo_root).strip()
    base_sha = run_git(["merge-base", "main", branch], check=False, cwd=repo_root).strip()
    if not head_sha or not base_sha:
        print(f"❌ Cannot resolve commit SHA or merge-base for shard branch '{branch}'.")
        return 1

    clean_merge, details = check_merge_conflict("main", branch, cwd=repo_root)
    if not clean_merge:
        print(f"❌ Shard branch '{branch}' conflicts with main:\n{details}")
        return 1

    changed_files = _changed_files_against_main(branch, repo_root)
    if not getattr(args, "skip_verify", False) and changed_files:
        py_bin = resolve_python(repo_root)
        cmd = [
            py_bin,
            str(target_cwd / "tools" / "verify_commit.py"),
            "--repo-root",
            str(target_cwd),
            "--shard-fast",
            "--files",
            *changed_files,
        ]
        proc = subprocess.run(cmd, cwd=target_cwd, capture_output=True, text=True, check=False, timeout=180)
        if proc.returncode != 0:
            print(f"❌ Fast shard gate failed for '{branch}':\n{proc.stdout}\n{proc.stderr}")
            return 1

    slug = slugify_branch(branch)
    payload: dict[str, Any] = {
        "pr_type": "SHARD_READY",
        "branch": branch,
        "head_sha": head_sha,
        "base_commit_sha": base_sha,
        "changed_files": changed_files,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "terminal_outcome": "PASS",
    }
    for root_dir in {repo_root, target_cwd}:
        rep_dir = root_dir / "reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        (rep_dir / f"pr_shard_{slug}_receipt.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"✅ Shard '{branch}' qualified ({head_sha[:8]}, {len(changed_files)} file(s)).")
    return 0


def _load_valid_shard_receipt(repo_root: Path, shard: str) -> tuple[dict[str, Any] | None, str]:
    slug = slugify_branch(shard)
    shard_wt = _resolve_wt_path(repo_root, shard)
    actual_sha = run_git(["rev-parse", shard], check=False, cwd=repo_root).strip()
    if not actual_sha:
        return None, f"Shard branch '{shard}' does not exist."
    for base in (repo_root, shard_wt):
        candidate = base / "reports" / f"pr_shard_{slug}_receipt.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return None, f"Corrupt shard receipt for '{shard}': {exc}"
            if data.get("terminal_outcome") != "PASS":
                return None, f"Shard receipt for '{shard}' is not PASS."
            if data.get("head_sha") != actual_sha:
                return None, f"Stale shard receipt for '{shard}' ({data.get('head_sha')} != {actual_sha})."
            return data, ""
    return None, f"Missing shard receipt reports/pr_shard_{slug}_receipt.json for '{shard}'."


def cmd_train(args: argparse.Namespace) -> int:
    """Assemble verified shard branches into a single wave merge-train branch."""
    repo_root = _resolve_root(args)
    wave_id = str(args.wave).strip()
    shards = [str(s).strip() for s in (args.shards or []) if str(s).strip()]
    if len(shards) < 1:
        print("❌ Wave merge train requires at least 1 shard branch (--shards <b1> ...).")
        return 1

    train_branch = str(getattr(args, "train_branch", None) or f"feat/wave-{wave_id}-train").strip()
    shard_files: dict[str, list[str]] = {}
    shard_heads: dict[str, str] = {}

    for shard in shards:
        receipt, err = _load_valid_shard_receipt(repo_root, shard)
        if receipt is None:
            print(f"❌ {err}")
            return 1
        files = _changed_files_against_main(shard, repo_root)
        shard_files[shard] = files
        shard_heads[shard] = str(receipt.get("head_sha", ""))

    train_wt = _resolve_wt_path(repo_root, train_branch)
    if train_wt == repo_root:
        existing_ref = run_git(["branch", "--list", train_branch], check=False, cwd=repo_root).strip()
        if existing_ref:
            run_git(["checkout", train_branch], check=True, cwd=repo_root)
            run_git(["reset", "--hard", "main"], check=True, cwd=repo_root)
        else:
            run_git(["checkout", "-b", train_branch, "main"], check=True, cwd=repo_root)
        train_cwd = repo_root
    else:
        train_cwd = train_wt
        run_git(["checkout", train_branch], check=True, cwd=train_cwd)
        run_git(["reset", "--hard", "main"], check=True, cwd=train_cwd)

    merge_env = sanitized_git_env({"GOVERNED_PR_MERGE": "1"})
    for shard in shards:
        res = subprocess.run(
            ["git", "merge", "--no-ff", shard, "-m", f"chore(train): merge shard {shard} into {train_branch}"],
            cwd=train_cwd,
            env=merge_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if res.returncode != 0:
            subprocess.run(["git", "merge", "--abort"], cwd=train_cwd, env=merge_env, check=False, timeout=15)
            print(f"❌ Failed merging shard '{shard}' into '{train_branch}':\n{res.stdout}\n{res.stderr}")
            return 1

    clamped = clamp_ratchet_if_available(train_cwd)
    if clamped:
        run_git(["add", "config/governance/file_budgets_ratchet.json"], check=True, cwd=train_cwd)
        subprocess.run(
            ["git", "commit", "--no-verify", "-m", f"chore(ratchet): clamp {len(clamped)} ceiling(s) on {train_branch}"],
            cwd=train_cwd,
            env=merge_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    train_head = run_git(["rev-parse", "HEAD"], check=True, cwd=train_cwd).strip()
    slug = slugify_branch(train_branch)
    manifest = {
        "train_branch": train_branch,
        "wave": wave_id,
        "head_sha": train_head,
        "shards": [{"branch": s, "head_sha": shard_heads[s], "changed_files": shard_files[s]} for s in shards],
        "clamped_ratchets": clamped,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "terminal_outcome": "PASS",
    }
    rep_dir = repo_root / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    (rep_dir / f"pr_train_{slug}_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"✅ Wave merge train '{train_branch}' assembled ({len(shards)} shards, head {train_head[:8]}).")
    return 0
