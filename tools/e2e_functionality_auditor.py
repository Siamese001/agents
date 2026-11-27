#!/usr/bin/env python3
"""Behavioral 6-Pillar Domain Business Pipelines Assurance Auditor (Agent 4).

Replaces print-only inline scripts and skipped resume checks with live,
fail-closed behavioral verification across domain business applications:
1. apps_research -> outreach_engine live briefing resolution, airlock, and cache reuse.
2. apps_research -> resume_graph_engine targeting brief contract & fail-closed delegation.
3. Authoritative E2E lifecycle smoke (outreach + deterministic resume + DOCX) in read-only mode.
4. Hermetic SQLite multi-hop resume/competency graph traversal.
5. Fail-closed AST scan rejecting unguarded broad exception empty returns across domain packages.
6. Production derivation purity (lint_production_purity).
"""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]
_STANDALONE_SYNC_DIGEST_RE = re.compile(
    r"^CORE_GOVERNANCE_[A-Z0-9_]+_SHA256\s*=\s*['\"][0-9a-f]{64}['\"]",
    re.MULTILINE,
)
AUDITED_PACKAGES = (
    "agents",
    "apps_eval",
    "apps_model_telemetry",
    "apps_research",
    "infrastructure",
    "ops_scripts",
    "outreach_engine",
    "resume_engine",
    "resume_graph_engine",
    "scripts",
    "tools",
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


def _has_valid_guardian_rationale(line_txt: str, prev_txt: str) -> bool:
    for txt in (line_txt, prev_txt):
        if "guardian:" in txt and "--" in txt.split("guardian:", 1)[1]:
            return True
    return False


def _is_auto_synced_standalone_bundle(pkg: str, py_file: Path, src: str) -> bool:
    """Return True only for auto-synced core-governance standalone fallback bundles (parity with ssot_boundary_auditor)."""
    return (
        pkg == "tools"
        and py_file.name.startswith("_standalone_")
        and bool(_STANDALONE_SYNC_DIGEST_RE.search(src))
    )


def _scan_silent_swallows_and_guardian_backlog(repo_root: Path) -> tuple[list[dict[str, Any]], int]:
    """Single-pass AST scan for unguarded silent swallows and guardian allow-silent-swallow backlog."""
    findings: list[dict[str, Any]] = []
    guardian_count = 0
    for pkg in AUDITED_PACKAGES:
        base = repo_root / pkg
        if not base.exists():
            continue
        for py_file in sorted(base.rglob("*.py")):
            rel = py_file.relative_to(repo_root).as_posix()
            if "/tests/" in f"/{rel}" or "/artifacts/" in f"/{rel}" or py_file.name.startswith("test_"):
                continue
            src = py_file.read_text(encoding="utf-8")
            if "except" not in src or _is_auto_synced_standalone_bundle(pkg, py_file, src):
                continue
            lines = src.splitlines()
            if "allow-silent-swallow" in src:
                for line in lines:
                    if "allow-silent-swallow" in line and "except Exception" in line:
                        guardian_count += 1
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
                if _has_valid_guardian_rationale(line_txt, prev_txt):
                    continue
                if len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Continue)):
                    findings.append({"file": rel, "line": node.lineno, "handler": line_txt.strip()})
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Return) and _is_empty_return_expr(sub.value):
                        findings.append(
                            {
                                "file": rel,
                                "line": node.lineno,
                                "handler": line_txt.strip(),
                            }
                        )
                        break
    return findings, guardian_count


def scan_unguarded_silent_swallows(repo_root: Path) -> list[dict[str, Any]]:
    """Fail-closed AST scan for unguarded broad except blocks returning empty values or bare pass/continue."""
    findings, _ = _scan_silent_swallows_and_guardian_backlog(repo_root)
    return findings


def count_guardian_silent_swallows(repo_root: Path) -> int:
    """Count broad except blocks carrying allow-silent-swallow across audited packages."""
    _, guardian_count = _scan_silent_swallows_and_guardian_backlog(repo_root)
    return guardian_count


def _require_module(repo_root: Path, rel_path: str) -> Any:
    from tools.cost_token_budget_probes import load_repo_module

    mod, err = load_repo_module(repo_root, rel_path)
    if mod is None or err is not None:
        raise RuntimeError(err or f"Unable to load {rel_path}")
    return mod


