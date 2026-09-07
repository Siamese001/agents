"""W4 — competencies graph_8x8 pool (adaptive paths -> 6-8 categories) + selector/judge split.

The selector receipt is Anthropic-backed; the formal competencies judge is Gemini-backed.
"""

from __future__ import annotations

import json

from tests.helpers import apps_rg_model_pins as pins

import pytest

from apps_rg.runtime.judges.bullet_pool_claude_selector import (
    PoolSelectionResult,
    PoolSelectorUnavailableError,
    _call_anthropic_pool_selector,
    _format_competency_pool,
    run_claude_bullet_pool_selection,
)
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.reasoning.bullet_lane_self_consistency import SelfConsistencyPath
from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude
from apps_rg.runtime.reasoning.competencies_graph_pool import (
    COMPETENCIES_CANDIDATE_CATEGORY_COUNT,
    COMPETENCIES_FINAL_CATEGORY_COUNT,
    COMPETENCIES_MAX_CATEGORY_COUNT,
    COMPETENCIES_MIN_CATEGORY_COUNT,
    COMPETENCIES_SC_PATH_COUNT,
    build_competencies_rejected_neighbor_audit,
    build_competencies_targeting_context,
    competencies_max_sc_path_count,
    evaluate_competencies_selection_quality,
    high_signal_competencies_selection_score,
    is_competencies_pool_generation,
    merge_competencies_graph_pool_top_eight,
    min_competencies_selection_score,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    competencies_pool_x1d_judge_rows,
    sc_path_count_for_lane,
)
from apps_rg.runtime.sections.section_product_shape_ssot import section_product_shape
from apps_rg.runtime.sections.competencies_lane_runtime import normalize_parsed_output
from apps_rg.runtime.sections.competencies_v3_contract import (
    category_v3_from_legacy,
    legacy_category_from_v3,
    sync_categories_competencies,
)
from apps_rg.runtime.sections.competencies_capability_projection import (
    apply_executive_capability_projection,
)


_DISTINCT_GRAPH_BUNDLE_IDS = (
    "ccb_partner_applied_ai_architecture",
    "ccb_agentic_platforms",
    "ccb_runtime_governance",
    "ccb_retrieval_context_engineering",
    "ccb_platform_productization",
    "ccb_llmops_reliability",
    "ccb_distributed_systems_engineering",
    "ccb_engineering_leadership",
)


def _cat(label: str, terms: list[str], *, bundle_id: str | None = None) -> dict:
    row = {
        "category_label": label,
        "terms": [
            {
                "text": t,
                "source_fact_id": "bul_001",
                "source_fact_ids": ["bul_001"],
                "support_class": "FACT_ONLY",
            }
            for t in terms
        ],
        "source_fact_ids": ["bul_001"],
    }
    if bundle_id:
        row["competency_bundle_id"] = bundle_id
    return row


def _path_with_categories(
    path_index: int,
    n_categories: int = COMPETENCIES_FINAL_CATEGORY_COUNT,
) -> SelfConsistencyPath:
    return SelfConsistencyPath(
        path_index=path_index,
        temperature=0.35 + path_index * 0.01,
        runtime_generation_status="REAL_LLM",
        raw_output="",
        parsed={
            "competencies": [
                _cat(
                    f"Category_{path_index}_{i}",
                    [f"t{i}a", f"t{i}b"],
                    bundle_id=_DISTINCT_GRAPH_BUNDLE_IDS[i],
                )
                for i in range(n_categories)
            ],
            "claim_ledger": [],
        },
        parse_error="",
        provider_result=None,
    )


class _FakeSelectorJudge:
    def __init__(
        self,
        *,
        provider_key: str = "anthropic_claude",
        model_name: str = pins.COMPETENCIES_SELECTOR_MODEL,
        passed: bool = True,
        status: str = "MODEL_BACKED_PASS",
        exact_provider_error: str | None = None,
        rationale: str = "yaml_judge_models",
    ) -> None:
        self.judge_id = f"x1d_{provider_key}_bullet_pool_selector"
        self.provider_name = "Anthropic Claude"
        self.provider_key = provider_key
        self.evaluator_mode = "MODEL_BACKED"
        self.provider_status = status
        self.model_name = model_name
        self.provider_available = True
        self.provider_blocked = not passed
        self.exact_provider_error = exact_provider_error
        self.pass_ = passed
        self.rationale = rationale

    def to_dict(self) -> dict[str, object]:
        return {
            "judge_id": self.judge_id,
            "provider_name": self.provider_name,
            "provider_key": self.provider_key,
            "evaluator_mode": self.evaluator_mode,
            "provider_status": self.provider_status,
            "model_name": self.model_name,
            "provider_available": self.provider_available,
            "provider_blocked": self.provider_blocked,
            "exact_provider_error": self.exact_provider_error,
            "pass": self.pass_,
            "pass_": self.pass_,
            "rationale": self.rationale,
        }


