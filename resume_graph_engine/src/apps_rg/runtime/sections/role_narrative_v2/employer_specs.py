"""Declarative EmployerNarrativeSpec registry for all 5 apps_rg employer narrative lanes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from apps_rg.runtime.sections.section_product_shape_ssot import NARRATIVE_MAX_CHARS, NARRATIVE_MAX_WORDS
from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_BULLET_IDS
from apps_rg.runtime.validators.unify_bullets_x2 import UNIFY_BULLET_IDS

UNIFY_NARRATIVE_BASE_FACT_ID = "unify_narrative_base_001"
UNIFY_NARRATIVE_C0_BULLET_PRIORITY: tuple[str, ...] = (
    "bul_unify_006", "bul_unify_001", "bul_unify_003", "bul_unify_002", "bul_unify_005", "bul_unify_004",
)


@dataclass(frozen=True)
class EmployerNarrativeSpec:
    section_id: str; employer_key: str; employer_label: str; employer_match_substring: str
    default_employment_fact_id: str; companion_bullet_lane: str; bullet_id_prefix: str
    canonical_bullet_ids: tuple[str, ...]; prompt_id: str; template_rel_path: str; output_filename: str
    header_key: str; temp_default: float; temp_range: tuple[float, float]; max_output_tokens: int
    max_words: int; max_chars: int; uses_role_episode_pipeline: bool
    zero_narrative_short_circuit: bool = False; base_narrative_fact_id: str | None = None


EMPLOYER_NARRATIVE_SPECS: Mapping[str, EmployerNarrativeSpec] = {
    "slalom_narrative": EmployerNarrativeSpec(
        "slalom_narrative", "slalom", "Slalom", "slalom", "exp_slalom_001", "slalom_bullets", "bul_slalom_",
        ("bul_slalom_001", "bul_slalom_002", "bul_slalom_003", "bul_slalom_004"), "slalom_narrative_v1",
        "apps_rg/prompt_assembly/templates/slalom_narrative_v1.yaml", "slalom_narrative_output.txt",
        "slalom_header", 0.40, (0.30, 0.55), 2400, NARRATIVE_MAX_WORDS, NARRATIVE_MAX_CHARS, True,
    ),
    "unify_narrative": EmployerNarrativeSpec(
        "unify_narrative", "unify", "Unify Consulting", "unify", "exp_unify_001", "unify_bullets", "bul_unify_",
        tuple(UNIFY_BULLET_IDS), "unify_position_narrative_v1",
        "apps_rg/prompt_assembly/templates/unify_position_narrative_v1.yaml", "unify_narrative_output.txt",
        "unify_header", 0.45, (0.35, 0.55), 4000, NARRATIVE_MAX_WORDS, NARRATIVE_MAX_CHARS, False,
        base_narrative_fact_id=UNIFY_NARRATIVE_BASE_FACT_ID,
    ),
    "ibm_narrative": EmployerNarrativeSpec(
        "ibm_narrative", "ibm", "IBM", "ibm", "exp_ibm_001", "ibm_bullets", "bul_ibm_",
        tuple(IBM_BULLET_IDS), "ibm_position_narrative_v1",
        "apps_rg/prompt_assembly/templates/ibm_position_narrative_v1.yaml", "ibm_narrative_output.txt",
        "ibm_header", 0.38, (0.30, 0.45), 4000, NARRATIVE_MAX_WORDS, NARRATIVE_MAX_CHARS, False,
    ),
    "insurtech_narrative": EmployerNarrativeSpec(
        "insurtech_narrative", "insurtech", "InsurTech", "insurtech", "exp_insurtech_001", "insurtech_bullets",
        "bul_insurtech_", ("bul_insurtech_001", "bul_insurtech_002"), "insurtech_narrative_v1",
        "apps_rg/prompt_assembly/templates/insurtech_narrative_v1.yaml", "insurtech_narrative_output.txt",
        "insurtech_header", 0.40, (0.30, 0.55), 2400, NARRATIVE_MAX_WORDS, NARRATIVE_MAX_CHARS, True,
    ),
    "ey_narrative": EmployerNarrativeSpec(
        "ey_narrative", "ey", "Ernst & Young", "ernst", "exp_ey_001", "ey_bullets", "bul_ey_", (),
        "ey_narrative_v1", "apps_rg/prompt_assembly/templates/ey_narrative_v1.yaml", "ey_narrative_output.txt",
        "ey_header", 0.40, (0.30, 0.55), 1600, NARRATIVE_MAX_WORDS, NARRATIVE_MAX_CHARS, True, True,
    ),
}


def get_employer_narrative_spec(section_id: str) -> EmployerNarrativeSpec:
    sid = str(section_id or "").strip()
    if sid not in EMPLOYER_NARRATIVE_SPECS:
        raise KeyError(f"Unsupported employer narrative section_id: {sid!r}")
    return EMPLOYER_NARRATIVE_SPECS[sid]