def _probe_research_to_outreach_handoff(repo_root: Path) -> dict[str, Any]:
    resolver_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/pipeline/briefing_resolver.py")
    resolver_cls = resolver_mod.GovernedBriefingResolver
    resolver_cls.clear_cache()
    targets = (
        ("Citi", "Head of AI Strategy", "Lead enterprise AI strategy and governance."),
        ("AIG", "SVP Enterprise Architecture", "Scale enterprise architecture and agentic AI across P&C."),
        ("Brown & Brown", "Chief AI Architect", "Drive federated enterprise architecture and M&A data integration."),
    )
    resolved_targets: dict[str, Any] = {}
    try:
        fallback = resolver_cls.resolve(
            company_name="Nonexistent_Shadow_Corp_999", target_role="VP AI",
            job_description_text="Offline probe", auto_research=False, force_fresh=False,
        )
        cache_len_after_fallback = len(resolver_cls._cache)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            for company, role, jd in targets:
                resolved_targets[company] = resolver_cls.resolve(
                    company_name=company, target_role=role, job_description_text=jd,
                    auto_research=True, force_fresh=False,
                )
            grounded = resolved_targets["Citi"]
            cached = resolver_cls.resolve(
                company_name="Citi", target_role="Head of AI Strategy",
                job_description_text="Lead enterprise AI strategy and governance.",
                auto_research=False, force_fresh=False,
            )
    finally:
        resolver_cls.clear_cache()

    outreach_delegation_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/integrations/managed_research_delegation.py")
    outreach_bridge_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/integrations/apps_research_bridge.py")
    unauth_outreach_req = outreach_delegation_mod.RequestForOutreachBriefing(
        request_id="req_outreach_unauth_probe", run_id="run_outreach_unauth_probe",
        trace_id="trace_outreach_unauth_probe", company_name="Citi",
        job_title="Head of AI Strategy", research_authorized=False,
    )
    with tempfile.TemporaryDirectory(prefix="e2e_aud_outreach_bridge_") as td:
        out_bridge = outreach_bridge_mod.AppsResearchBridge(artifact_runs_root=Path(td))
        unauth_outreach_res = outreach_delegation_mod.dispatch_outreach_research_briefing(unauth_outreach_req, bridge=out_bridge)
    unauth_outreach_blocked = isinstance(unauth_outreach_res, outreach_delegation_mod.ResearchDispatchFailure)

    gaps: list[str] = []
    for company, res_obj in resolved_targets.items():
        if not res_obj.is_verified or not res_obj.briefing_text.strip():
            gaps.append(f"GovernedBriefingResolver failed to resolve verified company brief for {company}")
    if cached.resolution_source != "CACHE_HIT" or cached.digest != grounded.digest:
        gaps.append(f"Expected second resolve to hit BriefingCache, got {cached.resolution_source!r}")
    if fallback.resolution_source != "HERMETIC_FALLBACK" or cache_len_after_fallback != 0:
        gaps.append("Unknown company with auto_research=False did not trigger non-poisoning HERMETIC_FALLBACK")
    if not unauth_outreach_blocked:
        gaps.append("dispatch_outreach_research_briefing did not fail closed when research_authorized=False")
    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "targets_verified": [c for c, r in resolved_targets.items() if r.is_verified and r.briefing_text.strip()],
        "grounded_chars": len(grounded.briefing_text),
        "cache_status": cached.resolution_source,
        "fallback_status": fallback.resolution_source,
        "unauthorized_outreach_dispatch_blocked": unauth_outreach_blocked,
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
    bad_verdict_lic = contract_mod.validate_targeting_brief_text(bad_brief, profile="apps_lic")
    bad_verdict_rg = contract_mod.validate_targeting_brief_text(bad_brief, profile="apps_rg")
    bad_rejected = (
        not bool(bad_verdict_lic.valid)
        and "bracket_placeholder_present" in bad_verdict_lic.violations
        and not bool(bad_verdict_rg.valid)
        and "bracket_placeholder_present" in bad_verdict_rg.violations
    )

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
    good_verdict_lic = contract_mod.validate_targeting_brief_text(valid_brief, profile="apps_lic")
    good_verdict_rg = contract_mod.validate_targeting_brief_text(valid_brief, profile="apps_rg")
    good_passed = bool(good_verdict_lic.valid) and bool(good_verdict_rg.valid)

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
    main_mod = _require_module(repo_root, "resume_graph_engine/src/apps_rg/__main__.py")
    policy_mod = _require_module(
        repo_root, "resume_graph_engine/src/apps_rg/runtime/product_output_policy.py"
    )
    chroma_mod = _require_module(
        repo_root, "resume_graph_engine/src/apps_rg/runtime/chroma_precomputed_collection.py"
    )
    seal_helper_ok = callable(getattr(main_mod, "_has_valid_sealed_stage_ledger", None))
    chroma_ef_ok = hasattr(chroma_mod, "ForbidChromaDefaultEmbeddingFunction")
    policy_doc_ok = "APPS_RG_ALLOW_PRODUCT_SHORTCUTS" in (
        policy_mod.product_fail_closed_runtime.__doc__ or ""
    )

    gaps: list[str] = []
    if not bad_rejected:
        gaps.append("validate_targeting_brief_text failed to reject placeholder/URL-contaminated brief")
    if not good_passed:
        gaps.append(f"validate_targeting_brief_text rejected valid structured brief: lic={good_verdict_lic}, rg={good_verdict_rg}")
    if not unauth_blocked:
        gaps.append("dispatch_resume_research_briefing did not fail closed when research_authorized=False")
    if not (seal_helper_ok and chroma_ef_ok and policy_doc_ok):
        gaps.append("apps_rg stage-ledger seal helper, Chroma EF guard, or shortcut policy missing")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "placeholder_brief_rejected": bad_rejected,
        "structured_brief_accepted": good_passed,
        "unauthorized_dispatch_blocked": unauth_blocked,
        "stage_ledger_seal_helper_present": seal_helper_ok,
    }


