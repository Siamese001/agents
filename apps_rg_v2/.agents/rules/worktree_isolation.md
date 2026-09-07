# Branch and Worktree Isolation Rule

## Policy
Creating, switching, or inspecting a branch or worktree is a Git-only operation.

## Constraints
1. Must not create or activate a virtual environment, install packages, start test discovery, or run pytest, coverage, or evaluation commands merely because a workspace opens or changes branches.
2. Keep generated environments and test artifacts outside version control. Never add a branch-startup hook or task that performs those actions implicitly.
3. Explicit user instructions to run tests take precedence, but must always use the smallest relevant selector first and run within the Defender boundary.
