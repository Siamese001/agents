"""Whole-run Exit aggregation for apps_rg section-dispatch runtime proof.

Computes one canonical product X3 disposition from lane rollups, assembly
gates, C0/FEC grounding signals, and X1D policy. Per-lane X3 codes are preserved as evidence
in ``aggregated_from_lane_x3``; they are not overwritten.

This module is apps_rg-local and does not import apps_rg.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.failure_evidence import atomic_write_json
from apps_rg.runtime.internal.generated_lane_contract import GENERATED_LANES
from apps_rg.runtime.authority_reconciliation import (
    LANE_X3_MIRROR_ARTIFACT,
    derive_final_assembly_authority,
    derive_lane_authority,
    resolve_lane_artifact_root,
)

X3D_ALLOW_FINISH = "X3D_ALLOW_FINISH"
X3B_ESCALATE_HITL = "X3B_ESCALATE_HITL"
X3A_DENY_REROUTE = "X3A_DENY_REROUTE"
X3E_SAFE_ABSTAIN = "X3E_SAFE_ABSTAIN"

RC_JUDGE_PROVIDER_UNAVAILABLE = "JUDGE_PROVIDER_UNAVAILABLE"
RC_JUDGE_QUORUM_NOT_SATISFIED = "JUDGE_QUORUM_NOT_SATISFIED"
RC_JUDGE_EXECUTION_PROVIDER_MISMATCH = "JUDGE_EXECUTION_PROVIDER_MISMATCH"
RC_JUDGE_MODEL_BACKED_QUALITY_FAIL = "JUDGE_MODEL_BACKED_QUALITY_FAIL"
RC_JUDGE_UNKNOWN_RESULT = "JUDGE_UNKNOWN_RESULT"
RC_JUDGE_SCHEMA_OR_PARSER_BLOCK = "JUDGE_SCHEMA_OR_PARSER_BLOCK"
RC_X1D_POLICY_MALFORMED = "X1D_POLICY_MALFORMED"
RC_LANE_X3_MIXED = "LANE_X3_MIXED"
RC_LANE_X3_NON_ALLOW = "LANE_X3_NON_ALLOW"
RC_FINAL_RESUME_X2_FAIL = "FINAL_RESUME_X2_FAIL"
RC_C0_SUPPORT_WEAK = "C0_SUPPORT_WEAK"
RC_PRODUCT_R4_BYPASS_PRELOADED_CONTEXT = "PRODUCT_R4_BYPASS_PRELOADED_CONTEXT"
RC_X1D_AGGREGATE_REVIEW = "X1D_AGGREGATE_REVIEW"

WHOLE_RUN_EXIT_ARTIFACT = "apps_rg_whole_run_exit_review_packet.json"
WHOLE_RUN_EXIT_SCHEMA = "apps_rg.whole_run_exit_review_packet.v1"
_FINAL_ASSEMBLY = Path("modular_r4") / "final_resume_assembly"
_LOCKED_SECTION_IDS = frozenset({"early_career", "education", "certifications"})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return (
        f"sha256:{hashlib.sha256(_canonical_json(value).encode('utf-8')).hexdigest()}"
    )


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _read_json_object(
    path: Path,
    errors: list[str],
    *,
    source_ref: str,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"UNREADABLE_JSON:{source_ref}:{type(exc).__name__}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON_NOT_OBJECT:{source_ref}")
        return {}
    return value


def _source_binding(root: Path, path: Path) -> dict[str, Any]:
    target = path.resolve()
    try:
        ref = target.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"whole-run Exit source escapes artifact_dir: {path}") from exc
    present = target.is_file()
    return {
        "artifact_ref": ref,
        "present": present,
        "sha256": _sha256_file(target) if present else "",
        "byte_length": target.stat().st_size if present else 0,
    }


def _gate_all_pass(payload: Mapping[str, Any]) -> bool:
    gates = payload.get("gates")
    return bool(
        payload.get("all_pass") is True
        and not list(payload.get("failed_gate_ids") or ())
        and isinstance(gates, list)
        and gates
        and all(isinstance(row, Mapping) and row.get("pass") is True for row in gates)
    )


def _failed_gate_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def build_whole_run_exit_signals(
    artifact_dir: Path,
) -> tuple[dict[str, Any], tuple[Path, ...], tuple[str, ...]]:
    """Derive product Exit inputs from persisted apps_rg artifacts only.

    The pinned core wrapper remains runtime-transport evidence.  It cannot
    decide the product disposition for the multi-lane apps_rg workload that it
    invokes as one L2 action.
    """

    root = Path(artifact_dir).resolve()
    errors: list[str] = []
    sources: list[Path] = []

    def load(relative: str | Path) -> dict[str, Any]:
        source_ref = Path(relative).as_posix()
        path = root / relative
        sources.append(path)
        return _read_json_object(path, errors, source_ref=source_ref)

    final_output = load("FINAL_RESUME_OUTPUT.json")
    section_status = load("full_run_section_status.json")
    final_resume = load(_FINAL_ASSEMBLY / "final_resume.json")
    final_x2 = load(_FINAL_ASSEMBLY / "final_resume_x2_gate_outputs.json")
    x1d = load(_FINAL_ASSEMBLY / "x1d_full_resume_judge_outputs.json")

    status_rows_raw = section_status.get("lanes")
    status_rows = status_rows_raw if isinstance(status_rows_raw, list) else []
    by_lane: dict[str, Mapping[str, Any]] = {}
    duplicate_lanes: set[str] = set()
    for row in status_rows:
        if not isinstance(row, Mapping):
            continue
        lane = str(row.get("lane") or "").strip()
        if not lane or lane == "final_resume_aggregation":
            continue
        if lane in by_lane:
            duplicate_lanes.add(lane)
        by_lane[lane] = row
    expected = set(GENERATED_LANES)
    exact_lane_coverage = set(by_lane) == expected and not duplicate_lanes

    lane_rows: list[dict[str, Any]] = []
    c0_evidence_count = 0
    c0_all_pass = exact_lane_coverage
    pa_consumed_c0 = exact_lane_coverage
    pa_evidence_data_only = exact_lane_coverage
    pa_schema_bound = exact_lane_coverage
    direct_l4_write_bypass = False
    mock_provider_pass = False
    judge_execution_incomplete_lanes: list[str] = []
    final_materialized_acceptance_failed_lanes: list[str] = []
    authoritative_lane_contract_failed_lanes: list[str] = []
    l2_handoff_failed_lanes: list[str] = []
    l2_spine_failed_lanes: list[str] = []
    core_x3_non_authorizing_lanes: list[str] = []
    mirror_authority_violation_lanes: list[str] = []
    lane_authority_rows: list[dict[str, Any]] = []
    cross_app_leakage = False

    for lane in GENERATED_LANES:
        status = by_lane.get(lane, {})
        failed_ids = _failed_gate_ids(status.get("x2_failed_gate_ids"))
        if status.get("runtime_generation_status") != "REAL_LLM":
            mock_provider_pass = True
        judges = status.get("judges")
        if status.get("x2_pass") == "PASS":
            if not isinstance(judges, list) or not judges:
                judge_execution_incomplete_lanes.append(lane)
            elif any(
                not isinstance(judge, Mapping)
                or str(judge.get("provider_status") or "")
                not in {"MODEL_BACKED_PASS", "MODEL_BACKED_FAIL"}
                for judge in judges
            ):
                judge_execution_incomplete_lanes.append(lane)

        lane_root = resolve_lane_artifact_root(root, lane)
        lane_authority = derive_lane_authority(root, lane)
        lane_authority_rows.append(lane_authority)
        required_artifacts = lane_authority.get("required_artifacts")
        required_artifacts = (
            required_artifacts if isinstance(required_artifacts, list) else []
        )
        for name in required_artifacts:
            sources.append(lane_root / name)
        lane_checks = lane_authority.get("checks")
        lane_checks = lane_checks if isinstance(lane_checks, Mapping) else {}
        if lane_authority.get("authorized") is not True:
            authoritative_lane_contract_failed_lanes.append(lane)
        if (
            lane_checks.get("l2_handoff_status_pass") is not True
            or lane_checks.get("l2_handoff_checks_all_pass") is not True
        ):
            l2_handoff_failed_lanes.append(lane)
        if lane_checks.get("l2_spine_status_pass") is not True:
            l2_spine_failed_lanes.append(lane)
        if lane_checks.get("lane_x3_exact_authorizing_code") is not True:
            core_x3_non_authorizing_lanes.append(lane)
        if (
            lane_checks.get("lane_mirror_declared_nonauthoritative") is not True
            or lane_checks.get("lane_mirror_points_to_core_receipt") is not True
            or lane_checks.get("lane_exit_mirror_declared_nonauthoritative") is not True
        ):
            mirror_authority_violation_lanes.append(lane)
        lane_rows.append(
            {
                "lane": lane,
                "x3_code": str(lane_authority.get("authoritative_x3_code") or ""),
                "mirror_x3_code": str(lane_authority.get("mirror_x3_code") or ""),
                "authoritative_contract_status": str(
                    lane_authority.get("status") or ""
                ),
                "x2_failed": 0
                if status.get("x2_pass") == "PASS"
                else max(1, len(failed_ids)),
                "x2_failed_gate_ids": failed_ids,
                "runtime_generation_status": str(
                    status.get("runtime_generation_status") or ""
                ),
                "product_quality_status": str(
                    status.get("product_quality_status") or ""
                ),
            }
        )
        c0_metrics = load(lane_root.relative_to(root) / "c0_metrics.json")
        compiled = load(lane_root.relative_to(root) / "compiled_prompt_artifact.json")
        fec_receipt = load(lane_root.relative_to(root) / "c0_fec_compose_receipt.json")
        lane_x2 = load(lane_root.relative_to(root) / "x2_gate_outputs.json")
        lane_x3 = load(lane_root.relative_to(root) / LANE_X3_MIRROR_ARTIFACT)

        counts = c0_metrics.get("evidence_counts")
        counts = counts if isinstance(counts, Mapping) else {}
        try:
            lane_evidence_count = int(counts.get("total") or 0)
        except (TypeError, ValueError):
            lane_evidence_count = 0
        c0_evidence_count += lane_evidence_count
        c0_all_pass = bool(
            c0_all_pass
            and c0_metrics.get("support_status") == "PASS"
            and c0_metrics.get("support_target_met") is True
            and lane_evidence_count > 0
            and fec_receipt.get("fec_bridge_status") == "PASS"
            and fec_receipt.get("precondition_status") == "PASS"
            and fec_receipt.get("support_status") == "PASS"
        )
        pa_consumed_c0 = bool(
            pa_consumed_c0
            and compiled.get("evidence_contract_consumed") is True
            and fec_receipt.get("pa_entry_allowed") is True
        )
        pa_evidence_data_only = bool(
            pa_evidence_data_only
            and compiled.get("raw_proof_pool_direct_to_pa") is False
            and fec_receipt.get("raw_proof_pool_direct_to_pa") is False
        )
        pa_schema_bound = bool(
            pa_schema_bound
            and compiled.get("section_id") == lane
            and bool(str(compiled.get("pa_prompt_hash") or ""))
            and bool(str(compiled.get("fec_bridge_ref") or ""))
            and bool(str(compiled.get("final_evidence_contract_ref") or ""))
            and bool(str(compiled.get("c0_fec_bridge_receipt_ref") or ""))
        )
        gates = lane_x2.get("gates")
        if isinstance(gates, list):
            for gate in gates:
                if not isinstance(gate, Mapping):
                    continue
                gate_id = str(gate.get("gate_id") or "").lower()
                if (
                    "target_company_as_experience_zero" in gate_id
                    or "cross_app_leakage" in gate_id
                ) and gate.get("pass") is not True:
                    cross_app_leakage = True
        if lane_x3.get("direct_l4_write_bypass") is True:
            direct_l4_write_bypass = True
        if lane_x3.get("final_materialized_acceptance_ok") is not True:
            final_materialized_acceptance_failed_lanes.append(lane)

    final_assembly_authority = derive_final_assembly_authority(root)
    final_assembly_receipt_path = root / _FINAL_ASSEMBLY / "final_resume_receipt.json"
    sources.append(final_assembly_receipt_path)
    final_sections = final_resume.get("sections")
    final_sections = final_sections if isinstance(final_sections, list) else []
    final_section_ids = {
        str(row.get("section_id") or "")
        for row in final_sections
        if isinstance(row, Mapping)
    }
    final_json_path = root / _FINAL_ASSEMBLY / "final_resume.json"
    final_resume_json_valid = bool(
        final_resume and isinstance(final_resume.get("sections"), list)
    )
    required_generated_sections_present = bool(
        exact_lane_coverage and expected.issubset(final_section_ids)
    )
    locked_sections_preserved = bool(
        _LOCKED_SECTION_IDS.issubset(final_section_ids)
        and isinstance(final_resume.get("locked_copy_invariants"), Mapping)
        and all(
            isinstance(gate, Mapping) and gate.get("pass") is True
            for gate in final_output.get("gates", [])
            if isinstance(gate, Mapping)
            and (
                "base_role_headers_preserved" in str(gate.get("gate_id") or "")
                or "education_copied_from_base" in str(gate.get("gate_id") or "")
                or "certifications_copied_from_base" in str(gate.get("gate_id") or "")
            )
        )
    )
    final_resume_x2_all_pass = _gate_all_pass(final_x2)
    section_gates_pass = bool(
        exact_lane_coverage
        and all(
            row.get("x2_pass") == "PASS"
            and row.get("product_quality_status") == "PASS"
            and row.get("executed") is True
            for row in by_lane.values()
        )
        and not authoritative_lane_contract_failed_lanes
    )

    aggregation = x1d.get("aggregation")
    aggregation = aggregation if isinstance(aggregation, Mapping) else {}
    judges = x1d.get("judges")
    judges = judges if isinstance(judges, list) else []
    try:
        quorum_required = int(aggregation.get("quorum_required") or 0)
    except (TypeError, ValueError):
        quorum_required = 0
    model_backed_pass_count = sum(
        1
        for judge in judges
        if isinstance(judge, Mapping) and judge.get("pass") is True
    )
    judge_quorum_satisfied = bool(
        quorum_required > 0
        and model_backed_pass_count >= quorum_required
        and aggregation.get("full_resume_coherence_pass") is True
        and not list(aggregation.get("blockers") or ())
    )

    signals: dict[str, Any] = {
        "final_resume_exists": final_json_path.is_file(),
        "final_resume_json_valid": final_resume_json_valid,
        "required_generated_sections_present": required_generated_sections_present,
        "locked_sections_preserved": locked_sections_preserved,
        "final_resume_x2_all_pass": final_resume_x2_all_pass,
        "cross_app_leakage": cross_app_leakage,
        "mock_provider_pass": mock_provider_pass,
        "direct_l4_write_bypass": direct_l4_write_bypass,
        "grounding_required": True,
        "c0_evidence_item_count": c0_evidence_count,
        "c0_support_status": "PASS" if c0_all_pass else "BLOCKED",
        "pa_consumed_c0": pa_consumed_c0,
        "pa_evidence_data_only": pa_evidence_data_only,
        "pa_schema_bound": pa_schema_bound,
        "x1d_overall": "PASS" if judge_quorum_satisfied else "BLOCKED",
        # An absent aggregate after an upstream lane block is not evidence of
        # malformed judge configuration.  Only an explicit persisted policy
        # failure may make this false.
        "x1d_policy_valid": x1d.get("policy_valid") is not False,
        "x1d_aggregate_present": bool(x1d),
        "judge_quorum_satisfied": judge_quorum_satisfied,
        "judge_execution_incomplete_lanes": sorted(
            set(judge_execution_incomplete_lanes)
        ),
        "final_materialized_acceptance_failed_lanes": sorted(
            set(final_materialized_acceptance_failed_lanes)
        ),
        "authoritative_lane_contracts_pass": not authoritative_lane_contract_failed_lanes,
        "authoritative_lane_contract_failed_lanes": sorted(
            set(authoritative_lane_contract_failed_lanes)
        ),
        "l2_handoff_failed_lanes": sorted(set(l2_handoff_failed_lanes)),
        "l2_spine_failed_lanes": sorted(set(l2_spine_failed_lanes)),
        "core_x3_non_authorizing_lanes": sorted(set(core_x3_non_authorizing_lanes)),
        "mirror_authority_violation_lanes": sorted(
            set(mirror_authority_violation_lanes)
        ),
        "lane_authority_rows": lane_authority_rows,
        "final_assembly_product_release_eligible": final_assembly_authority.get(
            "product_release_eligible"
        )
        is True,
        "final_assembly_authority_failed_checks": list(
            final_assembly_authority.get("failed_checks") or []
        ),
        "x2_unknown_lane": any(
            row["x2_failed"] > 0 and not row["x2_failed_gate_ids"] for row in lane_rows
        ),
        "section_gates_overall": "PASS" if section_gates_pass else "BLOCKED",
        "lane_rows": lane_rows,
        "min_chroma_evidence_items": len(GENERATED_LANES),
        "product_r4_bypass_documented": True,
        "final_resume_output_status": str(final_output.get("status") or ""),
        "final_resume_output_failed_gate_ids": _failed_gate_ids(
            final_output.get("failed_gate_ids")
        ),
        "expected_lane_ids": list(GENERATED_LANES),
        "observed_lane_ids": sorted(by_lane),
        "duplicate_lane_ids": sorted(duplicate_lanes),
    }
    unique_sources = tuple(dict.fromkeys(path.resolve() for path in sources))
    return signals, unique_sources, tuple(sorted(set(errors)))


def emit_whole_run_exit_review_packet(
    *,
    artifact_dir: Path,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist the one app-owned product Exit decision for a whole resume run."""

    root = Path(artifact_dir).resolve()
    signals, source_paths, source_errors = build_whole_run_exit_signals(root)
    decision = compute_whole_run_exit(signals)
    decision["exit_review_packet_ref"] = WHOLE_RUN_EXIT_ARTIFACT
    decision["x1_result_ref"] = (
        _FINAL_ASSEMBLY / "x1d_full_resume_judge_outputs.json"
    ).as_posix()
    decision["x2_result_ref"] = (
        _FINAL_ASSEMBLY / "final_resume_x2_gate_outputs.json"
    ).as_posix()
    packet: dict[str, Any] = {
        "schema_version": WHOLE_RUN_EXIT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "producer_component": "apps_rg.runtime.whole_run_exit",
        "status": (
            "PASS"
            if decision.get("x3_disposition") == X3D_ALLOW_FINISH and not source_errors
            else "BLOCKED"
        ),
        "identity": dict(identity),
        "unknown_never_pass": True,
        "signals": signals,
        "signal_source_errors": list(source_errors),
        "source_bindings": [_source_binding(root, path) for path in source_paths],
        **decision,
    }
    if source_errors:
        packet["x3_disposition"] = X3A_DENY_REROUTE
        packet["blockers"] = list(packet.get("blockers") or ()) + list(source_errors)
        source_reason = "SOURCE_BINDING_BLOCK: " + "; ".join(source_errors)
        existing_reason = str(packet.get("decisive_reason") or "").strip()
        packet["decisive_reason"] = (
            f"{existing_reason}; {source_reason}" if existing_reason else source_reason
        )
    packet["deterministic_digest"] = _digest(packet)
    atomic_write_json(root / WHOLE_RUN_EXIT_ARTIFACT, packet)
    return packet


