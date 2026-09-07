# Workspace Execution Policy - apps_lic_v2

## Branch and worktree isolation
- Creating, switching, or inspecting a branch or worktree is a Git-only operation.
- Keep generated environments and test artifacts outside version control.

## Standalone Subsystem Architecture
- `apps_lic_v2` is an independent, self-contained subsystem with ZERO imports of `agentic_core` or `apps_shared`.
- All domain models, prompt compilers, validators, touch sequence schedulers, and judge evaluators are locally bounded under `src/apps_lic/`.

## Explicit validation only
- Tests are opt-in: run them only when requested or after an in-scope code change.