def test_competencies_pool_generation_mode_detected() -> None:
    assert is_competencies_pool_generation(
        {"generation_mode": "model_competencies_graph_pool_adaptive_6_8_regen"}
    )
    assert not is_competencies_pool_generation({"generation_mode": "singleton"})


def test_sc_path_count_and_targeting_context_graph_8x8() -> None:
    # HBS/SVP alignment (2026-06): start with 4 SC paths, expand toward 8 only if gates need it.
    assert sc_path_count_for_lane("competencies") == COMPETENCIES_SC_PATH_COUNT == 4
    ctx = build_competencies_targeting_context(
        {
            "target_title": "SVP",
            "target_company": "Acme",
            "jd_text": "agentic AI",
            "briefing": "platform",
            "proof_pool_metadata": {
                "graph_ref": "artifacts/skills/graph.json",
                "proof_pool_type": "augmented_skills_graph",
                "selected_skill_rows": [{"skill_id": "sk_graph_001"}],
            },
            "selected_fact_plan": {"selection_method": "augmented_skills_graph"},
        },
        allowed_fact_ids={"bul_001"},
        allowed_skill_ids={"sk_graph_001"},
    )
    assert ctx["candidate_category_count"] == COMPETENCIES_CANDIDATE_CATEGORY_COUNT
    assert ctx["min_category_count"] == COMPETENCIES_MIN_CATEGORY_COUNT
    assert ctx["max_category_count"] == COMPETENCIES_MAX_CATEGORY_COUNT
    assert ctx["final_category_count"] == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert ctx["pool_path_count"] == 4
    assert ctx["initial_sc_path_count"] == 4
    assert ctx["max_sc_path_count"] == 8
    assert ctx["high_signal_selection_score"] == high_signal_competencies_selection_score()
    assert ctx["proof_pool_type"] == "augmented_skills_graph"
    assert ctx["selection_model"] == "graph_8x8_v1"


def test_section_product_shape_competencies_adaptive_six_to_eight() -> None:
    shape = section_product_shape("competencies")
    assert "x2_competencies_min_category_count" in shape.required_gate_ids
    assert "graph_8x8" in shape.shape_summary
    assert "adaptive 6-8" in shape.shape_summary


@pytest.mark.parametrize("alias_key", ["category", "display_label"])
def test_provider_category_alias_is_canonicalized_before_selector(alias_key: str) -> None:
    raw_category = {
        alias_key: "Partner Applied AI Architecture",
        "competency_bundle_id": "ccb_partner_applied_ai_architecture",
        "graph_skill_node_ids": ["skill_partner_architecture"],
        "terms": [
            {
                "text": "partner-led AI solution architecture",
                "source_fact_id": "bul_001",
                "source_fact_ids": ["bul_001"],
            }
        ],
        "source_fact_ids": ["bul_001"],
    }
    normalized = normalize_parsed_output(
        {"categories": [raw_category]},
        {"selected_fact_plan": {"required_fact_ids": ["bul_001"]}},
        {"bul_001"},
    )
    assert normalized is not None
    category = normalized["categories"][0]
    assert category["category_label"] == "Partner Applied AI Architecture"
    assert "category" not in category
    assert "display_label" not in category

    canonical = category_v3_from_legacy(raw_category)
    legacy = legacy_category_from_v3(canonical)
    assert canonical["category_label"] == "Partner Applied AI Architecture"
    assert canonical["competency_bundle_id"] == "ccb_partner_applied_ai_architecture"
    assert legacy["competency_bundle_id"] == "ccb_partner_applied_ai_architecture"
    assert legacy["graph_skill_node_ids"] == ["skill_partner_architecture"]

    path = SelfConsistencyPath(
        path_index=0,
        temperature=0.35,
        runtime_generation_status="REAL_LLM",
        raw_output="",
        parsed={"categories": [canonical]},
        parse_error="",
        provider_result=None,
    )
    pool_text = _format_competency_pool([path])
    assert "[Partner Applied AI Architecture]" in pool_text
    assert "[] terms=" not in pool_text

    merged, source_map = merge_competencies_graph_pool_top_eight(
        [path],
        [
            {
                "category_label": "Partner Applied AI Architecture",
                "path_index": 0,
                "score": 0.9,
                "passes": True,
            }
        ],
        min_score_threshold=0.72,
    )
    assert merged["competencies"][0]["category_label"] == "Partner Applied AI Architecture"
    assert source_map == {"partner applied ai architecture": 0}


