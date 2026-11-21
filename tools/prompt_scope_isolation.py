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
        "config/governance/",
        "config/schemas/",
        "config/structure_blueprint/",
        "config/provider_profiles.yaml",
        "config/model_catalog.json",
        "config/token_budget.yaml",
        "config/runtime_budget_policy.yaml",
        "outreach_engine/config/provider_profiles.yaml",
        "resume_graph_engine/config/models/",
        "resume_graph_engine/src/apps_rg/cache/",
        "apps_model_telemetry/",
        "infrastructure/",
        "scripts/local_llm/",
        ".mcp.json",
        ".gitignore",
        "pyproject.toml",
        "AGENTS.md",
        ".agents/",
        ".antigravity/",
        ".githooks/",
        "pytest.ini",
        "outreach_engine/pytest.ini",
        "resume_graph_engine/pytest.ini",
        "automations/prompts/_shared_governance_contract.md",
        "automations/prompts/agents_architecture_cost_agent.md",
        "tools/ssot_boundary_auditor.py",
        "tools/ssot_sprawl_scanner.py",
        "tools/ssot_hardcoding_scanner.py",
        "tools/check_config_ssot_drift.py",
        "tools/lint_architecture_boundaries.py",
        "tools/lint_layer_imports.py",
        "tools/lint_contract_schemas.py",
        "tools/lint_model_neutral_naming.py",
        "tools/lint_model_pins.py",
        "tools/lint_secrets.py",
        "tools/cost_token_budget_auditor.py",
        "tools/cost_token_budget_governor_probes.py",
        "tools/benchmark_macbook_runtime.py",
        "tools/storage_worktree_hygiene.py",
        "tools/prune_merged_chat_worktrees.py",
        "tools/pr_governance.py",
        "tools/pr_governance_core/",
        "tools/testing_gaps_auditor.py",
        "tools/audit_mock_reachability.py",
        "tools/validate_sidecar_separation.py",
        "tools/prompt_scope_isolation.py",
        "tests/unit/test_ssot_centralization_auditor.py",
        "tests/unit/test_sidecar_separation_governance.py",
        "tests/unit/test_prompt_collision_safeguards.py",
        "tests/unit/test_storage_hygiene_full_repo_remediation.py",
        "tests/unit/test_testing_gaps_full_parity.py",
        "tests/unit/test_evals_and_budget_full_parity.py",
        "tests/test_turn_gates.py",
        "tests/test_model_neutral_naming.py",
        "tests/test_post_merge_cleanup.py",
        "tests/test_pr_merge_queue_governance.py",
    ),
    "agents-core-runtime-orchestration": (
        "agents/orchestration/",
        "agents/persistence/",
        "agents/observability/",
        "agents/telemetry/",
        "agents/gateway/",
        "agents/context/budgeting.py",
        "agents/cli.py",
        "agents/_cli_helpers.py",
        "agents/health.py",
        "agents/e2e_artifacts.py",
        "agents/e2e_output.py",
        "agents/learning_cli.py",
        "agents/live_preflight.py",
        "tools/agent_runtime_auditor.py",
        "tools/unified_agent_architecture.py",
        "tools/hook_dispatch.py",
        "tools/hitl_governance.py",
        "automations/prompts/agents_core_runtime_orchestration_agent.md",
        "tests/test_unified_agent_architecture.py",
        "tests/test_hook_dispatch.py",
        "tests/test_hitl_governance_enforcement.py",
    ),
    "agents-domain-pipelines-retrieval": (
        "apps_research/",
        "outreach_engine/src/",
        "outreach_engine/tests/",
        "resume_engine/",
        "resume_graph_engine/src/apps_rg/chunking/",
        "resume_graph_engine/src/apps_rg/fact_inventory/",
        "resume_graph_engine/src/apps_rg/runtime/",
        "resume_graph_engine/src/apps_rg/engines/",
        "resume_graph_engine/src/apps_rg/resume/",
        "resume_graph_engine/src/apps_rg/prompt_assembly/",
        "resume_graph_engine/src/apps_rg/l2_recipe/",
        "resume_graph_engine/src/apps_rg/integrations/",
        "resume_graph_engine/src/apps_rg/bare_pipeline.py",
        "resume_graph_engine/tests/",
        "agents/context/precedent_bridge.py",
        "agents/context/provenance.py",
        "ops_scripts/",
        "tools/e2e_functionality_auditor.py",
        "tools/retrieval_surface_auditor.py",
        "tools/verify_graph_integrity_and_embeddings.py",
        "tools/run_resume_graph_traversal_probe.py",
        "tools/verify_pipeline_latency_caching.py",
        "automations/prompts/agents_domain_pipelines_retrieval_agent.md",
        "tests/test_sidecar_resume_graph_traversal.py",
        "tests/unit/test_e2e_and_retrieval_full_parity.py",
    ),
    "agents-evals-flywheel-assurance": (
        "agents/learning/",
        "agents/eval_flywheel_cli.py",
        "apps_eval/",
        "resume_graph_engine/src/apps_rg/evals/",
        "config/exit_eval_rubrics/",
        "config/judges/",
        "config/certification/",
        "config/routing_calibration.yaml",
        "config/prompt_governance/",
        "resume_graph_engine/config/certification/",
        "data/holdout/",
        "data/eval/",
        "data/certification/",
        "data/judge_calibration/",
        "outreach_engine/data/",
        "resume_graph_engine/data/",
        "tools/validate_eval_rubrics.py",
        "tools/lint_production_purity.py",
        "tools/audit_eval_construct_validity.py",
        "tools/audit_multi_ssot_judge_gate_drift.py",
        "tools/run_eval_flywheel_cycle.py",
        "tools/run_diff_scoped_eval_shield.py",
        "automations/prompts/agents_evals_flywheel_assurance_agent.md",
        "tests/unit/test_flywheel_hitl_dispatcher.py",
        "tests/end_to_end/test_flywheel_hitl_remediation_e2e.py",
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


def validate_stage_ownership_disjointness(
    repo_root: Path | None = None,
    stage_paths: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    """Return violations if any two stages overlap in write paths or declare missing repo paths."""
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
        if (resolved_root / "tools").is_dir():
            for agent_id, paths in mapping.items():
                for raw_path in paths:
                    if not (resolved_root / raw_path).exists():
                        violations.append(
                            f"STAGE_WRITE_PATH_MISSING: '{agent_id}' declares nonexistent path '{raw_path}'"
                        )
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
