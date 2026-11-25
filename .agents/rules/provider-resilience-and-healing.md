---
trigger: glob
globs: "{resume_graph_engine/src/apps_rg/runtime/providers/**,resume_graph_engine/src/apps_rg/runtime/judges/**,infrastructure/**}"
---

# Provider Resilience & Keyless Transport Rules (`agents` Overrides)

Inherits keyless IDE execution, bounded timeouts/concurrency, and cross-family judge orthogonality from `~/.gemini/config/plugins/core-governance/rules/provider-resilience-and-healing.md`.

## `agents` Transport & Boundary Bindings

- **Governed Transports**: Route generation and judging exclusively through `ops_scripts/agy_cli_transport.py`, `ide_cli_generation.py`, `x1d_ide_cli.py`, or `infrastructure/` with keyless `ide_cli` parity.
- **Concurrency & Effort Parity**: Align semaphore concurrency with `phase1_max_parallel` (`DEFAULT_AGY_MAX_CONCURRENCY`), persist `queue_wait_seconds`, and preserve section-level `reasoning_effort` (`low`/`medium`/`high`) across suffixed model slugs in `config/provider_profiles.yaml`.
- **Deterministic Spine Floor**: Keep C0 graph allocation, X2 invariant validation, schema checks, and X3 publication disposition 100% deterministic; never coerce failing blind judge scores upward or leak X2 pass flags into blind judge prompts.
