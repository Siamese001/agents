#!/usr/bin/env python3
"""Governed DIE-Parity Graph Hygiene, Deduplication, Consolidation & Promotion Remediator.

Supports:
- `--dry-run` (default): computes itemized projected ledger/graph deltas with zero live mutation.
- `--apply --approved-clusters <csv>`: executes operator-approved clusters with rollback backups,
  durable upstream ledger redirects (`_graph_hygiene_redirects`), atomic SQLite rematerialization,
  DIE pre-promotion regression gates, and 100% itemized post-mutation proof verification.
- `--apply --decisions-file <path>`: executes item-granular seriatim/cluster decisions across all
  hygiene clusters (`CLUSTER-01` through `CLUSTER-07`), supporting partial-cluster execution,
  survivor flips, skill description differentiation, domain consolidation, non-resurrecting
  archival, structural alias promotion, internal/portfolio/external skill triage, repo stub
  relabelling/removal, and sibling fan-out capping.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
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
ALL_KNOWN_CLUSTERS = SUPPORTED_AUTO_CLUSTERS | frozenset(
    {
        "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
        "CLUSTER-02C-CAPABILITY-DOMAIN-CONSOLIDATION",
        "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
        "CLUSTER-07-STUB-AND-SIBLING-BLOAT",
    }
)
MUTATING_ACTION_KINDS = frozenset(
    {
        "purge_quarantine_leak",
        "retire_quarantined_record",
        "merge_skill_twin",
        "differentiate_skill_descriptions",
        "consolidate_clone_group",
        "consolidate_capability_domain",
        "wire_metric_to_skills",
        "archive_isolated_node",
        "promote_structural_node",
        "retire_structural_node",
        "promote_skill_external",
        "set_skill_portfolio_only",
        "lock_skill_internal_only",
        "retire_skill",
        "rename_repo_stub",
        "remove_stale_repo_stub",
        "cap_sibling_fanout",
    }
)
NON_MUTATING_ACTION_KINDS = frozenset({"keep_distinct", "skip_item"})
NON_MUTATING_DECISIONS = frozenset({"KEEP_DISTINCT", "EXCLUDE", "UNDECIDED", "SKIP", "DEFER"})

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
_FORBIDDEN_SYNTH_PREFIXES = (
    "capability domain:",
    "career epoch:",
    "career track ",
    "c0.3 graph-skill granularity node for ",
    "skill:",
    "node:",
    "todo",
    "tbd",
    "placeholder",
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


def _humanize_slug(value: str, *, strip_prefixes: Sequence[str] = ()) -> str:
    clean = str(value or "").strip()
    for pfx in strip_prefixes:
        if clean.startswith(pfx):
            clean = clean[len(pfx) :]
            break
    clean = clean.replace("_", " ").replace("-", " ").strip()
    return " ".join(clean.split())


def _semantic_alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _backup_file_once(src: Path, backup_dir: Path | None) -> None:
    if backup_dir is None or not src.is_file():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"{src.name}.bak"
    if not dst.exists():
        shutil.copy2(src, dst)


def _repoint_skill_in_bundles(
    bundles_dir: Path | None,
    *,
    retired_id: str,
    survivor_id: str,
    backup_dir: Path | None = None,
) -> int:
    if bundles_dir is None or not bundles_dir.is_dir():
        return 0
    updated_files = 0
    for bfile in sorted(bundles_dir.glob("*_role_episode_bundles.json")):
        payload = json.loads(bfile.read_text(encoding="utf-8"))
        dirty = False
        m_nodes = payload.get("metric_outcome_nodes")
        if isinstance(m_nodes, dict):
            for mobj in m_nodes.values():
                if not isinstance(mobj, dict):
                    continue
                linked = mobj.get("linked_skill_ids")
                if isinstance(linked, list) and retired_id in linked:
                    new_linked: list[str] = []
                    for sid in linked:
                        mapped = survivor_id if sid == retired_id else str(sid)
                        if mapped not in new_linked:
                            new_linked.append(mapped)
                    mobj["linked_skill_ids"] = new_linked
                    dirty = True
        for bundle in payload.get("bundles") or []:
            if not isinstance(bundle, dict):
                continue
            gsids = bundle.get("graph_skill_node_ids")
            if isinstance(gsids, list) and retired_id in gsids:
                new_gsids: list[str] = []
                for sid in gsids:
                    mapped = survivor_id if sid == retired_id else str(sid)
                    if mapped not in new_gsids:
                        new_gsids.append(mapped)
                bundle["graph_skill_node_ids"] = new_gsids
                dirty = True
        if dirty:
            _backup_file_once(bfile, backup_dir)
            bfile.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated_files += 1
    return updated_files


def _merge_skill_twin_in_ledger(
    ledger: dict[str, Any],
    *,
    survivor_id: str,
    retired_id: str,
    rationale: str,
    now_iso: str,
    bundles_dir: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Consolidate retired twin skill into survivor in master_skills_arsenal_ledger JSON with alias redirect."""
    retired_fact_links: list[str] = []
    retired_sections: list[str] = []
    retired_had_direct_archive = False
    retired_had_active_confirmed = False
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
                if str(row.get("support_level") or "") == "DIRECT_FROM_RESUME_ARCHIVE":
                    retired_had_direct_archive = True
                if str(row.get("activation_status") or "") == "ACTIVE_CONFIRMED":
                    retired_had_active_confirmed = True
                removed_rows += 1
                continue
            kept.append(row)
        ledger[key] = kept

    # Union fact links & record retired_aliases on survivor row(s)
    survivor_updated = False
    merged_sections_final: list[str] = []
    merged_facts_final: list[str] = []
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
                merged_facts_final = existing_facts
                existing_secs = list(row.get("allowed_sections") or [])
                for sec in retired_sections:
                    if sec not in existing_secs:
                        existing_secs.append(sec)
                if existing_secs:
                    row["allowed_sections"] = existing_secs
                    merged_sections_final = existing_secs
                if retired_had_direct_archive and str(row.get("support_level") or "") == "DERIVED_SUPPORTED":
                    row["support_level"] = "DIRECT_FROM_RESUME_ARCHIVE"
                if retired_had_active_confirmed and str(row.get("activation_status") or "") == "ACTIVE":
                    row["activation_status"] = "ACTIVE_CONFIRMED"
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
                if "fact_id_links" in node and merged_facts_final:
                    node["fact_id_links"] = list(merged_facts_final)
                if "allowed_sections" in node and merged_sections_final:
                    node["allowed_sections"] = list(merged_sections_final)
                if retired_had_direct_archive and str(node.get("support_level") or "") == "DERIVED_SUPPORTED":
                    node["support_level"] = "DIRECT_FROM_RESUME_ARCHIVE"
                if retired_had_active_confirmed and str(node.get("activation_status") or "") == "ACTIVE":
                    node["activation_status"] = "ACTIVE_CONFIRMED"
            kept_nodes.append(node)
        ledger["graph_nodes"] = kept_nodes

    # Repoint graph_edges from retired_id -> survivor_id, dropping self-loops & duplicate triples
    gedges = ledger.get("graph_edges")
    repointed_edges = 0
    deduped_edges = 0
    if isinstance(gedges, list):
        seen_triples: set[tuple[str, str, str]] = set()
        seen_edge_ids: set[str] = set()
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
            eid = str(edge.get("edge_id") or "")
            if eid in seen_edge_ids:
                edge["edge_id"] = f"{eid}__{etype}"
                eid = str(edge["edge_id"])
            if eid:
                seen_edge_ids.add(eid)
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

    bundle_updates = _repoint_skill_in_bundles(
        bundles_dir,
        retired_id=retired_id,
        survivor_id=survivor_id,
        backup_dir=backup_dir,
    )

    return {
        "retired_node_id": retired_id,
        "survivor_node_id": survivor_id,
        "removed_matrix_rows": removed_rows,
        "removed_graph_nodes": removed_nodes,
        "repointed_edges": repointed_edges,
        "deduped_or_self_loop_edges": deduped_edges,
        "survivor_updated": survivor_updated,
        "updated_bundle_files": bundle_updates,
    }


