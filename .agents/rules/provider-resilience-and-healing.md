---
trigger: glob
globs: "{resume_graph_engine/src/apps_rg/runtime/providers/**,resume_graph_engine/src/apps_rg/runtime/judges/**,infrastructure/**}"
---
# Provider Resilience & Keyless Transport Rules

Governs LLM provider routing, concurrency bounds, timeouts, and cross-family orthogonality across `agents`.

## 1. Governed Provider Transport & Keyless Execution

1. **Central Transport Only**: All generation and judging calls must route through the governed provider transport (`ide_cli_generation.py`, `agy_cli_transport.py`, `x1d_ide_cli.py`, or `infrastructure/`). Ad-hoc HTTP client calls or sending one provider's API key to another provider's endpoint are strictly prohibited.
2. **Keyless IDE CLI Parity**: Repair, regeneration, and blind-judge lanes must support keyless `ide_cli` routing without requiring commercial API keys in environment variables.
3. **Bounded Timeouts & Concurrency**: Enforce explicit per-call timeouts, lane wall-clock budgets, and semaphore concurrency aligned with `phase1_max_parallel` (`DEFAULT_AGY_MAX_CONCURRENCY`), persisting `queue_wait_seconds` in receipts. Never clamp live rewrite calls below realistic model latency budgets.
4. **Effort Resolution Parity**: Section-level `reasoning_effort` settings (`low`/`medium`/`high`) must resolve cleanly onto model slugs rather than being silently dropped when a slug carries a suffix.
5. **Cross-Family Orthogonality**: Section drafters, voice/rewrite auditors, and dual blind judges must resolve orthogonal model families from `provider_profiles.yaml` to prevent self-preference bias.

## 2. Strict Deterministic Boundaries

- Pure deterministic Python only for C0 graph allocation, X2 invariant validation, schema verification, and X3 publication disposition.
- Never coerce failing blind judge scores upward or leak deterministic pass flags into blind `executive_summary` judge prompts.
