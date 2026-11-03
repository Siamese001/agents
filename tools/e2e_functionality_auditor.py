#!/usr/bin/env python3
"""Behavioral 6-Pillar End-to-End Pipeline Assurance Auditor (Agent 3).

Replaces print-only inline scripts and skipped resume checks with live,
fail-closed behavioral verification across:
1. apps_research -> outreach_engine live briefing resolution, airlock, and cache reuse.
2. apps_research -> resume_graph_engine targeting brief contract & fail-closed delegation.
3. Authoritative E2E lifecycle smoke (outreach + deterministic resume + DOCX) in read-only mode.
4. Hermetic SQLite multi-hop resume/competency graph traversal.
5. Fail-closed AST scan rejecting unguarded broad exception empty returns across 5 packages.
6. Production derivation purity (lint_production_purity).
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
AUDITED_PACKAGES = (
    "agents",
    "apps_research",
    "resume_graph_engine/src",
    "outreach_engine/src",
    "resume_engine",
)


def _ensure_paths(repo_root: Path) -> None:
    for p in reversed(
        (
            repo_root,
            repo_root / "resume_graph_engine" / "src",
            repo_root / "outreach_engine" / "src",
        )
    ):
        s = str(p)
        if p.exists() and s not in sys.path:
            sys.path.insert(0, s)


def _is_empty_return_expr(expr: ast.AST | None) -> bool:
    if expr is None:
        return True
    if isinstance(expr, ast.Constant) and expr.value in (None, "", False, 0):
        return True
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)) and len(expr.elts) == 0:
        return True
    if isinstance(expr, ast.Dict) and len(expr.keys) == 0:
        return True
    return False


def scan_unguarded_silent_swallows(repo_root: Path) -> list[dict[str, Any]]:
    """Fail-closed AST scan for unguarded broad except blocks returning empty values."""
    findings: list[dict[str, Any]] = []
    for pkg in AUDITED_PACKAGES:
        base = repo_root / pkg
        if not base.exists():
            continue
        for py_file in sorted(base.rglob("*.py")):
            rel = py_file.relative_to(repo_root).as_posix()
            if "/tests/" in f"/{rel}" or py_file.name.startswith("test_"):
                continue
            src = py_file.read_text(encoding="utf-8")
            lines = src.splitlines()
            tree = ast.parse(src, filename=str(py_file))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                is_broad = node.type is None or (
                    isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
                )
                if not is_broad:
                    continue
                line_txt = lines[node.lineno - 1] if 1 <= node.lineno <= len(lines) else ""
                prev_txt = lines[node.lineno - 2] if 2 <= node.lineno <= len(lines) else ""
                if "guardian:" in line_txt or "guardian:" in prev_txt:
                    continue
                for stmt in node.body:
                    if isinstance(stmt, ast.Return) and _is_empty_return_expr(stmt.value):
                        findings.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "handler": line_txt.strip(),
                            }
                        )
                        break
    return findings


def _require_module(repo_root: Path, rel_path: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    mod, err = load_repo_module(repo_root, rel_path)
    if mod is None or err is not None:
        raise RuntimeError(err or f"Unable to load {rel_path}")
    return mod


def _probe_research_to_outreach_handoff(repo_root: Path) -> dict[str, Any]:
    resolver_mod = _require_module(
        repo_root,
        "outreach_engine/src/apps_lic/pipeline/briefing_resolver.py",
    )
    resolver_cls = resolver_mod.GovernedBriefingResolver
    resolver_cls.clear_cache()
    try:
        fallback = resolver_cls.resolve(
            company_name="Nonexistent_Shadow_Corp_999",
            target_role="VP AI",
            job_description_text="Offline probe",
            auto_research=False,
            force_fresh=False,
        )
        cache_len_after_fallback = len(resolver_cls._cache)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            grounded = resolver_cls.resolve(
                company_name="Citi",
                target_role="Head of AI Strategy",
                job_description_text="Lead enterprise AI strategy and governance.",
                auto_research=True,
                force_fresh=False,
            )
            cached = resolver_cls.resolve(
                company_name="Citi",
                target_role="Head of AI Strategy",
                job_description_text="Lead enterprise AI strategy and governance.",
                auto_research=False,
                force_fresh=False,
            )
    finally:
        resolver_cls.clear_cache()

    gaps: list[str] = []
    if not grounded.is_verified or not grounded.briefing_text.strip():
        gaps.append("GovernedBriefingResolver failed to resolve verified company brief")
    if cached.resolution_source != "CACHE_HIT" or cached.digest != grounded.digest:
        gaps.append(f"Expected second resolve to hit BriefingCache, got {cached.resolution_source!r}")
    if fallback.resolution_source != "HERMETIC_FALLBACK" or cache_len_after_fallback != 0:
        gaps.append("Unknown company with auto_research=False did not trigger non-poisoning HERMETIC_FALLBACK")
    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "grounded_chars": len(grounded.briefing_text),
        "cache_status": cached.resolution_source,
        "fallback_status": fallback.resolution_source,
    }


def _probe_research_to_resume_handoff(repo_root: Path) -> dict[str, Any]:
    contract_mod = _require_module(
        repo_root,
        "apps_research/types/apps_rg_targeting_brief_contract.py",
    )
    delegation_mod = _require_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/integrations/managed_research_delegation.py",
    )
    bridge_mod = _require_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/integrations/apps_research_bridge.py",
    )

    bad_brief = "# Company Brief\n- [INSERT COMPANY STRATEGY PLACEHOLDER]\n- https://example.com/leak\n"
    bad_verdict = contract_mod.validate_targeting_brief_text(bad_brief, profile="apps_lic")
    bad_rejected = (not bool(bad_verdict.valid)) and ("bracket_placeholder_present" in bad_verdict.violations)

    valid_lines = [
        "# Enterprise Platform Briefing",
        "## Strategic Mandate",
        *[
            f"- Enterprise platform roadmap prioritizes governed AI architecture and operating model alignment across {i + 2} core divisions."
            for i in range(5)
        ],
        "## Commercial & Stakeholder Signals",
        *[
            f"- Leadership decision rights center on measurable adoption velocity, risk governance, and partner ecosystem delivery stage {i + 1}."
            for i in range(5)
        ],
        "## Forward Priorities",
        *[
            f"- Forward-looking infrastructure investment targets production reliability, latency control, and customer value realization wave {i + 1}."
            for i in range(4)
        ],
    ]
    valid_brief = "\n".join(valid_lines)
    good_verdict = contract_mod.validate_targeting_brief_text(valid_brief, profile="apps_lic")
    good_passed = bool(good_verdict.valid)

    # Verify fail-closed dispatch when research_authorized=False
    unauth_req = delegation_mod.RequestForResumeBriefing(
        request_id="req_unauth_probe",
        run_id="run_unauth_probe",
        trace_id="trace_unauth_probe",
        company_name="Anthropic",
        job_title="Manager of Applied AI Architecture",
        research_authorized=False,
    )
    with tempfile.TemporaryDirectory(prefix="e2e_aud_bridge_") as td:
        bridge = bridge_mod.AppsResearchBridge(artifact_runs_root=Path(td))
        unauth_res = delegation_mod.dispatch_resume_research_briefing(unauth_req, bridge=bridge)

    unauth_blocked = isinstance(unauth_res, delegation_mod.ResearchDispatchFailure)
    gaps: list[str] = []
    if not bad_rejected:
        gaps.append("validate_targeting_brief_text failed to reject placeholder/URL-contaminated brief")
    if not good_passed:
        gaps.append(f"validate_targeting_brief_text rejected valid structured brief: {good_verdict}")
    if not unauth_blocked:
        gaps.append("dispatch_resume_research_briefing did not fail closed when research_authorized=False")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "placeholder_brief_rejected": bad_rejected,
        "structured_brief_accepted": good_passed,
        "unauthorized_dispatch_blocked": unauth_blocked,
    }


def _probe_authoritative_e2e_smoke(repo_root: Path, *, read_only: bool) -> dict[str, Any]:
    smoke_mod = _require_module(
        repo_root,
        "ops_scripts/run_e2e_authoritative_smoke.py",
    )
    with tempfile.TemporaryDirectory(prefix="e2e_aud_rcpt_") as td:
        rcpt_path = Path(td) / "smoke_receipt.json"
        rc = smoke_mod.run_smoke(
            skip_resume=True,
            read_only=read_only,
            receipt_out=rcpt_path,
            repo_root=repo_root,
            verify_deterministic_resume=True,
            quiet=True,
        )
        rcpt_data = json.loads(rcpt_path.read_text(encoding="utf-8")) if rcpt_path.is_file() else {}

    verified = rcpt_data.get("verified_artifacts", {})
    has_outreach = "outreach_campaign" in verified
    has_resume = "resume_pipeline::resume.md" in verified and "resume_pipeline::resume.docx" in verified
    gaps: list[str] = []
    if rc != 0:
        gaps.append(f"run_e2e_authoritative_smoke returned non-zero exit code {rc}")
    if not has_outreach:
        gaps.append("outreach_campaign artifact missing from authoritative smoke receipt")
    if not has_resume:
        gaps.append("deterministic resume.md / resume.docx artifacts missing from smoke receipt")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "verified_artifact_count": len(verified),
        "det_resume_status": (rcpt_data.get("deterministic_resume_pipeline") or {}).get("status"),
    }


def _probe_graph_traversal(repo_root: Path) -> dict[str, Any]:
    probe_mod = _require_module(
        repo_root,
        "tools/run_resume_graph_traversal_probe.py",
    )
    payload = probe_mod.run_resume_graph_traversal_probe(max_paths=100)
    gaps: list[str] = []
    if payload.get("status") != "PASS":
        gaps.append(f"Resume graph traversal probe failed: {payload}")
    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "node_count": payload.get("node_count_sqlite", 0),
        "edge_count": payload.get("edge_count_sqlite", 0),
        "two_hop_paths": payload.get("two_hop_path_count", 0),
        "domain_skill_evidence_paths": payload.get("domain_skill_evidence_path_count", 0),
    }


def _probe_production_purity(repo_root: Path) -> dict[str, Any]:
    purity_mod = _require_module(repo_root, "tools/lint_production_purity.py")
    violations: list[str] = []
    for prod_dir in purity_mod.PRODUCTION_DIRECTORIES:
        d = repo_root / prod_dir
        if not d.exists():
            continue
        for py_file in sorted(d.rglob("*.py")):
            for lineno, symbol, msg in purity_mod.check_file_production_purity(py_file, repo_root):
                rel = py_file.relative_to(repo_root).as_posix()
                violations.append(f"{rel}:{lineno} [{symbol}] {msg}")
    return {
        "passed": len(violations) == 0,
        "gaps": violations[:15],
        "violation_count": len(violations),
    }


def run_e2e_functionality_audit(repo_root: Path | None = None, *, read_only: bool = True) -> dict[str, Any]:
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    _ensure_paths(root)

    p1 = _probe_research_to_outreach_handoff(root)
    p2 = _probe_research_to_resume_handoff(root)
    p3 = _probe_authoritative_e2e_smoke(root, read_only=read_only)
    p4 = _probe_graph_traversal(root)
    swallows = scan_unguarded_silent_swallows(root)
    p5 = {
        "passed": len(swallows) == 0,
        "gaps": [f"Unguarded silent swallow at {s['file']}:{s['line']}" for s in swallows[:15]],
        "unguarded_silent_swallow_count": len(swallows),
    }
    p6 = _probe_production_purity(root)

    pillars = {
        "pillar_1_research_to_outreach_handoff": p1,
        "pillar_2_research_to_resume_handoff": p2,
        "pillar_3_authoritative_e2e_smoke": p3,
        "pillar_4_resume_graph_traversal": p4,
        "pillar_5_fail_closed_exception_hygiene": p5,
        "pillar_6_production_derivation_purity": p6,
    }
    all_gaps: list[str] = []
    passing_count = 0
    for name, res in pillars.items():
        if res["passed"]:
            passing_count += 1
        for g in res.get("gaps", []):
            all_gaps.append(f"[{name}] {g}")

    is_clean = passing_count == len(pillars) and len(all_gaps) == 0
    return {
        "schema_version": "agents.e2e_functionality_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "read_only": read_only,
        "is_clean": is_clean,
        "passing_pillars": passing_count,
        "total_pillars": len(pillars),
        "total_gaps": len(all_gaps),
        "gaps": all_gaps,
        "pillars": pillars,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 6-pillar behavioral E2E functionality audit (Agent 3).")
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT, help="Repository root to audit")
    parser.add_argument("--read-only", action="store_true", default=True, help="Run in hermetic read-only mode")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON receipt output path")
    parser.add_argument("--json", action="store_true", help="Emit JSON report on stdout")
    args = parser.parse_args(argv)

    report = run_e2e_functionality_audit(args.repo_root.resolve(), read_only=args.read_only)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if report["is_clean"] else "FAIL"
        print(
            f"[{status}] E2E Functionality Audit: {report['passing_pillars']}/{report['total_pillars']} "
            f"pillars passing (gaps={report['total_gaps']})"
        )
        for gap in report["gaps"]:
            print(f"  - {gap}")

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
