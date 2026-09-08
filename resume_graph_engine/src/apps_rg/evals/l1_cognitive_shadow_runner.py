"""Apps RG-owned non-product runner for one L1 cognitive shadow arm.

This path is deliberately separate from the product whole-run entrypoint.  It
executes the Apps RG modular section lanes after Apps RG U0 -> L1 -> L0, so a
W4 experiment can observe whether the treatment reaches the section C0 -> PA
seam.  It does not grant product, release, or promotion authority.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Sequence

from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
    build_l1_cognitive_pair_config_receipt,
    build_l1_cognitive_pair_input_receipt,
    build_l1_cognitive_shadow_run_binding,
    validate_l1_cognitive_pair_config_receipt,
    validate_l1_cognitive_pair_input_receipt,
)
from apps_rg.l2_recipe.modular_lane_adapter import ModularLaneTargeting
from apps_rg.l2_recipe.modular_resume_generation import (
    ModularResumeInputPackage,
    ModularResumeProfile,
    run_modular_resume_generation,
)
from apps_rg.runtime.bindings.l0_binding import l0_route_apps_rg
from apps_rg.runtime.bindings.l1_binding import l1_plan_apps_rg
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.u0_binding import u0_validate_apps_rg
from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
    emit_l1_cognitive_treatment_execution_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr
from apps_rg.runtime.dispatch.apps_rg_dispatch import apps_rg_parse
from apps_rg.runtime.runtime_proof_layout import find_repo_root
from apps_rg.runtime.spine.validated_request_contract import (
    CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME,
    load_validated_request_contract,
    write_validated_request_contract,
)


L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_shadow_runner.v1"
)
L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_shadow_attempt_ledger.v1"
)
L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_FILENAME: Final[str] = (
    "l1_cognitive_shadow_attempt_ledger.json"
)
L1_COGNITIVE_SHADOW_TENANT_ID: Final[str] = "apps_rg_l1_cognitive_shadow"


class L1CognitiveShadowRunnerError(ValueError):
    """Raised when an App RG shadow arm cannot be created safely."""


def _read_required(path: Path, *, label: str) -> str:
    source = Path(path).resolve()
    if not source.is_file():
        raise L1CognitiveShadowRunnerError(f"{label} does not exist")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise L1CognitiveShadowRunnerError(f"{label} is unreadable") from exc
    if not text.strip():
        raise L1CognitiveShadowRunnerError(f"{label} is empty")
    return text


def _require_new_run_root(*, artifact_dir: Path, repo_root: Path) -> None:
    try:
        artifact_dir.relative_to(repo_root)
    except ValueError as exc:
        raise L1CognitiveShadowRunnerError(
            "shadow artifact_dir must be beneath the Apps RG repository"
        ) from exc
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        raise L1CognitiveShadowRunnerError(
            "shadow artifact_dir already contains an attempt; refusing overwrite"
        )
    artifact_dir.mkdir(parents=True, exist_ok=True)


def _write_l1_root_artifacts(
    *, artifact_dir: Path, validated_request: Any, l1_plan: Any
) -> None:
    """Persist the exact U0/L1 inputs section lanes rehydrate in whole-run mode."""

    task_spec = dict(getattr(l1_plan, "task_spec", None) or {})
    v1 = task_spec.get("apps_rg_planning_capsule")
    v2 = task_spec.get("apps_rg_planning_v2_capsule")
    treatment = task_spec.get("l1_cognitive_treatment")
    cognitive = task_spec.get("apps_rg_cognitive_v3_plan")
    if (
        not isinstance(v1, dict)
        or not isinstance(v2, dict)
        or not isinstance(treatment, dict)
    ):
        raise L1CognitiveShadowRunnerError("Apps RG L1 omitted required shadow lineage")

    write_validated_request_contract(
        artifact_dir / CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME,
        validated_request,
        consumer_stage="l1_cognitive_shadow_modular_sections",
    )
    sr.write_stage_receipt(
        artifact_dir / sr.FILENAME_L1_PLAN,
        {
            "schema_version": "apps_rg.l1_plan_contract.v1",
            "status": "PASS",
            "contract": asdict(l1_plan),
            "non_product_evaluation_only": True,
        },
    )
    sr.write_stage_receipt(artifact_dir / sr.FILENAME_L1_PLANNING_CAPSULE, v1)
    sr.write_stage_receipt(artifact_dir / sr.FILENAME_L1_PLANNING_V2_CAPSULE, v2)
    sr.write_stage_receipt(artifact_dir / sr.FILENAME_L1_COGNITIVE_TREATMENT, treatment)
    if cognitive is not None:
        if not isinstance(cognitive, dict):
            raise L1CognitiveShadowRunnerError("Apps RG L1 cognitive plan is malformed")
        sr.write_stage_receipt(artifact_dir / sr.FILENAME_L1_COGNITIVE_PLAN, cognitive)


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitiveShadowRunnerError(
            f"shadow artifact is unreadable: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise L1CognitiveShadowRunnerError(f"shadow artifact is invalid: {path.name}")
    return dict(value)


def _write_shadow_run_binding(
    *,
    artifact_dir: Path,
    target_company: str,
    target_role: str,
    target_level: str,
    generation_mode: str,
    jd_path: Path,
    briefing_path: Path,
    resume_path: Path,
    lane_provider: str,
    non_product_provider_preflight_disabled: bool,
    frozen_input_receipt: Mapping[str, Any] | None,
    config_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Persist the exact input/config provenance before an arm can execute."""

    observed_input = build_l1_cognitive_pair_input_receipt(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        generation_mode=generation_mode,
        jd_path=jd_path,
        briefing_path=briefing_path,
        resume_path=resume_path,
    )
    observed_config = build_l1_cognitive_pair_config_receipt(
        generation_mode=generation_mode,
        auto_research_internal=False,
        non_product_provider_preflight_disabled=non_product_provider_preflight_disabled,
        lane_provider=lane_provider,
    )
    frozen_input = observed_input
    if frozen_input_receipt is not None:
        frozen_input = dict(frozen_input_receipt)
        validate_l1_cognitive_pair_input_receipt(frozen_input)
        if frozen_input != observed_input:
            raise L1CognitiveShadowRunnerError(
                "supplied frozen input receipt does not match the shadow arm inputs"
            )
    config = observed_config
    if config_receipt is not None:
        config = dict(config_receipt)
        validate_l1_cognitive_pair_config_receipt(config)
        if config != observed_config:
            raise L1CognitiveShadowRunnerError(
                "supplied configuration receipt does not match the shadow arm settings"
            )
    binding = build_l1_cognitive_shadow_run_binding(
        frozen_input_receipt=frozen_input,
        config_receipt=config,
    )
    sr.write_stage_receipt(
        artifact_dir / L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
        binding,
    )
    return binding


