"""One-spine section RuntimeExhaustBundle — ExitDispositionReceipt → exhaust → L6 handoff (Wave 7).

Emits spine-aligned ``runtime_exhaust_bundle.json`` only after canonical Exit. L6 consumes
post-run exhaust only; no current-run rescue. Not product certification or durable UWG write.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.runtime.spine.exit_artifacts import EXIT_DISPOSITION_RECEIPT_ARTIFACT
from apps_rg.runtime.spine.front_contracts import fixture_dev_bypass_active
from apps_rg.runtime.section_l2_spine_receipt import SEALED_L2_ARTIFACT
from apps_rg.runtime.section_spine_terminology import CANONICAL_SPINE_CHAIN

RUNTIME_EXHAUST_BUNDLE_ARTIFACT = "runtime_exhaust_bundle.json"
RUNTIME_EXHAUST_RECEIPT_ARTIFACT = "runtime_exhaust_receipt.json"
L6_SHADOW_HANDOFF_RECEIPT_ARTIFACT = "l6_shadow_handoff_receipt.json"
L6_V40_SHADOW_EVAL_PACKAGE_ARTIFACT = "l6_v40_shadow_eval_package.json"
L6_V40_SHADOW_EVAL_SPANS_ARTIFACT = "l6_v40_shadow_eval_spans.json"

OBSERVED_CHAIN_WITH_EXHAUST: tuple[str, ...] = (
    "CLI",
    "canonical_dispatch.section_branch",
    "section_front_spine_bridge",
    "U0",
    "L1",
    "L0",
    "proof_pool_resolver",
    "section_fec_bridge",
    "section_PA",
    "section_L2_execution_packet",
    "section_L2_sealed",
    "section_Exit_disposition_receipt",
    "section_RuntimeExhaustBundle",
    "section_L6_shadow_handoff",
    "section_L6_shadow",
)


class SectionRuntimeExhaustPreconditionError(RuntimeError):
    """Raised when exhaust/L6 handoff runs without ExitDispositionReceipt."""


def runtime_exhaust_kill_switch_enabled() -> bool:
    return os.environ.get("APPS_RG_SECTION_RUNTIME_EXHAUST_KILL_SWITCH", "1").strip() not in (
        "0",
        "false",
        "no",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_exists(artifact_dir: Path, name: str) -> bool:
    return bool(name) and (artifact_dir / name).is_file()


def _load_json(artifact_dir: Path, name: str) -> dict[str, Any]:
    path = artifact_dir / name
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    nested = value.get("payload")
    return dict(nested) if isinstance(nested, dict) else value


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _section_runtime_identity(
    *,
    section_id: str,
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, str]:
    """Resolve the lane identity already present at the nested core boundary."""

    dispatch = _load_json(artifact_dir, "lane_dispatch_attempt.json")
    canonical = dispatch.get("identity")
    canonical = dict(canonical) if isinstance(canonical, dict) else {}
    from apps_rg.runtime.orchestration.canonical_identity_context import (
        current_canonical_run_identity,
    )

    # Section-only and patch-run entrypoints do not have the outer modular
    # dispatcher receipt. Their validated product identity remains available at
    # the app-owned dynamic boundary while the native exhaust is emitted.
    canonical = {**current_canonical_run_identity(), **canonical}
    core_identity = _payload(_load_json(artifact_dir, "runtime_identity_envelope.json"))
    route = _payload(_load_json(artifact_dir, "route_contract.json"))
    exit_receipt = _load_json(artifact_dir, EXIT_DISPOSITION_RECEIPT_ARTIFACT)
    lane_run_id = _first_text(
        runtime_payload.get("run_id"), exit_receipt.get("run_id"), section_id
    )
    parent_run_id = _first_text(
        runtime_payload.get("parent_run_id"),
        canonical.get("parent_run_id"),
        core_identity.get("run_id"),
    )
    child_run_id = _first_text(runtime_payload.get("child_run_id"), lane_run_id)
    section_attempt_id = _first_text(
        runtime_payload.get("section_attempt_id"),
        f"{section_id}:{child_run_id}:attempt:1" if child_run_id else "",
    )
    return {
        "request_id": _first_text(
            runtime_payload.get("request_id"),
            canonical.get("request_id"),
            core_identity.get("request_id"),
            route.get("request_id"),
        ),
        "run_id": lane_run_id,
        "parent_run_id": parent_run_id,
        "child_run_id": child_run_id,
        "section_attempt_id": section_attempt_id,
        "session_id": _first_text(
            runtime_payload.get("session_id"),
            canonical.get("child_run_id"),
            parent_run_id,
        ),
        "tenant_id": _first_text(
            runtime_payload.get("tenant_id"),
            canonical.get("tenant_id"),
            "default",
        ),
        "trace_root": _first_text(
            runtime_payload.get("trace_root"),
            canonical.get("trace_root"),
            core_identity.get("trace_root"),
            route.get("trace_root"),
        ),
        "policy_hash": _first_text(
            runtime_payload.get("policy_hash"),
            canonical.get("policy_hash"),
            route.get("policy_hash"),
            "no-policy",
        ),
        "blueprint_hash": _first_text(
            runtime_payload.get("blueprint_hash"),
            canonical.get("blueprint_hash"),
            route.get("blueprint_hash"),
            "no-blueprint",
        ),
        "replay_key": _first_text(
            runtime_payload.get("replay_key"),
            route.get("replay_key"),
            f"section:{section_id}:{child_run_id}",
        ),
    }
def _repo_rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _build_artifact_inventory(artifact_dir: Path, *, section_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for p in sorted(artifact_dir.iterdir()):
        if p.is_file():
            rows.append({"name": p.name, "kind": "file", "section_id": section_id})
    post_rt = artifact_dir / "post_runtime"
    if post_rt.is_dir():
        for p in sorted(post_rt.iterdir()):
            if p.is_file():
                rows.append({"name": f"post_runtime/{p.name}", "kind": "file", "section_id": section_id})
    return rows


def assert_section_runtime_exhaust_preconditions(
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
    *,
    product_visible: bool | None = None,
    fixture_dev_only_bypass: bool = False,
    non_product_certified: bool = False,
) -> None:
    if fixture_dev_only_bypass or fixture_dev_bypass_active():
        return
    if non_product_certified:
        return
    pv = product_visible if product_visible is not None else bool(
        runtime_payload.get("product_visible", True)
    )
    if not pv or not runtime_exhaust_kill_switch_enabled():
        return
    edr_ref = str(runtime_payload.get("exit_disposition_receipt_ref") or EXIT_DISPOSITION_RECEIPT_ARTIFACT)
    if not _artifact_exists(artifact_dir, edr_ref):
        raise SectionRuntimeExhaustPreconditionError(
            f"product-visible RuntimeExhaustBundle requires {edr_ref} before exhaust emission"
        )
    if runtime_payload.get("runtime_exhaust_bypass_without_exit") is True:
        raise SectionRuntimeExhaustPreconditionError(
            "RuntimeExhaustBundle without ExitDispositionReceipt is forbidden in product-visible mode"
        )


def assert_section_l6_may_consume_exhaust(
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
    *,
    product_visible: bool | None = None,
) -> None:
    """L6 shadow must not run before post-run exhaust boundary is sealed."""
    if fixture_dev_bypass_active():
        return
    pv = product_visible if product_visible is not None else bool(
        runtime_payload.get("product_visible", True)
    )
    if not pv or not runtime_exhaust_kill_switch_enabled():
        return
    if not _artifact_exists(artifact_dir, RUNTIME_EXHAUST_BUNDLE_ARTIFACT):
        raise SectionRuntimeExhaustPreconditionError(
            "L6 shadow handoff blocked: runtime_exhaust_bundle.json must exist before L6"
        )
    if not _artifact_exists(artifact_dir, L6_SHADOW_HANDOFF_RECEIPT_ARTIFACT):
        raise SectionRuntimeExhaustPreconditionError(
            "L6 shadow handoff blocked: l6_shadow_handoff_receipt.json must exist before L6"
        )


def build_runtime_exhaust_bundle_for_section(
    *,
    section_id: str,
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    edr = _load_json(artifact_dir, EXIT_DISPOSITION_RECEIPT_ARTIFACT)
    identity = _section_runtime_identity(
        section_id=section_id,
        runtime_payload=runtime_payload,
        artifact_dir=artifact_dir,
    )
    sealed_ref = str(runtime_payload.get("sealed_l2_artifact_ref") or SEALED_L2_ARTIFACT)
    x3_from_exit = edr.get("x3_disposition") if isinstance(edr.get("x3_disposition"), dict) else {}
    inventory = _build_artifact_inventory(artifact_dir, section_id=section_id)

    trace_refs: dict[str, str | None] = {}
    for name in (
        "route_contract.json",
        "final_evidence_contract_bridge.json",
        "l2_execution_packet.json",
        "exit_review_packet.json",
        "provider_request.json",
        "provider_response.json",
        "x2_gate_outputs.json",
        "x1d_llm_judge_outputs.json",
    ):
        p = artifact_dir / name
        trace_refs[name] = _repo_rel(repo_root, p) if p.is_file() else None

    bundle = {
        "schema_version": "section_runtime_exhaust_bundle_v1",
        "generated_at_utc": _utc_now(),
        "contract_type": "RuntimeExhaustBundle",
        "section_id": section_id,
        **identity,
        "producer_stage": "Exit",
        "consumer_stage": "L6",
        "exit_disposition_receipt_ref": EXIT_DISPOSITION_RECEIPT_ARTIFACT,
        "sealed_l2_artifact_ref": sealed_ref,
        "l2_execution_packet_ref": str(
            runtime_payload.get("l2_execution_packet_ref") or "l2_execution_packet.json"
        ),
        "section_x3_disposition_ref": "x3_disposition.json",
        "section_x3_authoritative": False,
        "canonical_exit_authority_ref": EXIT_DISPOSITION_RECEIPT_ARTIFACT,
        "x3_disposition": dict(x3_from_exit),
        "x3_code": str(x3_from_exit.get("x3_code") or edr.get("x3_code") or "UNKNOWN"),
        "artifact_inventory": inventory,
        "artifact_inventory_count": len(inventory),
        "l6_v40_shadow_eval_package_ref": L6_V40_SHADOW_EVAL_PACKAGE_ARTIFACT,
        "l6_v40_shadow_eval_spans_ref": L6_V40_SHADOW_EVAL_SPANS_ARTIFACT,
        "trace_refs": trace_refs,
        "proof_refs": {
            "exit_spine_receipt": "exit_spine_receipt.json"
            if _artifact_exists(artifact_dir, "exit_spine_receipt.json")
            else None,
            "l2_spine_receipt": "l2_spine_receipt.json"
            if _artifact_exists(artifact_dir, "l2_spine_receipt.json")
            else None,
        },
        "runtime_terminal_boundary": "post_exit_disposition",
        "durable_commit_occurred": False,
        "uwg_commit_occurred": False,
        "product_certification": "NOT_CLAIMED",
        "spine_runtime_exhaust_bundle_claimed": True,
        "explicit_non_claims": [
            "L6 is post-run shadow only; cannot mutate or rescue current run",
            "not product certification",
            "not durable UWG/L4 commit",
        ],
    }
    identity_seed = {
        "section_id": section_id,
        "parent_run_id": identity["parent_run_id"],
        "child_run_id": identity["child_run_id"],
        "section_attempt_id": identity["section_attempt_id"],
    }
    identity_digest = hashlib.sha256(
        json.dumps(identity_seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    bundle["runtime_exhaust_bundle_id"] = f"reb:{identity_digest[:24]}"
    bundle["runtime_exhaust_bundle_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return bundle


def build_runtime_exhaust_receipt(
    *,
    section_id: str,
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    fixture_dev = bool(fixture_dev_bypass_active())
    precond = _artifact_exists(artifact_dir, EXIT_DISPOSITION_RECEIPT_ARTIFACT) and _artifact_exists(
        artifact_dir, RUNTIME_EXHAUST_BUNDLE_ARTIFACT
    )
    return {
        "schema_version": "runtime_exhaust_receipt_v1",
        "generated_at_utc": _utc_now(),
        "plan_slug": "one-canonical-spine",
        "wave": "7",
        "lane": section_id,
        "section_id": section_id,
        "run_id": str(runtime_payload.get("run_id") or ""),
        "product_visible": bool(runtime_payload.get("product_visible", True)),
        "fixture_dev_only": fixture_dev,
        "non_product_certified": fixture_dev,
        "spine_mode": "section_lane_modular",
        "exhaust_alignment_mode": "section_runtime_exhaust_spine_receipt",
        "exhaust_spine_status": "PASS" if precond else "FAIL",
        "runtime_exhaust_bundle_ref": RUNTIME_EXHAUST_BUNDLE_ARTIFACT,
        "exit_disposition_receipt_ref": EXIT_DISPOSITION_RECEIPT_ARTIFACT,
        "sealed_l2_artifact_ref": str(runtime_payload.get("sealed_l2_artifact_ref") or SEALED_L2_ARTIFACT),
        "l6_v40_shadow_eval_package_ref": L6_V40_SHADOW_EVAL_PACKAGE_ARTIFACT,
        "l6_v40_shadow_eval_spans_ref": L6_V40_SHADOW_EVAL_SPANS_ARTIFACT,
        "l6_v40_shadow_eval_enabled": os.environ.get("APPS_RG_L6_V40_SHADOW_EVAL", "").strip()
        in {"1", "true", "TRUE", "yes", "YES", "on", "ON"},
        "durable_commit_occurred": False,
        "product_certification": "NOT_CLAIMED",
        "runtime_exhaust_kill_switch_enabled": runtime_exhaust_kill_switch_enabled(),
        "observed_chain": list(OBSERVED_CHAIN_WITH_EXHAUST),
        "canonical_spine_target": list(CANONICAL_SPINE_CHAIN),
    }


def build_l6_shadow_handoff_receipt(
    *,
    section_id: str,
    runtime_payload: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Receipt proving L6 may only consume post-run exhaust (no current-run rescue)."""
    exhaust = _load_json(artifact_dir, RUNTIME_EXHAUST_BUNDLE_ARTIFACT)
    return {
        "schema_version": "l6_shadow_handoff_receipt_v1",
        "generated_at_utc": _utc_now(),
        "contract_type": "L6ShadowHandoffReceipt",
        "section_id": section_id,
        "run_id": str(runtime_payload.get("run_id") or ""),
        "runtime_exhaust_bundle_ref": RUNTIME_EXHAUST_BUNDLE_ARTIFACT,
        "exit_disposition_receipt_ref": EXIT_DISPOSITION_RECEIPT_ARTIFACT,
        "l6_shadow_eval_package_ref": "l6_shadow_eval_package.json",
        "l6_v40_shadow_eval_package_ref": L6_V40_SHADOW_EVAL_PACKAGE_ARTIFACT,
        "l6_v40_shadow_eval_spans_ref": L6_V40_SHADOW_EVAL_SPANS_ARTIFACT,
        "l6_v40_g28_g29_receipts_required": True,
        "handoff_phase": "post_runtime_exhaust_only",
        "consumed_after_exit_disposition": True,
        "consumed_after_runtime_exhaust_bundle": True,
        "no_l6_current_run_rescue_assertion": True,
        "no_l6_current_run_mutation_assertion": True,
        "l6_can_change_x3": False,
        "l6_can_change_exit_disposition": False,
        "x3_authoritative_ref": EXIT_DISPOSITION_RECEIPT_ARTIFACT,
        "observed_x3_code": str(exhaust.get("x3_code") or ""),
        "durable_commit_occurred": False,
        "product_certification": "NOT_CLAIMED",
        "explicit_non_claims": [
            "L6 shadow does not rescue or mutate the current run",
            "not product certification",
        ],
    }


