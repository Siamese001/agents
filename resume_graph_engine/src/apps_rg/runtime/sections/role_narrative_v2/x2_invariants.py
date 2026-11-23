"""Pre-judge and post-judge deterministic X2 evaluation for role_narrative_v2."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.quality.overlap_engine import evaluate_narrative_section_overlap
from apps_rg.runtime.section_repair_ledger import infer_product_quality_with_repair_ledger
from apps_rg.runtime.sections.role_episode.x2_gates import run_role_episode_x2_gates
from apps_rg.runtime.validators.ibm_narrative_x2 import run_ibm_narrative_x2_gates
from apps_rg.runtime.validators.unify_narrative_x2 import run_unify_narrative_x2_gates
from .evidence_firewall import sha16

_X1D_WIRING_GATE_IDS = frozenset({"x2_x1d_required_judges_present", "x2_x1d_schema_valid"})


def enrich_unify_narrative_parsed_for_x2(
    parsed: dict[str, Any] | None, *, coverage: dict[str, Any], input_payload_hash: str, allowed_fact_ids: set[str],
) -> dict[str, Any] | None:
    if parsed is None:
        return None
    enriched = {**parsed, "text_claim_coverage": coverage}
    keys = ("narrative_sentence", "selected_fact_plan", "claim_ledger", "jd_alignment", "gap_notes", "change_log", "self_check", "text_claim_coverage")
    output_body = {k: enriched[k] for k in keys if k in enriched}
    enriched.update({
        "input_payload_hash": input_payload_hash,
        "output_payload_hash": sha16(json.dumps(output_body, sort_keys=True)),
        "claim_ledger_hash": sha16(json.dumps(enriched.get("claim_ledger") or [], sort_keys=True)),
        "allowed_fact_ids_hash": sha16(json.dumps(sorted(allowed_fact_ids), sort_keys=True)),
    })
    return enriched


def cosine_echo_diagnostic_summary(narrative_text: str, companion_bullets_list: list[str] | str) -> str:
    """Compute offending bullet index and shared content tokens via the shared Overlap Engine."""
    bullets = companion_bullets_as_list(companion_bullets_list) if isinstance(companion_bullets_list, str) else list(companion_bullets_list or [])
    if not narrative_text or not bullets:
        return "avoid echoing companion bullet vocabulary (target pairwise cosine <=0.3400)"
    report = evaluate_narrative_section_overlap(narrative_text, bullets, section_id="role_narrative")
    return f"max_cosine={report.max_narrative_to_bullet_idf_cosine:.4f}; {report.diagnostic_summary()}"


def infer_narrative_product_quality(
    section_id: str, runtime_generation_status: str, x2_gates: list[dict[str, Any]], *, artifact_dir: Path | None = None,
) -> tuple[str, str]:
    return infer_product_quality_with_repair_ledger(
        runtime_generation_status=runtime_generation_status,
        x2_failed_gate_ids=[g["gate_id"] for g in x2_gates if not g.get("pass")],
        pass_reason=f"REAL_LLM output passed all deterministic {section_id} gates.",
        artifact_dir=artifact_dir,
    )


def evaluate_narrative_v2_x2(
    *, section_id: str, narrative_sentence: str, parsed_output: dict[str, Any] | None, claim_ledger: list[dict[str, Any]], jd_text: str, briefing_text: str, runtime_generation_status: str, companion_bullet_texts: str | None, companion_bullets_status: str, companion_bullets_reason: str, candidate_name: str, provider_requested: str, provider_attempted: str, model_name: str | None, raw_output: str, x1d_judges: list[dict[str, Any]], allowed_fact_ids: set[str] | list[str], artifacts_dir: Path, srfs_source_fact_slice_gate_active: bool, proof_pool_metadata: dict[str, Any] | None, proof_pool_ref: str, proof_pool_digest: str, text_claim_coverage: dict[str, Any] | None = None, test_only_mock_provider: bool = False, role_episode_l2: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if section_id == "unify_narrative":
        return [g.to_dict() for g in run_unify_narrative_x2_gates(
            narrative_sentence=narrative_sentence, parsed_output=parsed_output, claim_ledger=claim_ledger, jd_text=jd_text,
            briefing_text=briefing_text, runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_bullet_texts,
            companion_bullets_status=companion_bullets_status, companion_bullets_reason=companion_bullets_reason,
            candidate_name=candidate_name, provider_requested=provider_requested, provider_attempted=provider_attempted,
            model_name=model_name, raw_output=raw_output, x1d_judges=x1d_judges, allowed_fact_ids=set(allowed_fact_ids),
            artifacts_dir=artifacts_dir, srfs_source_fact_slice_gate_active=srfs_source_fact_slice_gate_active,
            proof_pool_metadata=proof_pool_metadata, proof_pool_ref=proof_pool_ref, proof_pool_digest=proof_pool_digest,
        )]
    if section_id == "ibm_narrative":
        return [g.to_dict() for g in run_ibm_narrative_x2_gates(
            narrative_sentence=narrative_sentence, parsed_output=parsed_output, claim_ledger=claim_ledger, jd_text=jd_text,
            runtime_generation_status=runtime_generation_status, companion_bullet_texts=companion_bullet_texts,
            companion_bullets_status=companion_bullets_status, companion_bullets_reason=companion_bullets_reason,
            companion_aware=not test_only_mock_provider, candidate_name=candidate_name, provider_requested=provider_requested,
            provider_attempted=provider_attempted, model_name=model_name, raw_output=raw_output, x1d_judges=x1d_judges,
            allowed_fact_ids=list(allowed_fact_ids), test_only_mock_provider=test_only_mock_provider, artifacts_dir=artifacts_dir,
            text_claim_coverage=text_claim_coverage, srfs_source_fact_slice_gate_active=srfs_source_fact_slice_gate_active,
            proof_pool_metadata=proof_pool_metadata, proof_pool_ref=proof_pool_ref, proof_pool_digest=proof_pool_digest,
        )]
    return list(run_role_episode_x2_gates(section_id=section_id, l2=role_episode_l2 or (parsed_output or {}), allowed=list(allowed_fact_ids), runtime_generation_status=runtime_generation_status))


def pre_judge_failed_gate_ids(gates: list[dict[str, Any]]) -> list[str]:
    return [str(g.get("gate_id") or "") for g in gates if not g.get("pass") and str(g.get("gate_id") or "") not in _X1D_WIRING_GATE_IDS]


def companion_bullets_as_list(companion_text: str) -> list[str]:
    return [re.sub(r"^bul_[a-z]+_\d+:\s*", "", ln.strip().lstrip("-*").strip()) for ln in str(companion_text or "").splitlines() if ln.strip()]
