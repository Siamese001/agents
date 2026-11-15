"""Unify bullets lane constants, employment extraction, and runtime payload builders."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.briefing_resolution import resolve_briefing_for_lanes
from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.runtime.jd_resolution import resolve_jd_for_lanes
from apps_rg.runtime.reasoning.employment_bullet_pool import sc_path_count_for_lane
from apps_rg.runtime.resume_resolution import load_lane_base_resume_json
from apps_rg.runtime.sections.graph_evidence_contract import (
    build_graph_evidence_runtime_payload,
    build_selected_graph_evidence_plan,
)
from apps_rg.runtime.validators.unify_bullets_x2 import PROTECTED_BULLET_DEFAULT, UNIFY_BULLET_IDS
from ._parent import parent_attr

PROMPT_ID = "unify_bullet_tailor_v1"
UNIFY_TEMP_DEFAULT = 0.45
UNIFY_TEMP_RANGE = (0.35, 0.55)
# 2400 -> 8000 (W5, plan apps-rg-aig-remaining-lanes-closeout-d4e1f7): the 6-bullet +
# claim-ledger + coverage JSON exceeds ~2400 tokens, so every SC path's output was cut
# mid-string (full6: raw ends at `"claim_text": "Converted bespoke...`), parsed to nothing,
# and the selector merged 0 bullets -> 15-gate X2 cascade.
UNIFY_MAX_OUTPUT_TOKENS = 8000
TARGET_TITLE_DEFAULT = "SVP Engineering, Agentic AI Platforms"
TARGET_COMPANY_DEFAULT = "Synthetic Enterprise Corp."
JD_TEXT_DEFAULT = resolve_jd_for_lanes().description
BRIEFING_DEFAULT = resolve_briefing_for_lanes(briefing_artifact_ref=None).text

BULLET_ID_ALIASES = {
    **{f"B{i}": f"bul_unify_{i:03d}" for i in range(1, 7)},
    **{f"b{i}": f"bul_unify_{i:03d}" for i in range(1, 7)},
}


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps_rg" / "resume" / "base").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _find_repo_root()
LANE_KEY = "unify_bullets"
PROMPT_TEMPLATE = parent_attr("REPO_ROOT", REPO_ROOT) / "apps_rg" / "prompt_assembly" / "templates" / "unify_bullet_tailor_v1.yaml"


def sha16(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_base_resume() -> tuple[dict[str, Any], Path, str]:
    return parent_attr("load_lane_base_resume_json", load_lane_base_resume_json)(repo_root=parent_attr("REPO_ROOT", REPO_ROOT))


def extract_unify_employment(base_resume: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    facts_obj = base_resume.get("facts", base_resume)
    for emp in facts_obj.get("employment", []):
        if "unify" not in str(emp.get("employer", "")).lower():
            continue
        bullets: list[dict[str, Any]] = []
        allowed: set[str] = set()
        for bullet in emp.get("bullets", []):
            bid = bullet.get("bullet_id")
            if not bid:
                continue
            allowed.add(bid)
            row = {
                "fact_id": bid,
                "claim_text": bullet.get("text", ""),
                "source_employment": emp.get("employer"),
                "has_metric": bool(bullet.get("has_metric")),
                "metric_raw": bullet.get("metric_raw", "") if bullet.get("has_metric") else "",
                "domain": bullet.get("domain", ""),
                "technologies": bullet.get("technologies", []),
            }
            bullets.append(row)
            if row.get("metric_raw"):
                allowed.add(f"{bid}_metric_{parent_attr("sha16", sha16)(row['metric_raw'])[:8]}")
        header = {
            "employer": emp.get("employer"),
            "title": emp.get("title"),
            "location": emp.get("location"),
            "start_date": emp.get("start_date"),
            "end_date": emp.get("end_date"),
            "is_current": emp.get("is_current"),
            "fact_id": emp.get("fact_id", "exp_unify_001"),
        }
        return header, bullets, allowed
    raise ValueError("Unify employment entry not found in base resume.")


def build_selected_fact_plan(facts: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        facts,
        key=lambda r: UNIFY_BULLET_IDS.index(r["fact_id"]) if r["fact_id"] in UNIFY_BULLET_IDS else 99,
    )
    return build_selected_graph_evidence_plan(
        section_id="unify_bullets",
        selection_method="canonical_json_all_unify_bullets",
        facts=ordered,
        required_fact_ids=list(UNIFY_BULLET_IDS),
    )


def build_runtime_payload(
    *,
    base_json_path: Path,
    base_hash: str,
    unify_header: dict[str, Any],
    selected_fact_plan: dict[str, Any],
    allowed_fact_ids: set[str],
    target_title: str,
    target_company: str,
    jd_text: str,
    briefing: str,
) -> dict[str, Any]:
    return build_graph_evidence_runtime_payload(
        run_id_prefix="unify_bullets",
        section_id="unify_bullets",
        prompt_id=PROMPT_ID,
        repo_root=parent_attr("REPO_ROOT", REPO_ROOT),
        base_json_path=base_json_path,
        base_hash=base_hash,
        selected_graph_evidence_plan=selected_fact_plan,
        allowed_graph_evidence_ids=sorted(allowed_fact_ids),
        target_title=target_title,
        target_company=target_company,
        jd_text=jd_text,
        briefing=briefing,
        writable_context_scope="unify_bullets_only",
        extra_fields={
            "unify_header": unify_header,
            "protected_bullet_default": PROTECTED_BULLET_DEFAULT,
            "pool_path_count": sc_path_count_for_lane("unify_bullets"),
            "selection_model": "PROVIDER_MODEL_pool_claude_top_n_pass",
        },
    )
