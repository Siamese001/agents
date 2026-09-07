# Frozen Anthropic Partnership E2E failure

This directory is an immutable, canonical-JSON regression corpus from run
`e2e_20260808T062125Z_c9caf451`.

The run was produced by the Apps RG checkout at
`ad0898ad7bdf9efa35a765ac80fe92535319dd80` with the external
`agentic_core` checkout at
`cba1303f044f24af364b888122971cab7a972457`.

Only non-content-bearing authority and diagnostic artifacts are retained. The
corpus intentionally preserves contradictions; it is evidence of the defect,
not a successful or product-authorized fixture. `manifest.json` records each
original raw SHA-256 and a line-ending-independent canonical JSON SHA-256.

Wave 0 tests use this corpus for provenance and use freshly generated fault
runs for executable red tests, so later production fixes do not rewrite
history.
