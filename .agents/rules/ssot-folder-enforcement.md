# SSOT Folder Routing — pointer stub

> Demoted from the always-on surface to cut context (plan `always-on-rule-surface-cut-c7f3a1`).
> Loads on demand when creating new files. Enforcement unchanged (fires regardless).

**Invariant (kept):** Governance/CI/tool scripts follow canonical prefix routing — `check_*`/`*_gate.py`
→ `ops_scripts/ci/`; calibration/binder/poller → `ops_scripts/calibration/`; `purge_*`/`cleanup_*` →
`ops_scripts/maintenance/`; `pre_*`/`post_*` hooks → `.agents/scripts/`; standalone tooling →
`tools/<domain>/`. Hook-prefix files misrouted = silent disable. Pre-existing files exempt.
**Cohesive package decomposition (`INV-HOLISTIC-PIPELINE-PLANNING`):** Splitting an oversized
production file into `<= 600`-line submodules behind a facade or extracting shared domain contracts
across coupled upstream/downstream spine dependencies remains inside its owning production subsystem
package (`agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `outreach_engine/`,
`resume_engine/`, `resume_graph_engine/`, `infrastructure/`), distinct from unrelated drift.
Constitutional §31.

**Full detail (on demand):** sibling `plan-location.md`.
**Enforcement (prose-independent):** `pre_write_gate.py` (fail-closed) +
`ops_scripts/ci/check_ssot_folder_routing.py` (T7q). Bypass: `SSOT_FOLDER_BYPASS=1`.
