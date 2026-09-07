"""Contract tests for Gemini/OpenAI X1D packet and transport parity."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    from typing import Any, Callable

    class _MarkShim:
        @staticmethod
        def skipif(condition: bool, reason: str = "") -> Callable[[Any], Any]:
            def decorator(func: Any) -> Any:
                if condition:
                    return lambda *args, **kwargs: None
                return func
            return decorator

    class _PytestShim:
        mark = _MarkShim()

    pytest = _PytestShim()  # type: ignore[assignment]

from apps_rg.runtime.judges.executive_summary_judge_packet import (
    GRAPH_ONLY_GRADE_ONLY_RUBRIC,
    SRFS_GRADE_ONLY_RUBRIC,
    judge_contract_hash,
    reconcile_grade_only_judge_result,
)
from apps_rg.runtime.judges.executive_summary_x1d import _make_model_backed_output, build_x1d_judge_system_prompt
from apps_rg.runtime.sections.executive_summary_x1d_judge_contract import (
    audit_active_graph_rubric_x2_supremacy,
    audit_evidence_utilization_prompt_coherence,
    audit_executive_summary_x1d_judge_coherence,
    audit_identical_judge_json_same_pass_all_providers,
    audit_judge_packet_coherence,
    audit_provider_transport_parity,
    audit_rubric_soft_penalties_when_gates_pass,
    build_brown_brown_six_sentence_packet,
    load_frozen_post_x2_packet,
)

_REPO = Path(__file__).resolve().parents[3]


def _violation_codes(violations: list) -> list[str]:
    return [getattr(v, "code", getattr(v, "kind", "")) for v in violations]


# --- Would-have-caught: rubric / packet instruction conflict -----------------


def test_graph_rubric_includes_x2_supremacy_dim8_like_srfs() -> None:
    """SRFS has dim 8; active GRAPH rubric used on lane must match."""
    assert "penalize gates that show" in SRFS_GRADE_ONLY_RUBRIC.lower()
    violations = audit_active_graph_rubric_x2_supremacy()
    assert violations == [], _violation_codes(violations)


def test_graph_rubric_no_soft_penalty_on_passed_credential_gate() -> None:
    packet = build_brown_brown_six_sentence_packet()
    gates = packet["deterministic_gate_summary"]
    assert gates["x2_exec_summary_no_credential_dump"]["pass"] is True
    violations = audit_rubric_soft_penalties_when_gates_pass(packet)
    assert violations == [], _violation_codes(violations)


def test_graph_rubric_no_penalize_unused_when_util_gate_passed() -> None:
    packet = build_brown_brown_six_sentence_packet()
    gates = packet["deterministic_gate_summary"]
    assert gates["x2_exec_summary_evidence_utilization"]["pass"] is True
    eu = packet["evidence_utilization"]
    assert eu.get("unused_fact_count", 0) >= 1
    violations = audit_evidence_utilization_prompt_coherence(packet)
    assert violations == [], _violation_codes(violations)


def test_graph_and_srfs_rubrics_include_adversarial_review_lens() -> None:
    srf = SRFS_GRADE_ONLY_RUBRIC.lower()
    graph = GRAPH_ONLY_GRADE_ONLY_RUBRIC.lower()
    for blob in (srf, graph):
        assert "head of talent acquisition" in blob
        assert "ai-authenticity" in blob
        assert "buzzword soup" in blob


def test_brown_synthetic_packet_full_coherence_audit() -> None:
    packet = build_brown_brown_six_sentence_packet()
    violations = audit_judge_packet_coherence(packet)
    assert violations == [], _violation_codes(violations)


@pytest.mark.skipif(
    not (
        _REPO
        / "artifacts/apps_rg/runtime_proofs/executive_summary/real/exec_summary_20260524_001344/executive_summary_judge_packet_post_x2.json"
    ).is_file(),
    reason="frozen 001344 post-X2 packet not on disk",
)
def test_frozen_001344_post_x2_packet_coherence() -> None:
    packet = load_frozen_post_x2_packet(_REPO)
    assert packet is not None
    packet = dict(packet)
    packet["rubric"] = GRAPH_ONLY_GRADE_ONLY_RUBRIC
    summary = packet.get("deterministic_gate_summary") or {}
    failed = [k for k, v in summary.items() if isinstance(v, dict) and v.get("pass") is False]
    assert failed == [], f"fixture assumption broken: X2 fails {failed}"
    violations = audit_judge_packet_coherence(packet)
    assert violations == [], _violation_codes(violations)


# --- Would-have-caught: provider transport asymmetry -------------------------


def test_provider_transport_parity_zero_violations() -> None:
    violations = audit_provider_transport_parity()
    assert violations == [], _violation_codes(violations)


def test_canonical_contract_hash_stable_for_same_packet() -> None:
    packet_a = build_brown_brown_six_sentence_packet()
    packet_b = build_brown_brown_six_sentence_packet()
    assert judge_contract_hash(packet_a) == judge_contract_hash(packet_b)


def test_write_judge_packet_emits_canonical_contract_artifact(tmp_path: Path) -> None:
    from apps_rg.runtime.judges.executive_summary_judge_packet import (
        write_executive_summary_judge_packet,
    )

    packet = build_brown_brown_six_sentence_packet()
    pkt_path = tmp_path / "executive_summary_judge_packet.json"
    write_executive_summary_judge_packet(pkt_path, packet)
    canon_path = tmp_path / "canonical_judge_contract.json"
    assert canon_path.is_file()
    body = json.loads(canon_path.read_text(encoding="utf-8"))
    assert body["judge_contract_hash"] == judge_contract_hash(packet)
    assert body["canonical_judge_contract"]["judge_task"] == "GRADE_ONLY"


def test_build_x1d_judge_system_prompt_includes_score_schema() -> None:
    system = build_x1d_judge_system_prompt()
    assert "JUDGE_SCORE_SCHEMA" in system or "score_scale" in system
    assert "0_to_5" in system


# --- Sanity: pass math is provider-neutral for identical JSON ----------------


def test_identical_judge_json_same_pass_all_providers() -> None:
    violations = audit_identical_judge_json_same_pass_all_providers()
    assert violations == []


def test_make_model_backed_output_parity_explicit() -> None:
    body = {
        "score_scale": "0_to_5",
        "score": 3.5,
        "threshold": 4.0,
        "pass": False,
        "decisive_failure": False,
        "findings": ["metric stack"],
        "cited_sentence_indexes": [2],
        "remediation_suggestions": [],
    }
    gate_summary = {"x2_exec_summary_no_credential_dump": {"pass": True, "detail": "ok"}}
    statuses = {}
    for key in ("gemini_pro", "openai_chatgpt"):
        out = _make_model_backed_output(
            key, "h", "m", dict(body), deterministic_gate_summary=gate_summary
        )
        statuses[key] = (out.provider_status, out.normalized_score, out.pass_)
    assert statuses["gemini_pro"] == statuses["openai_chatgpt"]


def test_reconcile_strips_retired_criteria_findings_gemini_openai_class() -> None:
    """Retired five-part/S1-S5 findings must not survive reconcile (all providers)."""
    gate_summary = {
        "x2_exec_summary_sentence_count_6": {"pass": True, "detail": "ok"},
        "x2_exec_summary_evidence_utilization": {"pass": True, "detail": "ok"},
    }
    body = {
        "score_scale": "0_to_5",
        "score": 3.2,
        "threshold": 4.0,
        "pass": False,
        "decisive_failure": True,
        "findings": [
            "Missing mandatory S5 credibility sentence despite passing the deterministic gate.",
            "Weak synthesis on executive_signal.",
        ],
        "cited_sentence_indexes": [1],
        "remediation_suggestions": [],
    }
    reconciled = reconcile_grade_only_judge_result(body, gate_summary)

    findings_blob = " ".join(reconciled.get("findings") or []).lower()
    assert "mandatory s5" not in findings_blob
    assert "weak synthesis" in findings_blob


def test_build_x1d_judge_system_prompt_shared_by_gemini_openai_path() -> None:
    system = build_x1d_judge_system_prompt(compact=True)
    assert "GRADE_ONLY authority" in system
    assert "deterministic_gate_summary" in system
    assert "retired" in system.lower()


# --- CI-shaped aggregate (feeds drift gate when wired) -----------------------


def test_executive_summary_x1d_judge_coherence_aggregate() -> None:
    violations = audit_executive_summary_x1d_judge_coherence()
    assert violations == [], "\n".join(f"[{v.kind}] {v.detail}" for v in violations)


def test_active_rubric_is_graph_only() -> None:
    packet = build_brown_brown_six_sentence_packet()
    assert packet["rubric"] == GRAPH_ONLY_GRADE_ONLY_RUBRIC


def test_display_override_parity_synthesis() -> None:
    from apps_rg.runtime.judges.executive_summary_judge_packet import (
        build_executive_summary_judge_packet,
    )
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
    )

    override_fid = "fact_engineering_platform_002"
    expected_override = FACT_C0_DISPLAY_OVERRIDES[override_fid]

    # Model cited the fact, but allowed_fact_packet did not include the override row
    claim_ledger = [
        {
            "sentence_index": 1,
            "claim_text": "Built enterprise platform.",
            "source_fact_ids": [override_fid],
        }
    ]
    packet = build_executive_summary_judge_packet(
        resume_display_text="Sentence one. Sentence two. Sentence three. Sentence four. Sentence five. Sentence six.",
        claim_ledger=claim_ledger,
        allowed_fact_packet=[],
        allowed_fact_ids={"fact_other_001"},
        target_title="VP of Engineering",
        target_company="Acme Corp",
        jd_text="Job description",
        briefing_text="Briefing",
        parsed_output={"executive_summary": "six sentences"},
    )
    assert override_fid in packet["allowed_fact_ids"]
    gate_parity = packet["deterministic_gate_summary"].get(
        "x2_executive_summary_judge_packet_display_override_parity"
    )
    assert gate_parity is not None
    assert gate_parity["pass"] is True, f"Parity failed: {gate_parity}"
    matching_rows = [r for r in packet["allowed_fact_packet"] if r.get("fact_id") == override_fid]
    assert len(matching_rows) == 1
    assert matching_rows[0]["display_override_text"] == expected_override
