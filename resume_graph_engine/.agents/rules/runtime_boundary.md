# Runtime Boundary Rule

## Policy
For explicit Apps RG runtime work, runtime environment containment is governed by `.antigravity/runtime-boundary.json` and enforced in-process by `apps_rg.runtime.runtime_boundary`.

## Constraints
1. The checked-in runtime-boundary policy (`.antigravity/runtime-boundary.json`) is authoritative for writable caches, artifacts, model bytes, and runtime root.
2. Foreign inherited paths or environments outside the workspace boundary are rejected fail-closed as `PATH_AUTHORITY_VIOLATION`.
3. Tests are strictly opt-in and run only when the user requests validation or after an in-scope code change.
4. Legacy `codex-defender` wrappers are deprecated and retired; run directly using the workspace virtualenv (`.venv`).
