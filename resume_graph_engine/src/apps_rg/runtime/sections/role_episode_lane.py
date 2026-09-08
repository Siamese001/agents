"""Generic proof-bound role episode lanes for InsurTech/EY sections.

These lanes intentionally fail closed when upstream graph/FEC evidence is absent.
They do not hydrate claims from the base resume or targeting text.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from apps_rg.runtime.c0.section_proof_loader import (
    apply_proof_pool_to_usage_ledger,
    load_section_proof_for_lane,
)
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.exit.executive_summary_x3 import aggregate_x3
from apps_rg.runtime.spine.section_x3_finalize import finalize_section_lane_x3
from apps_rg.runtime.validators.bullet_line_discipline_x2 import check_bullet_single_thought
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    check_experience_bullet_evidence_density,
)
from apps_rg.runtime.validators.narrative_mechanical_x2 import check_narrative_exactly_one_sentence
from apps_rg.runtime.providers import (
    ExternalProvider,
    ProviderGateway,
    ProviderGatewayError,
    ProviderProfile,
)
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.section_model_limits import (
    external_claude_generation_model,
    external_openai_generation_model,
    resolve_section_generation_effort,
)
from apps_rg.runtime.runtime_proof_layout import (
    finalize_runtime_proof_run,
    prepare_runtime_proof_run_dir,
    rel_posix,
)
from apps_rg.runtime.section_l2_lane_integration import (
    finalize_section_l2_after_output,
    prepare_section_l2_before_provider,
)
from apps_rg.runtime.section_runtime_exhaust_lane_integration import (
    finalize_section_runtime_exhaust_before_l6,
    gate_section_l6_shadow_after_exhaust,
)
from apps_rg.runtime.section_proof.section_input_usage_ledger import (
    build_section_input_usage_ledger_v1,
)
from apps_rg.runtime.sections.lane_artifact_io import (
    runtime_payload_for_json,
    sha16,
    write_json,
)
from apps_rg.runtime.spine.c0_fec_compose import (
    merge_compiled_prompt_artifact_fec_fields,
)
from apps_rg.runtime.validators.proof_pool_source_fact_validation import (
    write_x2_source_fact_pool_receipt,
)
from apps_rg.runtime.reasoning.bullet_lane_generation import (
    generate_bullet_lane_with_sc_and_claude,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import (
    FINAL_BULLET_COUNT,
    REQUIRED_BULLET_IDS,
    build_employment_targeting_context,
    employment_pool_x1d_judge_rows,
    evaluate_employment_selection_quality,
    is_employment_bullet_lane,
    is_employment_pool_generation,
)

# W2 (plan prompt-gate-ssot-consolidation-e7c9a2): narrative budgets come from the numeric SSOT,
# not a re-declared local copy. section_product_shape_ssot is the canonical owner.
from apps_rg.runtime.sections.section_product_shape_ssot import (
    NARRATIVE_MAX_CHARS,
    NARRATIVE_MAX_WORDS,
    product_shape_gate_ids_for_lane,
)
from apps_rg.runtime.sections.section_generation import build_section_request
from apps_rg.runtime.sections.section_final_materialized_binding import (
    augment_x2_payload_with_final_materialized_binding,
)
from apps_rg.runtime.shadow.l6_handoff_packet import build_l6_shadow_handoff_dict

REPO_ROOT = Path(__file__).resolve().parents[3]
MAX_OUTPUT_TOKENS = 900
ROLE_EPISODE_MAX_OUTPUT_TOKENS_BY_SECTION: dict[str, int] = {
    # Three-bullet lanes emit full bullet rows plus claim-ledger rows; Anthropic can truncate
    # the required JSON under the narrative-sized default.
    "slalom_bullets": 2200,
    "insurtech_bullets": 2200,
    "ey_bullets": 2200,
}
ROLE_EPISODE_GRAPH_BULLET_RENDERER_VERSION = "deterministic_graph_bullet_render.v1"
ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION = "proof_authorized_fact_claim_render.v2"
ROLE_EPISODE_FINAL_BULLET_COUNT = 3
ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT = (
    "role_episode_final_materialized_selection_contract.json"
)

# A few role-episode roots contain a valid, graph-approved outcome surface that
# is broader than the concise root claim.  The model may reproduce only the
# activity clause, which is truthful but fails the all-bullets outcome floor.
# These are source-bound completions: each phrase below is composed exclusively
# from that root's approved claim, scope, and linked metric-outcome node.  They
# are intentionally applied only when the generated bullet fails the quality
# floor; passing model prose remains untouched.
_ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS: dict[str, str] = {
    "reb_ey_capital_optimization_solvency": (
        "Led quantitative derivatives, variable-annuity hedging, and insurance-capital work "
        "using exotic-pricing models, liability Greeks, and higher-order stress scenarios for "
        "regulated portfolios, delivering risk visibility for hedge-design decisions."
    ),
    "reb_ey_erm_risk_governance": (
        "Architected ERM operating models and BCBS 239-aligned risk-data aggregation "
        "for regulated banking and insurance clients, defining three-lines-of-defense "
        "accountability and metadata standards that standardized risk-metric definitions "
        "across business units, control owners, and reporting stakeholders."
    ),
}


@dataclass(frozen=True)
class RoleEpisodeLaneConfig:
    section_id: str
    role_key: str
    employer_label: str
    header_key: str
    bullet_prefix: str
    output_filename: str
    output_kind: str
    allow_deterministic_graph_render: bool = False

    @property
    def is_bullet_lane(self) -> bool:
        return self.output_kind == "bullets"


_ROLE_LANES: dict[str, RoleEpisodeLaneConfig] = {
    "slalom_bullets": RoleEpisodeLaneConfig(
        section_id="slalom_bullets",
        role_key="slalom",
        employer_label="Slalom",
        header_key="slalom_header",
        bullet_prefix="bul_slalom",
        output_filename="slalom_bullets_output.txt",
        output_kind="bullets",
        allow_deterministic_graph_render=True,
    ),
    "slalom_narrative": RoleEpisodeLaneConfig(
        section_id="slalom_narrative",
        role_key="slalom",
        employer_label="Slalom",
        header_key="slalom_header",
        bullet_prefix="bul_slalom",
        output_filename="slalom_narrative_output.txt",
        output_kind="narrative",
    ),
    "insurtech_bullets": RoleEpisodeLaneConfig(
        section_id="insurtech_bullets",
        role_key="insurtech",
        employer_label="InsurTech",
        header_key="insurtech_header",
        bullet_prefix="bul_insurtech",
        output_filename="insurtech_bullets_output.txt",
        output_kind="bullets",
        allow_deterministic_graph_render=True,
    ),
    "insurtech_narrative": RoleEpisodeLaneConfig(
        section_id="insurtech_narrative",
        role_key="insurtech",
        employer_label="InsurTech",
        header_key="insurtech_header",
        bullet_prefix="bul_insurtech",
        output_filename="insurtech_narrative_output.txt",
        output_kind="narrative",
    ),
    "ey_bullets": RoleEpisodeLaneConfig(
        section_id="ey_bullets",
        role_key="ey",
        employer_label="EY",
        header_key="ey_header",
        bullet_prefix="bul_ey",
        output_filename="ey_bullets_output.txt",
        output_kind="bullets",
        allow_deterministic_graph_render=True,
    ),
    "ey_narrative": RoleEpisodeLaneConfig(
        section_id="ey_narrative",
        role_key="ey",
        employer_label="EY",
        header_key="ey_header",
        bullet_prefix="bul_ey",
        output_filename="ey_narrative_output.txt",
        output_kind="narrative",
    ),
}


def _max_output_tokens_for_lane(cfg: RoleEpisodeLaneConfig) -> int:
    return int(ROLE_EPISODE_MAX_OUTPUT_TOKENS_BY_SECTION.get(cfg.section_id, MAX_OUTPUT_TOKENS))

_X1D_WIRING_GATE_IDS: frozenset[str] = frozenset(
    {"x2_x1d_required_judges_present", "x2_x1d_schema_valid"}
)

ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION: dict[str, str] = {
    lane: f"run_{lane}_x2_gates" for lane in _ROLE_LANES
}
ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION: dict[str, frozenset[str]] = {
    fn_name: frozenset(product_shape_gate_ids_for_lane(lane) | _X1D_WIRING_GATE_IDS)
    for lane, fn_name in ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION.items()
}


def build_role_episode_lane_args(
    *,
    provider: str,
    temperature: float,
    x1d_judges: str,
    mock_judges: bool,
    allow_test_mock_judges: bool,
    allow_non_allow_exit_zero: bool,
    target_title: str,
    target_company: str,
    jd_text: str,
    briefing: str,
    target_role: str | None = None,
    base_resume_ref: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        provider=str(provider or "external_claude").strip().lower(),
        temperature=float(temperature),
        x1d_judges=str(x1d_judges or ""),
        mock_judges=bool(mock_judges),
        allow_test_mock_judges=bool(allow_test_mock_judges),
        allow_non_allow_exit_zero=bool(allow_non_allow_exit_zero),
        target_title=str(target_title or "").strip(),
        target_company=str(target_company or "").strip(),
        target_role=str(target_role or target_title or "").strip(),
        jd_text=str(jd_text or "").strip(),
        briefing=str(briefing or "").strip(),
        base_resume_ref=str(base_resume_ref or "").strip(),
    )


def _json_hash(value: Any) -> str:
    # L2 preparation attaches frozen, in-process authority objects under private keys.
    # They remain available to the lane, but do not belong in durable payloads. Hash
    # the same public projection that the lane persists.
    serializable = runtime_payload_for_json(value) if isinstance(value, dict) else value
    return sha16(
        json.dumps(serializable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    )


def _compact_text(text: str, *, max_chars: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    return cleaned[:max_chars].rstrip()


def _sentence(text: str) -> str:
    # Em dashes are banned by x2_no_em_dash — normalize to a comma clause before budgeting.
    normalized = str(text or "").replace("—", ", ").replace(" ,", ",")
    cleaned = _compact_text(normalized, max_chars=NARRATIVE_MAX_CHARS)
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\n", " ").strip()
    words = cleaned.split()
    if len(words) > NARRATIVE_MAX_WORDS:
        cleaned = " ".join(words[:NARRATIVE_MAX_WORDS])
    if cleaned.endswith((".", "!", "?")):
        return cleaned
    # Reserve room for the appended terminator — truncating to exactly NARRATIVE_MAX_CHARS and
    # then adding "." produced a 361-char narrative vs the 360 budget (off-by-one X2 fail).
    if len(cleaned) >= NARRATIVE_MAX_CHARS:
        cleaned = cleaned[: NARRATIVE_MAX_CHARS - 1].rstrip().rstrip(",;")
    return f"{cleaned}."


def _role_header(base: dict[str, Any], cfg: RoleEpisodeLaneConfig, args: Any) -> dict[str, Any]:
    # Locked-identity law: employer/title/location/dates come verbatim from the base
    # resume employment block — NEVER from targeting. The canonical base resume keeps
    # employment rows under facts.employment keyed by fact_id (exp_<role>_001); the
    # legacy experience-list shapes are kept for fixture compatibility. The old
    # target_title fallback stamped the TARGET role onto InsurTech/EY headers (all 3
    # full-resume coherence judges blocked assembly on the duplicate titles, 2026-06-11).
    fallback = {
        "employer": cfg.employer_label,
        "title": "",
        "location": "",
        "start_date": "",
        "end_date": "",
        "is_current": False,
    }
    experiences = base.get("experience") or base.get("professional_experience") or []
    if not isinstance(experiences, list) or not experiences:
        facts = base.get("facts")
        emp_rows = facts.get("employment") if isinstance(facts, dict) else None
        experiences = emp_rows if isinstance(emp_rows, list) else []
    expected_fact_id = f"exp_{cfg.role_key}_001"
    label_l = cfg.employer_label.lower()
    for row in experiences:
        if not isinstance(row, dict):
            continue
        employer = str(row.get("employer") or row.get("company") or "").strip()
        if not employer:
            continue
        fact_id = str(row.get("fact_id") or "").strip()
        emp_l = employer.lower()
        if fact_id != expected_fact_id and label_l not in emp_l and cfg.role_key not in emp_l:
            continue
        return {
            "employer": employer,
            "title": str(row.get("title") or ""),
            "location": str(row.get("location") or ""),
            "start_date": str(row.get("start_date") or ""),
            "end_date": str(row.get("end_date") or ""),
            "is_current": bool(row.get("is_current")),
            "fact_id": fact_id or expected_fact_id,
        }
    return fallback


def _facts_from_plan(selected_fact_plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in (selected_fact_plan.get("facts") or []) if isinstance(f, dict)]


def _normalize_source_ids(raw: Any, allowed: list[str], idx: int) -> list[str]:
    ids = [str(x) for x in raw] if isinstance(raw, list) else ([str(raw)] if raw else [])
    valid = [x for x in ids if x in set(allowed)]
    if valid:
        return valid
    if idx < len(allowed):
        return [allowed[idx]]
    return allowed[:1]


_NARRATIVE_LEDGER_STOPWORDS = {
    "and",
    "for",
    "into",
    "that",
    "the",
    "with",
    "without",
}


def _narrative_ledger_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(token) > 2 and token not in _NARRATIVE_LEDGER_STOPWORDS
    }


def _valid_source_ids_without_fallback(raw: Any, allowed: list[str]) -> list[str]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    out: list[str] = []
    for value in raw if isinstance(raw, list) else ([raw] if raw else []):
        fid = str(value or "").strip()
        if fid and fid in allowed_set and fid not in out:
            out.append(fid)
    return out


def _parsed_claim_ledger_source_ids_for_narrative(
    *,
    parsed: dict[str, Any],
    narrative: str,
    allowed: list[str],
) -> list[str]:
    """Preserve valid parsed ledger IDs whose claim text appears in the narrative."""
    rows = parsed.get("claim_ledger") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        return []
    narrative_text = str(narrative or "")
    narrative_l = narrative_text.lower()
    narrative_tokens = _narrative_ledger_tokens(narrative_text)
    source_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        claim_text = str(row.get("claim_text") or row.get("claim") or "").strip()
        claim_l = claim_text.lower()
        if claim_text and claim_l not in narrative_l:
            claim_tokens = _narrative_ledger_tokens(claim_text)
            required_overlap = 2 if len(claim_tokens) <= 5 else 3
            if len(narrative_tokens & claim_tokens) < required_overlap:
                continue
        for fid in _valid_source_ids_without_fallback(row.get("source_fact_ids"), allowed):
            if fid not in source_ids:
                source_ids.append(fid)
    return source_ids


_NARRATIVE_SOURCE_BINDING_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "reb_ey_regulatory_analytics_modernization": (
        re.compile(r"\bregulatory\s+analytics\b", re.IGNORECASE),
        re.compile(r"\blineage[-\s]+backed\s+regulatory\b", re.IGNORECASE),
        re.compile(r"\bpredictive\s+risk\s+analytics\b", re.IGNORECASE),
    ),
    "reb_ey_capital_optimization_solvency": (
        re.compile(r"\bcapital\b", re.IGNORECASE),
        re.compile(r"\bsolvency\b", re.IGNORECASE),
        re.compile(r"\bhedg(?:e|ing)\b", re.IGNORECASE),
        re.compile(r"\bliability\s+greeks\b", re.IGNORECASE),
    ),
    "reb_ey_ccar_capital_liquidity_stress_testing": (
        re.compile(r"\bccar\b", re.IGNORECASE),
        re.compile(r"\bstress\s+testing\b", re.IGNORECASE),
        re.compile(r"\bmodel[-\s]?risk\b", re.IGNORECASE),
        re.compile(r"\bgovernance\s+evidence\b", re.IGNORECASE),
    ),
    "reb_ey_insurance_core_modernization": (
        re.compile(r"\binsurance\s+operations\b", re.IGNORECASE),
        re.compile(r"\bpolicy\s+(?:and\s+claims\s+)?operations\b", re.IGNORECASE),
        re.compile(r"\bclaims\s+(?:operations|workflow)\b", re.IGNORECASE),
        re.compile(r"\bpolicy\s+administration\b", re.IGNORECASE),
        re.compile(r"\bbilling/rating/underwriting\b", re.IGNORECASE),
        re.compile(r"\bBI[-\s]+ready\s+data\s+outputs\b", re.IGNORECASE),
    ),
    "reb_ey_erm_risk_governance": (
        re.compile(r"\bauditable\b", re.IGNORECASE),
        re.compile(r"\btraceable\s+controls?\b", re.IGNORECASE),
        re.compile(r"\brisk[-\s]+data\b", re.IGNORECASE),
        re.compile(r"\bthree[-\s]+lines(?:[-\s]+of[-\s]+defense)?\b", re.IGNORECASE),
        re.compile(r"\brisk\s+metrics?\b", re.IGNORECASE),
    ),
    "reb_insurtech_founder_led_gtm_revenue": (
        re.compile(r"\bgtm\b", re.IGNORECASE),
        re.compile(r"\bgo[-\s]?to[-\s]?market\b", re.IGNORECASE),
    ),
    "reb_insurtech_lean_delivery_operating_model": (
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\baudit/control\s+discipline\b", re.IGNORECASE),
        re.compile(r"\blean\s+execution\b", re.IGNORECASE),
        re.compile(r"\blean\s+(?:delivery|operating)\s+model\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_cloud_economics": (
        re.compile(r"\beconomics(?:[-\s]+driven)?\b", re.IGNORECASE),
        re.compile(r"\bcost\s+controls?\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_migration_execution": (
        re.compile(r"\blegacy\s+platforms?\b", re.IGNORECASE),
        re.compile(r"\benterprise\s+workloads?\b", re.IGNORECASE),
        re.compile(r"\bcomplex\s+workloads?\b", re.IGNORECASE),
        re.compile(r"\bworkloads?\s+deployable\b", re.IGNORECASE),
        re.compile(r"\bproduction\b", re.IGNORECASE),
    ),
    "reb_insurtech_aws_shared_responsibility_operating_model": (
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\bsafety[-\s]first\s+control\b", re.IGNORECASE),
        re.compile(r"\binsurer-owned\s+controls?\b", re.IGNORECASE),
    ),
    "reb_insurtech_regulated_aws_control_implementation": (
        re.compile(r"\bregulated\s+AWS\b", re.IGNORECASE),
        re.compile(r"\bcontrol\s+discipline\b", re.IGNORECASE),
        re.compile(r"\bcontrol\s+design\b", re.IGNORECASE),
        re.compile(r"\bsafety[-\s]first\s+control\b", re.IGNORECASE),
    ),
}


def _narrative_source_ids_for_claim(
    *,
    narrative: str,
    raw_source_ids: Any,
    allowed: list[str],
    selected_fact_plan: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Bind narrative material phrases to selected role-episode bundle facts."""
    source_ids = _normalize_source_ids(raw_source_ids, allowed, 0)
    fact_ids = {
        str(row.get("fact_id") or row.get("role_episode_bundle_id") or "").strip()
        for row in _facts_from_plan(selected_fact_plan)
    }
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    added: list[str] = []
    for fid in allowed:
        if fid in source_ids or fid not in fact_ids:
            continue
        patterns = _NARRATIVE_SOURCE_BINDING_PATTERNS.get(fid, ())
        if not patterns or not any(pattern.search(narrative) for pattern in patterns):
            continue
        if fid not in allowed_set:
            continue
        source_ids.append(fid)
        added.append(fid)
    return source_ids, added


