#!/usr/bin/env python3
"""Governed DIE-Parity Graph Hygiene, Deduplication, Consolidation & Promotion Remediator.

Supports:
- `--dry-run` (default): computes itemized projected ledger/graph deltas with zero live mutation.
- `--apply --approved-clusters <csv>`: executes ONLY operator-approved clusters with rollback backups,
  durable upstream ledger redirects (`_graph_hygiene_redirects`), atomic SQLite rematerialization,
  DIE pre-promotion regression gates, and 100% itemized post-mutation proof verification.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
RGE_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for _p in (str(REPO_ROOT), str(RGE_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.audit_graph_hygiene_and_consolidation import (  # noqa: E402
    DEFAULT_GRAPH_REL,
    run_graph_hygiene_audit,
    run_pre_promotion_regression_gates,
)

DEFAULT_LEDGER_REL = Path("resume_graph_engine/src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json")
SUPPORTED_AUTO_CLUSTERS = frozenset(
    {
        "CLUSTER-01-QUARANTINE-SEARCH-LEAKS",
        "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
        "CLUSTER-03-STRANDED-VERIFIED-METRICS",
        "CLUSTER-04-ISOLATED-AND-RETIRED-NODES",
        "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
    }
)
_SKILL_MATRIX_KEYS: tuple[str, ...] = (
    "skill_rows",
    "agentic_runtime_matrix",
    "actuarial_career_matrix",
    "partner_gtm_matrix",
    "revenue_operations_matrix",
    "commercial_expansion_matrix",
    "phase2_gtm_presales_matrix",
    "phase2_technical_presales_matrix",
    "senior_role_w8_w11_matrix",
    "senior_role_w12_partner_matrix",
)


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _parse_csv(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {tok.strip() for tok in raw.split(",") if tok.strip()}


def _merge_skill_twin_in_ledger(
    ledger: dict[str, Any],
    *,
    survivor_id: str,
    retired_id: str,
    rationale: str,
    now_iso: str,
) -> dict[str, Any]:
    """Consolidate retired twin skill into survivor in master_skills_arsenal_ledger JSON with alias redirect."""
    retired_fact_links: list[str] = []
    retired_sections: list[str] = []
    removed_rows = 0

    for key in _SKILL_MATRIX_KEYS:
        rows = ledger.get(key)
        if not isinstance(rows, list):
            continue
        kept: list[Any] = []
        for row in rows:
            if isinstance(row, dict) and str(row.get("skill_id") or "") == retired_id:
                retired_fact_links.extend(str(f) for f in (row.get("fact_id_links") or []) if f)
                retired_sections.extend(str(s) for s in (row.get("allowed_sections") or []) if s)
                removed_rows += 1
                continue
            kept.append(row)
        ledger[key] = kept

    # Union fact links & record retired_aliases on survivor row(s)
    survivor_updated = False
    for key in _SKILL_MATRIX_KEYS:
        rows = ledger.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and str(row.get("skill_id") or "") == survivor_id:
                existing_facts = list(row.get("fact_id_links") or [])
                for fid in retired_fact_links:
                    if fid not in existing_facts:
                        existing_facts.append(fid)
                row["fact_id_links"] = existing_facts
                existing_secs = list(row.get("allowed_sections") or [])
                for sec in retired_sections:
                    if sec not in existing_secs:
                        existing_secs.append(sec)
                if existing_secs:
                    row["allowed_sections"] = existing_secs
                aliases = list(row.get("retired_aliases") or [])
                if retired_id not in aliases:
                    aliases.append(retired_id)
                row["retired_aliases"] = aliases
                survivor_updated = True

    # Remove retired node from graph_nodes and record alias on survivor node
    gnodes = ledger.get("graph_nodes")
    removed_nodes = 0
    if isinstance(gnodes, list):
        kept_nodes: list[Any] = []
        for node in gnodes:
            if isinstance(node, dict) and str(node.get("node_id") or "") == retired_id:
                removed_nodes += 1
                continue
            if isinstance(node, dict) and str(node.get("node_id") or "") == survivor_id:
                aliases = list(node.get("retired_aliases") or [])
                if retired_id not in aliases:
                    aliases.append(retired_id)
                node["retired_aliases"] = aliases
            kept_nodes.append(node)
        ledger["graph_nodes"] = kept_nodes

    # Repoint graph_edges from retired_id -> survivor_id, dropping self-loops & duplicate triples
    gedges = ledger.get("graph_edges")
    repointed_edges = 0
    deduped_edges = 0
    if isinstance(gedges, list):
        seen_triples: set[tuple[str, str, str]] = set()
        kept_edges: list[Any] = []
        for edge in gedges:
            if not isinstance(edge, dict):
                kept_edges.append(edge)
                continue
            src = str(edge.get("source_node_id") or edge.get("source") or "")
            tgt = str(edge.get("target_node_id") or edge.get("target") or "")
            etype = str(edge.get("edge_type") or "")
            changed = False
            if src == retired_id:
                src = survivor_id
                if "source_node_id" in edge:
                    edge["source_node_id"] = survivor_id
                if "source" in edge:
                    edge["source"] = survivor_id
                changed = True
            if tgt == retired_id:
                tgt = survivor_id
                if "target_node_id" in edge:
                    edge["target_node_id"] = survivor_id
                if "target" in edge:
                    edge["target"] = survivor_id
                changed = True
            if changed:
                repointed_edges += 1
                basis_refs = edge.get("assertion_basis_refs")
                if isinstance(basis_refs, list):
                    edge["assertion_basis_refs"] = [
                        str(ref).replace(retired_id, survivor_id) for ref in basis_refs
                    ]
                if "edge_id" in edge and retired_id in str(edge["edge_id"]):
                    edge["edge_id"] = str(edge["edge_id"]).replace(retired_id, survivor_id)
            if src == tgt:
                deduped_edges += 1
                continue
            triple = (src, tgt, etype)
            if triple in seen_triples:
                deduped_edges += 1
                continue
            seen_triples.add(triple)
            kept_edges.append(edge)
        ledger["graph_edges"] = kept_edges

    redirects = ledger.setdefault("_graph_hygiene_redirects", [])
    if isinstance(redirects, list):
        redirects.append(
            {
                "retired_node_id": retired_id,
                "survivor_node_id": survivor_id,
                "rationale": rationale,
                "merged_at": now_iso,
            }
        )

    return {
        "retired_node_id": retired_id,
        "survivor_node_id": survivor_id,
        "removed_matrix_rows": removed_rows,
        "removed_graph_nodes": removed_nodes,
        "repointed_edges": repointed_edges,
        "deduped_or_self_loop_edges": deduped_edges,
        "survivor_updated": survivor_updated,
    }


def _promote_draft_structural_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
) -> int:
    target_set = set(node_ids)
    promoted = 0
    for node in ledger.get("graph_nodes") or []:
        if isinstance(node, dict) and str(node.get("node_id") or "") in target_set:
            if str(node.get("activation_status") or "") == "DRAFT":
                node["activation_status"] = "ACTIVE"
                promoted += 1
    for p in ledger.get("pillars") or []:
        if isinstance(p, dict) and str(p.get("pillar_id") or p.get("node_id") or "") in target_set:
            if str(p.get("activation_status") or "") == "DRAFT":
                p["activation_status"] = "ACTIVE"
    return promoted


def _archive_retired_isolated_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
    now_iso: str,
) -> int:
    target_set = set(node_ids)
    archived = ledger.setdefault("_retired_archived_nodes", [])
    kept: list[Any] = []
    removed = 0
    for node in ledger.get("graph_nodes") or []:
        if (
            isinstance(node, dict)
            and str(node.get("node_id") or "") in target_set
            and str(node.get("activation_status") or "") == "RETIRED"
        ):
            if isinstance(archived, list):
                archived.append({**node, "archived_at": now_iso})
            removed += 1
            continue
        kept.append(node)
    ledger["graph_nodes"] = kept
    return removed


def _reseal_ledger_hardening(ledger: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Re-run canonical W1/W2/W3 ledger hardening and authority reconciliation after approved edits."""
    from apps_rg.fact_inventory.c03_graph_authority_reconciliation_wave3 import (  # noqa: E402
        reconcile_graph_authority_wave3,
    )
    from apps_rg.fact_inventory.c03_graph_edge_semantic_hardening import (  # noqa: E402
        harden_graph_edge_semantics,
    )
    from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import (  # noqa: E402
        harden_graph_node_semantics,
    )
    from apps_rg.fact_inventory.skills_graph.classification import (  # noqa: E402
        default_candidate_fact_ledger_path,
    )

    rge_root = repo_root / "resume_graph_engine"
    cand_path = default_candidate_fact_ledger_path(rge_root)
    base_path = rge_root / "src/apps_rg/resume/base/amit_ayer_base_resume_v1.json"
    cand_payload = json.loads(cand_path.read_text(encoding="utf-8")) if cand_path.is_file() else {}
    base_payload = json.loads(base_path.read_text(encoding="utf-8")) if base_path.is_file() else {}

    gm = ledger.get("graph_metadata")
    if isinstance(gm, dict):
        gm.pop("node_semantic_hardening", None)
        gm.pop("edge_semantic_hardening", None)
        gm.pop("authority_reconciliation", None)

    # Strip W3-synthesized edges and stale W2 edge semantic stamps so W1->W2->W3 reseal cleanly
    raw_edges = ledger.get("graph_edges")
    if isinstance(raw_edges, list):
        cleaned_edges: list[Any] = []
        for e in raw_edges:
            if not isinstance(e, dict):
                cleaned_edges.append(e)
                continue
            if str(e.get("edge_id") or "").startswith(("edge:w3:", "edge:authority_fact:")):
                continue
            e = dict(e)
            for stale_key in (
                "edge_semantic_contract_version",
                "semantic_status",
                "lifecycle_disposition",
                "integrity_gap_reason",
                "canonical_assertion_text",
                "assertion_basis",
                "assertion_basis_refs",
            ):
                e.pop(stale_key, None)
            cleaned_edges.append(e)
        ledger["graph_edges"] = cleaned_edges

    w1 = harden_graph_node_semantics(
        ledger,
        candidate_fact_payload=cand_payload,
        base_resume_payload=base_payload,
    )
    w2 = harden_graph_edge_semantics(w1)
    w3 = reconcile_graph_authority_wave3(w2)
    return w3


