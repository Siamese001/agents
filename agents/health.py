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
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

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
        "description": "WorkflowExecutionEngine DAG transitions, sequential lifecycle, terminal status immutability",
        "test_files": [
            "tests/unit/test_orchestration_runtime_hardening.py::test_workflow_execution_engine_positive_dag",
            "tests/unit/test_orchestration_runtime_hardening.py::test_terminal_statuses_immutability",
            "tests/unit/test_orchestration_runtime_hardening.py::test_pipeline_coordinator_release_rejection_sets_failed_phase",
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
        "description": "Fail-closed stage termination, false-success prevention, retry exhaustion, tampered digests, forbidden claims",
        "test_files": [
            "tests/unit/test_orchestration_runtime_hardening.py::test_false_success_prevention_dict_status_failed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_false_success_prevention_dict_exit_code_non_zero",
            "tests/unit/test_orchestration_runtime_hardening.py::test_missing_dependency_fails_closed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_retry_budget_exhaustion_terminates_failed",
            "tests/unit/test_orchestration_runtime_hardening.py::test_non_transient_error_does_not_waste_retries",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_stage_failure",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_resume_failure",
            "tests/unit/test_agents_cli_e2e.py::test_e2e_orchestrator_fails_closed_on_outreach_failure",
            "outreach_engine/tests/test_managed_research_delegation.py::test_tampered_artifact_digest_fails_closed",
            "outreach_engine/tests/test_validators.py::test_grounding_validator_blocks_hallucinated_facts",
            "outreach_engine/tests/test_validators.py::test_forbidden_claims_validator_detects_compensation",
        ],
    },
]


def _resolve_pytest_bin() -> str:
    venv_pytest = _REPO_ROOT / ".venv" / "bin" / "pytest"
    if venv_pytest.is_file():
        return str(venv_pytest)
    return "pytest"


def run_health_checks(
    *,
    verbose: bool = False,
    domain_filter: str | None = None,
) -> dict[str, Any]:
    """Execute curated health check suite and return structured results."""
    pytest_bin = _resolve_pytest_bin()

    domains_to_run = HEALTH_DOMAINS
    if domain_filter:
        domains_to_run = [d for d in HEALTH_DOMAINS if domain_filter.lower() in d["domain"].lower()]
        if not domains_to_run:
            raise ValueError(f"No health domain matched filter: '{domain_filter}'")

    all_targets: list[str] = []
    domain_targets: dict[str, list[str]] = {}
    for d in domains_to_run:
        targets = d["test_files"]
        domain_targets[d["domain"]] = targets
        all_targets.extend(targets)

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped_targets: list[str] = []
    for t in all_targets:
        if t not in seen:
            seen.add(t)
            deduped_targets.append(t)

    t0 = time.perf_counter()
    cmd = [pytest_bin] + deduped_targets + ["-v" if verbose else "-q", "--tb=short"]
    env = dict(os.environ)

    proc = subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    duration = time.perf_counter() - t0

    success = proc.returncode == 0
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    # Parse test outcomes from stdout
    passed_count = 0
    failed_count = 0
    for line in stdout.splitlines():
        if " passed" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p.startswith("passed") and i > 0 and parts[i - 1].isdigit():
                    passed_count = int(parts[i - 1])
                elif "passed" in p and p[:-6].isdigit():
                    passed_count = int(p[:-6])
                if p.startswith("failed") and i > 0 and parts[i - 1].isdigit():
                    failed_count = int(parts[i - 1])

    domain_results: list[dict[str, Any]] = []
    for d in domains_to_run:
        dom_name = d["domain"]
        domain_results.append({
            "domain": dom_name,
            "description": d["description"],
            "checks_count": len(d["test_files"]),
            "status": "PASSED" if success else "FAILED",
        })

    report = {
        "status": "HEALTHY" if success else "UNHEALTHY",
        "exit_code": proc.returncode,
        "duration_seconds": round(duration, 2),
        "total_targets": len(deduped_targets),
        "tests_passed": passed_count,
        "tests_failed": failed_count,
        "domains": domain_results,
        "stdout": stdout if verbose else (stdout.splitlines()[-1] if stdout else ""),
        "error_details": stderr if proc.returncode != 0 else "",
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

    args = parser.parse_args(argv)

    if not args.json:
        print("\n" + "=" * 68)
        print("SOVEREIGN AGENTIC PLATFORM: LOCAL ARCHITECTURAL HEALTH-CHECK")
        print("=" * 68)
        print("Domains Covered: Startup, Orchestration, Both Engines, Contracts, Fail-Closed")
        print("=" * 68 + "\n")

    t_start = time.perf_counter()
    try:
        report = run_health_checks(verbose=args.verbose, domain_filter=args.domain)
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
        print(f"  {status_tag} {dom['domain']:<22} ({dom['checks_count']} checks) - {dom['description']}")

    print("\n" + "-" * 68)
    if report["status"] == "HEALTHY":
        print(f"  RESULT: ALL HEALTH CHECKS PASSED ({report['duration_seconds']}s)")
        print(f"  Verified: Startup, Orchestration, Apps RG, Outreach Engine, Contracts, Fail-Closed")
        print("=" * 68 + "\n")
        return 0
    else:
        print(f"  RESULT: HEALTH CHECK FAILED ({report['duration_seconds']}s)")
        if report.get("stdout"):
            print(f"  {report['stdout']}")
        if report.get("error_details"):
            sys.stderr.write(f"\n{report['error_details']}\n")
        print("=" * 68 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
