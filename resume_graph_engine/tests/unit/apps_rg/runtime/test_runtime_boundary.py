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
    policy = repo / ".antigravity" / "runtime-boundary.json"
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
    repo = tmp_path / "resume_graph_engine"
    repo.mkdir()
    policy = _policy(repo)
    env = {"CHROMA_PERSIST_DIR": str(tmp_path / "foreign" / "chromadb")}

    with pytest.raises(RuntimeBoundaryViolation, match="PATH_AUTHORITY_VIOLATION:CHROMA_PERSIST_DIR"):
        configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)

    assert env["CHROMA_PERSIST_DIR"] == str(tmp_path / "foreign" / "chromadb")
    assert "AGENTIC_REPO_ROOT" not in env


def test_boundary_sets_only_worktree_owned_paths_and_writes_receipt(tmp_path: Path) -> None:
    repo = tmp_path / "resume_graph_engine"
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
    repo = tmp_path / "resume_graph_engine"
    repo.mkdir()
    policy = _policy(repo)
    env: dict[str, str] = {}
    configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
    env["HF_HOME"] = str(tmp_path / "foreign" / "hf")

    with pytest.raises(RuntimeBoundaryViolation, match="PATH_AUTHORITY_VIOLATION:HF_HOME"):
        assert_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)


def test_boundary_allows_symlinked_shared_data_within_trusted_parent_checkout(tmp_path: Path) -> None:
    parent_checkout = tmp_path / "agents_checkout"
    parent_checkout.mkdir()
    (parent_checkout / ".git").mkdir()

    shared_model = parent_checkout / "artifacts" / "models" / "BAAI" / "bge-m3"
    shared_model.mkdir(parents=True)

    repo = parent_checkout / "resume_graph_engine"
    repo.mkdir()
    policy = _policy(repo)

    artifacts_dir = repo / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "models").symlink_to(parent_checkout / "artifacts" / "models")

    env: dict[str, str] = {}
    boundary = configure_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)
    verified = assert_apps_rg_runtime_boundary(repo_root=repo, environ=env, policy_path=policy)

    assert boundary.effective_paths["APPS_RG_EMBEDDING_MODEL_PATH"] == shared_model.resolve()
    assert verified.effective_paths["APPS_RG_EMBEDDING_MODEL_PATH"] == shared_model.resolve()


def test_product_entry_does_not_create_orphan_dir_when_boundary_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps_rg.runtime import product_entry

    repo = tmp_path / "resume_graph_engine"
    repo.mkdir()
    _policy(repo)

    orphan_dir = repo / "artifacts" / "apps_rg" / "runtime_proofs" / "full_resume_test_orphan"
    monkeypatch.setattr(product_entry, "find_repo_root", lambda: repo)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "foreign_hf"))

    with pytest.raises(RuntimeBoundaryViolation, match="PATH_AUTHORITY_VIOLATION:HF_HOME"):
        product_entry.run_product_whole_run_from_primitives(
            target_company="Anthropic",
            target_role="Manager of Applied AI Architecture, Partnerships",
            artifact_dir=str(orphan_dir),
        )

    assert not orphan_dir.exists()

