from __future__ import annotations

import copy
import random
from pathlib import Path

import pytest

from apps_rg.runtime.c0.resume_graph_allocation import (
    ALLOCATION_PLAN_ENV,
    ALL_CLAIM_BEARING_SECTIONS,
    ResumeGraphAllocationError,
    SECTION_EVIDENCE_CONTRACTS_ENV,
    SECTION_SOURCE_PLANS_ENV,
    allocate_candidate_sets,
    build_section_only_graph_allocation,
    build_resume_graph_usage_ledger,
    build_whole_resume_graph_allocation,
    CANONICAL_BULLET_CLAIM_UNITS,
    normalize_metric_signature,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
    write_whole_resume_graph_allocation_bundle,
)
from apps_rg.runtime.c0.c06_weak_refine import _validate_frozen_selected_plan
from apps_rg.runtime.c0.constants import C0_SECTIONS_ENABLED
from apps_rg.runtime.section_graph_skills_proof_pool import (
    bind_selector_selected_skills_to_section_plan,
)
from apps_rg.runtime.proof_pool_resolver import resolve_section_proof_pool


def _candidate(
    slot_id: str,
    skill_id: str,
    *,
    score: float,
    fact_id: str | None = None,
    metric_id: str = "",
    metric_text: str = "",
    authority_pass: bool = True,
    employer_lane: str = "unify",
) -> dict[str, object]:
    fact = fact_id or f"fact_{skill_id}"
    return {
        "candidate_id": f"cand:{slot_id}:{skill_id}:{metric_id or 'no_metric'}",
        "section_id": slot_id.split(":", 1)[0],
        "claim_unit_id": slot_id,
        "skill_id": skill_id,
        "fact_id": fact,
        "metric_outcome_id": metric_id,
        "metric_text": metric_text,
        "authority_pass": authority_pass,
        "proof_strength_raw": score,
        "target_alignment_score": score / 2,
        "path_confidence_raw": 1.0,
        "source_independence_score": 1.0,
        "employer_lane": employer_lane,
        "source_family": employer_lane,
        "graph_path_ids": [f"root:{fact}", f"root:{fact}/skill:{skill_id}"],
        "edge_ids": [f"edge:{fact}:{skill_id}"],
        "citation_refs": [fact],
        "metric_value": "22" if metric_id else "",
        "metric_unit": "USD_M" if metric_id else "",
    }


def _matrix() -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    slots = [
        {"slot_id": "headline:001", "section_id": "headline", "metric_required": False},
        {
            "slot_id": "executive_summary:001",
            "section_id": "executive_summary",
            "metric_required": True,
        },
        {
            "slot_id": "unify_bullets:001",
            "section_id": "unify_bullets",
            "metric_required": False,
            "employer_lane": "unify",
        },
    ]
    candidates = {
        "headline:001": [
            _candidate("headline:001", "skill_a", score=0.91),
            _candidate("headline:001", "skill_b", score=0.88),
        ],
        "executive_summary:001": [
            _candidate(
                "executive_summary:001",
                "skill_a",
                score=0.99,
                metric_id="metric_revenue",
                metric_text="$22M revenue",
            ),
            _candidate(
                "executive_summary:001",
                "skill_c",
                score=0.87,
                metric_id="metric_margin",
                metric_text="35 percent margin",
            ),
        ],
        "unify_bullets:001": [
            _candidate("unify_bullets:001", "skill_b", score=0.95),
            _candidate("unify_bullets:001", "skill_d", score=0.84),
        ],
    }
    return candidates, slots


def test_allocation_is_permutation_invariant_and_has_zero_reuse() -> None:
    candidates, slots = _matrix()
    expected = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
    )

    shuffled_candidates = copy.deepcopy(candidates)
    rng = random.Random(13)
    for rows in shuffled_candidates.values():
        rng.shuffle(rows)
    shuffled_slots = list(reversed(copy.deepcopy(slots)))
    actual = allocate_candidate_sets(
        candidate_sets=dict(reversed(list(shuffled_candidates.items()))),
        slot_specs=shuffled_slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
    )

    assert actual["allocation_plan_digest"] == expected["allocation_plan_digest"]
    assert actual["assignments"] == expected["assignments"]
    assert actual["uniqueness_receipt"]["pass"] is True
    assert not actual["uniqueness_receipt"]["repeated_skill_ids"]
    assert not actual["uniqueness_receipt"]["repeated_metric_outcome_ids"]