def test_evaluate_competencies_gate_rejects_text_only_family_smuggling() -> None:
    labels = [f"Cat_{i}" for i in range(COMPETENCIES_MIN_CATEGORY_COUNT)]
    selections = [
        {"category_label": lab, "path_index": 0, "score": 0.9, "passes": True} for lab in labels
    ]
    merged = {
        "competencies": [
            _cat(lab, ["a", "b"], bundle_id=_DISTINCT_GRAPH_BUNDLE_IDS[index])
            for index, lab in enumerate(labels)
        ]
    }
    merged["competencies"][0]["terms"].extend(
        [
            {"text": "distributed cloud infrastructure", "source_fact_ids": ["bul_001"]},
            {"text": "engineering organization leadership", "source_fact_ids": ["bul_001"]},
        ]
    )
    gate = evaluate_competencies_selection_quality(
        selections=selections,
        merged_parsed=merged,
        min_score=min_competencies_selection_score(),
    )
    assert gate.ok is False
    assert gate.missing_capability_families == (
        "distributed_infra",
        "engineering_leadership",
    )
    assert gate.categories_in_merged == COMPETENCIES_MIN_CATEGORY_COUNT
    assert gate.min_category_count == COMPETENCIES_MIN_CATEGORY_COUNT
    assert gate.max_category_count == COMPETENCIES_MAX_CATEGORY_COUNT


def test_merge_competencies_graph_pool_preserves_selector_scores() -> None:
    labels = [f"Category_0_{i}" for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)]
    scores = [0.91, 0.89, 0.88, 0.86, 0.84, 0.83, 0.81, 0.78]
    selections = [
        {"category_label": lab, "path_index": 0, "score": score, "passes": True}
        for lab, score in zip(labels, scores, strict=True)
    ]
    merged, _ = merge_competencies_graph_pool_top_eight(
        [_path_with_categories(0)],
        selections,
        min_score_threshold=0.72,
    )

    merged_scores = [
        row.get("selection_score")
        for row in (merged.get("competencies") or [])
    ]
    assert merged_scores == scores


def test_graph_pool_preserves_all_eight_distinct_passing_selector_rows() -> None:
    path = _path_with_categories(0)
    assert path.parsed is not None
    for index, row in enumerate(path.parsed["competencies"]):
        if index >= COMPETENCIES_MIN_CATEGORY_COUNT:
            row["terms"] = [
                {
                    "text": f"unsupported selected term {index}",
                    "source_fact_ids": [f"not_allowed_{index}"],
                }
            ]
    selections = [
        {
            "category_label": row["category_label"],
            "path_index": 0,
            "score": 0.95 - index * 0.01,
            "passes": True,
        }
        for index, row in enumerate(path.parsed["competencies"])
    ]

    merged, _ = merge_competencies_graph_pool_top_eight(
        [path],
        selections,
        min_score_threshold=0.72,
        allowed_fact_ids={"bul_001"},
    )

    assert len(merged["competencies"]) == COMPETENCIES_MAX_CATEGORY_COUNT
    assert {
        row["competency_bundle_id"] for row in merged["competencies"]
    } == set(_DISTINCT_GRAPH_BUNDLE_IDS)


def test_graph_pool_merge_replaces_stale_anchor_categories_atomically() -> None:
    path = _path_with_categories(0, COMPETENCIES_MIN_CATEGORY_COUNT)
    assert path.parsed is not None
    selected_rows = list(path.parsed["competencies"])
    selected_bundle_ids = {
        str(row["competency_bundle_id"]) for row in selected_rows
    }
    path.parsed["categories"] = [
        _cat(
            f"Stale anchor {index}",
            [f"stale{index}a", f"stale{index}b"],
            bundle_id=(
                "ccb_distributed_systems_engineering"
                if index == 0
                else "ccb_agentic_platforms"
            ),
        )
        for index in range(COMPETENCIES_MIN_CATEGORY_COUNT)
    ]
    selections = [
        {
            "category_label": row["category_label"],
            "path_index": 0,
            "score": 0.95 - index * 0.01,
            "passes": True,
        }
        for index, row in enumerate(selected_rows)
    ]

    merged, _ = merge_competencies_graph_pool_top_eight(
        [path], selections, min_score_threshold=0.72
    )
    sync_categories_competencies(merged)

    assert {
        str(row["competency_bundle_id"]) for row in merged["categories"]
    } == selected_bundle_ids
    assert {
        str(row["competency_bundle_id"]) for row in merged["competencies"]
    } == selected_bundle_ids
    assert all(
        not str(row["category_label"]).startswith("Stale anchor")
        for row in merged["categories"]
    )


