"""Unit and counterfactual tests for `INV-REPO-SCOPED-CONVERSATION-ISOLATION` across `agents` and `core-governance`."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from tools.hook_dispatch import handle_post_invocation, handle_pre_run_command

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_MCP = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
if str(CORE_MCP) not in sys.path:
    sys.path.insert(0, str(CORE_MCP))


def _make_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True, timeout=15)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True, timeout=15)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True, timeout=15)
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True, timeout=15)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "chore: init"], check=True, capture_output=True, timeout=15)
    return root


def test_pre_tool_blocks_unprompted_external_repo_and_check_all_repos(tmp_path: Path, capsys) -> None:
    git_parent = tmp_path / "Git"
    active = _make_git_repo(git_parent / "agents")
    sibling = _make_git_repo(git_parent / "external-alpha-repo")

    rc_block = handle_pre_run_command(
        {
            "cwd": str(active),
            "steps": [{"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "What is remaining?"}],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": f"git -C {sibling} worktree list"},
            },
        },
        repo_root=active,
    )
    out_block = json.loads(capsys.readouterr().out.strip())
    assert rc_block == 1
    assert out_block["decision"] == "deny"
    assert "INV-REPO-SCOPED-CONVERSATION-ISOLATION" in out_block["reason"]

    rc_all = handle_pre_run_command(
        {
            "cwd": str(active),
            "steps": [{"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Run parity check"}],
            "toolCall": {
                "name": "call_mcp_tool",
                "args": {
                    "ServerName": "core-governance_labeling_studio",
                    "ToolName": "audit_repo_zero_drift_parity",
                    "Arguments": {"check_all_repos": True},
                },
            },
        },
        repo_root=active,
    )
    out_all = json.loads(capsys.readouterr().out.strip())
    assert rc_all == 1
    assert out_all["decision"] == "deny"

    # Explicit user mention of the external repo authorizes read-only inspection
    rc_allow = handle_pre_run_command(
        {
            "cwd": str(active),
            "steps": [
                {
                    "type": "USER_INPUT",
                    "source": "USER_EXPLICIT",
                    "content": "Compare config against external-alpha-repo",
                }
            ],
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": f"ls {sibling}"},
            },
        },
        repo_root=active,
    )
    out_allow = json.loads(capsys.readouterr().out.strip())
    assert rc_allow == 0
    assert out_allow["decision"] == "allow"


def test_post_invocation_blocks_external_repo_and_unrelated_sibling_worktree_mentions(
    tmp_path: Path, capsys
) -> None:
    git_parent = tmp_path / "Git"
    active = _make_git_repo(git_parent / "agents")
    _make_git_repo(git_parent / "external-beta-repo")

    wt_owned = active / ".worktrees" / "feat_owned_task"
    wt_foreign = active / ".worktrees" / "feat_parallel_unrelated"
    subprocess.run(
        ["git", "-C", str(active), "worktree", "add", "-b", "feat/owned-task", str(wt_owned), "main"],
        check=True,
        capture_output=True,
        timeout=15,
    )
    subprocess.run(
        ["git", "-C", str(active), "worktree", "add", "-b", "feat/parallel-unrelated", str(wt_foreign), "main"],
        check=True,
        capture_output=True,
        timeout=15,
    )

    # 1. Mentioning unrelated parallel worktree branch -> intercepted
    handle_post_invocation(
        {
            "cwd": str(active),
            "steps": [
                {"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "What is remaining?"},
                {
                    "type": "TOOL_CALL",
                    "toolCalls": [
                        {
                            "name": "run_command",
                            "args": {"CommandLine": "python tools/pr_governance.py start feat/owned-task"},
                        }
                    ],
                },
                {
                    "type": "ASSISTANT",
                    "source": "MODEL",
                    "content": "Completed feat/owned-task; sibling branch feat/parallel-unrelated is still open.",
                },
            ],
        },
        repo_root=active,
    )
    res_leak = json.loads(capsys.readouterr().out.strip())
    assert res_leak.get("terminationBehavior") == "force_continue"
    assert "feat/parallel-unrelated" in res_leak["injectSteps"][0]["ephemeralMessage"]

    # 2. Mentioning external sibling repository -> intercepted
    handle_post_invocation(
        {
            "cwd": str(active),
            "steps": [
                {"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Summarize status"},
                {
                    "type": "ASSISTANT",
                    "source": "MODEL",
                    "content": "All checks passed here; external-beta-repo has one pending update.",
                },
            ],
        },
        repo_root=active,
    )
    res_ext = json.loads(capsys.readouterr().out.strip())
    assert res_ext.get("terminationBehavior") == "force_continue"
    assert "external-beta-repo" in res_ext["injectSteps"][0]["ephemeralMessage"]

    # 3. Discussing ONLY current turn's owned branch and main -> allowed cleanly
    handle_post_invocation(
        {
            "cwd": str(active),
            "steps": [
                {"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "What is remaining?"},
                {
                    "type": "TOOL_CALL",
                    "toolCalls": [
                        {
                            "name": "run_command",
                            "args": {"CommandLine": "python tools/pr_governance.py start feat/owned-task"},
                        }
                    ],
                },
                {
                    "type": "ASSISTANT",
                    "source": "MODEL",
                    "content": "Zero code items remain on main after completing feat/owned-task.",
                },
            ],
        },
        repo_root=active,
    )
    res_clean = json.loads(capsys.readouterr().out.strip())
    assert res_clean == {"injectSteps": []}

    # 4. Explicit user request to list worktrees -> allowed cleanly
    handle_post_invocation(
        {
            "cwd": str(active),
            "steps": [
                {"type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "Please list all active worktrees"},
                {
                    "type": "ASSISTANT",
                    "source": "MODEL",
                    "content": "Active worktrees: feat/owned-task and feat/parallel-unrelated.",
                },
            ],
        },
        repo_root=active,
    )
    res_explicit = json.loads(capsys.readouterr().out.strip())
    assert res_explicit == {"injectSteps": []}


def test_mcp_zero_drift_defaults_to_single_active_repo_and_worktree_root_symmetry(tmp_path: Path) -> None:
    import labeling_studio_server as lss
    import policy_ssot_parity_engine as pspe

    resp = lss.handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "audit_repo_zero_drift_parity",
                "arguments": {"repo_root": str(REPO_ROOT), "check_all_repos": True},
            },
        },
        data_dir=tmp_path / "studio_data",
    )
    assert resp is not None
    repos = resp["result"]["structuredContent"]["repositories"]
    assert len(repos) == 1
    assert Path(repos[0]["repo_root"]).name == "agents"

    root_hitl = pspe.check_centralized_hitl_question_store_parity(REPO_ROOT)
    assert root_hitl == []