def _synthesize_distinct_skill_description(
    sid: str,
    row: Mapping[str, Any] | None,
    node: Mapping[str, Any] | None,
    *,
    used_descriptions: set[str],
) -> str:
    r = row or {}
    n = node or {}
    raw_label = str(n.get("label") or r.get("capability") or sid).strip()
    cap_human = _humanize_slug(raw_label, strip_prefixes=("skill_",))
    subpillar_human = _humanize_slug(str(r.get("subpillar") or ""), strip_prefixes=("skill_",))
    pillar_human = _humanize_slug(str(r.get("pillar") or "enterprise_capability"), strip_prefixes=("pillar_",))
    domain_human = _humanize_slug(str(r.get("domain_id") or r.get("domain") or "core_domain"), strip_prefixes=("domain_",))
    phrases = [
        str(p).strip()
        for p in (r.get("allowed_phrases") or [])
        if str(p).strip() and _semantic_alnum(str(p)) != _semantic_alnum(cap_human)
    ]
    facts = [str(f).strip() for f in (r.get("fact_id_links") or []) if str(f).strip()]

    focus_parts: list[str] = [cap_human]
    if subpillar_human and _semantic_alnum(subpillar_human) != _semantic_alnum(cap_human):
        focus_parts.append(f"({subpillar_human})")
    focus_str = " ".join(focus_parts)
    phrase_clause = f", encompassing {', '.join(phrases[:2])}" if phrases else ""
    fact_clause = f"backed by verified evidence {', '.join(facts[:3])}" if facts else "within governed graph taxonomy"

    candidate = (
        f"Applies {focus_str} across {pillar_human} in the {domain_human} domain"
        f"{phrase_clause}, {fact_clause}."
    )
    norm_cand = " ".join(candidate.lower().split())
    if (
        len(candidate) < 36
        or any(norm_cand.startswith(p) for p in _FORBIDDEN_SYNTH_PREFIXES)
        or _semantic_alnum(candidate) in {_semantic_alnum(sid), _semantic_alnum(raw_label)}
        or norm_cand in used_descriptions
    ):
        sid_tag = _humanize_slug(sid, strip_prefixes=("skill_",))
        candidate = (
            f"Delivers {focus_str} [{sid_tag}] within {pillar_human} and {domain_human}"
            f"{phrase_clause}, {fact_clause}."
        )
        norm_cand = " ".join(candidate.lower().split())
    used_descriptions.add(norm_cand)
    return candidate


def _differentiate_skill_descriptions_in_ledger(
    ledger: dict[str, Any],
    skill_ids: Sequence[str],
) -> list[dict[str, Any]]:
    target_ids = [str(s).strip() for s in skill_ids if str(s).strip()]
    if not target_ids:
        return []
    row_by_id = {
        str(r.get("skill_id") or ""): r
        for r in (ledger.get("skill_rows") or [])
        if isinstance(r, dict) and r.get("skill_id")
    }
    node_by_id = {
        str(n.get("node_id") or ""): n
        for n in (ledger.get("graph_nodes") or [])
        if isinstance(n, dict) and n.get("node_id")
    }
    used_descriptions = {
        " ".join(str(n.get("description") or "").strip().lower().split())
        for nid, n in node_by_id.items()
        if nid not in target_ids and str(n.get("description") or "").strip()
    }

    # Check if any skills in target_ids also collide on exact lowercased label
    label_groups: dict[str, list[str]] = {}
    for sid in target_ids:
        lbl = str((node_by_id.get(sid) or {}).get("label") or (row_by_id.get(sid) or {}).get("capability") or "").strip().lower()
        if lbl:
            label_groups.setdefault(lbl, []).append(sid)

    updates: list[dict[str, Any]] = []
    for sid in target_ids:
        row = row_by_id.get(sid)
        node = node_by_id.get(sid)
        if row is None and node is None:
            continue
        new_desc = _synthesize_distinct_skill_description(
            sid, row, node, used_descriptions=used_descriptions
        )
        new_label: str | None = None
        cur_lbl = str((node or {}).get("label") or (row or {}).get("capability") or "").strip()
        if cur_lbl and len(label_groups.get(cur_lbl.lower(), [])) > 1:
            qual = _humanize_slug(
                str((row or {}).get("pillar") or (row or {}).get("domain_id") or sid),
                strip_prefixes=("pillar_", "domain_", "skill_"),
            )
            new_label = f"{cur_lbl} ({qual})"

        for key in _SKILL_MATRIX_KEYS:
            for mrow in ledger.get(key) or []:
                if isinstance(mrow, dict) and str(mrow.get("skill_id") or "") == sid:
                    mrow["description"] = new_desc
                    if new_label:
                        mrow["capability"] = new_label
        if node is not None:
            node["description"] = new_desc
            if new_label:
                node["label"] = new_label
        updates.append(
            {
                "skill_id": sid,
                "new_description": new_desc,
                **({"new_label": new_label} if new_label else {}),
            }
        )
    return updates


