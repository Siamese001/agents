# SSOT Folder Routing

> Loads on demand when creating new governance, tooling, or production files.

**Invariant:** Place new governance validators, auditors, and lifecycle dispatchers under `tools/` (wired via `.agents/hooks.json` -> `tools/hook_dispatch.py`), operational smoke scripts under `ops_scripts/`, local serving helpers under `scripts/`, and domain modules inside their owning package root (`agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `infrastructure/`).

**Cohesive package decomposition (`INV-HOLISTIC-PIPELINE-PLANNING`):** Splitting an oversized production file into `<= 600`-line submodules behind a `<= 150`-line facade or extracting shared domain contracts across coupled upstream/downstream spine dependencies stays inside its owning subsystem package (`Constitutional §31`). Enforced by `tools/verify_commit.py` and `tools/ssot_boundary_auditor.py`.
