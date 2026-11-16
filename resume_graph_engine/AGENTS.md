# Workspace Execution Policy

## Branch and worktree isolation

- Creating, switching, or inspecting a branch or worktree is a Git-only operation. It must not create or activate a virtual environment, install packages, start test discovery, or run pytest, coverage, or evaluation commands.
- Keep generated environments and test artifacts outside version control. Never add a branch-startup hook or task that performs those actions implicitly.

## Validation & Root-Cause Bug Resolution

- Do not start test discovery or install packages implicitly when merely switching branches or opening a workspace.
- When fixing bugs, refactoring, or running `/boost` / `/swarm`, run all impacted unit, integration, or full `resume_graph_engine/tests/` suites (`--timeout=60` or `--timeout=180`) freely without selector-size restrictions.

## Runtime boundary

- For explicit Apps RG runtime work, the checked-in runtime-boundary policy (`.antigravity/runtime-boundary.json`) is authoritative for writable caches, artifacts, model bytes, and runtime root.
- In-process path authority is enforced by `apps_rg.runtime.runtime_boundary`. A foreign inherited path or foreign cache outside the workspace is rejected as `PATH_AUTHORITY_VIOLATION`.
- External `codex-defender` wrappers are deprecated. Execute runtime commands directly in the workspace virtual environment (`.venv`).