def verify_whole_run_exit_review_packet(
    artifact_dir: Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Recompute the packet and reject changed, missing, or unbound sources."""

    root = Path(artifact_dir).resolve()
    path = root / WHOLE_RUN_EXIT_ARTIFACT
    errors: list[str] = []
    packet = _read_json_object(
        path,
        errors,
        source_ref=WHOLE_RUN_EXIT_ARTIFACT,
    )
    if packet.get("schema_version") != WHOLE_RUN_EXIT_SCHEMA:
        errors.append("WHOLE_RUN_EXIT_SCHEMA_INVALID")
    if expected_identity is not None and packet.get("identity") != dict(
        expected_identity
    ):
        errors.append("WHOLE_RUN_EXIT_IDENTITY_MISMATCH")
    stored_digest = str(packet.get("deterministic_digest") or "")
    digest_body = dict(packet)
    digest_body.pop("deterministic_digest", None)
    if stored_digest != _digest(digest_body):
        errors.append("WHOLE_RUN_EXIT_DIGEST_MISMATCH")
    signals, source_paths, source_errors = build_whole_run_exit_signals(root)
    if packet.get("signals") != signals:
        errors.append("WHOLE_RUN_EXIT_SIGNAL_DERIVATION_MISMATCH")
    if list(packet.get("signal_source_errors") or ()) != list(source_errors):
        errors.append("WHOLE_RUN_EXIT_SOURCE_ERROR_MISMATCH")
    expected_bindings = [_source_binding(root, source) for source in source_paths]
    if packet.get("source_bindings") != expected_bindings:
        errors.append("WHOLE_RUN_EXIT_SOURCE_BINDING_MISMATCH")
    decision = compute_whole_run_exit(signals)
    expected_x3 = X3A_DENY_REROUTE if source_errors else decision["x3_disposition"]
    if packet.get("x3_disposition") != expected_x3:
        errors.append("WHOLE_RUN_EXIT_DISPOSITION_MISMATCH")
    expected_status = (
        "PASS" if expected_x3 == X3D_ALLOW_FINISH and not source_errors else "BLOCKED"
    )
    if packet.get("status") != expected_status:
        errors.append("WHOLE_RUN_EXIT_STATUS_MISMATCH")
    return not errors, tuple(sorted(set(errors)))


def empty_whole_run_exit_shell() -> dict[str, Any]:
    return {
        "exit_review_packet_ref": "",
        "x1_result_ref": "",
        "x2_result_ref": "",
        "x3_disposition": "",
        "exactly_one_x3": True,
        "aggregated_from_lane_x3": [],
        "blockers": [],
        "warnings": [],
        "unknowns": [],
        "review_reasons": [],
        "block_reasons": [],
        "judge_reasons": [],
        "lane_x3_reasons": [],
        "decisive_reason": "",
    }


def _lower_list(xs: Any) -> list[str]:
    if not isinstance(xs, list):
        return []
    return [str(x) for x in xs]


def _lane_x2_failures_are_judge_only(row: Mapping[str, Any]) -> bool:
    xf = int(row.get("x2_failed") or 0)
    if xf <= 0:
        return True
    fg = _lower_list(row.get("x2_failed_gate_ids")) or _lower_list(
        row.get("x2_artifact_failed_gates")
    )
    if not fg:
        return False
    for g in fg:
        gl = g.lower()
        if "x1d" in gl or "judge" in gl:
            continue
        return False
    return True


def _unknown_dominates_section_gates(overall: str) -> bool:
    o = str(overall or "").strip().upper()
    return o in {"", "UNKNOWN"}


def write_exit_review_packet(
    repo_root: Path,
    payload: Mapping[str, Any],
    *,
    filename: str = "apps_rg_whole_run_exit_review_packet.json",
) -> Path:
    out = repo_root / "artifacts" / "ci" / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")
    return out


def compute_whole_run_exit(signals: Mapping[str, Any]) -> dict[str, Any]:
    out = empty_whole_run_exit_shell()
    blockers: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []
    review_rc: list[str] = []
    block_rc: list[str] = []
    judge_rc: list[str] = []
    lane_x3_rc: list[str] = []

    final_ok = bool(signals.get("final_resume_exists"))
    json_ok = bool(signals.get("final_resume_json_valid"))
    req = bool(signals.get("required_generated_sections_present"))
    locked = bool(signals.get("locked_sections_preserved"))
    xa2 = signals.get("final_resume_x2_all_pass")
    cross = bool(signals.get("cross_app_leakage"))
    mockp = bool(signals.get("mock_provider_pass"))
    l4bypass = bool(signals.get("direct_l4_write_bypass"))
    ground = bool(signals.get("grounding_required"))
    c0_count = int(signals.get("c0_evidence_item_count") or 0)
    c0_support = str(signals.get("c0_support_status") or "").strip().upper()
    pa_c = bool(signals.get("pa_consumed_c0"))
    pa_d = bool(signals.get("pa_evidence_data_only"))
    pa_s = bool(signals.get("pa_schema_bound"))
    x1d = str(signals.get("x1d_overall") or "").strip().upper()
    x2_unknown_lane = bool(signals.get("x2_unknown_lane"))
    lanes: list[dict[str, Any]] = list(signals.get("lane_rows") or [])
    policy_valid = bool(signals.get("x1d_policy_valid", True))
    quorum_sat = bool(signals.get("judge_quorum_satisfied", True))
    judge_incomplete_lanes = [
        str(value)
        for value in signals.get("judge_execution_incomplete_lanes", [])
        if str(value)
    ]
    acceptance_failed_lanes = [
        str(value)
        for value in signals.get("final_materialized_acceptance_failed_lanes", [])
        if str(value)
    ]
    authority_failed_lanes = [
        str(value)
        for value in signals.get("authoritative_lane_contract_failed_lanes", [])
        if str(value)
    ]
    l2_handoff_failed_lanes = [
        str(value) for value in signals.get("l2_handoff_failed_lanes", []) if str(value)
    ]
    l2_spine_failed_lanes = [
        str(value) for value in signals.get("l2_spine_failed_lanes", []) if str(value)
    ]
    core_x3_non_authorizing_lanes = [
        str(value)
        for value in signals.get("core_x3_non_authorizing_lanes", [])
        if str(value)
    ]
    mirror_authority_violation_lanes = [
        str(value)
        for value in signals.get("mirror_authority_violation_lanes", [])
        if str(value)
    ]
    final_assembly_release_eligible = bool(
        signals.get("final_assembly_product_release_eligible")
    )
    final_assembly_failed_checks = [
        str(value)
        for value in signals.get("final_assembly_authority_failed_checks", [])
        if str(value)
    ]
    final_output_status = str(signals.get("final_resume_output_status") or "").strip()
    final_output_failed_ids = [
        str(value)
        for value in signals.get("final_resume_output_failed_gate_ids", [])
        if str(value)
    ]
    product_r4_note = bool(signals.get("product_r4_bypass_documented", False))

    if product_r4_note:
        review_rc.append(RC_PRODUCT_R4_BYPASS_PRELOADED_CONTEXT)
    if c0_support == "WEAK":
        review_rc.append(RC_C0_SUPPORT_WEAK)

    out["aggregated_from_lane_x3"] = [
        {"lane": str(r.get("lane") or ""), "x3_code": str(r.get("x3_code") or "")}
        for r in lanes
    ]

    if not policy_valid:
        out["x3_disposition"] = X3A_DENY_REROUTE
        block_rc.append(RC_X1D_POLICY_MALFORMED)
        decisive_reason = (
            "X1D_POLICY_MALFORMED: invalid APPS_RG_E2E_X1D_JUDGES configuration"
        )
        out["blockers"] = [decisive_reason]
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if not final_ok:
        blockers.append("final_resume.json missing")
    if not json_ok:
        blockers.append("final_resume.json invalid or unreadable")
    if not req:
        blockers.append(
            "one or more required generated lane sections missing from final_resume"
        )
    if not locked:
        blockers.append("locked deterministic sections missing from final_resume")
    if final_output_status != "PASS" or final_output_failed_ids:
        blocker = f"FINAL_RESUME_OUTPUT status={final_output_status or 'MISSING'}"
        if final_output_failed_ids:
            blocker += " failed_gates=[" + ",".join(final_output_failed_ids) + "]"
        blockers.append(blocker)
    if xa2 is False:
        blockers.append("final_resume_x2 deterministic gates not all_pass")
        block_rc.append(RC_FINAL_RESUME_X2_FAIL)
    if xa2 is None and not blockers:
        unknowns.append(
            "final_resume_x2_all_pass unknown — could not read gate artifact"
        )
    if ground and c0_count <= 0:
        blockers.append(
            "grounding_required but C0/FEC produced zero grounded chroma evidence items"
        )

    for row in lanes:
        lk = str(row.get("lane") or "")
        xf = int(row.get("x2_failed") or 0)
        if xf > 0 and not _lane_x2_failures_are_judge_only(row):
            failed_ids = [
                str(value) for value in row.get("x2_failed_gate_ids", []) if str(value)
            ]
            detail = ",".join(failed_ids) if failed_ids else "UNKNOWN_GATE_ID"
            blockers.append(f"lane {lk}: deterministic X2 failed [{detail}]")

    if judge_incomplete_lanes:
        blockers.append(
            "model-backed judge execution incomplete for X2-pass lanes ["
            + ",".join(sorted(set(judge_incomplete_lanes)))
            + "]"
        )
    if acceptance_failed_lanes:
        blockers.append(
            "final materialized acceptance failed for lanes ["
            + ",".join(sorted(set(acceptance_failed_lanes)))
            + "]"
        )
    if authority_failed_lanes:
        blockers.append(
            "authoritative lane contract failed for lanes ["
            + ",".join(sorted(set(authority_failed_lanes)))
            + "]"
        )
    if l2_handoff_failed_lanes:
        blockers.append(
            "L2 handoff failed for lanes ["
            + ",".join(sorted(set(l2_handoff_failed_lanes)))
            + "]"
        )
    if l2_spine_failed_lanes:
        blockers.append(
            "L2 spine failed for lanes ["
            + ",".join(sorted(set(l2_spine_failed_lanes)))
            + "]"
        )
    if core_x3_non_authorizing_lanes:
        blockers.append(
            "producer-owned lane X3 is not an exact allow code for lanes ["
            + ",".join(sorted(set(core_x3_non_authorizing_lanes)))
            + "]"
        )
    if mirror_authority_violation_lanes:
        blockers.append(
            "app X3 mirror authority metadata invalid for lanes ["
            + ",".join(sorted(set(mirror_authority_violation_lanes)))
            + "]"
        )
    if not final_assembly_release_eligible:
        detail = ",".join(final_assembly_failed_checks) or "UNKNOWN"
        blockers.append(
            "final assembly is not product-release eligible [" + detail + "]"
        )

    if cross:
        blockers.append("cross_app_leakage true on C0 verification")
    if mockp:
        blockers.append("mock provider or MOCKED runtime treated as pass-path")
    if l4bypass:
        blockers.append("direct_l4_write_bypass true")

    if x2_unknown_lane:
        unknowns.append("rollup reported zero X2 gates for at least one lane")
    sg_overall = str(signals.get("section_gates_overall") or "")
    if _unknown_dominates_section_gates(sg_overall):
        unknowns.append("section_gates overall UNKNOWN")

    structural_blocked = bool(blockers)

    decisive_reason = ""

    if structural_blocked:
        out["x3_disposition"] = X3A_DENY_REROUTE
        decisive_reason = "STRUCTURAL_BLOCK: " + "; ".join(blockers[:12])
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if xa2 is None:
        out["x3_disposition"] = X3E_SAFE_ABSTAIN
        block_rc.append(RC_FINAL_RESUME_X2_FAIL)
        decisive_reason = (
            "SAFE_ABSTAIN: final_resume_x2 gate artifact missing or unreadable"
        )
        out["blockers"] = blockers
        out["warnings"] = warnings + ["do not treat UNKNOWN as runtime PASS"]
        out["unknowns"] = unknowns or ["final_resume_x2_all_pass unknown"]
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if not quorum_sat:
        judge_rc.append(RC_JUDGE_QUORUM_NOT_SATISFIED)
        out["x3_disposition"] = X3B_ESCALATE_HITL
        warnings.append("X1D aggregate judge quorum was not satisfied")
        decisive_reason = (
            "WHOLE_RUN_REVIEW: persisted X1D aggregate quorum not satisfied"
        )
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if x1d != "PASS":
        out["x3_disposition"] = X3B_ESCALATE_HITL
        fb = signals.get("x1d_judge_failure_breakdown")
        if not isinstance(fb, dict):
            fb = {}
        if bool(fb.get("x1d_judge_execution_mismatch")):
            judge_rc.append(RC_JUDGE_EXECUTION_PROVIDER_MISMATCH)
        if bool(fb.get("x1d_judge_model_backed_fail")):
            judge_rc.append(RC_JUDGE_MODEL_BACKED_QUALITY_FAIL)
        if bool(fb.get("x1d_judge_unknown_result")):
            judge_rc.append(RC_JUDGE_UNKNOWN_RESULT)
        if bool(fb.get("x1d_judge_schema_or_parser_blocked")):
            judge_rc.append(RC_JUDGE_SCHEMA_OR_PARSER_BLOCK)
        if bool(fb.get("x1d_judge_provider_unavailable_row")):
            judge_rc.append(RC_JUDGE_PROVIDER_UNAVAILABLE)
        if not judge_rc:
            judge_rc.append(RC_X1D_AGGREGATE_REVIEW)
        warnings.append(
            "X1D rollup overall != PASS — see x1d_lane_judge_diagnostics (E2E) or lane x1d artifacts"
        )
        decisive_reason = "WHOLE_RUN_REVIEW: X1D overall != PASS — diagnostics separate mismatch vs quality vs unknown"
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if x2_unknown_lane:
        out["x3_disposition"] = X3B_ESCALATE_HITL
        warnings.append(
            "rollup reported zero X2 gates for at least one lane — inspect lane x2_gate_outputs.json"
        )
        decisive_reason = (
            "WHOLE_RUN_REVIEW: rollup X2 gate coverage incomplete for at least one lane"
        )
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if _unknown_dominates_section_gates(sg_overall):
        out["x3_disposition"] = X3B_ESCALATE_HITL
        warnings.append(
            "section_gates overall UNKNOWN — do not infer PASS from ambiguous gate rollup"
        )
        decisive_reason = "WHOLE_RUN_REVIEW: section gate summary UNKNOWN"
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    codes = [
        str(r.get("x3_code") or "").strip()
        for r in lanes
        if str(r.get("x3_code") or "").strip()
    ]
    uniq = sorted(set(codes))
    supported_lane_x3_codes = {"X3_ALLOW", X3D_ALLOW_FINISH}
    mixed_lanes = (
        len(codes) != len(lanes)
        or len(uniq) > 1
        or any(c not in supported_lane_x3_codes for c in codes)
    )

    if mixed_lanes:
        out["x3_disposition"] = X3B_ESCALATE_HITL
        if len(uniq) > 1:
            lane_x3_rc.append(RC_LANE_X3_MIXED)
        if len(codes) != len(lanes) or any(
            c not in supported_lane_x3_codes for c in codes
        ):
            lane_x3_rc.append(RC_LANE_X3_NON_ALLOW)
        decisive_reason = (
            "WHOLE_RUN_REVIEW: producer-owned per-lane X3 codes differ, are missing, "
            "or are not an exact supported lane allow code"
        )
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    if not pa_c or not pa_d or not pa_s:
        out["x3_disposition"] = X3B_ESCALATE_HITL
        if not pa_c:
            warnings.append(
                "compiled_prompt FEC consumption marker missing on one or more lanes"
            )
        if not pa_d:
            warnings.append("evidence-as-data heuristic failed for one or more lanes")
        if not pa_s:
            warnings.append(
                "compiled_prompt schema binding heuristic failed on one or more lanes"
            )
        decisive_reason = "WHOLE_RUN_REVIEW: PA-equivalent prompt checks incomplete"
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    chroma_min = int(signals.get("min_chroma_evidence_items") or 1)
    if c0_count < chroma_min:
        out["x3_disposition"] = X3B_ESCALATE_HITL
        warnings.append(
            f"C0 evidence item count {c0_count} below policy minimum {chroma_min}"
        )
        decisive_reason = (
            "WHOLE_RUN_REVIEW: insufficient grounded evidence items for ALLOW_FINISH"
        )
        out["blockers"] = blockers
        out["warnings"] = warnings
        out["unknowns"] = unknowns
        out["review_reasons"] = review_rc
        out["block_reasons"] = block_rc
        out["judge_reasons"] = judge_rc
        out["lane_x3_reasons"] = lane_x3_rc
        out["decisive_reason"] = decisive_reason
        out["exactly_one_x3"] = True
        return out

    out["x3_disposition"] = X3D_ALLOW_FINISH
    decisive_reason = (
        "WHOLE_RUN_ALLOW_FINISH: structural and final-release gates PASS, X1D PASS, "
        "all producer-owned lane X3 receipts are exact and consistent allow codes, "
        "and PA/C0 grounding checks are satisfied"
    )
    out["blockers"] = blockers
    out["warnings"] = warnings
    out["unknowns"] = unknowns
    out["review_reasons"] = review_rc
    out["block_reasons"] = block_rc
    out["judge_reasons"] = judge_rc
    out["lane_x3_reasons"] = lane_x3_rc
    out["decisive_reason"] = decisive_reason
    out["exactly_one_x3"] = True
    return out
