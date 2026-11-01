#!/usr/bin/env python3
"""Read-only certification of a governed local-main merge commit."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_governance_core.common import sanitized_git_env, slugify_branch


def _git(repo_root: Path, *args: str) -> str:
    try:
        command = ["git", *args]
        proc = subprocess.run(command, timeout=10, cwd=repo_root, env=sanitized_git_env(), capture_output=True, text=True)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"git {' '.join(args)} timed out") from exc
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def verify_latest_merge(repo_root: Path, ref: str = "HEAD") -> tuple[bool, str]:
    """Prove the merge tree equals the reviewed branch plus its sealed receipt."""
    try:
        commit, *parents = _git(repo_root, "rev-list", "--parents", "-n", "1", ref).split()
        if len(parents) != 2:
            return False, "HEAD is not a two-parent merge commit."
        message = _git(repo_root, "log", "-1", "--format=%s", ref)
        match = re.fullmatch(r"Merge branch '([^']+)' into main \(.+\)", message)
        if not match:
            return False, "Merge commit message does not follow the governed format."
        branch = match.group(1)
        slug = slugify_branch(branch)
        receipt_path = f"reports/pr_merge_{slug}_receipt.json"
        expected = {
            "pr_type": "LOCAL_FEATURE_BRANCH_MERGE",
            "branch": branch,
            "head_sha": parents[1],
            "branch_head_sha": parents[1],
            "main_base_sha": parents[0],
            "merge_message": message,
            "target": "main",
            "terminal_outcome": "PASS",
        }
        changed = _git(repo_root, "diff", "--name-only", parents[1], commit).splitlines()
        if changed == [receipt_path]:
            receipt = json.loads(_git(repo_root, "show", f"{commit}:{receipt_path}"))
            for key, value in expected.items():
                if receipt.get(key) != value:
                    return False, f"Merge receipt field {key} does not match the commit."
            return True, f"Merge {commit[:10]} certified against reviewed branch {parents[1][:10]}."
        if changed == []:
            disk_receipt = repo_root / receipt_path
            if disk_receipt.is_file():
                receipt = json.loads(disk_receipt.read_text(encoding="utf-8"))
                for key, value in expected.items():
                    if receipt.get(key) != value:
                        return False, f"Merge receipt field {key} does not match the commit."
                return True, f"Merge {commit[:10]} certified against reviewed branch {parents[1][:10]} (out-of-tree receipt)."
            body = _git(repo_root, "log", "-1", "--format=%B", ref)
            if (
                "PR-Merge-Target: main" in body
                and f"PR-Branch-Head: {parents[1]}" in body
                and f"PR-Main-Base: {parents[0]}" in body
                and "PR-Terminal-Outcome: PASS" in body
            ):
                return True, f"Merge {commit[:10]} certified against reviewed branch {parents[1][:10]} (commit trailers)."
        return False, "Merged tree differs from the reviewed branch beyond its receipt."
    except (ValueError, json.JSONDecodeError) as exc:
        return False, str(exc)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT, help="Repository root path")
    parser.add_argument("--ref", default="HEAD", help="Merge commit ref to verify")
    args = parser.parse_args(argv)

    passed, detail = verify_latest_merge(args.repo_root.resolve(), ref=args.ref)
    print(f"{'PASS' if passed else 'FAIL'}: {detail}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