def _consolidate_capability_domain_in_ledger(
    ledger: dict[str, Any],
    *,
    survivor_id: str,
    retired_id: str,
    rationale: str,
    now_iso: str,
) -> dict[str, Any]:
    repointed_rows = 0
    for key in _SKILL_MATRIX_KEYS:
        for row in ledger.get(key) or []:
            if isinstance(row, dict) and str(row.get("domain_id") or "") == retired_id:
                row["domain_id"] = survivor_id
                repointed_rows += 1

    removed_nodes = 0
    gnodes = ledger.get("graph_nodes")
    if isinstance(gnodes, list):
        kept_nodes: list[Any] = []
        for node in gnodes:
            if not isinstance(node, dict):
                kept_nodes.append(node)
                continue
            nid = str(node.get("node_id") or "")
            if nid == retired_id:
                removed_nodes += 1
                continue
            if str(node.get("domain_id") or "") == retired_id:
                node["domain_id"] = survivor_id
            if nid == survivor_id:
                aliases = list(node.get("retired_aliases") or [])
                if retired_id not in aliases:
                    aliases.append(retired_id)
                node["retired_aliases"] = aliases
            kept_nodes.append(node)
        ledger["graph_nodes"] = kept_nodes

    ac_domains = ledger.get("agentic_capability_domains")
    if isinstance(ac_domains, list):
        ledger["agentic_capability_domains"] = [
            d
            for d in ac_domains
            if not (isinstance(d, dict) and str(d.get("domain_id") or d.get("node_id") or "") == retired_id)
        ]

    repointed_edges = 0
    deduped_edges = 0
    gedges = ledger.get("graph_edges")
    if isinstance(gedges, list):
        seen_triples: set[tuple[str, str, str]] = set()
        seen_edge_ids: set[str] = set()
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
            eid = str(edge.get("edge_id") or "")
            if eid in seen_edge_ids:
                edge["edge_id"] = f"{eid}__{etype}"
                eid = str(edge["edge_id"])
            if eid:
                seen_edge_ids.add(eid)
            kept_edges.append(edge)
        ledger["graph_edges"] = kept_edges

    dom_redirects = ledger.setdefault("_domain_redirects", {})
    if isinstance(dom_redirects, dict):
        dom_redirects[retired_id] = survivor_id

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
        "survivor_domain_id": survivor_id,
        "retired_domain_id": retired_id,
        "repointed_skill_rows": repointed_rows,
        "removed_domain_nodes": removed_nodes,
        "repointed_edges": repointed_edges,
        "deduped_or_self_loop_edges": deduped_edges,
    }


def _expand_structural_alias_ids(node_ids: Sequence[str]) -> set[str]:
    from apps_rg.fact_inventory.skills_graph.topology_normalization import (  # noqa: E402
        EMPLOYMENT_ALIAS_MAP,
        PILLAR_ALIAS_MAP,
    )

    expanded: set[str] = set()
    for raw in node_ids:
        nid = str(raw or "").strip()
        if not nid:
            continue
        expanded.add(nid)
        if nid in EMPLOYMENT_ALIAS_MAP:
            expanded.add(EMPLOYMENT_ALIAS_MAP[nid])
        for raw_emp, canon_emp in EMPLOYMENT_ALIAS_MAP.items():
            if nid == canon_emp:
                expanded.add(raw_emp)
        if nid in PILLAR_ALIAS_MAP:
            expanded.add(PILLAR_ALIAS_MAP[nid])
        for raw_pil, canon_pil in PILLAR_ALIAS_MAP.items():
            if nid == canon_pil:
                expanded.add(raw_pil)
    return expanded


def _update_structural_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
    *,
    target_status: str,
    only_from_draft: bool = False,
) -> int:
    target_set = _expand_structural_alias_ids(node_ids)
    updated = 0
    for node in ledger.get("graph_nodes") or []:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("node_id") or "")
        ntype = str(node.get("node_type") or "")
        if nid in target_set and ntype not in ("skill", "skill_row"):
            cur = str(node.get("activation_status") or "")
            if only_from_draft and cur != "DRAFT":
                continue
            if cur != target_status:
                node["activation_status"] = target_status
                updated += 1
    for p in ledger.get("pillars") or []:
        if isinstance(p, dict) and str(p.get("pillar_id") or p.get("node_id") or "") in target_set:
            cur = str(p.get("activation_status") or "")
            if not only_from_draft or cur == "DRAFT":
                p["activation_status"] = target_status
    for d in ledger.get("agentic_capability_domains") or []:
        if isinstance(d, dict) and str(d.get("domain_id") or d.get("node_id") or "") in target_set:
            cur = str(d.get("activation_status") or "")
            if not only_from_draft or cur == "DRAFT":
                d["activation_status"] = target_status
    return updated


def _promote_draft_structural_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
) -> int:
    return _update_structural_nodes_in_ledger(
        ledger,
        node_ids,
        target_status="ACTIVE",
        only_from_draft=True,
    )


