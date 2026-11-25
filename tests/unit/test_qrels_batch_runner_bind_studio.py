"""Unit tests for multi-project Studio session binding in ops_scripts/qrels_batch_runner.py."""

from __future__ import annotations

import json
from pathlib import Path

from ops_scripts.qrels_batch_runner import cmd_bind_studio


def test_cmd_bind_studio_preserves_other_projects_in_sessions_json(tmp_path: Path) -> None:
    qdir = tmp_path / "data" / "qrels"
    qdir.mkdir(parents=True, exist_ok=True)
    queue_file = qdir / "hitl_qrels_queue.v1.json"
    queue_file.write_text(
        json.dumps(
            [
                {
                    "qrel_id": "anchor-01",
                    "batch_index": 1,
                    "query_id": "q_01",
                    "query_text": "Test question?",
                    "candidates": [{"slot": s, "record_id": f"rec_{s}", "core_statement": f"stmt {s}"} for s in ("A", "B", "C", "D")],
                }
            ]
        ),
        encoding="utf-8",
    )

    plugin_data = tmp_path / "plugin_data"
    plugin_data.mkdir(parents=True, exist_ok=True)
    existing_sessions = {
        "schema_version": "2.0.0",
        "last_active_project_id": "die",
        "projects": {
            "die": {
                "project_id": "die",
                "mode": "qrels_4up",
                "repo_label": "DIE",
                "queue_path": "/tmp/die_queue.json",
                "ledger_path": "/tmp/die_ledger.json",
                "batch_index": 2,
            }
        },
    }
    (plugin_data / "sessions.json").write_text(json.dumps(existing_sessions, indent=2), encoding="utf-8")

    res = cmd_bind_studio(tmp_path, batch_index=1, plugin_data_dirs=[plugin_data])
    assert res["status"] == "PASS"
    assert res["project_id"] == "agents"

    updated_sessions = json.loads((plugin_data / "sessions.json").read_text(encoding="utf-8"))
    assert updated_sessions["last_active_project_id"] == "agents"
    assert updated_sessions["projects"]["die"]["batch_index"] == 2
    assert updated_sessions["projects"]["agents"]["queue_path"] == str(queue_file.resolve())

    active_cfg = json.loads((plugin_data / "active_session.json").read_text(encoding="utf-8"))
    assert active_cfg["project_id"] == "agents"
    assert active_cfg["batch_index"] == 1
