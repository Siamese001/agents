"""Deterministic W3 L6 shadow replay over sealed historical evidence.

The module remains stdlib-only at import time.  The caller installs the W0
zero-provider boundary before this module imports Apps Eval or an L6 runtime.
W3 executes the observer, binds independently persisted lane observations to
the sealed W2 scorecard, records every proof gap, and never mutates the source
run or requests a product/UWG write.
"""

from __future__ import annotations

import hashlib
import json
import os
import traceback
import uuid
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, Mapping


W3_COMPLETION_SCHEMA = "apps_rg.l6_shadow_replay_completion.v1"
W3_COMPLETION_FILENAME = "w3_completion_receipt.json"
W3_PACKAGE_SEAL_SCHEMA = "apps_rg.l6_shadow_replay_package_seal.v1"
W3_PACKAGE_SEAL_FILENAME = "w3_l6_shadow_package_seal.json"
W3_BINDINGS_SCHEMA = "apps_rg.l6_section_apps_eval_bindings.v3"
W3_BINDINGS_FILENAME = "l6_section_apps_eval_bindings.json"
W3_BINDING_CLOSURE_SCHEMA = "apps_rg.l6_apps_eval_binding_closure_receipt.v2"
W3_BINDING_CLOSURE_FILENAME = "l6_apps_eval_binding_closure_receipt.json"
W3_CALIBRATION_SCHEMA = "apps_rg.l6_judge_human_calibration_status.v1"
W3_CALIBRATION_FILENAME = "l6_judge_human_calibration_status.json"
W3_ERROR_RECEIPT_SCHEMA = "apps_rg.post_runtime_stage_error.v1"
W3_ERROR_SPAN_SCHEMA = "apps_rg.local_post_runtime_error_span.v1"
W3_RESUME_RECEIPT_SCHEMA = "apps_rg.post_runtime_stage_resume.v1"
W3_ERROR_RECEIPT_FILENAME = "failures/l6_shadow_error_receipt.json"
W3_ERROR_SPAN_FILENAME = "failures/l6_shadow_error_span.json"
W3_RESUME_RECEIPT_FILENAME = "failures/l6_shadow_resume_receipt.json"

W2_COMPLETION_FILENAME = "w2_completion_receipt.json"
W2_GUARD_FILENAME = "w2_zero_provider_guard_receipt.json"
W2_SUPERSESSION_SCHEMA = "apps_rg.eval_package_supersession_manifest.v1"
REQUIRED_ZERO_ACTIVITY_COUNTERS = frozenset(
    {
        "blocked_import_attempts",
        "embedding_calls",
        "judge_calls",
        "model_calls",
        "network_attempts",
        "provider_calls",
        "subprocess_attempts",
    }
)

EXPECTED_LANES: tuple[str, ...] = (
    "competencies",
    "executive_summary",
    "ey_bullets",
    "ey_narrative",
    "headline",
    "ibm_bullets",
    "ibm_narrative",
    "insurtech_bullets",
    "insurtech_narrative",
    "unify_bullets",
    "unify_narrative",
)


class L6ShadowReplayError(RuntimeError):
    """Raised when sealed W2 or source L6 evidence is unsafe to consume."""


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise L6ShadowReplayError(f"{label}_unreadable:{path}") from exc
    if not isinstance(payload, dict):
        raise L6ShadowReplayError(f"{label}_not_object:{path}")
    return payload


def _read_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise L6ShadowReplayError(f"{label}_unreadable:{path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, TypeError) as exc:
            raise L6ShadowReplayError(
                f"{label}_invalid_json:{path}:{line_number}"
            ) from exc
        if not isinstance(payload, dict):
            raise L6ShadowReplayError(
                f"{label}_row_not_object:{path}:{line_number}"
            )
        rows.append(payload)
    return rows


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)
    return path


def _write_semantic(path: Path, payload: Mapping[str, Any]) -> Path:
    body = dict(payload)
    body["semantic_digest"] = _canonical_digest(body)
    return _atomic_write_json(path, body)


def _stable_id(*parts: str, length: int) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


def _emit_stage_failure(
    *,
    output: Path,
    source_run_id: str,
    exc: Exception,
    attempt: int,
) -> dict[str, Path]:
    """Persist the real L6 boundary exception before propagating it."""

    stage_id = "L6_SHADOW_OBSERVABILITY"
    trace_id = _stable_id(
        source_run_id,
        stage_id,
        type(exc).__name__,
        str(exc),
        str(attempt),
        length=32,
    )
    span_id = _stable_id(trace_id, "span", length=16)
    receipt_path = output / W3_ERROR_RECEIPT_FILENAME
    span_path = output / W3_ERROR_SPAN_FILENAME
    formatted = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    _write_semantic(
        receipt_path,
        {
            "schema_version": W3_ERROR_RECEIPT_SCHEMA,
            "status": "CAPTURED",
            "wave": "W3",
            "stage_id": stage_id,
            "source_run_id": source_run_id,
            "attempt": attempt,
            "error_type": type(exc).__name__,
            "error_module": type(exc).__module__,
            "error_message": str(exc),
            "traceback": formatted,
            "trace_id": trace_id,
            "span_id": span_id,
            "recovery_action": "RESUME_FROM_L6_SAVED_W2",
            "w1_replayed": False,
            "w2_replayed": False,
            "apps_eval_replayed": False,
            "generation_replayed": False,
            "judge_replayed": False,
            "embedding_replayed": False,
            "uwg_operation_attempted": False,
            "provider_calls": 0,
            "judge_calls": 0,
            "embedding_calls": 0,
            "model_calls": 0,
            "network_attempts": 0,
            "local_authority": True,
        },
    )
    _write_semantic(
        span_path,
        {
            "schema_version": W3_ERROR_SPAN_SCHEMA,
            "status": "ERROR",
            "wave": "W3",
            "stage_id": stage_id,
            "source_run_id": source_run_id,
            "attempt": attempt,
            "trace_id": trace_id,
            "span_id": span_id,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "recovery_action": "RESUME_FROM_L6_SAVED_W2",
            "provider_execution": False,
            "apps_eval_execution": False,
            "generation_execution": False,
            "judge_execution": False,
            "embedding_execution": False,
            "uwg_execution": False,
            "local_authority": True,
            "remote_otel_role": "OPTIONAL_MIRROR_NOT_AUTHORITY",
        },
    )
    return {"error_receipt": receipt_path, "error_span": span_path}