def _probe_authoritative_e2e_smoke(repo_root: Path, *, read_only: bool) -> dict[str, Any]:
    smoke_mod = _require_module(
        repo_root,
        "ops_scripts/run_e2e_authoritative_smoke.py",
    )
    with tempfile.TemporaryDirectory(prefix="e2e_aud_rcpt_") as td:
        rcpt_path = Path(td) / "smoke_receipt.json"
        rc = smoke_mod.run_smoke(
            skip_resume=False,
            read_only=read_only,
            receipt_out=rcpt_path,
            repo_root=repo_root,
            verify_deterministic_resume=True,
            quiet=True,
        )
        rcpt_data = json.loads(rcpt_path.read_text(encoding="utf-8")) if rcpt_path.is_file() else {}

    verified = rcpt_data.get("verified_artifacts", {})
    stages = rcpt_data.get("stages") or {}
    has_outreach = "outreach_campaign" in verified and (stages.get("executive_outreach") or {}).get("status") == "PASSED"
    has_resume = (
        "final_resume" in verified
        and "resume_pipeline::resume.md" in verified
        and "resume_pipeline::resume.docx" in verified
        and (stages.get("resume_tailoring") or {}).get("status") == "PASSED"
        and rcpt_data.get("skip_resume") is False
    )
    cli_cmds = (
        [sys.executable, "-m", "agents", "resume", "--help"],
        [sys.executable, "-m", "agents", "outreach", "--help"],
        [sys.executable, "-m", "agents", "e2e", "--help"],
        [sys.executable, "-m", "resume_engine.cli", "--help"],
    )
    with ThreadPoolExecutor(max_workers=len(cli_cmds)) as cli_pool:
        cli_procs = list(
            cli_pool.map(
                lambda cmd: subprocess.run(
                    cmd,
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=30,
                ),
                cli_cmds,
            )
        )
    cli_probes_passed = all(proc.returncode == 0 for proc in cli_procs)

    inspectors_mod = _require_module(repo_root, "resume_engine/cli_inspectors.py")
    with contextlib.redirect_stdout(io.StringIO()):
        models_rc = inspectors_mod.handle_models(argparse.Namespace(json=True, role="executive_summary"))
        cache_rc = inspectors_mod.handle_cache(argparse.Namespace(json=True))
    if models_rc != 0 or cache_rc != 0:
        cli_probes_passed = False

    lic_models_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/domain/models.py")
    lic_disp_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/runtime/dispatch/canonical_dispatch.py")
    lic_cli_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/__main__.py")
    lic_out_mod = _require_module(repo_root, "outreach_engine/src/apps_lic/runtime/final_outreach_outputs.py")
    lic_draft = lic_models_mod.OutreachMessageDraft(
        draft_id="d_probe_1", channel=lic_models_mod.ChannelType.EMAIL,
        subject="Executive AI Platform Alignment", body="Led enterprise AI platform governance across 4 divisions.",
    )
    lic_tp = lic_models_mod.TouchPoint(
        touch_number=1, day_offset=0, channel=lic_models_mod.ChannelType.EMAIL,
        objective="Executive introduction", draft=lic_draft,
    )
    lic_seq = lic_models_mod.TouchSequence(
        sequence_id="seq_probe_1", candidate_id="cand_probe", opportunity_id="opp_probe", touches=[lic_tp],
    )
    lic_ingress = lic_disp_mod.build_cli_ingress_raw(company="Citi", role="Head of AI Strategy")
    lic_parser = lic_cli_mod._build_parser()
    lic_subcmds = {
        cmd for act in getattr(lic_parser, "_actions", ()) for cmd in (getattr(act, "choices", None) or {})
    }
    expected_9_cli = {"run", "patch-run", "eval", "validate", "show", "preflight", "models", "cache", "doctor"}
    if len(lic_seq.touches) != 1 or not isinstance(lic_ingress, dict) or not expected_9_cli.issubset(lic_subcmds):
        cli_probes_passed = False

    export_0644_ok = True
    with tempfile.TemporaryDirectory(prefix="e2e_aud_lic_export_") as td_exp:
        exp_dir = Path(td_exp)
        bundle = lic_out_mod.export_final_outreach_bundle(exp_dir, target_company="Citi", target_role="Head of AI Strategy")
        if not bundle.passed or not bundle.permissions_verified or not bundle.posix_paths_verified:
            export_0644_ok = False
        for fname in lic_out_mod.CANONICAL_OUTREACH_EXPORT_FILENAMES:
            fp = exp_dir / fname
            if not fp.is_file() or fp.stat().st_size == 0 or stat.S_IMODE(fp.stat().st_mode) != 0o644:
                export_0644_ok = False
        if not lic_out_mod.verify_docx_ecma376_compliance(exp_dir / "executive_outreach_packet.docx").get("passed"):
            export_0644_ok = False

    gaps: list[str] = []
    if rc != 0:
        gaps.append(f"run_e2e_authoritative_smoke returned non-zero exit code {rc}")
    if not has_outreach:
        gaps.append("outreach_campaign artifact or Stage 3 PASSED status missing from authoritative smoke receipt")
    if not has_resume:
        gaps.append("Stage 2 resume_tailoring PASSED or final_resume / resume.md / resume.docx missing from smoke receipt")
    if not cli_probes_passed:
        gaps.append(f"Unified CLI or 9-subcommand outreach surface probe failed (found={sorted(lic_subcmds)})")
    if not export_0644_ok:
        gaps.append("Outreach 4-format 0644 POSIX export or DOCX ECMA-376 compliance check failed")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "skip_resume": rcpt_data.get("skip_resume"),
        "verified_artifact_count": len(verified),
        "det_resume_status": (rcpt_data.get("deterministic_resume_pipeline") or {}).get("status"),
        "cli_subcommands_verified": cli_probes_passed,
        "outreach_9_cli_subcommands": sorted(lic_subcmds & expected_9_cli),
        "outreach_0644_exports_verified": export_0644_ok,
    }


