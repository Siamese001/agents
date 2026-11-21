#!/usr/bin/env python3
"""Audit candidate fact provenance across apps_rg role episode bundles (INV-FACT-GRAPH-NO-AGENT-SYNTHESIS).

Verifies that every role episode bundle and approved metric_outcome_node in
``resume_graph_engine/src/apps_rg/fact_inventory/*_role_episode_bundles.json``:
1. Contains zero self-certifying ``approved_by_graph_presence`` tokens.
2. Carries explicit verified provenance (``verified_base_resume`` or ``verified_operator_confirmed``)
   with non-empty ``provenance_source_refs`` resolving to canonical candidate sources:
   - ``amit_ayer_base_resume_v1.json`` (resolved via ``active_base_resume_pointer.json``)
   - ``master_candidate_skills_fact_ledger_20260518T1100Z.json``
   - ``slalom_graph_delta_proposal.json``
   - ``master_skills_arsenal_ledger.json``
3. Quarantines unverified synthetic claims (``approved: false``,
   ``support_level: "quarantined_unverified_synthetic"``) and blocks any unverified
   synthetic numbers or vendor tokens (e.g. ``Confluent``, ``Kafka``, ``24% renewal lift``)
   from remaining ``approved: true`` or appearing in active bundle claims.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VALID_VERIFIED_SUPPORT_LEVELS = frozenset(
    {"verified_base_resume", "verified_operator_confirmed"}
)
QUARANTINED_SUPPORT_LEVEL = "quarantined_unverified_synthetic"

FORBIDDEN_UNVERIFIED_TOKENS_RE = re.compile(
    r"\b(?:confluent|kafka)\b|"
    r"\b(?:24|28|32|34|38|42|48|60|72|98)\s*%|"
    r"\b54\s*%\s*(?:mttr|mean-time)|"
    r"\bmttr\b[^.]{0,30}\b54\s*%|"
    r"\b1,200\+|\b250k\+|\$3\.2m\b|"
    r"\b16\s+(?:enterprise\s+)?on-prem-to-aws\b|"
    r"\b7\s+reusable\b|"
    r"\b14\s+repeatable\s+terraform\b",
    re.IGNORECASE,
)


def _load_canonical_source_ids(repo_root: Path) -> tuple[set[str], str]:
    rg_src = repo_root / "resume_graph_engine" / "src" / "apps_rg"
    pointer_path = rg_src / "resume" / "base" / "active_base_resume_pointer.json"
    base_path = rg_src / "resume" / "base" / "amit_ayer_base_resume_v1.json"
    if pointer_path.is_file():
        ptr = json.loads(pointer_path.read_text(encoding="utf-8"))
        rel = str(ptr.get("active_base_resume_file") or ptr.get("file") or "").strip()
        if rel:
            candidate = (pointer_path.parent / Path(rel).name).resolve()
            if candidate.is_file():
                base_path = candidate

    known_ids: set[str] = {"amit_ayer_base_resume_v1"}
    base_doc = json.loads(base_path.read_text(encoding="utf-8"))
    known_ids.add(str(base_doc.get("base_resume_id") or "amit_ayer_base_resume_v1"))
    facts = base_doc.get("facts") or {}
    for emp in facts.get("employment") or []:
        if isinstance(emp, dict) and emp.get("fact_id"):
            known_ids.add(str(emp["fact_id"]))
            for bul in emp.get("bullets") or []:
                if isinstance(bul, dict) and bul.get("bullet_id"):
                    known_ids.add(str(bul["bullet_id"]))
    for section_key in ("skills", "education", "certifications"):
        for item in facts.get(section_key) or []:
            if isinstance(item, dict) and item.get("fact_id"):
                known_ids.add(str(item["fact_id"]))

    ledger_path = (
        repo_root
        / "resume_graph_engine"
        / "artifacts"
        / "apps_rg"
        / "fact_inventory"
        / "master_candidate_skills_fact_ledger_20260518T1100Z.json"
    )
    if ledger_path.is_file():
        known_ids.add("master_candidate_skills_fact_ledger_20260518T1100Z")
        ledger_doc = json.loads(ledger_path.read_text(encoding="utf-8"))
        for cf in ledger_doc.get("candidate_facts") or []:
            if isinstance(cf, dict) and cf.get("candidate_fact_id"):
                known_ids.add(str(cf["candidate_fact_id"]))

    slalom_prop_path = (
        repo_root
        / "resume_graph_engine"
        / "artifacts"
        / "apps_rg"
        / "slalom_extraction"
        / "slalom_graph_delta_proposal.json"
    )
    if slalom_prop_path.is_file():
        known_ids.add("slalom_graph_delta_proposal")
        prop_doc = json.loads(slalom_prop_path.read_text(encoding="utf-8"))
        for node in prop_doc.get("nodes") or []:
            if isinstance(node, dict) and node.get("node_id"):
                known_ids.add(str(node["node_id"]))

    arsenal_path = rg_src / "fact_inventory" / "master_skills_arsenal_ledger.json"
    if arsenal_path.is_file():
        known_ids.add("master_skills_arsenal_ledger")
        arsenal_doc = json.loads(arsenal_path.read_text(encoding="utf-8"))
        for sr in arsenal_doc.get("skill_rows") or []:
            if isinstance(sr, dict) and sr.get("skill_id"):
                known_ids.add(str(sr["skill_id"]))
        for gn in arsenal_doc.get("graph_nodes") or []:
            if isinstance(gn, dict) and gn.get("node_id"):
                known_ids.add(str(gn["node_id"]))

    return known_ids, str(base_path.relative_to(repo_root))


def audit_fact_provenance(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    known_ids, base_rel = _load_canonical_source_ids(root)
    inv_dir = root / "resume_graph_engine" / "src" / "apps_rg" / "fact_inventory"
    bundle_files = sorted(inv_dir.glob("*_role_episode_bundles.json"))

    violations: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    graph_presence_count = 0

    for path in bundle_files:
        rel_file = str(path.relative_to(root))
        raw_text = path.read_text(encoding="utf-8")
        gp_hits = raw_text.count("approved_by_graph_presence")
        graph_presence_count += gp_hits
        if gp_hits > 0:
            violations.append(
                {
                    "code": "FORBIDDEN_APPROVED_BY_GRAPH_PRESENCE",
                    "file": rel_file,
                    "entity_id": path.name,
                    "message": f"{gp_hits} self-certifying 'approved_by_graph_presence' occurrence(s) remain in {path.name}.",
                }
            )

        doc = json.loads(raw_text)
        for bundle in doc.get("bundles") or []:
            if not isinstance(bundle, dict):
                continue
            bid = str(bundle.get("role_episode_bundle_id") or "")
            support = str(bundle.get("support_level") or "").strip().lower()
            refs = [
                str(r).strip()
                for r in (bundle.get("provenance_source_refs") or bundle.get("linked_source_fact_ids") or [])
                if str(r).strip()
            ]
            bundle_rows.append(
                {
                    "file": path.name,
                    "bundle_id": bid,
                    "employer": str(bundle.get("employer") or ""),
                    "support_level": support,
                    "provenance_source_refs": refs,
                }
            )
            if support not in VALID_VERIFIED_SUPPORT_LEVELS:
                violations.append(
                    {
                        "code": "INVALID_BUNDLE_SUPPORT_LEVEL",
                        "file": rel_file,
                        "entity_id": bid,
                        "message": f"Bundle {bid} has invalid support_level={support!r}.",
                    }
                )
            unknown_refs = [r for r in refs if r not in known_ids]
            if not refs or unknown_refs:
                violations.append(
                    {
                        "code": "INVALID_BUNDLE_PROVENANCE_REFS",
                        "file": rel_file,
                        "entity_id": bid,
                        "message": f"Bundle {bid} missing or unknown provenance_source_refs (unknown={unknown_refs}).",
                    }
                )
            bundle_surface = " ".join(
                [
                    str(bundle.get("claim_text") or ""),
                    str(bundle.get("claim_action") or ""),
                    str(bundle.get("claim_scope") or ""),
                    str(bundle.get("claim_outcome") or ""),
                    " ".join(str(x) for x in (bundle.get("executive_scope_signals") or [])),
                ]
            )
            bad_match = FORBIDDEN_UNVERIFIED_TOKENS_RE.search(bundle_surface)
            if bad_match:
                violations.append(
                    {
                        "code": "UNVERIFIED_SYNTHETIC_TOKEN_IN_BUNDLE",
                        "file": rel_file,
                        "entity_id": bid,
                        "message": f"Bundle {bid} contains unverified synthetic token {bad_match.group(0)!r}.",
                    }
                )

        nodes = doc.get("metric_outcome_nodes") or {}
        node_items = (
            [(str(m.get("metric_outcome_id") or ""), m) for m in nodes if isinstance(m, dict)]
            if isinstance(nodes, list)
            else [(str(k), v) for k, v in nodes.items() if isinstance(v, dict)]
        )
        for mid, node in node_items:
            approved = bool(node.get("approved", False))
            support = str(node.get("support_level") or "").strip().lower()
            approval_status = str(node.get("approval_status") or "").strip()
            refs = [
                str(r).strip()
                for r in (node.get("provenance_source_refs") or [])
                if str(r).strip()
            ]
            metric_txt = str(node.get("metric") or "")
            metric_rows.append(
                {
                    "file": path.name,
                    "metric_id": mid,
                    "employer": str(node.get("employer") or ""),
                    "approved": approved,
                    "support_level": support,
                    "approval_status": approval_status,
                    "provenance_source_refs": refs,
                    "quarantine_reason": str(node.get("quarantine_reason") or ""),
                    "metric": metric_txt,
                }
            )
            if approved:
                if support not in VALID_VERIFIED_SUPPORT_LEVELS:
                    violations.append(
                        {
                            "code": "INVALID_APPROVED_METRIC_SUPPORT_LEVEL",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Approved metric {mid} has invalid support_level={support!r}.",
                        }
                    )
                if not approval_status.upper().startswith("APPROVED"):
                    violations.append(
                        {
                            "code": "INVALID_APPROVED_METRIC_STATUS",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Approved metric {mid} has non-approved approval_status={approval_status!r}.",
                        }
                    )
                unknown_refs = [r for r in refs if r not in known_ids]
                if not refs or unknown_refs:
                    violations.append(
                        {
                            "code": "MISSING_OR_UNKNOWN_METRIC_PROVENANCE",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Approved metric {mid} missing or unknown provenance_source_refs (unknown={unknown_refs}).",
                        }
                    )
                metric_surface = " ".join(
                    [
                        metric_txt,
                        str(node.get("claim_text") or ""),
                        " ".join(str(x) for x in (node.get("surface_tokens") or [])),
                    ]
                )
                bad_match = FORBIDDEN_UNVERIFIED_TOKENS_RE.search(metric_surface)
                if bad_match:
                    violations.append(
                        {
                            "code": "UNVERIFIED_SYNTHETIC_TOKEN_IN_APPROVED_METRIC",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Approved metric {mid} contains unverified synthetic token {bad_match.group(0)!r}.",
                        }
                    )
            else:
                if support != QUARANTINED_SUPPORT_LEVEL:
                    violations.append(
                        {
                            "code": "UNAPPROVED_METRIC_MISSING_QUARANTINE_SUPPORT_LEVEL",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Unapproved metric {mid} must carry support_level={QUARANTINED_SUPPORT_LEVEL!r}, got {support!r}.",
                        }
                    )
                if not str(node.get("quarantine_reason") or "").strip():
                    violations.append(
                        {
                            "code": "QUARANTINED_METRIC_MISSING_REASON",
                            "file": rel_file,
                            "entity_id": mid,
                            "message": f"Quarantined metric {mid} is missing quarantine_reason.",
                        }
                    )

    verified_base_bundles = sum(1 for r in bundle_rows if r["support_level"] == "verified_base_resume")
    verified_op_bundles = sum(1 for r in bundle_rows if r["support_level"] == "verified_operator_confirmed")
    verified_base_metrics = sum(1 for r in metric_rows if r["approved"] and r["support_level"] == "verified_base_resume")
    verified_op_metrics = sum(1 for r in metric_rows if r["approved"] and r["support_level"] == "verified_operator_confirmed")
    quarantined_metrics = sum(1 for r in metric_rows if not r["approved"])

    return {
        "schema_version": "agents.fact_graph_provenance_audit.v1",
        "status": "PASS" if not violations else "FAIL",
        "base_resume_source": base_rel,
        "bundle_files_scanned": len(bundle_files),
        "graph_presence_count": graph_presence_count,
        "counts": {
            "total_bundles": len(bundle_rows),
            "verified_base_resume_bundles": verified_base_bundles,
            "verified_operator_confirmed_bundles": verified_op_bundles,
            "total_metrics": len(metric_rows),
            "verified_base_resume_metrics": verified_base_metrics,
            "verified_operator_confirmed_metrics": verified_op_metrics,
            "quarantined_unverified_synthetic_metrics": quarantined_metrics,
        },
        "violation_count": len(violations),
        "violations": violations,
        "bundles": bundle_rows,
        "metrics": metric_rows,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# Candidate Fact Graph Provenance Audit (`INV-FACT-GRAPH-NO-AGENT-SYNTHESIS`)",
        "",
        f"- **Audit Status**: `{report['status']}`",
        f"- **Canonical Base Resume**: `{report['base_resume_source']}`",
        f"- **Self-Certifying `approved_by_graph_presence` Count**: `{report['graph_presence_count']}` (Ceiling: `0`)",
        f"- **Role Episode Bundles Audited**: `{counts['total_bundles']}` (`{counts['verified_base_resume_bundles']}` `verified_base_resume`, `{counts['verified_operator_confirmed_bundles']}` `verified_operator_confirmed`)",
        f"- **Metric Outcome Nodes Audited**: `{counts['total_metrics']}` (`{counts['verified_base_resume_metrics']}` `verified_base_resume`, `{counts['verified_operator_confirmed_metrics']}` `verified_operator_confirmed`, `{counts['quarantined_unverified_synthetic_metrics']}` `quarantined_unverified_synthetic`)",
        "",
        "## Quarantined Unverified Synthetic Metrics (`approved: false`)",
        "",
        "| Employer | Metric Outcome ID | Quarantine Reason | Original Synthetic Surface |",
        "|---|---|---|---|",
    ]
    for row in report["metrics"]:
        if row["approved"]:
            continue
        lines.append(
            f"| {row['employer']} | `{row['metric_id']}` | {row['quarantine_reason']} | `{row['metric']}` |"
        )
    lines.extend(
        [
            "",
            "## Verified Active Metrics (`approved: true`)",
            "",
            "| Employer | Metric Outcome ID | Classification | Provenance Source Refs | Verified Metric Surface |",
            "|---|---|---|---|---|",
        ]
    )
    for row in report["metrics"]:
        if not row["approved"]:
            continue
        refs = ", ".join(f"`{r}`" for r in row["provenance_source_refs"])
        lines.append(
            f"| {row['employer']} | `{row['metric_id']}` | `{row['support_level']}` | {refs} | `{row['metric']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit candidate fact provenance across role episode bundles.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, default=None, help="Optional path to write Markdown audit report.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary to stdout.")
    parser.add_argument("--strict", action="store_true", help="Fail with exit code 1 on any violation.")
    args = parser.parse_args(argv)

    result = audit_fact_provenance(args.repo_root)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_markdown_report(result), encoding="utf-8")

    if args.json:
        summary = {k: v for k, v in result.items() if k not in {"bundles", "metrics"}}
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"[FACT-PROVENANCE] status={result['status']} "
            f"graph_presence={result['graph_presence_count']} "
            f"verified_metrics={result['counts']['verified_base_resume_metrics'] + result['counts']['verified_operator_confirmed_metrics']} "
            f"quarantined_metrics={result['counts']['quarantined_unverified_synthetic_metrics']} "
            f"violations={result['violation_count']}"
        )
        for v in result["violations"][:20]:
            print(f"  - [{v['code']}] {v['file']} :: {v['entity_id']} -> {v['message']}")

    if result["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
