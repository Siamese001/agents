"""Configuration dataclasses, lane registries, and core argument/text helpers."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps_rg.repository_layout import repository_root
from apps_rg.runtime.sections.lane_artifact_io import runtime_payload_for_json, sha16
from apps_rg.runtime.sections.section_product_shape_ssot import (
    NARRATIVE_MAX_CHARS,
    NARRATIVE_MAX_WORDS,
    product_shape_gate_ids_for_lane,
)

REPO_ROOT = repository_root(Path(__file__))
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

# Source-bound completions for role-episode roots whose raw claim omits the approved outcome floor.
_ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS: dict[str, str] = {
    "reb_ey_capital_optimization_solvency": "Led quantitative derivatives, variable-annuity hedging, and insurance-capital work using exotic-pricing models, liability Greeks, and higher-order stress scenarios for regulated portfolios, delivering risk visibility for hedge-design decisions.",
    "reb_ey_erm_risk_governance": "Architected ERM operating models and BCBS 239-aligned risk-data aggregation for regulated banking and insurance clients, defining three-lines-of-defense accountability and metadata standards that standardized risk-metric definitions across business units, control owners, and reporting stakeholders.",
    "reb_slalom_agentic_client_delivery": "Architected and delivered production multi-agent orchestration (LangGraph, AWS Bedrock/AgentCore, typed A2A contracts) across utility AI charters, advancing a $3.5M modernization program, SCADA grid-restoration intelligence, and customer outage self-service targeting 20% call-center deflection.",
    "reb_slalom_engineering_practice_leadership": "Directed 105 software engineers and data leaders across 33 enterprise AI and analytics charters (29 active) for a Fortune 200 utility client, stewarding $25M+ in cumulative SOW portfolio value and sustaining 11 core outcome-led workstreams with zero red escalations.",
    "reb_slalom_governed_runtime_scaling": "Engineered outcome-based agentic evaluation harnesses, deterministic proof lineage, and a safety validation mesh enforcing 100% gate conformance, 100% citation accuracy, and 100% abstention precision across safety-critical enterprise decisions.",
    "reb_slalom_ecosystem_accelerators": "Directed Google Cloud (GCP), Anthropic Claude, and OpenAI partner co-sell and licensing expansion, scaling Gemini Enterprise from 750 to 5,750+ seats toward 10,000+ across Vertex AI and Model Armor, launching a $2.4M Claude enablement workstream with 45-day Claude Code pods, and cutting human handoffs 15 percentage points in 10 days via OpenAI Codex.",
    "reb_slalom_visual_asset_intelligence": "Architected and remediated a six-figure multi-modal visual asset intelligence SOW for power generation equipment nameplates, pairing vision-LLM extraction with deterministic Python adjudication to achieve 90% primary-field accuracy, 92% OCR accuracy, and 100% high-confidence auto-acceptance into IBM Maximo.",
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

