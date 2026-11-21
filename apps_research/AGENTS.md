# Apps Research - Autonomous Subsystem Contract

> `apps_research` is an autonomous subsystem owning company research retrieval, BGE-M3 hybrid search, targeting briefs, and structured research handoff artifacts.

## Subsystem Ownership & Boundaries

- **Owned surface**: `apps_research/` source modules, retrieval/brief pipelines, and unit tests under `tests/unit/apps_research/`.
- **Autonomous isolation**: Keep cross-subsystem imports directional and decoupled; never import private internals from sibling domain subsystems (`tools/ssot_boundary_auditor.py`, `tools/lint_architecture_boundaries.py`).
- **Fail-closed briefs**: Missing or schema-invalid targeting briefs and handoff envelopes must fail closed rather than substituting fabricated summaries.
- **Hardware policy**: Resolve MPS/CPU device selection via `infrastructure/device/device_manager.py`; keep control-plane orchestration and SQLite/FTS operations on CPU.

## Root-Cause Bug Resolution & Verification

Root-cause bug fixes and cohesive refactors across `apps_research/` and its connected upstream/downstream contracts execute freely with zero file-count, file-size, line-count, or blast-radius caps (`INV-REFACTOR-EXTENT-UNBOUNDED`):

- Run impacted tests (`tests/unit/apps_research/`) with `--timeout=60`.
- Verify retrieval surface and boundaries via `tools/retrieval_surface_auditor.py` and `tools/ssot_boundary_auditor.py`.

## References

- Root [`AGENTS.md`](../AGENTS.md)
- `.agents/rules/apps-research.md`