def _emit_stage_resume(
    *,
    output: Path,
    source_run_id: str,
    w2: Mapping[str, Any],
) -> Path | None:
    error_path = output / W3_ERROR_RECEIPT_FILENAME
    span_path = output / W3_ERROR_SPAN_FILENAME
    if not error_path.is_file() and not span_path.is_file():
        return None
    if not error_path.is_file() or not span_path.is_file():
        raise L6ShadowReplayError("W3 failure evidence is incomplete")
    error = _read_json(error_path, label="w3_error_receipt")
    span = _read_json(span_path, label="w3_error_span")
    checks = {
        "error_schema": error.get("schema_version") == W3_ERROR_RECEIPT_SCHEMA,
        "error_semantic": _semantic_digest_valid(error),
        "error_stage": error.get("stage_id") == "L6_SHADOW_OBSERVABILITY",
        "error_source": error.get("source_run_id") == source_run_id,
        "error_zero_upstream_replay": error.get("w1_replayed") is False
        and error.get("w2_replayed") is False
        and error.get("apps_eval_replayed") is False
        and error.get("generation_replayed") is False
        and error.get("judge_replayed") is False
        and error.get("embedding_replayed") is False
        and error.get("uwg_operation_attempted") is False,
        "span_schema": span.get("schema_version") == W3_ERROR_SPAN_SCHEMA,
        "span_semantic": _semantic_digest_valid(span),
        "span_source": span.get("source_run_id") == source_run_id,
        "span_zero_upstream_execution": span.get("provider_execution") is False
        and span.get("apps_eval_execution") is False
        and span.get("generation_execution") is False
        and span.get("judge_execution") is False
        and span.get("embedding_execution") is False
        and span.get("uwg_execution") is False,
        "identity": error.get("trace_id") == span.get("trace_id")
        and error.get("span_id") == span.get("span_id"),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    if failures:
        raise L6ShadowReplayError(
            "w3_failure_evidence_invalid:" + ",".join(failures)
        )
    return _write_semantic(
        output / W3_RESUME_RECEIPT_FILENAME,
        {
            "schema_version": W3_RESUME_RECEIPT_SCHEMA,
            "status": "PASS",
            "wave": "W3",
            "stage_id": "L6_SHADOW_OBSERVABILITY",
            "source_run_id": source_run_id,
            "resume_from_stage": "L6_SHADOW_OBSERVABILITY",
            "upstream_saved_artifacts_reused": True,
            "w1_replayed": False,
            "w2_replayed": False,
            "apps_eval_replayed": False,
            "generation_replayed": False,
            "judge_replayed": False,
            "embedding_replayed": False,
            "uwg_operation_attempted": False,
            "w2_completion_ref": w2["completion_path"].as_posix(),
            "w2_completion_semantic_digest": w2["completion"][
                "semantic_digest"
            ],
            "w2_guard_ref": w2["guard_path"].as_posix(),
            "w2_guard_semantic_digest": w2["guard"]["semantic_digest"],
            "error_receipt": _file_binding(error_path, relative_to=output),
            "error_span": _file_binding(span_path, relative_to=output),
        },
    )


def _semantic_digest_valid(payload: Mapping[str, Any]) -> bool:
    body = dict(payload)
    observed = str(body.pop("semantic_digest", "") or "")
    return bool(observed) and observed == _canonical_digest(body)


def _contained(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    parent = root.resolve()
    return resolved == parent or parent in resolved.parents


def _file_binding(path: Path, *, relative_to: Path) -> dict[str, Any]:
    target = path.resolve(strict=True)
    root = relative_to.resolve()
    if not _contained(target, root):
        raise L6ShadowReplayError(f"derived_artifact_outside_w3:{target}")
    return {
        "artifact_ref": target.relative_to(root).as_posix(),
        "byte_length": target.stat().st_size,
        "sha256": _sha256_file(target),
    }


def _resolve_binding(root: Path, binding: Any, *, label: str) -> Path:
    if not isinstance(binding, Mapping):
        raise L6ShadowReplayError(f"{label}_binding_missing")
    ref = str(binding.get("artifact_ref") or "").strip()
    if not ref:
        raise L6ShadowReplayError(f"{label}_ref_missing")
    candidate = (root / ref).resolve()
    if not _contained(candidate, root):
        raise L6ShadowReplayError(f"{label}_outside_w2:{candidate}")
    if not candidate.is_file():
        raise L6ShadowReplayError(f"{label}_missing:{candidate}")
    if int(binding.get("byte_length") or -1) != candidate.stat().st_size:
        raise L6ShadowReplayError(f"{label}_length_mismatch:{candidate}")
    if str(binding.get("sha256") or "") != _sha256_file(candidate):
        raise L6ShadowReplayError(f"{label}_digest_mismatch:{candidate}")
    return candidate


def _verify_eval_package_seal(run_dir: Path) -> tuple[bool, list[str]]:
    seal_path = run_dir / "apps_rg_eval_package_seal.json"
    try:
        seal = _read_json(seal_path, label="eval_package_seal")
    except L6ShadowReplayError:
        return False, ["eval_package_seal_unreadable"]
    errors: list[str] = []
    if seal.get("schema_version") != "apps_eval.apps_rg_eval_package_seal.v1":
        errors.append("eval_package_seal_schema_mismatch")
    if seal.get("status") != "PASS":
        errors.append("eval_package_seal_not_passed")
    body = {key: value for key, value in seal.items() if key != "manifest_sha256"}
    if seal.get("manifest_sha256") != _canonical_digest(body):
        errors.append("eval_package_seal_manifest_digest_mismatch")
    artifacts = seal.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("eval_package_seal_artifacts_missing")
        artifacts = []
    seen_roles: set[str] = set()
    for row in artifacts:
        if not isinstance(row, Mapping):
            errors.append("eval_package_seal_artifact_not_object")
            continue
        role = str(row.get("artifact_role") or "")
        seen_roles.add(role)
        candidate = (run_dir / str(row.get("artifact_ref") or "")).resolve()
        if not _contained(candidate, run_dir):
            errors.append(f"eval_package_seal_artifact_outside_root:{role}")
            continue
        if not candidate.is_file():
            errors.append(f"eval_package_seal_artifact_missing:{role}")
            continue
        if row.get("sha256") != _sha256_file(candidate):
            errors.append(f"eval_package_seal_artifact_digest_mismatch:{role}")
        if row.get("byte_length") != candidate.stat().st_size:
            errors.append(f"eval_package_seal_artifact_length_mismatch:{role}")
    required_roles = {
        "eval_record",
        "scorecard_rows",
        "component_scorecards",
        "coverage_matrix",
        "regression_summary",
    }
    errors.extend(
        f"eval_package_seal_role_missing:{role}"
        for role in sorted(required_roles - seen_roles)
    )
    return not errors, errors


def _validate_w2(output_dir: Path, source: Path) -> dict[str, Any]:
    w2_dir = output_dir.parent / "w2"
    completion_path = w2_dir / W2_COMPLETION_FILENAME
    guard_path = w2_dir / W2_GUARD_FILENAME
    completion = _read_json(completion_path, label="w2_completion")
    guard = _read_json(guard_path, label="w2_guard")
    counters = guard.get("attempt_counters")
    counters = dict(counters) if isinstance(counters, Mapping) else {}

    eval_record_path = _resolve_binding(
        w2_dir, completion.get("eval_record"), label="w2_eval_record"
    )
    eval_seal_path = _resolve_binding(
        w2_dir, completion.get("eval_package_seal"), label="w2_eval_package_seal"
    )
    scorecard_rows_path = _resolve_binding(
        w2_dir, completion.get("scorecard_rows"), label="w2_scorecard_rows"
    )
    l6_handoff_path = _resolve_binding(
        w2_dir, completion.get("l6_handoff"), label="w2_l6_handoff"
    )
    supersession_path = _resolve_binding(
        w2_dir,
        completion.get("eval_package_supersession_manifest"),
        label="w2_eval_package_supersession_manifest",
    )
    supersession = _read_json(
        supersession_path,
        label="w2_eval_package_supersession_manifest",
    )
    seal_valid, seal_errors = _verify_eval_package_seal(eval_record_path.parent)
    record_id = str(completion.get("record_id") or "")
    checks = {
        "completion_schema_exact": completion.get("schema_version")
        == "apps_rg.apps_eval_replay_completion.v1",
        "completion_digest_valid": _semantic_digest_valid(completion),
        "completion_source_bound": completion.get("source_run_id") == source.name,
        "completion_pass": completion.get("status") == "PASS"
        and completion.get("scope_complete") is True,
        "completion_authorizes_w3": completion.get("w3_authorized") is True,
        "apps_eval_complete": completion.get("eval_execution_complete") is True,
        "apps_eval_release_blocked": completion.get("eval_verdict") == "fail"
        and completion.get("release_blocked") is True,
        "l6_handoff_only": completion.get("l6_handoff_emitted") is True
        and completion.get("l6_shadow_bridge_executed") is False,
        "record_id_bound": bool(record_id),
        "eval_seal_binding_exact": eval_seal_path
        == eval_record_path.parent / "apps_rg_eval_package_seal.json",
        "eval_package_seal_valid": seal_valid and not seal_errors,
        "supersession_schema_exact": supersession.get("schema_version")
        == W2_SUPERSESSION_SCHEMA,
        "supersession_digest_valid": _semantic_digest_valid(supersession),
        "supersession_pass": supersession.get("status") == "PASS"
        and supersession.get("authoritative_record_id") == record_id,
        "one_canonical_eval_package": supersession.get(
            "canonical_package_count"
        )
        == 1
        and supersession.get("canonical_package_ids") == [record_id]
        and eval_record_path.parent.name == record_id,
        "superseded_packages_recoverable": supersession.get(
            "destructive_delete_performed"
        )
        is False
        and supersession.get("packages_recoverable") is True,
        "guard_schema_exact": guard.get("schema_version")
        == "apps_rg.post_runtime_zero_provider_replay.v1",
        "guard_digest_valid": _semantic_digest_valid(guard),
        "guard_source_bound": guard.get("source_run_id") == source.name,
        "guard_pass": guard.get("status") == "PASS"
        and guard.get("source_unchanged") is True,
        "guard_completion_bound": guard.get("operation_completion_semantic_digest")
        == completion.get("semantic_digest"),
        "guard_zero_calls": REQUIRED_ZERO_ACTIVITY_COUNTERS.issubset(counters)
        and all(type(value) is int and value == 0 for value in counters.values()),
        "guard_activity_exact": guard.get("apps_eval_executed") is True
        and guard.get("l6_executed") is False
        and guard.get("uwg_operation_attempted") is False,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise L6ShadowReplayError("w2_evidence_invalid:" + ",".join(failed))
    return {
        "checks": checks,
        "completion": completion,
        "completion_path": completion_path,
        "guard": guard,
        "guard_path": guard_path,
        "eval_record_path": eval_record_path,
        "scorecard_rows_path": scorecard_rows_path,
        "l6_handoff_path": l6_handoff_path,
        "supersession": supersession,
        "supersession_path": supersession_path,
    }


def _dataclass_kwargs(cls: type[Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    names = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in names}


def _load_completed_eval_record(path: Path) -> Any:
    payload = _read_json(path, label="eval_record")
    # Lazy imports preserve the stdlib-only pre-guard module boundary.
    from apps_eval.contracts.models import (  # noqa: PLC0415
        CompletedEvalRecord,
        EvalRunMetadata,
        FixtureProvenance,
        RegressionFlywheelSummary,
        RegressionSummary,
        Scorecard,
    )

    scorecard_payload = payload.get("scorecard")
    regression_payload = payload.get("regression")
    if not isinstance(scorecard_payload, Mapping) or not isinstance(
        regression_payload, Mapping
    ):
        raise L6ShadowReplayError("eval_record_nested_contract_missing")
    kwargs = _dataclass_kwargs(CompletedEvalRecord, payload)
    kwargs["scorecard"] = Scorecard(
        **_dataclass_kwargs(Scorecard, scorecard_payload)
    )
    kwargs["regression"] = RegressionSummary(
        **_dataclass_kwargs(RegressionSummary, regression_payload)
    )
    run_metadata = payload.get("run_metadata")
    kwargs["run_metadata"] = EvalRunMetadata(
        **_dataclass_kwargs(
            EvalRunMetadata,
            run_metadata if isinstance(run_metadata, Mapping) else {},
        )
    )
    flywheel = payload.get("regression_flywheel")
    kwargs["regression_flywheel"] = RegressionFlywheelSummary(
        **_dataclass_kwargs(
            RegressionFlywheelSummary,
            flywheel if isinstance(flywheel, Mapping) else {},
        )
    )
    provenance = payload.get("fixture_provenance")
    kwargs["fixture_provenance"] = [
        FixtureProvenance(**_dataclass_kwargs(FixtureProvenance, item))
        for item in (provenance if isinstance(provenance, list) else [])
        if isinstance(item, Mapping)
    ]
    return CompletedEvalRecord(**kwargs)


def _emit_projection_bridge(
    record: Any,
    output_dir: Path,
    *,
    eval_record_path: Path,
    l6_handoff_path: Path,
) -> dict[str, str]:
    """Materialize an Apps RG-owned, advisory-only projection package."""

    output_dir.mkdir(parents=True, exist_ok=True)
    common = {
        "schema_version": "apps_rg.l6_shadow_bridge.v2",
        "record_id": str(getattr(record, "record_id", "") or ""),
        "eval_record_ref": Path(eval_record_path).as_posix(),
        "l6_handoff_ref": Path(l6_handoff_path).as_posix(),
        "deterministic_replay": True,
        "projection_consistency_only": True,
        "evidence_class": "CONTRACT_ONLY_ADVISORY",
        "independent_observation_required_for_bound_proof": True,
        "current_run_mutated": False,
        "direct_l4_write_attempted": False,
        "durable_write_attempted": False,
        "future_run_only": True,
        "readiness_decision": "ADVISORY_ONLY",
        "g28_audit_completeness": {"verdict": "NOT_APPLICABLE"},
        "g29_learning_firewall": {"verdict": "PASS"},
    }
    roles = (
        "l6_shadow_bridge",
        "projection_summary",
        "projection_scorecard",
        "projection_findings",
        "projection_gate_map",
        "projection_provenance",
        "projection_scope",
        "projection_determinism",
        "projection_advisory",
        "projection_manifest",
    )
    paths: dict[str, str] = {}
    for role in roles:
        payload = {**common, "artifact_role": role}
        path = output_dir / f"{role}.json"
        _write_semantic(path, payload)
        paths[role] = path.as_posix()
    return paths


def _source_ref(source: Path, path: Path | None) -> str:
    if path is None:
        return ""
    resolved = path.resolve()
    if not _contained(resolved, source):
        return ""
    return resolved.relative_to(source.resolve()).as_posix()


def _resolve_source_ref(
    ref: Any,
    *,
    source: Path,
    package_dir: Path,
    fallback_name: str,
) -> Path | None:
    text = str(ref or "").strip()
    candidates: list[Path] = []
    if text:
        raw = Path(text)
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend((source / raw, package_dir / raw, Path.cwd() / raw))
    candidates.append(package_dir / fallback_name)
    for candidate in candidates:
        resolved = candidate.resolve()
        if _contained(resolved, source) and resolved.is_file():
            return resolved
    return None


def _normal_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    raw = text.removeprefix("sha256:")
    if len(raw) != 64:
        return ""
    try:
        int(raw, 16)
    except ValueError:
        return ""
    return f"sha256:{raw}"


def _gate_pass(value: Any) -> bool:
    return isinstance(value, Mapping) and str(
        value.get("verdict") or value.get("status") or ""
    ).upper() == "PASS"


def _revalidate_observability_closure(
    *,
    closure: Mapping[str, Any],
    package: Mapping[str, Any],
    source: Path,
) -> list[str]:
    refs = closure.get("refs")
    digests = closure.get("artifact_digests")
    if not isinstance(refs, Mapping) or not isinstance(digests, Mapping):
        return ["observability_closure_artifact_map_missing"]
    gaps: list[str] = []
    recomputed: dict[str, str] = {}
    for name, ref in sorted(refs.items()):
        raw = Path(str(ref or ""))
        candidates = [raw] if raw.is_absolute() else [source / raw, Path.cwd() / raw]
        path = next(
            (
                item.resolve()
                for item in candidates
                if item.resolve().is_file() and _contained(item.resolve(), source)
            ),
            None,
        )
        if path is None:
            gaps.append(f"closure_artifact_missing_or_uncontained:{name}")
            continue
        actual = _sha256_file(path)
        recomputed[str(name)] = actual
        if str(digests.get(name) or "").lower() != actual.lower():
            gaps.append(f"closure_artifact_digest_mismatch:{name}")
    if {str(key) for key in digests} != set(recomputed):
        gaps.append("closure_artifact_set_mismatch")
    identity_fields = (
        "runtime_exhaust_bundle_id",
        "runtime_exhaust_bundle_digest",
        "parent_run_id",
        "child_run_id",
        "section_attempt_id",
        "microstep_contract_digest",
        "registry_digest",
    )
    for field in identity_fields:
        observed = str(closure.get(field) or "")
        expected = str(package.get(field) or "")
        if not observed or observed != expected:
            gaps.append(f"closure_identity_mismatch:{field}")
    seed = {
        "runtime_exhaust_bundle_id": str(
            closure.get("runtime_exhaust_bundle_id") or ""
        ),
        "runtime_exhaust_bundle_digest": _normal_sha256(
            closure.get("runtime_exhaust_bundle_digest")
        ),
        "parent_run_id": str(closure.get("parent_run_id") or ""),
        "child_run_id": str(closure.get("child_run_id") or ""),
        "section_attempt_id": str(closure.get("section_attempt_id") or ""),
        "microstep_contract_digest": str(
            closure.get("microstep_contract_digest") or ""
        ),
        "registry_digest": _normal_sha256(closure.get("registry_digest")),
        "checks": dict(closure.get("checks") or {}),
        "artifact_digests": recomputed,
    }
    if str(closure.get("closure_digest") or "").lower() != _canonical_digest(
        seed
    ).lower():
        gaps.append("observability_closure_digest_mismatch")
    return sorted(set(gaps))


def _lane_package(source: Path, lane_id: str, name: str) -> Path | None:
    candidates = (
        source / "lanes" / lane_id / name,
        source / "modular_r4" / "sections" / lane_id / name,
        source / lane_id / name,
    )
    return next((path.resolve() for path in candidates if path.is_file()), None)


def _write_independent_bindings(
    *,
    source: Path,
    output_dir: Path,
    record: Any,
    scorecard_rows: list[dict[str, Any]],
    scorecard_ref: str,
) -> dict[str, Any]:
    from apps_rg.runtime.local_shadow import (
        SEALED_APPS_RG_OBSERVATION_ORIGIN,
        build_independent_apps_eval_parity,
    )

    binding_dir = output_dir / "independent_bindings"
    binding_dir.mkdir(parents=True, exist_ok=True)
    lane_ids = sorted(
        {
            str(row.get("lane_id") or "").strip()
            for row in scorecard_rows
            if str(row.get("lane_id") or "").strip()
        }
    )
    bindings: list[dict[str, Any]] = []
    artifact_paths: dict[str, Path] = {}

    for lane_id in lane_ids:
        lane_rows = [
            row
            for row in scorecard_rows
            if row.get("required", True)
            and str(row.get("lane_id") or "") == lane_id
        ]
        v40_path = _lane_package(source, lane_id, "l6_v40_shadow_eval_package.json")
        legacy_path = _lane_package(source, lane_id, "l6_shadow_eval_package.json")
        parity: dict[str, Any] = {}
        proof_gaps: list[str] = []
        observation_count = 0

        if v40_path is None:
            status = "LEGACY_PACKAGE_ADVISORY" if legacy_path else "MISSING_PACKAGE"
            proof_gaps.append(
                "governed_v40_package_required_for_independent_binding"
            )
            binding = {
                "section_id": lane_id,
                "binding_status": status,
                "source_evidence_status": "UNAVAILABLE_SOURCE_EVIDENCE",
                "source_evidence_reason_codes": [
                    "GOVERNED_V40_PACKAGE_MISSING"
                ],
                "evidence_class": "CONTRACT_ONLY_ADVISORY",
                "l6_package_tier": "legacy" if legacy_path else "missing",
                "l6_package_ref": _source_ref(source, legacy_path),
                "l6_package_sha256": _sha256_file(legacy_path)
                if legacy_path
                else "",
                "apps_eval_row_count": len(lane_rows),
                "l6_observation_row_count": 0,
                "independent_observations": False,
                "proof_gaps": proof_gaps,
                "package_immutable": True,
                "current_run_mutation_assertion": False,
                "direct_l4_write_assertion": False,
                "durable_write_assertion": False,
                "future_run_only": True,
            }
        else:
            package = _read_json(v40_path, label=f"{lane_id}_v40_package")
            observation_path = _resolve_source_ref(
                package.get("l6_microstep_observations_ref"),
                source=source,
                package_dir=v40_path.parent,
                fallback_name="l6_microstep_observations.jsonl",
            )
            closure_path = _resolve_source_ref(
                package.get("l6_observability_closure_receipt_ref"),
                source=source,
                package_dir=v40_path.parent,
                fallback_name="l6_observability_closure_receipt.json",
            )
            closure = (
                _read_json(closure_path, label=f"{lane_id}_observability_closure")
                if closure_path
                else {}
            )
            source_evidence_reason_codes = []
            if observation_path is None:
                source_evidence_reason_codes.append(
                    "L6_MICROSTEP_OBSERVATIONS_MISSING"
                )
            if closure_path is None:
                source_evidence_reason_codes.append(
                    "L6_OBSERVABILITY_CLOSURE_MISSING"
                )
            source_evidence_status = (
                "AVAILABLE_SOURCE_EVIDENCE"
                if not source_evidence_reason_codes
                else "UNAVAILABLE_SOURCE_EVIDENCE"
            )
            package_checks = {
                "v40_schema": package.get("schema_version")
                == "apps_rg.l6_v40_shadow_eval.v2",
                "section_id_bound": package.get("section_id") == lane_id,
                "valid_v40_shadow_exhaust": package.get(
                    "valid_v40_shadow_exhaust"
                )
                is True,
                "l5_certification_valid": package.get("l5_certification_valid")
                is True,
                "readiness_scorable": str(package.get("readiness_decision") or "")
                in {"READY_FOR_6B", "PARTIAL_BUT_SCORABLE", "READY_FOR_EVAL"},
                "g28_pass": _gate_pass(package.get("g28_audit_completeness")),
                "g29_pass": _gate_pass(package.get("g29_learning_firewall")),
                "observability_closure_pass": str(
                    closure.get("observability_closure_status")
                    or closure.get("closure_status")
                    or ""
                )
                == "PASS",
                "observations_present": observation_path is not None,
                "closure_present": closure_path is not None,
                "apps_eval_rows_present": bool(lane_rows),
            }
            proof_gaps.extend(
                name for name, passed in package_checks.items() if not passed
            )
            if closure_path:
                proof_gaps.extend(
                    _revalidate_observability_closure(
                        closure=closure,
                        package=package,
                        source=source,
                    )
                )
            observations: list[dict[str, Any]] = []
            if observation_path:
                observations = [
                    row
                    for row in _read_jsonl(
                        observation_path, label=f"{lane_id}_l6_observations"
                    )
                    if row.get("required", True)
                    and str(row.get("lane_id") or "") == lane_id
                ]
                observation_count = len(observations)
                parity = build_independent_apps_eval_parity(
                    run_id=str(record.record_id or ""),
                    runtime_exhaust_bundle_id=str(
                        package.get("runtime_exhaust_bundle_id") or ""
                    ),
                    microstep_contract_digest=str(
                        package.get("microstep_contract_digest") or ""
                    ),
                    apps_eval_scorecard_ref=scorecard_ref,
                    l6_observation_ref=_source_ref(source, observation_path),
                    apps_eval_rows=lane_rows,
                    l6_observations=observations,
                    observation_origin=SEALED_APPS_RG_OBSERVATION_ORIGIN,
                    expected_observation_bundle_id=str(
                        package.get("runtime_exhaust_bundle_id") or ""
                    ),
                    parent_run_id=str(package.get("parent_run_id") or ""),
                    child_run_id=str(package.get("child_run_id") or ""),
                    section_attempt_id=str(
                        package.get("section_attempt_id") or ""
                    ),
                    eval_record_id=str(record.record_id or ""),
                    snapshot_digest=str(record.snapshot_digest or ""),
                    registry_digest=str(
                        record.registry_digest
                        or package.get("registry_digest")
                        or ""
                    ),
                    source_run_root=source.as_posix(),
                    repository_root=Path(__file__).resolve().parents[3].as_posix(),
                    compare_artifact_digests=True,
                )
                parity_path = binding_dir / f"{lane_id}.independent_parity.json"
                _atomic_write_json(parity_path, parity)
                artifact_paths[f"{lane_id}_independent_parity"] = parity_path
                if parity.get("grain_parity_status") != "PASS":
                    proof_gaps.append("independent_grain_parity_failed")
            proof_gaps = sorted(set(proof_gaps))
            bound = not proof_gaps and parity.get("grain_parity_status") == "PASS"
            binding = {
                "section_id": lane_id,
                "binding_status": "BOUND_PASS" if bound else "PARITY_FAIL",
                "source_evidence_status": source_evidence_status,
                "source_evidence_reason_codes": sorted(
                    source_evidence_reason_codes
                ),
                "evidence_class": "APPS_EVAL_BOUND_PROOF"
                if bound
                else "CONTRACT_ONLY_ADVISORY",
                "l6_package_tier": "v40",
                "l6_package_ref": _source_ref(source, v40_path),
                "l6_package_sha256": _sha256_file(v40_path),
                "l6_observability_closure_ref": _source_ref(
                    source, closure_path
                ),
                "l6_observability_closure_sha256": _sha256_file(closure_path)
                if closure_path
                else "",
                "l6_microstep_observations_ref": _source_ref(
                    source, observation_path
                ),
                "l6_microstep_observations_sha256": _sha256_file(
                    observation_path
                )
                if observation_path
                else "",
                "independent_parity_ref": (
                    f"independent_bindings/{lane_id}.independent_parity.json"
                    if parity
                    else ""
                ),
                "apps_eval_row_count": len(lane_rows),
                "l6_observation_row_count": observation_count,
                "package_checks": package_checks,
                "independent_observations": bool(
                    parity.get("independent_observations") is True
                ),
                "proof_gaps": proof_gaps,
                "package_immutable": True,
                "current_run_mutation_assertion": False,
                "direct_l4_write_assertion": False,
                "durable_write_assertion": False,
                "future_run_only": True,
            }
        binding_path = binding_dir / f"{lane_id}.binding.json"
        _atomic_write_json(binding_path, binding)
        artifact_paths[f"{lane_id}_binding"] = binding_path
        bindings.append(binding)

    expected_set = set(EXPECTED_LANES)
    observed_set = set(lane_ids)
    all_expected_sections_inspected = observed_set == expected_set
    all_bound = all_expected_sections_inspected and bool(bindings) and all(
        item.get("binding_status") == "BOUND_PASS" for item in bindings
    )
    summary = {
        "sections_total": len(bindings),
        "sections_bound": sum(
            item.get("binding_status") == "BOUND_PASS" for item in bindings
        ),
        "sections_v40": sum(
            item.get("l6_package_tier") == "v40" for item in bindings
        ),
        "sections_legacy": sum(
            item.get("l6_package_tier") == "legacy" for item in bindings
        ),
        "sections_missing": sum(
            item.get("l6_package_tier") == "missing" for item in bindings
        ),
        "sections_source_evidence_available": sum(
            item.get("source_evidence_status") == "AVAILABLE_SOURCE_EVIDENCE"
            for item in bindings
        ),
        "sections_source_evidence_unavailable": sum(
            item.get("source_evidence_status") == "UNAVAILABLE_SOURCE_EVIDENCE"
            for item in bindings
        ),
        "sections_observability_closed": sum(
            item.get("binding_status") == "BOUND_PASS" for item in bindings
        ),
        "apps_eval_rows_seen": sum(
            int(item.get("apps_eval_row_count") or 0) for item in bindings
        ),
        "l6_observation_rows_seen": sum(
            int(item.get("l6_observation_row_count") or 0) for item in bindings
        ),
        "apps_eval_rows_bound": all_bound,
        "grain_parity_status": "PASS" if all_bound else "FAIL",
        "shadow_observability_verdict": "pass" if all_bound else "fail",
        "expected_lane_ids": list(EXPECTED_LANES),
        "observed_lane_ids": lane_ids,
        "missing_lane_ids": sorted(expected_set - observed_set),
        "unexpected_lane_ids": sorted(observed_set - expected_set),
        "binding_status_by_section": {
            str(item["section_id"]): str(item["binding_status"])
            for item in bindings
        },
        "source_evidence_status_by_section": {
            str(item["section_id"]): str(item["source_evidence_status"])
            for item in bindings
        },
    }
    payload: dict[str, Any] = {
        "schema_version": W3_BINDINGS_SCHEMA,
        "eval_record_id": str(record.record_id or ""),
        "eval_record_ref": scorecard_ref,
        "summary": summary,
        "bindings": bindings,
        "alignment_source": "independent_persisted_observations",
        "projection_consistency_only": False,
        "current_run_mutation_assertion": False,
        "direct_l4_write_assertion": False,
        "durable_write_assertion": False,
        "future_run_only": True,
    }
    payload["semantic_digest"] = _canonical_digest(payload)
    bindings_path = _atomic_write_json(output_dir / W3_BINDINGS_FILENAME, payload)
    artifact_paths["l6_section_apps_eval_bindings"] = bindings_path

    closure_checks = {
        "all_expected_sections_inspected": all_expected_sections_inspected,
        "independent_observation_boundary_explicit": all(
            item.get("evidence_class")
            in {"APPS_EVAL_BOUND_PROOF", "CONTRACT_ONLY_ADVISORY"}
            for item in bindings
        ),
        "no_legacy_bound_proof": all(
            item.get("l6_package_tier") != "legacy"
            or item.get("evidence_class") != "APPS_EVAL_BOUND_PROOF"
            for item in bindings
        ),
        "source_evidence_availability_classified": all(
            item.get("source_evidence_status")
            in {
                "AVAILABLE_SOURCE_EVIDENCE",
                "UNAVAILABLE_SOURCE_EVIDENCE",
            }
            for item in bindings
        ),
        "unavailable_source_evidence_never_bound": all(
            item.get("source_evidence_status")
            != "UNAVAILABLE_SOURCE_EVIDENCE"
            or item.get("binding_status") != "BOUND_PASS"
            for item in bindings
        ),
        "source_packages_immutable": all(
            item.get("package_immutable") is True for item in bindings
        ),
        "no_current_run_mutation": all(
            item.get("current_run_mutation_assertion") is False
            for item in bindings
        ),
        "no_direct_l4_write": all(
            item.get("direct_l4_write_assertion") is False for item in bindings
        ),
        "no_durable_write": all(
            item.get("durable_write_assertion") is False for item in bindings
        ),
        "all_required_sections_bound": all_bound,
    }
    proof_failed = sorted(
        name for name, passed in closure_checks.items() if not passed
    )
    closure: dict[str, Any] = {
        "schema_version": W3_BINDING_CLOSURE_SCHEMA,
        "eval_record_id": str(record.record_id or ""),
        "l6_execution_complete": True,
        "binding_closure_status": "PASS" if all_bound else "FAIL",
        "shadow_observability_verdict": "pass" if all_bound else "fail",
        "release_blocked": not all_bound,
        "checks": closure_checks,
        "failed_checks": proof_failed,
        "l6_section_apps_eval_bindings_ref": W3_BINDINGS_FILENAME,
        "evidence_class": "APPS_EVAL_BOUND_PROOF"
        if all_bound
        else "CONTRACT_ONLY_ADVISORY",
        "apps_eval_rows_bound": all_bound,
        "independent_observations": all_bound,
        "unavailable_source_evidence_count": sum(
            item.get("source_evidence_status") == "UNAVAILABLE_SOURCE_EVIDENCE"
            for item in bindings
        ),
        "unavailable_source_evidence_section_ids": sorted(
            str(item["section_id"])
            for item in bindings
            if item.get("source_evidence_status")
            == "UNAVAILABLE_SOURCE_EVIDENCE"
        ),
        "current_run_mutation_assertion": False,
        "direct_l4_write_assertion": False,
        "durable_write_assertion": False,
        "future_run_only": True,
    }
    closure["semantic_digest"] = _canonical_digest(closure)
    closure_path = _atomic_write_json(
        output_dir / W3_BINDING_CLOSURE_FILENAME, closure
    )
    artifact_paths["l6_apps_eval_binding_closure"] = closure_path
    return {
        "payload": payload,
        "summary": summary,
        "closure": closure,
        "artifact_paths": artifact_paths,
    }


def _emit_calibration_status(
    *,
    output_dir: Path,
    source_run_id: str,
    record_id: str,
) -> tuple[dict[str, Any], Path]:
    """Record why judge-vs-human calibration is intentionally not measured."""

    payload: dict[str, Any] = {
        "schema_version": W3_CALIBRATION_SCHEMA,
        "status": "PASS",
        "wave": "W3",
        "source_run_id": source_run_id,
        "eval_record_id": record_id,
        "calibration_status": "NOT_MEASURED",
        "human_labels_present": False,
        "n_calibration_samples": 0,
        "spearman_rho": None,
        "p_value": None,
        "informational_only": True,
        "required_for_exit": False,
        "release_authority_effect": "NONE",
        "reason_code": "HUMAN_LABELS_NOT_PROVIDED_TO_ARTIFACT_REPLAY",
        "human_grade_inference_attempted": False,
        "provider_execution": False,
        "judge_execution": False,
        "uwg_operation_attempted": False,
        "future_run_only": True,
    }
    path = _write_semantic(output_dir / W3_CALIBRATION_FILENAME, payload)
    return _read_json(path, label="w3_calibration_status"), path


def _emit_package_seal(
    *,
    output_dir: Path,
    record_id: str,
    artifacts: Mapping[str, Path],
) -> Path:
    rows: list[dict[str, Any]] = []
    for role, path in sorted(artifacts.items()):
        binding = _file_binding(path, relative_to=output_dir)
        rows.append({"artifact_role": role, **binding})
    body: dict[str, Any] = {
        "schema_version": W3_PACKAGE_SEAL_SCHEMA,
        "status": "PASS",
        "record_id": record_id,
        "artifact_count": len(rows),
        "artifacts": rows,
        "emission_phase": "POST_EMISSION_REOPENED_AND_VALIDATED",
    }
    seal = {**body, "manifest_sha256": _canonical_digest(body)}
    return _atomic_write_json(output_dir / W3_PACKAGE_SEAL_FILENAME, seal)


def _verify_package_seal(
    output_dir: Path, seal_path: Path
) -> tuple[bool, list[str], dict[str, str]]:
    seal = _read_json(seal_path, label="w3_package_seal")
    errors: list[str] = []
    body = {key: value for key, value in seal.items() if key != "manifest_sha256"}
    if seal.get("schema_version") != W3_PACKAGE_SEAL_SCHEMA:
        errors.append("w3_package_seal_schema_mismatch")
    if seal.get("status") != "PASS":
        errors.append("w3_package_seal_not_passed")
    if seal.get("manifest_sha256") != _canonical_digest(body):
        errors.append("w3_package_seal_manifest_digest_mismatch")
    artifacts = seal.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("w3_package_seal_artifacts_missing")
        artifacts = []
    observed: dict[str, str] = {}
    seen_roles: set[str] = set()
    for row in artifacts:
        if not isinstance(row, Mapping):
            errors.append("w3_package_seal_artifact_not_object")
            continue
        role = str(row.get("artifact_role") or "")
        if role in seen_roles:
            errors.append(f"w3_package_seal_duplicate_role:{role}")
        seen_roles.add(role)
        path = (output_dir / str(row.get("artifact_ref") or "")).resolve()
        if not _contained(path, output_dir):
            errors.append(f"w3_package_seal_artifact_outside_root:{role}")
            continue
        if not path.is_file():
            errors.append(f"w3_package_seal_artifact_missing:{role}")
            continue
        digest = _sha256_file(path)
        observed[role] = digest
        if row.get("sha256") != digest:
            errors.append(f"w3_package_seal_artifact_digest_mismatch:{role}")
        if row.get("byte_length") != path.stat().st_size:
            errors.append(f"w3_package_seal_artifact_length_mismatch:{role}")
    if seal.get("artifact_count") != len(artifacts):
        errors.append("w3_package_seal_artifact_count_mismatch")
    required_roles = {
        "projection_l6_shadow_bridge",
        "l6_section_apps_eval_bindings",
        "l6_apps_eval_binding_closure",
        "l6_judge_human_calibration_status",
        *(f"{lane}_binding" for lane in EXPECTED_LANES),
    }
    errors.extend(
        f"w3_package_seal_role_missing:{role}"
        for role in sorted(required_roles - seen_roles)
    )
    return not errors, errors, observed


def _execute_once(
    *,
    source: Path,
    output_dir: Path,
    w2: Mapping[str, Any],
) -> dict[str, Any]:
    record = _load_completed_eval_record(w2["eval_record_path"])
    if str(record.record_id or "") != str(w2["completion"].get("record_id") or ""):
        raise L6ShadowReplayError("eval_record_id_w2_completion_mismatch")
    scorecard_rows = _read_jsonl(
        w2["scorecard_rows_path"], label="sealed_scorecard_rows"
    )
    if _canonical_digest(scorecard_rows) != _canonical_digest(
        list(record.scorecard.scorecard_rows or [])
    ):
        raise L6ShadowReplayError("eval_record_scorecard_rows_mismatch")

    projection_dir = output_dir / "projection"
    projection_paths = _emit_projection_bridge(
        record,
        projection_dir,
        eval_record_path=w2["eval_record_path"],
        l6_handoff_path=w2["l6_handoff_path"],
    )
    projection_artifacts = {
        f"projection_{role}": Path(path).resolve()
        for role, path in projection_paths.items()
    }
    bridge_path = projection_artifacts["projection_l6_shadow_bridge"]
    bridge = _read_json(bridge_path, label="projection_l6_shadow_bridge")
    projection_checks = {
        "schema_exact": bridge.get("schema_version")
        == "apps_eval.l6_shadow_bridge.v2",
        "record_id_bound": bridge.get("record_id") == record.record_id,
        "deterministic_replay": bridge.get("deterministic_replay") is True,
        "projection_consistency_only": bridge.get("projection_consistency_only")
        is True,
        "independent_proof_not_claimed": bridge.get("evidence_class")
        == "CONTRACT_ONLY_ADVISORY"
        and bridge.get("independent_observation_required_for_bound_proof") is True,
        "no_current_run_mutation": bridge.get("current_run_mutated") is False,
        "no_direct_l4_write": bridge.get("direct_l4_write_attempted") is False,
        "no_durable_write": bridge.get("durable_write_attempted") is False,
        "future_run_only": bridge.get("future_run_only") is True,
    }
    projection_failed = sorted(
        name for name, passed in projection_checks.items() if not passed
    )
    if projection_failed:
        raise L6ShadowReplayError(
            "projection_bridge_invalid:" + ",".join(projection_failed)
        )

    bindings = _write_independent_bindings(
        source=source,
        output_dir=output_dir,
        record=record,
        scorecard_rows=scorecard_rows,
        scorecard_ref=w2["scorecard_rows_path"].as_posix(),
    )
    calibration, calibration_path = _emit_calibration_status(
        output_dir=output_dir,
        source_run_id=source.name,
        record_id=str(record.record_id or ""),
    )
    calibration_checks = {
        "schema_exact": calibration.get("schema_version")
        == W3_CALIBRATION_SCHEMA,
        "semantic_digest_valid": _semantic_digest_valid(calibration),
        "not_measured": calibration.get("calibration_status")
        == "NOT_MEASURED",
        "no_human_labels": calibration.get("human_labels_present") is False
        and calibration.get("n_calibration_samples") == 0,
        "metrics_absent": calibration.get("spearman_rho") is None
        and calibration.get("p_value") is None,
        "informational_only": calibration.get("informational_only") is True
        and calibration.get("required_for_exit") is False
        and calibration.get("release_authority_effect") == "NONE",
        "no_human_grade_inference": calibration.get(
            "human_grade_inference_attempted"
        )
        is False,
    }
    calibration_failed = sorted(
        name for name, passed in calibration_checks.items() if not passed
    )
    if calibration_failed:
        raise L6ShadowReplayError(
            "w3_calibration_status_invalid:" + ",".join(calibration_failed)
        )
    artifacts = {
        **projection_artifacts,
        **bindings["artifact_paths"],
        "l6_judge_human_calibration_status": calibration_path,
    }
    seal_path = _emit_package_seal(
        output_dir=output_dir,
        record_id=record.record_id,
        artifacts=artifacts,
    )
    seal_valid, seal_errors, artifact_digests = _verify_package_seal(
        output_dir, seal_path
    )
    if not seal_valid:
        raise L6ShadowReplayError(
            "w3_package_seal_invalid:" + ",".join(seal_errors)
        )
    return {
        "record": record,
        "bridge": bridge,
        "bridge_path": bridge_path,
        "projection_checks": projection_checks,
        "bindings": bindings,
        "calibration": calibration,
        "calibration_path": calibration_path,
        "calibration_checks": calibration_checks,
        "seal_path": seal_path,
        "seal_artifact_digests": artifact_digests,
    }


def emit_w3_l6_shadow_replay(
    *,
    source_run: Path | str,
    output_dir: Path | str,
    fault_injector: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    """Execute and seal W3 twice without running Apps Eval, judges, or UWG."""

    source = Path(source_run).resolve(strict=True)
    output = Path(output_dir).resolve()
    if _contained(output, source):
        raise L6ShadowReplayError("W3 output cannot be inside source run")
    w2 = _validate_w2(output, source)

    def _execute(attempt: int) -> dict[str, Any]:
        try:
            if fault_injector is not None:
                fault_injector("L6_SHADOW_OBSERVABILITY", attempt)
            return _execute_once(source=source, output_dir=output, w2=w2)
        except Exception as exc:
            evidence = _emit_stage_failure(
                output=output,
                source_run_id=source.name,
                exc=exc,
                attempt=attempt,
            )
            raise L6ShadowReplayError(
                "l6_shadow_stage_failed:"
                f"{type(exc).__name__}:{exc}:"
                f"receipt={evidence['error_receipt'].as_posix()}"
            ) from exc

    first = _execute(1)
    first_seal_sha = _sha256_file(first["seal_path"])
    first_artifact_digests = dict(first["seal_artifact_digests"])
    second = _execute(2)
    second_seal_sha = _sha256_file(second["seal_path"])
    second_artifact_digests = dict(second["seal_artifact_digests"])
    resume_path = _emit_stage_resume(
        output=output,
        source_run_id=source.name,
        w2=w2,
    )

    bindings = second["bindings"]
    summary = bindings["summary"]
    closure = bindings["closure"]
    bridge = second["bridge"]
    calibration = second["calibration"]
    observed_lanes = set(summary.get("observed_lane_ids") or [])
    checks = {
        "w2_evidence_validated": all(w2["checks"].values()),
        "l6_projection_executed": bool(second["bridge_path"].is_file()),
        "l6_projection_advisory_only": bridge.get("projection_consistency_only")
        is True
        and bridge.get("evidence_class") == "CONTRACT_ONLY_ADVISORY",
        "independent_binding_executed": bindings["artifact_paths"][
            "l6_section_apps_eval_bindings"
        ].is_file(),
        "all_expected_lanes_inspected": observed_lanes == set(EXPECTED_LANES),
        "all_lane_binding_receipts_emitted": all(
            f"{lane}_binding" in bindings["artifact_paths"]
            for lane in EXPECTED_LANES
        ),
        "source_evidence_availability_explicit": (
            int(summary.get("sections_source_evidence_available") or 0)
            + int(summary.get("sections_source_evidence_unavailable") or 0)
            == len(EXPECTED_LANES)
            and set(
                (summary.get("source_evidence_status_by_section") or {}).values()
            )
            <= {
                "AVAILABLE_SOURCE_EVIDENCE",
                "UNAVAILABLE_SOURCE_EVIDENCE",
            }
        ),
        "unavailable_source_evidence_never_bound": bindings["closure"]
        .get("checks", {})
        .get("unavailable_source_evidence_never_bound")
        is True,
        "calibration_status_explicit": all(
            second["calibration_checks"].values()
        )
        and calibration.get("calibration_status") == "NOT_MEASURED"
        and calibration.get("human_labels_present") is False
        and calibration.get("n_calibration_samples") == 0
        and calibration.get("informational_only") is True,
        "shadow_verdict_explicit": closure.get("shadow_observability_verdict")
        in {"pass", "fail"},
        "release_state_explicit": closure.get("release_blocked")
        is (closure.get("shadow_observability_verdict") == "fail"),
        "no_false_bound_proof": (
            closure.get("evidence_class") == "APPS_EVAL_BOUND_PROOF"
            and closure.get("apps_eval_rows_bound") is True
        )
        or (
            closure.get("evidence_class") == "CONTRACT_ONLY_ADVISORY"
            and closure.get("apps_eval_rows_bound") is False
        ),
        "package_sealed": second["seal_path"].is_file(),
        "repeated_replay_seal_stable": first_seal_sha == second_seal_sha,
        "repeated_replay_artifact_bytes_stable": first_artifact_digests
        == second_artifact_digests,
        "observer_law_preserved": bridge.get("current_run_mutated") is False
        and bridge.get("direct_l4_write_attempted") is False
        and bridge.get("durable_write_attempted") is False
        and bridge.get("future_run_only") is True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    shadow_verdict = str(closure.get("shadow_observability_verdict") or "fail")
    release_blocked = bool(
        w2["completion"].get("release_blocked") is True
        or shadow_verdict != "pass"
    )
    completion: dict[str, Any] = {
        "schema_version": W3_COMPLETION_SCHEMA,
        "wave": "W3",
        "status": "PASS" if not failed else "BLOCKED",
        "scope_complete": not failed,
        "w4_authorized": not failed,
        "source_run_id": source.name,
        "record_id": str(second["record"].record_id or ""),
        "l6_execution_complete": True,
        "l6_shadow_observability_verdict": shadow_verdict,
        "binding_closure_status": closure.get("binding_closure_status"),
        "release_blocked": release_blocked,
        "product_authorized": False,
        "pipeline_complete": False,
        "projection_consistency_only": True,
        "alignment_source": "independent_persisted_observations",
        "apps_eval_rows_bound": bool(closure.get("apps_eval_rows_bound") is True),
        "evidence_class": str(closure.get("evidence_class") or ""),
        "calibration_status": calibration["calibration_status"],
        "human_labels_present": calibration["human_labels_present"],
        "n_calibration_samples": calibration["n_calibration_samples"],
        "calibration_informational_only": calibration["informational_only"],
        "calibration_required_for_exit": calibration["required_for_exit"],
        "projection_readiness_decision": str(
            bridge.get("readiness_decision") or ""
        ),
        "projection_g28_verdict": str(
            (bridge.get("g28_audit_completeness") or {}).get("verdict") or ""
        ),
        "projection_g29_verdict": str(
            (bridge.get("g29_learning_firewall") or {}).get("verdict") or ""
        ),
        "section_summary": summary,
        "determinism_replay": {
            "execution_count": 2,
            "first_package_seal_sha256": first_seal_sha,
            "second_package_seal_sha256": second_seal_sha,
            "package_seal_bytes_stable": first_seal_sha == second_seal_sha,
            "artifact_bytes_stable": first_artifact_digests
            == second_artifact_digests,
        },
        "w3_package_seal": _file_binding(
            second["seal_path"], relative_to=output
        ),
        "l6_shadow_bridge": _file_binding(
            second["bridge_path"], relative_to=output
        ),
        "l6_section_apps_eval_bindings": _file_binding(
            bindings["artifact_paths"]["l6_section_apps_eval_bindings"],
            relative_to=output,
        ),
        "l6_apps_eval_binding_closure": _file_binding(
            bindings["artifact_paths"]["l6_apps_eval_binding_closure"],
            relative_to=output,
        ),
        "l6_judge_human_calibration_status": _file_binding(
            second["calibration_path"],
            relative_to=output,
        ),
        "stage_resume_receipt": (
            _file_binding(resume_path, relative_to=output)
            if resume_path is not None
            else None
        ),
        "w2_completion_ref": w2["completion_path"].as_posix(),
        "w2_completion_semantic_digest": w2["completion"]["semantic_digest"],
        "w2_guard_ref": w2["guard_path"].as_posix(),
        "w2_guard_semantic_digest": w2["guard"]["semantic_digest"],
        "w2_eval_package_supersession_ref": w2[
            "supersession_path"
        ].as_posix(),
        "w2_eval_package_supersession_semantic_digest": w2["supersession"][
            "semantic_digest"
        ],
        "eval_record_ref": w2["eval_record_path"].as_posix(),
        "eval_record_sha256": _sha256_file(w2["eval_record_path"]),
        "current_run_mutated": False,
        "direct_l4_write_attempted": False,
        "durable_write_attempted": False,
        "future_run_only": True,
        "checks": checks,
        "failed_checks": failed,
    }
    completion["semantic_digest"] = _canonical_digest(completion)
    _atomic_write_json(output / W3_COMPLETION_FILENAME, completion)
    return {
        "completion": completion,
        "activity": {
            "apps_eval_executed": False,
            "l6_executed": True,
            "uwg_operation_attempted": False,
        },
        "record_id": completion["record_id"],
        "w3_package_seal_path": second["seal_path"].as_posix(),
        "l6_shadow_bridge_path": second["bridge_path"].as_posix(),
        "l6_bindings_path": bindings["artifact_paths"][
            "l6_section_apps_eval_bindings"
        ].as_posix(),
        "l6_binding_closure_path": bindings["artifact_paths"][
            "l6_apps_eval_binding_closure"
        ].as_posix(),
        "l6_calibration_status_path": second["calibration_path"].as_posix(),
    }


__all__ = [
    "EXPECTED_LANES",
    "L6ShadowReplayError",
    "W3_CALIBRATION_FILENAME",
    "W3_CALIBRATION_SCHEMA",
    "W3_COMPLETION_FILENAME",
    "W3_COMPLETION_SCHEMA",
    "W3_ERROR_RECEIPT_SCHEMA",
    "W3_ERROR_SPAN_SCHEMA",
    "W3_PACKAGE_SEAL_FILENAME",
    "W3_PACKAGE_SEAL_SCHEMA",
    "W3_RESUME_RECEIPT_SCHEMA",
    "emit_w3_l6_shadow_replay",
]
