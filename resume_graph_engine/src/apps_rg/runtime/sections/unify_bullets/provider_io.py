"""Provider retry/parsing, mock construction, quality inference, and prompt compilation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.offline_contract_status import OFFLINE_CONTRACT_STUB_RUNTIME_STATUS
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import infer_product_quality_blocked_or_mock
from apps_rg.runtime.sections.section_generation import generate_section, tag_reasoning_lane
from apps_rg.runtime.sections.unify_bullets_pa import compile_unify_bullets_prompt
from apps_rg.runtime.validators.unify_bullets_x2 import UNIFY_BULLET_IDS
from ._parent import parent_attr
from .lane_constants import (
    LANE_KEY,
    PROMPT_TEMPLATE,
    REPO_ROOT,
    UNIFY_MAX_OUTPUT_TOKENS,
    extract_unify_employment,
    sha16,
)
from .metric_surfaces import _authoritative_selected_fact_plan, _selected_fact_plan_has_runtime_facts
from .repairs import normalize_unify_parsed_without_ledger_synthesis

def parse_model_json(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
                strip_employment_bullet_intensity_model,
            )

            return strip_employment_bullet_intensity_model(parsed), ""
    except json.JSONDecodeError as exc:
        return None, f"JSON parse failed: {exc}"
    return None, "Model output was not a JSON object."


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
                "Use bullet_id values bul_unify_001..bul_unify_006 exactly. "
                "Include a non-empty claim_ledger: every row must have non-empty claim_text and valid source_fact_ids. "
                "Include all six bullets bul_unify_001..bul_unify_006. "
                "Do NOT emit rewrite_intensity, rewrite_distribution, or HEAVY/MODERATE/LIGHT_PROTECTED fields."
            ),
        },
    ]
    repair_payload = {
        **provider_payload,
        "messages": repair_messages,
        "max_tokens": UNIFY_MAX_OUTPUT_TOKENS,
        "anthropic_workload_kind": "REPAIR",
    }
    result = parent_attr("generate_section", generate_section)(parent_attr("tag_reasoning_lane", tag_reasoning_lane)(repair_payload, LANE_KEY))
    if result.runtime_generation_status != "REAL_LLM":
        return raw_output, None, parse_error
    new_raw = result.raw_model_output
    new_parsed, new_err = parse_model_json(new_raw)
    return new_raw, new_parsed, new_err


def _clamp_mock_bullet_text(text: str, *, max_chars: int) -> str:
    """Keep offline mock bullets within line-discipline paragraph cap."""
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    head = cleaned[: max_chars - 3].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{head}..."


def build_mock_output(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    from apps_rg.runtime.validators.bullet_line_discipline_x2 import DEFAULT_BULLET_MAX_CHARS

    by_id = {f["fact_id"]: f for f in runtime_payload["selected_fact_plan"]["facts"]}
    bullets = []
    claim_ledger = []
    for bid in UNIFY_BULLET_IDS:
        fact = by_id[bid]
        text = str(fact["claim_text"] or "")
        if ": " in text:
            text = text.split(": ", 1)[-1].strip()
        if bid == "bul_unify_001":
            text = (
                "Designed and operationalized a governed agentic AI platform for regulated enterprise "
                "workflows, combining policy gating and validation controls for traceable production delivery."
            )
        elif bid == "bul_unify_006":
            text = (
                "Productized agentic AI platform services, generating $22M IP-led revenue and 20% "
                "gross-margin expansion while scaling the ML organization from 8 to 28 engineers and "
                "compressing delivery from six months to three weeks."
            )
        else:
            text = _clamp_mock_bullet_text(text, max_chars=DEFAULT_BULLET_MAX_CHARS)
        metric_ids = [bid]
        if fact.get("metric_raw"):
            metric_ids.append(f"{bid}_metric_{parent_attr("sha16", sha16)(fact['metric_raw'])[:8]}")
        bullets.append(
            {
                "bullet_id": bid,
                "bullet_text": text,
                "has_metric": fact.get("has_metric", False),
                "metric_raw": fact.get("metric_raw") or None,
                "source_fact_ids": metric_ids,
            }
        )
        claim_ledger.append({"claim_text": text, "source_fact_ids": metric_ids})

    return {
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


def bullets_display_text(bullets: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {b.get('bullet_id')}: {b.get('bullet_text', '')}" for b in bullets)


def enrich_unify_parsed_for_x2(
    parsed: dict[str, Any] | None,
    *,
    coverage: dict[str, Any],
    input_payload_hash: str,
    allowed_fact_ids: set[str],
) -> dict[str, Any] | None:
    if parsed is None:
        return None
    from apps_rg.runtime.reasoning.employment_bullet_output_sanitize import (
        strip_employment_bullet_intensity_model,
    )

    parsed = strip_employment_bullet_intensity_model(parsed)
    enriched = dict(parsed)
    enriched["text_claim_coverage"] = coverage
    output_body = {
        key: enriched[key]
        for key in (
            "bullets",
            "selected_fact_plan",
            "claim_ledger",
            "jd_alignment",
            "gap_notes",
            "change_log",
            "self_check",
            "text_claim_coverage",
        )
        if key in enriched
    }
    enriched["input_payload_hash"] = input_payload_hash
    enriched["output_payload_hash"] = parent_attr("sha16", sha16)(json.dumps(output_body, sort_keys=True))
    enriched["claim_ledger_hash"] = parent_attr("sha16", sha16)(json.dumps(enriched.get("claim_ledger") or [], sort_keys=True))
    enriched["allowed_fact_ids_hash"] = parent_attr("sha16", sha16)(json.dumps(sorted(allowed_fact_ids), sort_keys=True))
    return enriched


def infer_unify_bullets_product_quality(
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
        pass_reason="REAL_LLM output passed all deterministic Unify bullet gates.",
    )


def build_prompt_messages(runtime_payload: dict[str, Any]) -> list[dict[str, str]]:
    """PA-assembled messages via ``section_prompt_adapter`` + unify bullets template."""
    run_id = str(runtime_payload.get("run_id") or "unify_bullets_prompt_build")
    compiled = parent_attr("compile_unify_bullets_prompt", compile_unify_bullets_prompt)(runtime_payload, run_id=run_id)
    return compiled.artifact.messages
