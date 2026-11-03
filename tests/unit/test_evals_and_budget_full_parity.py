"""Unit tests for Wave 3 11-Grader Evals, L6 Bridge/Render/Trends, and Telemetry/Governor Live Probes (Agents 5 & 6)."""

from __future__ import annotations

from pathlib import Path

from apps_eval.contracts import models as eval_models
from apps_eval.graders.deterministic import core as det_graders
from tools.cost_token_budget_auditor import run_eight_pillar_cost_token_audit
from tools.validate_eval_rubrics import _probe_app_graders, validate_eval_rubrics

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_validate_eval_rubrics_probes_all_11_deterministic_graders_and_l6_surfaces() -> None:
    graders = det_graders.build_default_graders()
    assert len(graders) == 11
    expected_ids = {
        "schema",
        "artifact_presence",
        "x3_disposition",
        "forbidden_content",
        "grounded_claim",
        "provenance",
        "section_structure",
        "length_bounds",
        "side_effect",
        "escalation",
        "determinism",
    }
    assert {g.grader_id for g in graders} == expected_ids

    errs = _probe_app_graders(
        eval_models,
        det_graders,
        "apps_rg",
        "Led enterprise platform transformation delivering measurable latency gains across 18 services.",
        "Resume headline promising a guaranteed_offer upon submission.",
    )
    assert errs == []

    rep = validate_eval_rubrics(REPO_ROOT)
    assert rep["is_clean"] is True, rep["violations"]
    assert rep["data_file_count"] == 314


def test_cost_token_budget_auditor_probes_run_manifest_telemetry_facade_and_exact_reuse() -> None:
    report = run_eight_pillar_cost_token_audit(REPO_ROOT)
    assert report["is_clean"] is True, report["pillars"]
    assert report["pillars_passing"] == 8
    p7 = next(p for p in report["pillars"] if p["pillar"].startswith("7_"))
    assert p7["status"] == "PASS"
    assert p7["gaps"] == []
