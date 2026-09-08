"""Capture Apps RG paired-run evidence without inventing outcome success.

The runner is deliberately separate from provider dispatch: it reads two
already-completed App RG run roots, checks their treatment receipts, and emits
the protocol-shaped technical pair. Failed attempts remain as ``FAIL`` rows.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.evals.l1_cognitive_outcome_protocol import (
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
    write_l1_cognitive_paired_shadow_receipt,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
)
from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
    validate_l1_cognitive_treatment_execution_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_PAIR_INPUT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_pair_input.v2"
)
L1_COGNITIVE_PAIR_CONFIG_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_pair_config.v2"
)
L1_COGNITIVE_SHADOW_RUN_BINDING_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_shadow_run_binding.v1"
)
L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME: Final[str] = (
    "l1_cognitive_shadow_run_binding.json"
)
_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_RUNTIME_POLICY_OVERRIDE: Final[str] = "APPS_RG_ALLOW_PRODUCT_SHORTCUTS=1"


class L1CognitivePairedShadowCaptureError(ValueError):
    """Raised when paired Apps RG run evidence cannot be bound safely."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise L1CognitivePairedShadowCaptureError(f"{label} is unreadable") from exc
    if not isinstance(value, Mapping):
        raise L1CognitivePairedShadowCaptureError(f"{label} is invalid")
    return dict(value)


def _path_binding(path: Path, *, label: str) -> dict[str, str]:
    source = Path(path).resolve()
    if not source.is_file():
        raise L1CognitivePairedShadowCaptureError(f"{label} does not exist")
    return {"basename": source.name, "sha256": _file_digest(source)}


def _jd_payload_digest(path: Path, *, label: str) -> str:
    """Bind the exact U0 JD payload without retaining its text."""

    source = Path(path).resolve()
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise L1CognitivePairedShadowCaptureError(f"{label} is unreadable") from exc
    if not text.strip():
        raise L1CognitivePairedShadowCaptureError(f"{label} is empty")
    # This is deliberately the same canonical payload shape used by the L1 v2
    # source binding.  It lets capture prove that the recorded frozen file was
    # the JD text actually admitted at U0, without persisting the text itself.
    return _sha256({"jd_text": text})


def _require_digest(value: Any, *, field: str) -> str:
    digest = str(value or "").strip()
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise L1CognitivePairedShadowCaptureError(f"{field} must be a SHA-256 digest")
    return digest


