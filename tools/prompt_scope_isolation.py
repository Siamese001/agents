"""Mechanical stage write-scope and parallel subagent scope isolation guards."""

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
    "agents-storage-worktree-hygiene": (
        "tools/storage_worktree_hygiene.py",
        "tools/prune_merged_chat_worktrees.py",
        "tools/pr_governance.py",
        "tools/pr_governance_core/",
        ".gitignore",
        "automations/prompts/agents_storage_worktree_hygiene_agent.md",
        "tests/unit/test_storage_hygiene_full_repo_remediation.py",
        "tests/unit/test_sidecar_separation_governance.py",
        "tests/test_post_merge_cleanup.py",
        "tests/test_prune_merged_chat_worktrees_stub_and_manifest.py",
        "tests/test_pr_merge_queue_governance.py",
    ),
    "agents-ssot-boundary-governance": (
        "config/",
        "infrastructure/",
        "data/",
        ".mcp.json",
        "pytest.ini",
        "AGENTS.md",
        ".agents/",
        ".antigravity/",
        "automations/",
        "tools/ssot_boundary_auditor.py",
        "tools/check_config_ssot_drift.py",
        "tools/lint_architecture_boundaries.py",
        "tools/lint_layer_imports.py",
        "tools/ssot_sprawl_scanner.py",
        "tools/validate_sidecar_separation.py",
        "tools/validate_turn_gates.py",
        "tools/verify_commit.py",
        "tools/lint_file_budgets.py",
        "tools/prompt_scope_isolation.py",
        "outreach_engine/config/",
        "resume_engine/config/",
        "resume_graph_engine/config/",
        "apps_research/config/",
        "tests/unit/test_sidecar_separation_governance.py",
        "tests/unit/test_ssot_boundary_governance.py",
        "tests/test_turn_gates.py",
    ),
    "agents-core-runtime-orchestration": (
        "agents/",
        "tools/agent_runtime_auditor.py",
        "tools/unified_agent_architecture.py",
        "tools/hook_dispatch.py",
        "tools/hitl_governance.py",
        "automations/prompts/agents_core_runtime_orchestration_agent.md",
        "tests/unit/test_agent_runtime_orchestration.py",
        "tests/test_unified_agent_architecture.py",
        "tests/test_hook_dispatch.py",
        "tests/test_hitl_governance_enforcement.py",
    ),
    "agents-domain-applications-pipeline": (
        "outreach_engine/",
        "resume_engine/",
        "resume_graph_engine/src/",
        "ops_scripts/",
        "scripts/",
        "tools/e2e_functionality_auditor.py",
        "automations/prompts/agents_domain_applications_pipeline_agent.md",
        "tests/e2e/",
        "resume_graph_engine/tests/",
    ),
    "agents-research-retrieval-surface": (
        "apps_research/",
        "agents/context/",
        "tools/retrieval_surface_auditor.py",
        "tools/verify_graph_integrity_and_embeddings.py",
        "automations/prompts/agents_research_retrieval_surface_agent.md",
        "resume_graph_engine/src/apps_rg/runtime/quad_graph_retriever.py",
        "resume_graph_engine/tests/apps_research/",
        "tests/unit/test_retrieval_surface_governance.py",
    ),
    "agents-evals-judge-assurance": (
        "apps_eval/",
        "config/eval_rubrics/",
        "resume_graph_engine/config/eval_rubrics/",
        "outreach_engine/config/eval_rubrics/",
        "resume_engine/config/eval_rubrics/",
        "apps_research/config/eval_rubrics/",
        "tools/validate_eval_rubrics.py",
        "tools/lint_production_purity.py",
        "automations/prompts/agents_evals_judge_assurance_agent.md",
        "tests/unit/test_evals_and_budget_full_parity.py",
    ),
    "agents-cost-token-budget": (
        "apps_model_telemetry/",
        "config/provider_profiles.yaml",
        "tools/cost_token_budget_auditor.py",
        "tools/model_routing.py",
        "automations/prompts/agents_cost_token_budget_agent.md",
        "tests/unit/test_evals_and_budget_full_parity.py",
        "tests/unit/test_model_neutral_naming.py",
    ),
    "agents-testing-gaps-assurance": (
        "tests/",
        "resume_graph_engine/tests/",
        "outreach_engine/tests/",
        "resume_engine/tests/",
        "apps_eval/tests/",
        "apps_research/tests/",
        ".githooks/",
        "tools/testing_gaps_auditor.py",
        "tools/audit_mock_reachability.py",
        "tools/lint_pytest_integrity.py",
        "automations/prompts/agents_testing_gaps_assurance_agent.md",
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


def evaluate_prompt_stage_write_scope(
    target_file: Path | str,
    repo_root: Path,
    agent_id: str | None = None,
) -> tuple[bool, str]:
    """Return (blocked, reason) if an active agents-* stage writes outside its declared scope."""
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
    if allowed is None:
        return True, f"PROMPT_STAGE_SCOPE_VIOLATION: unknown agent_id '{effective_id}' cannot modify '{rel}'"

    for prefix in allowed:
        if paths_overlap(rel, prefix):
            return False, f"allowed within stage scope '{effective_id}'"

    return True, f"PROMPT_STAGE_SCOPE_VIOLATION: stage '{effective_id}' cannot modify '{rel}'"


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


def _load_active_leases(registry_path: Path, now_ts: float) -> list[dict[str, Any]]:
    if not registry_path.is_file():
        return []
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # guardian: allow-silent-swallow -- treat corrupt lease JSON as empty
        return []
    leases = raw.get("leases", []) if isinstance(raw, dict) else []
    return [entry for entry in leases if isinstance(entry, dict) and float(entry.get("expires_at", 0.0)) > now_ts]


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
    now_ts: float | None = None,
) -> tuple[bool, str, str]:
    """Register a subagent delegation scope lease and fail closed on overlapping inherit scope_in claims."""
    task_id = str(contract.get("task_id", "")).strip()
    if not task_id:
        return False, "DELEGATION_VIOLATION: missing non-empty task_id", ""

    mode = (workspace_mode or "inherit").strip().lower()
    if mode not in ("", "inherit"):
        return True, f"isolated workspace mode '{mode}' bypasses shared workspace contention", task_id

    ts = float(now_ts if now_ts is not None else time.time())
    budget = contract.get("budget") if isinstance(contract.get("budget"), dict) else {}
    timeout_s = float(budget.get("timeout_seconds", 1800.0) or 1800.0)
    ttl = max(60.0, min(timeout_s, 7200.0))
    scope_in = [str(p) for p in contract.get("scope_in", []) if str(p).strip()]
    scope_out = [str(p) for p in contract.get("scope_out", []) if str(p).strip()]
    workspace_key = str(repo_root.resolve())
    gov_dir = _resolve_common_git_root(repo_root) / ".local" / "governance"

    with _scope_registry_lock(gov_dir) as registry_path:
        active = _load_active_leases(registry_path, ts)
        for existing in active:
            if existing.get("workspace_root") != workspace_key or existing.get("task_id") == task_id:
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
        updated.append(
            {
                "task_id": task_id,
                "workspace_root": workspace_key,
                "scope_in": scope_in,
                "scope_out": scope_out,
                "expires_at": ts + ttl,
            }
        )
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


