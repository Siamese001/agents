"""Mechanical stage write-scope and subagent scope lease helpers (opt-in exclusive locks; full-repo root-cause writes)."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ALWAYS_ALLOWED_EPHEMERAL_PREFIXES: tuple[str, ...] = (
    "plans/",
    "artifacts/",
    "reports/",
    ".sidecar_active_run.lock",
)

PROMPT_STAGE_ALLOWED_WRITE_PATHS: dict[str, tuple[str, ...]] = {
    "agents-architecture-cost-governance": (
        ".agents/",
        ".antigravity/",
        ".env.example",
        ".gitattributes",
        ".githooks/",
        ".gitignore",
        ".local/",
        ".mcp.json",
        ".vscode/",
        "AGENTS.md",
        "README.md",
        "apps_model_telemetry/",
        "automations/prompts/_shared_governance_contract.md",
        "automations/prompts/agents_architecture_cost_agent.md",
        "config/adg_gate_fanin_map.yaml",
        "config/apps_spine_delegation_allowlist.yaml",
        "config/architectural_exceptions.yaml",
        "config/canonical_pipelines.yaml",
        "config/config_references_allowlist.yaml",
        "config/contracts/",
        "config/cross_app_import_allowlist.yaml",
        "config/crosswalk/",
        "config/dashboards/",
        "config/exception_contracts.yaml",
        "config/excluded_paths.yaml",
        "config/expected_wiring.yaml",
        "config/experimental_model_routing_recommendations.yaml",
        "config/governance/",
        "config/ledger_freshness_slo.yaml",
        "config/lifecycle_pairs.yaml",
        "config/model_catalog.json",
        "config/north_star_state.json",
        "config/notion_databases.yaml",
        "config/observability/",
        "config/otel/",
        "config/profiles/",
        "config/provider_profiles.yaml",
        "config/release_signer/",
        "config/routing/",
        "config/routing_thresholds.yaml",
        "config/runtime_budget_policy.yaml",
        "config/runtime_hitl_policy.yaml",
        "config/runtime_trace/",
        "config/sc_ap_config.json",
        "config/schemas/",
        "config/structure_blueprint/",
        "config/test_harness_coverage_allowlist.yaml",
        "config/token_budget.yaml",
        "config/wiring_dynamic_dispatch_anchors.yaml",
        "config/wiring_gate_waivers.yaml",
        "conftest.py",
        "docs/",
        "infrastructure/__init__.py",
        "infrastructure/config/",
        "infrastructure/device/",
        "infrastructure/live_execution.py",
        "infrastructure/live_governor.py",
        "infrastructure/reasoning/",
        "infrastructure/runtime/",
        "infrastructure/types/",
        "infrastructure/utils/",
        "outreach_engine/config/provider_profiles.yaml",
        "outreach_engine/pytest.ini",
        "pyproject.toml",
        "pytest.ini",
        "resume_graph_engine/config/models/",
        "resume_graph_engine/pytest.ini",
        "resume_graph_engine/src/apps_rg/cache/",
        "scripts/local_llm/",
        "tests/__init__.py",
        "tests/fixtures/",
        "tests/local_llm/",
        "tests/macbook_runtime/",
        "tests/test_governance_adversarial_redteam.py",
        "tests/test_implementation_plan_governance.py",
        "tests/test_model_neutral_naming.py",
        "tests/test_post_merge_cleanup.py",
        "tests/test_pr_merge_queue_governance.py",
        "tests/test_turn_gates.py",
        "tests/unit/",
        "tools/__init__.py",
        "tools/_standalone_boundary_naming.py",
        "tools/_standalone_graph_quality_gate.py",
        "tools/_standalone_plan_validator.py",
        "tools/_standalone_security_purity.py",
        "tools/_testing_gaps_helpers.py",
        "tools/adg_impact_tests.py",
        "tools/audit_governance_harmonization.py",
        "tools/audit_mock_reachability.py",
        "tools/audit_skills_budget.py",
        "tools/benchmark_macbook_runtime.py",
        "tools/change_lane_classifier.py",
        "tools/check_config_ssot_drift.py",
        "tools/cost_token_budget_auditor.py",
        "tools/cost_token_budget_governor_probes.py",
        "tools/cost_token_budget_probes.py",
        "tools/health_check.py",
        "tools/implementation_plan_core/",
        "tools/install_githooks.py",
        "tools/lint_architecture_boundaries.py",
        "tools/lint_commit_message.py",
        "tools/lint_contract_schemas.py",
        "tools/lint_layer_imports.py",
        "tools/lint_model_neutral_naming.py",
        "tools/lint_model_pins.py",
        "tools/lint_secrets.py",
        "tools/pr_governance.py",
        "tools/pr_governance_core/",
        "tools/prompt_scope_isolation.py",
        "tools/prune_merged_chat_worktrees.py",
        "tools/rebase_orchestrator.py",
        "tools/ssot_boundary_auditor.py",
        "tools/ssot_hardcoding_scanner.py",
        "tools/ssot_sprawl_scanner.py",
        "tools/storage_worktree_hygiene.py",
        "tools/testing_gaps_auditor.py",
        "tools/validate_implementation_plan.py",
        "tools/validate_sidecar_separation.py",
        "tools/validate_turn_gates.py",
        "tools/verify_commit.py",
        "tools/verify_main_readiness.py",
        "tools/verify_merge_receipt.py",
        "tools/verify_post_merge.py",
        "tools/zero_bugfix_constraint_gate.py",
        "uv.lock",
    ),
    "agents-core-runtime-orchestration": (
        "agents/__init__.py",
        "agents/__main__.py",
        "agents/_cli_helpers.py",
        "agents/cli.py",
        "agents/context/__init__.py",
        "agents/context/budgeting.py",
        "agents/e2e_artifacts.py",
        "agents/e2e_output.py",
        "agents/gateway/",
        "agents/health.py",
        "agents/learning_cli.py",
        "agents/live_preflight.py",
        "agents/observability/",
        "agents/orchestration/",
        "agents/persistence/",
        "agents/telemetry/",
        "automations/prompts/agents_core_runtime_orchestration_agent.md",
        "infrastructure/sdks_mcps/",
        "ops_scripts/agy_cli_transport.py",
        "tests/integration/",
        "tests/test_hitl_confidence_bayesian_scoring.py",
        "tests/test_hitl_governance_enforcement.py",
        "tests/test_hook_dispatch.py",
        "tests/test_unified_agent_architecture.py",
        "tools/agent_runtime_auditor.py",
        "tools/antigravity_sdk_hooks.py",
        "tools/characterize_runtime_routes.py",
        "tools/hitl_governance.py",
        "tools/hook_dispatch.py",
        "tools/snapshot_agent_learning_registry.py",
        "tools/unified_agent_architecture.py",
    ),
    "agents-graph-retrieval-qrels-assurance": (
        "agents/context/precedent_bridge.py",
        "agents/context/provenance.py",
        "apps_eval/qrels/",
        "automations/prompts/agents_graph_retrieval_qrels_agent.md",
        "config/retrieval/",
        "data/qrels/",
        "infrastructure/candidate_evidence/",
        "ops_scripts/build_qrels_benchmark.py",
        "ops_scripts/qrels_batch_runner.py",
        "ops_scripts/qrels_calibration_cli.py",
        "resume_graph_engine/C03_EMBEDDING_PRODUCTION_PROMOTION.md",
        "resume_graph_engine/artifacts/",
        "resume_graph_engine/config/retrieval/",
        "resume_graph_engine/src/apps_rg/chunking/",
        "resume_graph_engine/src/apps_rg/fact_inventory/",
        "tests/test_graph_hygiene_and_consolidation.py",
        "tests/test_sidecar_resume_graph_traversal.py",
        "tools/_retrieval_surface_helpers.py",
        "tools/apply_graph_hygiene_remediation.py",
        "tools/apps_rg_standalone/",
        "tools/audit_graph_hygiene_and_consolidation.py",
        "tools/audit_qrels_coverage.py",
        "tools/audit_resume_fact_provenance.py",
        "tools/graph_hygiene_judge_v3.py",
        "tools/retrieval_surface_auditor.py",
        "tools/run_resume_graph_traversal_probe.py",
        "tools/verify_graph_integrity_and_embeddings.py",
        "tools/verify_pipeline_latency_caching.py",
    ),
    "agents-research-intelligence-handoff": (
        "apps_research/",
        "automations/prompts/agents_research_intelligence_handoff_agent.md",
        "tests/test_governed_research_lineage.py",
        "tests/test_research_boundary_policy.py",
        "tests/test_research_retrieval_engine.py",
        "tools/apps_research_auditor.py",
    ),
    "agents-live-canary-release-certification": (
        "automations/prompts/agents_live_canary_release_certification_agent.md",
        "scripts/serve_agents_graph_portal.py",
        "tools/export_interactive_knowledge_graph.py",
        "tools/interactive_graph_export_core/",
        "tools/live_canary_release_auditor.py",
        "tools/mcp/",
        "tools/verify_graph_explorer_gate.py",
        "tools/verify_release_gate.py",
    ),
    "agents-domain-synthesis-pipelines": (
        "automations/prompts/agents_domain_synthesis_pipelines_agent.md",
        "data/fixtures/",
        "ops_scripts/apps_rg_overlap_replay.py",
        "ops_scripts/generation_parity_probe.py",
        "ops_scripts/run_e2e_authoritative_smoke.py",
        "outreach_engine/.antigravity/",
        "outreach_engine/AGENTS.md",
        "outreach_engine/README.md",
        "outreach_engine/__init__.py",
        "outreach_engine/__main__.py",
        "outreach_engine/config/candidate_profile.json",
        "outreach_engine/config/prompt_templates/",
        "outreach_engine/config/rubrics/",
        "outreach_engine/config/spam_trigger_phrases.py",
        "outreach_engine/config/targeting/",
        "outreach_engine/src/",
        "outreach_engine/tests/",
        "resume_engine/",
        "resume_graph_engine/.antigravity/",
        "resume_graph_engine/.gitattributes",
        "resume_graph_engine/.gitignore",
        "resume_graph_engine/AGENTS.md",
        "resume_graph_engine/MIGRATION_PROVENANCE.md",
        "resume_graph_engine/README.md",
        "resume_graph_engine/SOURCE_SYNC_RECEIPT.json",
        "resume_graph_engine/__init__.py",
        "resume_graph_engine/__main__.py",
        "resume_graph_engine/config/adg_gate_fanin_map.yaml",
        "resume_graph_engine/config/apps_spine_delegation_allowlist.yaml",
        "resume_graph_engine/config/architectural_exceptions.yaml",
        "resume_graph_engine/config/canonical_pipelines.yaml",
        "resume_graph_engine/config/config_references_allowlist.yaml",
        "resume_graph_engine/config/contracts/",
        "resume_graph_engine/config/cross_app_import_allowlist.yaml",
        "resume_graph_engine/config/crosswalk/",
        "resume_graph_engine/config/dashboards/",
        "resume_graph_engine/config/exception_contracts.yaml",
        "resume_graph_engine/config/excluded_paths.yaml",
        "resume_graph_engine/config/expected_wiring.yaml",
        "resume_graph_engine/config/ledger_freshness_slo.yaml",
        "resume_graph_engine/config/lifecycle_pairs.yaml",
        "resume_graph_engine/config/model_catalog.json",
        "resume_graph_engine/config/north_star_state.json",
        "resume_graph_engine/config/notion_databases.yaml",
        "resume_graph_engine/config/observability/",
        "resume_graph_engine/config/otel/",
        "resume_graph_engine/config/profiles/",
        "resume_graph_engine/config/prompt_governance/",
        "resume_graph_engine/config/quality/",
        "resume_graph_engine/config/release_signer/",
        "resume_graph_engine/config/routing/",
        "resume_graph_engine/config/routing_calibration.yaml",
        "resume_graph_engine/config/routing_thresholds.yaml",
        "resume_graph_engine/config/runtime_budget_policy.yaml",
        "resume_graph_engine/config/runtime_hitl_policy.yaml",
        "resume_graph_engine/config/runtime_trace/",
        "resume_graph_engine/config/sc_ap_config.json",
        "resume_graph_engine/config/schemas/",
        "resume_graph_engine/config/structure_blueprint/",
        "resume_graph_engine/config/test_harness_coverage_allowlist.yaml",
        "resume_graph_engine/config/token_budget.yaml",
        "resume_graph_engine/config/wiring_dynamic_dispatch_anchors.yaml",
        "resume_graph_engine/config/wiring_gate_waivers.yaml",
        "resume_graph_engine/docs/",
        "resume_graph_engine/src/apps_rg/AGENTIC_SPINE.md",
        "resume_graph_engine/src/apps_rg/AGENTS.md",
        "resume_graph_engine/src/apps_rg/HARDENING_REVIEW.md",
        "resume_graph_engine/src/apps_rg/LEAN_CORE.md",
        "resume_graph_engine/src/apps_rg/REFACTOR_MANIFEST.json",
        "resume_graph_engine/src/apps_rg/__init__.py",
        "resume_graph_engine/src/apps_rg/__main__.py",
        "resume_graph_engine/src/apps_rg/bare_pipeline.py",
        "resume_graph_engine/src/apps_rg/config/",
        "resume_graph_engine/src/apps_rg/config_root.py",
        "resume_graph_engine/src/apps_rg/contracts/",
        "resume_graph_engine/src/apps_rg/enforcement/",
        "resume_graph_engine/src/apps_rg/engines/",
        "resume_graph_engine/src/apps_rg/exit/",
        "resume_graph_engine/src/apps_rg/hitl/",
        "resume_graph_engine/src/apps_rg/integrations/",
        "resume_graph_engine/src/apps_rg/l2_recipe/",
        "resume_graph_engine/src/apps_rg/prerequisites/",
        "resume_graph_engine/src/apps_rg/profiles/",
        "resume_graph_engine/src/apps_rg/prompt_assembly/",
        "resume_graph_engine/src/apps_rg/prompt_governance/",
        "resume_graph_engine/src/apps_rg/repository_layout.py",
        "resume_graph_engine/src/apps_rg/resume/",
        "resume_graph_engine/src/apps_rg/rg_evidence_profile.yaml",
        "resume_graph_engine/src/apps_rg/rg_output_schema.json",
        "resume_graph_engine/src/apps_rg/rg_prompt_profile.yaml",
        "resume_graph_engine/src/apps_rg/rg_style_profile.yaml",
        "resume_graph_engine/src/apps_rg/runtime/",
        "resume_graph_engine/src/apps_rg/scripts/",
        "resume_graph_engine/src/apps_rg/spine_manifest.yaml",
        "resume_graph_engine/src/apps_rg/tools/",
        "resume_graph_engine/src/apps_rg/types/",
        "resume_graph_engine/src/apps_rg/utils/",
        "resume_graph_engine/src/apps_standalone_import_guard.py",
        "resume_graph_engine/tests/",
        "resume_graph_engine/tools/",
        "tools/e2e_functionality_auditor.py",
        "tools/lint_apps_rg_domain_literals.py",
        "tools/lint_no_jd_overfitting.py",
        "tools/lint_prompt_validator_vocab_symmetry.py",
    ),
    "agents-evals-flywheel-assurance": (
        "agents/eval_flywheel_cli.py",
        "agents/learning/",
        "apps_eval/README.md",
        "apps_eval/__init__.py",
        "apps_eval/__main__.py",
        "apps_eval/_core_governance_bridge.py",
        "apps_eval/_telemetry.py",
        "apps_eval/_write_gateway.py",
        "apps_eval/adapters/",
        "apps_eval/artifacts/",
        "apps_eval/baselines/",
        "apps_eval/baselines.py",
        "apps_eval/bootstrap_baselines.py",
        "apps_eval/cli.py",
        "apps_eval/construct_validity.py",
        "apps_eval/contracts/",
        "apps_eval/coverage/",
        "apps_eval/diagnostics/",
        "apps_eval/fixtures/",
        "apps_eval/golden_suite_runner.py",
        "apps_eval/graders/",
        "apps_eval/harness_orchestrator.py",
        "apps_eval/holdout_replay.py",
        "apps_eval/integrations/",
        "apps_eval/l6_eval_ladder.py",
        "apps_eval/l6_shadow_bridge.py",
        "apps_eval/longitudinal.py",
        "apps_eval/matrix.py",
        "apps_eval/online_grader.py",
        "apps_eval/outputs/",
        "apps_eval/pareto.py",
        "apps_eval/promotion_gate.py",
        "apps_eval/registries/",
        "apps_eval/registry/",
        "apps_eval/resources.py",
        "apps_eval/rubrics/",
        "apps_eval/runner/",
        "apps_eval/sandbox/",
        "apps_eval/scenarios.py",
        "apps_eval/suites/",
        "apps_eval/tests/",
        "apps_eval/trends.py",
        "apps_eval/triage_promoter.py",
        "automations/prompts/agents_evals_flywheel_assurance_agent.md",
        "config/certification/",
        "config/exit_eval_rubrics/",
        "config/judges/",
        "config/prompt_governance/",
        "config/routing_calibration.yaml",
        "data/certification/",
        "data/eval/",
        "data/holdout/",
        "data/judge_calibration/",
        "ops_scripts/blind_human_grading_cli.py",
        "ops_scripts/ci/",
        "ops_scripts/curate_ide_judge_gold_corpus.py",
        "ops_scripts/judge_parity_probe.py",
        "ops_scripts/mark_stub_judge_artifacts.py",
        "ops_scripts/run_ide_judge_drift.py",
        "outreach_engine/data/",
        "resume_graph_engine/config/certification/",
        "resume_graph_engine/config/exit_eval_rubrics/",
        "resume_graph_engine/config/judges/",
        "resume_graph_engine/data/",
        "resume_graph_engine/src/apps_rg/evals/",
        "tests/adversarial/",
        "tests/end_to_end/",
        "tests/test_evals_adversarial_redteam.py",
        "tools/_eval_rubrics_helpers.py",
        "tools/audit_eval_construct_validity.py",
        "tools/audit_multi_ssot_judge_gate_drift.py",
        "tools/eval_shield_core/",
        "tools/govern_eval_findings.py",
        "tools/lint_production_purity.py",
        "tools/loophole_redteam_auditor.py",
        "tools/run_diff_scoped_eval_shield.py",
        "tools/run_eval_flywheel_cycle.py",
        "tools/validate_eval_rubrics.py",
        "tools/validate_judge_rubrics_v3.py",
        "tools/verify_fix_eval_pinning.py",
    ),
}


def _normalize_token(raw_path: str) -> str:
    cleaned = raw_path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.strip("/")


def paths_overlap(path_a: str, path_b: str) -> bool:
    """Return True when two relative file or directory prefixes intersect."""
    norm_a = _normalize_token(path_a)
    norm_b = _normalize_token(path_b)
    if norm_a in ("", ".", "*") or norm_b in ("", ".", "*"):
        return True
    return norm_a == norm_b or norm_b.startswith(f"{norm_a}/") or norm_a.startswith(f"{norm_b}/")


def _resolve_repo_relative_path(target_file: Path | str, repo_root: Path) -> str | None:
    candidate = Path(target_file)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    for base, target in ((repo_root, candidate), (repo_root.resolve(), candidate.resolve())):
        try:
            return target.relative_to(base).as_posix()
        except ValueError:  # guardian: allow-silent-swallow -- retry with resolved symlink paths
            continue
    return None


def _resolve_common_git_root(repo_root: Path) -> Path:
    resolved = repo_root.resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            git_common = Path(proc.stdout.strip())
            if git_common.name == ".git":
                return git_common.parent.resolve()
    except (OSError, subprocess.SubprocessError):  # guardian: allow-silent-swallow -- non-git temp dirs fall back cleanly
        pass
    return resolved


ACTIVE_STAGE_LEASES_FILENAME = "active_stage_leases.json"
ACTIVE_STAGE_LEASES_LOCK_FILENAME = "active_stage_leases.lock"
DEFAULT_STAGE_LEASE_TTL_SECONDS = 7200.0


def validate_stage_full_repo_coverage(
    repo_root: Path,
    stage_paths: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Return violations if any tracked repository file is not covered by ephemeral prefixes or a stage owner."""
    mapping = stage_paths if stage_paths is not None else PROMPT_STAGE_ALLOWED_WRITE_PATHS
    resolved_root = repo_root.resolve()
    if not (resolved_root / "tools").is_dir():
        return []
    try:
        proc = subprocess.run(
            ["git", "-C", str(resolved_root), "ls-files", "-z"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if proc.returncode != 0 or not proc.stdout:
            return []
        tracked = [raw.decode("utf-8", errors="replace") for raw in proc.stdout.split(b"\x00") if raw]
    except (OSError, subprocess.SubprocessError):
        return []

    all_prefixes = tuple(p for prefs in mapping.values() for p in prefs)
    uncovered: list[str] = []
    for rel_path in tracked:
        if any(paths_overlap(rel_path, ep) for ep in ALWAYS_ALLOWED_EPHEMERAL_PREFIXES):
            continue
        if any(paths_overlap(rel_path, pref) for pref in all_prefixes):
            continue
        uncovered.append(rel_path)

    return [f"STAGE_WRITE_PATH_UNCOVERED: tracked file '{rel}' has no stage owner" for rel in uncovered[:50]]


def validate_stage_ownership_disjointness(
    repo_root: Path | None = None,
    stage_paths: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Return violations if any two stages overlap in write paths, declare missing paths, or leave tracked files uncovered."""
    mapping = stage_paths if stage_paths is not None else PROMPT_STAGE_ALLOWED_WRITE_PATHS
    violations: list[str] = []
    agents = list(mapping.keys())
    for i in range(len(agents)):
        for j in range(i + 1, len(agents)):
            a, b = agents[i], agents[j]
            for pa in mapping[a]:
                for pb in mapping[b]:
                    if paths_overlap(pa, pb):
                        violations.append(
                            f"STAGE_WRITE_PATH_OVERLAP: '{a}' ('{pa}') overlaps '{b}' ('{pb}')"
                        )
    if repo_root is not None:
        resolved_root = repo_root.resolve()
        if (resolved_root / "tools" / "prompt_scope_isolation.py").is_file():
            for agent_id, paths in mapping.items():
                for raw_path in paths:
                    if not (resolved_root / raw_path).exists():
                        violations.append(
                            f"STAGE_WRITE_PATH_MISSING: '{agent_id}' declares nonexistent path '{raw_path}'"
                        )
            if stage_paths is None:
                violations.extend(validate_stage_full_repo_coverage(resolved_root, mapping))
    return violations


@contextmanager
def _stage_lease_registry_lock(gov_dir: Path) -> Iterator[Path]:
    gov_dir.mkdir(parents=True, exist_ok=True)
    lock_path = gov_dir / ACTIVE_STAGE_LEASES_LOCK_FILENAME
    registry_path = gov_dir / ACTIVE_STAGE_LEASES_FILENAME
    with open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield registry_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_active_stage_leases(registry_path: Path, now_ts: float) -> list[dict[str, Any]]:
    if not registry_path.is_file():
        return []
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # guardian: allow-silent-swallow -- treat corrupt stage lease JSON as empty
        return []
    leases = raw.get("leases", []) if isinstance(raw, dict) else []
    active: list[dict[str, Any]] = []
    for entry in leases:
        if not isinstance(entry, dict) or float(entry.get("expires_at", 0.0)) <= now_ts:
            continue
        owner_pid = int(entry.get("owner_pid", 0) or 0)
        if owner_pid > 0 and not _is_pid_alive(owner_pid):
            # Keep newly created subprocess leases alive only while worktree still exists on disk
            wt_str = str(entry.get("worktree_dir") or "").strip()
            if not wt_str or not Path(wt_str).is_dir():
                continue
        active.append(entry)
    return active


def register_active_stage_lease(
    repo_root: Path,
    agent_id: str,
    branch_name: str,
    worktree_dir: Path | str,
    *,
    owner_pid: int | None = None,
    ttl_seconds: float = DEFAULT_STAGE_LEASE_TTL_SECONDS,
    now_ts: float | None = None,
) -> dict[str, Any]:
    """Atomically register an active automation stage lease for parallel collision prevention."""
    clean_agent = agent_id.strip()
    clean_branch = branch_name.strip()
    if not clean_agent:
        raise ValueError("agent_id must be non-empty")
    ts = float(now_ts if now_ts is not None else time.time())
    ttl = max(60.0, min(float(ttl_seconds), 28800.0))
    wt_resolved = str(Path(worktree_dir).resolve())
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    pid = int(owner_pid) if isinstance(owner_pid, int) and owner_pid > 0 else os.getpid()
    record = {
        "agent_id": clean_agent,
        "branch": clean_branch,
        "worktree_dir": wt_resolved,
        "owner_pid": pid,
        "started_at": ts,
        "expires_at": ts + ttl,
    }
    with _stage_lease_registry_lock(gov_dir) as registry_path:
        active = _load_active_stage_leases(registry_path, ts)
        updated = [
            e
            for e in active
            if not (
                e.get("agent_id") == clean_agent
                and (e.get("branch") == clean_branch or e.get("worktree_dir") == wt_resolved)
            )
        ]
        updated.append(record)
        _write_leases_atomic(registry_path, updated)
    return record


def release_active_stage_lease(
    repo_root: Path,
    *,
    agent_id: str | None = None,
    branch_name: str | None = None,
    worktree_dir: Path | str | None = None,
) -> int:
    """Release matching active automation stage lease(s); returns number removed."""
    clean_agent = (agent_id or "").strip()
    clean_branch = (branch_name or "").strip()
    clean_wt = str(Path(worktree_dir).resolve()) if worktree_dir else ""
    if not any((clean_agent, clean_branch, clean_wt)):
        return 0
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    with _stage_lease_registry_lock(gov_dir) as registry_path:
        active = _load_active_stage_leases(registry_path, time.time())
        remaining: list[dict[str, Any]] = []
        removed = 0
        for entry in active:
            match_branch = bool(clean_branch and entry.get("branch") == clean_branch)
            match_wt = bool(clean_wt and entry.get("worktree_dir") == clean_wt)
            match_agent_only = bool(clean_agent and not clean_branch and not clean_wt and entry.get("agent_id") == clean_agent)
            if match_branch or match_wt or match_agent_only:
                removed += 1
            else:
                remaining.append(entry)
        if removed:
            _write_leases_atomic(registry_path, remaining)
    return removed


def list_active_stage_leases(repo_root: Path, *, now_ts: float | None = None) -> list[dict[str, Any]]:
    """Return currently active automation stage leases across all worktrees of the repository."""
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    registry_path = gov_dir / ACTIVE_STAGE_LEASES_FILENAME
    if not registry_path.is_file():
        return []
    ts = float(now_ts if now_ts is not None else time.time())
    with _stage_lease_registry_lock(gov_dir) as locked_path:
        return _load_active_stage_leases(locked_path, ts)


def has_active_stage_lease_for_worktree(
    repo_root: Path,
    wt_path: Path | str,
    *,
    now_ts: float | None = None,
) -> bool:
    """Return True if wt_path currently holds a live entry in active_stage_leases.json."""
    target = str(Path(wt_path).resolve())
    for entry in list_active_stage_leases(repo_root, now_ts=now_ts):
        if str(entry.get("worktree_dir") or "") == target:
            return True
    return False


def evaluate_prompt_stage_write_scope(
    target_file: Path | str,
    repo_root: Path,
    agent_id: str | None = None,
    *,
    now_ts: float | None = None,
) -> tuple[bool, str]:
    """Return (blocked, reason) if an active agents-* stage collides with a running peer stage's owned paths."""
    effective_id = (agent_id if agent_id is not None else os.environ.get("AGY_SIDECAR_AGENT_ID", "")).strip()
    if not effective_id:
        return False, "no active sidecar agent stage"

    rel = _resolve_repo_relative_path(target_file, repo_root)
    if rel is None:
        return False, "target outside repository root"

    for prefix in ALWAYS_ALLOWED_EPHEMERAL_PREFIXES:
        if paths_overlap(rel, prefix):
            return False, f"ephemeral stage artifact path '{rel}' allowed"

    allowed = PROMPT_STAGE_ALLOWED_WRITE_PATHS.get(effective_id)
    if allowed is not None:
        for prefix in allowed:
            if paths_overlap(rel, prefix):
                return False, f"allowed within stage scope '{effective_id}'"

    strict_parallel = os.environ.get("AGY_PARALLEL_STAGE_STRICT", "").strip() == "1"
    active_peers: set[str] = set()
    if strict_parallel:
        active_peers = {peer for peer in PROMPT_STAGE_ALLOWED_WRITE_PATHS if peer != effective_id}
    else:
        for lease in list_active_stage_leases(repo_root, now_ts=now_ts):
            peer_id = str(lease.get("agent_id") or "").strip()
            if peer_id and peer_id != effective_id:
                active_peers.add(peer_id)

    for peer_id in sorted(active_peers):
        for peer_prefix in PROMPT_STAGE_ALLOWED_WRITE_PATHS.get(peer_id, ()):
            if paths_overlap(rel, peer_prefix):
                return (
                    True,
                    (
                        f"PARALLEL_STAGE_OWNERSHIP_CONFLICT: stage '{effective_id}' cannot modify '{rel}' "
                        f"because active peer stage '{peer_id}' owns '{peer_prefix}'"
                    ),
                )

    return False, f"allowed root-cause cross-repo write for stage '{effective_id}' on '{rel}'"


@contextmanager
def _scope_registry_lock(gov_dir: Path) -> Iterator[Path]:
    gov_dir.mkdir(parents=True, exist_ok=True)
    lock_path = gov_dir / "active_subagent_scopes.lock"
    registry_path = gov_dir / "active_subagent_scopes.json"
    with open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield registry_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def resolve_persistent_caller_pid() -> int:
    """Resolve persistent parent/host PID across direct subprocesses and transient '-c' shell wrappers."""
    env_pid = os.environ.get("AGY_HOST_PID", "").strip()
    if env_pid.isdigit() and int(env_pid) > 1:
        return int(env_pid)
    pid = os.getppid() if os.getppid() > 1 else os.getpid()
    for _ in range(4):
        if pid <= 1:
            break
        try:
            proc = subprocess.run(
                ["ps", "-o", "ppid=,comm=,args=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
            line = proc.stdout.strip()
            if not line:
                break
            parts = line.split(None, 2)
            ppid = int(parts[0])
            comm = os.path.basename(parts[1]) if len(parts) > 1 else ""
            cmd_args = parts[2] if len(parts) > 2 else ""
            if comm in ("sh", "bash", "zsh", "dash") and " -c " in f" {cmd_args} " and ppid > 1:
                pid = ppid
                continue
        except (OSError, subprocess.SubprocessError, ValueError):  # guardian: allow-silent-swallow -- fallback to current ppid
            pass
        break
    return pid


def is_subagent_turn(steps: list[dict[str, Any]], payload: dict[str, Any] | None = None) -> bool:
    """Return True when post_invocation is evaluating a delegated /boost or /swarm subagent turn."""
    if os.environ.get("AGY_SUBAGENT_TASK_ID", "").strip():
        return True
    if isinstance(payload, dict) and bool(payload.get("is_subagent", False)):
        return True
    for step in steps:
        if not isinstance(step, dict):
            continue
        content = str(step.get("content") or "")
        if "<subagent_reminder>" in content or ("<SYSTEM_MESSAGE>" in content and "sender=" in content and "<original_task>" in content):
            return True
        tcs = step.get("tool_calls") or step.get("toolCalls") or ([] if not step.get("toolCall") else [step["toolCall"]])
        for tc in tcs:
            if isinstance(tc, dict):
                tname = str(tc.get("name") or tc.get("tool_name") or "").split(":")[-1]
                if tname == "send_message":
                    return True
    return False


def _load_active_leases(registry_path: Path, now_ts: float) -> list[dict[str, Any]]:
    if not registry_path.is_file():
        return []
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # guardian: allow-silent-swallow -- treat corrupt lease JSON as empty
        return []
    leases = raw.get("leases", []) if isinstance(raw, dict) else []
    active: list[dict[str, Any]] = []
    for entry in leases:
        if not isinstance(entry, dict) or float(entry.get("expires_at", 0.0)) <= now_ts:
            continue
        owner_pid = int(entry.get("owner_pid", 0) or 0)
        if owner_pid > 0 and not _is_pid_alive(owner_pid):
            continue
        active.append(entry)
    return active


def _write_leases_atomic(registry_path: Path, leases: list[dict[str, Any]]) -> None:
    payload = json.dumps({"leases": leases}, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=".scopes_", suffix=".tmp", dir=str(registry_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, registry_path)
    except Exception:  # guardian: allow-broad-exception-cleanup -- clean temp file before re-raising
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def register_and_check_subagent_scope(
    repo_root: Path,
    contract: dict[str, Any],
    *,
    workspace_mode: str = "inherit",
    check_cross_workspace: bool = False,
    now_ts: float | None = None,
    owner_pid: int | None = None,
) -> tuple[bool, str, str]:
    """Register a subagent delegation scope lease (opt-in exclusive_lock / enforce_strict_scope)."""
    task_id = str(contract.get("task_id", "")).strip()
    if not task_id:
        return False, "DELEGATION_VIOLATION: missing non-empty task_id", ""

    mode = (workspace_mode or "inherit").strip().lower()
    enforce_cross = bool(check_cross_workspace or contract.get("preauth_manifest_id") or contract.get("check_cross_workspace"))
    if mode not in ("", "inherit") and not enforce_cross:
        return True, f"isolated workspace mode '{mode}' bypasses shared workspace contention", task_id

    ts = float(now_ts if now_ts is not None else time.time())
    budget = contract.get("budget") if isinstance(contract.get("budget"), dict) else {}
    timeout_s = float(budget.get("timeout_seconds", 1800.0) or 1800.0)
    ttl = max(60.0, min(timeout_s, 7200.0))
    scope_in = [str(p) for p in contract.get("scope_in", []) if str(p).strip()]
    scope_out = [str(p) for p in contract.get("scope_out", []) if str(p).strip()]
    workspace_key = str(repo_root.resolve())
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    raw_owner_pid = contract.get("owner_pid") if owner_pid is None else owner_pid
    effective_owner_pid = int(raw_owner_pid) if isinstance(raw_owner_pid, int) and raw_owner_pid > 0 else os.getpid()

    with _scope_registry_lock(gov_dir) as registry_path:
        active = _load_active_leases(registry_path, ts)
        exclusive_lock = bool(contract.get("exclusive_lock", False))
        if exclusive_lock:
            for existing in active:
                if existing.get("task_id") == task_id:
                    continue
                if not enforce_cross and existing.get("workspace_root") != workspace_key:
                    continue
                if not bool(existing.get("exclusive_lock", False)):
                    continue
                for new_path in scope_in:
                    for held_path in existing.get("scope_in", []):
                        if paths_overlap(new_path, str(held_path)):
                            return (
                                False,
                                (
                                    f"PARALLEL_SUBAGENT_SCOPE_CONFLICT: '{task_id}' scope_in '{new_path}' "
                                    f"overlaps active subagent '{existing.get('task_id')}' ('{held_path}')"
                                ),
                                task_id,
                            )
        updated = [entry for entry in active if entry.get("task_id") != task_id]
        lease_record = {
            "task_id": task_id,
            "owner_pid": effective_owner_pid,
            "workspace_root": workspace_key,
            "workspace_mode": mode or "inherit",
            "scope_in": scope_in,
            "scope_out": scope_out,
            "exclusive_lock": exclusive_lock,
            "enforce_strict_scope": bool(contract.get("enforce_strict_scope", False)),
            "expires_at": ts + ttl,
        }
        updated.append(lease_record)
        _write_leases_atomic(registry_path, updated)
    return True, "registered active subagent scope", task_id


def release_subagent_scope(repo_root: Path, task_id: str) -> bool:
    """Release an active subagent scope lease by task_id."""
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    with _scope_registry_lock(gov_dir) as registry_path:
        active = _load_active_leases(registry_path, time.time())
        remaining = [entry for entry in active if entry.get("task_id") != task_id]
        if len(remaining) == len(active):
            return False
        _write_leases_atomic(registry_path, remaining)
    return True


def _resolve_worktree_lease_task_id(repo_root: Path) -> str:
    env_tid = os.environ.get("AGY_SUBAGENT_TASK_ID", "").strip()
    if env_tid:
        return env_tid
    try:
        git_marker = repo_root / ".git"
        git_dir = git_marker
        if git_marker.is_file():
            raw = git_marker.read_text(encoding="utf-8").strip()
            if raw.startswith("gitdir:"):
                git_dir = Path(raw.split("gitdir:", 1)[1].strip())
                if not git_dir.is_absolute():
                    git_dir = (repo_root / git_dir).resolve()
        lease_file = git_dir / "agy_active_lease.json"
        if lease_file.is_file():
            data = json.loads(lease_file.read_text(encoding="utf-8"))
            return str(data.get("task_id", "")).strip()
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return ""


def evaluate_active_subagent_write_scope(
    target_file: Path | str,
    repo_root: Path,
    task_id: str | None = None,
    *,
    now_ts: float | None = None,
    is_subagent_caller: bool = False,
) -> tuple[bool, str]:
    """Return (blocked, reason) if target_file violates active subagent scope_in/scope_out leases."""
    rel = _resolve_repo_relative_path(target_file, repo_root)
    if rel is None:
        return False, "target outside repository root"

    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"
    registry_path = gov_dir / "active_subagent_scopes.json"
    if not registry_path.is_file():
        return False, "no active subagent leases"

    ts = float(now_ts if now_ts is not None else time.time())
    workspace_key = str(repo_root.resolve())
    effective_task_id = (task_id if task_id is not None else _resolve_worktree_lease_task_id(repo_root)).strip()
    with _scope_registry_lock(gov_dir) as locked_path:
        active = [e for e in _load_active_leases(locked_path, ts) if e.get("workspace_root") == workspace_key]

    if not effective_task_id and is_subagent_caller:
        exclusive_entries = [e for e in active if bool(e.get("exclusive_lock", False))]
        if len(exclusive_entries) == 1:
            effective_task_id = str(exclusive_entries[0].get("task_id", "")).strip()

    own_lease: dict[str, Any] | None = None
    for entry in active:
        tid = str(entry.get("task_id", ""))
        if effective_task_id and tid == effective_task_id:
            own_lease = entry
            continue
        if not bool(entry.get("exclusive_lock", False)):
            continue
        for held in entry.get("scope_in", []):
            if paths_overlap(rel, str(held)):
                return True, f"SUBAGENT_SCOPE_CONFLICT: '{rel}' is leased to active subagent '{tid}'"

    if own_lease is not None and bool(own_lease.get("enforce_strict_scope", False)):
        for forbidden in own_lease.get("scope_out", []):
            if paths_overlap(rel, str(forbidden)):
                return True, f"SUBAGENT_SCOPE_VIOLATION: '{rel}' matches scope_out '{forbidden}' for '{effective_task_id}'"
        scope_in = own_lease.get("scope_in", [])
        if scope_in and not any(paths_overlap(rel, str(allowed)) for allowed in scope_in):
            return True, f"SUBAGENT_SCOPE_VIOLATION: '{rel}' is outside scope_in for '{effective_task_id}'"

    return False, "subagent write scope allowed"


def _sync_teamwork_request_atomic(repo_root: Path, prompt_text: str, run_id: str | None = None) -> None:
    """Atomically sync .agents/teamwork/ORIGINAL_REQUEST.md and optional per-run request file."""
    effective_run = (run_id or os.environ.get("AGY_TEAMWORK_RUN_ID", "")).strip()
    targets = [repo_root / ".agents" / "teamwork" / "ORIGINAL_REQUEST.md"]
    if effective_run:
        targets.append(repo_root / ".agents" / "teamwork" / "runs" / effective_run / "ORIGINAL_REQUEST.md")
    for orig_req in targets:
        try:
            orig_req.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".orig_req_", suffix=".tmp", dir=str(orig_req.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(f"{prompt_text}\n")
                os.replace(tmp_name, orig_req)
            except Exception:  # guardian: allow-broad-exception-cleanup -- clean temp file before re-raising
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
                raise
        except OSError:  # guardian: allow-silent-swallow -- best-effort atomic teamwork request sync
            pass
