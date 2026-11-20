"""Per-run L2 vs X1D contract manifest (apps_rg executive_summary)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from apps_rg.prompt_assembly.e0_examples import _EXEC_SUMMARY_POSITIVE_COMPILE_IDS
from apps_rg.runtime.sections.executive_summary_targeting_publish import (
    instructional_surface_drift_risk,
    judge_regen_blocked_by_trim,
)
from apps_rg.runtime.targeting_context_authority import (
    GenerationMaterialContext,
    JudgeMaterialContext,
    evaluate_targeting_parity,
    sha256_hex64,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_MAX_CHARS,
    EXEC_SUMMARY_MAX_SENTENCES,
    EXEC_SUMMARY_MAX_WORDS,
    EXEC_SUMMARY_MIN_CHARS,
    EXEC_SUMMARY_MIN_SENTENCES,
)

MANIFEST_SCHEMA = "generation_grade_contract_manifest_v1"
MANIFEST_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "generation_grade_contract_manifest.v1.schema.json"
)

JUDGE_EXCLUDED_BY_DESIGN: tuple[str, ...] = (
    "full_E0_many_shot_examples",
    "full_I0_proof_law_and_composition_heuristics",
    "SRFS_style_only_oneshot_block",
    "composition_plan_brushstroke_injection",
    "graph_only_quality_guardrails_block",
    "R0_generator_json_schema",
)


def generation_law_digest_text() -> str:
    """Compact generation laws mirrored for judges (not full I0/E0; zero X2 pass flags)."""
    return (
        "GENERATION_LAW_DIGEST:\n"
        "- Proof: ALLOWED_SOURCE_FACT_IDS + C0 lines only; JD/briefing targeting-only.\n"
        f"- Visual layout band: {EXEC_SUMMARY_MIN_SENTENCES} to {EXEC_SUMMARY_MAX_SENTENCES} crisp sentences, "
        f"{EXEC_SUMMARY_MIN_CHARS} to {EXEC_SUMMARY_MAX_CHARS} characters (max {EXEC_SUMMARY_MAX_WORDS} words overflow cap), "
        "one spoken executive paragraph.\n"
        "- Leadership first: open with sharp executive identity, scale, and rare differentiator before domain keywords.\n"
        "- Display metric weave: concrete dollar/percent/headcount outcomes from allowed facts appear directly in display prose.\n"
        "- Human spoken register: zero AI bridge crutches ('In parallel,', 'Building on that', 'Across enterprise programs,') "
        "and zero abstract noun soup ('operating-model framing', 'governed activation', 'durable economics').\n"
        "- Anti-inventory: no comma-chain mechanism dumps, no cert/employer inventories, no JD phrase copying.\n"
        "- Truthfulness: every displayed claim must be faithfully supported by allowed facts without inflation or conflation.\n"
    )


def dimension_gate_map() -> dict[str, str]:
    """Human hiring-committee LLM judge dimensions (strictly decoupled from X2 deterministic pass flags)."""
    return {
        "immediate_call_conviction": "human_judge_only",
        "spoken_executive_authenticity": "x2_exec_summary_no_ai_bridge_crutches",
        "differentiated_edge": "human_judge_only",
        "six_second_scannability": "x2_exec_summary_visual_char_band",
        "strategic_mandate_resonance": "x2_jd_phrase_copy_violation_zero",
        "factual_truth_and_non_exaggeration": "x2_unsupported_claim_zero",
    }


def digest_json_blob(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_generation_grade_contract_manifest(
    *,
    run_id: str,
    generation: GenerationMaterialContext,
    judge: JudgeMaterialContext,
    parity_receipt: dict[str, Any],
    judge_packet: dict[str, Any] | None,
    token_budget_receipt: dict[str, Any] | None,
    composition_plan: dict[str, Any] | None,
    allowed_fact_packet: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    trim_applied = bool((token_budget_receipt or {}).get("trim_applied"))
    trimmed_components = [
        str(row.get("component") or "")
        for row in ((token_budget_receipt or {}).get("trimmed_components") or [])
        if isinstance(row, dict)
    ]
    drift_risk = instructional_surface_drift_risk(token_budget_receipt)
    regen_trim_block = judge_regen_blocked_by_trim(token_budget_receipt)
    gate_summary = (judge_packet or {}).get("deterministic_gate_summary") or {}
    return {
        "schema": MANIFEST_SCHEMA,
        "section": "executive_summary",
        "run_id": str(run_id or ""),
        "surfaces": {
            "l2_compiled_prompt": "compiled_prompt.txt",
            "x1d_judge_packet": "executive_summary_judge_packet_post_x2.json",
            "judge_regen_remediation": "judge_remediation_cycles.json",
        },
        "targeting": {
            "generation_material_digest": generation.generation_material_digest,
            "judge_material_digest": judge.judge_material_digest,
            "parity_match": parity_receipt.get("parity_match") is True,
            "trim_applied": trim_applied,
            "token_trim_components": trimmed_components,
            "instructional_surface_drift_risk": drift_risk,
            "judge_regen_trim_block": regen_trim_block,
            "judge_regen_allowed": parity_receipt.get("parity_match") is True and not regen_trim_block,
        },
        "instructional_digests": {
            "e0_compile_ids": list(_EXEC_SUMMARY_POSITIVE_COMPILE_IDS),
            "rubric_ref": str((judge_packet or {}).get("rubric_ref") or ""),
            "generation_law_digest_sha256": sha256_hex64(generation_law_digest_text()),
            "composition_plan_digest": digest_json_blob(composition_plan or {}),
            "fact_packet_digest": digest_json_blob(allowed_fact_packet or []),
        },
        "judge_excluded_by_design": list(JUDGE_EXCLUDED_BY_DESIGN),
        "deterministic_gate_summary_keys": sorted(str(k) for k in gate_summary if str(k).startswith("x2_")),
        "dimension_gate_map": dimension_gate_map(),
    }


def write_generation_grade_contract_manifest(path: Path, body: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False, default=str)
    return str(path)


__all__ = [
    "JUDGE_EXCLUDED_BY_DESIGN",
    "MANIFEST_SCHEMA",
    "MANIFEST_SCHEMA_PATH",
    "build_generation_grade_contract_manifest",
    "dimension_gate_map",
    "generation_law_digest_text",
    "write_generation_grade_contract_manifest",
]
