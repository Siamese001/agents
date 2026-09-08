# Workspace Execution Policy

## Branch and worktree isolation

- Creating, switching, or inspecting a branch or worktree is a Git-only operation. It must not create or activate a virtual environment, install packages, start test discovery, or run pytest, coverage, or evaluation commands.
- Keep generated environments and test artifacts outside version control. Never add a branch-startup hook or task that performs those actions implicitly.

## Explicit validation only

- Tests are opt-in: run them only when the user requests validation or after an in-scope code change, using the smallest relevant selector first.
- Do not run a broad `pytest` command, create a virtual environment, or install dependencies merely because a workspace opens or changes branches. An explicit user instruction to do so takes precedence.

## Runtime boundary and Defender

- For explicit Apps RG runtime work, use `codex-defender run --policy .codex/runtime-boundary.json --command ...`. The Defender is the machine-global owner of the worktree-scoped venv, clean process environment, timeout, and child-process tree.
- Provision and synchronize a managed environment only as an explicit requested operation. A Defender run never performs installation implicitly; the checked-in GPU lock remains the dependency authority.
- Do not bypass the Defender with a direct `python`, `py`, `pytest`, `pip`, or evaluation command. A Codex pre-tool hook rejects those commands; the product independently rejects foreign runtime paths.
- The checked-in runtime-boundary policy is authoritative for writable caches, artifacts, model bytes, and runtime root. A foreign inherited path is a `PATH_AUTHORITY_VIOLATION`, not a reason to relax an evaluation, exit, or judge gate.