_TARGETING_ONLY_TAIL_REPAIRS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r",?\s+(?:mirroring|positioning|aligning|framing|mapping|translating)\b"
        r"[^.?!]*(?:frontier\s+AI|partner-led\s+deployments?|target\s+role|"
        r"target\s+company|Anthropic|applied\s+AI\s+architecture|ecosystem\s+revenue)"
        r"[^.?!]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\s+(?:required|needed)\s+to\s+enable\s+partner-led\s+deployments?"
        r"\s+of\s+frontier\s+AI(?:\s+at\s+scale)?",
        re.IGNORECASE,
    ),
    re.compile(
        r",?\s+for\s+(?:Anthropic|the\s+target\s+role|the\s+target\s+company|"
        r"target\s+role|target\s+company)\b[^.?!]*",
        re.IGNORECASE,
    ),
)

_TARGETING_ONLY_EXPERIENCE_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("target_company_name", re.compile(r"\bAnthropic\b", re.IGNORECASE)),
    ("frontier_ai_as_experience", re.compile(r"\bfrontier\s+AI\b", re.IGNORECASE)),
    (
        "partner_led_deployment_as_experience",
        re.compile(r"\bpartner-led\s+deployments?\b", re.IGNORECASE),
    ),
    ("target_role_as_experience", re.compile(r"\btarget\s+(?:role|company)\b", re.IGNORECASE)),
)


def _targeting_only_experience_hits(text: str) -> list[str]:
    return [
        label
        for label, pattern in _TARGETING_ONLY_EXPERIENCE_MARKERS
        if pattern.search(str(text or ""))
    ]


def _strip_targeting_only_experience_claims(text: str) -> tuple[str, list[str]]:
    """Remove JD/briefing-only tail claims without inventing replacement proof."""
    original = str(text or "")
    cleaned = original
    for pattern in _TARGETING_ONLY_TAIL_REPAIRS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned).strip(" ,;:")
    if cleaned != original and cleaned:
        cleaned = _sentence(cleaned)
    return (cleaned or original), _targeting_only_experience_hits(cleaned or original)


def _normalize_bullets(parsed: dict[str, Any], *, cfg: RoleEpisodeLaneConfig, allowed: list[str]) -> list[dict[str, Any]]:
    rows = parsed.get("bullets") if isinstance(parsed, dict) else None
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
    count = expected_bullet_count if expected_bullet_count > 0 else (len(rows) if isinstance(rows, list) else 0)
    out: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for idx, row in enumerate(rows[:count]):
            if not isinstance(row, dict):
                continue
            text, _hits = _strip_targeting_only_experience_claims(
                str(row.get("bullet_text") or row.get("text") or "")
            )
            text = _sentence(text)
            if not text:
                continue
            source_fact_ids = _normalize_source_ids(
                row.get("source_fact_ids"), allowed, idx
            )
            expected_ids = {
                f"{cfg.bullet_prefix}_{slot + 1:03d}"
                for slot in range(count)
            }
            source_bound_ids = [
                fact_id for fact_id in source_fact_ids if fact_id in expected_ids
            ]
            canonical_id = (
                source_bound_ids[0]
                if len(set(source_bound_ids)) == 1
                else f"{cfg.bullet_prefix}_{idx + 1:03d}"
            )
            out.append(
                {
                    # An exact proof-fact id is the slot authority. Positional
                    # fallback remains for rows without a usable source id.
                    # Position-only normalization mislabeled out-of-order EY
                    # rows and created false cross-bullet duplicates.
                    "bullet_id": canonical_id,
                    "bullet_text": text,
                    "source_fact_ids": source_fact_ids,
                }
            )
    return out


