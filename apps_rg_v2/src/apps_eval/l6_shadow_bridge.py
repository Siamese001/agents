"""apps_eval bridge into core L6 shadow observability.

apps_eval is a proof harness.  Rows projected into L6 observations inside this
module are explicitly labelled projection consistency, not independent
apps_eval-bound proof.  Independent bound proof is emitted only by the
post-boundary binder over persisted apps_rg L6 observations.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from apps_rg.runtime.apps_runtime_compat import (
    build_l6_apps_eval_grain_parity,
)
from apps_rg.runtime.apps_runtime_compat import (
    EVIDENCE_CLASS_CONTRACT_ONLY_ADVISORY,
    build_apps_eval_alignment,
    build_future_run_proposals,
    build_microstep_coverage,
    build_microstep_patterns,
    build_microstep_rca,
    build_observations_from_eval_rows,
)
from apps_rg.runtime.apps_runtime_compat import (
    L6PipelineState,
    run_6a,
    run_observer,
)
from apps_rg.runtime.apps_runtime_compat import write_span_artifacts
from apps_eval import _write_gateway as _wg
from apps_eval.contracts import CURRENT_EVAL_RECORD_SCHEMA_VERSION, CompletedEvalRecord

L6_SHADOW_BRIDGE_ARTIFACT = "l6_shadow_bridge.json"
L6_SHADOW_BRIDGE_SPANS_ARTIFACT = "l6_shadow_bridge_spans.json"
L6_SHADOW_BRIDGE_SPANS_JSONL_ARTIFACT = "l6_shadow_bridge_spans.jsonl"
L6_MICROSTEP_OBSERVATIONS_ARTIFACT = "l6_microstep_observations.jsonl"
L6_MICROSTEP_COVERAGE_ARTIFACT = "l6_microstep_coverage.json"
L6_MICROSTEP_RCA_ARTIFACT = "l6_microstep_rca.json"
L6_MICROSTEP_PATTERNS_ARTIFACT = "l6_microstep_patterns.json"
L6_MICROSTEP_FUTURE_RUN_PROPOSALS_ARTIFACT = "l6_microstep_future_run_proposals.json"
L6_APPS_EVAL_ALIGNMENT_ARTIFACT = "l6_apps_eval_alignment.json"
L6_APPS_EVAL_GRAIN_PARITY_ARTIFACT = "l6_apps_eval_grain_parity.json"


@contextmanager
def _deterministic_l6_runtime(
    *,
    seed: str,
    timestamp: str,
) -> Iterator[None]:
    """Make the imported core observer deterministic for artifact replay.

    Core L6 correctly uses fresh UUIDs and wall-clock timestamps for ordinary
    live observations.  Historical replay needs byte-stable evidence instead,
    so this narrow bridge temporarily supplies digest-derived identifiers and
    the completed record timestamp.  The patch is restored before returning
    and is never used by the live apps_rg runtime.
    """

    ingest = importlib.import_module(
        "apps_rg.L6_observability.shadow_eval.ingest"
    )
    observer = importlib.import_module(
        "apps_rg.L6_observability.shadow_eval.observer"
    )
    span_export = importlib.import_module(
        "apps_rg.L6_observability.shadow_eval.span_export"
    )
    originals = {
        "ingest_id": ingest._gen_id,
        "observer_id": observer._gen_id,
        "observer_now": observer._now_iso,
        "span_now": span_export._now_iso,
    }
    counters: dict[str, int] = {}

    def _stable_id(prefix: str) -> str:
        ordinal = counters.get(prefix, 0)
        counters[prefix] = ordinal + 1
        digest = hashlib.sha256(
            f"{seed}:{prefix}:{ordinal}".encode("utf-8")
        ).hexdigest()
        return f"{prefix}-{digest[:32]}"

    stable_timestamp = timestamp or "1970-01-01T00:00:00Z"
    ingest._gen_id = _stable_id
    observer._gen_id = _stable_id
    observer._now_iso = lambda: stable_timestamp
    span_export._now_iso = lambda: stable_timestamp
    try:
        yield
    finally:
        ingest._gen_id = originals["ingest_id"]
        observer._gen_id = originals["observer_id"]
        observer._now_iso = originals["observer_now"]
        span_export._now_iso = originals["span_now"]


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _hash_ref(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _write_json_artifact(path: Path, payload: Any) -> Path:
    _wg.write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def _write_jsonl_artifact(path: Path, rows: list[Mapping[str, Any]]) -> Path:
    _wg.write_text(
        path,
        "".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _trace_reconciliation_refs(record: CompletedEvalRecord) -> list[str]:
    refs: list[str] = []
    for row in record.scorecard.scorecard_rows or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("artifact_role") or "") != "trace_reconciliation":
            continue
        ref = str(row.get("artifact_ref") or "").strip().replace("\\", "/")
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _resolve_ref(ref: str, *, record_ref: str) -> Path | None:
    path = Path(ref)
    candidates = [path] if path.is_absolute() else [Path(record_ref).parent / path, Path.cwd() / path]
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def _trace_observability_summary_refs(
    record: CompletedEvalRecord,
    *,
    eval_record_path: str,
) -> list[str]:
    """Return only existing, schema-valid summaries; never trust filename inference alone."""

    refs: list[str] = []
    for reconciliation_ref in _trace_reconciliation_refs(record):
        if not reconciliation_ref.endswith("trace_reconciliation.json"):
            continue
        candidate_ref = (
            reconciliation_ref[: -len("trace_reconciliation.json")]
            + "l6_trace_observability_summary.json"
        )
        candidate = _resolve_ref(candidate_ref, record_ref=eval_record_path)
        if candidate is None:
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, Mapping):
            continue
        if str(payload.get("schema_version") or "") != "apps_rg.l6_trace_observability_summary.v1":
            continue
        normalized = candidate.as_posix()
        if normalized not in refs:
            refs.append(normalized)
    return refs


def _diagnostic_refs(record: CompletedEvalRecord) -> dict[str, str]:
    refs: dict[str, str] = {}
    for key in ("diagnostic_rows", "diagnostic_summary"):
        ref = str(record.artifact_paths.get(key) or "").strip()
        if ref:
            refs[key] = ref.replace("\\", "/")
    return refs


def _emit_record_microstep_artifacts(
    record: CompletedEvalRecord,
    run_dir: Path,
    *,
    runtime_exhaust_bundle_id: str,
) -> dict[str, str]:
    if record.app_id != "apps_rg":
        return {}
    scorecard_rows = [
        dict(row)
        for row in list(record.scorecard.scorecard_rows or [])
        if isinstance(row, Mapping) and row.get("required", True)
    ]
    if not scorecard_rows:
        return {}

    observations = build_observations_from_eval_rows(
        scorecard_rows,
        runtime_exhaust_bundle_id=runtime_exhaust_bundle_id,
    )
    observation_dicts = [observation.to_dict() for observation in observations]
    observation_path = _write_jsonl_artifact(
        run_dir / L6_MICROSTEP_OBSERVATIONS_ARTIFACT,
        observation_dicts,
    )
    coverage_path = _write_json_artifact(
        run_dir / L6_MICROSTEP_COVERAGE_ARTIFACT,
        build_microstep_coverage(observation_dicts),
    )
    rca_path = _write_json_artifact(
        run_dir / L6_MICROSTEP_RCA_ARTIFACT,
        build_microstep_rca(observation_dicts),
    )
    patterns_path = _write_json_artifact(
        run_dir / L6_MICROSTEP_PATTERNS_ARTIFACT,
        build_microstep_patterns(observation_dicts),
    )
    proposals_path = _write_json_artifact(
        run_dir / L6_MICROSTEP_FUTURE_RUN_PROPOSALS_ARTIFACT,
        build_future_run_proposals(observation_dicts),
    )
    scorecard_ref = str(
        record.artifact_paths.get("scorecard_rows") or (run_dir / "scorecard_rows.jsonl")
    ).replace("\\", "/")
    contract_digest = str(record.record_seed.get("apps_rg_microstep_contract_digest") or "")
    registry_digest = str(
        record.registry_digest
        or record.record_seed.get("registry_digest")
        or contract_digest
    )

    alignment = build_apps_eval_alignment(
        run_id=record.record_id,
        runtime_exhaust_bundle_id=runtime_exhaust_bundle_id,
        microstep_contract_digest=contract_digest,
        apps_eval_scorecard_ref=scorecard_ref,
        l6_observation_ref=observation_path.as_posix(),
        apps_eval_rows=scorecard_rows,
        l6_observations=observation_dicts,
        alignment_source="contract_only_pseudo_rows",
        apps_eval_rows_bound=False,
        registry_digest=registry_digest,
    )
    alignment.update(
        {
            "projection_consistency_only": True,
            "projection_source": "apps_eval_scorecard_rows",
            "independent_observation_required_for_bound_proof": True,
            "evidence_class": EVIDENCE_CLASS_CONTRACT_ONLY_ADVISORY,
        }
    )
    alignment_path = _write_json_artifact(
        run_dir / L6_APPS_EVAL_ALIGNMENT_ARTIFACT,
        alignment,
    )

    parity = build_l6_apps_eval_grain_parity(
        run_id=record.record_id,
        runtime_exhaust_bundle_id=runtime_exhaust_bundle_id,
        microstep_contract_digest=contract_digest,
        apps_eval_scorecard_ref=scorecard_ref,
        l6_observation_ref=observation_path.as_posix(),
        apps_eval_rows=scorecard_rows,
        l6_observations=observation_dicts,
        alignment_source="contract_only_pseudo_rows",
        registry_digest=registry_digest,
    )
    parity.update(
        {
            "projection_consistency_only": True,
            "projection_source": "apps_eval_scorecard_rows",
            "independent_observations": False,
            "apps_eval_rows_bound": False,
            "grain_parity_status": "WARN",
            "evidence_class": EVIDENCE_CLASS_CONTRACT_ONLY_ADVISORY,
        }
    )
    parity_path = _write_json_artifact(
        run_dir / L6_APPS_EVAL_GRAIN_PARITY_ARTIFACT,
        parity,
    )
    return {
        "l6_microstep_observations": observation_path.as_posix(),
        "l6_microstep_coverage": coverage_path.as_posix(),
        "l6_microstep_rca": rca_path.as_posix(),
        "l6_microstep_patterns": patterns_path.as_posix(),
        "l6_microstep_future_run_proposals": proposals_path.as_posix(),
        "l6_apps_eval_alignment": alignment_path.as_posix(),
        "l6_apps_eval_grain_parity": parity_path.as_posix(),
    }


def build_completed_eval_shadow_exhaust(
    record: CompletedEvalRecord,
    *,
    eval_record_path: str,
    l6_handoff_path: str = "",
) -> dict[str, object]:
    """Build completed-eval exhaust without inventing trusted trace sidecars."""

    scorecard = record.scorecard.to_dict()
    record_ref = eval_record_path.replace("\\", "/")
    handoff_ref = l6_handoff_path.replace("\\", "/") if l6_handoff_path else ""
    trace_refs = _trace_reconciliation_refs(record)
    trace_summary_refs = _trace_observability_summary_refs(
        record,
        eval_record_path=eval_record_path,
    )
    diagnostic_refs = _diagnostic_refs(record)
    outcome_class = "normal_success" if record.scorecard.verdict == "pass" else "policy_failure"
    trace_root = f"trace:apps_eval:{record.record_id}"
    generated = [record_ref] + ([handoff_ref] if handoff_ref else []) + trace_refs + trace_summary_refs
    generated += list(diagnostic_refs.values())

    source_exhaust: list[dict[str, object]] = [
        {
            "source_type": "apps_eval_completed_eval_record",
            "source_ref": record_ref,
            "source_hash": _hash_ref(record.to_dict()),
            "source_schema_version": CURRENT_EVAL_RECORD_SCHEMA_VERSION,
            "observed_stage": "EXIT",
            "expected_stage_order": 7,
            "lineage_parent_refs": [trace_root],
            "completeness_status": "COMPLETE",
            "trust_status": "TRUSTED",
        }
    ]
    source_exhaust.extend(
        {
            "source_type": "apps_rg_trace_reconciliation",
            "source_ref": ref,
            "source_hash": _hash_ref({"trace_reconciliation_ref": ref}),
            "source_schema_version": "apps_rg.trace_reconciliation.v1",
            "observed_stage": "L6",
            "expected_stage_order": 11,
            "lineage_parent_refs": [trace_root, record_ref],
            "completeness_status": "COMPLETE",
            "trust_status": "TRUSTED",
        }
        for ref in trace_refs
    )
    source_exhaust.extend(
        {
            "source_type": "apps_rg_l6_trace_observability_summary",
            "source_ref": ref,
            "source_hash": _hash_ref(Path(ref).read_text(encoding="utf-8")),
            "source_schema_version": "apps_rg.l6_trace_observability_summary.v1",
            "observed_stage": "L6",
            "expected_stage_order": 11,
            "lineage_parent_refs": [trace_root, record_ref],
            "completeness_status": "COMPLETE",
            "trust_status": "TRUSTED",
        }
        for ref in trace_summary_refs
    )
    source_exhaust.extend(
        {
            "source_type": f"apps_eval_{key}",
            "source_ref": ref,
            "source_hash": _hash_ref({"diagnostic_ref": ref, "diagnostic_role": key}),
            "source_schema_version": (
                "apps_eval.diagnostic_observation.v1"
                if key == "diagnostic_rows"
                else "apps_eval.diagnostic_summary.v1"
            ),
            "observed_stage": "L6",
            "expected_stage_order": 11,
            "lineage_parent_refs": [trace_root, record_ref],
            "completeness_status": "COMPLETE",
            "trust_status": "TRUSTED",
        }
        for key, ref in diagnostic_refs.items()
    )

    file_hashes = {record_ref: _hash_ref(record.to_dict())}
    file_hashes.update({ref: _hash_ref({"ref": ref}) for ref in generated if ref != record_ref})
    return {
        "runtime_boundary_crossed": True,
        "completed_at": record.created_at,
        "request_id": f"apps-eval:{record.record_id}",
        "run_id": record.record_id,
        "session_id": record.suite_id,
        "tenant_id": "apps_eval",
        "trace_root": trace_root,
        "exit_disposition_ref": record_ref,
        "exit_disposition": record.scorecard.verdict,
        "route_id": record.suite_id,
        "execution_form": "apps_eval_completed_eval_record",
        "terminal_class": outcome_class,
        "outcome_class": outcome_class,
        "policy_hash": _hash_ref(record.rubric_ids),
        "blueprint_hash": _hash_ref({"suite_id": record.suite_id, "app_id": record.app_id}),
        "replay_key": f"apps_eval:deterministic:{record.record_id}",
        "route_contract_ref": record.suite_id,
        "l1_plan_ref": "apps_eval:proof_harness",
        "c0_evidence_contract_refs": [record_ref],
        "prompt_envelope_refs": [],
        "l2_artifact_refs": [record_ref],
        "source_lineage_manifest_ref": record_ref,
        "l5_certification_ref": f"l5-cert-ref:apps_eval:{record.record_id}",
        "source_exhaust": source_exhaust,
        "events": [
            {
                "event_type": "apps_eval.scorecard",
                "stage": "EXIT",
                "source_ref": record_ref,
                "payload_ref": record_ref,
                "trace_id": trace_root,
                "span_id": f"apps_eval:{record.record_id}:scorecard",
                "parent_span_id": None,
                "provider_lane": "apps_eval",
                "prompt_hash": "",
                "context_hash": "",
                "artifact_digest": _hash_ref(scorecard),
                "eval_readiness_hint": "READY",
            }
        ],
        "artifacts": {
            "generated": generated,
            "sealed": [record_ref],
            "file_hashes": file_hashes,
            "artifact_lineage": {ref: [trace_root, record_ref] for ref in generated},
            "missing": [],
            "orphans": [],
        },
    }


def emit_completed_eval_l6_shadow_bridge(
    record: CompletedEvalRecord,
    run_dir: Path,
    *,
    eval_record_path: str,
    l6_handoff_path: str = "",
    deterministic_replay: bool = False,
) -> dict[str, str]:
    raw_exhaust = build_completed_eval_shadow_exhaust(
        record,
        eval_record_path=eval_record_path,
        l6_handoff_path=l6_handoff_path,
    )
    runtime_context = (
        _deterministic_l6_runtime(
            seed=f"apps-eval-l6-shadow:{record.record_id}",
            timestamp=record.created_at,
        )
        if deterministic_replay
        else nullcontext()
    )
    with runtime_context:
        state = L6PipelineState()
        ingest = run_6a(state, raw_exhaust)
        readiness = run_observer(state)
        state.recorder.assert_no_runtime_feedback_edge()
        state.recorder.assert_pipeline_order()
        span_paths = write_span_artifacts(
            state.recorder.records,
            run_dir,
            json_name=L6_SHADOW_BRIDGE_SPANS_ARTIFACT,
            jsonl_name=L6_SHADOW_BRIDGE_SPANS_JSONL_ARTIFACT,
            source="apps_eval_l6_shadow_bridge",
        )
        microstep_paths = _emit_record_microstep_artifacts(
            record,
            run_dir,
            runtime_exhaust_bundle_id=ingest.bundle.runtime_exhaust_bundle_id,
        )
    bridge = {
        "schema_version": "apps_eval.l6_shadow_bridge.v2",
        "record_id": record.record_id,
        "suite_id": record.suite_id,
        "app_id": record.app_id,
        "contract_profile_id": record.contract_profile_id,
        "evidence_class": (
            record.evidence_class or EVIDENCE_CLASS_CONTRACT_ONLY_ADVISORY
        ),
        "product_eligible": record.product_eligible,
        "runtime_exhaust_bundle_id": ingest.bundle.runtime_exhaust_bundle_id,
        "readiness_decision": readiness.readiness_decision,
        "readiness_receipt": _jsonable(readiness),
        "g28_audit_completeness": _jsonable(state.g28),
        "g29_learning_firewall": _jsonable(state.g29),
        "span_export_ref": span_paths["span_export_json"].as_posix(),
        "span_export_jsonl_ref": span_paths["span_export_jsonl"].as_posix(),
        "l6_microstep_artifact_refs": dict(microstep_paths),
        "l6_projection_evidence_class": (
            EVIDENCE_CLASS_CONTRACT_ONLY_ADVISORY if microstep_paths else ""
        ),
        "projection_consistency_only": bool(microstep_paths),
        "independent_observation_required_for_bound_proof": True,
        "trace_reconciliation_refs": _trace_reconciliation_refs(record),
        "trace_observability_summary_refs": _trace_observability_summary_refs(
            record,
            eval_record_path=eval_record_path,
        ),
        "diagnostic_artifact_refs": _diagnostic_refs(record),
        "requested_action": "consume_completed_eval_record_only",
        "current_run_mutated": False,
        "direct_l4_write_attempted": False,
        "durable_write_attempted": False,
        "future_run_only": True,
        "deterministic_replay": deterministic_replay,
    }
    bridge_path = _write_json_artifact(run_dir / L6_SHADOW_BRIDGE_ARTIFACT, bridge)
    return {
        "l6_shadow_bridge": bridge_path.as_posix(),
        "l6_shadow_bridge_spans": span_paths["span_export_json"].as_posix(),
        "l6_shadow_bridge_spans_jsonl": span_paths["span_export_jsonl"].as_posix(),
        **microstep_paths,
    }


def build_driver_l6_shadow_bridge_payload(
    *,
    eval_id: str | None,
    app_scorecards: list[Mapping[str, Any]],
    output_refs: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "apps_eval.driver_l6_shadow_bridge.v1",
        "eval_id": eval_id,
        "scorecard_count": len(app_scorecards),
        "output_refs": dict(output_refs),
        "requires_g28_audit_completeness": True,
        "requires_g29_learning_firewall": True,
        "requested_action": "consume_completed_eval_artifacts_only",
        "current_run_mutated": False,
        "direct_l4_write_attempted": False,
        "durable_write_attempted": False,
        "future_run_only": True,
    }


def emit_driver_l6_shadow_bridge(
    run_dir: Path,
    *,
    eval_id: str | None,
    app_scorecards: list[Mapping[str, Any]],
    output_refs: Mapping[str, str],
) -> dict[str, str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    bridge = build_driver_l6_shadow_bridge_payload(
        eval_id=eval_id,
        app_scorecards=app_scorecards,
        output_refs=output_refs,
    )
    bridge_path = _write_json_artifact(run_dir / L6_SHADOW_BRIDGE_ARTIFACT, bridge)
    return {"l6_shadow_bridge": bridge_path.as_posix()}


__all__ = [
    "L6_SHADOW_BRIDGE_ARTIFACT",
    "L6_SHADOW_BRIDGE_SPANS_ARTIFACT",
    "L6_SHADOW_BRIDGE_SPANS_JSONL_ARTIFACT",
    "build_completed_eval_shadow_exhaust",
    "build_driver_l6_shadow_bridge_payload",
    "emit_completed_eval_l6_shadow_bridge",
    "emit_driver_l6_shadow_bridge",
]
