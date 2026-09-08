# Apps RG v2 Canonical Resume Entrypoint

## Scope

This document governs the **end-to-end resume pipeline** only. It does not
turn every maintenance, graph, calibration, or evaluation utility in the
repository into a resume-pipeline command.

## The one public command

```text
python -m apps_rg run [optional JD/resume overrides]
```

The zero-input form uses the canonical Anthropic partnership JD and canonical
Amit Ayer base resume. It is the only supported user-facing command that runs
the governed end-to-end product flow: signed preflight, Apps Research, U0/L1/
L0/C0/PA/L2/X1/X3, Exit/UWG, Apps Eval, L6 shadow evidence, and terminal E2E
sealing. A run is successful only when the product and pipeline completion
claims, E2E stage ledger, Apps Eval package, L6 bridge, and final résumé output
all verify.

The same top-level command owns inspection actions:

```text
python -m apps_rg eval --run-dir <completed-run>
python -m apps_rg show --run-dir <completed-run> --artifact resume|research|summary|evaluation
```

`eval` only reads existing full-run evidence and makes no provider call. It
verifies the existing Apps Eval package seal and E2E closure; it never runs a
late evaluation to repair an incomplete product run. `show` prints the exact
stored artifact.

Every `run` emits the same three inline outputs, in order: `FULL_RESUME`,
`EVALS`, and `RUNTIME_DETAILS`. They are mandatory even on failure; an
unavailable final resume is represented explicitly rather than omitted.
## Explicitly not resume-pipeline entrypoints

The following may remain as internal libraries, maintenance tools, or
separate-app utilities. They are not allowed to be represented as alternate
end-to-end Apps RG resume runners:

- `python -m apps_research` — separate research-app surface.
- `python -m apps_eval` — generic grader harness; the public product command
  invokes the governed current-run Apps Eval integration itself.
- `python -m apps_rg.*` — nested Apps RG modules are import-only libraries;
  they have no executable CLI entrypoint.
- `tools/apps_rg_standalone/*` — historical/maintenance tools.
- `apps_rg.runtime.*`, `apps_rg.fact_inventory.*`, and section-lane modules —
  implementation or maintenance surfaces, not operator resume pipelines.

The historical section-selection, `doctor`, bootstrap, manual-brief, cache,
W6, and legacy-spine command shapes are not part of this public resume
command. They must not be added back to its parser.

## Enforcement

The public parser exposes only `run`, `eval`, and `show`. Focused tests verify
the complete stage contract and that `eval` and `show` operate only on
completed artifacts.