def test_graph_pool_deduplicates_bundle_and_taxonomy_identities() -> None:
    path = _path_with_categories(0)
    assert path.parsed is not None
    path.parsed["competencies"][1]["competency_bundle_id"] = _DISTINCT_GRAPH_BUNDLE_IDS[0]
    labels = [f"Category_0_{i}" for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)]
    selections = [
        {
            "category_label": label,
            "path_index": 0,
            "score": 0.95 - index * 0.01,
            "passes": True,
        }
        for index, label in enumerate(labels)
    ]

    merged, _ = merge_competencies_graph_pool_top_eight(
        [path], selections, min_score_threshold=0.72
    )
    rows = merged["competencies"]
    assert len(rows) == 7
    bundle_ids = [row["competency_bundle_id"] for row in rows]
    assert len(bundle_ids) == len(set(bundle_ids))
    gate = evaluate_competencies_selection_quality(
        selections=selections,
        merged_parsed=merged,
        min_score=0.72,
    )
    assert gate.ok is False
    assert gate.missing_capability_families
    assert gate.duplicate_bundle_ids == ()
    assert gate.duplicate_taxonomy_category_ids == ()


def test_graph_pool_keeps_selector_winner_with_one_of_three_allowed_terms() -> None:
    path = _path_with_categories(0, COMPETENCIES_MIN_CATEGORY_COUNT)
    assert path.parsed is not None
    runtime_category = path.parsed["competencies"][2]
    runtime_category["terms"] = [
        {
            "text": "allowed runtime graph control",
            "source_fact_id": "bul_001",
            "source_fact_ids": ["bul_001"],
        },
        {
            "text": "unsupported candidate term one",
            "source_fact_id": "not_allowed_1",
            "source_fact_ids": ["not_allowed_1"],
        },
        {
            "text": "unsupported candidate term two",
            "source_fact_id": "not_allowed_2",
            "source_fact_ids": ["not_allowed_2"],
        },
    ]
    selections = [
        {
            "category_label": row["category_label"],
            "path_index": 0,
            "score": 0.95 - index * 0.01,
            "passes": True,
        }
        for index, row in enumerate(path.parsed["competencies"])
    ]

    merged, _ = merge_competencies_graph_pool_top_eight(
        [path],
        selections,
        min_score_threshold=0.72,
        allowed_fact_ids={"bul_001"},
    )

    assert runtime_category["competency_bundle_id"] in {
        row["competency_bundle_id"] for row in merged["competencies"]
    }


def test_taxonomy_projection_preserves_selected_graph_bundle_authority() -> None:
    bundle_ids = _DISTINCT_GRAPH_BUNDLE_IDS[:6]
    parsed = {
        "categories": [
            {
                "category_id": bundle_id,
                "category_label": f"Dynamic capability {index}",
                "competency_bundle_id": bundle_id,
                "graph_skill_node_ids": [f"skill_{index}"],
                "selection_score": 0.9 - index * 0.01,
                "terms": [
                    {
                        "term": f"Graph capability mechanism {index}",
                        "source_fact_ids": ["bul_001"],
                        "support_class": "FACT_ONLY",
                    }
                ],
                "source_fact_ids": ["bul_001"],
            }
            for index, bundle_id in enumerate(bundle_ids)
        ]
    }

    projected = apply_executive_capability_projection(
        parsed,
        allowed_fact_ids={"bul_001"},
        allowed_skill_ids=set(),
        skill_rows_by_id={},
        resume_support_blob_lower="graph capability mechanism",
    )
    rows = projected["categories"]
    assert len(rows) == 6
    assert {row["competency_bundle_id"] for row in rows} == set(bundle_ids)
    assert all(row["graph_skill_node_ids"] for row in rows)
    assert len({row["category_id"] for row in rows}) == 6
    assert not any(
        change.get("operation") == "drop_unmapped_category"
        for change in projected.get("change_log") or []
    )


def test_taxonomy_projection_prefers_selected_bundle_over_conflicting_model_category_id() -> None:
    parsed = {
        "categories": [
            {
                "category_id": "llmops_reliability",
                "category_label": "Engineering Leadership for AI Platforms",
                "competency_bundle_id": "ccb_engineering_leadership",
                "graph_skill_node_ids": ["skill_engineering_leadership"],
                "selection_score": 0.9,
                "terms": [
                    {
                        "term": "AI engineering organization leadership",
                        "source_fact_ids": ["bul_001"],
                        "support_class": "FACT_ONLY",
                    }
                ],
                "source_fact_ids": ["bul_001"],
            }
        ]
    }

    projected = apply_executive_capability_projection(
        parsed,
        allowed_fact_ids={"bul_001"},
        allowed_skill_ids=set(),
        skill_rows_by_id={},
        resume_support_blob_lower="ai engineering organization leadership",
    )

    row = next(
        item
        for item in projected["categories"]
        if item.get("competency_bundle_id") == "ccb_engineering_leadership"
    )
    assert row["category_id"] == "engineering_delivery_leadership"


