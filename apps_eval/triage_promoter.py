"""Human-gated ADR-040 triage candidate promoter for apps_eval fixture suites.

Pure JSON/filesystem module inside ``apps_eval/`` (excluded from production purity
fixture bans, zero SQLite imports to honor domain storage isolation).

Never runs automatically during evaluation; requires explicit human invocation via
``python -m agents learning promote-candidate <candidate_id>``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_eval.bootstrap_baselines import compute_snapshot_hash
from apps_eval.scenarios import validate_suite_fixtures

_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,80}$")

_ALL_GRADERS: list[str] = [
    "schema",
    "artifact_presence",
    "x3_disposition",
    "forbidden_content",
    "grounded_claim",
    "provenance",
    "section_structure",
    "length_bounds",
    "side_effect",
    "escalation",
    "determinism",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sanitize_scenario_id(raw: str, app_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", raw.lower()).strip("_")
    prefix = "rg_" if app_id == "apps_rg" else "lic_"
    if not cleaned.startswith(prefix):
        cleaned = f"{prefix}{cleaned}"
    cleaned = cleaned[:78].rstrip("_")
    if len(cleaned) < 4:
        cleaned = f"{prefix}triage_case"
    return cleaned


def _build_fixture_payloads(
    packet: dict[str, Any],
    scenario_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    app_id = str(packet.get("app_id", "apps_rg"))
    reason = str(packet.get("trigger_reason") or "flywheel_triage_candidate")
    expected_x3 = str(packet.get("expected_x3") or "X3B_ESCALATE_HITL")
    escalation_req = expected_x3 == "X3B_ESCALATE_HITL"

    if app_id == "apps_rg":
        req = {
            "generation_mode": "strategic_tailor",
            "jd": str(packet.get("input_summary") or "Promoted resume governance regression case."),
            "target_company": str(packet.get("target_company") or "TriageTargetCo"),
            "target_role": str(packet.get("target_role") or "VP AI Architecture"),
        }
        exp = {
            "allow_side_effects": False,
            "escalation_required": escalation_req,
            "expected_x3": expected_x3,
            "forbidden_terms": ["salary", "age", "photo", "married", "race", "religion"],
            "grounded_claims_required": True,
            "length_bounds": {"max_words": 160, "min_words": 12},
            "required_artifacts": ["resume.md"],
            "required_output_keys": ["sections"],
            "required_provenance": ["policy:triage"],
            "required_sections": ["executive_summary", "experience", "skills"],
        }
        snap: dict[str, Any] = {
            "app_id": "apps_rg",
            "artifacts": ["resume.md"],
            "claims": [
                {
                    "id": f"{scenario_id}_claim_1",
                    "source_ids": ["policy:triage"],
                    "supported": True,
                    "text": f"Promoted triage regression case: {reason}",
                }
            ],
            "output": {
                "sections": {
                    "executive_summary": f"Governed resume output for promoted triage scenario covering {reason}.",
                    "experience": "Verified delivery record enforcing strict grounding and failure-mode non-regression.",
                    "skills": "AI governance, grounding enforcement, deterministic evaluation, risk controls.",
                }
            },
            "provenance": {"evidence_refs": ["policy:triage"], "rubric_refs": ["apps_rg_resume_generation_v1"]},
            "scenario_id": scenario_id,
            "side_effects": {"product_state_mutated": False, "writes": []},
            "x3_disposition": expected_x3,
        }
        snap["deterministic_hash"] = compute_snapshot_hash(snap)
        return req, exp, snap, "resume.md", f"{scenario_id} promoted triage artifact\n"

    req = {
        "channel": "linkedin",
        "lead_profile": {"name": "Alex", "role_context": str(packet.get("input_summary") or "Executive AI role")},
        "manual_brief": f"Promoted outreach regression case: {reason}",
        "outreach_mode": "cold",
        "recipient_class": "executive_contact",
    }
    exp = {
        "allow_side_effects": False,
        "escalation_required": escalation_req,
        "expected_x3": expected_x3,
        "forbidden_terms": ["guarantee", "fake connection", "we met", "urgent secret", "bypass policy"],
        "grounded_claims_required": True,
        "length_bounds": {"max_words": 120, "min_words": 12},
        "required_artifacts": ["outreach.md"],
        "required_output_keys": ["message", "rationale", "compliance_notes"],
        "required_provenance": ["policy:triage"],
        "required_sections": ["message", "rationale", "compliance_notes"],
    }
    snap = {
        "app_id": "apps_lic",
        "artifacts": ["outreach.md"],
        "claims": [
            {
                "id": f"{scenario_id}_claim_1",
                "source_ids": ["policy:triage"],
                "supported": True,
                "text": f"Promoted outreach triage case: {reason}",
            }
        ],
        "output": {
            "compliance_notes": f"Promoted triage regression guard active for {reason}.",
            "message": "Hi Alex, sharing verified executive AI delivery background aligned strictly with supplied opportunity context.",
            "rationale": f"Bounded outreach regression scenario capturing {reason}.",
        },
        "provenance": {"evidence_refs": ["policy:triage"], "rubric_refs": ["apps_lic_outreach_v1"]},
        "scenario_id": scenario_id,
        "side_effects": {"product_state_mutated": False, "writes": []},
        "x3_disposition": expected_x3,
    }
    snap["deterministic_hash"] = compute_snapshot_hash(snap)
    return req, exp, snap, "outreach.md", f"{scenario_id} promoted triage artifact\n"


def promote_staged_triage_packet(
    packet_path: str | Path,
    *,
    target_split: str = "dev",
    reviewer: str = "operator",
    fixtures_base_dir: str | Path | None = None,
    suites_registry_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote a human-reviewed ADR-040 triage packet into an apps_eval fixture suite."""
    if target_split not in ("dev", "holdout"):
        raise ValueError(f"target_split must be 'dev' or 'holdout', got {target_split!r}")
    if not reviewer or not str(reviewer).strip():
        raise ValueError("human reviewer identifier is required for ADR-040 gated promotion")

    src = Path(packet_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"triage packet not found: {src}")
    packet = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("triage packet must be a JSON object")

    app_id = str(packet.get("app_id") or "")
    if app_id not in ("apps_rg", "apps_lic"):
        raise ValueError(f"unsupported app_id in triage packet: {app_id!r}")

    candidate_id = str(packet.get("candidate_id") or src.stem)
    scenario_id = _sanitize_scenario_id(candidate_id, app_id)
    if not _SAFE_ID_RE.fullmatch(scenario_id):
        raise ValueError(f"invalid sanitized scenario_id: {scenario_id!r}")

    suite_id = (
        f"apps_rg.{target_split}.resume_generation"
        if app_id == "apps_rg"
        else f"apps_lic.{target_split}.outreach_message"
    )
    repo_root = Path(__file__).resolve().parents[1]
    base_dir = (
        Path(fixtures_base_dir).resolve()
        if fixtures_base_dir is not None
        else (repo_root / "apps_eval" / "fixtures" / target_split / app_id).resolve()
    )
    scenario_dir = base_dir / scenario_id

    if dry_run:
        return {
            "status": "DRY_RUN",
            "candidate_id": candidate_id,
            "scenario_id": scenario_id,
            "suite_id": suite_id,
            "target_dir": scenario_dir.as_posix(),
            "reviewer": reviewer,
        }

    req, exp, snap, art_name, art_text = _build_fixture_payloads(packet, scenario_id)
    _write_json(
        scenario_dir / "scenario.yaml",
        {
            "description": str(packet.get("description") or f"Human-promoted triage case ({candidate_id})."),
            "graders": _ALL_GRADERS,
            "scenario_id": scenario_id,
        },
    )
    _write_json(scenario_dir / "input" / "request.json", req)
    _write_json(scenario_dir / "expected" / "expectations.json", exp)
    _write_json(scenario_dir / "snapshots" / "app_output_snapshot.json", snap)
    art_path = scenario_dir / "snapshots" / "artifacts" / art_name
    art_path.parent.mkdir(parents=True, exist_ok=True)
    art_path.write_text(art_text, encoding="utf-8")

    # Optionally update suites.yaml when targeting registry
    reg_path = (
        Path(suites_registry_path).resolve()
        if suites_registry_path is not None
        else (repo_root / "apps_eval" / "registry" / "suites.yaml").resolve()
    )
    registered = False
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        suites = reg.get("suites") or {}
        if suite_id in suites:
            scenarios = list(suites[suite_id].get("scenarios") or [])
            if scenario_id not in scenarios:
                scenarios.append(scenario_id)
                suites[suite_id]["scenarios"] = scenarios
                reg_path.write_text(json.dumps(reg, indent=2) + "\n", encoding="utf-8")
            registered = True

    # Mark triage packet promoted (audit trail preserved)
    packet["status"] = "PROMOTED"
    packet["promoted_at"] = _utc_now()
    packet["promoted_by"] = reviewer
    packet["promoted_suite_id"] = suite_id
    packet["promoted_scenario_id"] = scenario_id
    src.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation_problems: list[str] = []
    if fixtures_base_dir is None and registered:
        validation_problems = validate_suite_fixtures(suite_id)

    return {
        "status": "PROMOTED" if not validation_problems else "PROMOTED_WITH_WARNINGS",
        "candidate_id": candidate_id,
        "scenario_id": scenario_id,
        "suite_id": suite_id,
        "target_dir": scenario_dir.as_posix(),
        "registered": registered,
        "reviewer": reviewer,
        "validation_problems": validation_problems,
    }
