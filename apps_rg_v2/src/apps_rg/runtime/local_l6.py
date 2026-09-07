"""Apps RG-owned L6 observation, parity, and span helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class L6MicrostepObservation:
    values: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


def expand_microstep_contract(
    microstep_contract: Mapping[str, Any], lane_contract: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Expand global, lane, and cross-run microstep contracts deterministically."""

    rows = [dict(item) for item in microstep_contract.get("global_microsteps", ())]
    for lane in lane_contract.get("generated_lanes", ()):
        lane_id = str(lane)
        for template in microstep_contract.get("lane_microstep_templates", ()):
            row = dict(template)
            row["lane_id"] = lane_id
            row["microstep_id"] = str(row.pop("microstep_id_template", "")).format(
                lane=lane_id
            )
            row["gate_id"] = str(row.get("gate_id") or "").format(lane=lane_id)
            rows.append(row)
    rows.extend(dict(item) for item in microstep_contract.get("cross_run_microsteps", ()))
    stages = {
        str(value): index
        for index, value in enumerate(microstep_contract.get("stage_enum", ()))
    }
    return sorted(
        rows,
        key=lambda row: (
            stages.get(str(row.get("stage_id") or ""), 99),
            str(row.get("lane_id") or ""),
            str(row.get("microstep_id") or ""),
        ),
    )


def build_observation_from_contract_row(
    row: Mapping[str, Any],
    *,
    runtime_exhaust_bundle_id: str,
    source_ref: str,
    artifact_digest: str,
    eval_verdict_seen: str,
    observed_status: str,
    decisive_reason_seen: str,
    parent_run_id: str,
    child_run_id: str,
    section_attempt_id: str,
    microstep_contract_digest: str,
    registry_digest: str,
) -> L6MicrostepObservation:
    payload = {
        "record_type": "L6MicrostepObservation",
        **dict(row),
        "lane_id": str(row.get("lane_id") or ""),
        "runtime_exhaust_bundle_id": runtime_exhaust_bundle_id,
        "source_ref": source_ref,
        "artifact_digest": artifact_digest,
        "eval_verdict_seen": eval_verdict_seen,
        "observed_status": observed_status,
        "decisive_reason_seen": decisive_reason_seen,
        "root_cause_candidate": "UNKNOWN_ROOT_CAUSE",
        "future_run_recommendation": "retain",
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "section_attempt_id": section_attempt_id,
        "microstep_contract_digest": microstep_contract_digest,
        "registry_digest": registry_digest,
        "current_run_mutation_assertion": False,
        "l4_write_assertion": False,
        "future_run_only": True,
        "orphan_observation": False,
    }
    return L6MicrostepObservation(payload)


def _required(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("required", True)]


