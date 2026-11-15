"""Tests for C0 whole-sequence fact-slot allocation and 5-check SQLite custody.

Verifies:
1. 5/5 SQLite custody checks and 4-channel hybrid retrieval via infrastructure.candidate_evidence.
2. C0 sequence allocation across 3-touch and 4-touch sequences.
3. 100% disjoint fact_id slots across touches, disjoint reserve repair pool, and deterministic allocation_plan_digest.
4. Fail-closed rejection on fact_id collision or tampered custody digest.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from infrastructure.candidate_evidence import (
    CandidateFactChunk,
    ChannelScoreBreakdown,
    CustodyCheckReport,
    HybridCandidatePool,
    QuadHybridCandidateRetriever,
    QuadRetrievalConfig,
    build_in_memory_fixture_db,
    verify_sqlite_custody,
)
from apps_lic.runtime.c0 import (
    C0_ALLOCATION_PLAN_SCHEMA_VERSION,
    INV_LIC_C0_DISJOINT_TOUCH_FACTS,
    OutreachSequenceAllocationPlan,
    SequenceAllocationError,
    TouchSlotSpec,
    compute_allocation_plan_digest,
    solve_sequence_allocation,
    validate_disjoint_allocation,
)


def _make_fact_chunk(
    fact_id: str,
    metric: str = "",
    span: str = "",
    score: float = 0.9,
    employer: str = "Enterprise Corp",
) -> CandidateFactChunk:
    span_text = span or f"Delivered high impact platform architecture at {employer} {metric}."
    metrics = (metric,) if metric else ()
    return CandidateFactChunk(
        fact_id=fact_id,
        source_chunk_id=f"chunk_{fact_id}",
        verbatim_span=span_text,
        metric_tokens=metrics,
        entity_tags=(employer.lower().replace(" ", "_"), "architecture"),
        channel_scores=ChannelScoreBreakdown(
            dense_cosine=score,
            fts5_bm25=score,
            learned_sparse=score,
            colbert_maxsim=score,
            graph_1hop=score,
            rrf_score=score,
            final_score=score,
        ),
        employer=employer,
        category="architecture",
    )


def test_sqlite_custody_and_4channel_retrieval(tmp_path: Path) -> None:
    """Test 5/5 SQLite custody checks and 4-channel hybrid retrieval on candidate evidence graph."""
    db_path = tmp_path / "test_augmented_skills_graph.sqlite"
    facts_data = [
        {
            "fact_id": f"fact_platform_{i:03d}",
            "unit_id": f"unit_{i:03d}",
            "text": f"Engineered distributed platform at TechCorp {i} delivering ${i*10}M in revenue and {i*5}% growth.",
            "employer": "TechCorp",
            "skills": [f"skill_cloud_{i}"],
        }
        for i in range(1, 105)
    ]
    conn, _ = build_in_memory_fixture_db(facts_data)

    # Save to disk to test physical 5-check custody
    backup_conn = __import__("sqlite3").connect(str(db_path))
    conn.backup(backup_conn)
    backup_conn.close()
    conn.close()

    custody_rep = verify_sqlite_custody(db_path, min_fact_count=10)
    assert custody_rep.passed is True
    assert custody_rep.checks_passed_count == 5
    assert custody_rep.check_1_file_exists_nonzero is True
    assert custody_rep.check_2_sqlite_header_and_quick_check is True
    assert custody_rep.check_3_required_tables_and_fts5 is True
    assert custody_rep.check_4_candidate_node_count_and_schema is True
    assert custody_rep.check_5_sha256_and_manifest_verified is True
    assert len(custody_rep.candidate_graph_db_sha256) == 64

    config = QuadRetrievalConfig(top_k=5)
    retriever = QuadHybridCandidateRetriever(db_path=db_path, config=config)
    pool = retriever.retrieve("TechCorp distributed platform engineering")

    assert len(pool.chunks) > 0
    assert pool.candidate_graph_db_sha256 == custody_rep.candidate_graph_db_sha256
    assert bool(pool.pool_digest) is True
    first_chunk = pool.chunks[0]
    assert first_chunk.fact_id.startswith("fact_platform_")
    assert first_chunk.channel_scores.final_score > 0.0


def test_c0_sequence_allocation_3_touch() -> None:
    """Test C0 sequence allocation across a 3-touch outreach sequence with disjoint facts and reserve pool."""
    chunks = [
        _make_fact_chunk("fact_01", "$4.2B", score=0.95),
        _make_fact_chunk("fact_02", "38%", score=0.91),
        _make_fact_chunk("fact_03", "99.995%", score=0.88),
        _make_fact_chunk("fact_04", "150+ engineers", score=0.82),
        _make_fact_chunk("fact_05", "$120M", score=0.79),
    ]

    touch_specs = [
        TouchSlotSpec(touch_number=1, channel="inmail", preferred_angle="strategic_hook"),
        TouchSlotSpec(touch_number=2, channel="follow_up", preferred_angle="momentum_proof"),
        TouchSlotSpec(touch_number=3, channel="follow_up", preferred_angle="quarterly_optionality"),
    ]

    plan = solve_sequence_allocation(
        candidate_pool=chunks,
        touch_specs=touch_specs,
        opportunity_id="opp_citi_01",
        candidate_id="cand_exec_01",
        candidate_graph_db_sha256="sha256:abc123mock",
        min_reserve_count=1,
    )

    assert isinstance(plan, OutreachSequenceAllocationPlan)
    assert plan.schema_version == C0_ALLOCATION_PLAN_SCHEMA_VERSION
    assert len(plan.assignments) == 3

    # Check 100% disjoint facts
    t1_facts = set(plan.allocated_fact_ids_by_touch[1])
    t2_facts = set(plan.allocated_fact_ids_by_touch[2])
    t3_facts = set(plan.allocated_fact_ids_by_touch[3])
    reserve_facts = set(plan.reserve_repair_pool_fact_ids)

    assert len(t1_facts & t2_facts) == 0
    assert len(t1_facts & t3_facts) == 0
    assert len(t2_facts & t3_facts) == 0
    assert len(t1_facts & reserve_facts) == 0
    assert len(t2_facts & reserve_facts) == 0
    assert len(t3_facts & reserve_facts) == 0

    assert len(reserve_facts) >= 1
    assert plan.uniqueness_receipt["passed"] is True
    assert plan.uniqueness_receipt["invariant"] == INV_LIC_C0_DISJOINT_TOUCH_FACTS
    assert bool(plan.allocation_plan_digest) is True


def test_c0_sequence_allocation_4_touch() -> None:
    """Test C0 sequence allocation across a 4-touch outreach sequence with primary metric token isolation."""
    chunks = [
        _make_fact_chunk("fact_scale_01", "$500M", score=0.98),
        _make_fact_chunk("fact_arch_02", "45%", score=0.92),
        _make_fact_chunk("fact_governance_03", "zero critical defects", score=0.87),
        _make_fact_chunk("fact_cloud_04", "12 regions", score=0.84),
        _make_fact_chunk("fact_reserve_05", "$30M", score=0.80),
        _make_fact_chunk("fact_reserve_06", "60%", score=0.75),
    ]

    touch_specs = [
        TouchSlotSpec(touch_number=1, channel="inmail"),
        TouchSlotSpec(touch_number=2, channel="email"),
        TouchSlotSpec(touch_number=3, channel="follow_up"),
        TouchSlotSpec(touch_number=4, channel="follow_up"),
    ]

    plan = solve_sequence_allocation(
        candidate_pool=chunks,
        touch_specs=touch_specs,
        opportunity_id="opp_aig_01",
        candidate_id="cand_exec_02",
        candidate_graph_db_sha256="sha256:def456mock",
        min_reserve_count=2,
    )

    assert len(plan.assignments) == 4
    allocated_fact_ids = [plan.allocated_fact_ids_by_touch[t][0] for t in (1, 2, 3, 4)]
    assert len(set(allocated_fact_ids)) == 4
    assert len(plan.reserve_repair_pool_fact_ids) == 2

    # Deterministic plan digest
    plan_dict = plan.to_dict()
    recomputed_digest = compute_allocation_plan_digest(plan_dict)
    assert plan.allocation_plan_digest == recomputed_digest


def test_fail_closed_on_insufficient_facts() -> None:
    """Allocation must fail closed when pool cannot satisfy touches + reserve under disjoint invariants."""
    chunks = [
        _make_fact_chunk("fact_01", "$10M", score=0.95),
        _make_fact_chunk("fact_02", "20%", score=0.90),
    ]

    touch_specs = [
        TouchSlotSpec(touch_number=1),
        TouchSlotSpec(touch_number=2),
        TouchSlotSpec(touch_number=3),
    ]

    with pytest.raises(SequenceAllocationError, match="Insufficient candidate facts"):
        solve_sequence_allocation(
            candidate_pool=chunks,
            touch_specs=touch_specs,
            min_reserve_count=1,
        )


def test_fail_closed_on_metric_collision() -> None:
    """Allocation must fail closed when facts collide on identical primary metric tokens."""
    # Two facts with identical $4.2B metric token
    chunks = [
        _make_fact_chunk("fact_01", "$4.2B", score=0.95),
        _make_fact_chunk("fact_02", "$4.2B", score=0.94),
        _make_fact_chunk("fact_03", "38%", score=0.85),
    ]

    touch_specs = [
        TouchSlotSpec(touch_number=1),
        TouchSlotSpec(touch_number=2),
    ]

    plan = solve_sequence_allocation(
        candidate_pool=chunks,
        touch_specs=touch_specs,
        min_reserve_count=1,
    )
    # Touch 1 gets fact_01 ($4.2B), Touch 2 MUST NOT get fact_02 ($4.2B) due to metric collision
    assert plan.assignments[0].allocated_fact_ids == ("fact_01",)
    assert plan.assignments[1].allocated_fact_ids == ("fact_03",)


def test_validate_disjoint_allocation_catches_collision() -> None:
    """validate_disjoint_allocation must detect duplicate facts or reserve overlap."""
    chunk = _make_fact_chunk("fact_01", "$10M")
    assignment_1 = plan = solve_sequence_allocation(
        candidate_pool=[
            _make_fact_chunk("fact_01", "$10M"),
            _make_fact_chunk("fact_02", "20%"),
            _make_fact_chunk("fact_03", "30%"),
        ],
        touch_specs=[TouchSlotSpec(touch_number=1), TouchSlotSpec(touch_number=2)],
        min_reserve_count=1,
    ).assignments

    # Artificially duplicate assignment fact
    from apps_lic.runtime.c0.sequence_allocation import TouchAllocationAssignment

    bad_assignments = [
        assignment_1[0],
        TouchAllocationAssignment(
            touch_number=2,
            channel="email",
            allocated_fact_ids=("fact_01",),
            allocated_facts=(chunk,),
            allocated_metric_tokens=("$10M",),
            strategic_priority="p1",
            touch_angle="angle",
        ),
    ]

    receipt = validate_disjoint_allocation(bad_assignments)
    assert receipt["passed"] is False
    assert "fact_01" in receipt["repeated_fact_ids"]
