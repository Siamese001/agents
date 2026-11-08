"""Fast, reliable local health-check runner for the Sovereign Agentic Platform.

Covers 5 core architectural domains:
1. Startup: CLI entrypoint parsing, subparser routing, preflight authorization.
2. Orchestration: WorkflowExecutionEngine DAG transitions, sequential execution, terminal status immutability.
3. Both Engines: Resume Graph Engine (apps_rg) bare pipeline modes; Outreach Engine (apps_lic) pipeline & touch sequence.
4. Integration Contracts: Inter-engine handoffs, briefing resolution, schema contracts, cryptographic provenance sealing.
5. Failure Handling: Fail-closed stage termination, false-success prevention, retry budget exhaustion, tampered digests, and ungrounded/forbidden claims detection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from infrastructure.config.env_loader import snapshot_process_env

_REPO_ROOT = Path(__file__).resolve().parent.parent

HEALTH_DOMAINS: list[dict[str, Any]] = [
    {
        "domain": "Startup",
        "description": "CLI parser flags, engine dispatch routing, help dispatch, preflight verification",
        "test_files": [
            "tests/unit/test_agents_cli_e2e.py::test_cli_parser_e2e_flags",
            "outreach_engine/tests/test_unified_cli.py::test_agents_cli_help",
            "outreach_engine/tests/test_unified_cli.py::test_agents_cli_resume_help",
            "outreach_engine/tests/test_unified_cli.py::test_agents_cli_outreach_help",
            "resume_graph_engine/tests/unit/apps_rg/test_e2e_preflight.py",
        ],
    },
    {
        "domain": "Orchestration",
        "description": "WorkflowExecutionEngine DAG transitions, sequential lifecycle, terminal status immutability, stage preservation",
        "test_files": [
            "tests/unit/test_orchestration_runtime_hardening.py::test_workflow_execution_engine_positive_dag",
            "tests/unit/test_orchestration_runtime_hardening.py::test_terminal_statuses_immutability",
            "tests/unit/test_orchestration_runtime_hardening.py::test_pipeline_coordinator_release_rejection_sets_failed_phase",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_never_retry_completed_product_stages_for_transport_failures",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_preserve_successful_checkpoints_on_failure",
        ],
    },
    {
        "domain": "Both Engines",
        "description": "apps_rg bare pipeline contract modes and apps_lic multi-touch outreach pipeline execution",
        "test_files": [
            "resume_graph_engine/tests/unit/apps_rg/test_bare_pipeline_contract.py",
            "outreach_engine/tests/test_smoke_pipeline.py::test_orchestrator_e2e_pass",
            "outreach_engine/tests/test_smoke_pipeline.py::test_canonical_dispatch_channels_pass",
            "outreach_engine/tests/test_touch_sequence.py::test_touch_sequence_planner_generates_3_touch_cadence",
            "outreach_engine/tests/test_unified_cli.py::test_outreach_engine_canonical_run_and_inspection",
        ],
    },
    {
        "domain": "Integration Contracts",
        "description": "Inter-engine briefing handoffs, cryptographic sealing, SHA-256 artifact proofs, schema contracts",
        "test_files": [
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_stage_continuity_and_provenance",
            "outreach_engine/tests/test_managed_research_delegation.py::test_canonical_brief_resolution",
            "resume_graph_engine/tests/apps_research/test_contract.py",
            "outreach_engine/tests/test_modularity_and_config.py::test_root_exports_complete",
            "outreach_engine/tests/test_unified_cli.py::test_resume_engine_module_shims",
        ],
    },
    {
        "domain": "Failure Handling",
        "description": "Fail-closed stage termination, false-success prevention, retry exhaustion, idempotency gating, timeouts, tampered digests",
        "test_files": [
            "tests/unit/test_orchestration_runtime_hardening.py::test_false_success_prevention_dict_status_failed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_false_success_prevention_dict_exit_code_non_zero",
            "tests/unit/test_orchestration_runtime_hardening.py::test_missing_dependency_fails_closed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_retry_budget_exhaustion_terminates_failed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_non_transient_error_does_not_waste_retries",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_non_idempotent_operation_never_retries_on_transport_failure",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_idempotent_operation_retries_and_succeeds_within_ssot_budget",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_idempotent_operation_exhausts_budget_and_fails_closed",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_enforce_bounded_timeouts_prevents_unbounded_execution",
            "tests/unit/test_workflow_execution_engine_hardening.py::test_verify_no_redundant_provider_calls",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_stage_failure",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_resume_failure",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_outreach_failure",
            "outreach_engine/tests/test_managed_research_delegation.py::test_tampered_artifact_digest_fails_closed",
            "outreach_engine/tests/test_validators.py::test_grounding_validator_blocks_hallucinated_facts",
            "outreach_engine/tests/test_validators.py::test_forbidden_claims_validator_detects_compensation",
        ],
    },
]


def _resolve_pytest_cmd() -> list[str]:
    """Resolve pytest command across worktrees, shared main repository virtual environments, and system paths."""
    try:
        from tools.pr_governance_core.common import resolve_pytest

        resolved = resolve_pytest(_REPO_ROOT)
        if resolved:
            return resolved
    except (ImportError, OSError, RuntimeError, ValueError):  # guardian: allow-silent-swallow -- fallback to local venv resolution if helper import fails
        pass
    # 1. Local worktree venv
    venv_pytest = _REPO_ROOT / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return [str(venv_pytest)]
    # 2. Main repository venv from worktree (.worktrees/<slug>/../../.venv)
    parent_venv = _REPO_ROOT.parent.parent / ".venv" / "bin" / "pytest"
    if parent_venv.is_file():
        return [str(parent_venv)]
    # 3. Current python executable's sibling pytest
    sys_bin_pytest = Path(sys.executable).parent / "pytest"
    if sys_bin_pytest.is_file():
        return [str(sys_bin_pytest)]
    # 4. PATH lookup
    import shutil
    path_pytest = shutil.which("pytest")
    if path_pytest:
        return [path_pytest]
    # 5. sys.executable -m pytest fallback
    return [sys.executable, "-m", "pytest"]


def _extract_failures_from_output(stdout: str, stderr: str) -> list[dict[str, str]]:
    """Extract structured failure diagnostics from pytest output."""
    failures: list[dict[str, str]] = []
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if line_clean.startswith("FAILED "):
            target = line_clean[7:].split(" - ")[0].strip()
            msg = line_clean[7:].split(" - ")[1].strip() if " - " in line_clean else ""
            # Look ahead for exception message
            if not msg:
                for next_line in lines[i + 1 : i + 8]:
                    if next_line.strip().startswith("E   "):
                        msg = next_line.strip()[4:].strip()
                        break
            failures.append({
                "target": target,
                "error": msg or "Test failed",
            })
    if not failures and stderr:
        failures.append({"target": "pytest_runtime", "error": stderr.strip()})
    return failures


def run_health_checks(
    *,
    verbose: bool = False,
    domain_filter: str | None = None,
    domain_timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Execute curated health check suite with per-domain isolation, bounded timeouts, and exact diagnostics."""
    pytest_cmd = _resolve_pytest_cmd()

    domains_to_run = HEALTH_DOMAINS
    if domain_filter:
        domains_to_run = [d for d in HEALTH_DOMAINS if domain_filter.lower() in d["domain"].lower()]
        if not domains_to_run:
            raise ValueError(f"No health domain matched filter: '{domain_filter}'")

    domain_results: list[dict[str, Any]] = []
    total_passed = 0
    total_failed = 0
    all_failures: list[dict[str, Any]] = []
    t0_all = time.perf_counter()

    env = snapshot_process_env()

    for d in domains_to_run:
        dom_name = d["domain"]
        targets = d["test_files"]

        # Deduplicate targets while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                deduped.append(t)

        cmd = pytest_cmd + deduped + ["-v" if verbose else "-q", "--tb=short"]
        t_dom_start = time.perf_counter()

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=domain_timeout_seconds,
                check=False,
            )
            dom_duration = time.perf_counter() - t_dom_start
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            exit_code = proc.returncode

            dom_passed = 0
            dom_failed = 0
            for line in stdout.splitlines():
                if " passed" in line or " passed," in line:
                    parts = line.split()
                    for idx, p in enumerate(parts):
                        if (p.startswith("passed") or p.startswith("passed,")) and idx > 0 and parts[idx - 1].isdigit():
                            dom_passed = int(parts[idx - 1])
                        elif "passed" in p and p[:-6].isdigit():
                            dom_passed = int(p[:-6])
                        if (p.startswith("failed") or p.startswith("failed,")) and idx > 0 and parts[idx - 1].isdigit():
                            dom_failed = int(parts[idx - 1])

            dom_failures = _extract_failures_from_output(stdout, stderr) if exit_code != 0 else []
            dom_success = exit_code == 0

        except subprocess.TimeoutExpired as exc:
            dom_duration = time.perf_counter() - t_dom_start
            exit_code = 124
            dom_success = False
            dom_passed = 0
            dom_failed = len(deduped)
            dom_failures = [{
                "target": dom_name,
                "error": f"Domain checks timed out after {domain_timeout_seconds}s (bounded timeout enforced)",
            }]
            stdout = ""
            stderr = f"TimeoutExpired: Command exceeded {domain_timeout_seconds}s limit"

        total_passed += dom_passed
        total_failed += dom_failed
        for f in dom_failures:
            all_failures.append({
                "domain": dom_name,
                **f,
            })

        domain_results.append({
            "domain": dom_name,
            "description": d["description"],
            "checks_count": len(deduped),
            "tests_passed": dom_passed,
            "tests_failed": dom_failed,
            "status": "PASSED" if dom_success else "FAILED",
            "duration_seconds": round(dom_duration, 2),
            "exit_code": exit_code,
            "failures": dom_failures,
            "stdout": stdout if verbose else (stdout.splitlines()[-1] if stdout else ""),
            "stderr": stderr if exit_code != 0 else "",
        })

    total_duration = time.perf_counter() - t0_all
    overall_healthy = all(d["status"] == "PASSED" for d in domain_results)

    report = {
        "status": "HEALTHY" if overall_healthy else "UNHEALTHY",
        "exit_code": 0 if overall_healthy else 1,
        "duration_seconds": round(total_duration, 2),
        "domains_count": len(domain_results),
        "domains_passed": sum(1 for d in domain_results if d["status"] == "PASSED"),
        "domains_failed": sum(1 for d in domain_results if d["status"] == "FAILED"),
        "tests_passed": total_passed,
        "tests_failed": total_failed,
        "domains": domain_results,
        "failures": all_failures,
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m agents check",
        description="Fast, reliable local health-check command covering startup, orchestration, both engines, contracts, and failure handling.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose pytest execution details")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--domain", help="Filter by specific domain (e.g., startup, orchestration, engines, contracts, failure)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-domain bounded execution timeout in seconds (default: 60s)")

    args = parser.parse_args(argv)

    if not args.json:
        print("\n" + "=" * 68)
        print("SOVEREIGN AGENTIC PLATFORM: LOCAL ARCHITECTURAL HEALTH-CHECK")
        print("=" * 68)
        print("Domains Covered: Startup, Orchestration, Both Engines, Contracts, Fail-Closed")
        print("=" * 68 + "\n")

    t_start = time.perf_counter()
    try:
        report = run_health_checks(
            verbose=args.verbose,
            domain_filter=args.domain,
            domain_timeout_seconds=args.timeout,
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2))
        else:
            sys.stderr.write(f"\n[agents health] Error executing health-checks: {exc}\n")
        return 1

    t_elapsed = time.perf_counter() - t_start

    if args.json:
        print(json.dumps(report, indent=2))
        return report["exit_code"]

    for dom in report["domains"]:
        status_tag = "[PASS]" if dom["status"] == "PASSED" else "[FAIL]"
        print(f"  {status_tag} {dom['domain']:<22} ({dom['checks_count']} checks, {dom['duration_seconds']}s) - {dom['description']}")
        if dom["status"] == "FAILED" and dom.get("failures"):
            for fail in dom["failures"]:
                print(f"         \u2717 {fail['target']}: {fail['error']}")

    print("\n" + "-" * 68)
    if report["status"] == "HEALTHY":
        print(f"  RESULT: ALL HEALTH CHECKS PASSED ({report['duration_seconds']}s)")
        print(f"  Verified: Startup, Orchestration, Apps RG, Outreach Engine, Contracts, Fail-Closed")
        print("=" * 68 + "\n")
        return 0
    else:
        print(f"  RESULT: HEALTH CHECK FAILED ({report['duration_seconds']}s) - {report['domains_failed']} domain(s) failed")
        print("=" * 68 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