def _wire_stranded_verified_metrics_in_bundles(
    repo_root: Path,
    items: Sequence[Mapping[str, Any]],
) -> int:
    """Attach verified 2-hop fact-matched skill links onto stranded APPROVED_GRAPH_SSOT metrics in bundle JSONs."""
    by_metric = {
        str(it["metric_id"]): list(it.get("candidate_skill_ids") or [])
        for it in items
        if it.get("auto_linkable") and it.get("candidate_skill_ids")
    }
    if not by_metric:
        return 0
    fact_dir = repo_root / "resume_graph_engine/src/apps_rg/fact_inventory"
    wired = 0
    for bundle_file in sorted(fact_dir.glob("*_role_episode_bundles.json")):
        payload = json.loads(bundle_file.read_text(encoding="utf-8"))
        m_nodes = payload.get("metric_outcome_nodes")
        if not isinstance(m_nodes, dict):
            continue
        dirty = False
        for mid, mobj in m_nodes.items():
            if mid not in by_metric or not isinstance(mobj, dict):
                continue
            if str(mobj.get("approval_status") or "") != "APPROVED_GRAPH_SSOT":
                continue
            existing = list(mobj.get("linked_skill_ids") or [])
            added = [sid for sid in by_metric[mid] if sid not in existing]
            if added:
                mobj["linked_skill_ids"] = existing + added
                wired += 1
                dirty = True
        if dirty:
            bundle_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return wired