def _require_nonempty_string(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise L1CognitivePairedShadowCaptureError(f"{field} is required")
    return normalized


def _validate_path_binding(
    value: Any, *, field: str, jd_payload: bool = False
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise L1CognitivePairedShadowCaptureError(f"{field} is invalid")
    expected_fields = {"basename", "sha256"}
    if jd_payload:
        expected_fields.add("u0_payload_digest")
    if set(value) != expected_fields:
        raise L1CognitivePairedShadowCaptureError(f"{field} fields are invalid")
    basename = _require_nonempty_string(
        value.get("basename"), field=f"{field}.basename"
    )
    if Path(basename).name != basename:
        raise L1CognitivePairedShadowCaptureError(
            f"{field}.basename must not contain a path"
        )
    result = {
        "basename": basename,
        "sha256": _require_digest(value.get("sha256"), field=f"{field}.sha256"),
    }
    if jd_payload:
        result["u0_payload_digest"] = _require_digest(
            value.get("u0_payload_digest"), field=f"{field}.u0_payload_digest"
        )
    return result


def validate_l1_cognitive_pair_input_receipt(receipt: Mapping[str, Any]) -> None:
    """Fail closed unless the frozen input receipt is self-consistent and safe."""

    if not isinstance(receipt, Mapping) or set(receipt) != {
        "schema_version",
        "app_scope",
        "target",
        "inputs",
        "input_digest",
    }:
        raise L1CognitivePairedShadowCaptureError(
            "paired input receipt fields are invalid"
        )
    if receipt.get("schema_version") != L1_COGNITIVE_PAIR_INPUT_SCHEMA_VERSION:
        raise L1CognitivePairedShadowCaptureError(
            "paired input receipt schema is invalid"
        )
    if receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitivePairedShadowCaptureError(
            "paired input receipt scope is invalid"
        )
    target = receipt.get("target")
    if not isinstance(target, Mapping) or set(target) != {
        "company",
        "role",
        "level",
        "generation_mode",
    }:
        raise L1CognitivePairedShadowCaptureError("paired input target is invalid")
    for field in ("company", "role", "level", "generation_mode"):
        _require_nonempty_string(target.get(field), field=f"target.{field}")
    inputs = receipt.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        "job_description",
        "briefing",
        "resume",
    }:
        raise L1CognitivePairedShadowCaptureError("paired input bindings are invalid")
    _validate_path_binding(
        inputs.get("job_description"), field="inputs.job_description", jd_payload=True
    )
    _validate_path_binding(inputs.get("briefing"), field="inputs.briefing")
    _validate_path_binding(inputs.get("resume"), field="inputs.resume")
    expected_digest = _sha256(
        {key: value for key, value in receipt.items() if key != "input_digest"}
    )
    if receipt.get("input_digest") != expected_digest:
        raise L1CognitivePairedShadowCaptureError(
            "paired input receipt digest is invalid"
        )


def validate_l1_cognitive_pair_config_receipt(receipt: Mapping[str, Any]) -> None:
    """Fail closed unless the provider/tool configuration was fully frozen."""

    if not isinstance(receipt, Mapping) or set(receipt) != {
        "schema_version",
        "app_scope",
        "provider_model",
        "tools",
        "generation_mode",
        "execution",
        "provider_model_config_digest",
        "tool_config_digest",
        "config_digest",
    }:
        raise L1CognitivePairedShadowCaptureError(
            "paired config receipt fields are invalid"
        )
    if receipt.get("schema_version") != L1_COGNITIVE_PAIR_CONFIG_SCHEMA_VERSION:
        raise L1CognitivePairedShadowCaptureError(
            "paired config receipt schema is invalid"
        )
    if receipt.get("app_scope") != _APP_SCOPE:
        raise L1CognitivePairedShadowCaptureError(
            "paired config receipt scope is invalid"
        )
    provider_model = receipt.get("provider_model")
    if not isinstance(provider_model, Mapping) or set(provider_model) != {
        "provider_mode",
        "section_models",
    }:
        raise L1CognitivePairedShadowCaptureError(
            "paired provider configuration is invalid"
        )
    _require_nonempty_string(
        provider_model.get("provider_mode"), field="provider_model.provider_mode"
    )
    section_models = provider_model.get("section_models")
    if not isinstance(section_models, Mapping) or not section_models:
        raise L1CognitivePairedShadowCaptureError(
            "paired section model configuration is invalid"
        )
    for section, model in section_models.items():
        _require_nonempty_string(section, field="provider_model.section_models key")
        _require_nonempty_string(
            model, field=f"provider_model.section_models[{section}]"
        )
    tools = receipt.get("tools")
    if (
        not isinstance(tools, Mapping)
        or set(tools)
        != {
            "auto_research_internal",
            "non_product_provider_preflight_disabled",
            "no_secret_material_recorded",
        }
        or any(not isinstance(tools.get(field), bool) for field in tools)
    ):
        raise L1CognitivePairedShadowCaptureError(
            "paired tool configuration is invalid"
        )
    if tools.get("no_secret_material_recorded") is not True:
        raise L1CognitivePairedShadowCaptureError(
            "paired tool secrecy assertion is invalid"
        )
    generation_mode = _require_nonempty_string(
        receipt.get("generation_mode"), field="generation_mode"
    )
    execution = receipt.get("execution")
    if not isinstance(execution, Mapping) or set(execution) != {
        "lane_provider",
        "runtime_policy_override",
    }:
        raise L1CognitivePairedShadowCaptureError(
            "paired execution configuration is invalid"
        )
    if not isinstance(execution.get("lane_provider"), str):
        raise L1CognitivePairedShadowCaptureError("paired lane provider is invalid")
    if execution.get("runtime_policy_override") != _RUNTIME_POLICY_OVERRIDE:
        raise L1CognitivePairedShadowCaptureError("paired runtime policy is invalid")
    if receipt.get("provider_model_config_digest") != _sha256(provider_model):
        raise L1CognitivePairedShadowCaptureError(
            "paired provider configuration digest is invalid"
        )
    if receipt.get("tool_config_digest") != _sha256(
        {
            "tools": tools,
            "generation_mode": generation_mode,
            "execution": execution,
        }
    ):
        raise L1CognitivePairedShadowCaptureError(
            "paired tool configuration digest is invalid"
        )
    expected_digest = _sha256(
        {key: value for key, value in receipt.items() if key != "config_digest"}
    )
    if receipt.get("config_digest") != expected_digest:
        raise L1CognitivePairedShadowCaptureError(
            "paired config receipt digest is invalid"
        )


def build_l1_cognitive_pair_input_receipt(
    *,
    target_company: str,
    target_role: str,
    target_level: str,
    generation_mode: str,
    jd_path: Path,
    briefing_path: Path,
    resume_path: Path,
) -> dict[str, Any]:
    """Freeze matched non-secret inputs by file digest, never by raw text."""

    receipt: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_PAIR_INPUT_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "target": {
            "company": str(target_company),
            "role": str(target_role),
            "level": str(target_level),
            "generation_mode": str(generation_mode),
        },
        "inputs": {
            "job_description": {
                **_path_binding(jd_path, label="job description"),
                "u0_payload_digest": _jd_payload_digest(
                    jd_path, label="job description"
                ),
            },
            "briefing": _path_binding(briefing_path, label="briefing"),
            "resume": _path_binding(resume_path, label="resume"),
        },
        "input_digest": "",
    }
    receipt["input_digest"] = _sha256(
        {key: value for key, value in receipt.items() if key != "input_digest"}
    )
    validate_l1_cognitive_pair_input_receipt(receipt)
    return receipt


