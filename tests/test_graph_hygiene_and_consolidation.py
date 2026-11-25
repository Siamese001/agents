"""Unmocked regression & counterfactual tests for DIE-parity graph hygiene, dedup, consolidation & promotion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from apps_rg.fact_inventory.skills_graph.materializer import (
    materialize_augmented_skills_graph_sqlite,
)
from tools.apply_graph_hygiene_remediation import (
    DEFAULT_LEDGER_REL,
    apply_graph_hygiene_remediation,
)
from tools.audit_graph_hygiene_and_consolidation import (
    DEFAULT_GRAPH_REL,
    compute_string_similarity,
    normalize_text,
    open_readonly_sqlite,
    run_graph_hygiene_audit,
    run_pre_promotion_regression_gates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_graph_hygiene_audit_runs_readonly_and_detects_real_clusters() -> None:
    report = run_graph_hygiene_audit(repo_root=REPO_ROOT)
    assert report["read_only"] is True
    assert report["schema_version"] == "agents.graph_hygiene_consolidation_audit.v1"
    assert report["baseline_counts"]["node_count"] > 300
    assert report["pre_promotion_regression_gates"]["status"] == "PASS"
    assert report["pre_promotion_regression_gates"]["fts_exact_active_parity"]["leaks"] == 0
    assert report["pre_promotion_regression_gates"]["quarantine_semantic_unit_isolation"]["leaks"] == 0

    cluster_ids = {c["cluster_id"] for c in report["hitl_clusters"]}
    # Real clusters must be surfaced until operator approves remediation
    assert "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS" in cluster_ids or "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS" in cluster_ids
    for c in report["hitl_clusters"]:
        assert c["council_debate"]["panel_mode"] == "hybrid_deterministic_council"
        assert c["item_count"] == len(c["items"]) > 0


def test_02a_and_02b_disjointness_and_07_repo_stub_path_enrichment() -> None:
    report = run_graph_hygiene_audit(repo_root=REPO_ROOT)
    dup_scan = report["scanners"]["duplicate_and_near_duplicate_nodes"]
    stub_scan = report["scanners"]["evidence_and_stub_hygiene"]

    twins_02a = dup_scan["exact_skill_twins"]
    groups_02b = dup_scan["verbatim_clone_groups"]

    retired_02a = {str(t["retired_node_id"]) for t in twins_02a}
    members_02b = {str(mid) for g in groups_02b for mid in g["member_ids"]}

    # Zero overlap between 02A retired twins and 02B clone groups
    assert retired_02a.isdisjoint(members_02b)
    assert "skill_quant_multi_greek_hedging" in retired_02a
    assert "skill_quant_multi_greek_hedging" not in members_02b

    # skill_p2_gtm_joint_vendor_roadmaps must be routed to 02A with non-p2 canonical survivor
    p2_roadmap_matches = [
        t for t in twins_02a if t["retired_node_id"] == "skill_p2_gtm_joint_vendor_roadmaps"
    ]
    assert len(p2_roadmap_matches) == 1
    assert p2_roadmap_matches[0]["survivor_node_id"] == "skill_partner_cloud_vendor_joint_gtm"
    assert "skill_p2_gtm_joint_vendor_roadmaps" not in members_02b

    # CLUSTER-07 hex repo_evidence stubs must carry target_relpath, suggested_label, and path_exists
    hex_stubs = stub_scan["hex_repo_evidence_stubs"]
    assert len(hex_stubs) > 0
    for stub in hex_stubs:
        assert isinstance(stub.get("target_relpath"), str) and stub["target_relpath"] != ""
        assert isinstance(stub.get("suggested_label"), str) and stub["suggested_label"] != ""
        assert isinstance(stub.get("path_exists"), bool)
    assert any(s["path_exists"] is True for s in hex_stubs)
    assert any(s["path_exists"] is False and s["target_relpath"].startswith(".codex/") for s in hex_stubs)


def test_counterfactual_fts_and_quarantine_leak_triggers_fail_closed_gate(tmp_path: Path) -> None:
    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)

    # Inject a synthetic quarantined node directly into graph_nodes_fts to prove fail-closed detection
    with sqlite3.connect(str(sandbox_db)) as conn:
        q_row = conn.execute(
            "SELECT node_id, node_type, label, description FROM graph_nodes "
            "WHERE activation_status = 'QUARANTINED_UNVERIFIED_SYNTHETIC' LIMIT 1"
        ).fetchone()
        assert q_row is not None
        conn.execute(
            "INSERT INTO graph_nodes_fts (node_id, node_type, label, description) VALUES (?, ?, ?, ?)",
            q_row,
        )
        conn.commit()

    gates = run_pre_promotion_regression_gates(sandbox_db)
    assert gates["status"] == "FAIL"
    assert gates["fts_exact_active_parity"]["status"] == "FAIL"
    assert gates["fts_exact_active_parity"]["leaks"] >= 1


def test_dry_run_remediation_never_mutates_graph_or_ledger() -> None:
    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        apply_changes=False,
    )
    assert receipt["mode"] == "DRY_RUN"
    assert receipt["status"] == "DRY_RUN_READY"
    assert receipt["mutated"] is False
    assert len(receipt["projected_actions"]) > 0


def test_apply_remediation_requires_explicit_approved_clusters() -> None:
    with pytest.raises(ValueError, match="empty --approved-clusters"):
        apply_graph_hygiene_remediation(
            repo_root=REPO_ROOT,
            approved_clusters=(),
            apply_changes=True,
        )

    # Non-mutating item decisions alone with empty approved_clusters must also refuse --apply
    with pytest.raises(ValueError, match="empty --approved-clusters"):
        apply_graph_hygiene_remediation(
            repo_root=REPO_ROOT,
            approved_clusters=(),
            decisions_payload={
                "items": {
                    "grp_hold": {
                        "cluster_id": "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
                        "action_kind": "keep_distinct",
                        "decision": "KEEP_DISTINCT",
                    }
                }
            },
            apply_changes=True,
        )


def test_sandbox_apply_skill_twin_merge_and_draft_promotion_preserves_redirects(tmp_path: Path) -> None:
    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    sandbox_ledger = tmp_path / "master_skills_arsenal_ledger.json"
    backup_dir = tmp_path / "backups"
    src_ledger = REPO_ROOT / DEFAULT_LEDGER_REL
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)
    shutil.copy2(src_ledger, sandbox_ledger)

    pre = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    pre_twins = pre["baseline_counts"]["exact_skill_twins_count"]
    pre_drafts = pre["baseline_counts"]["draft_structural_count"]
    assert pre_twins > 0
    assert pre_drafts > 0

    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        db_path=sandbox_db,
        ledger_path=sandbox_ledger,
        approved_clusters=[
            "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
            "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
        ],
        apply_changes=True,
        skip_rematerialize=True,
        backup_dir=backup_dir,
    )
    assert receipt["status"] == "PASS", json.dumps(
        {
            "gates": receipt["pre_promotion_regression_gates"],
            "pre": receipt["baseline_counts"],
            "post": receipt["post_counts"],
        },
        indent=2,
    )
    assert receipt["mutated"] is True
    assert (backup_dir / "master_skills_arsenal_ledger.json.bak").is_file()

    updated_ledger = json.loads(sandbox_ledger.read_text(encoding="utf-8"))
    redirects = updated_ledger.get("_graph_hygiene_redirects") or []
    assert len(redirects) == pre_twins
    assert receipt["applied_deltas"]["CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS"]["promoted_nodes"] > 0

    # Rebuild SQLite from the consolidated sandbox ledger and verify zero-regression & twin reduction
    rebuilt_db = tmp_path / "rebuilt_graph.sqlite"
    materialize_augmented_skills_graph_sqlite(
        repo_root=REPO_ROOT / "resume_graph_engine",
        db_path=rebuilt_db,
        json_source_path=sandbox_ledger,
    )
    post = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=rebuilt_db)
    assert post["pre_promotion_regression_gates"]["status"] == "PASS"
    assert post["baseline_counts"]["exact_skill_twins_count"] == 0
    assert post["baseline_counts"]["draft_structural_count"] == 0


def test_item_granular_decisions_file_end_to_end_across_clusters_in_sandbox(tmp_path: Path) -> None:
    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    sandbox_ledger = tmp_path / "master_skills_arsenal_ledger.json"
    decisions_path = tmp_path / "decisions.json"
    backup_dir = tmp_path / "backups"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)
    shutil.copy2(REPO_ROOT / DEFAULT_LEDGER_REL, sandbox_ledger)

    pre = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    clusters_by_id = {c["cluster_id"]: c for c in pre["hitl_clusters"]}
    all_c05_ids = [it["node_id"] for it in clusters_by_id["CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS"]["items"]]
    assert len(all_c05_ids) == 52

    items_payload: dict[str, dict[str, object]] = {
        # CLUSTER-02A: survivor flip (keep skill_p2_gtm_solution_mapping, retire canonical)
        "02a_flip": {
            "cluster_id": "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
            "action_kind": "merge_skill_twin",
            "decision": "APPROVE",
            "params": {
                "survivor_id": "skill_p2_gtm_solution_mapping",
                "retired_id": "skill_partner_presales_sa_support",
                "rationale": "Operator survivor flip test",
            },
        },
        # CLUSTER-02A: differentiate descriptions instead of merging
        "02a_diff": {
            "cluster_id": "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
            "action_kind": "differentiate_skill_descriptions",
            "decision": "APPROVE",
            "params": {
                "skill_ids": [
                    "skill_greeks_hedging_multi_greek_hedging",
                    "skill_quant_multi_greek_hedging",
                ]
            },
        },
        # CLUSTER-02B: differentiate one clone group, consolidate another, keep_distinct a third
        "02b_diff_greeks": {
            "cluster_id": "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
            "action_kind": "differentiate_skill_descriptions",
            "decision": "APPROVE",
            "params": {"skill_ids": ["skill_greeks_vega", "skill_greeks_theta"]},
        },
        "02b_consolidate_alliance": {
            "cluster_id": "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
            "action_kind": "consolidate_clone_group",
            "decision": "APPROVE",
            "params": {
                "survivor_id": "skill_partner_alliance_gtm_execution",
                "retired_ids": ["skill_partner_ai_architecture_advisory"],
            },
        },
        "02b_keep_distinct": {
            "cluster_id": "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
            "action_kind": "keep_distinct",
            "decision": "KEEP_DISTINCT",
        },
        # CLUSTER-02C: consolidate overlapping capability domain
        "02c_domain_merge": {
            "cluster_id": "CLUSTER-02C-CAPABILITY-DOMAIN-CONSOLIDATION",
            "action_kind": "consolidate_capability_domain",
            "decision": "APPROVE",
            "params": {
                "survivor_id": "domain_phase2_gtm_presales",
                "retired_id": "domain_gtm_presales_motion",
            },
        },
        # CLUSTER-04: archive retired policy node AND isolated section node without resurrection
        "04_archive_policy": {
            "cluster_id": "CLUSTER-04-ISOLATED-AND-RETIRED-NODES",
            "action_kind": "archive_isolated_node",
            "decision": "APPROVE",
            "params": {"node_id": "policy_executive_summary_high_confidence_only"},
        },
        "04_archive_section": {
            "cluster_id": "CLUSTER-04-ISOLATED-AND-RETIRED-NODES",
            "action_kind": "archive_isolated_node",
            "decision": "APPROVE",
            "params": {"node_id": "section_leadership"},
        },
        # CLUSTER-06: external promotion, portfolio hold, internal hold, and retirement
        "06_promote_ext": {
            "cluster_id": "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
            "action_kind": "promote_skill_external",
            "decision": "APPROVE",
            "params": {"skill_id": "skill_policycenter_workflow_mapping"},
        },
        "06_portfolio_hold": {
            "cluster_id": "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
            "action_kind": "set_skill_portfolio_only",
            "decision": "APPROVE",
            "params": {"skill_id": "skill_public_vs_private_cloud_tco_framing"},
        },
        "06_internal_hold": {
            "cluster_id": "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
            "action_kind": "lock_skill_internal_only",
            "decision": "APPROVE",
            "params": {"skill_id": "skill_reserved_instance_rightsizing_strategy"},
        },
        "06_retire_skill": {
            "cluster_id": "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
            "action_kind": "retire_skill",
            "decision": "APPROVE",
            "params": {"skill_id": "skill_sr_insurance_systems_resilience_internal"},
        },
        # CLUSTER-07: rename valid repo stub, remove stale .codex repo stub, and cap sibling fan-out
        "07_rename_stub": {
            "cluster_id": "CLUSTER-07-STUB-AND-SIBLING-BLOAT",
            "action_kind": "rename_repo_stub",
            "decision": "APPROVE",
            "params": {
                "node_id": "repo_f161d0",
                "new_label": "Candidate Fact Ledger Module",
                "target_relpath": "apps_rg/fact_inventory/candidate_fact_ledger.py",
            },
        },
        "07_remove_stale_stub": {
            "cluster_id": "CLUSTER-07-STUB-AND-SIBLING-BLOAT",
            "action_kind": "remove_stale_repo_stub",
            "decision": "APPROVE",
            "params": {"node_id": "repo_c303f9"},
        },
        "07_cap_siblings": {
            "cluster_id": "CLUSTER-07-STUB-AND-SIBLING-BLOAT",
            "action_kind": "cap_sibling_fanout",
            "decision": "APPROVE",
            "params": {"max_siblings_per_node": 10},
        },
    }
    # CLUSTER-05: promote all 52 structural nodes item-by-item (pillars, domains, employments, tracks)
    for nid in all_c05_ids:
        items_payload[f"05_prom_{nid}"] = {
            "cluster_id": "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
            "action_kind": "promote_structural_node",
            "decision": "APPROVE",
            "params": {"node_id": nid},
        }

    decisions_path.write_text(json.dumps({"items": items_payload}, indent=2) + "\n", encoding="utf-8")

    # Dry-run first: must preview projected actions & skipped items with zero file mutation
    dry = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        db_path=sandbox_db,
        ledger_path=sandbox_ledger,
        decisions_file=decisions_path,
        apply_changes=False,
    )
    assert dry["status"] == "DRY_RUN_READY"
    assert dry["mutated"] is False
    assert len(dry["skipped_or_held_items"]) == 1

    # Full unmocked apply + SQLite rebuild + pre-promotion regression gates
    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        db_path=sandbox_db,
        ledger_path=sandbox_ledger,
        decisions_file=decisions_path,
        apply_changes=True,
        skip_rematerialize=False,
        backup_dir=backup_dir,
    )
    assert receipt["status"] == "PASS", json.dumps(
        {
            "gates": receipt["pre_promotion_regression_gates"],
            "pre": receipt["baseline_counts"],
            "post": receipt["post_counts"],
        },
        indent=2,
    )
    assert receipt["pre_promotion_regression_gates"]["status"] == "PASS"

    post = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    assert post["pre_promotion_regression_gates"]["status"] == "PASS"
    assert post["baseline_counts"]["domain_near_duplicates_count"] == 0
    assert post["baseline_counts"]["draft_structural_count"] == 0

    stub_scan = post["scanners"]["evidence_and_stub_hygiene"]
    assert stub_scan["sibling_links_per_node"] <= 10.0
    assert stub_scan["sibling_bloat_detected"] is False
    remaining_hex_ids = {s["node_id"] for s in stub_scan["hex_repo_evidence_stubs"]}
    assert "repo_f161d0" not in remaining_hex_ids
    assert "repo_c303f9" not in remaining_hex_ids

    conn = open_readonly_sqlite(sandbox_db)
    try:
        # 02A survivor flip verified
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_id = 'skill_p2_gtm_solution_mapping'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_id = 'skill_partner_presales_sa_support'"
        ).fetchone()[0] == 0

        # 02A & 02B differentiated skills remain present with distinct descriptions
        vega_desc = conn.execute(
            "SELECT description FROM graph_nodes WHERE node_id = 'skill_greeks_vega'"
        ).fetchone()[0]
        theta_desc = conn.execute(
            "SELECT description FROM graph_nodes WHERE node_id = 'skill_greeks_theta'"
        ).fetchone()[0]
        assert len(vega_desc) >= 36 and len(theta_desc) >= 36
        assert vega_desc != theta_desc

        # 02B consolidated clone removed
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_id = 'skill_partner_ai_architecture_advisory'"
        ).fetchone()[0] == 0

        # 04 non-resurrection verified for both policy and section nodes
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_id IN "
            "('policy_executive_summary_high_confidence_only', 'section_leadership')"
        ).fetchone()[0] == 0

        # 05 all 4 structural types promoted to ACTIVE
        draft_cnt = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_type IN "
            "('pillar', 'capability_domain', 'employment', 'career_track') AND activation_status = 'DRAFT'"
        ).fetchone()[0]
        assert draft_cnt == 0

        # 06 external promotion vs portfolio/internal/retired holds preserved without override
        ext_row = conn.execute(
            "SELECT activation_status, support_level, external_eligible FROM graph_nodes "
            "WHERE node_id = 'skill_policycenter_workflow_mapping'"
        ).fetchone()
        assert tuple(ext_row) == ("ACTIVE_CONFIRMED", "DIRECT_FROM_RESUME_ARCHIVE", 1)

        port_row = conn.execute(
            "SELECT support_level, external_eligible FROM graph_nodes "
            "WHERE node_id = 'skill_public_vs_private_cloud_tco_framing'"
        ).fetchone()
        assert tuple(port_row) == ("REPO_EVIDENCE_PORTFOLIO", 0)

        int_row = conn.execute(
            "SELECT support_level, external_eligible FROM graph_nodes "
            "WHERE node_id = 'skill_reserved_instance_rightsizing_strategy'"
        ).fetchone()
        assert tuple(int_row) == ("INTERNAL_ONLY", 0)

        ret_row = conn.execute(
            "SELECT activation_status, external_eligible FROM graph_nodes "
            "WHERE node_id = 'skill_sr_insurance_systems_resilience_internal'"
        ).fetchone()
        assert tuple(ret_row) == ("RETIRED", 0)
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes_fts WHERE node_id = 'skill_sr_insurance_systems_resilience_internal'"
        ).fetchone()[0] == 0

        # 07 renamed stub & removed stale stub & max 10 siblings per node
        stub_lbl = conn.execute(
            "SELECT label FROM graph_nodes WHERE node_id = 'repo_f161d0'"
        ).fetchone()[0]
        assert stub_lbl == "Candidate Fact Ledger Module"
        assert conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_id = 'repo_c303f9'"
        ).fetchone()[0] == 0
        max_per_node = conn.execute(
            "SELECT COALESCE(MAX(c), 0) FROM (SELECT COUNT(*) c FROM graph_sibling_links GROUP BY node_id)"
        ).fetchone()[0]
        assert max_per_node <= 10
    finally:
        conn.close()


def test_item_granular_cluster_03_wire_metric_subset_never_touches_tracked_bundles(tmp_path: Path) -> None:
    tracked_bundle_dir = REPO_ROOT / "resume_graph_engine/src/apps_rg/fact_inventory"
    tracked_bundles = sorted(tracked_bundle_dir.glob("*_role_episode_bundles.json"))
    pre_bundle_hashes = {p.name: _sha256(p) for p in tracked_bundles}

    sandbox_bundles = tmp_path / "bundles"
    sandbox_bundles.mkdir(parents=True, exist_ok=True)
    for bfile in tracked_bundles:
        shutil.copy2(bfile, sandbox_bundles / bfile.name)

    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    sandbox_ledger = tmp_path / "master_skills_arsenal_ledger.json"
    backup_dir = tmp_path / "backups"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)
    shutil.copy2(REPO_ROOT / DEFAULT_LEDGER_REL, sandbox_ledger)

    pre = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    c03 = next(c for c in pre["hitl_clusters"] if c["cluster_id"] == "CLUSTER-03-STRANDED-VERIFIED-METRICS")
    linkable = [it for it in c03["items"] if it["auto_linkable"] and it["candidate_skill_ids"]]
    assert len(linkable) >= 2
    chosen = linkable[:2]

    decisions_payload = {
        "items": {
            it["metric_id"]: {
                "cluster_id": "CLUSTER-03-STRANDED-VERIFIED-METRICS",
                "action_kind": "wire_metric_to_skills",
                "decision": "APPROVE",
                "params": {
                    "metric_id": it["metric_id"],
                    "skill_ids": it["candidate_skill_ids"][:2],
                },
            }
            for it in chosen
        }
    }

    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        db_path=sandbox_db,
        ledger_path=sandbox_ledger,
        bundles_dir=sandbox_bundles,
        decisions_payload=decisions_payload,
        apply_changes=True,
        skip_rematerialize=False,
        backup_dir=backup_dir,
    )
    assert receipt["status"] == "PASS", json.dumps(
        {
            "gates": receipt["pre_promotion_regression_gates"],
            "pre": receipt["baseline_counts"],
            "post": receipt["post_counts"],
        },
        indent=2,
    )
    assert receipt["pre_promotion_regression_gates"]["status"] == "PASS"

    post = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    assert post["baseline_counts"]["stranded_verified_metrics_count"] == (
        pre["baseline_counts"]["stranded_verified_metrics_count"] - 2
    )

    conn = open_readonly_sqlite(sandbox_db)
    try:
        for it in chosen:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM graph_edges "
                "WHERE edge_type = 'skill_surfaces_metric_outcome' AND target_node_id = ?",
                (it["metric_id"],),
            ).fetchone()[0]
            assert cnt >= 1
    finally:
        conn.close()

    # Tracked bundle JSONs in the worktree must be 100% untouched
    post_bundle_hashes = {p.name: _sha256(p) for p in tracked_bundles}
    assert post_bundle_hashes == pre_bundle_hashes


def test_legacy_approve_inference_cli_single_item_and_alias_edge_cases(tmp_path: Path) -> None:
    from tools.apply_graph_hygiene_remediation import main as remediator_cli_main

    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    sandbox_ledger = tmp_path / "master_skills_arsenal_ledger.json"
    decisions_path = tmp_path / "single_item_decisions.json"
    receipt_path = tmp_path / "receipt.json"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)
    shutil.copy2(REPO_ROOT / DEFAULT_LEDGER_REL, sandbox_ledger)

    # Single-item partial cluster apply via CLI --decisions-file + legacy "APPROVE" without action_kind
    # plus raw alias IDs (exp_ey_001, pillar_agentic_runtime_governance) and skill_risk_enterprise_risk_controls
    decisions_path.write_text(
        json.dumps(
            {
                "items": {
                    "exp_ey_001": {
                        "cluster_id": "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
                        "decision": "APPROVE",
                    },
                    "pillar_agentic_runtime_governance": {
                        "cluster_id": "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
                        "decision": "APPROVE",
                    },
                    "domain_healing_retry_resilience": {
                        "cluster_id": "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
                        "action_kind": "retire_structural_node",
                        "decision": "APPROVE",
                        "params": {"node_id": "domain_healing_retry_resilience"},
                    },
                    "skill_risk_enterprise_risk_controls": {
                        "cluster_id": "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
                        "action_kind": "promote_skill_external",
                        "decision": "APPROVE",
                        "params": {"skill_id": "skill_risk_enterprise_risk_controls"},
                    },
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    rc = remediator_cli_main(
        [
            "--repo-root",
            str(REPO_ROOT),
            "--db",
            str(sandbox_db),
            "--ledger",
            str(sandbox_ledger),
            "--decisions-file",
            str(decisions_path),
            "--apply",
            "--receipt",
            str(receipt_path),
        ]
    )
    assert rc == 0
    saved_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert saved_receipt["status"] == "PASS"

    conn = open_readonly_sqlite(sandbox_db)
    try:
        ey_status = conn.execute(
            "SELECT activation_status FROM graph_nodes WHERE node_id = 'employment_exp_ey_001'"
        ).fetchone()[0]
        assert ey_status == "ACTIVE"
        pil_status = conn.execute(
            "SELECT activation_status FROM graph_nodes WHERE node_id = 'pillar_agentic_ai_platforms'"
        ).fetchone()[0]
        assert pil_status == "ACTIVE"
        dom_status = conn.execute(
            "SELECT activation_status FROM graph_nodes WHERE node_id = 'domain_healing_retry_resilience'"
        ).fetchone()[0]
        assert dom_status == "RETIRED"
        erc_row = conn.execute(
            "SELECT activation_status, external_eligible FROM graph_nodes "
            "WHERE node_id = 'skill_risk_enterprise_risk_controls'"
        ).fetchone()
        assert tuple(erc_row) == ("ACTIVE_CONFIRMED", 1)
    finally:
        conn.close()


def test_string_similarity_helper_matches_die_scan1_formula() -> None:
    n1 = normalize_text("Phase2 Gtm Presales")
    n2 = normalize_text("Gtm Presales Motion")
    sim, seq, jacc = compute_string_similarity(n1, n2)
    assert 0.65 <= sim <= 1.0
    assert sim == round(0.55 * seq + 0.45 * jacc, 4)
