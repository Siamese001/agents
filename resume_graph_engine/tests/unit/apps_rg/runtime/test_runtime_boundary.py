"""Focused path-authority regression coverage for the public Apps RG runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.runtime_boundary import (
    RuntimeBoundaryViolation,
    assert_apps_rg_runtime_boundary,
    configure_apps_rg_runtime_boundary,
    write_apps_rg_runtime_boundary_receipt,
)


def _policy(repo: Path) -> Path:
    policy = repo / ".codex" / "runtime-boundary.json"
    policy.parent.mkdir()
    policy.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "worktreeRoot": "..",
                "environmentPaths": {
                    "AGENTIC_REPO_ROOT": ".",
                    "CHROMA_PERSIST_DIR": "data/cache/chromadb",
                    "APPS_RG_EMBEDDING_MODEL_PATH": "artifacts/models/BAAI/bge-m3",
                    "HF_HOME": ".runtime/huggingface",
                },
            }
        ),
        encoding="utf-8",
    )
    return policy


def test_boundary_rejects_foreign_cache_before_mutating_environment(tmp_path: Path) -> None:
    repo = tmp_path / "apps_rg_v2"
    repo.mkdir()
    policy = _policy(repo)
    env = {"CHROMA_PERSIST_DIR": str(tmp_path / "foreign" / "chromadb")}

    with pytest.raises(RuntimeBoundaryViolation, match="PATH_AUTHORITY_VIOLATION:CHROMA_PERSIST_DIR"):
        configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)

    assert env["CHROMA_PERSIST_DIR"] == str(tmp_path / "foreign" / "chromadb")
    assert "AGENTIC_REPO_ROOT" not in env


def test_boundary_sets_only_worktree_owned_paths_and_writes_receipt(tmp_path: Path) -> None:
    repo = tmp_path / "apps_rg_v2"
    repo.mkdir()
    policy = _policy(repo)
    env: dict[str, str] = {}

    boundary = configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
    verified = assert_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
    receipt = write_apps_rg_runtime_boundary_receipt(repo / "artifacts" / "apps_rg" / "runtime_proofs" / "r1", verified)

    assert boundary.repo_root == repo.resolve()
    assert Path(env["CHROMA_PERSIST_DIR"]).is_relative_to(repo)
    assert Path(env["APPS_RG_EMBEDDING_MODEL_PATH"]).is_relative_to(repo)
    assert env["HF_HUB_OFFLINE"] == "1"
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "PASS"


def test_boundary_detects_later_path_mutation(tmp_path: Path) -> None:
    repo = tmp_path / "apps_rg_v2"
    repo.mkdir()
    policy = _policy(repo)
    env: dict[str, str] = {}
    configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
    env["HF_HOME"] = str(tmp_path / "foreign" / "hf")

    with pytest.raises(RuntimeBoundaryViolation, match="PATH_AUTHORITY_VIOLATION:HF_HOME"):
        assert_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