def build_l1_cognitive_pair_config_receipt(
    *,
    generation_mode: str,
    auto_research_internal: bool,
    non_product_provider_preflight_disabled: bool = False,
    lane_provider: str = "",
) -> dict[str, Any]:
    """Freeze the non-secret provider/tool configuration for both arms."""

    from apps_rg.runtime.section_model_limits import resolve_section_generation_model

    sections = (
        "competencies",
        "executive_summary",
        "headline",
        "ibm_bullets",
        "ibm_narrative",
        "unify_bullets",
        "unify_narrative",
    )
    receipt: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_PAIR_CONFIG_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "provider_model": {
            "provider_mode": str(
                __import__("os").environ.get("APPS_RG_L2_PROVIDER_MODE")
                or "LIVE_ALLOWED_DEFAULT"
            ),
            "section_models": {
                section: resolve_section_generation_model(section)
                for section in sections
            },
        },
        "tools": {
            "auto_research_internal": bool(auto_research_internal),
            "non_product_provider_preflight_disabled": bool(
                non_product_provider_preflight_disabled
            ),
            "no_secret_material_recorded": True,
        },
        "generation_mode": str(generation_mode),
        "execution": {
            "lane_provider": str(lane_provider),
            "runtime_policy_override": _RUNTIME_POLICY_OVERRIDE,
        },
        "provider_model_config_digest": "",
        "tool_config_digest": "",
        "config_digest": "",
    }
    receipt["provider_model_config_digest"] = _sha256(receipt["provider_model"])
    receipt["tool_config_digest"] = _sha256(
        {
            "tools": receipt["tools"],
            "generation_mode": receipt["generation_mode"],
            "execution": receipt["execution"],
        }
    )
    receipt["config_digest"] = _sha256(
        {key: value for key, value in receipt.items() if key != "config_digest"}
    )
    validate_l1_cognitive_pair_config_receipt(receipt)
    return receipt


