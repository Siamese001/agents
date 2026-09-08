---
name: run-defender-pipeline
description: Standard operating procedure for executing the canonical apps_rg resume pipeline or evaluation suite through the global Defender runtime boundary.
---

# Running the Apps RG Pipeline via Defender

## Canonical Resume Run
The sole public Apps RG resume command is:

```powershell
C:\Users\amita\.codex\defender\bin\codex-defender.cmd run --policy .codex/runtime-boundary.json --command python -m apps_rg run
```

## Running Evaluations
The offline evaluation suite under `src/apps_rg/evals` evaluates the G1-G6 measurement contract.
To run evaluations through the Defender boundary:

```powershell
C:\Users\amita\.codex\defender\bin\codex-defender.cmd run --policy .codex/runtime-boundary.json --command python -m pytest -q src/apps_rg/evals
```

## Policy Boundaries
- Never run `python` or `pytest` directly from the shell without wrapping in `codex-defender`.
- The runtime policy is governed by `.codex/runtime-boundary.json`.
- The Defender ensures process environment cleanliness, timeout safety, and path isolation.