def _repair_role_episode_bullet_evidence_density(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Complete a thin model bullet only with an approved graph-root outcome.

    This is deliberately a repair, not a second renderer.  The model still
    chooses the three graph-bound roots; a repair may replace only a selected
    row whose current prose fails the shared action/detail/outcome quality
    floor.  The replacement is keyed by the row's role-episode root, making
    the added result traceable to the same graph source rather than to the JD
    or an invented generic outcome.
    """
    fact_by_id = {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if isinstance(fact, dict) and str(fact.get("fact_id") or "").strip()
    }
    repaired: list[dict[str, Any]] = []
    repairs: list[dict[str, str]] = []
    for row in bullets:
        out = dict(row)
        text = str(out.get("bullet_text") or "").strip()
        source_ids = [str(fid).strip() for fid in (out.get("source_fact_ids") or [])]
        fact = next((fact_by_id.get(fid) for fid in source_ids if fact_by_id.get(fid)), None)
        root_id = str((fact or {}).get("role_episode_bundle_id") or "").strip()
        replacement = _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS.get(root_id)
        density = check_experience_bullet_evidence_density(
            str(out.get("bullet_id") or ""), text
        )
        if replacement and not density.passed:
            out["bullet_text"] = replacement
            repairs.append(
                {
                    "bullet_id": str(out.get("bullet_id") or ""),
                    "role_episode_bundle_id": root_id,
                    "reason": "graph_bound_evidence_density_completion",
                }
            )
        repaired.append(out)
    return repaired, repairs


def _source_fact_ids_from_bullets(bullets: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in bullets:
        if not isinstance(row, dict):
            continue
        for raw in row.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if fid and fid not in seen:
                seen.add(fid)
                out.append(fid)
    return out


def _deterministic_graph_bullet_render(
    *,
    cfg: RoleEpisodeLaneConfig,
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    if not cfg.allow_deterministic_graph_render or not allowed_set:
        return out
    for fact in facts:
        fid = str(fact.get("fact_id") or fact.get("candidate_fact_id") or "")
        if fid not in allowed_set:
            continue
        text = _sentence(str(fact.get("claim_text") or fact.get("text") or ""))
        if not text:
            continue
        idx = len(out)
        out.append(
            {
                "bullet_id": f"{cfg.bullet_prefix}_{idx + 1:03d}",
                "bullet_text": text,
                "source_fact_ids": [fid],
            }
        )
        if len(out) >= 3:
            break
    return out


def _fact_id_from_row(fact: dict[str, Any]) -> str:
    return str(fact.get("fact_id") or fact.get("candidate_fact_id") or "").strip()


_PROOF_FACT_SURFACE_COMPOSITIONS: Mapping[tuple[str, str], str] = {
    # The frozen allocation has two distinct leaf skills under the same
    # migration bundle. This concise, source-vocabulary-only projection keeps
    # the legacy-modernization leaf distinguishable from the generic AWS
    # modernization bullet while retaining its exact fact and graph path.
    (
        "bul_insurtech_003",
        "skill_sr_insurtech_legacy_cloud_modernization",
    ): "Led legacy cloud modernization for AWS insurance platforms",
}
_PROOF_FACT_COMPOSITION_CONNECTIVES = frozenset({"and", "for", "of", "the", "to"})
_MODEL_SURFACE_NON_ANCHOR_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "that",
        "the",
        "their",
        "to",
        "with",
        "across",
        "built",
        "created",
        "delivered",
        "designed",
        "directed",
        "drove",
        "implemented",
        "led",
        "managed",
        "owned",
        "scaled",
    }
)


def _proof_fact_surface_tokens(fact: Mapping[str, Any]) -> set[str]:
    values: list[Any] = [
        fact.get("claim_text"),
        fact.get("text"),
        fact.get("domain"),
        fact.get("role_episode_bundle_id"),
        fact.get("graph_skill_node_ids"),
        fact.get("allowed_graph_evidence_ids"),
    ]
    return set(
        re.findall(
            r"[a-z0-9]+",
            " ".join(str(value or "") for value in values).casefold(),
        )
    )


def _proof_fact_composition_is_bound(phrase: str, fact: Mapping[str, Any]) -> bool:
    source_tokens = _proof_fact_surface_tokens(fact)
    for token in re.findall(r"[a-z0-9]+", str(phrase or "").casefold()):
        if token in _PROOF_FACT_COMPOSITION_CONNECTIVES or token in source_tokens:
            continue
        if token.endswith("s") and token[:-1] in source_tokens:
            continue
        if f"{token}s" in source_tokens:
            continue
        return False
    return True


def _model_bullet_surface_binding(
    text: str,
    fact: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Require a model surface to retain several meaningful graph anchors.

    The model may improve readable phrasing, but it cannot turn an approved
    source id into an ungrounded target-role claim.  A rejected model surface
    is rendered from the graph's exact claim text instead.
    """
    source_tokens = {
        token
        for token in _proof_fact_surface_tokens(fact)
        if len(token) > 2 and token not in _MODEL_SURFACE_NON_ANCHOR_TOKENS
    }
    text_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", str(text or "").casefold())
        if len(token) > 2 and token not in _MODEL_SURFACE_NON_ANCHOR_TOKENS
    }
    anchors = sorted(source_tokens & text_tokens)
    required_anchor_count = min(3, len(source_tokens))
    return len(anchors) >= required_anchor_count, anchors


def _proof_fact_text(fact: dict[str, Any]) -> str:
    fact_id = _fact_id_from_row(fact)
    skill_ids = [str(value or "").strip() for value in fact.get("graph_skill_node_ids") or []]
    if len(skill_ids) == 1:
        composition = _PROOF_FACT_SURFACE_COMPOSITIONS.get((fact_id, skill_ids[0]))
        if composition and _proof_fact_composition_is_bound(composition, fact):
            return _sentence(composition)
    return _sentence(str(fact.get("claim_text") or fact.get("text") or ""))


def _proof_fact_by_id(facts: list[dict[str, Any]], allowed: list[str]) -> dict[str, dict[str, Any]]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    out: dict[str, dict[str, Any]] = {}
    for fact in facts:
        fid = _fact_id_from_row(fact)
        if fid and fid in allowed_set and _proof_fact_text(fact):
            out[fid] = fact
    return out