def test_normalize_accepts_only_packet_authorized_bundle_id_alias() -> None:
    runtime_payload = {
        "selected_fact_plan": {"required_fact_ids": ["bul_001"]},
        "proof_pool_metadata": {
            "competency_capability_section_packet": {
                "competency_bundles": [
                    {"competency_bundle_id": "ccb_retrieval_context_engineering"}
                ]
            }
        },
    }
    normalized = normalize_parsed_output(
        {
            "categories": [
                {
                    "category_id": "ccb_retrieval_context_engineering",
                    "display_label": "Retrieval & Context Engineering",
                    "terms": [],
                },
                {
                    "category_id": "ccb_model_invented",
                    "display_label": "Invented Bundle",
                    "terms": [],
                },
            ]
        },
        runtime_payload,
        {"bul_001"},
    )
    assert normalized is not None
    assert normalized["categories"][0]["competency_bundle_id"] == (
        "ccb_retrieval_context_engineering"
    )
    assert "competency_bundle_id" not in normalized["categories"][1]


def test_competencies_rejected_neighbor_audit_records_unselected_candidates() -> None:
    paths = [_path_with_categories(0), _path_with_categories(1)]
    labels = [f"Category_0_{i}" for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)]
    selections = [
        {"category_label": lab, "path_index": 0, "score": 0.9, "passes": True}
        for lab in labels
    ]
    merged, source_map = merge_competencies_graph_pool_top_eight(
        paths,
        selections,
        min_score_threshold=0.72,
    )

    audit = build_competencies_rejected_neighbor_audit(
        paths,
        selections,
        merged,
        source_map,
        min_score_threshold=0.72,
    )

    assert audit["schema_version"] == "competencies_rejected_neighbor_audit_v1"
    assert audit["audit_status"] == "present"
    assert audit["candidate_label_count"] == 16
    assert audit["selected_count"] == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert audit["rejected_neighbor_count"] == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert {row["rejection_reason"] for row in audit["rejected_neighbors"]} == {
        "not_selected_by_model"
    }


def test_claude_competencies_selection_emits_high_signal_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [_path_with_categories(0)]
    selections = [
        {
            "category_label": f"Category_0_{i}",
            "path_index": 0,
            "score": 0.9,
            "passes": True,
            "rationale": f"slot {i}",
        }
        for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)
    ]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector.bootstrap_apps_rg_env",
        lambda: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector._call_anthropic_pool_selector",
        lambda **_: (_FakeSelectorJudge(), {"selections": selections, "pool_summary": {}}),
    )
    pool: PoolSelectionResult = run_claude_bullet_pool_selection(
        section_id="competencies",
        slot_kind="competencies",
        paths=paths,
        targeting_context={
            "allowed_fact_ids": ["bul_001"],
            "allowed_skill_ids": [],
            "resume_support_blob_lower": "bul_001 alpha beta",
        },
        mode="blocked_if_unavailable",
    )
    assert pool.selection_mode == "competencies_advisory_selector_required_eight_pass"
    assert pool.judge_output is not None
    assert pool.judge_output.provider_key == "anthropic_claude"
    assert pool.judge_output.model_name == pins.COMPETENCIES_SELECTOR_MODEL
    comps = pool.merged_parsed.get("competencies") or []
    assert len(comps) == COMPETENCIES_FINAL_CATEGORY_COUNT
    audit = pool.rejected_neighbor_audit
    assert audit is not None
    assert audit["schema_version"] == "competencies_rejected_neighbor_audit_v1"