def build_l1_cognitive_shadow_run_binding(
    *,
    frozen_input_receipt: Mapping[str, Any],
    config_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one shadow arm to the frozen pair inputs and execution settings."""

    frozen_input = dict(frozen_input_receipt)
    config = dict(config_receipt)
    validate_l1_cognitive_pair_input_receipt(frozen_input)
    validate_l1_cognitive_pair_config_receipt(config)
    binding: dict[str, Any] = {
        "schema_version": L1_COGNITIVE_SHADOW_RUN_BINDING_SCHEMA_VERSION,
        "app_scope": _APP_SCOPE,
        "frozen_input": frozen_input,
        "execution_config": config,
        "frozen_input_digest": str(frozen_input["input_digest"]),
        "provider_model_config_digest": str(config["provider_model_config_digest"]),
        "tool_config_digest": str(config["tool_config_digest"]),
        "binding_digest": "",
    }
    binding["binding_digest"] = _sha256(
        {key: value for key, value in binding.items() if key != "binding_digest"}
    )
    validate_l1_cognitive_shadow_run_binding(binding)
    return binding


def validate_l1_cognitive_shadow_run_binding(binding: Mapping[str, Any]) -> None:
    """Verify the arm-local provenance receipt consumed by pair capture/review."""

    if not isinstance(binding, Mapping) or set(binding) != {
        "schema_version",
        "app_scope",
        "frozen_input",
        "execution_config",
        "frozen_input_digest",
        "provider_model_config_digest",
        "tool_config_digest",
        "binding_digest",
    }:
        raise L1CognitivePairedShadowCaptureError(
            "shadow run binding fields are invalid"
        )
    if binding.get("schema_version") != L1_COGNITIVE_SHADOW_RUN_BINDING_SCHEMA_VERSION:
        raise L1CognitivePairedShadowCaptureError(
            "shadow run binding schema is invalid"
        )
    if binding.get("app_scope") != _APP_SCOPE:
        raise L1CognitivePairedShadowCaptureError("shadow run binding scope is invalid")
    frozen_input = binding.get("frozen_input")
    config = binding.get("execution_config")
    if not isinstance(frozen_input, Mapping) or not isinstance(config, Mapping):
        raise L1CognitivePairedShadowCaptureError(
            "shadow run binding payload is invalid"
        )
    validate_l1_cognitive_pair_input_receipt(frozen_input)
    validate_l1_cognitive_pair_config_receipt(config)
    if binding.get("frozen_input_digest") != frozen_input.get("input_digest"):
        raise L1CognitivePairedShadowCaptureError("shadow run input binding is invalid")
    if binding.get("provider_model_config_digest") != config.get(
        "provider_model_config_digest"
    ):
        raise L1CognitivePairedShadowCaptureError(
            "shadow run provider binding is invalid"
        )
    if binding.get("tool_config_digest") != config.get("tool_config_digest"):
        raise L1CognitivePairedShadowCaptureError("shadow run tool binding is invalid")
    expected_digest = _sha256(
        {key: value for key, value in binding.items() if key != "binding_digest"}
    )
    if binding.get("binding_digest") != expected_digest:
        raise L1CognitivePairedShadowCaptureError(
            "shadow run binding digest is invalid"
        )


def load_l1_cognitive_shadow_run_binding(run_root: Path) -> dict[str, Any]:
    """Load the sealed Apps RG-local input/config binding for one shadow arm."""

    binding_path = Path(run_root) / L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME
    if not binding_path.is_file():
        raise L1CognitivePairedShadowCaptureError(
            "shadow run lacks the required pre-execution Apps RG-local input/config binding"
        )
    binding = _read_json(
        binding_path,
        label="shadow run input/config binding",
    )
    validate_l1_cognitive_shadow_run_binding(binding)
    return binding


def _relative_run_ref(campaign_root: Path, run_root: Path) -> str:
    try:
        return run_root.resolve().relative_to(campaign_root.resolve()).as_posix()
    except ValueError as exc:
        raise L1CognitivePairedShadowCaptureError(
            "run root must be beneath campaign root"
        ) from exc


def _final_output_binding(run_root: Path) -> tuple[str, str]:
    final_resume = (
        run_root / "modular_r4" / "final_resume_assembly" / "final_resume.json"
    )
    output_contract = run_root / "FINAL_RESUME_OUTPUT.json"
    if final_resume.is_file() and output_contract.is_file():
        contract = _read_json(output_contract, label="final output contract")
        if contract.get("status") == "PASS":
            return _file_digest(final_resume), "PASS"
    for fallback in (
        output_contract,
        run_root / "mandatory_run_output.json",
        run_root / sr.FILENAME_SPINE_MANIFEST,
    ):
        if fallback.is_file():
            return _file_digest(fallback), "FAIL"
    raise L1CognitivePairedShadowCaptureError("run has no terminal output artifact")


def _arm_row(
    *, campaign_root: Path, run_root: Path, expected_arm: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(run_root).resolve()
    receipt = _read_json(
        root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION,
        label="treatment execution receipt",
    )
    validate_l1_cognitive_treatment_execution_receipt(receipt)
    treatment = receipt.get("treatment")
    lineage = receipt.get("lineage")
    if not isinstance(treatment, Mapping) or treatment.get("arm") != expected_arm:
        raise L1CognitivePairedShadowCaptureError(
            "run treatment arm does not match pair"
        )
    if not isinstance(lineage, Mapping):
        raise L1CognitivePairedShadowCaptureError("run treatment lineage is invalid")
    output_digest, completion_status = _final_output_binding(root)
    records = receipt.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise L1CognitivePairedShadowCaptureError("run prompt observations are invalid")
    row: dict[str, Any] = {
        "run_ref": _relative_run_ref(campaign_root, root),
        "run_id": root.name,
        "compiled_prompt_digest": _sha256(list(records)),
        "output_digest": output_digest,
        "completion_status": completion_status,
        "l1_cognitive_treatment_execution_digest": str(receipt["receipt_digest"]),
    }
    if expected_arm == L1_COGNITIVE_V2_CONTROL_ARM:
        row["l1_v2_capsule_digest"] = str(lineage.get("l1_v2_capsule_digest") or "")
    else:
        for field in (
            "l1_cognitive_plan_digest",
            "l1_cognitive_advisory_digest",
            "c0_outcome_set_digest",
            "l1_cognitive_revision_set_digest",
        ):
            row[field] = str(lineage.get(field) or "")
    return row, receipt


def _verify_run_binding(
    *,
    run_root: Path,
    frozen_input_receipt: Mapping[str, Any],
    config_receipt: Mapping[str, Any],
    arm: str,
) -> None:
    binding = load_l1_cognitive_shadow_run_binding(run_root)
    if binding["frozen_input"] != dict(frozen_input_receipt):
        raise L1CognitivePairedShadowCaptureError(
            f"{arm} run does not bind the supplied frozen input receipt"
        )
    if binding["execution_config"] != dict(config_receipt):
        raise L1CognitivePairedShadowCaptureError(
            f"{arm} run does not bind the supplied configuration receipt"
        )


def _verify_u0_jd_binding(
    *, v2_capsule: Mapping[str, Any], frozen_input_receipt: Mapping[str, Any], arm: str
) -> None:
    source_binding = v2_capsule.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise L1CognitivePairedShadowCaptureError(f"{arm} v2 source binding is invalid")
    expected = (
        frozen_input_receipt.get("inputs", {})
        .get("job_description", {})
        .get("u0_payload_digest")
    )
    if (
        source_binding.get("source_class") != "U0_VALIDATED_JD_PAYLOAD"
        or source_binding.get("inline_jd_available") is not True
        or source_binding.get("inline_jd_digest") != expected
    ):
        raise L1CognitivePairedShadowCaptureError(
            f"{arm} v2 capsule is not bound to the frozen U0 JD payload"
        )


def capture_l1_cognitive_paired_shadow(
    *,
    campaign_root: Path,
    pair_id: str,
    control_run_root: Path,
    candidate_run_root: Path,
    frozen_input_receipt: Mapping[str, Any],
    config_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and persist one all-attempts-preserving technical paired receipt."""

    campaign = Path(campaign_root).resolve()
    frozen_input = dict(frozen_input_receipt)
    config = dict(config_receipt)
    validate_l1_cognitive_pair_input_receipt(frozen_input)
    validate_l1_cognitive_pair_config_receipt(config)
    input_digest = str(frozen_input["input_digest"])
    provider_digest = str(config["provider_model_config_digest"])
    tool_digest = str(config["tool_config_digest"])
    _verify_run_binding(
        run_root=control_run_root,
        frozen_input_receipt=frozen_input,
        config_receipt=config,
        arm="control",
    )
    _verify_run_binding(
        run_root=candidate_run_root,
        frozen_input_receipt=frozen_input,
        config_receipt=config,
        arm="candidate",
    )
    control, control_receipt = _arm_row(
        campaign_root=campaign,
        run_root=control_run_root,
        expected_arm=L1_COGNITIVE_V2_CONTROL_ARM,
    )
    candidate, candidate_receipt = _arm_row(
        campaign_root=campaign,
        run_root=candidate_run_root,
        expected_arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
    )
    control_v2 = _read_json(
        Path(control_run_root) / sr.FILENAME_L1_PLANNING_V2_CAPSULE,
        label="control v2 capsule",
    )
    candidate_v2 = _read_json(
        Path(candidate_run_root) / sr.FILENAME_L1_PLANNING_V2_CAPSULE,
        label="candidate v2 capsule",
    )
    control_jd = (control_v2.get("source_binding") or {}).get("jd_hash")
    candidate_jd = (candidate_v2.get("source_binding") or {}).get("jd_hash")
    if not control_jd or control_jd != candidate_jd:
        raise L1CognitivePairedShadowCaptureError(
            "paired runs do not share a frozen JD"
        )
    _verify_u0_jd_binding(
        v2_capsule=control_v2,
        frozen_input_receipt=frozen_input,
        arm="control",
    )
    _verify_u0_jd_binding(
        v2_capsule=candidate_v2,
        frozen_input_receipt=frozen_input,
        arm="candidate",
    )
    if control_receipt["treatment"]["assignment_origin"] != "U0_VALIDATED_INGRESS":
        raise L1CognitivePairedShadowCaptureError("control treatment was not U0-bound")
    if candidate_receipt["treatment"]["assignment_origin"] != "U0_VALIDATED_INGRESS":
        raise L1CognitivePairedShadowCaptureError(
            "candidate treatment was not U0-bound"
        )
    pairs = [
        {
            "pair_id": str(pair_id),
            "frozen_input_digest": input_digest,
            "provider_model_config_digest": provider_digest,
            "tool_config_digest": tool_digest,
            "control": control,
            "candidate": candidate,
        }
    ]
    protocol = load_l1_cognitive_outcome_protocol()
    paired = build_l1_cognitive_paired_shadow_receipt(protocol=protocol, pairs=pairs)
    write_l1_cognitive_paired_shadow_receipt(
        output_path=campaign / "l1_cognitive_paired_shadow_receipt.json",
        receipt=paired,
        protocol=protocol,
        pairs=pairs,
    )
    sr.write_stage_receipt(
        campaign / "l1_cognitive_pair_input.json", frozen_input_receipt
    )
    sr.write_stage_receipt(campaign / "l1_cognitive_pair_config.json", config_receipt)
    return paired


__all__ = [
    "L1CognitivePairedShadowCaptureError",
    "build_l1_cognitive_pair_config_receipt",
    "build_l1_cognitive_pair_input_receipt",
    "build_l1_cognitive_shadow_run_binding",
    "capture_l1_cognitive_paired_shadow",
    "L1_COGNITIVE_PAIR_CONFIG_SCHEMA_VERSION",
    "L1_COGNITIVE_PAIR_INPUT_SCHEMA_VERSION",
    "L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME",
    "L1_COGNITIVE_SHADOW_RUN_BINDING_SCHEMA_VERSION",
    "load_l1_cognitive_shadow_run_binding",
    "validate_l1_cognitive_pair_config_receipt",
    "validate_l1_cognitive_pair_input_receipt",
    "validate_l1_cognitive_shadow_run_binding",
]