def apply_graph_hygiene_remediation(
    *,
    repo_root: Path = REPO_ROOT,
    db_path: Path | None = None,
    ledger_path: Path | None = None,
    approved_clusters: Sequence[str] = (),
    excluded_clusters: Sequence[str] = (),
    apply_changes: bool = False,
    skip_rematerialize: bool = False,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Preview (--dry-run) or execute (--apply) approved graph hygiene clusters with pre-promotion gates."""
    resolved_root = Path(repo_root).resolve()
    target_db = Path(db_path).resolve() if db_path is not None else (resolved_root / DEFAULT_GRAPH_REL)
    target_ledger = Path(ledger_path).resolve() if ledger_path is not None else (resolved_root / DEFAULT_LEDGER_REL)
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pre_audit = run_graph_hygiene_audit(repo_root=resolved_root, db_path=target_db)
    clusters_by_id = {str(c["cluster_id"]): c for c in pre_audit["hitl_clusters"]}
    approved_set = set(approved_clusters)
    excluded_set = set(excluded_clusters)

    # Fail closed on unknown cluster IDs
    unknown = (approved_set | excluded_set) - (set(clusters_by_id) | SUPPORTED_AUTO_CLUSTERS)
    if unknown:
        raise ValueError(f"Unknown cluster ID(s): {sorted(unknown)}")

    projected_actions: list[dict[str, Any]] = []
    target_clusters = sorted(approved_set) if approved_set else [c["cluster_id"] for c in pre_audit["hitl_clusters"]]
    for cid in target_clusters:
        if cid in excluded_set or cid not in clusters_by_id:
            continue
        c = clusters_by_id[cid]
        projected_actions.append(
            {
                "cluster_id": cid,
                "proposed_fix": c["proposed_fix"],
                "item_count": c["item_count"],
                "supported_automated_handler": cid in SUPPORTED_AUTO_CLUSTERS,
                "requires_isolated_scrutiny": c["requires_isolated_scrutiny"],
            }
        )

    pre_db_sha = _sha256_file(target_db)
    pre_ledger_sha = _sha256_file(target_ledger)
    receipt: dict[str, Any] = {
        "schema_version": "agents.graph_hygiene_remediation_receipt.v1",
        "timestamp_utc": now_iso,
        "mode": "APPLY" if apply_changes else "DRY_RUN",
        "mutated": False,
        "pre_db_sha256": pre_db_sha,
        "pre_ledger_sha256": pre_ledger_sha,
        "approved_clusters": sorted(approved_set),
        "excluded_clusters": sorted(excluded_set),
        "projected_actions": projected_actions,
        "baseline_counts": pre_audit["baseline_counts"],
    }

    if not apply_changes:
        receipt["status"] = "DRY_RUN_READY"
        return receipt

    if not approved_set:
        raise ValueError("Refusing to mutate graph with --apply and empty --approved-clusters (HITL required).")

    unsupported = approved_set - SUPPORTED_AUTO_CLUSTERS
    if unsupported:
        raise ValueError(
            f"Approved cluster(s) require manual/editorial review rather than blind auto-merge: {sorted(unsupported)}"
        )

    # Create rollback backup before mutating anything
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if target_db.is_file():
            shutil.copy2(target_db, backup_dir / f"{target_db.name}.bak")
        if target_ledger.is_file():
            shutil.copy2(target_ledger, backup_dir / f"{target_ledger.name}.bak")
        receipt["backup_dir"] = str(backup_dir)

    ledger = json.loads(target_ledger.read_text(encoding="utf-8"))
    ledger_dirty = False
    applied_deltas: dict[str, Any] = {}

    if "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS" in approved_set and "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS" in clusters_by_id:
        merges = []
        for item in clusters_by_id["CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS"]["items"]:
            merges.append(
                _merge_skill_twin_in_ledger(
                    ledger,
                    survivor_id=str(item["survivor_node_id"]),
                    retired_id=str(item["retired_node_id"]),
                    rationale=str(item.get("rationale") or "Duplicate skill twin consolidation"),
                    now_iso=now_iso,
                )
            )
            ledger_dirty = True
        applied_deltas["CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS"] = {"merged_pairs": len(merges), "details": merges}

    if "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS" in approved_set and "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS" in clusters_by_id:
        ids = [str(it["node_id"]) for it in clusters_by_id["CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS"]["items"]]
        promoted = _promote_draft_structural_nodes_in_ledger(ledger, ids)
        ledger_dirty = ledger_dirty or (promoted > 0)
        applied_deltas["CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS"] = {"promoted_nodes": promoted}

    if "CLUSTER-04-ISOLATED-AND-RETIRED-NODES" in approved_set and "CLUSTER-04-ISOLATED-AND-RETIRED-NODES" in clusters_by_id:
        ids = [
            str(it["node_id"])
            for it in clusters_by_id["CLUSTER-04-ISOLATED-AND-RETIRED-NODES"]["items"]
            if it.get("disposition") == "archive_retired"
        ]
        archived = _archive_retired_isolated_nodes_in_ledger(ledger, ids, now_iso)
        ledger_dirty = ledger_dirty or (archived > 0)
        applied_deltas["CLUSTER-04-ISOLATED-AND-RETIRED-NODES"] = {"archived_retired_nodes": archived}

    if "CLUSTER-03-STRANDED-VERIFIED-METRICS" in approved_set and "CLUSTER-03-STRANDED-VERIFIED-METRICS" in clusters_by_id:
        wired = _wire_stranded_verified_metrics_in_bundles(
            resolved_root,
            clusters_by_id["CLUSTER-03-STRANDED-VERIFIED-METRICS"]["items"],
        )
        applied_deltas["CLUSTER-03-STRANDED-VERIFIED-METRICS"] = {"wired_verified_metrics": wired}

    if ledger_dirty:
        ledger = _reseal_ledger_hardening(ledger, resolved_root)
        gm = ledger.get("graph_metadata")
        if isinstance(gm, dict):
            gm["node_count"] = len(ledger.get("graph_nodes") or [])
            gm["edge_count"] = len(ledger.get("graph_edges") or [])
        target_ledger.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not skip_rematerialize:
        from apps_rg.fact_inventory.skills_graph.materializer import (  # noqa: E402
            materialize_augmented_skills_graph_sqlite,
        )

        mat_summary = materialize_augmented_skills_graph_sqlite(
            graph=ledger,
            repo_root=resolved_root / "resume_graph_engine",
            db_path=target_db,
            json_source_path=target_ledger,
        )
        receipt["materialization_summary"] = {
            "node_count": mat_summary.get("node_count_sqlite"),
            "edge_count": mat_summary.get("edge_count_sqlite"),
            "semantic_unit_count": mat_summary.get("semantic_unit_count"),
        }

    post_gates = run_pre_promotion_regression_gates(target_db, before_metrics=pre_audit["baseline_counts"])
    post_audit = run_graph_hygiene_audit(repo_root=resolved_root, db_path=target_db)

    receipt["mutated"] = True
    receipt["applied_deltas"] = applied_deltas
    receipt["post_db_sha256"] = _sha256_file(target_db)
    receipt["post_ledger_sha256"] = _sha256_file(target_ledger)
    receipt["post_counts"] = post_audit["baseline_counts"]
    receipt["pre_promotion_regression_gates"] = post_gates
    receipt["status"] = "PASS" if post_gates["status"] == "PASS" else "FAIL"
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Governed DIE-parity Graph Hygiene Remediation Runner.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--approved-clusters", type=str, default="", help="Comma-separated approved cluster IDs.")
    parser.add_argument("--excluded-clusters", type=str, default="", help="Comma-separated excluded cluster IDs.")
    parser.add_argument("--dry-run", action="store_true", help="Preview projected deltas with zero live mutation.")
    parser.add_argument("--apply", action="store_true", help="Apply operator-approved clusters and rematerialize.")
    parser.add_argument("--skip-rematerialize", action="store_true", help="Skip SQLite rebuild after ledger update.")
    parser.add_argument("--backup-dir", type=Path, default=None, help="Directory for pre-mutation rollback backups.")
    parser.add_argument("--receipt", type=Path, default=None, help="Optional path to write JSON receipt.")
    parser.add_argument("--json", action="store_true", help="Print JSON receipt.")
    args = parser.parse_args(argv)

    apply_mode = bool(args.apply) and not bool(args.dry_run)
    receipt = apply_graph_hygiene_remediation(
        repo_root=args.repo_root,
        db_path=args.db,
        ledger_path=args.ledger,
        approved_clusters=sorted(_parse_csv(args.approved_clusters)),
        excluded_clusters=sorted(_parse_csv(args.excluded_clusters)),
        apply_changes=apply_mode,
        skip_rematerialize=bool(args.skip_rematerialize),
        backup_dir=args.backup_dir,
    )
    if args.receipt is not None:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] in ("DRY_RUN_READY", "PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