def test_governed_baseline_completes_a_missing_required_bundle() -> None:
    from apps_rg.runtime.judges.bullet_pool_claude_selector import (
        _complete_governed_required_bundle_selections,
    )

    provider_path = _path_with_categories(0)
    baseline_categories = []
    for index, bundle_id in enumerate(_DISTINCT_GRAPH_BUNDLE_IDS):
        category = _cat(
            f"Governed baseline {index}",
            [f"governed supported capability {index}"],
            bundle_id=bundle_id,
        )
        category["candidate_origin"] = "governed_required_bundle_baseline"
        baseline_categories.append(category)
    baseline_path = SelfConsistencyPath(
        path_index=10_000,
        temperature=0.0,
        runtime_generation_status="GOVERNED_GRAPH_BASELINE",
        raw_output="",
        parsed={"competencies": baseline_categories, "categories": baseline_categories},
        parse_error="",
        provider_result=None,
    )
    selections = [
        {
            "category_label": f"Category_0_{index}",
            "path_index": 0,
            "score": 0.9,
            "passes": True,
        }
        for index in range(COMPETENCIES_FINAL_CATEGORY_COUNT - 1)
    ]

    completed, additions, dropped = _complete_governed_required_bundle_selections(
        [provider_path, baseline_path],
        selections,
        min_score_threshold=0.72,
        targeting_context={
            "allowed_fact_ids": ["bul_001"],
            "allowed_skill_ids": [],
            "resume_support_blob_lower": "",
        },
    )

    assert len(completed) == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert dropped == []
    assert [row["competency_bundle_id"] for row in additions] == [
        "ccb_engineering_leadership"
    ]
    assert additions[0]["selection_origin"] == "governed_required_bundle_completion"
    assert additions[0]["score_source"] == "deterministic_graph_fact_support_ratio"


def test_claude_competencies_selector_request_reserves_output_room(
    tmp_path,
) -> None:
    judge_output, selection = _call_anthropic_pool_selector(
        api_key="test-key-never-sent",
        prompt="Select the strongest competencies.",
        model=pins.COMPETENCIES_SELECTOR_MODEL,
        reasoning_effort=pins.COMPETENCIES_SELECTOR_REASONING_EFFORT,
        input_hash="selector-input-hash",
        model_source="test-provider-profile",
        artifact_dir=tmp_path,
        timeout_s=1.0,
    )

    assert selection is None
    assert judge_output.provider_blocked is True
    request_paths = list(
        tmp_path.glob("x1d_anthropic_claude_provider_request_*.json")
    )
    assert len(request_paths) == 1
    payload = json.loads(request_paths[0].read_text(encoding="utf-8"))["payload"]
    assert payload["model"] == pins.COMPETENCIES_SELECTOR_MODEL
    assert payload["output_config"]["effort"] == (
        pins.COMPETENCIES_SELECTOR_REASONING_EFFORT
    ) == "low"
    assert payload["thinking"] == {"type": "adaptive", "display": "omitted"}
    assert payload["max_tokens"] > 0
    assert "temperature" not in payload
    assert "max_completion_tokens" not in payload


def test_claude_competencies_selector_fails_closed_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [_path_with_categories(0)]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector.bootstrap_apps_rg_env",
        lambda: None,
    )

    with pytest.raises(
        PoolSelectorUnavailableError,
        match="competencies selector unavailable: missing Claude credentials",
    ):
        run_claude_bullet_pool_selection(
            section_id="competencies",
            slot_kind="competencies",
            paths=paths,
            targeting_context={
                "allowed_fact_ids": ["bul_001"],
                "allowed_skill_ids": [],
                "resume_support_blob_lower": "bul_001 alpha beta",
            },
            mode="blocked_if_unavailable",
        )


def test_competencies_no_parsed_paths_preserves_first_provider_error() -> None:
    paths = [
        SelfConsistencyPath(
            path_index=0,
            temperature=0.38,
            runtime_generation_status="BLOCKED",
            raw_output="",
            parsed=None,
            parse_error=(
                "External provider HTTP 400: "
                "`temperature` is deprecated for this model."
            ),
            provider_result=None,
        )
    ]

    with pytest.raises(PoolSelectorUnavailableError, match="temperature.*deprecated"):
        run_claude_bullet_pool_selection(
            section_id="competencies",
            slot_kind="competencies",
            paths=paths,
            targeting_context={
                "allowed_fact_ids": ["bul_001"],
                "allowed_skill_ids": [],
                "resume_support_blob_lower": "bul_001 alpha beta",
            },
            mode="blocked_if_unavailable",
        )