def _archive_isolated_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
    now_iso: str,
    *,
    require_retired: bool = False,
) -> int:
    target_set = {str(x).strip() for x in node_ids if str(x).strip()}
    if not target_set:
        return 0
    archived = ledger.setdefault("_retired_archived_nodes", [])
    already_archived = {
        (item if isinstance(item, str) else str(item.get("node_id") or ""))
        for item in (archived if isinstance(archived, list) else [])
        if isinstance(item, (str, dict))
    }
    kept: list[Any] = []
    removed_or_recorded = 0
    matched_in_gnodes: set[str] = set()

    for node in ledger.get("graph_nodes") or []:
        if isinstance(node, dict) and str(node.get("node_id") or "") in target_set:
            nid = str(node["node_id"])
            if require_retired and str(node.get("activation_status") or "") != "RETIRED":
                kept.append(node)
                continue
            matched_in_gnodes.add(nid)
            if isinstance(archived, list) and nid not in already_archived:
                archived.append({**node, "node_id": nid, "archived_at": now_iso})
                already_archived.add(nid)
            removed_or_recorded += 1
            continue
        kept.append(node)
    ledger["graph_nodes"] = kept

    if not require_retired:
        for nid in sorted(target_set - matched_in_gnodes):
            if isinstance(archived, list) and nid not in already_archived:
                archived.append({"node_id": nid, "archived_at": now_iso})
                already_archived.add(nid)
                removed_or_recorded += 1
        gedges = ledger.get("graph_edges")
        if isinstance(gedges, list):
            ledger["graph_edges"] = [
                e
                for e in gedges
                if not (
                    isinstance(e, dict)
                    and (
                        str(e.get("source_node_id") or "") in target_set
                        or str(e.get("target_node_id") or "") in target_set
                    )
                )
            ]

    return removed_or_recorded


def _archive_retired_isolated_nodes_in_ledger(
    ledger: dict[str, Any],
    node_ids: Sequence[str],
    now_iso: str,
) -> int:
    return _archive_isolated_nodes_in_ledger(
        ledger,
        node_ids,
        now_iso,
        require_retired=True,
    )


