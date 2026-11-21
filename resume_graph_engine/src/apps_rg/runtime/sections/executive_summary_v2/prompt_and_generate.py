"""Prompt assembly (~2KB) & zero-mutation generation for executive_summary_v2 (INV-NO-POST-LLM-PROSE-MUTATORS)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from apps_rg.runtime.offline_contract_status import OFFLINE_CONTRACT_STUB_RUNTIME_STATUS
from apps_rg.runtime.section_model_limits import external_openai_generation_model, resolve_section_generation_model
from apps_rg.runtime.sections.executive_summary_context_limits import resolve_scratch_max_output_tokens
from apps_rg.runtime.sections.section_generation import build_section_request, generate_section, tag_reasoning_lane

from .evidence_firewall import APPS_RG_SRC_ROOT, LANE_KEY, sha16

TEMPLATE_PATH = APPS_RG_SRC_ROOT / "apps_rg" / "prompt_assembly" / "templates" / "executive_summary_v2.yaml"
EXEC_SUMMARY_TEMP_DEFAULT = 0.45
EXEC_SUMMARY_TEMP_RANGE = (0.35, 0.55)


@dataclass(frozen=True)
class GenerationTurnOutput:
    attempt: int
    messages: list[dict[str, str]]
    compiled_prompt: str
    prompt_hash: str
    model_name: str
    temperature: float
    runtime_generation_status: str
    raw_output: str
    parsed_output: dict[str, Any] | None
    resume_display_text: str
    claim_ledger: list[dict[str, Any]]
    parse_error: str
    provider_request_data: dict[str, Any]
    provider_result_data: dict[str, Any]


def load_v2_prompt_template() -> dict[str, Any]:
    data = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid YAML prompt template: {TEMPLATE_PATH}")
    return data


def build_v2_prompt_messages(
    *, target_company: str, target_title: str, jd_text: str, briefing_text: str,
    allowed_fact_ids_ordered: Sequence[str], compact_verified_facts: Sequence[Mapping[str, Any]],
    prior_draft: str = "", rejection_feedback: str = "",
) -> list[dict[str, str]]:
    tpl = load_v2_prompt_template()
    citable_ids: list[str] = []
    for row in compact_verified_facts:
        for cid in row.get("citable_ids") or [row.get("fact_id")]:
            if (s := str(cid or "").strip()) and s not in citable_ids:
                citable_ids.append(s)
    if not citable_ids:
        citable_ids = [str(x) for x in allowed_fact_ids_ordered[:12] if str(x).strip()]
    user_body = str(tpl.get("user_template") or "").strip().format(
        target_company=target_company, target_title=target_title,
        jd_excerpt=" ".join(str(jd_text or "").split())[:900],
        briefing_excerpt=" ".join(str(briefing_text or "").split())[:500] or "None provided.",
        allowed_fact_ids_json=json.dumps(citable_ids, ensure_ascii=False),
        verified_facts_json=json.dumps(list(compact_verified_facts), ensure_ascii=False, separators=(",", ":")),
    )
    if prior_draft and rejection_feedback:
        user_body += "\n" + str(tpl.get("rewrite_appendix_template") or "").strip().format(
            prior_draft=prior_draft.strip(), rejection_feedback=rejection_feedback.strip(),
        )
    return [{"role": "system", "content": str(tpl.get("system_prompt") or "").strip()}, {"role": "user", "content": user_body}]


def parse_strict_json_without_mutation(raw_text: str) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]], str]:
    """Parse strict model JSON without mutating a single character of resume_display_text."""
    raw = str(raw_text or "").strip()
    if not raw:
        return None, "", [], "empty_model_output"
    if raw.startswith("```"):
        raw = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", raw)).strip()
    if not raw.startswith("{") and (start := raw.find("{")) != -1 and (end := raw.rfind("}")) > start:
        raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, "", [], f"json_decode_error:{exc}"
    if not isinstance(parsed, dict):
        return None, "", [], "parsed_json_not_object"
    if not isinstance(display_raw := parsed.get("resume_display_text"), str):
        return parsed, "", [], "missing_or_non_string_resume_display_text"
    ledger = [
        {"claim_text": str(it.get("claim_text") or "").strip(), "source_fact_ids": [str(x).strip() for x in (it.get("source_fact_ids") or []) if str(x).strip()]}
        for it in (parsed.get("claim_ledger") or []) if isinstance(it, dict)
    ]
    return parsed, display_raw.strip(), ledger, ""


def _build_offline_mock_stub(compact_facts: Sequence[Mapping[str, Any]], allowed_fact_ids: set[str]) -> dict[str, Any]:
    ids = [str(f.get("fact_id") or "") for f in compact_facts if str(f.get("fact_id") or "") in allowed_fact_ids] or sorted(allowed_fact_ids)[:3] or ["exp_slalom_001"]
    s1 = "Enterprise AI and platform engineering executive directing governed multi-agent systems and cloud delivery across regulated industries."
    s2 = "Productized reusable agentic AI architectures, deterministic validation controls, and GraphRAG retrieval into enterprise production platforms."
    s3 = "Scaled high-performing engineering teams while aligning C-suite stakeholders around measurable reliability, security, and commercial adoption."
    return {
        "resume_display_text": f"{s1} {s2} {s3}",
        "claim_ledger": [
            {"claim_text": s1, "source_fact_ids": [ids[0]]},
            {"claim_text": s2, "source_fact_ids": [ids[min(1, len(ids) - 1)]]},
            {"claim_text": s3, "source_fact_ids": [ids[-1]]},
        ],
        "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False, "companion_context_used_as_proof": False},
    }


def generate_executive_summary_v2_turn(
    *, attempt: int, provider_name: str, temperature: float, input_payload_hash: str, run_id: str, artifact_dir: Path,
    target_company: str, target_title: str, jd_text: str, briefing_text: str, allowed_fact_ids: set[str],
    allowed_fact_ids_ordered: Sequence[str], compact_verified_facts: Sequence[Mapping[str, Any]],
    prior_draft: str = "", rejection_feedback: str = "",
) -> GenerationTurnOutput:
    messages = build_v2_prompt_messages(
        target_company=target_company, target_title=target_title, jd_text=jd_text, briefing_text=briefing_text,
        allowed_fact_ids_ordered=allowed_fact_ids_ordered, compact_verified_facts=compact_verified_facts,
        prior_draft=prior_draft, rejection_feedback=rejection_feedback,
    )
    compiled_prompt = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
    prompt_hash = sha16(compiled_prompt)
    bounded_temp = float(min(max(float(temperature), EXEC_SUMMARY_TEMP_RANGE[0]), EXEC_SUMMARY_TEMP_RANGE[1]))
    if str(provider_name).strip().lower() == "mock":
        raw_out = json.dumps(_build_offline_mock_stub(compact_verified_facts, allowed_fact_ids), ensure_ascii=False)
        parsed, disp, ledger, err = parse_strict_json_without_mutation(raw_out)
        return GenerationTurnOutput(
            attempt=attempt, messages=messages, compiled_prompt=compiled_prompt, prompt_hash=prompt_hash,
            model_name="offline_contract_stub", temperature=bounded_temp, runtime_generation_status=OFFLINE_CONTRACT_STUB_RUNTIME_STATUS,
            raw_output=raw_out, parsed_output=parsed, resume_display_text=disp, claim_ledger=ledger, parse_error=err,
            provider_request_data={"provider_requested": "mock", "provider_attempted": False, "model": "offline_contract_stub"},
            provider_result_data={"provider_available": False, "model": "offline_contract_stub", "exact_provider_error": None},
        )
    section_model = external_openai_generation_model(section_id=LANE_KEY) if str(provider_name) == "external_openai" else resolve_section_generation_model(LANE_KEY, provider_profile=str(provider_name))
    prov_req, req_payload = build_section_request(
        messages=messages, prompt_hash=prompt_hash, input_payload_hash=input_payload_hash, temperature=bounded_temp,
        max_tokens=resolve_scratch_max_output_tokens(), model=section_model, provider_requested=str(provider_name), temperature_bounds=EXEC_SUMMARY_TEMP_RANGE,
    )
    prov_res = generate_section(tag_reasoning_lane(req_payload, LANE_KEY), artifact_dir=artifact_dir, run_id=run_id, provider_profile=str(provider_name))
    raw_out, status = str(prov_res.raw_text or ""), str(prov_res.runtime_generation_status or "BLOCKED")
    parsed, disp, ledger, parse_err = parse_strict_json_without_mutation(raw_out) if status == "REAL_LLM" and raw_out.strip() else (None, "", [], str(prov_res.exact_provider_error or "provider_blocked"))
    req_dict = prov_req.to_dict() if hasattr(prov_req, "to_dict") else {"provider_requested": provider_name, "model": section_model}
    res_dict = prov_res.to_dict() if hasattr(prov_res, "to_dict") else {"provider_available": bool(prov_res.provider_available), "model": prov_res.model or section_model, "exact_provider_error": prov_res.exact_provider_error, "runtime_generation_status": status}
    return GenerationTurnOutput(
        attempt=attempt, messages=messages, compiled_prompt=compiled_prompt, prompt_hash=prompt_hash,
        model_name=str(prov_res.model or section_model), temperature=bounded_temp, runtime_generation_status=status,
        raw_output=raw_out, parsed_output=parsed, resume_display_text=disp, claim_ledger=ledger, parse_error=parse_err,
        provider_request_data=req_dict, provider_result_data=res_dict,
    )