def _probe_graph_traversal(repo_root: Path, *, probe_mod: Any | None = None) -> dict[str, Any]:
    mod = probe_mod if probe_mod is not None else _require_module(
        repo_root,
        "tools/run_resume_graph_traversal_probe.py",
    )
    payload = mod.run_resume_graph_traversal_probe(max_paths=100)
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


def _probe_production_purity(repo_root: Path, *, purity_mod: Any | None = None) -> dict[str, Any]:
    mod = purity_mod if purity_mod is not None else _require_module(repo_root, "tools/lint_production_purity.py")
    violations: list[str] = []
    for prod_dir in mod.PRODUCTION_DIRECTORIES:
        d = repo_root / prod_dir
        if not d.exists():
            continue
        for py_file in sorted(d.rglob("*.py")):
            for lineno, symbol, msg in mod.check_file_production_purity(py_file, repo_root):
                rel = py_file.relative_to(repo_root).as_posix()
                violations.append(f"{rel}:{lineno} [{symbol}] {msg}")
    return {
        "passed": len(violations) == 0,
        "gaps": violations[:15],
        "violation_count": len(violations),
    }


def _probe_vocab_symmetry_overlap_and_v2_sealing(repo_root: Path) -> dict[str, Any]:
    """Pillar 7: Verify prompt-validator vocab symmetry, overlap/domain-literal ratchet, anti-overfitting, and V2 spine receipt sealing."""
    gaps: list[str] = []

    if (repo_root / "tools" / "lint_prompt_validator_vocab_symmetry.py").is_file():
        from tools.lint_prompt_validator_vocab_symmetry import audit_prompt_validator_vocab_symmetry

        vocab_errs = audit_prompt_validator_vocab_symmetry(repo_root)
        gaps.extend(vocab_errs[:10])

    if (repo_root / "tools" / "lint_apps_rg_domain_literals.py").is_file():
        from tools.lint_apps_rg_domain_literals import audit_apps_rg_domain_literals

        lit_errs = audit_apps_rg_domain_literals(repo_root)
        gaps.extend(lit_errs[:10])

    if (repo_root / "tools" / "lint_no_jd_overfitting.py").is_file():
        from tools.lint_no_jd_overfitting import collect_production_files, scan_files

        ov_rep = scan_files(collect_production_files(repo_root), repo_root)
        if int(ov_rep.get("unbaselined_count", 0)) > 0:
            gaps.append(f"lint_no_jd_overfitting detected {ov_rep.get('unbaselined_count')} unbaselined JD branches")

    v2_checks = (
        (
            "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_v2",
            ("write_x2_source_fact_pool_receipt", "set_authoritative_attempt"),
            ("graph_targeting_capsule", "section_metric_receipt.json"),
        ),
        (
            "resume_graph_engine/src/apps_rg/runtime/sections/headline_v2",
            ("write_x2_source_fact_pool_receipt", "set_authoritative_attempt"),
            ("section_metric_receipt.json",),
        ),
        (
            "resume_graph_engine/src/apps_rg/runtime/sections/role_narrative_v2",
            ("write_x2_source_fact_pool_receipt", "set_authoritative_attempt"),
            ("section_metric_receipt.json",),
        ),
    )
    for rel_dir, required_calls, required_literals in v2_checks:
        d = repo_root / rel_dir
        if not d.is_dir():
            gaps.append(f"Missing V2 section directory: {rel_dir}")
            continue
        called_names: set[str] = set()
        str_literals: set[str] = set()
        for py_p in sorted(d.rglob("*.py")):
            tree = ast.parse(py_p.read_text(encoding="utf-8", errors="replace"), filename=str(py_p))
            for n in ast.walk(tree):
                if isinstance(n, ast.Call):
                    if isinstance(n.func, ast.Name):
                        called_names.add(n.func.id)
                    elif isinstance(n.func, ast.Attribute):
                        called_names.add(n.func.attr)
                elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                    str_literals.add(n.value)
        for fn_name in required_calls:
            if fn_name not in called_names:
                gaps.append(f"{rel_dir} AST missing call to V2 sealing helper '{fn_name}'")
        for lit in required_literals:
            if not any(lit in s for s in str_literals):
                gaps.append(f"{rel_dir} AST missing V2 receipt literal '{lit}'")

    # Behavioral probe: Executive Summary V2 X2 rejects post-repair inanimate openers & AI crutches
    try:
        from apps_rg.runtime.sections.executive_summary_v2.x2_invariants import evaluate_executive_summary_v2_x2

        bad_probe = (
            "Engineering executive scaling governed AI platforms across regulated accounts. "
            "Platform ownership covered deterministic controls across banking teams. "
            "In parallel, field delivery scaled regulated workflows."
        )
        probe_gates = {
            g["gate_id"]: g["pass"]
            for g in evaluate_executive_summary_v2_x2(
                resume_display_text=bad_probe,
                claim_ledger=[{"claim_text": "s", "source_fact_ids": ["f1"]} for _ in range(3)],
                parsed_output={"resume_display_text": bad_probe},
                allowed_fact_ids={"f1"},
                verified_numbers=frozenset(),
                verified_corpus_lower="agentic cloud banking",
                target_company="TargetBank",
                jd_text="banking ai",
            )
        }
        if probe_gates.get("x2_v2_no_inanimate_subject_openers") is not False:
            gaps.append("executive_summary_v2 X2 failed to reject inanimate-subject opener")
        if probe_gates.get("x2_v2_no_ai_bridge_crutches") is not False:
            gaps.append("executive_summary_v2 X2 failed to reject AI bridge crutch")
    except Exception as exc:  # guardian: allow-broad-exception -- report V2 X2 behavioral probe failure
        gaps.append(f"executive_summary_v2 X2 behavioral probe error: {type(exc).__name__}: {exc}")

    # Verify patch_run frozen graph-authority enforcement helpers exist via AST
    patch_run_path = repo_root / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "orchestration" / "patch_run.py"
    if patch_run_path.is_file():
        pr_tree = ast.parse(patch_run_path.read_text(encoding="utf-8", errors="replace"), filename=str(patch_run_path))
        pr_defs = {n.name for n in ast.walk(pr_tree) if isinstance(n, ast.FunctionDef)}
        for req_fn in ("_whole_resume_graph_rollup_authority", "_lane_matches_frozen_graph_authority"):
            if req_fn not in pr_defs:
                gaps.append(f"patch_run.py missing frozen graph-authority function '{req_fn}'")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "vocab_symmetry_and_v2_sealing_verified": len(gaps) == 0,
    }