def test_blocked_highest_score_never_wins() -> None:
    candidates, slots = _matrix()
    candidates["headline:001"].append(
        _candidate("headline:001", "skill_blocked", score=100.0, authority_pass=False)
    )
    plan = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
    )
    assert "skill_blocked" not in {row["skill_id"] for row in plan["assignments"]}
    blocked = [
        row
        for row in plan["candidate_decisions"]
        if row["candidate_id"].endswith(":skill_blocked:no_metric")
    ]
    assert blocked and blocked[0]["reason_codes"] == ["authority_gate_failed"]


def test_selection_margin_records_global_constraint_tradeoff() -> None:
    candidates, slots = _matrix()
    plan = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
    )
    assignments = {row["claim_unit_id"]: row for row in plan["assignments"]}

    # The globally unique solution reserves skill_a for executive summary, so
    # headline selects skill_b even though skill_a is its stronger local peer.
    headline = assignments["headline:001"]
    assert headline["skill_id"] == "skill_b"
    assert headline["selection_margin"] == -0.03
    assert headline["selection_margin_available"] is True
    assert headline["selection_margin_basis"] == "proof_strength_raw"
    assert headline["best_eligible_rejected_candidate_id"].endswith(
        ":skill_a:no_metric"
    )
    assert (
        plan["solver_metadata"]["selection_margin_policy"]
        == "signed_first_differing_lexicographic_component_vs_best_locally_eligible_rejected_v1"
    )


def test_equivalent_metric_signatures_cannot_be_reused() -> None:
    slots = [
        {"slot_id": "executive_summary:001", "section_id": "executive_summary", "metric_required": True},
        {"slot_id": "unify_bullets:001", "section_id": "unify_bullets", "metric_required": True},
    ]
    candidates = {
        "executive_summary:001": [
            _candidate(
                "executive_summary:001",
                "skill_a",
                score=1.0,
                metric_id="metric_a",
                metric_text="35% operating margin",
            )
        ],
        "unify_bullets:001": [
            _candidate(
                "unify_bullets:001",
                "skill_b",
                score=1.0,
                metric_id="metric_b",
                metric_text="35 percent operating margin",
            )
        ],
    }
    with pytest.raises(ResumeGraphAllocationError, match="normalized_metric_signature") as exc:
        allocate_candidate_sets(
            candidate_sets=candidates,
            slot_specs=slots,
            graph_digest="g" * 64,
            policy_digest="p" * 64,
        )
    assert "unsatisfied_constraints" in exc.value.receipt


def test_usage_ledger_is_plan_bound_and_section_only_does_not_claim_global_uniqueness() -> None:
    candidates, slots = _matrix()
    plan = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
        allocation_scope="SECTION_ONLY",
    )
    ledger = build_resume_graph_usage_ledger(plan)
    assert plan["global_uniqueness_claimed"] is False
    assert ledger["allocation_plan_digest"] == plan["allocation_plan_digest"]
    assert ledger["durable_graph_state_mutated"] is False
    assert ledger["current_run_only"] is True
    assert validate_resume_graph_allocation_plan(plan) == []


def test_section_only_allocation_preserves_graph_authored_visible_surfaces() -> None:
    """A late résumé projection must never need to reverse-engineer graph IDs."""

    section_plan = {
        "section_id": "competencies",
        "plan_id": "competencies:unit",
        "plan_digest": "p" * 64,
        "source_authority_contract": {"graph_digest": "g" * 64},
        "graph_traversal_receipt": {"pass": True, "events_digest": "e" * 64},
        "facts": [
            {
                "role_episode_bundle_id": "reb_controls",
                "domain": "Regulated AWS Control Implementation",
                "claim_text": "Implemented AWS controls for regulated insurers.",
                "linked_source_fact_ids": ["fact_controls"],
            }
        ],
        "selected_skills": [
            {
                "skill_id": "skill_aws_iam_kms_cloudtrail_controls",
                "role_episode_bundle_id": "reb_controls",
            }
        ],
        "graph_candidate_decision_ledger": [
            {
                "candidate_id": "skill_aws_iam_kms_cloudtrail_controls",
                "candidate_type": "leaf_skill",
                "root_id": "reb_controls",
                "skill_label": "AWS IAM KMS CloudTrail Controls",
                "source_refs": ["fact_controls", "Implemented AWS controls for regulated insurers."],
            }
        ],
    }

    result = build_section_only_graph_allocation(
        section_plan=section_plan,
        section_id="competencies",
    )
    assignment = result["allocation_plan"]["assignments"][0]
    assert assignment["skill_label"] == "AWS IAM KMS CloudTrail Controls"
    assert assignment["root_bundle_theme"] == "Regulated AWS Control Implementation"
    assert "Implemented AWS controls for regulated insurers." in assignment["source_refs"]


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("35% operating margin", "35 percent operating margin"),
        ("$22M IP-led revenue", "USD 22 million IP led revenue"),
    ],
)
def test_metric_signature_normalization_collapses_equivalent_surfaces(
    left: str, right: str
) -> None:
    assert normalize_metric_signature(left) == normalize_metric_signature(right)


