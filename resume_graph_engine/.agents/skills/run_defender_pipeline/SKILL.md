---
name: run-defender-pipeline
description: Standard operating procedure for executing the canonical apps_rg resume pipeline or evaluation suite through the Antigravity runtime boundary.
---

# Running the Apps RG Pipeline

## Canonical Resume Run
The sole public Apps RG resume command is:

```powershell
python -m apps_rg run
```

Or using the workspace virtual environment:

```powershell
& "..\.venv\Scripts\python.exe" -m apps_rg run
```

## Running Evaluations
The offline evaluation suite under `src/apps_rg/evals` evaluates the G1-G6 measurement contract.
To run evaluations:

```powershell
python -m pytest -q src/apps_rg/evals
```

Or using the workspace virtual environment:

```powershell
& "..\.venv\Scripts\python.exe" -m pytest -q src/apps_rg/evals
```

## Policy Boundaries
- The runtime policy is governed by `.antigravity/runtime-boundary.json` and enforced in-process by `apps_rg.runtime.runtime_boundary`.
- The runtime boundary verifies workspace path containment, sets offline hub guards (`HF_HUB_OFFLINE=1`), and prevents foreign cache inheritance.
- External `codex-defender` wrappers are deprecated and retired.
