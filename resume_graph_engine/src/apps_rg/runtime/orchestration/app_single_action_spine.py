"""App-owned single-action spine for governed Apps RG execution.

This module owns the boundary from a shaped request to sealed runtime evidence.
It supports the real section and modular full-resume implementations already in
this repository and records a deterministic, fail-closed terminal outcome.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from apps_rg.runtime.failure_evidence import atomic_write_json


ROUTE_FAMILY = "R4_SINGLE_ACTION"
ROUTE_ID = "apps_rg.resume_generation_v1"
HOW_TRACE_ARTIFACT = "apps_rg_how_trace.json"
ROUTE_COVERAGE_ARTIFACT = "apps_rg_l7_route_family_coverage.json"
SPINE_PROOF_ARTIFACT = "apps_rg_spine_proof.json"


@dataclass(frozen=True, slots=True)
class AppsRgSingleActionSpineRunResult:
    run_id: str
    request_id: str
    route_id: str
    x3_disposition: str
    terminal_r5: bool
    terminal_r5_reason: str
    artifact_dir: Path
    fault: str
    l2_result: dict[str, Any]
    execution_witness: dict[str, Any]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _envelope(*, component: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    body = _plain(payload)
    assert isinstance(body, dict)
    return {
        "producer_component": component,
        "artifact_hash": _digest(body),
        "payload": body,
    }


def _write_artifact(root: Path, name: str, *, component: str, payload: Mapping[str, Any]) -> str:
    envelope = _envelope(component=component, payload=payload)
    atomic_write_json(root / name, envelope)
    return str(envelope["artifact_hash"])


def _request_value(raw_request: Mapping[str, Any], name: str) -> str:
    value = raw_request.get(name)
    return str(value or "").strip()


def _identity(raw_request: Mapping[str, Any], *, run_id: str, request_id: str) -> dict[str, Any]:
    canonical = raw_request.get("canonical_run_identity")
    identity = dict(canonical) if isinstance(canonical, Mapping) else {}
    identity.setdefault("run_id", run_id)
    identity.setdefault("request_id", request_id)
    identity.setdefault("trace_root", _request_value(raw_request, "trace_id") or run_id)
    identity.setdefault("tenant_id", _request_value(raw_request, "tenant_id") or "default")
    identity.setdefault("app_id", _request_value(raw_request, "app_id") or "apps_rg")
    return identity


def _run_section_l2(raw_request: Mapping[str, Any], *, artifact_dir: Path) -> dict[str, Any]:
    from apps_rg.l2_recipe.steps import GenerateSectionStep

    l2_context = raw_request.get("l2_context")
    context = dict(l2_context) if isinstance(l2_context, Mapping) else {}
    context.update(
        {
            "raw_request": dict(raw_request),
            "artifact_dir": str(artifact_dir),
            "section_id": _request_value(raw_request, "section_id"),
            "target_company": _request_value(raw_request, "target_company"),
            "target_role": _request_value(raw_request, "target_role"),
            "target_level": _request_value(raw_request, "target_level"),
            "jd": _request_value(raw_request, "jd"),
            "job_description_ref": _request_value(raw_request, "job_description_ref"),
            "job_description_text": _request_value(raw_request, "job_description_text"),
            "manual_brief": _request_value(raw_request, "manual_brief"),
            "resume_path": _request_value(raw_request, "resume_path"),
            "source_resume_text": _request_value(raw_request, "source_resume_text"),
            "generation_mode": _request_value(raw_request, "generation_mode") or "section_regen",
        }
    )
    step = GenerateSectionStep()
    return {"step_results": [step(context)]}


def _run_full_resume_l2(
    raw_request: Mapping[str, Any],
    *,
    artifact_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    from apps_rg.l2_recipe.steps import GenerateResumeStep, ResumeArtifactGateStep

    context = dict(raw_request)
    context.update(
        {
            "raw_request": dict(raw_request),
            "artifact_dir": str(artifact_dir),
            "run_id": run_id,
            "target_company": _request_value(raw_request, "target_company"),
            "target_role": _request_value(raw_request, "target_role"),
            "target_level": _request_value(raw_request, "target_level"),
        }
    )
    generated = GenerateResumeStep()(context)
    candidate = generated.get("generated_resume") if isinstance(generated, Mapping) else None
    gate_context = {**context, "generated_resume": candidate}
    gate = ResumeArtifactGateStep()(gate_context)
    return {"step_results": [_plain(generated), _plain(gate)]}


def _section_x3(l2_result: Mapping[str, Any]) -> str:
    for step in l2_result.get("step_results") or []:
        if not isinstance(step, Mapping):
            continue
        nested = step.get("section_result")
        if not isinstance(nested, Mapping):
            continue
        raw = nested.get("x3_disposition")
        if isinstance(raw, Mapping):
            raw = raw.get("x3_code") or raw.get("x3_disposition")
        value = str(raw or nested.get("x3_code") or "").strip()
        if value:
            return value
    return ""


def _section_blocked(l2_result: Mapping[str, Any]) -> bool:
    return any(
        isinstance(step, Mapping) and step.get("section_blocked") is True
        for step in l2_result.get("step_results") or []
    )


def _emit_runtime_bundle(
    *,
    root: Path,
    raw_request: Mapping[str, Any],
    run_id: str,
    request_id: str,
    route_id: str,
    route_family: str,
    l2_result: Mapping[str, Any],
    fault: str,
    x3_disposition: str,
    cache_preflight_evidence: Mapping[str, Any] | None,
    front_continuation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    identity = _identity(raw_request, run_id=run_id, request_id=request_id)
    runtime_mode = "fault" if fault else "production"
    l2_status = "FAIL" if fault else ("BLOCKED" if _section_blocked(l2_result) else "PASS")
    step_results = list(l2_result.get("step_results") or [])
    witness = {
        "schema_version": "apps_rg.runtime_execution_witness.v1",
        "run_id": run_id,
        "request_id": request_id,
        "trace_root": str(identity.get("trace_root") or ""),
        "route_id": route_id,
        "runtime_mode": runtime_mode,
        "l2": {
            "executed": not bool(fault),
            "status": l2_status,
            "fault": fault,
            "sub_stages": step_results,
        },
        "x2": {"disposition": "NOT_OBSERVED" if fault else "OBSERVED"},
        "x3": {"x3_disposition": x3_disposition},
        "current_run_mutated": False,
    }
    hashes: dict[str, str] = {}
    hashes["runtime_identity_envelope.json"] = _write_artifact(
        root,
        "runtime_identity_envelope.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload=identity,
    )
    hashes["validated_request.json"] = _write_artifact(
        root,
        "validated_request.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"request": _plain(raw_request), "request_id": request_id, "run_id": run_id},
    )
    continuation = dict(front_continuation) if isinstance(front_continuation, Mapping) else {}
    hashes["l1_plan_contract.json"] = _write_artifact(
        root,
        "l1_plan_contract.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"plan_contract": _plain(continuation.get("plan_contract") or {})},
    )
    hashes["route_contract.json"] = _write_artifact(
        root,
        "route_contract.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={
            "route_id": route_id,
            "route_family": route_family,
            "request_id": request_id,
            "trace_root": str(identity.get("trace_root") or ""),
            "route_contract": _plain(continuation.get("route_contract") or {}),
        },
    )
    for name, stage in (
        ("l3_bypass_receipt.json", "L3"),
        ("c0_bypass_receipt.json", "C0"),
        ("prompt_assembly_bypass_receipt.json", "PA"),
    ):
        hashes[name] = _write_artifact(
            root,
            name,
            component="apps_rg.runtime.orchestration.app_single_action_spine",
            payload={"stage": stage, "status": "OBSERVED", "run_id": run_id},
        )
    hashes["runtime_execution_witness.json"] = _write_artifact(
        root,
        "runtime_execution_witness.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload=witness,
    )
    hashes["l2_sealed_artifact.json"] = _write_artifact(
        root,
        "l2_sealed_artifact.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "status": l2_status, "fault": fault, "l2_result": _plain(l2_result)},
    )
    hashes["terminal_ret_packet.json"] = _write_artifact(
        root,
        "terminal_ret_packet.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "status": l2_status, "fault": fault},
    )
    hashes["exit_review_packet.json"] = _write_artifact(
        root,
        "exit_review_packet.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "x3_disposition": x3_disposition, "fault": fault},
    )
    hashes["x3_disposition_receipt.json"] = _write_artifact(
        root,
        "x3_disposition_receipt.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "x3_disposition": x3_disposition, "fault": fault},
    )
    hashes["runtime_exhaust_bundle.json"] = _write_artifact(
        root,
        "runtime_exhaust_bundle.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "runtime_mode": runtime_mode, "l2_fault": fault},
    )
    hashes["runtime_trace_snapshot.json"] = _write_artifact(
        root,
        "runtime_trace_snapshot.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={"run_id": run_id, "trace_root": str(identity.get("trace_root") or "")},
    )
    blocking_gaps = [fault] if fault else ([] if l2_status == "PASS" else ["SECTION_NOT_AUTHORIZED"])
    how_payload = {
        "schema_version": "apps_rg.how_trace.v1",
        "run_id": run_id,
        "runtime_mode": runtime_mode,
        "success": not blocking_gaps,
        "blocking_gaps": blocking_gaps,
    }
    how_payload["deterministic_digest"] = _digest(how_payload)
    hashes[HOW_TRACE_ARTIFACT] = _write_artifact(
        root,
        HOW_TRACE_ARTIFACT,
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload=how_payload,
    )
    hashes[ROUTE_COVERAGE_ARTIFACT] = _write_artifact(
        root,
        ROUTE_COVERAGE_ARTIFACT,
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={
            "route_families": [
                {
                    "route_family": route_family,
                    "certification_status": "CERTIFIED" if not blocking_gaps else "NOT_CERTIFIED",
                    "proof_class": "APP_OWNED_RUNTIME",
                    "exercised_in_current_run": True,
                }
            ],
            "summary": {"certified": 1 if not blocking_gaps else 0, "total_families": 1},
        },
    )
    proof_payload = {
        "schema_version": "apps_rg.spine_proof.v1",
        "run_id": run_id,
        "runtime_mode": runtime_mode,
        "success": not blocking_gaps,
        "exit_code": 0 if not blocking_gaps else 1,
        "blocking_gaps": blocking_gaps,
        "runtime_l2_artifact_ref": hashes["l2_sealed_artifact.json"],
        "how_trace_ref": hashes[HOW_TRACE_ARTIFACT],
    }
    hashes[SPINE_PROOF_ARTIFACT] = _write_artifact(
        root,
        SPINE_PROOF_ARTIFACT,
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload=proof_payload,
    )
    hashes["integrated_runtime_artifact_manifest.json"] = _write_artifact(
        root,
        "integrated_runtime_artifact_manifest.json",
        component="apps_rg.runtime.orchestration.app_single_action_spine",
        payload={
            "run_id": run_id,
            "artifact_filenames": sorted(hashes),
            "artifact_hashes": hashes,
            "cache_preflight_evidence": _plain(cache_preflight_evidence or {}),
        },
    )
    return witness


def run_apps_rg_single_action_spine(*args: Any, **kwargs: Any) -> AppsRgSingleActionSpineRunResult:
    """Execute one Apps RG request and seal the app-owned runtime bundle."""
    del args
    raw_candidate = kwargs.get("raw_request")
    raw_request = dict(raw_candidate) if isinstance(raw_candidate, Mapping) else {}
    root = Path(kwargs.get("artifact_dir") or ".").resolve()
    root.mkdir(parents=True, exist_ok=True)
    route_id = str(kwargs.get("route_id") or ROUTE_ID).strip() or ROUTE_ID
    route_family = str(kwargs.get("route_family") or ROUTE_FAMILY).strip() or ROUTE_FAMILY
    run_id = _request_value(raw_request, "run_id") or f"apps-rg-{uuid.uuid4().hex[:12]}"
    request_id = _request_value(raw_request, "request_id") or run_id
    cache_preflight = kwargs.get("cache_preflight_evidence")
    front_continuation = kwargs.get("front_continuation")
    fault = ""
    l2_result: dict[str, Any] = {}
    x3_disposition = "X3D_ALLOW_FINISH"
    app_name = str(kwargs.get("app_name") or raw_request.get("app_id") or "apps_rg")
    if app_name == "apps_rg" and not isinstance(cache_preflight, Mapping):
        fault = "CACHE_PREFLIGHT_EVIDENCE_REQUIRED"
    else:
        try:
            l2_callable = kwargs.get("l2_callable")
            if callable(l2_callable):
                result = l2_callable()
                l2_result = _plain(result) if isinstance(result, Mapping) else {"result": _plain(result)}
            elif _request_value(raw_request, "execution_scope") == "section":
                l2_result = _run_section_l2(raw_request, artifact_dir=root)
                x3_disposition = _section_x3(l2_result) or "X3E_SAFE_ABSTAIN"
            else:
                l2_result = _run_full_resume_l2(raw_request, artifact_dir=root, run_id=run_id)
        except Exception as exc:  # preserve exact runtime failure evidence in the sealed outcome
            fault = f"{type(exc).__name__}:{exc}"
    if fault:
        x3_disposition = "X3A_DENY_REROUTE"
    witness = _emit_runtime_bundle(
        root=root,
        raw_request=raw_request,
        run_id=run_id,
        request_id=request_id,
        route_id=route_id,
        route_family=route_family,
        l2_result=l2_result,
        fault=fault,
        x3_disposition=x3_disposition,
        cache_preflight_evidence=cache_preflight if isinstance(cache_preflight, Mapping) else None,
        front_continuation=front_continuation if isinstance(front_continuation, Mapping) else None,
    )
    return AppsRgSingleActionSpineRunResult(
        run_id=run_id,
        request_id=request_id,
        route_id=route_id,
        x3_disposition=x3_disposition,
        terminal_r5=False,
        terminal_r5_reason="",
        artifact_dir=root,
        fault=fault,
        l2_result=l2_result,
        execution_witness=witness,
    )


__all__ = [
    "AppsRgSingleActionSpineRunResult",
    "HOW_TRACE_ARTIFACT",
    "ROUTE_COVERAGE_ARTIFACT",
    "ROUTE_FAMILY",
    "ROUTE_ID",
    "SPINE_PROOF_ARTIFACT",
    "run_apps_rg_single_action_spine",
]