def test_real_graph_whole_resume_allocation_covers_all_lanes_and_is_order_invariant() -> None:
    repo = Path(__file__).resolve().parents[5]
    forward = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Agentic Engineering and Platform",
    )
    section_order = list(reversed(list(forward["section_plans"])))
    reverse = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Agentic Engineering and Platform",
        section_order=section_order,
    )
    plan = forward["allocation_plan"]
    assert reverse["allocation_plan"]["allocation_plan_digest"] == plan[
        "allocation_plan_digest"
    ]
    assert plan["uniqueness_receipt"]["pass"] is True
    assert plan["global_uniqueness_claimed"] is True
    assert len(plan["assignments"]) == 48
    assert set(forward["section_final_evidence_contracts"]) == set(
        forward["section_plans"]
    )
    assert all(
        row["pass"] is True
        for row in forward["section_final_evidence_contracts"].values()
    )
    headline_slice = slice_section_plan_for_allocation(
        section_plan=forward["section_plans"]["headline"],
        allocation_plan=plan,
        final_evidence_contract=forward["section_final_evidence_contracts"]["headline"],
        section_id="headline",
    )
    allocated_headline_skills = {
        row["skill_id"]
        for row in plan["assignments"]
        if row["section_id"] == "headline"
    }
    assert len(allocated_headline_skills) == 3
    assert set(headline_slice["selected_skill_ids"]) == allocated_headline_skills
    assert headline_slice["allocation_plan_digest"] == plan["allocation_plan_digest"]


def test_allocation_slices_keep_exact_selected_authority_paths() -> None:
    """Every frozen allocation slice must remain a valid C0.6 retry input."""

    repo = Path(__file__).resolve().parents[5]
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Agentic Engineering and Platform",
        jd_text="agentic platform governance revenue growth margin",
        briefing_text="enterprise platform operating model",
    )
    allocation = bundle["allocation_plan"]
    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        sliced = slice_section_plan_for_allocation(
            section_plan=bundle["section_plans"][section_id],
            allocation_plan=allocation,
            final_evidence_contract=bundle["section_final_evidence_contracts"][section_id],
            section_id=section_id,
        )
        assert _validate_frozen_selected_plan(sliced, section_id=section_id) == []
        expected_pairs = {
            (
                str(fact.get("role_episode_bundle_id") or fact["fact_id"]),
                str(skill_id),
            )
            for fact in sliced["facts"]
            for skill_id in fact.get("graph_skill_node_ids") or []
        }
        observed_pairs = {
            (str(row["root_id"]), str(row["candidate_id"]))
            for row in sliced["graph_candidate_decision_ledger"]
            if row.get("candidate_type") == "leaf_skill"
            and row.get("allocation_selected") is True
        }
        assert observed_pairs == expected_pairs
        if section_id in CANONICAL_BULLET_CLAIM_UNITS:
            assert {
                str(fact.get("fact_id") or "") for fact in sliced["facts"]
            } == set(CANONICAL_BULLET_CLAIM_UNITS[section_id])
            assert all(
                str(fact.get("role_episode_bundle_id") or "").startswith("reb_")
                for fact in sliced["facts"]
            )
        source_traversal = sliced["allocation_source_traversal_evidence"]
        assert source_traversal["scope"] == "C03_SOURCE_CANDIDATE_UNIVERSE"
        assert source_traversal["graph_candidate_receipt"]["candidate_decision_count"] >= len(
            sliced["graph_candidate_decision_ledger"]
        )