def evaluate_active_subagent_write_scope(
    target_file: Path | str,
    repo_root: Path,
    task_id: str | None = None,
    *,
    now_ts: float | None = None,
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
    effective_task_id = (task_id if task_id is not None else os.environ.get("AGY_SUBAGENT_TASK_ID", "")).strip()
    with _scope_registry_lock(gov_dir) as locked_path:
        active = [e for e in _load_active_leases(locked_path, ts) if e.get("workspace_root") == workspace_key]

    own_lease: dict[str, Any] | None = None
    for entry in active:
        tid = str(entry.get("task_id", ""))
        if effective_task_id and tid == effective_task_id:
            own_lease = entry
            continue
        for held in entry.get("scope_in", []):
            if paths_overlap(rel, str(held)):
                return True, f"SUBAGENT_SCOPE_CONFLICT: '{rel}' is leased to active subagent '{tid}'"

    if own_lease is not None:
        for forbidden in own_lease.get("scope_out", []):
            if paths_overlap(rel, str(forbidden)):
                return True, f"SUBAGENT_SCOPE_VIOLATION: '{rel}' matches scope_out '{forbidden}' for '{effective_task_id}'"
        scope_in = own_lease.get("scope_in", [])
        if scope_in and not any(paths_overlap(rel, str(allowed)) for allowed in scope_in):
            return True, f"SUBAGENT_SCOPE_VIOLATION: '{rel}' is outside scope_in for '{effective_task_id}'"

    return False, "subagent write scope allowed"
