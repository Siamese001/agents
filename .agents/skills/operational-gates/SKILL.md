---
name: operational-gates
description: Gate destructive, state-changing, migration, deletion, or multi-file operations with explicit recovery points, tool contracts, and failure-recovery protocols.
---

# Operational Gates

Use this procedure for operations where a partial result would be costly or difficult to reverse. Ordinary read-only analysis and small edits (<= 20 lines) do not need checkpoint ceremony.

## 1. Pre-Operation Gate & Rollback Checkpoint

Before starting any multi-file, migration, or destructive operation:
1. Confirm the exact files, database tables, remote resources, and side effects in scope.
2. Verify a clean baseline:
   ```bash
   git status --short
   git rev-parse HEAD
   ```
3. Establish a recoverable baseline using an isolated worktree (`.venv/bin/python tools/pr_governance.py start <branch>`) or recorded commit hash.
4. Record the intended recovery command:
   ```bash
   git checkout --force <baseline_commit>
   git clean -fd
   ```

## 2. Multi-Phase Gate Protocol

For migrations or refactors spanning multiple files:
1. Deconstruct work into sequential, testable phases.
2. Execute exactly one bounded phase at a time.
3. Validate each phase before advancing:
   - Check file diff: `git diff --name-only`
   - Run scoped tests: `.venv/bin/pytest <phase_test_file> -v --timeout=60`
4. Halt immediately if any intermediate assertion or gate fails.

## 3. Tool-Contract Validation Checklist

Validate tool names, parameters, and authorities without mutating production state:
- Verify the tool is present in the active tool definitions.
- Required arguments are provided with correct types (`string`, `int`, `bool`, `list`, `dict`).
- Values reside within allowable boundaries (e.g. timeout <= 180s, word limits <= 300 words).
- No undocumented or hallucinated parameters are supplied.
- Dry-run or read-only mode is prioritized before executing write operations.

## 4. Failure Recovery & Escalation

When an operational gate or validation step fails:
1. **Stop immediately**: Cease further modifications to prevent cascading corruption.
2. **Preserve evidence**: Capture error messages, diffs, and execution logs.
3. **Execute rollback**: Run the declared recovery command to restore baseline state:
   ```bash
   git checkout --force <baseline_commit>
   ```
4. **Verify restoration**: Ensure `git status --short` returns clean.
5. **Diagnose and correct**: Address the underlying root cause before retrying.

## 5. Validation

```bash
git status --short
.venv/bin/python tools/validate_turn_gates.py --mode pre-turn
.venv/bin/python tools/verify_commit.py
```