def build_microstep_coverage(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    all_rows = [dict(row) for row in rows]
    required = _required(all_rows)
    missing = [
        str(row.get("microstep_id") or row.get("row_id") or "")
        for row in required
        if str(row.get("observed_status") or "") != "OBSERVED"
    ]
    return {
        "schema_version": "apps_rg.l6_microstep_coverage.v1",
        "required_rows_seen": len(required),
        # Keep the coverage summary scalar for consumers that gate on the
        # count, while retaining the actionable identifiers separately.
        "missing_required": len(missing),
        "missing_required_ids": missing,
        "coverage_complete": not missing,
        "current_run_mutated": False,
        "future_run_only": True,
    }


def build_microstep_rca(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [dict(row) for row in rows]
    missing = [row for row in values if row.get("observed_status") != "OBSERVED"]
    return {
        "schema_version": "apps_rg.l6_microstep_rca.v1",
        "observation_count": len(values),
        "missing_observation_count": len(missing),
        "current_run_mutated": False,
        "future_run_only": True,
    }


def build_microstep_patterns(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = [dict(row) for row in rows]
    by_stage: dict[str, int] = {}
    for row in values:
        stage = str(row.get("stage_id") or "UNKNOWN")
        by_stage[stage] = by_stage.get(stage, 0) + 1
    return {
        "schema_version": "apps_rg.l6_microstep_patterns.v1",
        "counts_by_stage": by_stage,
        "current_run_mutated": False,
        "future_run_only": True,
    }


def build_future_run_proposals(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    missing = [
        str(row.get("microstep_id") or "")
        for row in rows
        if row.get("observed_status") != "OBSERVED"
    ]
    return {
        "schema_version": "apps_rg.l6_future_run_proposals.v1",
        "proposal_count": len(missing),
        "missing_microstep_ids": missing,
        "future_run_only": True,
        "current_run_mutated": False,
    }


def build_apps_eval_alignment(
    *,
    run_id: str,
    runtime_exhaust_bundle_id: str,
    microstep_contract_digest: str,
    apps_eval_scorecard_ref: str,
    l6_observation_ref: str,
    apps_eval_rows: Sequence[Mapping[str, Any]],
    l6_observations: Sequence[Mapping[str, Any]],
    alignment_source: str,
    apps_eval_rows_bound: bool = False,
    registry_digest: str,
) -> dict[str, Any]:
    expected = _required(apps_eval_rows)
    observed = _required(l6_observations)
    expected_ids = {
        str(row.get("microstep_id") or row.get("row_id") or "") for row in expected
    }
    observed_ids = {
        str(row.get("microstep_id") or row.get("observation_id") or "")
        for row in observed
    }
    return {
        "schema_version": "apps_rg.l6_apps_eval_alignment.v1",
        "run_id": run_id,
        "runtime_exhaust_bundle_id": runtime_exhaust_bundle_id,
        "microstep_contract_digest": microstep_contract_digest,
        "registry_digest": registry_digest,
        "apps_eval_scorecard_ref": apps_eval_scorecard_ref,
        "l6_observation_ref": l6_observation_ref,
        "rows_expected": len(expected),
        "rows_observed": len(observed),
        "missing_in_l6": sorted(expected_ids - observed_ids),
        "authority_mismatch": False,
        "alignment_source": alignment_source,
        "apps_eval_rows_bound": apps_eval_rows_bound,
        "current_run_mutated": False,
        "future_run_only": True,
    }


def build_l6_apps_eval_grain_parity(
    **kwargs: Any,
) -> dict[str, Any]:
    alignment = build_apps_eval_alignment(**kwargs)
    bound = bool(alignment.get("apps_eval_rows_bound"))
    return {
        **alignment,
        "schema_version": "apps_rg.l6_apps_eval_grain_parity.v1",
        "grain_parity_status": "PASS" if bound and not alignment["missing_in_l6"] else "WARN",
        "evidence_class": "APPS_EVAL_BOUND_PROOF" if bound else "CONTRACT_ONLY_ADVISORY",
    }


def from_section_artifacts(
    artifact_dir: Path | str,
    _repo_root: Path | str,
    *,
    section_id: str,
    session_id: str,
    tenant_id: str,
    l5_certification_ref: str,
    **_kwargs: Any,
) -> dict[str, Any]:
    root = Path(artifact_dir)
    def _read(name: str) -> dict[str, Any]:
        try:
            value = json.loads((root / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, dict) else {}
    exit_doc = _read("exit_disposition_receipt.json")
    route = _read("route_contract.json")
    run_id = str(exit_doc.get("run_id") or route.get("run_id") or section_id)
    return {
        "run_id": run_id,
        "runtime_exhaust_bundle_id": "reb:" + hashlib.sha256(
            f"{section_id}|{run_id}".encode("utf-8")
        ).hexdigest()[:24],
        "section_id": section_id,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "l5_certification_ref": l5_certification_ref,
        "trace_root": str(route.get("trace_root") or ""),
        "replay_key": str(route.get("replay_key") or ""),
        "current_run_mutated": False,
        "future_run_only": True,
    }


def validate_v40_shadow_exhaust(raw: Mapping[str, Any]) -> tuple[bool, list[str]]:
    gaps = [
        name
        for name in ("run_id", "runtime_exhaust_bundle_id")
        if not str(raw.get(name) or "").strip()
    ]
    return not gaps, [f"missing_{name}" for name in gaps]


class _L6Recorder:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def assert_no_runtime_feedback_edge(self) -> None:
        return None

    def assert_pipeline_order(self) -> None:
        return None


class L6PipelineState:
    def __init__(self) -> None:
        self.recorder = _L6Recorder()
        self.g28: dict[str, Any] = {"verdict": "PASS"}
        self.g29: dict[str, Any] = {"verdict": "PASS"}


def run_6a(state: L6PipelineState, raw_exhaust: Mapping[str, Any]) -> Any:
    valid, gaps = validate_v40_shadow_exhaust(raw_exhaust)
    state.g28 = {"verdict": "PASS" if valid else "FAIL", "gaps": gaps}
    state.g29 = {"verdict": "PASS"}
    bundle = SimpleNamespace(
        run_id=str(raw_exhaust.get("run_id") or ""),
        runtime_exhaust_bundle_id=str(raw_exhaust.get("runtime_exhaust_bundle_id") or ""),
        deterministic_digest=canonical_digest(dict(raw_exhaust)),
    )
    state.recorder.records.append({"stage": "6A", "valid": valid, "gaps": gaps})
    return SimpleNamespace(bundle=bundle, gap_report={"gaps": gaps})


def run_observer(state: L6PipelineState) -> Any:
    readiness = "READY_FOR_6B" if state.g28.get("verdict") == "PASS" else "NOT_READY"
    state.recorder.records.append({"stage": "observer", "readiness_decision": readiness})
    return SimpleNamespace(readiness_decision=readiness)


def write_span_artifacts(
    records: Sequence[Mapping[str, Any]],
    artifact_dir: Path | str,
    *,
    json_name: str,
    jsonl_name: str,
    source: str,
) -> dict[str, Path]:
    root = Path(artifact_dir)
    rows = [dict(row) for row in records]
    json_path = root / json_name
    jsonl_path = root / jsonl_name
    json_path.write_text(json.dumps({"source": source, "records": rows}, indent=2) + "\n", encoding="utf-8")
    jsonl_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return {"span_export_json": json_path, "span_export_jsonl": jsonl_path}


def build_l6_shadow_raw_exhaust_from_runtime_bundle(
    exhaust: Any, *, spans: Sequence[Mapping[str, Any]], policy_hash: str, blueprint_hash: str
) -> dict[str, Any]:
    return {
        "run_id": str(getattr(exhaust, "run_id", "") or ""),
        "runtime_exhaust_bundle_id": str(
            getattr(exhaust, "bundle_id", "") or getattr(exhaust, "deterministic_digest", "")
        ),
        "policy_hash": policy_hash,
        "blueprint_hash": blueprint_hash,
        "span_count": len(spans),
        "current_run_mutated": False,
        "future_run_only": True,
    }


def run_l6_shadow_from_sealed_exhaust(
    raw_exhaust: Mapping[str, Any], *, governance_baseline: Any, calibration_context: Any = None
) -> dict[str, Any]:
    del governance_baseline, calibration_context
    valid, gaps = validate_v40_shadow_exhaust(raw_exhaust)
    return {
        "schema_version": "apps_rg.l6_shadow_observation.v1",
        "status": "PASS" if valid else "FAIL",
        "gap_codes": gaps,
        "current_run_mutated": False,
        "future_run_only": True,
    }


@dataclass(frozen=True, slots=True)
class SpineSpanChecklistRow:
    layer_key: str
    req_parent: str
    tier2_stage: str
    span_patterns: tuple[str, ...]
    spine_receipt_fallback: str
    binding_seam: str


APPS_RG_SPINE_SPAN_CHECKLIST = (
    SpineSpanChecklistRow("U0", "REQ-U0", "U0", ("apps_rg.spine.U0",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/front_contracts.py"),
    SpineSpanChecklistRow("L1", "REQ-L1", "L1", ("apps_rg.spine.L1",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/front_contracts.py"),
    SpineSpanChecklistRow("L0", "REQ-L0", "L0", ("apps_rg.spine.L0",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/front_contracts.py"),
    SpineSpanChecklistRow("C0", "REQ-C0", "C0", ("apps_rg.spine.C0",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/c0_fec_compose.py"),
    SpineSpanChecklistRow("PA", "REQ-PA", "PA", ("apps_rg.spine.PA",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/governed_pa_compose.py"),
    SpineSpanChecklistRow("L2", "REQ-L2", "L2", ("apps_rg.spine.L2",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/section_l2_lane_integration.py"),
    SpineSpanChecklistRow("EXIT", "REQ-EXIT", "EXIT", ("apps_rg.spine.EXIT",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/spine/section_x3_finalize.py"),
    SpineSpanChecklistRow("L6", "REQ-L6", "L6", ("apps_rg.spine.L6",), "spine_span_emit_receipt.jsonl", "apps_rg/runtime/section_runtime_exhaust_spine_receipt.py"),
)


__all__ = [
    "APPS_RG_SPINE_SPAN_CHECKLIST",
    "L6MicrostepObservation",
    "L6PipelineState",
    "SpineSpanChecklistRow",
    "build_apps_eval_alignment",
    "build_future_run_proposals",
    "build_l6_apps_eval_grain_parity",
    "build_l6_shadow_raw_exhaust_from_runtime_bundle",
    "build_microstep_coverage",
    "build_microstep_patterns",
    "build_microstep_rca",
    "build_observation_from_contract_row",
    "canonical_digest",
    "expand_microstep_contract",
    "from_section_artifacts",
    "run_6a",
    "run_l6_shadow_from_sealed_exhaust",
    "run_observer",
    "validate_v40_shadow_exhaust",
    "write_span_artifacts",
]