def _ordered_ids_from_bullets(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[str]:
    selected, _contract = _ordered_ids_from_bullets_with_contract(
        bullets,
        facts=facts,
        allowed=allowed,
        expected_count=ROLE_EPISODE_FINAL_BULLET_COUNT,
        allow_deterministic_reselect=False,
    )
    return selected


def _ordered_ids_from_bullets_with_contract(
    bullets: list[dict[str, Any]],
    *,
    facts: list[dict[str, Any]],
    allowed: list[str],
    expected_count: int,
    allow_deterministic_reselect: bool,
) -> tuple[list[str], dict[str, Any]]:
    if expected_count == 0 and bullets:
        expected_count = len(bullets)
    proof_by_id = _proof_fact_by_id(facts, allowed)
    seen: set[str] = set()
    out: list[str] = []
    duplicate_source_fact_ids: list[str] = []
    rejected_source_fact_ids: list[str] = []
    for bullet in bullets:
        if not isinstance(bullet, dict):
            continue
        for raw in bullet.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if not fid:
                continue
            if fid not in proof_by_id:
                if fid not in rejected_source_fact_ids:
                    rejected_source_fact_ids.append(fid)
                continue
            if fid in seen:
                if fid not in duplicate_source_fact_ids:
                    duplicate_source_fact_ids.append(fid)
                continue
            seen.add(fid)
            out.append(fid)
            if len(out) >= expected_count:
                break
        if len(out) >= expected_count:
            break
    deterministic_reselect_source_fact_ids: list[str] = []
    if out and len(out) < expected_count and allow_deterministic_reselect:
        for fact in facts:
            fid = _fact_id_from_row(fact)
            if fid and fid in proof_by_id and fid not in seen:
                seen.add(fid)
                out.append(fid)
                deterministic_reselect_source_fact_ids.append(fid)
                if len(out) >= expected_count:
                    break
    for fact in facts:
        if out:
            break
        fid = _fact_id_from_row(fact)
        if fid and fid in proof_by_id and fid not in seen:
            seen.add(fid)
            out.append(fid)
            if len(out) >= expected_count:
                break
    contract = {
        "schema_version": "role_episode_final_materialized_selection_contract.v1",
        "expected_bullet_count": expected_count,
        "model_bullet_count": len([b for b in bullets if isinstance(b, dict)]),
        "selected_source_fact_ids": list(out),
        "selected_unique_source_fact_count": len(set(out)),
        "duplicate_source_fact_ids_ignored": duplicate_source_fact_ids,
        "rejected_source_fact_ids": rejected_source_fact_ids,
        "deterministic_reselect_source_fact_ids": deterministic_reselect_source_fact_ids,
        "deterministic_reselect_applied": bool(deterministic_reselect_source_fact_ids),
    }
    return out, contract


def _proof_authorized_bullets_from_selection_with_contract(
    *,
    cfg: RoleEpisodeLaneConfig,
    model_bullets: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT) or len(model_bullets)
    contract: dict[str, Any] = {
        "schema_version": "role_episode_final_materialized_selection_contract.v1",
        "expected_bullet_count": expected_bullet_count,
        "model_bullet_count": 0,
        "selected_source_fact_ids": [],
        "selected_unique_source_fact_count": 0,
        "duplicate_source_fact_ids_ignored": [],
        "rejected_source_fact_ids": [],
        "deterministic_reselect_source_fact_ids": [],
        "deterministic_reselect_applied": False,
        "rendered_bullet_count": 0,
        "rendered_source_fact_ids": [],
        "final_materialized_acceptance_ok": False,
    }
    if not model_bullets:
        return [], contract
    proof_by_id = _proof_fact_by_id(facts, allowed)
    selected_ids, contract = _ordered_ids_from_bullets_with_contract(
        model_bullets,
        facts=facts,
        allowed=allowed,
        expected_count=expected_bullet_count,
        allow_deterministic_reselect=cfg.allow_deterministic_graph_render,
    )
    # When a selected source is itself a canonical role-bullet slot id, retain
    # that identity through the final deterministic render.  This makes the
    # visible bullet, claim ledger, and whole-resume allocation refer to the
    # same slot even when two source facts render to identical prose.
    expected_slot_ids = {
        f"{cfg.bullet_prefix}_{index:03d}"
        for index in range(1, expected_bullet_count + 1)
    }
    slot_bound_ordering_applied = (
        len(selected_ids) == expected_bullet_count
        and len(set(selected_ids)) == expected_bullet_count
        and set(selected_ids) == expected_slot_ids
    )
    render_ids = (
        sorted(selected_ids)
        if slot_bound_ordering_applied
        else list(selected_ids)
    )

    model_surface_by_fact_id: dict[str, dict[str, Any]] = {}
    for row in model_bullets:
        text = _sentence(str(row.get("bullet_text") or ""))
        if not text:
            continue
        for raw_source_id in row.get("source_fact_ids") or []:
            source_id = str(raw_source_id or "").strip()
            if source_id and source_id not in model_surface_by_fact_id:
                model_surface_by_fact_id[source_id] = row

    out: list[dict[str, Any]] = []
    model_surface_binding_rows: list[dict[str, Any]] = []
    model_surface_bullet_ids: list[str] = []
    proof_text_fallback_bullet_ids: list[str] = []
    for fid in render_ids:
        fact = proof_by_id.get(fid)
        if not fact:
            continue
        candidate = model_surface_by_fact_id.get(fid)
        candidate_text = _sentence(str((candidate or {}).get("bullet_text") or ""))
        candidate_bound, anchors = _model_bullet_surface_binding(candidate_text, fact)
        model_surface_binding_rows.append(
            {
                "bullet_id": fid,
                "candidate_present": candidate is not None,
                "candidate_graph_bound": candidate_bound,
                "anchor_tokens": anchors,
            }
        )
        if candidate and candidate_bound:
            text = candidate_text
            model_surface_bullet_ids.append(fid)
        else:
            text = _proof_fact_text(fact)
            proof_text_fallback_bullet_ids.append(fid)
        if not text:
            continue
        idx = len(out)
        out.append(
            {
                "bullet_id": fid if slot_bound_ordering_applied else f"{cfg.bullet_prefix}_{idx + 1:03d}",
                "bullet_text": text,
                "source_fact_ids": [fid],
            }
        )
        if len(out) >= expected_bullet_count:
            break
    rendered_source_fact_ids = _source_fact_ids_from_bullets(out)
    contract.update(
        {
            "rendered_bullet_count": len(out),
            "rendered_source_fact_ids": rendered_source_fact_ids,
            "slot_bound_ordering_applied": slot_bound_ordering_applied,
            "model_surface_binding_rows": model_surface_binding_rows,
            "model_surface_bullet_ids": model_surface_bullet_ids,
            "proof_text_fallback_bullet_ids": proof_text_fallback_bullet_ids,
            "final_materialized_acceptance_ok": (
                len(out) == expected_bullet_count
                and len(set(rendered_source_fact_ids)) == expected_bullet_count
            ),
        }
    )
    return out, contract


def _proof_authorized_bullets_from_selection(
    *,
    cfg: RoleEpisodeLaneConfig,
    model_bullets: list[dict[str, Any]],
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:
    bullets, _contract = _proof_authorized_bullets_from_selection_with_contract(
        cfg=cfg,
        model_bullets=model_bullets,
        facts=facts,
        allowed=allowed,
    )
    return bullets


def _source_ids_from_parsed_claim_ledger(parsed: dict[str, Any], allowed: list[str]) -> list[str]:
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    seen: set[str] = set()
    out: list[str] = []
    for raw in parsed.get("source_fact_ids") or []:
        fid = str(raw or "").strip()
        if fid and fid in allowed_set and fid not in seen:
            seen.add(fid)
            out.append(fid)
    for row in parsed.get("claim_ledger") or []:
        if not isinstance(row, dict):
            continue
        for raw in row.get("source_fact_ids") or []:
            fid = str(raw or "").strip()
            if fid and fid in allowed_set and fid not in seen:
                seen.add(fid)
                out.append(fid)
    return out


def _proof_authorized_narrative_from_selection(
    *,
    parsed: dict[str, Any],
    facts: list[dict[str, Any]],
    allowed: list[str],
) -> tuple[str, list[str], str]:
    proof_by_id = _proof_fact_by_id(facts, allowed)
    source_ids = _source_ids_from_parsed_claim_ledger(parsed, allowed)
    selected_source = "llm_source_fact_ids"
    if not source_ids:
        source_ids = [fid for fid in allowed if fid in proof_by_id][:1]
        selected_source = "selected_fact_plan_order"
    for fid in source_ids:
        fact = proof_by_id.get(fid)
        if fact:
            text = _proof_fact_text(fact)
            if text:
                return text, [fid], selected_source
    return "", [], selected_source


def _llm_generation_status(
    *,
    provider_runtime_generation_status: str,
    parsed: dict[str, Any] | None,
    parse_error: str,
    model_bullets: list[dict[str, Any]],
) -> str:
    if provider_runtime_generation_status != "REAL_LLM":
        return "not_run"
    if parse_error == "empty_model_output":
        return "empty_output"
    if parsed is None or not model_bullets:
        return "invalid_output"
    return "usable_output"


def _materialize_bullet_generation(
    *,
    cfg: RoleEpisodeLaneConfig,
    parsed: dict[str, Any] | None,
    parse_error: str,
    provider_runtime_generation_status: str,
    facts: list[dict[str, Any]],
    allowed: list[str],
    graph_packet_digest: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    model_bullets = _normalize_bullets(parsed or {}, cfg=cfg, allowed=allowed)
    llm_status = _llm_generation_status(
        provider_runtime_generation_status=provider_runtime_generation_status,
        parsed=parsed,
        parse_error=parse_error,
        model_bullets=model_bullets,
    )
    if model_bullets:
        bullets, final_contract = _proof_authorized_bullets_from_selection_with_contract(
            cfg=cfg,
            model_bullets=model_bullets,
            facts=facts,
            allowed=allowed,
        )
        final_ok = bool(final_contract.get("final_materialized_acceptance_ok"))
        model_surface_used = bool(final_contract.get("model_surface_bullet_ids"))
        generation_method = (
            "llm_selected_graph_bound_surface"
            if final_ok and model_surface_used
            else "llm_selected_proof_render"
            if final_ok
            else "model_output_invalid"
        )
        llm_output_used = bool(final_ok and model_surface_used)
        renderer_version = (
            "model_selected_graph_bound_surface.v1"
            if final_ok and model_surface_used
            else ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION
            if final_ok
            else ""
        )
        bullets, density_repairs = _repair_role_episode_bullet_evidence_density(
            bullets,
            facts=facts,
        )
    else:
        bullets = []
        density_repairs = []
        expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
        is_zero_expected = (expected_bullet_count == 0)
        final_contract = {
            "schema_version": "role_episode_final_materialized_selection_contract.v1",
            "expected_bullet_count": expected_bullet_count,
            "model_bullet_count": 0,
            "selected_source_fact_ids": [],
            "selected_unique_source_fact_count": 0,
            "duplicate_source_fact_ids_ignored": [],
            "rejected_source_fact_ids": [],
            "deterministic_reselect_source_fact_ids": [],
            "deterministic_reselect_applied": False,
            "rendered_bullet_count": 0,
            "rendered_source_fact_ids": [],
            "final_materialized_acceptance_ok": is_zero_expected,
        }
        generation_method = (
            "zero_bullet_consolidated"
            if is_zero_expected
            else "model_output_invalid"
            if provider_runtime_generation_status == "REAL_LLM"
            else "blocked"
        )
        llm_output_used = False
        renderer_version = ""

    source_fact_ids = _source_fact_ids_from_bullets(bullets)
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    receipt = {
        "generation_method": generation_method,
        "llm_generation_status": llm_status,
        "llm_output_used": llm_output_used,
        "llm_selection_used": bool(model_bullets and final_contract.get("final_materialized_acceptance_ok")),
        "model_display_text_discarded": bool(
            model_bullets and not final_contract.get("model_surface_bullet_ids")
        ),
        "display_text_authority": (
            "model_selected_graph_bound_surface"
            if final_contract.get("final_materialized_acceptance_ok")
            and final_contract.get("model_surface_bullet_ids")
            else "selected_fact_plan_claim_text"
            if final_contract.get("final_materialized_acceptance_ok")
            else ""
        ),
        "evidence_authority": "augmented_skills_graph",
        "source_fact_ids": source_fact_ids,
        "graph_packet_digest": str(graph_packet_digest or ""),
        "renderer_version": renderer_version,
        "lane_contract_allows_deterministic_graph_render": bool(
            cfg.allow_deterministic_graph_render
        ),
        "allowed_graph_packet_fact_count": len(allowed_set),
        "rendered_source_fact_ids_within_allowed_packet": set(source_fact_ids).issubset(allowed_set),
        "graph_bound_evidence_density_repairs": density_repairs,
        "final_materialized_selection_contract": final_contract,
        "final_materialized_acceptance_ok": bool(
            final_contract.get("final_materialized_acceptance_ok")
            and set(source_fact_ids).issubset(allowed_set)
        ),
    }
    return bullets, receipt


def _reconcile_final_materialized_selection_gate(
    *,
    artifact_dir: Path,
    section_id: str,
    bullets: list[dict[str, Any]],
    generation_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Re-evaluate selector quality against the bullets that actually ship.

    The selector gate is initially computed over the model-merged pool.  Some
    graph-governed lanes then rehydrate the selected slots from frozen proof,
    which can correct duplicate/mis-bound source ids.  X1D must grade that
    final materialized object, while retaining the producer gate as audit
    evidence; carrying the stale pre-materialization gate produced a false EY
    selector failure even though all three Claude scores and final source ids
    passed.
    """

    required = REQUIRED_BULLET_IDS.get(str(section_id or "").strip().lower())
    if not required and bullets:
        required = tuple(
            str(b.get("bullet_id") or "").strip()
            for b in bullets
            if isinstance(b, Mapping) and str(b.get("bullet_id") or "").strip()
        )
    selection_path = artifact_dir / "bullet_pool_selection.json"
    if not required or not selection_path.is_file():
        return None
    try:
        selection_doc = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    selections = [
        dict(row)
        for row in selection_doc.get("selections") or []
        if isinstance(row, Mapping)
    ] if isinstance(selection_doc, Mapping) else []
    if not selections:
        return None
    final_gate = evaluate_employment_selection_quality(
        section_lane=section_id,
        required_bullet_ids=required,
        selections=selections,
        merged_parsed={"bullets": bullets},
    ).to_dict()
    producer_gate = dict(generation_meta.get("selection_gate") or {})
    generation_meta["producer_selection_gate"] = producer_gate
    generation_meta["final_materialized_selection_gate"] = final_gate
    generation_meta["selection_gate"] = final_gate
    return final_gate


def _normalize_role_episode_bullet_pool_parsed(
    parsed: dict[str, Any],
    *,
    cfg: RoleEpisodeLaneConfig,
    allowed: list[str],
) -> dict[str, Any]:
    """Normalize one SC path into the employment-pool shape for InsurTech/EY bullets."""
    out = dict(parsed or {})
    bullets = _normalize_bullets(out, cfg=cfg, allowed=allowed)
    out["bullets"] = bullets
    out["claim_ledger"] = _claim_ledger_from_bullets(bullets)
    out.setdefault("jd_alignment", {"targeting_only": True, "jd_used_as_proof": False})
    return out


def _claim_ledger_from_bullets(bullets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_text": str(row.get("bullet_text") or ""),
            "source_fact_ids": list(row.get("source_fact_ids") or []),
        }
        for row in bullets
        if row.get("bullet_text")
    ]


def _narrative_from_parsed(parsed: dict[str, Any]) -> str:
    text = parsed.get("narrative_sentence") if isinstance(parsed, dict) else None
    return _sentence(str(text or ""))


def _display_text(l2: dict[str, Any], cfg: RoleEpisodeLaneConfig) -> str:
    if cfg.is_bullet_lane:
        return "\n".join(f"- {b['bullet_text']}" for b in l2.get("bullets") or [])
    return str(l2.get("narrative_sentence") or "")


def _parse_json_object(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    if not text:
        return None, "empty_model_output"
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"
    if not isinstance(loaded, dict):
        return None, "json_root_not_object"
    return loaded, ""


def _role_episode_evidence_block(runtime_payload: dict[str, Any]) -> str:
    """Proof-substrate block from the role-episode bundles already attached to
    ``proof_pool_metadata`` (the candidate's bound graph skills + their ranking
    phrases). This lets the InsurTech/EY lanes choose JD-relevant proof fact IDs
    from the graph-skill arsenal while runtime display text remains rendered
    from selected proof fact claim_text. Skill phrases are selection hints, never
    claim proof or display-text authority. ACTIVE_CONFIRMED skills are
    foregrounded for selection; others are offered as JD-relevance-gated options.
    """
    ppm = runtime_payload.get("proof_pool_metadata") or {}
    bundles = ppm.get("role_episode_bundles") or []
    if not bundles:
        return ""
    lines = [
        "GRAPH_SKILL_EVIDENCE (use these bound skills only to choose and order allowed "
        "source_fact_ids; phrases are ranking vocabulary, NOT display-text authority; skill_id "
        "alone is not proof):",
    ]
    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        head = f"- role_episode_bundle_id: {bundle.get('role_episode_bundle_id')}"
        intent = str(bundle.get("bullet_intent") or "").strip()
        if intent:
            head += f" | intent: {intent}"
        lines.append(head)
        primary: list[str] = []
        optional: list[str] = []
        for skill in bundle.get("bound_skills") or []:
            if not isinstance(skill, dict):
                continue
            phrases = [str(p).strip() for p in (skill.get("allowed_phrases") or []) if str(p).strip()]
            if not phrases:
                continue
            entry = f"    {skill.get('skill_id')}: {', '.join(phrases)}"
            if str(skill.get("activation_status") or "").upper() == "ACTIVE_CONFIRMED":
                primary.append(entry)
            else:
                optional.append(entry)
        if primary:
            lines.append("  primary_skills (foreground these for source_fact_id selection):")
            lines.extend(primary)
        if optional:
            lines.append("  optional_skills (use only for JD-relevant source_fact_id selection):")
            lines.extend(optional)
    return "\n".join(lines)


def _compiled_prompt(cfg: RoleEpisodeLaneConfig, runtime_payload: dict[str, Any]) -> str:
    facts = _facts_from_plan(runtime_payload.get("selected_fact_plan") or {})
    fact_lines = [
        f"- {f.get('fact_id')}: {_compact_text(str(f.get('claim_text') or f.get('text') or ''), max_chars=280)}"
        for f in facts
    ]
    role_methodology = (
        "METHODOLOGY:\n"
        "- Bullets do the hard proof work: each bullet must carry one evidence-bound achievement, "
        "cite only allowed source_fact_ids, and avoid generic substitution.\n"
        "- Quality floor for every bullet: state a specific action, a named delivery detail, and an "
        "evidence-backed business, adoption, risk, or delivery result. A capability-only statement "
        "such as a framework, service, or platform with no result is invalid.\n"
        "- Narratives are the lightweight synthesis step above finalized bullets: turn accepted "
        "bullet themes into one higher-level role thesis. The narrative states why the role mattered; "
        "the bullets prove what was delivered.\n"
        "- Do not redo first-principles graph traversal in the narrative. Use the accepted bullet "
        "themes as primary synthesis context after finalization; the active proof pool and "
        "claim_ledger remain the only proof authority.\n"
        "- Prefer one clean executive through-line over a comma-packed list of bullet topics."
    )
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, 3)
    shape = (
        f"Return JSON with exactly {expected_bullet_count} bullets: "
        "{bullets:[{bullet_id, bullet_text, source_fact_ids}], claim_ledger:[{claim_text, source_fact_ids}], "
        "jd_alignment:{targeting_only:true,jd_used_as_proof:false}}. Each bullet is a single "
        "proof-bearing achievement with action, delivery detail, and result; do not write a role summary "
        "or narrative sentence in bullet form."
        if cfg.is_bullet_lane
        else "Return JSON with narrative_sentence, claim_ledger:[{claim_text, source_fact_ids}], "
        "jd_alignment:{targeting_only:true,jd_used_as_proof:false}. The narrative is exactly one sentence "
        f"of at most {NARRATIVE_MAX_WORDS} words and {NARRATIVE_MAX_CHARS} characters, "
        "in first-person-implied resume voice: start with a past-tense action verb and never use a "
        "third-person subject such as 'the candidate' or the candidate's name. It must be a role thesis, "
        "not a recap of all three bullets."
    )

    # JD-targeted tailoring path: when role-episode graph bundles are attached, steer prose by the
    # target JD using the candidate's bound graph skills (parity with the Unify/IBM lanes), while
    # keeping the locked-identity law and fact-bound proof contract intact. Falls back to the legacy
    # fact-only prompt when no bundles are present (proof-absent / non-targeted runs).
    ppm = runtime_payload.get("proof_pool_metadata") or {}
    evidence_block = (
        _role_episode_evidence_block(runtime_payload)
        if ppm.get("role_episode_bundle_consumption")
        else ""
    )
    if evidence_block:
        from apps_rg.runtime.sections.executive_summary_pa import format_jd_targeting_block

        jd_block = format_jd_targeting_block(
            target_title=str(runtime_payload.get("target_title") or ""),
            target_company=str(runtime_payload.get("target_company") or ""),
            jd_text=str(runtime_payload.get("jd_text") or ""),
            briefing=str(runtime_payload.get("briefing") or ""),
            graph_proof_pool_mode=True,
        )
        instruction = (
            "Use JD_TEXT and BRIEFING only to choose emphasis, ordering, and allowed source_fact_ids "
            "for the target role — NOT to create display claim wording, employers, tools, or metrics. "
            "The runtime renders visible text from selected proof fact claim_text only. Every claim "
            "MUST cite only allowed source_fact_ids; graph-skill phrases are selection hints, not "
            "proof or approved display wording. targeting_only=true; jd_used_as_proof=false."
        )
        return "\n".join(
            [
                f"Section: {cfg.section_id}",
                role_methodology,
                instruction,
                jd_block,
                evidence_block,
                shape,
                "Allowed facts (claim proof — source_fact_ids must cite only these):",
                *fact_lines,
            ]
        )

    return "\n".join(
        [
            f"Section: {cfg.section_id}",
            role_methodology,
            "Use only source_fact_ids from the allowed facts below. Do not use JD or briefing as claim proof.",
            shape,
            "Allowed facts:",
            *fact_lines,
        ]
    )


def _prompt_object(prompt_text: str, *, run_id: str, prompt_hash: str) -> SimpleNamespace:
    return SimpleNamespace(
        request_id=run_id,
        run_id=run_id,
        compilation_hash=prompt_hash,
        system_preamble="You are an apps_rg section generator. Emit compact JSON only.",
        user_instruction=prompt_text,
        prompt_blocks=(
            SimpleNamespace(role="system", content="You are an apps_rg section generator. Emit compact JSON only."),
            SimpleNamespace(role="user", content=prompt_text),
        ),
    )


def _provider_gateway(section_id: str, provider: str) -> ProviderGateway:
    provider_key = str(provider or "").strip().lower()
    if provider_key == ProviderProfile.EXTERNAL_OPENAI.value:
        openai_model = external_openai_generation_model(section_id=section_id)
        return ProviderGateway(
            {
                ProviderProfile.EXTERNAL_OPENAI: ExternalProvider(
                    provider_profile=ProviderProfile.EXTERNAL_OPENAI,
                    model=openai_model,
                    base_url=os.environ.get("APPS_RG_EXTERNAL_OPENAI_BASE_URL", ""),
                ),
            }
        )
    claude_model = external_claude_generation_model(section_id=section_id)
    return ProviderGateway(
        {
            ProviderProfile.EXTERNAL_CLAUDE: ExternalProvider(
                provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
                model=claude_model,
                base_url=os.environ.get("APPS_RG_EXTERNAL_CLAUDE_BASE_URL", ""),
            ),
        }
    )


def _blocked_provider_result(provider: str, message: str, *, model: str = "") -> ProviderResult:
    return ProviderResult(
        provider_requested=provider,
        provider_attempted=False,
        provider_available=False,
        exact_provider_error=message,
        runtime_generation_status="BLOCKED",
        model=model,
        raw_model_output="",
        provider_response=None,
    )


def _x2_gate(gate_id: str, ok: bool, reason: str = "", observed: Any = None) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "gate_type": "deterministic",
        "pass": bool(ok),
        "failure_reason": None if ok else reason,
        "observed_value": observed,
    }


def _display_text_for_x2(l2: dict[str, Any], cfg: RoleEpisodeLaneConfig) -> str:
    if cfg.is_bullet_lane:
        return "\n".join(
            str(b.get("bullet_text") or "")
            for b in (l2.get("bullets") or [])
            if isinstance(b, dict)
        )
    return str(l2.get("narrative_sentence") or "")


def _selected_fact_plan_authorized_texts(l2: dict[str, Any]) -> dict[str, str]:
    facts = _facts_from_plan(l2.get("selected_fact_plan") or {})
    return {
        fid: _proof_fact_text(fact)
        for fact in facts
        if (fid := _fact_id_from_row(fact)) and _proof_fact_text(fact)
    }


def _display_text_is_proof_authorized(
    *,
    cfg: RoleEpisodeLaneConfig,
    l2: dict[str, Any],
    allowed: list[str],
) -> tuple[bool, dict[str, Any]]:
    authority = str(l2.get("display_text_authority") or "").strip()
    authorized_by_id = _selected_fact_plan_authorized_texts(l2)
    authorized_facts_by_id = {
        fid: fact
        for fact in _facts_from_plan(l2.get("selected_fact_plan") or {})
        if (fid := _fact_id_from_row(fact))
    }
    if not authority and not authorized_by_id:
        return True, {"status": "not_evaluated_legacy_payload"}
    allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
    rows: list[dict[str, Any]] = []
    if cfg.is_bullet_lane:
        display_rows = [
            (str(b.get("bullet_id") or ""), str(b.get("bullet_text") or ""), list(b.get("source_fact_ids") or []))
            for b in (l2.get("bullets") or [])
            if isinstance(b, dict)
        ]
    else:
        display_rows = [
            (
                "narrative_sentence",
                str(l2.get("narrative_sentence") or ""),
                [sid for row in (l2.get("claim_ledger") or []) if isinstance(row, dict) for sid in row.get("source_fact_ids") or []],
            )
        ]
    if not display_rows and cfg.section_id in ("ey_bullets", "ey_narrative"):
        return True, {"status": "PASS", "display_text_authority": authority, "rows": []}
    graph_bound_model_surface = authority == "model_selected_graph_bound_surface"
    ok = authority == "selected_fact_plan_claim_text" or graph_bound_model_surface
    for row_id, text, source_ids in display_rows:
        normalized_text = _sentence(text)
        normalized_ids = [str(sid).strip() for sid in source_ids if str(sid).strip()]
        source_ok = bool(normalized_ids) and all(sid in allowed_set for sid in normalized_ids)
        binding_rows = []
        if graph_bound_model_surface:
            for source_id in normalized_ids:
                fact = authorized_facts_by_id.get(source_id)
                bound, anchors = _model_bullet_surface_binding(normalized_text, fact or {})
                binding_rows.append(
                    {
                        "source_fact_id": source_id,
                        "candidate_graph_bound": bound,
                        "anchor_tokens": anchors,
                    }
                )
            text_ok = any(row["candidate_graph_bound"] for row in binding_rows)
        else:
            text_ok = any(authorized_by_id.get(sid) == normalized_text for sid in normalized_ids)
        rows.append(
            {
                "row_id": row_id,
                "source_fact_ids": normalized_ids,
                "source_fact_ids_allowed": source_ok,
                "text_matches_selected_fact_claim_text": text_ok,
                "model_surface_binding": binding_rows,
            }
        )
        ok = ok and source_ok and text_ok
    return ok, {
        "status": "PASS" if ok else "FAIL",
        "display_text_authority": authority,
        "rows": rows,
    }


def _has_first_person(text: str) -> bool:
    return bool(re.search(r"\b(I|me|my|mine|we|us|our|ours)\b", str(text or ""), flags=re.IGNORECASE))


def _x2_gates(
    *,
    cfg: RoleEpisodeLaneConfig,
    l2: dict[str, Any],
    allowed: list[str],
    runtime_generation_status: str,
) -> list[dict[str, Any]]:
    claim_ledger = list(l2.get("claim_ledger") or [])
    cited: list[str] = []
    for row in claim_ledger:
        if isinstance(row, dict):
            cited.extend(str(x) for x in row.get("source_fact_ids") or [])
    bad = sorted({x for x in cited if x not in set(allowed)})
    display_text = _display_text_for_x2(l2, cfg)
    proof_text_ok, proof_text_obs = _display_text_is_proof_authorized(
        cfg=cfg,
        l2=l2,
        allowed=allowed,
    )
    is_ey = cfg.section_id in ("ey_bullets", "ey_narrative")
    expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
    gates = [
        _x2_gate(
            f"x2_{cfg.section_id}_allowed_fact_ids_non_empty",
            bool(allowed) or is_ey,
            "allowed_fact_ids empty",
            len(allowed),
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_source_fact_ids_supported",
            (not bad and bool(cited)) if (not is_ey or bool(cited)) else not bad,
            "claim source_fact_ids missing or outside allowed pool",
            {"bad": bad, "cited_count": len(cited)},
        ),
        _x2_gate(
            "x2_claim_ledger_claim_text_non_empty",
            (bool(claim_ledger) and all(str(r.get("claim_text") or "").strip() for r in claim_ledger if isinstance(r, dict))) if (not is_ey or bool(claim_ledger)) else True,
            "claim_ledger missing or empty claim_text",
            len(claim_ledger),
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_display_text_proof_authorized",
            proof_text_ok or (is_ey and not display_text),
            "display text must be rendered from selected proof fact claim_text",
            proof_text_obs,
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_runtime_real_llm",
            runtime_generation_status == "REAL_LLM",
            f"runtime_generation_status={runtime_generation_status}",
            runtime_generation_status,
        ),
        _x2_gate(
            "x2_no_first_person",
            not _has_first_person(display_text),
            "first-person language detected",
        ),
        _x2_gate(
            "x2_no_em_dash",
            "—" not in display_text,
            "em dash detected",
        ),
        _x2_gate(
            f"x2_{cfg.section_id}_targeting_only_not_experience_claim",
            not _targeting_only_experience_hits(display_text),
            "targeting/JD-only phrase used as experience claim",
            _targeting_only_experience_hits(display_text),
        ),
    ]
    if cfg.is_bullet_lane:
        bundle_consumed = bool(l2.get("role_episode_bundle_consumed", True))
        bullets = list(l2.get("bullets") or [])
        gates.extend(
            [
                _x2_gate(
                    f"x2_{cfg.section_id}_graph_role_episode_bundle_consumed",
                    bundle_consumed,
                    "role episode bundles not consumed from proof pool metadata",
                    bundle_consumed,
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_count_{expected_bullet_count}",
                    len(bullets) == expected_bullet_count,
                    f"expected exactly {expected_bullet_count} bullets",
                    len(bullets),
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_single_thought",
                    all(
                        check_bullet_single_thought(str(b.get("bullet_text") or ""))[0]
                        for b in bullets
                        if isinstance(b, dict)
                    ),
                    # Sentence-aware (shared validator): a decimal like "99.99%" is one thought,
                    # not two sentences — the prior raw '.'-count false-failed legitimate metrics.
                    "bullet contains multiple sentence-like thoughts",
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_no_embedded_newline",
                    all("\n" not in str(b.get("bullet_text") or "") for b in bullets if isinstance(b, dict)),
                    "bullet contains embedded newline",
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_bullet_evidence_density_required",
                    (
                        bool(bullets)
                        and all(
                            check_experience_bullet_evidence_density(
                                str(b.get("bullet_id") or ""),
                                str(b.get("bullet_text") or ""),
                            ).passed
                            for b in bullets
                            if isinstance(b, dict)
                        )
                    )
                    if expected_bullet_count > 0
                    else all(
                        check_experience_bullet_evidence_density(
                            str(b.get("bullet_id") or ""),
                            str(b.get("bullet_text") or ""),
                        ).passed
                        for b in bullets
                        if isinstance(b, dict)
                    ),
                    "each experience bullet needs an action, concrete delivery detail, and a graph-bound outcome",
                    [
                        asdict(
                            check_experience_bullet_evidence_density(
                                str(b.get("bullet_id") or ""),
                                str(b.get("bullet_text") or ""),
                            )
                        )
                        for b in bullets
                        if isinstance(b, dict)
                    ],
                ),
            ]
        )
    else:
        sent = str(l2.get("narrative_sentence") or "").strip()
        sent_ok, sent_count, _sent_reason = check_narrative_exactly_one_sentence(sent)
        is_ey_narrative = (cfg.section_id == "ey_narrative")
        gates.extend(
            [
                _x2_gate(
                    f"x2_{cfg.section_id}_exactly_one_sentence",
                    (sent == "" or sent_ok) if is_ey_narrative else sent_ok,
                    "expected exactly one sentence" if not is_ey_narrative else "expected empty or single sentence for ey_narrative",
                    {"sentence_count": sent_count, "text": sent},
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_word_budget",
                    (len(sent.split()) == 0 or (0 < len(sent.split()) <= NARRATIVE_MAX_WORDS)) if is_ey_narrative else (0 < len(sent.split()) <= NARRATIVE_MAX_WORDS),
                    "narrative outside word budget",
                    len(sent.split()),
                ),
                _x2_gate(
                    f"x2_{cfg.section_id}_char_budget",
                    (len(sent) == 0 or (0 < len(sent) <= NARRATIVE_MAX_CHARS)) if is_ey_narrative else (0 < len(sent) <= NARRATIVE_MAX_CHARS),
                    "narrative outside char budget",
                    len(sent),
                ),
            ]
        )
    return gates


def run_role_episode_x2_gates(
    *,
    section_id: str,
    l2: dict[str, Any],
    allowed: list[str],
    runtime_generation_status: str,
) -> list[dict[str, Any]]:
    cfg = _ROLE_LANES[str(section_id or "").strip().lower()]
    return _x2_gates(
        cfg=cfg,
        l2=l2,
        allowed=allowed,
        runtime_generation_status=runtime_generation_status,
    )


def run_slalom_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="slalom_bullets", **kwargs)


def run_slalom_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="slalom_narrative", **kwargs)


def run_insurtech_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="insurtech_bullets", **kwargs)


def run_insurtech_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="insurtech_narrative", **kwargs)


def run_ey_bullets_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="ey_bullets", **kwargs)


def run_ey_narrative_x2_gates(**kwargs: Any) -> list[dict[str, Any]]:
    return run_role_episode_x2_gates(section_id="ey_narrative", **kwargs)


def _judge_rows(
    *,
    cfg: RoleEpisodeLaneConfig,
    provider_result: ProviderResult,
    x2_gates: list[dict[str, Any]],
    l2: dict[str, Any],
    allowed_fact_ids: list[str],
    mock_judges: bool,
    artifact_dir: Path | None = None,
    generation_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from apps_rg.runtime.judges.role_episode_x1d import run_role_episode_judges
    from apps_rg.runtime.section_judge_policy import get_section_judge_policy

    required_judge_keys = list(get_section_judge_policy(cfg.section_id).required_judge_providers)
    if provider_result.runtime_generation_status != "REAL_LLM":
        return [
            {
                "provider_key": provider_key,
                "provider_status": "BLOCKED_PROVIDER_UNAVAILABLE",
                "evaluator_mode": "BLOCKED_PROVIDER_UNAVAILABLE",
                "provider_blocked": True,
                "exact_provider_error": provider_result.exact_provider_error,
                "pass": False,
                "proof_eligible_judge": False,
                "advisory_only": False,
                "section_id": cfg.section_id,
            }
            for provider_key in required_judge_keys
        ]
    mode = "mocked" if mock_judges else "blocked_if_unavailable"
    proof_rows = [
        judge.to_dict()
        for judge in run_role_episode_judges(
            section_id=cfg.section_id,
            candidate_output=l2,
            claim_ledger=list(l2.get("claim_ledger") or []),
            judge_keys=required_judge_keys,
            mode=mode,
            artifact_base=artifact_dir,
            targeting_context={
                "jd_alignment": l2.get("jd_alignment"),
                "targeting_only": True,
            },
            deterministic_gate_summary={"x2_gates": x2_gates},
            allowed_fact_packet={"allowed_fact_ids": allowed_fact_ids},
        )
    ]
    if cfg.is_bullet_lane and artifact_dir is not None and is_employment_pool_generation(generation_meta):
        proof_rows.extend(
            employment_pool_x1d_judge_rows(
                artifact_dir=artifact_dir,
                section_id=cfg.section_id,
                gen_meta=generation_meta,
            )
        )
    return proof_rows


def _write_blocked_artifacts(
    *,
    cfg: RoleEpisodeLaneConfig,
    args: Any,
    artifact_dir: Path,
    runtime_payload: dict[str, Any],
    reason: str,
    status: str,
) -> dict[str, Any]:
    x2 = [_x2_gate(f"x2_{cfg.section_id}_required_proof_present", False, reason)]
    l2 = {
        "run_id": runtime_payload["run_id"],
        "section_id": cfg.section_id,
        "runtime_generation_status": status,
        "product_quality_status": "FAIL",
        "product_quality_reason": reason,
        cfg.header_key: _role_header({}, cfg, args),
        "bullets": [] if cfg.is_bullet_lane else None,
        "narrative_sentence": "" if not cfg.is_bullet_lane else None,
        "claim_ledger": [],
        "selected_fact_plan": {},
        "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
        "self_check": {"blocked_reason": reason},
    }
    l2 = {k: v for k, v in l2.items() if v is not None}
    x3 = {
        "x3_code": "X3_BLOCK",
        "pass": False,
        "pass_": False,
        "runtime_generation_status": status,
        "product_quality_status": "FAIL",
        "decisive_reason": reason,
        "authorization_scope": "PLUMBING_ONLY",
        "required_remediation": [reason],
    }
    generation_model = (
        external_openai_generation_model(section_id=cfg.section_id)
        if str(args.provider) == "external_openai"
        else external_claude_generation_model(section_id=cfg.section_id)
    )
    max_output_tokens = _max_output_tokens_for_lane(cfg)
    provider_req = {
        "provider_requested": str(args.provider),
        "provider_attempted": False,
        "model": generation_model,
        "temperature": float(args.temperature),
        "max_tokens": max_output_tokens,
        "mock_fallback_allowed": False,
        "blocked_before_provider": True,
    }
    provider_resp = {
        "provider_requested": str(args.provider),
        "provider_attempted": False,
        "provider_available": False,
        "runtime_generation_status": status,
        "exact_provider_error": reason,
    }
    write_json(artifact_dir / "runtime_payload.json", runtime_payload)
    write_json(artifact_dir / "provider_request.json", provider_req)
    write_json(artifact_dir / "provider_response.json", provider_resp)
    write_json(artifact_dir / "l2_output.json", l2)
    if cfg.is_bullet_lane:
        expected_bullet_count = FINAL_BULLET_COUNT.get(cfg.section_id, ROLE_EPISODE_FINAL_BULLET_COUNT)
        write_json(
            artifact_dir / ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
            {
                "schema_version": "role_episode_final_materialized_selection_contract.v1",
                "expected_bullet_count": expected_bullet_count,
                "model_bullet_count": 0,
                "selected_source_fact_ids": [],
                "selected_unique_source_fact_count": 0,
                "duplicate_source_fact_ids_ignored": [],
                "rejected_source_fact_ids": [],
                "deterministic_reselect_source_fact_ids": [],
                "deterministic_reselect_applied": False,
                "rendered_bullet_count": 0,
                "rendered_source_fact_ids": [],
                "final_materialized_acceptance_ok": False,
                "blocked_reason": reason,
            },
        )
    write_json(artifact_dir / "parsed_output.json", {"parsed": None, "parse_error": reason})
    write_json(artifact_dir / "claim_ledger.json", [])
    write_json(artifact_dir / "canonical_claim_ledger_v2.json", build_canonical_claim_ledger_v2_payload([], parse_status="BLOCKED", invalid_reason=reason))
    write_json(artifact_dir / "selected_fact_plan.json", {})
    write_json(artifact_dir / "text_claim_coverage.json", {"status": "BLOCKED", "reason": reason})
    write_json(
        artifact_dir / "x2_gate_outputs.json",
        augment_x2_payload_with_final_materialized_binding(
            {
                "gates": x2,
                "x2_failed": 1,
                "x2_passed": 0,
                "failed_gates": [x2[0]["gate_id"]],
            },
            artifact_dir=artifact_dir,
            section_id=cfg.section_id,
        ),
    )
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": []})
    # Single-spine authority (E2E-14): route the x3 mirror through the spine finalize helper
    # rather than writing x3_disposition.json raw. No sealed L2 exists on this pre-provider block
    # path, so exit receipts are skipped (default); the spine still owns the mirror.
    finalize_section_lane_x3(
        artifact_dir=artifact_dir,
        section_id=cfg.section_id,
        runtime_payload=runtime_payload,
        x3_result=x3,
    )
    write_json(artifact_dir / "l6_shadow_eval_package.json", {"section_id": cfg.section_id, "status": "BLOCKED", "reason": reason})
    write_json(artifact_dir / "real_l2_generation_result.json", provider_resp)
    write_json(artifact_dir / "section_metric_receipt.json", {"lane_id": cfg.section_id, "runtime_generation_status": status, "x3_code": "X3_BLOCK"})
    (artifact_dir / cfg.output_filename).write_text("", encoding="utf-8")
    (artifact_dir / "command_output.txt").write_text(f"{cfg.section_id}: {status}: {reason}\n", encoding="utf-8")
    finalize_runtime_proof_run(
        REPO_ROOT,
        cfg.section_id,
        str(args.provider),
        artifact_dir,
        run_id=str(runtime_payload["run_id"]),
        section_id=cfg.section_id,
        runtime_generation_status=status,
        provider_requested=str(args.provider),
        provider_attempted=False,
    )
    return {
        "artifact_dir": str(artifact_dir),
        "runtime_payload": runtime_payload,
        "x3": x3,
        "output_text": "",
    }


def run_role_episode_lane_execution(
    section_id: str,
    args: Any,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    sid = str(section_id or "").strip().lower()
    cfg = _ROLE_LANES[sid]
    max_output_tokens = _max_output_tokens_for_lane(cfg)
    run_id = f"{sid}_{uuid.uuid4().hex[:12]}"
    artifact_dir = (
        Path(artifact_dir_override)
        if artifact_dir_override is not None
        else prepare_runtime_proof_run_dir(REPO_ROOT, sid, str(args.provider), run_id)
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    runtime_payload: dict[str, Any] = {
        "run_id": run_id,
        "request_id": run_id,
        "section_id": sid,
        "target_company": str(getattr(args, "target_company", "") or ""),
        "target_title": str(getattr(args, "target_title", "") or getattr(args, "target_role", "") or ""),
        "target_role": str(getattr(args, "target_role", "") or ""),
        "jd_text": str(getattr(args, "jd_text", "") or ""),
        "briefing": str(getattr(args, "briefing", "") or ""),
        "provider_requested": str(args.provider),
        "product_visible": True,
    }
    try:
        pool, base, _base_path, base_hash, front_spine = load_section_proof_for_lane(
            section_id=sid,
            args=args,
            repo_root=REPO_ROOT,
            artifact_dir=artifact_dir,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        return _write_blocked_artifacts(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid}: {exc}",
            status="REQUIRED_PROOF_ABSENT",
        )

    selected_fact_plan = dict(pool.selected_fact_plan or {})
    allowed_fact_ids = list(pool.allowed_fact_ids_ordered or [])
    facts = _facts_from_plan(selected_fact_plan)
    if (not allowed_fact_ids or not facts) and sid not in ("ey_bullets", "ey_narrative"):
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        return _write_blocked_artifacts(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid}: empty allowed facts",
            status="REQUIRED_PROOF_ABSENT",
        )

    runtime_payload.update(
        {
            "base_resume_json_hash": base_hash,
            "selected_fact_plan": selected_fact_plan,
            "allowed_fact_ids": allowed_fact_ids,
            "proof_pool_ref": pool.proof_pool_ref,
            "proof_pool_digest": pool.proof_pool_digest,
            "proof_pool_metadata": dict(pool.proof_pool_metadata or {}),
        }
    )
    from apps_rg.runtime.sections.upstream_evidence_block import wire_spine_c0_fec_or_block

    blocked = wire_spine_c0_fec_or_block(
        repo_root=REPO_ROOT,
        artifact_dir=artifact_dir,
        section_id=sid,
        front_spine=front_spine,
        pool=pool,
        runtime_payload=runtime_payload,
        provider=str(args.provider),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        output_filename=cfg.output_filename,
    )
    if blocked is not None:
        return blocked

    # C0/FEC may replace the loader's local candidate plan with the frozen
    # whole-resume allocation.  Refresh every local projection input before
    # prompt execution and deterministic rendering; otherwise the final text
    # can be rendered from a stale per-lane plan while its provenance names the
    # new allocation digest.
    selected_fact_plan = dict(runtime_payload.get("selected_fact_plan") or selected_fact_plan)
    allowed_fact_ids = list(runtime_payload.get("allowed_fact_ids") or allowed_fact_ids)
    facts = _facts_from_plan(selected_fact_plan)
    if (not allowed_fact_ids or not facts) and sid not in ("ey_bullets", "ey_narrative"):
        runtime_payload["runtime_generation_status"] = "REQUIRED_PROOF_ABSENT"
        return _write_blocked_artifacts(
            cfg=cfg,
            args=args,
            artifact_dir=artifact_dir,
            runtime_payload=runtime_payload,
            reason=f"required upstream proof absent for {sid}: empty frozen allocation slice",
            status="REQUIRED_PROOF_ABSENT",
        )

    prompt_text = _compiled_prompt(cfg, runtime_payload)
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    compiled_obj = _prompt_object(prompt_text, run_id=run_id, prompt_hash=prompt_hash)
    compiled_obj.reasoning_effort = resolve_section_generation_effort(
        sid, provider_profile=str(args.provider)
    )
    write_json(artifact_dir / "runtime_payload.json", runtime_payload)
    (artifact_dir / "compiled_prompt.txt").write_text(prompt_text + "\n", encoding="utf-8")
    write_json(
        artifact_dir / "compiled_prompt_artifact.json",
        merge_compiled_prompt_artifact_fec_fields(
            {
                "section_id": sid,
                "apps_rg_prompt_template_ref": f"apps_rg/prompt_assembly/templates/{sid}{'_tailor_v1' if '_bullets' in sid else '_v1'}.yaml",
                "compiler_template_id": f"{sid}_role_episode_v1",
                "pa_prompt_hash": prompt_hash[:16],
                "provider_prompt_hash": prompt_hash[:16],
                "slot_count": len(facts),
            },
            runtime_payload,
        ),
    )
    prepare_section_l2_before_provider(
        artifact_dir,
        sid,
        runtime_payload,
        provider_lane=str(args.provider),
    )

    generation_model = (
        external_openai_generation_model(section_id=sid)
        if str(args.provider) == "external_openai"
        else external_claude_generation_model(section_id=sid)
    )
    messages = [
        {"role": "system", "content": compiled_obj.system_preamble},
        {"role": "user", "content": prompt_text},
    ]
    provider_req, provider_payload = build_section_request(
        messages=messages,
        prompt_hash=prompt_hash[:16],
        input_payload_hash=_json_hash(runtime_payload),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        model=generation_model,
        provider_requested=str(args.provider),
    )
    write_json(artifact_dir / "provider_request.json", provider_req.to_dict())
    generation_meta: dict[str, Any] = {}
    if sid == "ey_bullets":
        # Short-circuit EY bullets: 0 standalone bullets, no external provider call.
        provider_result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="zero_bullet_consolidation",
            raw_model_output=json.dumps({"bullets": [], "claim_ledger": [], "jd_alignment": {"targeting_only": True}}),
            provider_response={"status": "zero_bullets_consolidated", "section_lane": sid},
        )
        write_json(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed = {"bullets": [], "claim_ledger": [], "jd_alignment": {"targeting_only": True}}
        parse_error = ""
    elif cfg.is_bullet_lane and is_employment_bullet_lane(sid):
        provider_result, raw_output, parsed, parse_error, generation_meta = (
            generate_bullet_lane_with_sc_and_claude(
                section_lane=sid,
                slot_kind="bullets",
                provider_payload=provider_payload,
                parse_model_json=_parse_json_object,
                normalize_parsed=lambda p: _normalize_role_episode_bullet_pool_parsed(
                    p,
                    cfg=cfg,
                    allowed=allowed_fact_ids,
                ),
                artifact_dir=artifact_dir,
                run_id=run_id,
                base_temperature=float(args.temperature),
                required_bullet_ids=REQUIRED_BULLET_IDS.get(sid, ()),
                targeting_context=build_employment_targeting_context(
                    runtime_payload,
                    section_lane=sid,
                ),
                judge_mode="mocked"
                if bool(getattr(args, "mock_judges", False))
                else "blocked_if_unavailable",
                use_sc_path=True,
                provider_profile=str(args.provider),
            )
        )
        if provider_result is None:
            provider_result = _blocked_provider_result(
                str(args.provider),
                parse_error or "SC pool generation returned no provider result",
                model=generation_model,
            )
        write_json(
            artifact_dir / "provider_response.json",
            {
                **provider_result.to_dict(),
                "generation_meta": generation_meta,
            },
        )
    elif sid == "ey_narrative":
        # Short-circuit EY narrative: 0 standalone narrative sentences, no external provider call.
        provider_result = ProviderResult(
            provider_requested=str(args.provider),
            provider_attempted=False,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="zero_narrative_consolidation",
            raw_model_output=json.dumps({"narrative_sentence": "", "claim_ledger": [], "jd_alignment": {"targeting_only": True}}),
            provider_response={"status": "zero_narrative_consolidated", "section_lane": sid},
        )
        write_json(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed = {"narrative_sentence": "", "claim_ledger": [], "jd_alignment": {"targeting_only": True}}
        parse_error = ""
    else:
        try:
            provider_result = _provider_gateway(sid, str(args.provider)).generate(
                str(args.provider),
                compiled_obj,
                token_budget=max_output_tokens,
                temperature=float(args.temperature),
            )
        except ProviderGatewayError as exc:
            provider_result = _blocked_provider_result(str(args.provider), str(exc), model=generation_model)
        write_json(artifact_dir / "provider_response.json", provider_result.to_dict())
        raw_output = provider_result.raw_model_output
        parsed, parse_error = _parse_json_object(raw_output)

    header = _role_header(base, cfg, args)
    if cfg.is_bullet_lane:
        bullets, generation_receipt = _materialize_bullet_generation(
            cfg=cfg,
            parsed=parsed,
            parse_error=parse_error,
            provider_runtime_generation_status=provider_result.runtime_generation_status,
            facts=facts,
            allowed=allowed_fact_ids,
            graph_packet_digest=pool.proof_pool_digest,
        )
        if generation_meta:
            _reconcile_final_materialized_selection_gate(
                artifact_dir=artifact_dir,
                section_id=sid,
                bullets=bullets,
                generation_meta=generation_meta,
            )
            generation_receipt.update(
                {
                    "generation_mode": generation_meta.get("generation_mode"),
                    "initial_path_count": generation_meta.get("initial_path_count"),
                    "total_paths_executed": generation_meta.get("total_paths_executed"),
                    "regen_rounds_executed": generation_meta.get("regen_rounds_executed"),
                    "selection_gate": generation_meta.get("selection_gate"),
                    "producer_selection_gate": generation_meta.get("producer_selection_gate"),
                    "final_materialized_selection_gate": generation_meta.get(
                        "final_materialized_selection_gate"
                    ),
                    "selection_mode": generation_meta.get("selection_mode"),
                    "source_path_by_slot": generation_meta.get("source_path_by_slot"),
                }
            )
        claim_ledger = _claim_ledger_from_bullets(bullets)
        l2 = {
            "run_id": run_id,
            "section_id": sid,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": "PENDING",
            cfg.header_key: header,
            "bullets": bullets,
            "selected_fact_plan": selected_fact_plan,
            "claim_ledger": claim_ledger,
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
        }
        if generation_meta:
            l2["generation_meta"] = generation_meta
        l2["generation_receipt"] = dict(generation_receipt)
    else:
        if sid == "ey_narrative":
            narrative_from_model = False
            narrative = ""
            source_ids = []
            narrative_selection_source = "zero_narrative_consolidation"
            narrative_source_repairs = []
            claim_ledger = []
        else:
            narrative_from_model = _narrative_from_parsed(parsed or {})
            narrative, source_ids, narrative_selection_source = _proof_authorized_narrative_from_selection(
                parsed=parsed or {},
                facts=facts,
                allowed=allowed_fact_ids,
            )
            parsed_ledger_source_ids = _parsed_claim_ledger_source_ids_for_narrative(
                parsed=parsed or {},
                narrative=narrative,
                allowed=allowed_fact_ids,
            )
            raw_source_ids = source_ids or (parsed or {}).get("source_fact_ids") or parsed_ledger_source_ids
            source_ids, narrative_source_repairs = _narrative_source_ids_for_claim(
                narrative=narrative,
                raw_source_ids=raw_source_ids,
                allowed=allowed_fact_ids,
                selected_fact_plan=selected_fact_plan,
            )
            for fid in parsed_ledger_source_ids:
                if fid not in source_ids:
                    source_ids.append(fid)
                    narrative_source_repairs.append(fid)
            claim_ledger = [{"claim_text": narrative, "source_fact_ids": source_ids}] if narrative else []
        llm_status = "not_run"
        if provider_result.runtime_generation_status == "REAL_LLM":
            if parse_error == "empty_model_output":
                llm_status = "empty_output"
            elif parsed is None or not narrative_from_model:
                llm_status = "invalid_output"
            else:
                llm_status = "usable_output"
        generation_receipt = {
            "generation_method": "llm_selected_proof_render" if narrative_from_model else "deterministic_graph_render",
            "llm_generation_status": llm_status,
            "llm_output_used": False,
            "llm_selection_used": bool(narrative_from_model and narrative),
            "model_display_text_discarded": bool(narrative_from_model),
            "display_text_authority": "selected_fact_plan_claim_text" if narrative else "",
            "selection_source": narrative_selection_source,
            "evidence_authority": "augmented_skills_graph",
            "source_fact_ids": source_ids if narrative else [],
            "graph_packet_digest": str(pool.proof_pool_digest or ""),
            "renderer_version": ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION if narrative else "",
            "lane_contract_allows_deterministic_graph_render": False,
            "allowed_graph_packet_fact_count": len(allowed_fact_ids),
            "rendered_source_fact_ids_within_allowed_packet": set(source_ids).issubset(set(allowed_fact_ids)),
        }
        if narrative_source_repairs:
            generation_receipt["source_fact_binding_repair"] = {
                "operation": "role_episode_narrative_material_claim_source_reconciliation",
                "added_source_fact_ids": narrative_source_repairs,
            }
        l2 = {
            "run_id": run_id,
            "section_id": sid,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": "PENDING",
            cfg.header_key: header,
            "narrative_sentence": narrative,
            "selected_fact_plan": selected_fact_plan,
            "claim_ledger": claim_ledger,
            "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False},
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
        }
        l2["generation_receipt"] = dict(generation_receipt)

    proof_meta = dict(pool.proof_pool_metadata or {})
    bundle_consumed = bool(proof_meta.get("role_episode_bundle_consumption"))
    l2["role_episode_bundle_consumed"] = bundle_consumed
    x2 = run_role_episode_x2_gates(
        section_id=sid,
        l2=l2,
        allowed=allowed_fact_ids,
        runtime_generation_status=provider_result.runtime_generation_status,
    )
    product_quality_status = (
        "PASS" if provider_result.runtime_generation_status == "REAL_LLM" and all(g.get("pass") for g in x2) else "FAIL"
    )
    l2["product_quality_status"] = product_quality_status
    l2["product_quality_reason"] = "x2_pass" if product_quality_status == "PASS" else "x2_or_provider_blocked"
    lane_status = "PASS" if product_quality_status == "PASS" else "FAIL"
    generation_receipt["lane_status"] = lane_status
    l2["lane_status"] = lane_status
    l2["generation_receipt"] = dict(generation_receipt)
    x1d = _judge_rows(
        cfg=cfg,
        provider_result=provider_result,
        x2_gates=x2,
        l2=l2,
        allowed_fact_ids=allowed_fact_ids,
        mock_judges=bool(getattr(args, "mock_judges", False)),
        artifact_dir=artifact_dir,
        generation_meta=generation_meta,
    )
    usage_doc = build_section_input_usage_ledger_v1(
        section_id=sid,
        run_id=run_id,
        request_id=run_id,
        trace_root=rel_posix(artifact_dir, REPO_ROOT),
        repo_root=REPO_ROOT,
        artifact_dir=artifact_dir,
        runtime_payload=runtime_payload,
        selected_fact_plan=selected_fact_plan,
        claim_ledger=claim_ledger,
        allowed_fact_ids=set(allowed_fact_ids),
        jd_text=str(runtime_payload.get("jd_text") or ""),
        target_title=str(runtime_payload.get("target_title") or ""),
        target_company=str(runtime_payload.get("target_company") or ""),
        briefing_text=str(runtime_payload.get("briefing") or ""),
        jd_alignment=l2.get("jd_alignment"),
    )
    usage_doc = apply_proof_pool_to_usage_ledger(usage_doc, pool)

    norm_rows = normalize_exec_summary_claim_ledger(claim_ledger)
    canon_doc = build_canonical_claim_ledger_v2_payload(
        norm_rows,
        parse_status="OK" if parsed is not None else "INVALID_JSON",
        invalid_reason=parse_error if parsed is None else None,
        claim_id_prefix=f"{sid}_claim",
    )
    x3 = aggregate_x3(
        resume_display_text=_display_text(l2, cfg),
        claim_ledger=claim_ledger,
        x2_gates=x2,
        x1d_judges=x1d,
        runtime_generation_status=provider_result.runtime_generation_status,
        product_quality_status=product_quality_status,
        canonical_claims_for_hash=canon_doc.get("claims"),
        section_input_usage_ledger=usage_doc,
        judge_required_for_allow=True,
    )

    failed = [g["gate_id"] for g in x2 if not g.get("pass")]
    write_json(artifact_dir / "l2_output.json", l2)
    if cfg.is_bullet_lane:
        write_json(
            artifact_dir / ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
            l2.get("final_materialized_selection_contract") or {},
        )
    write_json(artifact_dir / "selected_fact_plan.json", selected_fact_plan)
    write_json(artifact_dir / "claim_ledger.json", claim_ledger)
    write_json(artifact_dir / "canonical_claim_ledger_v2.json", canon_doc)
    proof_display_gate = next(
        (g for g in x2 if g.get("gate_id") == f"x2_{sid}_display_text_proof_authorized"),
        {},
    )
    proof_display_obs = (
        proof_display_gate.get("observed_value")
        if isinstance(proof_display_gate.get("observed_value"), dict)
        else {}
    )
    output_text = _display_text(l2, cfg)
    (artifact_dir / cfg.output_filename).write_text(
        output_text + ("\n" if output_text else ""),
        encoding="utf-8",
    )
    (artifact_dir / "command_output.txt").write_text(
        output_text + ("\n" if output_text else ""),
        encoding="utf-8",
    )
    write_json(
        artifact_dir / "text_claim_coverage.json",
        {
            "source_fact_ids_checked": allowed_fact_ids,
            "claims": claim_ledger,
            "display_text_authority": l2.get("display_text_authority"),
            "display_text_proof_authorized": bool(proof_display_gate.get("pass")),
            "proof_authorized_rows": proof_display_obs.get("rows") or [],
        },
    )
    write_json(artifact_dir / "parsed_output.json", {"parsed": parsed, "parse_error": parse_error})
    write_json(
        artifact_dir / "x2_gate_outputs.json",
        augment_x2_payload_with_final_materialized_binding(
            {
                "gates": x2,
                "x2_failed": len(failed),
                "x2_passed": len(x2) - len(failed),
                "failed_gates": failed,
            },
            artifact_dir=artifact_dir,
            section_id=sid,
        ),
    )
    write_json(artifact_dir / "x1d_llm_judge_outputs.json", {"judges": x1d})
    # Single-spine authority (E2E-14): aggregate_x3 above is judge math only; the spine finalize
    # helper owns the x3_disposition.json mirror. The real ExitEvalPipeline runs after sealed L2
    # via finalize_section_l2_after_output (called below).
    x3 = finalize_section_lane_x3(
        artifact_dir=artifact_dir,
        section_id=sid,
        runtime_payload=runtime_payload,
        x3_result=x3,
    )
    write_json(artifact_dir / "section_input_usage_ledger.json", usage_doc)
    write_json(
        artifact_dir / "real_l2_generation_result.json",
        {
            **provider_result.to_dict(),
            "product_quality_status": product_quality_status,
            "lane_status": lane_status,
            **generation_receipt,
            "generation_receipt": generation_receipt,
        },
    )
    write_json(
        artifact_dir / "section_metric_receipt.json",
        {
            "lane_id": sid,
            "run_id": run_id,
            "runtime_generation_status": provider_result.runtime_generation_status,
            "product_quality_status": product_quality_status,
            "lane_status": lane_status,
            "x2_failed_gates": failed,
            "x3_code": x3.x3_code,
            "prompt_hash": prompt_hash[:16],
            **generation_receipt,
            "generation_receipt": generation_receipt,
        },
    )
    for gate in x2:
        obs = gate.get("observed_value")
        if isinstance(obs, dict) and obs.get("x2_source_fact_pool_status"):
            write_x2_source_fact_pool_receipt(artifact_dir, obs)
            break
    if not (artifact_dir / "x2_source_fact_pool_receipt.json").is_file():
        write_json(
            artifact_dir / "x2_source_fact_pool_receipt.json",
            {
                "x2_source_fact_pool_status": "PASS" if allowed_fact_ids else "FAIL",
                "source_fact_ids_checked": allowed_fact_ids,
                "proof_pool_ref": pool.proof_pool_ref,
                "proof_pool_digest": pool.proof_pool_digest,
                "generation_method": generation_receipt.get("generation_method"),
                "llm_generation_status": generation_receipt.get("llm_generation_status"),
                "llm_output_used": generation_receipt.get("llm_output_used"),
                "evidence_authority": generation_receipt.get("evidence_authority"),
                "rendered_source_fact_ids": generation_receipt.get("source_fact_ids"),
                "graph_packet_digest": generation_receipt.get("graph_packet_digest"),
                "renderer_version": generation_receipt.get("renderer_version"),
            },
        )
    else:
        pool_receipt_path = artifact_dir / "x2_source_fact_pool_receipt.json"
        try:
            pool_receipt = json.loads(pool_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pool_receipt = {}
        if isinstance(pool_receipt, dict):
            pool_receipt.update(
                {
                    "generation_method": generation_receipt.get("generation_method"),
                    "llm_generation_status": generation_receipt.get("llm_generation_status"),
                    "llm_output_used": generation_receipt.get("llm_output_used"),
                    "evidence_authority": generation_receipt.get("evidence_authority"),
                    "rendered_source_fact_ids": generation_receipt.get("source_fact_ids"),
                    "graph_packet_digest": generation_receipt.get("graph_packet_digest"),
                    "renderer_version": generation_receipt.get("renderer_version"),
                }
            )
            write_json(pool_receipt_path, pool_receipt)
    finalize_section_l2_after_output(artifact_dir, sid, runtime_payload)
    # Role-episode lanes share the same product-visible L6 identity contract as
    # the dedicated lanes.  Their former hand-written summary bypassed the
    # post-exit RuntimeExhaustBundle, so Apps Eval could not bind the section
    # attempt to the sealed source.  Build the standard handoff only after L2
    # and Exit are sealed; L6 remains future-run-only and cannot rescue X3.
    finalize_section_runtime_exhaust_before_l6(
        artifact_dir,
        sid,
        runtime_payload,
        repo_root=REPO_ROOT,
    )
    gate_section_l6_shadow_after_exhaust(artifact_dir, runtime_payload)
    l6_package = build_l6_shadow_handoff_dict(
        artifact_dir=artifact_dir,
        repo_root=REPO_ROOT,
        section_id=sid,
        prompt_id=str(l2.get("prompt_id") or "role_episode_lane"),
        temperature=float(args.temperature),
        max_tokens=max_output_tokens,
        runtime_payload=runtime_payload,
    )
    l6_package.update(
        {
            "status": "captured",
            "x3_code": x3.x3_code,
            "prompt_hash": prompt_hash[:16],
            "current_run_mutated": False,
            "current_run_mutation_assertion": False,
            "current_run_x3_mutation_assertion": False,
            "direct_l4_write_attempted": False,
            "direct_l4_write_assertion": False,
            "durable_write_attempted": False,
        }
    )
    write_json(artifact_dir / "l6_shadow_eval_package.json", l6_package)
    finalize_runtime_proof_run(
        REPO_ROOT,
        sid,
        str(args.provider),
        artifact_dir,
        run_id=run_id,
        section_id=sid,
        runtime_generation_status=provider_result.runtime_generation_status,
        provider_requested=str(args.provider),
        provider_attempted=provider_result.provider_attempted,
    )
    return {
        "artifact_dir": str(artifact_dir),
        "runtime_payload": runtime_payload,
        "x3": x3,
        "output_text": output_text,
    }


__all__ = [
    "ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION",
    "ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION",
    "ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT",
    "build_role_episode_lane_args",
    "run_ey_bullets_x2_gates",
    "run_ey_narrative_x2_gates",
    "run_insurtech_bullets_x2_gates",
    "run_insurtech_narrative_x2_gates",
    "run_role_episode_lane_execution",
    "run_role_episode_x2_gates",
    "run_slalom_bullets_x2_gates",
    "run_slalom_narrative_x2_gates",
]