def test_whole_resume_bullet_lanes_use_frozen_root_plans_and_keep_visible_slots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A final bullet lane must not try to attach graph roots to legacy slots."""

    repo = Path(__file__).resolve().parents[5]
    target_role = "SVP Agentic Engineering and Platform"
    jd_text = "agentic platform governance revenue growth margin"
    briefing_text = "enterprise platform operating model"
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    refs = write_whole_resume_graph_allocation_bundle(
        bundle,
        output_dir=tmp_path / "frozen_whole_resume",
    )
    monkeypatch.setenv(ALLOCATION_PLAN_ENV, refs["allocation_plan"])
    monkeypatch.setenv(
        SECTION_EVIDENCE_CONTRACTS_ENV,
        refs["section_final_evidence_contracts"],
    )
    monkeypatch.setenv(SECTION_SOURCE_PLANS_ENV, refs["section_plans"])

    for section_id, claim_unit_ids in CANONICAL_BULLET_CLAIM_UNITS.items():
        legacy_visible_plan = {
            "section_id": section_id,
            "facts": [{"fact_id": claim_unit_id} for claim_unit_id in claim_unit_ids],
        }
        frozen_source = bind_selector_selected_skills_to_section_plan(
            legacy_visible_plan,
            repo_root=repo,
            section_id=section_id,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
        )
        assert frozen_source["plan_digest"] == bundle["section_plans"][section_id][
            "plan_digest"
        ]
        assert all(
            str(fact.get("role_episode_bundle_id") or "").startswith("reb_")
            for fact in frozen_source["facts"]
        )

        sliced = slice_section_plan_for_allocation(
            section_plan=frozen_source,
            allocation_plan=bundle["allocation_plan"],
            final_evidence_contract=bundle["section_final_evidence_contracts"][
                section_id
            ],
            section_id=section_id,
        )
        assert {
            str(fact.get("fact_id") or "") for fact in sliced["facts"]
        } == set(claim_unit_ids)
        assert _validate_frozen_selected_plan(sliced, section_id=section_id) == []
        if section_id == "unify_bullets":
            slot_map = frozen_source["unify_bullet_slot_bundle_map_resolved"]
            assignments = {
                str(row["claim_unit_id"]): row
                for row in sliced["allocation_assignments"]
            }
            assert {
                str(fact["fact_id"]): str(fact["role_episode_bundle_id"])
                for fact in sliced["facts"]
            } == slot_map
            assert all(
                str(assignments[f"unify_bullets:{slot_id}"]["root_id"])
                == str(expected_root)
                for slot_id, expected_root in slot_map.items()
            )
            assert all(
                assignments[f"unify_bullets:{slot_id}"].get("metric_outcome_id")
                for slot_id in slot_map
            )


def test_whole_resume_shared_lanes_consume_sealed_source_plans_before_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase-one shared lanes may not re-run selection after C0.3 seals it."""

    repo = Path(__file__).resolve().parents[5]
    jd_text = (repo / "src/apps_rg/config/targeting" / "anthropic_manager_applied_ai_architecture_partnerships_jd.txt").read_text(
        encoding="utf-8"
    )
    briefing_text = (
        repo
        / "tests/fixtures/apps_rg"
        / "anthropic_manager_applied_ai_architecture_partnerships_briefing.md"
    ).read_text(encoding="utf-8")
    target_role = jd_text.split("\n", 1)[0]
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    refs = write_whole_resume_graph_allocation_bundle(
        bundle,
        output_dir=tmp_path / "frozen_whole_resume",
    )
    monkeypatch.setenv(ALLOCATION_PLAN_ENV, refs["allocation_plan"])
    monkeypatch.setenv(
        SECTION_EVIDENCE_CONTRACTS_ENV,
        refs["section_final_evidence_contracts"],
    )
    monkeypatch.setenv(SECTION_SOURCE_PLANS_ENV, refs["section_plans"])

    def _selector_must_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("whole-resume execution must use its sealed C0.3 source plan")

    monkeypatch.setattr(
        "apps_rg.runtime.sections.graph_role_episode_selector."
        "build_selected_graph_evidence_plan_for_section",
        _selector_must_not_run,
    )

    for section_id in ("executive_summary", "headline"):
        pool = resolve_section_proof_pool(
            section=section_id,
            repo_root=repo,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
            product_visible=False,
        )
        frozen_source_digest = bundle["section_plans"][section_id]["plan_digest"]
        final_contract = pool.proof_pool_metadata["final_graph_evidence_contract"]
        assert final_contract["source_section_plan_digest"] == frozen_source_digest
        assert pool.selected_fact_plan["allocation_plan_digest"] == bundle[
            "allocation_plan"
        ]["allocation_plan_digest"]


def test_c0_authority_lane_set_matches_whole_resume_allocator() -> None:
    assert C0_SECTIONS_ENABLED == frozenset(ALL_CLAIM_BEARING_SECTIONS)
