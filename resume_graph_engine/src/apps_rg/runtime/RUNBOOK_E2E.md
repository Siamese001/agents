# Apps RG resume workflow

The sole public, end-to-end resume command is:

```bash
python -m apps_rg run [--target-company <company>] [--target-role <role>] [--jd <path-or-text>] [--resume <path>]
```

The command uses the canonical Anthropic partnership JD and base resume.

## Supported actions

| Goal | Command |
| --- | --- |
| Run the complete governed product workflow, including Apps Eval and L6 | `python -m apps_rg run` |
| Verify a completed full run's Apps Eval package and E2E closure | `python -m apps_rg eval --run-dir <run-dir>` |
| Print a stored artifact | `python -m apps_rg show --run-dir <run-dir> --artifact resume\|research\|summary\|evaluation` |

`eval` and `show` are actions of the same command surface; neither produces a
new résumé or makes a provider call. `eval` fails closed if Apps Eval, L6, the
E2E ledger, or terminal product outputs are missing or invalid.

## Retired command shapes

There is no compact, deterministic, section, manual-brief, bootstrap, cache,
W6, patch-run, or runtime-module command for the public résumé workflow.
Those historical paths must not be used to claim an end-to-end Apps RG run.
Runtime modules, evaluators, validators, fact-inventory tools, and graph
maintenance utilities may have their own maintainer interfaces, but none
generates the complete resume product.

Every `run` always prints exactly three inline sections in this order:
`FULL_RESUME`, `EVALS`, and `RUNTIME_DETAILS`. On a failed or incomplete run,
the same sections appear with an explicit unavailable/failure reason; none is
silently omitted. See
[`docs/APPS_RG_V2_CANONICAL_ENTRYPOINTS.md`](../../../docs/APPS_RG_V2_CANONICAL_ENTRYPOINTS.md)
for the authoritative public-command contract.