def run_e2e_functionality_audit(repo_root: Path | None = None, *, read_only: bool = True) -> dict[str, Any]:
    root = (repo_root or DEFAULT_REPO_ROOT).resolve()
    _ensure_paths(root)

    p1 = _probe_research_to_outreach_handoff(root)
    p2 = _probe_research_to_resume_handoff(root)

    # Pre-load read-only worker probe modules on the main thread before concurrent execution.
    graph_probe_mod = _require_module(root, "tools/run_resume_graph_traversal_probe.py")
    purity_mod = _require_module(root, "tools/lint_production_purity.py")
    if (root / "tools" / "lint_prompt_validator_vocab_symmetry.py").is_file():
        import tools.lint_prompt_validator_vocab_symmetry  # noqa: F401
    if (root / "tools" / "lint_apps_rg_domain_literals.py").is_file():
        import tools.lint_apps_rg_domain_literals  # noqa: F401
    if (root / "tools" / "lint_no_jd_overfitting.py").is_file():
        import tools.lint_no_jd_overfitting  # noqa: F401

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_p4 = pool.submit(_probe_graph_traversal, root, probe_mod=graph_probe_mod)
        f_p5 = pool.submit(_scan_silent_swallows_and_guardian_backlog, root)
        f_p6 = pool.submit(_probe_production_purity, root, purity_mod=purity_mod)
        f_p7 = pool.submit(_probe_vocab_symmetry_overlap_and_v2_sealing, root)
        p3 = _probe_authoritative_e2e_smoke(root, read_only=read_only)
        p4 = f_p4.result()
        swallows, guardian_backlog = f_p5.result()
        p6 = f_p6.result()
        p7 = f_p7.result()

    p5 = {
        "passed": len(swallows) == 0,
        "gaps": [f"Unguarded silent swallow at {s['file']}:{s['line']}" for s in swallows[:15]],
        "unguarded_silent_swallow_count": len(swallows),
        "guardian_swallow_backlog": guardian_backlog,
    }

    pillars = {
        "pillar_1_research_to_outreach_handoff": p1,
        "pillar_2_research_to_resume_handoff": p2,
        "pillar_3_authoritative_e2e_smoke": p3,
        "pillar_4_resume_graph_traversal": p4,
        "pillar_5_fail_closed_exception_hygiene": p5,
        "pillar_6_production_derivation_purity": p6,
        "pillar_7_vocab_symmetry_overlap_and_v2_sealing": p7,
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
        "status": "PASS" if is_clean else "FAIL",
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
