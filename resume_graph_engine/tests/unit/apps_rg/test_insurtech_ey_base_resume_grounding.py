"""InsurTech/EY role lanes use graph bundle proof, not base-resume bullets.

The base resume is retained as an identity spine only. Claim evidence for these lanes must come
from role_episode_bundle_id values (reb_insurtech_* / reb_ey_*).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.runtime.section_graph_skills_proof_pool import (
    _ROLE_EPISODE_BASE_RESUME_NEEDLES,
    _SECTION_MIN_FACTS,
    _base_resume_role_episode_plan,
    _role_episode_bundle_plan,
    bind_selector_selected_skills_to_section_plan,
)
from apps_rg.runtime.sections.graph_role_episode_selector import (
    build_selected_graph_evidence_plan_for_section,
)

REPO = Path(__file__).resolve().parents[3]


def test_base_resume_role_episode_planner_is_deprecated() -> None:
    assert _ROLE_EPISODE_BASE_RESUME_NEEDLES == {}
    assert _base_resume_role_episode_plan(
        "insurtech_bullets", needles=("insurtech",), limit=3, repo_root=REPO
    ) is None
    assert _base_resume_role_episode_plan(
        "ey_bullets", needles=("ernst", "young"), limit=3, repo_root=REPO
    ) is None


@pytest.mark.parametrize(
    "section,expected_prefix,forbidden_prefix",
    [
        ("insurtech_bullets", "reb_insurtech_", "bul_insurtech_"),
        ("insurtech_narrative", "reb_insurtech_", "bul_insurtech_"),
        ("ey_bullets", "reb_ey_", "bul_ey_"),
        ("ey_narrative", "reb_ey_", "bul_ey_"),
    ],
)
def test_role_episode_bundle_plan_uses_graph_ids(section, expected_prefix, forbidden_prefix) -> None:
    result = _role_episode_bundle_plan(
        section_id=section,
        repo_root=REPO,
        limit=_SECTION_MIN_FACTS[section],
    )
    assert result is not None, f"{section} graph bundle planner returned None"
    plan, ordered, allowed = result
    facts = plan["facts"]
    assert len(facts) == _SECTION_MIN_FACTS[section]
    assert len(ordered) == len(facts)
    assert set(ordered) == allowed
    assert plan["selection_method"] == f"augmented_skills_graph_{section}_role_episode_bundle"
    assert plan["role_episode_bundle_fallback"] is True
    for f in facts:
        fact_id = str(f["fact_id"])
        assert fact_id.startswith(expected_prefix), fact_id
        assert not fact_id.startswith(forbidden_prefix), fact_id
        assert f["source_fact_ids"] == [fact_id]
        assert f["role_episode_bundle_id"] == fact_id
        assert f["srfs_verification_status"] == "GRAPH_ROLE_EPISODE_BUNDLE"
        assert f["claim_text"].strip()


def test_planner_not_applied_to_ibm_or_unify() -> None:
    assert "ibm_bullets" not in _ROLE_EPISODE_BASE_RESUME_NEEDLES
    assert "unify_bullets" not in _ROLE_EPISODE_BASE_RESUME_NEEDLES


def test_insurtech_selected_skills_are_copied_from_graph_selector() -> None:
    result = _role_episode_bundle_plan(
        section_id="insurtech_bullets",
        repo_root=REPO,
        limit=_SECTION_MIN_FACTS["insurtech_bullets"],
    )
    assert result is not None
    source_plan = result[0]
    selector_plan, _, _ = build_selected_graph_evidence_plan_for_section(
        repo_root=REPO,
        section_id="insurtech_bullets",
        target_role="VP",
        jd_text="Lead agentic AI platform strategy.",
        briefing_text="AIG agentic AI.",
    )

    bound = bind_selector_selected_skills_to_section_plan(
        source_plan,
        repo_root=REPO,
        section_id="insurtech_bullets",
        target_role="VP",
        jd_text="Lead agentic AI platform strategy.",
        briefing_text="AIG agentic AI.",
    )

    source_by_root = {
        str(row["role_episode_bundle_id"]): row for row in source_plan["facts"]
    }
    assert all(
        row == source_by_root[str(row["role_episode_bundle_id"])]
        for row in bound["facts"]
    )
    assert len(bound["facts"]) == 10
    assert bound["selection_method"] == source_plan["selection_method"]
    assert bound["selected_skills"] == selector_plan["selected_skills"]
    authority = bound["selected_skills_authority"]
    assert authority["selector_plan_digest"] == selector_plan["plan_digest"]
    assert authority["skills_synthesized_from_facts"] is False
    assert authority["source_required_fact_ids"] == source_plan["required_fact_ids"]
    assert authority["authority_narrowed_root_ids"] == [
        "reb_insurtech_founder_led_gtm_revenue",
        "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
    ]


def test_selector_skill_binding_fails_closed_without_exact_fact_roots(monkeypatch) -> None:
    selector_plan = {
        "plan_id": "selector:test",
        "plan_digest": "digest",
        "selection_method": "selected_graph_evidence_plan_unify_bullets",
        "selected_skills": [
            {
                "skill_id": "skill_graph_authorized",
                "role_episode_bundle_id": "reb_unify_graph_authorized",
            }
        ],
    }
    monkeypatch.setattr(
        "apps_rg.runtime.sections.graph_role_episode_selector."
        "build_selected_graph_evidence_plan_for_section",
        lambda **_kwargs: (selector_plan, [], set()),
    )

    with pytest.raises(ValueError, match="no role_episode_bundle_id bindings"):
        bind_selector_selected_skills_to_section_plan(
            {"section_id": "unify_bullets", "facts": [{"fact_id": "bul_unify_001"}]},
            repo_root=REPO,
            section_id="unify_bullets",
            target_role="VP",
            jd_text="platform",
            briefing_text="brief",
        )

    with pytest.raises(ValueError, match="selector-selected skill roots are absent"):
        bind_selector_selected_skills_to_section_plan(
            {
                "section_id": "ibm_bullets",
                "facts": [
                    {
                        "fact_id": "bul_ibm_001",
                        "role_episode_bundle_id": "reb_ibm_other_root",
                    }
                ],
            },
            repo_root=REPO,
            section_id="ibm_bullets",
            target_role="VP",
            jd_text="platform",
            briefing_text="brief",
        )


def test_end_to_end_proof_pool_nonempty_for_all_four_lanes() -> None:
    """Full proof resolution: insurtech/ey bullets+narrative use graph bundle ids."""
    from types import SimpleNamespace

    pytest.importorskip(
        "apps_rg_runtime.runtime.contracts.apps_rg_ingress_payload",
        reason="standalone checkout omits the external Agentic Workflow contract runtime",
    )
    from apps_rg.runtime.c0.section_proof_loader import load_section_proof_for_lane

    args = SimpleNamespace(
        provider="external_claude", temperature=0.3, x1d_judges="", mock_judges=True,
        allow_test_mock_judges=True, allow_non_allow_exit_zero=True,
        target_title="VP Global Head of Agentic AI Solutions", target_company="AIG",
        target_role="VP", jd_text="Lead agentic AI platform strategy.",
        briefing="AIG agentic AI.", base_resume_ref="",
    )
    expectations = {
        # Two bundle roots contain only DRAFT/pending-source skills, so the
        # authority-passing selector narrows the 12 source bundles to 10.
        "insurtech_bullets": ("reb_insurtech_", 10),
        "insurtech_narrative": ("reb_insurtech_", 10),
        "ey_bullets": ("reb_ey_", 5),
        "ey_narrative": ("reb_ey_", 5),
    }
    for sid, (prefix, expected_count) in expectations.items():
        pool, *_ = load_section_proof_for_lane(section_id=sid, args=args, repo_root=REPO)
        facts = (pool.selected_fact_plan or {}).get("facts") or []
        allowed = pool.allowed_fact_ids_ordered or []
        root_ids = [str(fact.get("fact_id") or "") for fact in facts]
        assert len(facts) == expected_count, f"{sid}: expected graph facts, got {len(facts)}"
        assert set(root_ids).issubset(allowed), f"{sid}: selected roots missing from graph allowlist"
        assert pool.base_resume_fallback_used is False
        assert all(root_id.startswith(prefix) for root_id in root_ids)
        assert (pool.selected_fact_plan or {}).get("selected_skills")
