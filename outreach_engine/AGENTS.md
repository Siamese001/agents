# Workspace Execution Policy - apps_lic_v2

## Branch and worktree isolation
- Creating, switching, or inspecting a branch or worktree is a Git-only operation.
- Keep generated environments and test artifacts outside version control.

## Standalone Subsystem Architecture
- `apps_lic_v2` is an independent, self-contained subsystem with standard library and local package dependencies only.
- All domain models, prompt compilers, validators, touch sequence schedulers, and judge evaluators are locally bounded under `src/apps_lic/`.

## Validation & Root-Cause Bug Resolution
- Do not trigger implicit test sweeps on branch switch alone; during bug fixes, refactoring, `/boost`, or `/swarm`, run any impacted test slices or the full `outreach_engine/tests/` suite (`--timeout=60`) without restriction.
