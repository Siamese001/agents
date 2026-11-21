"""Unit and adversarial edge-case tests for tools/change_lane_classifier.py."""

from __future__ import annotations

from pathlib import Path

from tools.change_lane_classifier import classify_paths, load_risk_lanes_policy

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_lane0_docs_and_tests_only() -> None:
    report = classify_paths(
        ["docs/architecture/overview.md", "tests/unit/test_example.py"],
        repo_root=REPO_ROOT,
    )
    assert report["effective_lane"] == 0
    assert report["lanes_touched"] == [0]
    assert report["unrecognized_paths"] == []
    assert report["self_referential_lock"] is False
    assert report["advisories"] == []


def test_lane1_standard_application_module() -> None:
    report = classify_paths(
        ["outreach_engine/src/campaign.py", "apps_research/src/search.py"],
        repo_root=REPO_ROOT,
    )
    assert report["effective_lane"] == 1
    assert report["lanes_touched"] == [1]
    assert report["unrecognized_paths"] == []


def test_lane2_critical_fact_inventory_and_judges() -> None:
    report = classify_paths(
        [
            "resume_graph_engine/src/apps_rg/fact_inventory/ibm_role_episode_bundles.json",
            "resume_graph_engine/src/apps_rg/runtime/judges/executive_summary_x1d.py",
        ],
        repo_root=REPO_ROOT,
    )
    assert report["effective_lane"] == 2
    assert report["lanes_touched"] == [2]
    assert len(report["required_readiness_stages"]) == 9


def test_unrecognized_path_escalates_fail_closed_to_lane2() -> None:
    report = classify_paths(
        ["mystery_top_level_dir/unmapped_script.py"],
        repo_root=REPO_ROOT,
    )
    assert report["effective_lane"] == 2
    assert report["unrecognized_paths"] == ["mystery_top_level_dir/unmapped_script.py"]
    codes = {a["code"] for a in report["advisories"]}
    assert "UNRECOGNIZED_PATH_ESCALATED" in codes


def test_mixed_lane_escalates_to_highest_lane_with_advisories() -> None:
    report = classify_paths(
        [
            "docs/readme_note.md",
            "outreach_engine/src/campaign.py",
            ".agents/rules/risk-tiered-change-lanes.md",
        ],
        repo_root=REPO_ROOT,
    )
    assert report["effective_lane"] == 2
    assert report["lanes_touched"] == [0, 1, 2]
    codes = {a["code"] for a in report["advisories"]}
    assert "MIXED_RISK_LANES" in codes
    assert "LANE2_GOVERNANCE_ESCALATION" in codes


def test_self_referential_policy_and_classifier_cannot_downgrade() -> None:
    tampered_policy = dict(load_risk_lanes_policy(REPO_ROOT))
    tampered_policy["default_unrecognized_lane"] = 0
    tampered_policy["self_referential_immutable_paths"] = []
    report = classify_paths(
        ["config/governance/risk_lanes_policy.json", "tools/change_lane_classifier.py"],
        repo_root=REPO_ROOT,
        policy=tampered_policy,
    )
    assert report["effective_lane"] == 2
    assert report["self_referential_lock"] is True
    assert set(report["self_referential_paths"]) == {
        "config/governance/risk_lanes_policy.json",
        "tools/change_lane_classifier.py",
    }


def test_soft_batch_advisories_are_non_blocking() -> None:
    many_files = [f"outreach_engine/src/mod_{i}.py" for i in range(10)]
    report = classify_paths(many_files, repo_root=REPO_ROOT, churn_loc=750)
    assert report["effective_lane"] == 1
    codes = {a["code"] for a in report["advisories"]}
    assert "SOFT_BATCH_PROD_FILES" in codes
    assert "SOFT_BATCH_CHURN_LOC" in codes
    assert all(a["severity"] == "advisory" for a in report["advisories"])
