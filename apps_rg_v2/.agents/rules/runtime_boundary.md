# Runtime Boundary & Codex Defender Rule

## Policy
For explicit Apps RG runtime work, use `codex-defender run --policy .codex/runtime-boundary.json --command ...`.
The Defender is the machine-global owner of the worktree-scoped venv, clean process environment, timeout, and child-process tree.

## Constraints
1. Never bypass Defender with a direct `python`, `py`, `pytest`, `pip`, `uv`, or evaluation command.
2. The checked-in runtime-boundary policy (`.codex/runtime-boundary.json`) is authoritative for writable caches, artifacts, model bytes, and runtime root.
3. Foreign inherited paths or environments outside the Defender runtime are rejected as `PATH_AUTHORITY_VIOLATION`.
4. Tests are strictly opt-in and run only when the user requests validation or after an in-scope code change.