def run_l1_cognitive_shadow_arm(
    *,
    artifact_dir: Path,
    target_company: str,
    target_role: str,
    target_level: str,
    generation_mode: str,
    jd_path: Path,
    briefing_path: Path,
    resume_path: Path,
    treatment_arm: str,
    repo_root: Path | None = None,
    lane_provider: str = "",
    allow_nonproduct_provider_preflight_disable: bool = False,
    frozen_input_receipt: Mapping[str, Any] | None = None,
    config_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one matched, non-product Apps RG modular shadow arm.

    The source plan is U0-bound from ``treatment_arm``.  A control arm cannot
    carry an L1 v3 cognitive plan; a candidate arm must carry one.  A result is
    evidence of the execution attempted, never an outcome-quality verdict.

    ``allow_nonproduct_provider_preflight_disable`` is an explicit, retained
    evaluation-only escape hatch for a known provider preflight process exit.
    It never changes product authorization and must be frozen identically for
    matched control and candidate arms.
    """

    arm = str(treatment_arm).strip()
    if arm not in {L1_COGNITIVE_V2_CONTROL_ARM, L1_COGNITIVE_V3_CANDIDATE_ARM}:
        raise L1CognitiveShadowRunnerError("shadow treatment arm is invalid")
    repo = Path(repo_root or find_repo_root()).resolve()
    root = Path(artifact_dir).resolve()
    preflight_disabled = bool(allow_nonproduct_provider_preflight_disable)
    _require_new_run_root(artifact_dir=root, repo_root=repo)
    jd_source = Path(jd_path).resolve()
    brief_source = Path(briefing_path).resolve()
    resume_source = Path(resume_path).resolve()
    jd_text = _read_required(jd_source, label="job description")
    brief_text = _read_required(brief_source, label="briefing")
    _read_required(resume_source, label="resume")
    pair_binding = _write_shadow_run_binding(
        artifact_dir=root,
        target_company=str(target_company),
        target_role=str(target_role),
        target_level=str(target_level),
        generation_mode=str(generation_mode),
        jd_path=jd_source,
        briefing_path=brief_source,
        resume_path=resume_source,
        lane_provider=str(lane_provider),
        non_product_provider_preflight_disabled=preflight_disabled,
        frozen_input_receipt=frozen_input_receipt,
        config_receipt=config_receipt,
    )

    envelope = apps_rg_parse(
        {
            "app_id": "apps_rg",
            "task_class": "resume_generation",
            # Section L2 execution requires a non-empty, internally consistent
            # tenant chain from U0 through PA.  This is a clearly non-product
            # evaluation tenant, not a substitute for the product-only canonical
            # Apps Research identity.
            "tenant_id": L1_COGNITIVE_SHADOW_TENANT_ID,
            "target_company": str(target_company),
            "target_role": str(target_role),
            "target_level": str(target_level),
            "job_description_ref": str(jd_source),
            "job_description_text": jd_text,
            "briefing_artifact_ref": str(brief_source),
            "source_resume_ref": str(resume_source),
            "generation_mode": str(generation_mode),
            "l1_cognitive_treatment_arm": arm,
            "l5_certification_ref": "test:valid:w6",
            "user_constraints": {
                "briefing_text": brief_text,
                "source_channel": "apps_rg_l1_cognitive_shadow",
            },
        }
    )
    validated_request = u0_validate_apps_rg(envelope, allow_missing_profiles=False)
    l1_plan = l1_plan_apps_rg(validated_request)
    task_spec = dict(getattr(l1_plan, "task_spec", None) or {})
    observed_treatment = build_l1_cognitive_treatment(
        arm, assignment_origin="U0_VALIDATED_INGRESS"
    )
    if task_spec.get("l1_cognitive_treatment") != observed_treatment:
        raise L1CognitiveShadowRunnerError(
            "shadow treatment was not preserved by Apps RG U0"
        )
    has_candidate_plan = isinstance(task_spec.get("apps_rg_cognitive_v3_plan"), dict)
    if has_candidate_plan != (arm == L1_COGNITIVE_V3_CANDIDATE_ARM):
        raise L1CognitiveShadowRunnerError(
            "shadow L1 plan does not match its treatment arm"
        )
    route = l0_route_apps_rg(l1_plan)
    _write_l1_root_artifacts(
        artifact_dir=root,
        validated_request=validated_request,
        l1_plan=l1_plan,
    )
    sr.write_stage_receipt(
        root / sr.FILENAME_SPINE_MANIFEST,
        {
            "schema_version": L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION,
            "status": "ATTEMPTED",
            "app_scope": "APPS_RG_V2_ONLY",
            "non_product_evaluation_only": True,
            "product_authorized": False,
            "non_product_provider_preflight_disabled": preflight_disabled,
            "pipeline_complete": False,
            "treatment_arm": arm,
            "route_id": str(getattr(route, "route_id", "") or ""),
            "route_family": str(getattr(route, "route_family", "") or ""),
            "input_refs": {
                "job_description": str(jd_source),
                "briefing": str(brief_source),
                "resume": str(resume_source),
            },
            "pair_provenance": {
                "binding_ref": L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
                "binding_digest": str(pair_binding["binding_digest"]),
                "frozen_input_digest": str(pair_binding["frozen_input_digest"]),
                "provider_model_config_digest": str(
                    pair_binding["provider_model_config_digest"]
                ),
                "tool_config_digest": str(pair_binding["tool_config_digest"]),
            },
        },
    )

    previous_shortcuts = os.environ.get("APPS_RG_ALLOW_PRODUCT_SHORTCUTS")
    previous_preflight_disable = os.environ.get(
        "APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE"
    )
    os.environ["APPS_RG_ALLOW_PRODUCT_SHORTCUTS"] = "1"
    if preflight_disabled:
        os.environ["APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE"] = "1"
    modular_result: Any | None = None
    modular_exception = ""
    try:
        modular_result = run_modular_resume_generation(
            ModularResumeInputPackage(
                repo_root=repo,
                target_company=str(target_company),
                target_role=str(target_role),
            ),
            root,
            str(getattr(validated_request, "run_id", "") or root.name),
            ModularResumeProfile(
                run_phase0_synthetic_assembly=False,
                validate_rg_output_fixture=False,
                phase1_invoke_real_lanes=True,
                phase1_lane_provider=str(lane_provider),
            ),
            lane_targeting=ModularLaneTargeting(
                target_company=str(target_company),
                target_title=str(target_role),
                jd_text=jd_text,
                jd_source="FROZEN_PAIR_INPUT",
                jd_ref_used=str(jd_source),
                briefing_text=brief_text,
                briefing_source="FROZEN_PAIR_INPUT",
                briefing_ref_used=str(brief_source),
            ),
        )
    except (
        Exception,
        SystemExit,
    ) as exc:  # retain every failed arm as experiment evidence
        modular_exception = f"{type(exc).__name__}:{exc}"
    finally:
        if previous_shortcuts is None:
            os.environ.pop("APPS_RG_ALLOW_PRODUCT_SHORTCUTS", None)
        else:
            os.environ["APPS_RG_ALLOW_PRODUCT_SHORTCUTS"] = previous_shortcuts
        if previous_preflight_disable is None:
            os.environ.pop("APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE", None)
        else:
            os.environ["APPS_RG_COMPETENCIES_PROVIDER_PREFLIGHT_DISABLE"] = (
                previous_preflight_disable
            )
    execution_path = emit_l1_cognitive_treatment_execution_receipt(
        run_root=root,
        l1_plan=l1_plan,
    )
    sr.write_stage_receipt(
        root / "l1_cognitive_shadow_run_result.json",
        {
            "schema_version": L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION,
            "status": "FAIL" if modular_exception else "COMPLETED",
            "app_scope": "APPS_RG_V2_ONLY",
            "non_product_evaluation_only": True,
            "non_product_runtime_policy_override": "APPS_RG_ALLOW_PRODUCT_SHORTCUTS=1",
            "non_product_provider_preflight_disabled": preflight_disabled,
            "product_authorized": False,
            "pipeline_complete": False,
            "treatment_arm": arm,
            "modular_decisive_status": str(
                getattr(modular_result, "decisive_status", "") or ""
            ),
            "modular_failure_reason": str(
                getattr(modular_result, "failure_reason", "") or ""
            ),
            "modular_exception": modular_exception,
            "treatment_execution_receipt_ref": sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION,
            "pair_provenance_binding_ref": L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
        },
    )
    return {
        "schema_version": L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION,
        "app_scope": "APPS_RG_V2_ONLY",
        "non_product_evaluation_only": True,
        "non_product_provider_preflight_disabled": preflight_disabled,
        "product_authorized": False,
        "pipeline_complete": False,
        "artifact_dir": str(root),
        "treatment_arm": arm,
        "treatment_execution_receipt": str(execution_path),
        "pair_provenance_binding": str(root / L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME),
        "modular_decisive_status": str(
            getattr(modular_result, "decisive_status", "") or ""
        ),
        "modular_failure_reason": str(
            getattr(modular_result, "failure_reason", "") or ""
        ),
        "modular_exception": modular_exception,
    }


def finalize_incomplete_l1_cognitive_shadow_attempt(
    *, artifact_dir: Path
) -> dict[str, Any]:
    """Terminalize a retained arm when its caller stopped before writing a receipt.

    This never reruns or overwrites the attempt.  It only derives the missing
    Apps RG observation from artifacts already present under its run root.
    """

    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise L1CognitiveShadowRunnerError("shadow attempt directory does not exist")
    contract_path = root / CANONICAL_APPS_RG_VALIDATED_REQUEST_FILENAME
    if not contract_path.is_file():
        # v1 shadow attempts written before the canonical filename correction
        # are retained and terminalized in place; no request is regenerated.
        contract_path = root / "validated_request.json"
    if not contract_path.is_file():
        raise L1CognitiveShadowRunnerError("shadow attempt lacks its validated request")
    validated_request = load_validated_request_contract(contract_path)
    l1_plan = l1_plan_apps_rg(validated_request)
    execution_path = root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION
    if not execution_path.is_file():
        emit_l1_cognitive_treatment_execution_receipt(run_root=root, l1_plan=l1_plan)
    result_path = root / "l1_cognitive_shadow_run_result.json"
    if not result_path.is_file():
        task_spec = dict(getattr(l1_plan, "task_spec", None) or {})
        treatment = dict(task_spec.get("l1_cognitive_treatment") or {})
        sr.write_stage_receipt(
            result_path,
            {
                "schema_version": L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION,
                "status": "INTERRUPTED_OR_CALLER_DID_NOT_RETURN",
                "app_scope": "APPS_RG_V2_ONLY",
                "non_product_evaluation_only": True,
                "product_authorized": False,
                "pipeline_complete": False,
                "treatment_arm": str(treatment.get("arm") or ""),
                "treatment_execution_receipt_ref": sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION,
                "terminalization": "artifact_observation_only_no_rerun",
            },
        )
    return {
        "artifact_dir": str(root),
        "treatment_execution_receipt": str(execution_path),
        "shadow_run_result": str(result_path),
    }


def write_l1_cognitive_shadow_attempt_ledger(
    *, campaign_root: Path, attempt_roots: Sequence[Path]
) -> dict[str, Any]:
    """Persist the W4 denominator, including failed and incomplete attempts."""

    campaign = Path(campaign_root).resolve()
    if not campaign.is_dir():
        raise L1CognitiveShadowRunnerError("shadow campaign directory does not exist")
    rows: list[dict[str, Any]] = []
    for supplied in attempt_roots:
        root = Path(supplied).resolve()
        try:
            run_ref = root.relative_to(campaign).as_posix()
        except ValueError as exc:
            raise L1CognitiveShadowRunnerError(
                "shadow attempt must be beneath the campaign directory"
            ) from exc
        if not root.is_dir():
            raise L1CognitiveShadowRunnerError(f"shadow attempt is missing: {run_ref}")
        treatment_path = root / sr.FILENAME_L1_COGNITIVE_TREATMENT
        treatment = (
            _load_json_mapping(treatment_path) if treatment_path.is_file() else {}
        )
        execution_path = root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION
        result_path = root / "l1_cognitive_shadow_run_result.json"
        execution = (
            _load_json_mapping(execution_path) if execution_path.is_file() else {}
        )
        result = _load_json_mapping(result_path) if result_path.is_file() else {}
        rows.append(
            {
                "run_ref": run_ref,
                "treatment_arm": str(treatment.get("arm") or "UNKNOWN"),
                "treatment_digest": str(treatment.get("treatment_digest") or ""),
                "execution_receipt_status": str(execution.get("status") or "MISSING"),
                "execution_receipt_digest": str(execution.get("receipt_digest") or ""),
                "runner_status": str(result.get("status") or "MISSING"),
                "runner_result_digest": _file_sha256(result_path)
                if result_path.is_file()
                else "",
                "retained": True,
            }
        )
    if len({row["run_ref"] for row in rows}) != len(rows):
        raise L1CognitiveShadowRunnerError(
            "shadow attempt ledger contains duplicate run roots"
        )
    rows.sort(key=lambda row: row["run_ref"])
    receipt = {
        "schema_version": L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_SCHEMA_VERSION,
        "app_scope": "APPS_RG_V2_ONLY",
        "non_product_evaluation_only": True,
        "product_authorized": False,
        "attempts": rows,
        "summary": {
            "attempt_count": len(rows),
            "candidate_attempt_count": sum(
                row["treatment_arm"] == L1_COGNITIVE_V3_CANDIDATE_ARM for row in rows
            ),
            "control_attempt_count": sum(
                row["treatment_arm"] == L1_COGNITIVE_V2_CONTROL_ARM for row in rows
            ),
            "missing_execution_receipt_count": sum(
                row["execution_receipt_status"] == "MISSING" for row in rows
            ),
            "all_attempts_retained": True,
        },
    }
    sr.write_stage_receipt(
        campaign / L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_FILENAME,
        receipt,
    )
    return receipt


__all__ = [
    "L1CognitiveShadowRunnerError",
    "L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_FILENAME",
    "L1_COGNITIVE_SHADOW_ATTEMPT_LEDGER_SCHEMA_VERSION",
    "L1_COGNITIVE_SHADOW_RUNNER_SCHEMA_VERSION",
    "L1_COGNITIVE_SHADOW_TENANT_ID",
    "finalize_incomplete_l1_cognitive_shadow_attempt",
    "run_l1_cognitive_shadow_arm",
    "write_l1_cognitive_shadow_attempt_ledger",
]
