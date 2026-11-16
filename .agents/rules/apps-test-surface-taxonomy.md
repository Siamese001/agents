---
trigger: model_decision
---

# Apps Test Surface Taxonomy — stub

> On-demand when adding/moving apps_* tests (plan `always-on-rule-surface-cut-c7f3a1`); enforcement unchanged. All `apps_<x>` tests live in 3 canonical surfaces — Unit `tests/unit/<app>/`, Integration `tests/<app>/`, Contract `tests/_apps_contract/test_<app>_*.py`; `apps_<x>/tests/` and `tests/integration/apps_<x>/` FORBIDDEN. Detail: sibling `apps-folder-taxonomy.md`. Enforced: `ssot_boundary_auditor.py` (T7r), `testing_gaps_auditor.py` (TSP1).