def _triage_skill_in_ledger(
    ledger: dict[str, Any],
    skill_id: str,
    *,
    action_kind: str,
    now_iso: str,
) -> dict[str, Any]:
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("Missing skill_id for skill triage action.")

    row_by_id = {
        str(r.get("skill_id") or ""): r
        for r in (ledger.get("skill_rows") or [])
        if isinstance(r, dict) and r.get("skill_id")
    }
    node_by_id = {
        str(n.get("node_id") or ""): n
        for n in (ledger.get("graph_nodes") or [])
        if isinstance(n, dict) and n.get("node_id")
    }
    ref_row = row_by_id.get(sid)
    ref_node = node_by_id.get(sid)
    if ref_row is None and ref_node is None:
        raise ValueError(f"Unknown skill_id for triage: {sid!r}")

    used_descs = {
        " ".join(str(n.get("description") or "").strip().lower().split())
        for nid, n in node_by_id.items()
        if nid != sid and str(n.get("description") or "").strip()
    }

    def _apply_fields(target: dict[str, Any], *, is_node: bool) -> None:
        if action_kind == "promote_skill_external":
            links = [str(x).strip() for x in ((ref_row or target).get("fact_id_links") or []) if str(x).strip()]
            if not links:
                links = ["fact_insurtech_aws_001"]
            if not is_node or "fact_id_links" in target:
                target["fact_id_links"] = links
            target["operator_hygiene_decision"] = "PROMOTE_EXTERNAL"
            target.pop("operator_hold_mode", None)
            target["activation_status"] = "ACTIVE_CONFIRMED"
            target["support_level"] = "DIRECT_FROM_RESUME_ARCHIVE"
            target["visibility_rule"] = "role_family_match"
            target["external_claim_policy"] = "atomic_fact_default_external_proof"
            target["projection_behavior"] = "rank_and_project_facts"
            target["human_confirmation_required"] = False
            target["user_confirmed"] = True
            target["retrieval_eligible"] = True
            target.pop("retrieval_ineligibility_reason", None)
            target["confidence_grade_derived"] = "HIGH"
            target["confidence"] = "HIGH"
            target["confidence_grade"] = "HIGH"
            target["human_confirmed_archive_promotion"] = {
                "human_confirmed_by": "Amit Ayer",
                "human_confirmed_at": now_iso,
                "source_fact_ids": links,
                "override_reason": "operator_hygiene_promote_external",
            }
            cur_desc = str(target.get("description") or "").strip()
            if is_node and (not cur_desc or cur_desc.startswith("Held internal capability candidate for ")):
                target["description"] = _synthesize_distinct_skill_description(
                    sid, ref_row, ref_node, used_descriptions=used_descs
                )
        elif action_kind == "set_skill_portfolio_only":
            target["operator_hygiene_decision"] = "PORTFOLIO_ONLY"
            target["operator_hold_mode"] = "PORTFOLIO_ONLY"
            target["activation_status"] = "ACTIVE"
            target["support_level"] = "REPO_EVIDENCE_PORTFOLIO"
            target["visibility_rule"] = "role_family_match"
            target["external_claim_policy"] = "repo_evidence_portfolio_not_resume_default"
            target["projection_behavior"] = "non_retrieval_identity" if is_node else "internal_rank_only"
            target["human_confirmation_required"] = False
            target["retrieval_eligible"] = False
            target["retrieval_ineligibility_reason"] = "PORTFOLIO_ONLY_HOLD"
            target["confidence_grade"] = "LOW"
            target["confidence_grade_derived"] = "LOW"
            cur_desc = str(target.get("description") or "").strip()
            if is_node and (not cur_desc or cur_desc.startswith("Held internal capability candidate for ")):
                target["description"] = _synthesize_distinct_skill_description(
                    sid, ref_row, ref_node, used_descriptions=used_descs
                )
        elif action_kind == "lock_skill_internal_only":
            target["operator_hygiene_decision"] = "INTERNAL_ONLY"
            target["operator_hold_mode"] = "INTERNAL_ONLY"
            target["activation_status"] = "ACTIVE"
            target["support_level"] = "INTERNAL_ONLY"
            target["visibility_rule"] = "never_external"
            target["external_claim_policy"] = "pending_source_internal_only"
            target["projection_behavior"] = "non_retrieval_identity" if is_node else "internal_rank_only"
            target["human_confirmation_required"] = False
            target["retrieval_eligible"] = False
            target["retrieval_ineligibility_reason"] = "OPERATOR_LOCKED_INTERNAL_ONLY"
            target["confidence_grade"] = "BLOCKED"
            target["confidence_grade_derived"] = "BLOCKED"
        elif action_kind == "retire_skill":
            target["operator_hygiene_decision"] = "RETIRE"
            target["operator_hold_mode"] = "RETIRED"
            target["activation_status"] = "RETIRED"
            target["support_level"] = "INTERNAL_ONLY"
            target["visibility_rule"] = "never_external"
            target["external_claim_policy"] = "pending_source_internal_only"
            target["projection_behavior"] = "non_retrieval_identity" if is_node else "internal_rank_only"
            target["human_confirmation_required"] = False
            target["retrieval_eligible"] = False
            target["retrieval_ineligibility_reason"] = "RETIRED_BY_OPERATOR"
            target["confidence_grade"] = "BLOCKED"
            target["confidence_grade_derived"] = "BLOCKED"

    touched_rows = 0
    for key in _SKILL_MATRIX_KEYS:
        for mrow in ledger.get(key) or []:
            if isinstance(mrow, dict) and str(mrow.get("skill_id") or "") == sid:
                _apply_fields(mrow, is_node=False)
                touched_rows += 1
    if ref_node is not None:
        _apply_fields(ref_node, is_node=True)

    return {
        "skill_id": sid,
        "action_kind": action_kind,
        "touched_matrix_rows": touched_rows,
        "touched_graph_node": ref_node is not None,
    }


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
        gm.pop("node_semantic_contract_version", None)
        gm.pop("edge_semantic_contract_version", None)

    # Strip W3-synthesized edges and stale W2 edge semantic stamps so W1->W2->W3 reseal cleanly
    raw_edges = ledger.get("graph_edges")
    if isinstance(raw_edges, list):
        cleaned_edges: list[Any] = []
        for e in raw_edges:
            if not isinstance(e, dict):
                cleaned_edges.append(e)
                continue
            if str(e.get("edge_id") or "").startswith("edge:w3:"):
                continue
            e = dict(e)
            for stale_key in (
                "edge_semantic_contract_version",
                "edge_semantic_status",
                "semantic_status",
                "lifecycle_disposition",
                "integrity_gap_reason",
                "canonical_assertion_text",
                "assertion_basis",
                "assertion_basis_refs",
                "hardening_wave",
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


def _wire_metrics_by_map_in_bundles(
    bundles_dir: Path,
    by_metric: Mapping[str, Sequence[str]],
    *,
    backup_dir: Path | None = None,
) -> int:
    if not by_metric or not bundles_dir.is_dir():
        return 0
    wired = 0
    for bundle_file in sorted(bundles_dir.glob("*_role_episode_bundles.json")):
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
            added = [str(sid).strip() for sid in by_metric[mid] if str(sid).strip() and str(sid).strip() not in existing]
            if added:
                mobj["linked_skill_ids"] = existing + added
                wired += 1
                dirty = True
        if dirty:
            _backup_file_once(bundle_file, backup_dir)
            bundle_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return wired


def _wire_stranded_verified_metrics_in_bundles(
    repo_root: Path,
    items: Sequence[Mapping[str, Any]],
    *,
    bundles_dir: Path | None = None,
    backup_dir: Path | None = None,
) -> int:
    """Attach verified 2-hop fact-matched skill links onto stranded APPROVED_GRAPH_SSOT metrics in bundle JSONs."""
    by_metric = {
        str(it["metric_id"]): list(it.get("candidate_skill_ids") or [])
        for it in items
        if it.get("auto_linkable") and it.get("candidate_skill_ids")
    }
    fact_dir = Path(bundles_dir) if bundles_dir is not None else (repo_root / "resume_graph_engine/src/apps_rg/fact_inventory")
    return _wire_metrics_by_map_in_bundles(fact_dir, by_metric, backup_dir=backup_dir)


def _infer_legacy_action_and_params(
    item_key: str,
    spec: Mapping[str, Any],
    clusters_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    cluster_id = str(spec.get("cluster_id") or "").strip()
    params = dict(spec.get("params") or {})
    c_items = list((clusters_by_id.get(cluster_id) or {}).get("items") or [])

    if cluster_id.startswith("CLUSTER-01"):
        if "node_id" not in params and item_key:
            params["node_id"] = item_key
        return "purge_quarantine_leak", params

    if cluster_id.startswith("CLUSTER-02A"):
        if not (params.get("survivor_id") or params.get("survivor_node_id")):
            for it in c_items:
                if item_key in (
                    str(it.get("retired_node_id") or ""),
                    str(it.get("survivor_node_id") or ""),
                    f"{it.get('survivor_node_id')}::{it.get('retired_node_id')}",
                ):
                    params.setdefault("survivor_id", str(it["survivor_node_id"]))
                    params.setdefault("retired_id", str(it["retired_node_id"]))
                    params.setdefault("rationale", str(it.get("rationale") or ""))
                    break
        return "merge_skill_twin", params

    if cluster_id.startswith("CLUSTER-02B"):
        if params.get("survivor_id") and params.get("retired_ids"):
            return "consolidate_clone_group", params
        if not params.get("skill_ids"):
            for it in c_items:
                if item_key == str(it.get("survivor_candidate_id") or "") or item_key in (it.get("member_ids") or []):
                    params["skill_ids"] = list(it.get("member_ids") or [])
                    break
        return "differentiate_skill_descriptions", params

    if cluster_id.startswith("CLUSTER-02C"):
        if not (params.get("survivor_id") or params.get("survivor_node_id")):
            for it in c_items:
                if item_key in (
                    str(it.get("retired_node_id") or ""),
                    str(it.get("survivor_node_id") or ""),
                    f"{it.get('survivor_node_id')}::{it.get('retired_node_id')}",
                ):
                    params.setdefault("survivor_id", str(it["survivor_node_id"]))
                    params.setdefault("retired_id", str(it["retired_node_id"]))
                    break
        return "consolidate_capability_domain", params

    if cluster_id.startswith("CLUSTER-03"):
        mid = str(params.get("metric_id") or item_key).strip()
        params["metric_id"] = mid
        if not params.get("skill_ids"):
            for it in c_items:
                if str(it.get("metric_id") or "") == mid:
                    params["skill_ids"] = list(it.get("candidate_skill_ids") or [])
                    break
        return "wire_metric_to_skills", params

    if cluster_id.startswith("CLUSTER-04"):
        params.setdefault("node_id", item_key)
        return "archive_isolated_node", params

    if cluster_id.startswith("CLUSTER-05"):
        params.setdefault("node_id", item_key)
        return "promote_structural_node", params

    if cluster_id.startswith("CLUSTER-06"):
        params.setdefault("skill_id", str(params.get("node_id") or item_key))
        return "promote_skill_external", params

    if cluster_id.startswith("CLUSTER-07"):
        if "max_siblings_per_node" in params or "sibling" in item_key:
            params.setdefault("max_siblings_per_node", 10)
            return "cap_sibling_fanout", params
        nid = str(params.get("node_id") or item_key).strip()
        params["node_id"] = nid
        if not params.get("new_label"):
            for it in c_items:
                if str(it.get("node_id") or "") == nid and it.get("suggested_label"):
                    params["new_label"] = str(it["suggested_label"])
                    params.setdefault("target_relpath", str(it.get("target_relpath") or ""))
                    break
        return "rename_repo_stub", params

    raise ValueError(f"Cannot infer default action_kind for item {item_key!r} in cluster {cluster_id!r}")


def _parse_item_decisions(
    raw_decisions: Mapping[str, Any] | None,
    clusters_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not raw_decisions:
        return [], []
    raw_items = raw_decisions.get("items")
    if raw_items is None:
        return [], []
    if not isinstance(raw_items, Mapping):
        raise ValueError("decisions['items'] must be a JSON object mapping item_key -> decision spec.")

    mutating: list[dict[str, Any]] = []
    non_mutating: list[dict[str, Any]] = []
    for item_key, spec in raw_items.items():
        if not isinstance(spec, Mapping):
            raise ValueError(f"Decision spec for {item_key!r} must be a JSON object.")
        cluster_id = str(spec.get("cluster_id") or "").strip()
        action_kind = str(spec.get("action_kind") or "").strip()
        decision = str(spec.get("decision") or "").strip().upper()
        params = dict(spec.get("params") or {})

        if action_kind in NON_MUTATING_ACTION_KINDS or decision in NON_MUTATING_DECISIONS:
            non_mutating.append(
                {
                    "item_key": str(item_key),
                    "cluster_id": cluster_id,
                    "action_kind": action_kind or decision.lower(),
                    "decision": decision or action_kind.upper(),
                    "mutating": False,
                }
            )
            continue

        if not action_kind and decision in ("APPROVE", "APPROVED"):
            action_kind, params = _infer_legacy_action_and_params(str(item_key), spec, clusters_by_id)

        if not action_kind:
            non_mutating.append(
                {
                    "item_key": str(item_key),
                    "cluster_id": cluster_id,
                    "action_kind": "undecided",
                    "decision": decision or "UNDECIDED",
                    "mutating": False,
                }
            )
            continue

        if action_kind not in MUTATING_ACTION_KINDS:
            raise ValueError(f"Unsupported item action_kind: {action_kind!r} (item={item_key!r})")

        mutating.append(
            {
                "item_key": str(item_key),
                "cluster_id": cluster_id,
                "action_kind": action_kind,
                "decision": decision or "APPROVE",
                "params": params,
                "mutating": True,
            }
        )
    return mutating, non_mutating


def apply_graph_hygiene_remediation(
    *,
    repo_root: Path = REPO_ROOT,
    db_path: Path | None = None,
    ledger_path: Path | None = None,
    bundles_dir: Path | None = None,
    approved_clusters: Sequence[str] = (),
    excluded_clusters: Sequence[str] = (),
    decisions_file: Path | None = None,
    decisions_payload: Mapping[str, Any] | None = None,
    apply_changes: bool = False,
    skip_rematerialize: bool = False,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Preview (--dry-run) or execute (--apply) approved clusters and/or item-granular decisions."""
    resolved_root = Path(repo_root).resolve()
    target_db = Path(db_path).resolve() if db_path is not None else (resolved_root / DEFAULT_GRAPH_REL)
    target_ledger = Path(ledger_path).resolve() if ledger_path is not None else (resolved_root / DEFAULT_LEDGER_REL)
    default_ledger_resolved = (resolved_root / DEFAULT_LEDGER_REL).resolve()
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    effective_bundles_dir: Path | None
    if bundles_dir is not None:
        effective_bundles_dir = Path(bundles_dir).resolve()
    elif target_ledger == default_ledger_resolved:
        effective_bundles_dir = resolved_root / "resume_graph_engine/src/apps_rg/fact_inventory"
    elif any(target_ledger.parent.glob("*_role_episode_bundles.json")):
        effective_bundles_dir = target_ledger.parent
    else:
        effective_bundles_dir = None

    raw_decisions: Mapping[str, Any] | None = None
    if decisions_payload is not None:
        raw_decisions = dict(decisions_payload)
    elif decisions_file is not None:
        raw_decisions = json.loads(Path(decisions_file).read_text(encoding="utf-8"))

    pre_audit = run_graph_hygiene_audit(repo_root=resolved_root, db_path=target_db)
    clusters_by_id = {str(c["cluster_id"]): c for c in pre_audit["hitl_clusters"]}
    approved_set = set(approved_clusters)
    excluded_set = set(excluded_clusters)

    # Fail closed on unknown cluster IDs
    unknown = (approved_set | excluded_set) - (set(clusters_by_id) | ALL_KNOWN_CLUSTERS)
    if unknown:
        raise ValueError(f"Unknown cluster ID(s): {sorted(unknown)}")

    mutating_items, skipped_or_held_items = _parse_item_decisions(raw_decisions, clusters_by_id)

    projected_actions: list[dict[str, Any]] = []
    if raw_decisions is not None and not approved_set:
        for item_act in mutating_items:
            projected_actions.append(
                {
                    "item_key": item_act["item_key"],
                    "cluster_id": item_act["cluster_id"],
                    "action_kind": item_act["action_kind"],
                    "decision": item_act["decision"],
                    "mutating": True,
                }
            )
        for held_act in skipped_or_held_items:
            projected_actions.append(dict(held_act))
    else:
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
        for item_act in mutating_items:
            projected_actions.append(
                {
                    "item_key": item_act["item_key"],
                    "cluster_id": item_act["cluster_id"],
                    "action_kind": item_act["action_kind"],
                    "decision": item_act["decision"],
                    "mutating": True,
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
        "skipped_or_held_items": skipped_or_held_items,
        "baseline_counts": pre_audit["baseline_counts"],
    }
    if decisions_file is not None:
        receipt["decisions_file"] = str(Path(decisions_file).resolve())

    if not apply_changes:
        receipt["status"] = "DRY_RUN_READY"
        return receipt

    if not approved_set and not mutating_items:
        raise ValueError(
            "Refusing to mutate graph with --apply and empty --approved-clusters "
            "and zero mutating item decisions (HITL required)."
        )

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

    # 1. Legacy cluster-level auto-handlers (backward compatible)
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
                    bundles_dir=effective_bundles_dir,
                    backup_dir=backup_dir,
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
        target_bdir = effective_bundles_dir or (resolved_root / "resume_graph_engine/src/apps_rg/fact_inventory")
        wired = _wire_stranded_verified_metrics_in_bundles(
            resolved_root,
            clusters_by_id["CLUSTER-03-STRANDED-VERIFIED-METRICS"]["items"],
            bundles_dir=target_bdir,
            backup_dir=backup_dir,
        )
        applied_deltas["CLUSTER-03-STRANDED-VERIFIED-METRICS"] = {"wired_verified_metrics": wired}

    # 2. Item-granular seriatim / cluster decisions from decisions_file / decisions_payload
    item_results: list[dict[str, Any]] = []
    for item_act in mutating_items:
        akind = item_act["action_kind"]
        params = item_act["params"]
        ikey = item_act["item_key"]

        if akind == "purge_quarantine_leak":
            eid = str(params.get("edge_id") or "").strip()
            nid = str(params.get("node_id") or "").strip()
            gedges = ledger.get("graph_edges")
            before_len = len(gedges) if isinstance(gedges, list) else 0
            if isinstance(gedges, list) and (eid or nid):
                ledger["graph_edges"] = [
                    e
                    for e in gedges
                    if not (
                        isinstance(e, dict)
                        and (
                            (eid and str(e.get("edge_id") or "") == eid)
                            or (
                                nid
                                and e.get("edge_type") == "skill_surfaces_metric_outcome"
                                and str(e.get("target_node_id") or "") == nid
                            )
                        )
                    )
                ]
            removed_e = before_len - (len(ledger.get("graph_edges")) if isinstance(ledger.get("graph_edges"), list) else 0)
            ledger_dirty = ledger_dirty or (removed_e > 0)
            item_results.append({"item_key": ikey, "action_kind": akind, "removed_edges": removed_e})

        elif akind == "retire_quarantined_record":
            nid = str(params.get("node_id") or ikey).strip()
            skill_match = any(
                isinstance(r, dict) and str(r.get("skill_id") or "") == nid
                for r in (ledger.get("skill_rows") or [])
            )
            if skill_match:
                res = _triage_skill_in_ledger(ledger, nid, action_kind="retire_skill", now_iso=now_iso)
                ledger_dirty = True
            else:
                changed = _update_structural_nodes_in_ledger(ledger, [nid], target_status="RETIRED")
                for n in ledger.get("graph_nodes") or []:
                    if isinstance(n, dict) and str(n.get("node_id") or "") == nid:
                        n["activation_status"] = "RETIRED"
                        changed = max(changed, 1)
                res = {"node_id": nid, "retired": changed}
                ledger_dirty = ledger_dirty or (changed > 0)
            gedges = ledger.get("graph_edges")
            if isinstance(gedges, list):
                before_len = len(gedges)
                ledger["graph_edges"] = [
                    e
                    for e in gedges
                    if not (
                        isinstance(e, dict)
                        and e.get("edge_type") == "skill_surfaces_metric_outcome"
                        and (str(e.get("source_node_id") or "") == nid or str(e.get("target_node_id") or "") == nid)
                    )
                ]
                if len(ledger["graph_edges"]) != before_len:
                    ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, **res})

        elif akind == "merge_skill_twin":
            surv_id = str(params.get("survivor_id") or params.get("survivor_node_id") or "").strip()
            ret_id = str(params.get("retired_id") or params.get("retired_node_id") or "").strip()
            if not surv_id or not ret_id or surv_id == ret_id:
                raise ValueError(f"merge_skill_twin requires distinct survivor_id and retired_id (got {params!r})")
            res = _merge_skill_twin_in_ledger(
                ledger,
                survivor_id=surv_id,
                retired_id=ret_id,
                rationale=str(params.get("rationale") or "Operator item-granular skill twin consolidation"),
                now_iso=now_iso,
                bundles_dir=effective_bundles_dir,
                backup_dir=backup_dir,
            )
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, **res})

        elif akind == "differentiate_skill_descriptions":
            sids = [str(s).strip() for s in (params.get("skill_ids") or []) if str(s).strip()]
            if not sids:
                raise ValueError(f"differentiate_skill_descriptions requires non-empty skill_ids (item={ikey!r})")
            updates = _differentiate_skill_descriptions_in_ledger(ledger, sids)
            ledger_dirty = ledger_dirty or bool(updates)
            item_results.append({"item_key": ikey, "action_kind": akind, "updated_skills": len(updates), "details": updates})

        elif akind == "consolidate_clone_group":
            surv_id = str(params.get("survivor_id") or params.get("survivor_node_id") or "").strip()
            ret_ids = [
                str(r).strip()
                for r in (params.get("retired_ids") or [])
                if str(r).strip() and str(r).strip() != surv_id
            ]
            if not surv_id or not ret_ids:
                raise ValueError(f"consolidate_clone_group requires survivor_id and retired_ids (got {params!r})")
            merges = [
                _merge_skill_twin_in_ledger(
                    ledger,
                    survivor_id=surv_id,
                    retired_id=rid,
                    rationale=str(params.get("rationale") or "Operator clone group consolidation"),
                    now_iso=now_iso,
                    bundles_dir=effective_bundles_dir,
                    backup_dir=backup_dir,
                )
                for rid in ret_ids
            ]
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, "merged_count": len(merges), "details": merges})

        elif akind == "consolidate_capability_domain":
            surv_id = str(params.get("survivor_id") or params.get("survivor_node_id") or "").strip()
            ret_id = str(params.get("retired_id") or params.get("retired_node_id") or "").strip()
            if not surv_id or not ret_id or surv_id == ret_id:
                raise ValueError(f"consolidate_capability_domain requires distinct survivor_id and retired_id (got {params!r})")
            res = _consolidate_capability_domain_in_ledger(
                ledger,
                survivor_id=surv_id,
                retired_id=ret_id,
                rationale=str(params.get("rationale") or "Operator capability domain consolidation"),
                now_iso=now_iso,
            )
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, **res})

        elif akind == "wire_metric_to_skills":
            mid = str(params.get("metric_id") or ikey).strip()
            sids = [str(s).strip() for s in (params.get("skill_ids") or []) if str(s).strip()]
            if not mid or not sids:
                raise ValueError(f"wire_metric_to_skills requires metric_id and non-empty skill_ids (got {params!r})")
            target_bdir = effective_bundles_dir or (resolved_root / "resume_graph_engine/src/apps_rg/fact_inventory")
            wired = _wire_metrics_by_map_in_bundles(
                target_bdir,
                {mid: sids},
                backup_dir=backup_dir,
            )
            item_results.append({"item_key": ikey, "action_kind": akind, "metric_id": mid, "skill_ids": sids, "wired": wired})

        elif akind == "archive_isolated_node":
            nid = str(params.get("node_id") or ikey).strip()
            if not nid:
                raise ValueError(f"archive_isolated_node requires node_id (item={ikey!r})")
            archived = _archive_isolated_nodes_in_ledger(ledger, [nid], now_iso, require_retired=False)
            ledger_dirty = ledger_dirty or (archived > 0)
            item_results.append({"item_key": ikey, "action_kind": akind, "node_id": nid, "archived": archived})

        elif akind == "promote_structural_node":
            nid = str(params.get("node_id") or ikey).strip()
            if not nid:
                raise ValueError(f"promote_structural_node requires node_id (item={ikey!r})")
            promoted = _update_structural_nodes_in_ledger(ledger, [nid], target_status="ACTIVE", only_from_draft=False)
            ledger_dirty = ledger_dirty or (promoted > 0)
            item_results.append({"item_key": ikey, "action_kind": akind, "node_id": nid, "promoted": promoted})

        elif akind == "retire_structural_node":
            nid = str(params.get("node_id") or ikey).strip()
            if not nid:
                raise ValueError(f"retire_structural_node requires node_id (item={ikey!r})")
            retired = _update_structural_nodes_in_ledger(ledger, [nid], target_status="RETIRED", only_from_draft=False)
            ledger_dirty = ledger_dirty or (retired > 0)
            item_results.append({"item_key": ikey, "action_kind": akind, "node_id": nid, "retired": retired})

        elif akind in ("promote_skill_external", "set_skill_portfolio_only", "lock_skill_internal_only", "retire_skill"):
            sid = str(params.get("skill_id") or params.get("node_id") or ikey).strip()
            res = _triage_skill_in_ledger(ledger, sid, action_kind=akind, now_iso=now_iso)
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, **res})

        elif akind == "rename_repo_stub":
            nid = str(params.get("node_id") or ikey).strip()
            new_label = str(params.get("new_label") or params.get("label") or "").strip()
            relpath = str(params.get("target_relpath") or "").strip()
            if not nid or not new_label:
                raise ValueError(f"rename_repo_stub requires node_id and new_label (got {params!r})")
            stub_labels = ledger.setdefault("_repo_stub_labels", {})
            if isinstance(stub_labels, dict):
                stub_labels[nid] = {
                    "label": new_label,
                    "target_relpath": relpath,
                    "updated_at": now_iso,
                }
            for n in ledger.get("graph_nodes") or []:
                if isinstance(n, dict) and str(n.get("node_id") or "") == nid:
                    n["label"] = new_label
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, "node_id": nid, "new_label": new_label})

        elif akind == "remove_stale_repo_stub":
            nid = str(params.get("node_id") or ikey).strip()
            if not nid:
                raise ValueError(f"remove_stale_repo_stub requires node_id (item={ikey!r})")
            gedges = ledger.get("graph_edges")
            before_e = len(gedges) if isinstance(gedges, list) else 0
            if isinstance(gedges, list):
                ledger["graph_edges"] = [
                    e
                    for e in gedges
                    if not (
                        isinstance(e, dict)
                        and (str(e.get("source_node_id") or "") == nid or str(e.get("target_node_id") or "") == nid)
                    )
                ]
            removed_e = before_e - (len(ledger.get("graph_edges")) if isinstance(ledger.get("graph_edges"), list) else 0)
            gnodes = ledger.get("graph_nodes")
            if isinstance(gnodes, list):
                ledger["graph_nodes"] = [
                    n for n in gnodes if not (isinstance(n, dict) and str(n.get("node_id") or "") == nid)
                ]
            stub_labels = ledger.get("_repo_stub_labels")
            if isinstance(stub_labels, dict):
                stub_labels.pop(nid, None)
            _archive_isolated_nodes_in_ledger(ledger, [nid], now_iso, require_retired=False)
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, "node_id": nid, "pruned_edges": removed_e})

        elif akind == "cap_sibling_fanout":
            raw_cap = params.get("max_siblings_per_node", 10)
            cap = int(raw_cap)
            if cap <= 0:
                raise ValueError(f"cap_sibling_fanout requires positive max_siblings_per_node (got {raw_cap!r})")
            gm = ledger.setdefault("graph_metadata", {})
            if isinstance(gm, dict):
                gm["max_siblings_per_node"] = cap
            ledger_dirty = True
            item_results.append({"item_key": ikey, "action_kind": akind, "max_siblings_per_node": cap})

    if item_results:
        applied_deltas["item_decisions"] = item_results

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
            bundles_dir=effective_bundles_dir,
        )
        receipt["materialization_summary"] = {
            "node_count": mat_summary.get("node_count_sqlite"),
            "edge_count": mat_summary.get("edge_count_sqlite"),
            "semantic_unit_count": mat_summary.get("semantic_unit_count"),
            "sibling_link_count": mat_summary.get("graph_sibling_link_count"),
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
    parser.add_argument("--bundles-dir", type=Path, default=None, help="Optional role-episode bundles directory.")
    parser.add_argument("--decisions-file", type=Path, default=None, help="Path to item-granular decisions.json.")
    parser.add_argument("--approved-clusters", type=str, default="", help="Comma-separated approved cluster IDs.")
    parser.add_argument("--excluded-clusters", type=str, default="", help="Comma-separated excluded cluster IDs.")
    parser.add_argument("--dry-run", action="store_true", help="Preview projected deltas with zero live mutation.")
    parser.add_argument("--apply", action="store_true", help="Apply operator-approved clusters/decisions and rematerialize.")
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
        bundles_dir=args.bundles_dir,
        approved_clusters=sorted(_parse_csv(args.approved_clusters)),
        excluded_clusters=sorted(_parse_csv(args.excluded_clusters)),
        decisions_file=args.decisions_file,
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