def test_generate_competencies_graph_pool_lane_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [_path_with_categories(i, n_categories=COMPETENCIES_FINAL_CATEGORY_COUNT) for i in range(4)]
    baseline_categories: list[dict[str, object]] = []
    for index, bundle_id in enumerate(_DISTINCT_GRAPH_BUNDLE_IDS):
        category = _cat(
            f"Governed baseline {index}",
            [f"governed supported capability {index}"],
            bundle_id=bundle_id,
        )
        category["candidate_origin"] = "governed_required_bundle_baseline"
        baseline_categories.append(category)
    selector_prompts: list[str] = []

    class _Judge:
        provider_key = "anthropic_claude"
        provider_name = "Anthropic Claude"
        model_name = pins.COMPETENCIES_SELECTOR_MODEL
        provider_status = "MODEL_BACKED_PASS"
        exact_provider_error = None
        pass_ = True
        rationale = "yaml_judge_models"

        def to_dict(self) -> dict[str, object]:
            return {
                "judge_id": "x1d_anthropic_claude_bullet_pool_selector",
                "provider_name": self.provider_name,
                "provider_key": self.provider_key,
                "provider_status": self.provider_status,
                "model_name": self.model_name,
                "provider_available": True,
                "provider_blocked": False,
                "exact_provider_error": self.exact_provider_error,
                "pass": True,
                "pass_": True,
                "rationale": self.rationale,
            }

    def _fake_paths(**kwargs: object) -> tuple[list[SelfConsistencyPath], ProviderResult]:
        path_count = int(kwargs.get("path_count") or len(paths))
        return paths[:path_count], ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="stub",
            raw_model_output="{}",
            provider_response={},
        )

    monkeypatch.setattr(
        "apps_rg.runtime.reasoning.bullet_lane_generation.run_provider_self_consistency_paths",
        _fake_paths,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")
    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector.bootstrap_apps_rg_env",
        lambda: None,
    )
    def _fake_selector(**kwargs: object) -> tuple[_Judge, dict[str, object]]:
        selector_prompts.append(str(kwargs.get("prompt") or ""))
        return (
            _Judge(),
            {
                "selections": [
                    {
                        "category_label": f"Category_0_{i}",
                        "path_index": 0,
                        "score": 0.9,
                        "passes": True,
                        "rationale": f"slot {i}",
                    }
                    for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)
                ],
                "pool_summary": {},
            },
        )

    monkeypatch.setattr(
        "apps_rg.runtime.judges.bullet_pool_claude_selector._call_anthropic_pool_selector",
        _fake_selector,
    )

    result, raw, parsed, err, meta = generate_bullet_lane_with_sc_and_claude(
        section_lane="competencies",
        slot_kind="competencies",
        provider_payload={"model": "stub", "messages": []},
        parse_model_json=lambda r: (json.loads(r) if r.strip().startswith("{") else None, ""),
        normalize_parsed=lambda p: p,
        targeting_context={
            "allowed_fact_ids": ["bul_001"],
            "resume_support_blob_lower": "",
            "governed_required_bundle_candidates": baseline_categories,
        },
        judge_mode="mocked",
    )
    assert err == ""
    assert is_competencies_pool_generation(meta)
    assert meta["initial_path_count"] == 4
    assert meta["max_path_count"] == competencies_max_sc_path_count()
    assert meta["adaptive_sc_enabled"] is True
    assert meta["stop_reason"] == "selection_gate_passed"
    assert meta["final_category_count"] == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert parsed is not None
    assert len(parsed.get("competencies") or []) == COMPETENCIES_FINAL_CATEGORY_COUNT
    assert result is not None
    assert selector_prompts
    assert "=== PATH 10000" in selector_prompts[0]
    assert "ccb_retrieval_context_engineering" in selector_prompts[0]


def test_generate_competencies_graph_pool_lane_forced_sc_ignores_disable_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[bool] = []

    def _fake_competencies_graph_pool_lane(**_: object) -> tuple[None, str, dict[str, object], str, dict[str, object]]:
        called.append(True)
        return (
            None,
            '{"competencies":[],"claim_ledger":[]}',
            {"competencies": [], "claim_ledger": []},
            "",
            {"generation_mode": "model_competencies_graph_pool_adaptive_6_8_regen"},
        )

    monkeypatch.setenv("APPS_RG_BULLET_SC_DISABLE", "1")
    monkeypatch.setattr(
        "apps_rg.runtime.reasoning.bullet_lane_generation._generate_competencies_graph_pool_lane",
        _fake_competencies_graph_pool_lane,
    )

    result, raw, parsed, err, meta = generate_bullet_lane_with_sc_and_claude(
        section_lane="competencies",
        slot_kind="competencies",
        provider_payload={"model": "stub", "messages": []},
        parse_model_json=lambda r: (json.loads(r) if r.strip().startswith("{") else None, ""),
        normalize_parsed=lambda p: p,
        targeting_context={"allowed_fact_ids": ["bul_001"], "resume_support_blob_lower": ""},
        judge_mode="mocked",
        use_sc_path=True,
    )

    assert called == [True]
    assert result is None
    assert raw == '{"competencies":[],"claim_ledger":[]}'
    assert parsed == {"competencies": [], "claim_ledger": []}
    assert err == ""
    assert meta["generation_mode"] == "model_competencies_graph_pool_adaptive_6_8_regen"


