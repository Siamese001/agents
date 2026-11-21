"""Executive-summary v2 extensions for X2/X1D contract (zero post-LLM prose mutation, judge rubrics, parity)."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.judges import executive_summary_judge_packet as judge_packet_mod
from apps_rg.runtime.sections.executive_summary_v2 import (
    blind_judge_and_loop as v2_loop_mod,
    prompt_and_generate as v2_gen_mod,
    x2_invariants as v2_x2_mod,
)
from apps_rg.runtime.sections.executive_summary_x1d_judge_contract import (
    audit_executive_summary_x1d_judge_coherence,
)
from apps_rg.runtime.sections.section_product_shape_parity import (
    audit_ssot_seam_parity,
    judge_rubric_shape_constraints,
)
from apps_rg.runtime.sections.section_product_shape_ssot import (
    RETIRED_EXEC_SUMMARY_X2_GATE_IDS,
    section_product_shape,
)
from apps_rg.runtime.sections.section_x2_x1d_contract import (
    X2X1dDriftViolation,
    assert_all_generated_lanes_x2_x1d_contract,
    audit_all_generated_lanes_x2_x1d_drift,
    audit_lane_x2_x1d_drift,
    extract_runtime_x2_gate_ids,
)

JUDGE_PACKET_REQUIRED_GATE_KEYS: frozenset[str] = frozenset(v2_x2_mod.EXEC_SUMMARY_V2_CORE_GATE_IDS)
REPAIR_LOOP_PHASE_MARKERS: tuple[tuple[str, str], ...] = (
    ("generate_v2_turn", "generate_v2_turn("),
    ("evaluate_executive_summary_v2_x2", "evaluate_executive_summary_v2_x2("),
    ("evaluate_blind_human_judges", "evaluate_blind_human_judges("),
)
SYNTHESIS_CHECK_TO_X2_GATE: dict[str, str] = {gid: gid for gid in v2_x2_mod.EXEC_SUMMARY_V2_CORE_GATE_IDS}


def judge_packet_pre_x2_gate_keys() -> frozenset[str]:
    return JUDGE_PACKET_REQUIRED_GATE_KEYS


def _audit_v2_zero_prose_mutation_and_loop() -> list[X2X1dDriftViolation]:
    out: list[X2X1dDriftViolation] = []
    gen_src = Path(v2_gen_mod.__file__).read_text(encoding="utf-8")
    if "re.sub(" in gen_src and "resume_display_text" in gen_src.split("def parse_strict_json_without_mutation", 1)[-1]:
        # Only JSON code-fence stripping on raw_output is permitted before json.loads; display_text is never regex-mutated.
        body = gen_src.split("def parse_strict_json_without_mutation", 1)[-1]
        if "re.sub(" in body.split("json.loads", 1)[-1]:
            out.append(
                X2X1dDriftViolation(
                    "executive_summary",
                    "post_llm_prose_mutator_detected",
                    "parse_strict_json_without_mutation must never regex-mutate parsed resume_display_text",
                    v2_gen_mod.__file__ or "",
                )
            )
    loop_src = Path(v2_loop_mod.__file__).read_text(encoding="utf-8")
    positions: list[tuple[str, int]] = []
    for phase, marker in REPAIR_LOOP_PHASE_MARKERS:
        idx = loop_src.find(marker)
        if idx < 0:
            out.append(
                X2X1dDriftViolation(
                    "executive_summary",
                    "repair_loop_marker_missing",
                    f"blind_judge_and_loop missing phase {phase}: {marker!r}",
                    v2_loop_mod.__file__ or "",
                )
            )
        else:
            positions.append((phase, idx))
    for (p0, i0), (p1, i1) in zip(positions, positions[1:]):
        if i1 < i0:
            out.append(
                X2X1dDriftViolation(
                    "executive_summary",
                    "repair_loop_order_inverted",
                    f"{p1} appears before {p0}",
                    v2_loop_mod.__file__ or "",
                )
            )
    return out


def _audit_exec_judge_packet_rubrics() -> list[X2X1dDriftViolation]:
    out: list[X2X1dDriftViolation] = []
    shape = section_product_shape("executive_summary")
    for rubric_name, rubric in (
        ("SRFS_GRADE_ONLY_RUBRIC", judge_packet_mod.SRFS_GRADE_ONLY_RUBRIC),
        ("GRAPH_ONLY_GRADE_ONLY_RUBRIC", judge_packet_mod.GRAPH_ONLY_GRADE_ONLY_RUBRIC),
    ):
        issues = judge_rubric_shape_constraints(shape, rubric)
        if issues:
            out.append(
                X2X1dDriftViolation(
                    "executive_summary",
                    "judge_rubric_looser_than_ssot",
                    f"{rubric_name}: {issues}",
                    judge_packet_mod.__file__ or "",
                )
            )
        retired_hits = sorted(g for g in RETIRED_EXEC_SUMMARY_X2_GATE_IDS if g in rubric)
        if retired_hits:
            out.append(
                X2X1dDriftViolation(
                    "executive_summary",
                    "judge_rubric_retired_gate_id",
                    f"{rubric_name} mentions retired gates: {retired_hits}",
                    judge_packet_mod.__file__ or "",
                )
            )
    if "INANIMATE_SUBJECT_DATASHEET_BAN" not in judge_packet_mod.GRAPH_ONLY_GRADE_ONLY_RUBRIC:
        out.append(
            X2X1dDriftViolation(
                "executive_summary",
                "judge_rubric_missing_inanimate_subject_ban",
                "GRAPH_ONLY_GRADE_ONLY_RUBRIC must enforce INANIMATE_SUBJECT_DATASHEET_BAN",
                judge_packet_mod.__file__ or "",
            )
        )
    return out


def audit_executive_summary_extended_drift(
    runtime_gates: frozenset[str] | None = None,
) -> list[X2X1dDriftViolation]:
    """Executive-summary v2 checks (zero prose mutators, loop order, judge rubrics, parity)."""
    _ = runtime_gates or extract_runtime_x2_gate_ids(
        x2_module_ref="apps_rg/runtime/sections/executive_summary_v2/x2_invariants.py",
        x2_run_function="run_executive_summary_v2_x2_gates",
    )
    violations: list[X2X1dDriftViolation] = []
    violations.extend(_audit_v2_zero_prose_mutation_and_loop())
    violations.extend(_audit_exec_judge_packet_rubrics())
    violations.extend(
        X2X1dDriftViolation("executive_summary", "ssot_seam_parity", m.detail, m.seam)
        for m in audit_ssot_seam_parity()
    )
    violations.extend(audit_executive_summary_x1d_judge_coherence())
    return violations


def audit_executive_summary_x2_x1d_drift() -> list[X2X1dDriftViolation]:
    return audit_lane_x2_x1d_drift("executive_summary")


def assert_executive_summary_x2_x1d_contract() -> None:
    violations = audit_executive_summary_x2_x1d_drift()
    if violations:
        lines = "\n".join(f"  [{v.kind}] {v.detail} ({v.path})" for v in violations)
        raise AssertionError(f"executive_summary X2/X1D contract drift:\n{lines}")


__all__ = [
    "JUDGE_PACKET_REQUIRED_GATE_KEYS",
    "REPAIR_LOOP_PHASE_MARKERS",
    "SYNTHESIS_CHECK_TO_X2_GATE",
    "X2X1dDriftViolation",
    "assert_all_generated_lanes_x2_x1d_contract",
    "assert_executive_summary_x2_x1d_contract",
    "audit_all_generated_lanes_x2_x1d_drift",
    "audit_executive_summary_extended_drift",
    "audit_executive_summary_x2_x1d_drift",
    "audit_lane_x2_x1d_drift",
    "extract_runtime_x2_gate_ids",
    "judge_packet_pre_x2_gate_keys",
]
