"""Unit tests for Wave 4 Rule 6 technical artifact exemption in handle_pre_file_write."""

from __future__ import annotations

from pathlib import Path

from tools.hook_dispatch import handle_pre_file_write


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_pre_file_write_allows_technical_precision_in_rule6_engineering_artifacts() -> None:
    for path in (
        "/Users/test/.gemini/antigravity/brain/conv-123/implementation_plan.md",
        "/Users/test/.gemini/antigravity/brain/conv-123/learning_proposal.md",
        "/Users/test/.gemini/antigravity/brain/conv-123/walkthrough.md",
        "/Users/test/.gemini/antigravity/brain/conv-123/cross_repo_assessment.md",
    ):
        payload = {
            "toolCall": {
                "name": "write_file",
                "args": {
                    "Path": path,
                    "Content": (
                        "Update `schema_ddl.py` and `graph_skill_hybrid_retrieval.py` "
                        "to add SQLite FTS5 BM25 ranking and RRF fusion."
                    ),
                    "ArtifactMetadata": {
                        "Summary": "Technical wave implementation plan with pytest and SQLite FTS5",
                        "UserFacing": True,
                        "RequestFeedback": False,
                    },
                },
            }
        }
        rc = handle_pre_file_write(payload, _repo_root())
        assert rc == 0


def test_pre_file_write_still_guards_non_engineering_user_facing_artifacts() -> None:
    payload = {
        "toolCall": {
            "name": "write_file",
            "args": {
                "Path": "/Users/test/.gemini/antigravity/brain/conv-123/customer_note.md",
                "Content": "Run `pytest` on `schema_ddl.py` with SQLite WAL and BM25.",
                "ArtifactMetadata": {
                    "Summary": "Customer note",
                    "UserFacing": True,
                    "RequestFeedback": False,
                },
            },
        }
    }
    rc = handle_pre_file_write(payload, _repo_root())
    assert rc == 1