def test_competencies_pool_x1d_row_from_generation_meta(tmp_path) -> None:
    selections = [
        {"category_label": f"C{i}", "path_index": 0, "score": 0.88, "passes": True}
        for i in range(COMPETENCIES_FINAL_CATEGORY_COUNT)
    ]
    (tmp_path / "bullet_pool_selection.json").write_text(
        json.dumps({"selections": selections}),
        encoding="utf-8",
    )
    gen_meta = {
        "generation_mode": "model_competencies_graph_pool_adaptive_6_8_regen",
        "selection_gate": {"ok": True, "categories_in_merged": COMPETENCIES_FINAL_CATEGORY_COUNT},
        "selection_mode": "competencies_advisory_selector_adaptive_6_8_pass",
    }
    rows = competencies_pool_x1d_judge_rows(
        artifact_dir=tmp_path,
        section_id="competencies",
        gen_meta=gen_meta,
    )
    assert len(rows) == 1
    assert rows[0]["judge_id"] == "x1d_anthropic_claude_competencies_pool"
    assert rows[0]["provider_key"] == "anthropic_claude"
    assert rows[0]["provider_name"] == "Anthropic Claude"
    assert rows[0]["model_name"] == pins.COMPETENCIES_SELECTOR_MODEL
    assert rows[0]["selection_mode"] == (
        "competencies_advisory_selector_adaptive_6_8_pass"
    )
    assert rows[0]["judge_role"] == "competencies_graph_pool_selector"
    assert rows[0]["advisory_only"] is True
    assert rows[0]["proof_eligible_judge"] is False


def test_competencies_non_sc_path_is_removed() -> None:
    from apps_rg.runtime.reasoning.bullet_lane_generation import generate_bullet_lane_with_sc_and_claude

    with pytest.raises(ValueError, match="competencies lane requires self-consistency generation"):
        generate_bullet_lane_with_sc_and_claude(
            section_lane="competencies",
            slot_kind="competencies",
            provider_payload={"model": "stub", "messages": []},
            parse_model_json=lambda r: (json.loads(r) if r.strip().startswith("{") else None, ""),
            normalize_parsed=lambda p: p,
            targeting_context={"allowed_fact_ids": ["bul_001"], "resume_support_blob_lower": ""},
            judge_mode="mocked",
            use_sc_path=False,
        )


def test_apply_executive_capability_projection_preserves_adaptive_selection() -> None:
    from apps_rg.runtime.sections.competencies_capability_projection import (
        apply_executive_capability_projection,
    )
    from apps_rg.runtime.sections.competencies_rigor import MAX_CATEGORY_COUNT

    parsed = {
        "competencies": [
            _cat(
                "Technology Strategy & Innovation",
                ["Enterprise roadmap ownership", "Innovation portfolio governance"],
            ),
            _cat(
                "AI Platform Leadership",
                ["GraphRAG retrieval engineering", "Multi-agent orchestration"],
            ),
            _cat(
                "Data & Analytics Modernization",
                ["Lakehouse data modernization", "Enterprise data cataloging"],
            ),
            _cat(
                "Governance, Risk & Compliance",
                ["Policy-gated AI governance", "Audit traceability controls"],
            ),
            _cat(
                "Engineering & Delivery Leadership",
                ["Engineering organization scale-out", "Cross-functional delivery governance"],
            ),
            _cat(
                "Commercial & Operating Impact",
                ["IP-led commercialization strategy", "Enterprise platform adoption"],
            ),
        ],
        "change_log": [],
    }
    out = apply_executive_capability_projection(
        parsed,
        allowed_fact_ids={"bul_001"},
        allowed_skill_ids={"sk_graph_001"},
        skill_rows_by_id={
            "sk_graph_001": {"skill_id": "sk_graph_001", "canonical_name": "GraphRAG"}
        },
        resume_support_blob_lower="bul_001 graphrag orchestration",
    )
    comps = out.get("competencies") or []
    assert COMPETENCIES_MIN_CATEGORY_COUNT <= len(comps) <= MAX_CATEGORY_COUNT
    assert COMPETENCIES_MIN_CATEGORY_COUNT <= len(out.get("categories") or []) <= MAX_CATEGORY_COUNT


def test_canonical_competencies_cli_uses_required_openai_judge() -> None:
    from apps_rg.runtime.internal.generated_lane_rollup import canonical_lane_command

    cmd = canonical_lane_command("competencies")
    assert "--x1d-judges openai_chatgpt" in cmd
    assert "gemini_pro" not in cmd
    assert "anthropic_claude" not in cmd


def test_competencies_standalone_parser_defaults_to_claude_and_openai_judge() -> None:
    from apps_rg.runtime.sections.competencies_lane_runtime import build_parser

    args = build_parser().parse_args([])
    assert args.provider == "external_claude"
    assert args.x1d_judges == "openai_chatgpt"