def emit_section_runtime_exhaust_spine_artifacts(
    artifact_dir: Path,
    *,
    section_id: str,
    runtime_payload: dict[str, Any],
    repo_root: Path,
) -> dict[str, Path]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    assert_section_runtime_exhaust_preconditions(runtime_payload, artifact_dir)

    bundle = build_runtime_exhaust_bundle_for_section(
        section_id=section_id,
        runtime_payload=runtime_payload,
        artifact_dir=artifact_dir,
        repo_root=repo_root,
    )
    p_bundle = artifact_dir / RUNTIME_EXHAUST_BUNDLE_ARTIFACT
    p_bundle.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    receipt = build_runtime_exhaust_receipt(
        section_id=section_id,
        runtime_payload=runtime_payload,
        artifact_dir=artifact_dir,
    )
    p_receipt = artifact_dir / RUNTIME_EXHAUST_RECEIPT_ARTIFACT
    p_receipt.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    handoff = build_l6_shadow_handoff_receipt(
        section_id=section_id,
        runtime_payload=runtime_payload,
        artifact_dir=artifact_dir,
    )
    p_handoff = artifact_dir / L6_SHADOW_HANDOFF_RECEIPT_ARTIFACT
    p_handoff.write_text(json.dumps(handoff, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # The outer app spine later writes its own transport receipt with the
    # legacy filename.  Preserve the lane-owned, identity-complete exhaust
    # record before that happens so L6 and Apps Eval bind the correct source.
    from apps_rg.runtime.section_evidence_package import (
        mirror_preferred_section_shim_names,
    )

    mirror_preferred_section_shim_names(artifact_dir)

    runtime_payload["runtime_exhaust_bundle_ref"] = RUNTIME_EXHAUST_BUNDLE_ARTIFACT
    runtime_payload["runtime_exhaust_receipt_ref"] = RUNTIME_EXHAUST_RECEIPT_ARTIFACT
    runtime_payload["l6_shadow_handoff_receipt_ref"] = L6_SHADOW_HANDOFF_RECEIPT_ARTIFACT
    runtime_payload["l6_post_runtime_boundary_sealed"] = True

    from apps_rg.runtime.spine.spine_span_emit import (
        emit_spine_span_coverage_receipt,
        emit_spine_span_event,
    )

    product_visible = bool(runtime_payload.get("product_visible", True))
    emit_spine_span_event(
        artifact_dir,
        layer_key="L6",
        binding_seam="apps_rg/runtime/spine/governed_l6_shadow_compose.py",
        product_visible=product_visible,
        extra={"handoff_phase": "post_runtime_exhaust_only"},
    )
    emit_spine_span_coverage_receipt(artifact_dir, product_visible=product_visible)

    from apps_rg.runtime.spine.governed_l6_shadow_compose import (
        GOVERNED_L6_SHADOW_MODE_SECTION,
        build_governed_l6_handoff_envelope,
    )
    from apps_rg.runtime.spine.l6_eval_before_learn_receipt import (
        build_l6_eval_before_learn_receipt,
        emit_l6_eval_before_learn_receipt,
    )

    governed_env = runtime_payload.get("governed_l6_handoff_envelope")
    if not isinstance(governed_env, dict):
        exhaust_doc = _load_json(artifact_dir, RUNTIME_EXHAUST_BUNDLE_ARTIFACT)
        governed_env = build_governed_l6_handoff_envelope(
            section_id=section_id,
            run_id=str(runtime_payload.get("run_id") or ""),
            mode=GOVERNED_L6_SHADOW_MODE_SECTION,
            runtime_exhaust_ref=RUNTIME_EXHAUST_BUNDLE_ARTIFACT,
            exit_disposition_ref=EXIT_DISPOSITION_RECEIPT_ARTIFACT,
            x3_code=str(exhaust_doc.get("x3_code") or ""),
        )
        runtime_payload["governed_l6_handoff_envelope"] = governed_env
    eval_receipt = build_l6_eval_before_learn_receipt(
        section_id=section_id,
        run_id=str(runtime_payload.get("run_id") or ""),
        governed_envelope=governed_env,
        runtime_exhaust_ref=RUNTIME_EXHAUST_BUNDLE_ARTIFACT,
        exit_disposition_ref=EXIT_DISPOSITION_RECEIPT_ARTIFACT,
    )
    emit_l6_eval_before_learn_receipt(artifact_dir, eval_receipt)
    runtime_payload["l6_eval_before_learn_receipt_ref"] = "l6_eval_before_learn_receipt.json"

    return {
        "runtime_exhaust_bundle": p_bundle,
        "runtime_exhaust_receipt": p_receipt,
        "l6_shadow_handoff_receipt": p_handoff,
    }


__all__ = [
    "L6_SHADOW_HANDOFF_RECEIPT_ARTIFACT",
    "L6_V40_SHADOW_EVAL_PACKAGE_ARTIFACT",
    "L6_V40_SHADOW_EVAL_SPANS_ARTIFACT",
    "RUNTIME_EXHAUST_BUNDLE_ARTIFACT",
    "RUNTIME_EXHAUST_RECEIPT_ARTIFACT",
    "SectionRuntimeExhaustPreconditionError",
    "assert_section_l6_may_consume_exhaust",
    "assert_section_runtime_exhaust_preconditions",
    "build_l6_shadow_handoff_receipt",
    "build_runtime_exhaust_bundle_for_section",
    "build_runtime_exhaust_receipt",
    "emit_section_runtime_exhaust_spine_artifacts",
    "runtime_exhaust_kill_switch_enabled",
]
