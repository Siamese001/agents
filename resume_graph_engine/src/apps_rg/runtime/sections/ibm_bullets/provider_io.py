"""IBM bullets provider retry/parsing helpers, mock builder, and quality inference."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.section_proof.lane_proof_accounting import generation_status_allows_json_parse
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import infer_product_quality_blocked_or_mock
from apps_rg.runtime.sections.section_generation import generate_section, tag_reasoning_lane
from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_BULLET_IDS
from ._parent import parent_attr
from .frozen_allocation import normalize_parsed_output
from .lane_constants import (
    DEFAULT_INTENSITY_BY_BULLET,
    IBM_MAX_OUTPUT_TOKENS,
    LANE_KEY,
    extract_ibm_employment,
    sha16,
)

def retry_provider_for_parse(
    messages: list[dict[str, str]],
    provider_payload: dict[str, Any],
    raw_output: str,
    parse_error: str,
) -> tuple[str, dict[str, Any] | None, str]:
    repair_messages = [
        *messages,
        {"role": "assistant", "content": raw_output},
        {
            "role": "user",
            "content": (
                f"JSON INVALID: {parse_error}. Return a NEW complete compact JSON object only. "
                f"Use bullet_id values {', '.join(IBM_BULLET_IDS)} exactly. "
                f"Include non-empty claim_ledger and rewrite_distribution with total={len(IBM_BULLET_IDS)}, HEAVY=0."
            ),
        },
    ]
    repair_payload = {
        **provider_payload,
        "messages": repair_messages,
        "max_tokens": IBM_MAX_OUTPUT_TOKENS,
        "anthropic_workload_kind": "REPAIR",
    }
    result = parent_attr("generate_section", generate_section)(parent_attr("tag_reasoning_lane", tag_reasoning_lane)(repair_payload, LANE_KEY))
    if not generation_status_allows_json_parse(result.runtime_generation_status):
        return raw_output, None, parse_error
    new_raw = result.raw_model_output
    new_parsed, new_err = parse_model_json(new_raw)
    return new_raw, new_parsed, new_err


def parse_model_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, ""
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failed: {exc}"
    return None, "Model output was not a JSON object."


def build_mock_output(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    by_id = {f["fact_id"]: f for f in runtime_payload["selected_fact_plan"]["facts"]}
    bullets = []
    claim_ledger = []
    for bid in IBM_BULLET_IDS:
        fact = by_id[bid]
        intensity = DEFAULT_INTENSITY_BY_BULLET[bid]
        text = fact["claim_text"]
        metric_ids = [bid]
        if fact.get("metric_raw"):
            metric_ids.append(f"{bid}_metric_{sha16(fact['metric_raw'])[:8]}")
        bullets.append(
            {
                "bullet_id": bid,
                "bullet_text": text,
                "rewrite_intensity": intensity,
                "has_metric": fact.get("has_metric", False),
                "metric_raw": fact.get("metric_raw") or None,
                "source_fact_ids": metric_ids,
            }
        )
        claim_ledger.append({"claim_text": text, "source_fact_ids": metric_ids})

    from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
        strip_employment_bullet_intensity_model,
    )

    return strip_employment_bullet_intensity_model(
        {
            "bullets": bullets,
            "selected_fact_plan": runtime_payload["selected_fact_plan"],
            "claim_ledger": claim_ledger,
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "gap_notes": [],
            "change_log": [{"operation": "offline_contract_stub", "reason": "APPS_RG_PROVIDER_MODEL_OFFLINE_CONTRACT_STUB"}],
            "self_check": {
                "bullet_count_valid": True,
                "no_cross_contamination": True,
                "metrics_preserved": True,
            },
        }
    )


def infer_product_quality(
    runtime_generation_status: str,
    x2_gates: list[dict[str, Any]],
    *,
    artifact_dir: Path | None = None,
) -> tuple[str, str]:
    from apps_rg.runtime.section_repair_lane_integration import infer_lane_product_quality

    return infer_lane_product_quality(
        runtime_generation_status,
        x2_gates,
        artifact_dir=artifact_dir,
        pass_reason="REAL_LLM output passed all deterministic IBM bullet gates.",
    )


def bullets_display_text(bullets: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {b.get('bullet_id')}: {b.get('bullet_text', '')}" for b in bullets)
