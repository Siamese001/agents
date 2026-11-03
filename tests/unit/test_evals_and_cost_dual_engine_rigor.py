"""Unit tests for Wave 4 symmetric Evals/Judge and dual-engine Cost/Token probes."""

from __future__ import annotations

from pathlib import Path

from tools.cost_token_budget_auditor import run_eight_pillar_cost_token_audit
from tools.validate_eval_rubrics import CONFIG_ROOTS, DATA_ROOTS, validate_eval_rubrics

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_validate_eval_rubrics_covers_all_five_config_roots_and_314_data_files() -> None:
    rep = validate_eval_rubrics(REPO_ROOT)
    assert rep["is_clean"] is True, rep["violations"]
    assert rep["config_roots_audited"] == list(CONFIG_ROOTS)
    assert rep["data_counts_by_root"] == {
        "data": 154,
        "outreach_engine/data": 8,
        "resume_graph_engine/data": 152,
    }
    assert rep["data_file_count"] == 314
    assert rep["eval_module_count"] >= 250
    assert rep["validated_schema_count"] >= 30


def test_validate_eval_rubrics_fails_closed_on_subsystem_data_and_rubric_defects(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    for droot in DATA_ROOTS:
        (tmp_path / droot).mkdir(parents=True)

    # 1. Malformed dataset inside outreach_engine/data and empty dataset in resume_graph_engine/data
    (tmp_path / "outreach_engine" / "data" / "broken.json").write_text("{not-json", encoding="utf-8")
    (tmp_path / "resume_graph_engine" / "data" / "empty.jsonl").write_text("", encoding="utf-8")

    # 2. Empty judge module without 'eval' in its filename inside outreach_engine/src
    judge_py = tmp_path / "outreach_engine" / "src" / "apps_lic" / "domain" / "broken_judge.py"
    judge_py.parent.mkdir(parents=True)
    judge_py.write_text("# comment only judge file\n", encoding="utf-8")

    # 3. Broken outreach lens weight sum and broken apps_eval informational_only weight
    lic_rub = tmp_path / "outreach_engine" / "config" / "rubrics"
    lic_rub.mkdir(parents=True)
    (lic_rub / "bad_outreach.yaml").write_text(
        "rubric_id: bad_outreach\n"
        "lenses:\n"
        "  l1: {weight: 0.6, threshold: 0.7}\n"
        "  l2: {weight: 0.6, threshold: 0.7}\n",
        encoding="utf-8",
    )

    eval_rub = tmp_path / "apps_eval" / "rubrics"
    eval_rub.mkdir(parents=True)
    (eval_rub / "bad_app_eval.yaml").write_text(
        "rubric_id: bad_app_eval\n"
        "dimensions:\n"
        "  - id: core_fit\n"
        "    weight: 0.8\n"
        "  - id: advisory_tell\n"
        "    weight: 0.2\n"
        "    informational_only: true\n",
        encoding="utf-8",
    )

    res_rub = tmp_path / "apps_research" / "config" / "domain_contract"
    res_rub.mkdir(parents=True)
    (res_rub / "eval_rubrics.yaml").write_text(
        "- eval_rubric_id: aer_bad\n"
        "  score_dimensions:\n"
        "    - dimension_id: d1\n"
        "      weight: 0.9\n"
        "      min_required_score: 0.8\n"
        "    - dimension_id: d2\n"
        "      weight: 0.3\n"
        "      min_required_score: 0.8\n",
        encoding="utf-8",
    )

    rep = validate_eval_rubrics(tmp_path)
    assert rep["is_clean"] is False
    vtext = "\n".join(rep["violations"])
    assert "outreach_engine/data/broken.json" in vtext
    assert "resume_graph_engine/data/empty.jsonl" in vtext
    assert "broken_judge.py" in vtext
    assert "outreach lenses weights sum to 1.2000 != 1.0" in vtext
    assert "informational_only dimension must have weight 0.0" in vtext
    assert "score_dimensions weights sum to 1.2000 != 1.0" in vtext


def test_cost_token_budget_auditor_verifies_outreach_repair_governor_and_inline_hygiene() -> None:
    report = run_eight_pillar_cost_token_audit(REPO_ROOT)
    assert report["is_clean"] is True, report["pillars"]
    assert report["pillars_passing"] == 8
    assert report["roi_benchmark"]["roi_multiple"] >= 2.5

    p5 = next(p for p in report["pillars"] if p["pillar"].startswith("5_"))
    assert p5["status"] == "PASS"
    assert p5["live_metrics"]["outreach_prompt_templates_verified"] >= 8
    assert p5["live_metrics"]["outreach_repair_verified"] is True

    p7 = next(p for p in report["pillars"] if p["pillar"].startswith("7_"))
    assert p7["status"] == "PASS"
    assert p7["gaps"] == []
