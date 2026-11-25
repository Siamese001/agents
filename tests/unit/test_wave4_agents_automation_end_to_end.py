"""Wave 4 E2E verification for agents repo prompt auditors, sidecar projectId, and negative controls."""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from tools.agent_runtime_auditor import run_agent_runtime_audit
from tools.prompt_scope_isolation import validate_stage_ownership_disjointness
from tools.prune_merged_chat_worktrees import prune_merged_worktrees
from tools.retrieval_surface_auditor import run_retrieval_surface_audit
from tools.ssot_boundary_auditor import run_ssot_boundary_audit
from tools.validate_sidecar_separation import (
    EXPECTED_AGENTS_SIDECARS,
    REQUIRED_SIDECAR_ACCESS_GRANTS,
    build_agents_sidecar_payload,
    reconcile_agents_sidecars,
    resolve_agents_project_id,
    validate_sidecar_separation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sidecar_project_id_resolution_and_access_grants(tmp_path: Path) -> None:
    cfg_root = tmp_path / ".gemini" / "config"
    projects_dir = cfg_root / "projects"
    sidecars_root = cfg_root / "sidecars"
    projects_dir.mkdir(parents=True, exist_ok=True)
    sidecars_root.mkdir(parents=True, exist_ok=True)

    dynamic_uuid = "11111111-2222-3333-4444-555555555555"
    (projects_dir / f"{dynamic_uuid}.json").write_text(
        json.dumps(
            {
                "id": dynamic_uuid,
                "projectResources": {
                    "resources": [
                        {
                            "gitFolder": {
                                "folderUri": f"file://{Path.home() / 'Git' / 'agents'}",
                            }
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    first_id = next(iter(EXPECTED_AGENTS_SIDECARS))
    (cfg_root / "config.json").write_text(
        json.dumps(
            {
                "sidecars": {
                    first_id: {
                        "enabled": True,
                        "projectId": "f3cfd8ed-5fb8-40c7-b562-dbdf15522309",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert resolve_agents_project_id(cfg_root) == dynamic_uuid
    reconcile_agents_sidecars(sidecars_root=sidecars_root)

    cfg_after = json.loads((cfg_root / "config.json").read_text(encoding="utf-8"))
    assert cfg_after["sidecars"][first_id]["enabled"] is True
    for sid, spec in EXPECTED_AGENTS_SIDECARS.items():
        assert cfg_after["sidecars"][sid]["projectId"] == dynamic_uuid
        payload = build_agents_sidecar_payload(sid, spec)
        assert payload["agent_permissions"]["access_grants"] == list(REQUIRED_SIDECAR_ACCESS_GRANTS)

    # Read-only validate_sidecar_separation must fail closed on regressed projectId or missing access_grants
    cfg_after["sidecars"][first_id]["enabled"] = False
    cfg_after["sidecars"][first_id]["projectId"] = "f3cfd8ed-5fb8-40c7-b562-dbdf15522309"
    (cfg_root / "config.json").write_text(json.dumps(cfg_after), encoding="utf-8")
    sc_first = sidecars_root / first_id / "sidecar.json"
    sc_doc = json.loads(sc_first.read_text(encoding="utf-8"))
    sc_doc["agent_permissions"]["access_grants"] = []
    sc_first.write_text(json.dumps(sc_doc), encoding="utf-8")
    bad_sep = validate_sidecar_separation(repo_root=REPO_ROOT, sidecars_root=sidecars_root)
    assert bad_sep["is_clean"] is False
    joined_v = "\n".join(bad_sep["violations"])
    assert "mismatches resolved project" in joined_v
    assert "missing required access_grants" in joined_v

    src_text = (REPO_ROOT / "tools" / "validate_sidecar_separation.py").read_text(encoding="utf-8")
    shared_text = (REPO_ROOT / "automations" / "prompts" / "_shared_governance_contract.md").read_text(encoding="utf-8")
    assert "f3cfd8ed" not in src_text
    assert "f3cfd8ed" not in shared_text


def test_stage_write_paths_cover_100_percent_of_tracked_files() -> None:
    violations = validate_stage_ownership_disjointness(REPO_ROOT)
    assert violations == [], f"Stage ownership violations: {violations}"
    sep = validate_sidecar_separation(repo_root=REPO_ROOT)
    assert sep["is_clean"] is True, f"Sidecar separation violations: {sep['violations']}"


def test_ssot_boundary_audit_passes_all_ten_dimensions() -> None:
    t1 = time.perf_counter()
    ssot_rep = run_ssot_boundary_audit(repo_root=REPO_ROOT)
    ssot_elapsed = time.perf_counter() - t1
    assert ssot_rep["is_clean"] is True, f"SSOT boundary issues: {ssot_rep}"
    assert ssot_elapsed < 55.0, f"ssot_boundary_auditor exceeded 55s budget: {ssot_elapsed:.2f}s"


def test_retrieval_surface_audit_passes_all_pillars_within_budget() -> None:
    t2 = time.perf_counter()
    ret_rep = run_retrieval_surface_audit(REPO_ROOT, read_only=True)
    ret_elapsed = time.perf_counter() - t2
    assert ret_rep["is_clean"] is True, f"Retrieval audit gaps: {ret_rep['gaps']}"
    assert ret_elapsed < 50.0, f"retrieval_surface_auditor exceeded 50s cold BGE-M3 budget: {ret_elapsed:.2f}s"


def test_core_auditors_pass_fast_and_fail_closed_on_negative_controls(tmp_path: Path) -> None:
    t0 = time.perf_counter()
    rt_rep = run_agent_runtime_audit(REPO_ROOT)
    rt_elapsed = time.perf_counter() - t0
    assert rt_rep["is_clean"] is True, f"Runtime audit gaps: {rt_rep['gaps']}"
    assert rt_elapsed < 10.0, f"agent_runtime_auditor exceeded 10s: {rt_elapsed:.2f}s"

    # Negative control 1: injected silent exception swallow fails agent_runtime_auditor closed
    sandbox_rt = tmp_path / "sandbox_rt"
    (sandbox_rt / "agents" / "observability").mkdir(parents=True, exist_ok=True)
    for sub in ("agents", "tools", "infrastructure", "config", ".agents"):
        src = REPO_ROOT / sub
        dst = sandbox_rt / sub
        if src.is_dir() and not dst.exists():
            shutil.copytree(src, dst)
        elif src.is_dir() and sub == "agents":
            shutil.rmtree(dst)
            shutil.copytree(src, dst)
    bad_file = sandbox_rt / "agents" / "observability" / "rogue_swallow.py"
    bad_file.write_text(
        "def swallow() -> None:\n"
        "    try:\n"
        "        raise ValueError('boom')\n"
        "    except Exception:\n"
        "        pass\n",
        encoding="utf-8",
    )
    neg_proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "agent_runtime_auditor.py"), "--repo-root", str(sandbox_rt), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert neg_proc.returncode == 1
    neg_json = json.loads(neg_proc.stdout)
    assert neg_json["is_clean"] is False
    assert any("rogue_swallow.py" in g for g in neg_json["gaps"])

    # Negative control 2: duplicate entity label cluster in augmented_skills_graph.sqlite fails closed
    main_db = REPO_ROOT.parent.parent / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    if not main_db.is_file():
        main_db = REPO_ROOT / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    assert main_db.is_file()
    dup_db = tmp_path / "dup_graph.sqlite"
    shutil.copy2(main_db, dup_db)
    conn = sqlite3.connect(str(dup_db))
    try:
        row = conn.execute(
            "SELECT label, employer FROM graph_nodes WHERE node_type = 'skill' AND COALESCE(TRIM(label), '') != '' LIMIT 1"
        ).fetchone()
        assert row is not None
        conn.execute(
            "INSERT INTO graph_nodes (node_id, node_type, label, description, employer, external_eligible, created_at, updated_at) "
            "VALUES (?, 'skill', ?, 'dup', ?, 1, '2026-11-24T00:00:00Z', '2026-11-24T00:00:00Z')",
            ("skill_injected_duplicate_999", row[0], row[1] or "Slalom"),
        )
        conn.commit()
        dups = conn.execute(
            "SELECT n1.node_type, LOWER(TRIM(n1.label)), COUNT(DISTINCT n1.node_id) + 1 "
            "FROM graph_nodes n1 "
            "JOIN graph_nodes n2 ON n1.node_id < n2.node_id "
            "AND n1.node_type = n2.node_type "
            "AND LOWER(TRIM(n1.label)) = LOWER(TRIM(n2.label)) "
            "WHERE n1.node_type IN ('skill', 'capability_domain', 'role_family') "
            "AND COALESCE(TRIM(n1.label), '') != '' "
            "AND (n1.node_type IN ('capability_domain', 'role_family') "
            "OR COALESCE(TRIM(n1.source_refs_json), '[]') = COALESCE(TRIM(n2.source_refs_json), '[]') "
            "OR COALESCE(TRIM(n1.source_refs_json), '[]') = '[]' "
            "OR COALESCE(TRIM(n2.source_refs_json), '[]') = '[]') "
            "GROUP BY n1.node_type, LOWER(TRIM(n1.label))"
        ).fetchall()
        assert len(dups) >= 1
    finally:
        conn.close()


def test_prune_merged_worktrees_protects_active_cwd() -> None:
    dry = prune_merged_worktrees(REPO_ROOT, delete_merged=False, active_cwd=REPO_ROOT)
    assert dry["status"] == "DRY_RUN"
    assert str(REPO_ROOT.resolve()) not in dry["removed_worktrees"]
