"""Section-lane hooks for canonical L2 authority and compatibility mirrors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apps_rg.runtime.section_l2_spine_receipt import (
    COMPILED_PROMPT_ARTIFACT,
    L2_EXECUTION_PACKET_ARTIFACT,
    assert_section_l2_spine_preconditions,
    build_l2_execution_packet_for_section,
    emit_l2_execution_packet_artifact,
    emit_section_l2_spine_receipt_artifacts,
)


def _product_visible(runtime_payload: dict[str, Any]) -> bool:
    return bool(runtime_payload.get("product_visible", True))


def _resolve_authority_model_lane(
    *,
    section_id: str,
    provider_lane: str,
    model_lane: str | None,
) -> str:
    """Resolve the model before E1/E2 signs the execution packet.

    Provider routing can change before a lane starts (including a governed
    Anthropic-limit route).  Signing the static PA compatibility model and
    resolving the real provider model afterwards produced packets that named
    Claude while the request executed OpenAI.  The authority packet must bind
    the same provider-specific model that the section call will use.
    """

    explicit = str(model_lane or "").strip()
    if explicit:
        return explicit
    provider = str(provider_lane or "").strip().lower()
    from apps_rg.runtime.section_model_limits import (
        external_openai_generation_model,
        resolve_section_generation_model,
    )

    if provider == "external_openai":
        return external_openai_generation_model(section_id=section_id)
    return resolve_section_generation_model(section_id)


def prepare_section_l2_before_provider(
    artifact_dir: Path,
    section_id: str,
    runtime_payload: dict[str, Any],
    *,
    provider_lane: str,
    model_lane: str | None = None,
) -> dict[str, Any]:
    """Run E1/E2 before a product section provider call.

    Non-product/fixture lanes retain the legacy mirror packet. Product-visible
    lanes cannot reach the provider until signed U0/L0/PA authority validates.
    """
    runtime_payload.setdefault("compiled_prompt_artifact_ref", COMPILED_PROMPT_ARTIFACT)
    assert_section_l2_spine_preconditions(runtime_payload, artifact_dir)

    if _product_visible(runtime_payload):
        from apps_rg.runtime.section_l2_authority import prepare_section_l2_authority

        resolved_model_lane = _resolve_authority_model_lane(
            section_id=section_id,
            provider_lane=provider_lane,
            model_lane=model_lane,
        )
        packet = prepare_section_l2_authority(
            artifact_dir,
            section_id,
            runtime_payload,
            provider_lane=provider_lane,
            model_lane=resolved_model_lane,
        )
    else:
        packet = build_l2_execution_packet_for_section(
            section_id=section_id,
            runtime_payload=runtime_payload,
            provider_lane=provider_lane,
            model_lane=model_lane,
        )
        emit_l2_execution_packet_artifact(artifact_dir, packet)
        runtime_payload["l2_execution_packet"] = packet
        runtime_payload["l2_execution_packet_ref"] = L2_EXECUTION_PACKET_ARTIFACT

    from apps_rg.runtime.spine.spine_span_emit import emit_spine_span_event

    emit_spine_span_event(
        artifact_dir,
        layer_key="L2",
        binding_seam=(
            "apps_rg/runtime/section_l2_authority.py"
            if _product_visible(runtime_payload)
            else "apps_rg/runtime/section_l2_spine_receipt.py"
        ),
        status="authority_validated"
        if _product_visible(runtime_payload)
        else "legacy_mirror",
        product_visible=_product_visible(runtime_payload),
    )
    return packet


def finalize_section_l2_after_output(
    artifact_dir: Path,
    section_id: str,
    runtime_payload: dict[str, Any],
    *,
    section_output_ref: str | None = None,
    l2_output_ref: str = "l2_output.json",
) -> dict[str, Path]:
    """Seal observed E3 output and derive section mirrors from the canonical bundle.

    The Apps RG-local L1 cognitive projection and gate run after an L2 result
    exists but before its seal and exit mirror. The projection adds only
    source-bound non-display C0 gap diagnostics; it never changes provider
    content, display content, claims, evidence, routing, retries, or promotion.
    The following gate verifies that those diagnostics remain bound to L2 and
    also prevents an unsafe X3 mirror from authorizing finalization when a
    source-bound hard user-goal constraint or critical L1 requirement remains
    unresolved.
    """
    from apps_rg.runtime.contracts.l1_cognitive_output_disposition import (
        apply_l1_cognitive_output_disposition_to_x3_mirror,
        apply_l1_cognitive_output_projection,
        emit_l1_cognitive_output_disposition,
    )

    apply_l1_cognitive_output_projection(
        artifact_dir=artifact_dir,
        section_id=section_id,
        runtime_payload=runtime_payload,
    )
    emit_l1_cognitive_output_disposition(
        artifact_dir=artifact_dir,
        section_id=section_id,
        runtime_payload=runtime_payload,
    )
    if _product_visible(runtime_payload):
        from apps_rg.runtime.section_l2_authority import finalize_section_l2_authority

        paths = finalize_section_l2_authority(
            artifact_dir,
            section_id,
            runtime_payload,
            section_output_ref=section_output_ref,
            l2_output_ref=l2_output_ref,
        )
    else:
        paths = emit_section_l2_spine_receipt_artifacts(
            artifact_dir,
            section_id=section_id,
            runtime_payload=runtime_payload,
            l2_output_ref=l2_output_ref,
            section_output_ref=section_output_ref,
        )

    from apps_rg.runtime.graph_skills_run_artifacts import (
        persist_graph_skills_lane_artifacts,
    )

    persist_graph_skills_lane_artifacts(
        artifact_dir,
        section_id=section_id,
        runtime_payload=runtime_payload,
    )
    apply_l1_cognitive_output_disposition_to_x3_mirror(artifact_dir)

    from apps_rg.runtime.spine.section_x3_finalize import (
        finalize_section_spine_exit_after_sealed_l2,
    )

    finalize_section_spine_exit_after_sealed_l2(
        artifact_dir,
        section_id=section_id,
        runtime_payload=runtime_payload,
    )
    return paths


__all__ = ["finalize_section_l2_after_output", "prepare_section_l2_before_provider"]
