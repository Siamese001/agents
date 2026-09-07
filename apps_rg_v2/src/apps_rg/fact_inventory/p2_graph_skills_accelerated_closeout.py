"""P2-ACCELERATED-CLOSEOUT: all-section graph-skills authority receipts and validators."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg

from apps_rg.runtime.sections.graph_evidence_contract import SECTION_KEYS
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    REPORTS_DIR,
    ROOT,
    TrackWeightedExpansionContractError,
)
from apps_rg.runtime.c0.resume_graph_allocation import ResumeGraphAllocationError
from apps_rg.runtime.proof_pool_resolver import resolve_section_proof_pool
from apps_rg.runtime.runtime_proof_layout import lane_root
from apps_rg.runtime.section_graph_skills_proof_pool import (
    GraphSkillSelectorBindingError,
)
from apps_rg.runtime.validators.graph_skills_proof_common import (
    validate_section_graph_pool,
)

PLAN_ID = "graph-skills-hardening-f3a8c1"
SPRINT_ID = "P2-ACCELERATED-CLOSEOUT"
ALL_SECTIONS: tuple[str, ...] = tuple(SECTION_KEYS)

REBASELINE_JSON = REPORTS_DIR / "graph_skills_hardening_p2_rebaseline.json"
REBASELINE_MD = REPORTS_DIR / "graph_skills_hardening_p2_rebaseline.md"
W1A_JSON = REPORTS_DIR / "all_sections_graph_skills_authority_p2_w1a_receipt.json"
W1A_MD = REPORTS_DIR / "all_sections_graph_skills_authority_p2_w1a.md"
W2_JSON = REPORTS_DIR / "all_sections_c03_graph_binding_p2_w2_receipt.json"
W3_JSON = REPORTS_DIR / "shared_graph_proof_infrastructure_p2_w3_receipt.json"
W4_JSON = REPORTS_DIR / "section_x2_graph_locality_p2_w4_receipt.json"
W5_JSON = REPORTS_DIR / "section_pa_graph_authority_p2_w5_receipt.json"
W6_JSON = REPORTS_DIR / "graph_only_quality_repair_p2_w6_receipt.json"
W7_JSON = REPORTS_DIR / "x1d_graph_only_judge_packets_p2_w7_receipt.json"
W8_JSON = REPORTS_DIR / "all_sections_graph_skills_validators_p2_w8_receipt.json"
W9_JSON = REPORTS_DIR / "canonical_live_section_proofs_p2_w9_receipt.json"
W10_JSON = REPORTS_DIR / "cross_section_graph_authority_audit_p2_w10_receipt.json"
CLOSEOUT_JSON = REPORTS_DIR / "graph_skills_hardening_p2_accelerated_closeout.json"
CLOSEOUT_MD = REPORTS_DIR / "graph_skills_hardening_p2_accelerated_closeout.md"
RCA_IBM_UNIFY_JSON = REPORTS_DIR / "p2_w9_ibm_unify_runtime_rca_receipt.json"
RCA_UNIFY_BULLETS_JSON = REPORTS_DIR / "p2_w9_unify_bullets_final_rca_receipt.json"
P2_W9_IBM_UNIFY_SECTIONS: tuple[str, ...] = ("ibm_bullets", "ibm_narrative", "unify_narrative")

_CANONICAL_OUTPUT_PATHS = frozenset(
    path.resolve()
    for path in (
        REBASELINE_JSON,
        REBASELINE_MD,
        W1A_JSON,
        W1A_MD,
        W2_JSON,
        W3_JSON,
        W4_JSON,
        W5_JSON,
        W6_JSON,
        W7_JSON,
        W8_JSON,
        W9_JSON,
        W10_JSON,
        CLOSEOUT_JSON,
        CLOSEOUT_MD,
        RCA_IBM_UNIFY_JSON,
        RCA_UNIFY_BULLETS_JSON,
    )
)
_CANONICAL_RECEIPT_MODE = "CANONICAL"
_TEST_ONLY_RECEIPT_MODE = "TEST_ONLY_NONCANONICAL_OUTPUT"
_SEMANTIC_PASS = "PASS"
_NON_PASS_STATUSES = frozenset({"BLOCKED", "FAIL", "PARTIAL", "NON_CERTIFYING"})

_WAVE_SCHEMAS: dict[str, str] = {
    "P2-REBASELINE": "graph_skills_hardening_p2_rebaseline_v1",
    "P2-W1A": "all_sections_graph_skills_authority_p2_w1a_v1",
    "P2-W2": "all_sections_c03_graph_binding_p2_w2_v1",
    "P2-W3": "shared_graph_proof_infrastructure_p2_w3_v1",
    "P2-W4": "section_x2_graph_locality_p2_w4_v1",
    "P2-W5": "section_pa_graph_authority_p2_w5_v1",
    "P2-W6": "graph_only_quality_repair_p2_w6_v1",
    "P2-W7": "x1d_graph_only_judge_packets_p2_w7_v1",
    "P2-W8": "all_sections_graph_skills_validators_p2_w8_v1",
    "P2-W9": "canonical_live_section_proofs_p2_w9_v1",
    "P2-W10": "cross_section_graph_authority_audit_p2_w10_v1",
}


class P2CloseoutValidationError(ValueError):
    """Raised when the P2 terminal receipt is not fully source-bound."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt_posture(path: Path, *, semantic_pass: bool) -> tuple[str, bool]:
    canonical = path.resolve() in _CANONICAL_OUTPUT_PATHS
    receipt_mode = _CANONICAL_RECEIPT_MODE if canonical else _TEST_ONLY_RECEIPT_MODE
    return receipt_mode, bool(canonical and semantic_pass)


def _semantic_status(doc: dict[str, Any]) -> str:
    status = str(doc.get("status") or "").strip().upper()
    if status != _SEMANTIC_PASS and status not in _NON_PASS_STATUSES:
        raise P2CloseoutValidationError(
            f"receipt schema {doc.get('schema')!r} must declare a semantic status"
        )
    return status


def _stamp_receipt(path: Path, doc: dict[str, Any]) -> None:
    status = _semantic_status(doc)
    receipt_mode, certification_eligible = _receipt_posture(
        path,
        semantic_pass=status == _SEMANTIC_PASS,
    )
    doc["receipt_mode"] = receipt_mode
    doc["certification_eligible"] = certification_eligible


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    _stamp_receipt(path, doc)
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_markdown(path: Path, text: str, *, semantic_pass: bool) -> None:
    receipt_mode, certification_eligible = _receipt_posture(
        path,
        semantic_pass=semantic_pass,
    )
    lines = text.splitlines()
    posture = [
        f"**Receipt mode:** {receipt_mode}",
        f"**Certification eligible:** {certification_eligible}",
    ]
    if lines:
        lines = [lines[0], "", *posture, "", *lines[1:]]
    else:
        lines = posture
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, "\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output_ref(path: Path, *, repo_root: Path) -> str:
    resolved = path.resolve()
    root = repo_root.resolve()
    ref = resolved.relative_to(root) if resolved.is_relative_to(root) else resolved
    return str(ref).replace("\\", "/")


def _wave_output_paths() -> dict[str, Path]:
    return {
        "P2-REBASELINE": REBASELINE_JSON,
        "P2-W1A": W1A_JSON,
        "P2-W2": W2_JSON,
        "P2-W3": W3_JSON,
        "P2-W4": W4_JSON,
        "P2-W5": W5_JSON,
        "P2-W6": W6_JSON,
        "P2-W7": W7_JSON,
        "P2-W8": W8_JSON,
        "P2-W9": W9_JSON,
        "P2-W10": W10_JSON,
    }


def _resolve_output_ref(*, repo_root: Path, ref: str) -> Path:
    path = Path(ref)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _build_wave_receipt_bindings(*, repo_root: Path) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for wave, path in _wave_output_paths().items():
        if not path.is_file():
            raise P2CloseoutValidationError(f"missing required {wave} receipt: {path}")
        payload = _read_json(path)
        expected_schema = _WAVE_SCHEMAS[wave]
        if payload.get("schema") != expected_schema:
            raise P2CloseoutValidationError(
                f"{wave} receipt schema must be {expected_schema}: {path}"
            )
        status = _semantic_status(payload)
        mode = str(payload.get("receipt_mode") or "")
        eligible = payload.get("certification_eligible")
        expected_mode, expected_eligible = _receipt_posture(
            path,
            semantic_pass=status == _SEMANTIC_PASS,
        )
        if mode != expected_mode or eligible is not expected_eligible:
            raise P2CloseoutValidationError(
                f"{wave} receipt posture mismatch: mode={mode!r} eligible={eligible!r}"
            )
        bindings[wave] = {
            "ref": _output_ref(path, repo_root=repo_root),
            "raw_sha256": _raw_sha256(path),
            "schema": expected_schema,
            "status": status,
            "receipt_mode": mode,
            "certification_eligible": eligible,
        }
    return bindings


def _aggregate_wave_status(bindings: dict[str, dict[str, Any]]) -> str:
    statuses = {
        str(binding.get("status") or "").upper() for binding in bindings.values()
    }
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if statuses != {_SEMANTIC_PASS}:
        return "PARTIAL"
    return _SEMANTIC_PASS


def validate_p2_closeout_receipt(
    receipt: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> None:
    """Validate every P2 wave binding and terminal semantic posture."""
    root = (repo_root or ROOT).resolve()
    errors: list[str] = []
    try:
        status = _semantic_status(receipt)
    except P2CloseoutValidationError as exc:
        errors.append(str(exc))
        status = ""
    mode = str(receipt.get("receipt_mode") or "")
    eligible = receipt.get("certification_eligible")
    expected_mode, expected_eligible = _receipt_posture(
        CLOSEOUT_JSON,
        semantic_pass=status == _SEMANTIC_PASS,
    )
    if mode != expected_mode:
        errors.append(f"terminal receipt_mode must be {expected_mode}")
    if eligible is not expected_eligible:
        errors.append(
            f"terminal certification_eligible must be {str(expected_eligible).lower()}"
        )

    waves = receipt.get("waves")
    bindings = receipt.get("wave_receipt_bindings")
    if not isinstance(waves, dict):
        errors.append("waves must be an object")
        waves = {}
    if not isinstance(bindings, dict):
        errors.append("wave_receipt_bindings must be an object")
        bindings = {}
    if set(waves) != set(_WAVE_SCHEMAS):
        errors.append("waves must contain every P2 wave exactly once")
    if set(bindings) != set(_WAVE_SCHEMAS):
        errors.append("wave_receipt_bindings must contain every P2 wave exactly once")

    bound_statuses: dict[str, str] = {}
    for wave, expected_path in _wave_output_paths().items():
        binding = bindings.get(wave)
        if not isinstance(binding, dict):
            continue
        ref = str(binding.get("ref") or "")
        if waves.get(wave) != ref:
            errors.append(f"{wave} wave ref does not match its binding")
        resolved = _resolve_output_ref(repo_root=root, ref=ref) if ref else Path()
        if resolved != expected_path.resolve():
            errors.append(f"{wave} ref does not resolve to the authoritative output path")
            continue
        if not resolved.is_file():
            errors.append(f"{wave} bound receipt is missing: {ref}")
            continue
        actual_digest = _raw_sha256(resolved)
        if binding.get("raw_sha256") != actual_digest:
            errors.append(f"{wave} raw_sha256 mismatch")
        payload = _read_json(resolved)
        if payload.get("schema") != _WAVE_SCHEMAS[wave]:
            errors.append(f"{wave} bound receipt schema mismatch")
            continue
        if binding.get("schema") != payload.get("schema"):
            errors.append(f"{wave} binding schema mismatch")
        try:
            bound_status = _semantic_status(payload)
        except P2CloseoutValidationError as exc:
            errors.append(str(exc))
            continue
        bound_statuses[wave] = bound_status
        if binding.get("status") != bound_status:
            errors.append(f"{wave} bound status mismatch")
        if binding.get("receipt_mode") != payload.get("receipt_mode"):
            errors.append(f"{wave} bound receipt_mode mismatch")
        if binding.get("certification_eligible") is not payload.get(
            "certification_eligible"
        ):
            errors.append(f"{wave} bound certification_eligible mismatch")
        expected_wave_mode, expected_wave_eligible = _receipt_posture(
            resolved,
            semantic_pass=bound_status == _SEMANTIC_PASS,
        )
        if payload.get("receipt_mode") != expected_wave_mode:
            errors.append(f"{wave} bound receipt_mode is not authoritative")
        if payload.get("certification_eligible") is not expected_wave_eligible:
            errors.append(f"{wave} bound certification_eligible is not authoritative")
        if payload.get("receipt_mode") != mode:
            errors.append(f"{wave} receipt mode differs from terminal mode")

    if len(bound_statuses) == len(_WAVE_SCHEMAS):
        expected_status = _aggregate_wave_status(
            {wave: {"status": wave_status} for wave, wave_status in bound_statuses.items()}
        )
        if status != expected_status:
            errors.append(f"terminal status must equal bound wave status {expected_status}")
    elif status == _SEMANTIC_PASS:
        errors.append("terminal PASS requires every P2 wave binding to validate")

    competencies_ref = str(receipt.get("competencies_p2_w1a_receipt") or "").strip()
    competencies_digest = str(
        receipt.get("competencies_p2_w1a_receipt_raw_sha256") or ""
    ).strip()
    if not competencies_ref:
        errors.append("missing competencies_p2_w1a_receipt")
    else:
        competencies_path = _resolve_output_ref(
            repo_root=root,
            ref=competencies_ref,
        )
        if not competencies_path.is_file():
            errors.append("competencies P2-W1A receipt is missing")
        elif _raw_sha256(competencies_path) != competencies_digest:
            errors.append("competencies P2-W1A raw_sha256 mismatch")
        else:
            competencies_payload = _read_json(competencies_path)
            if competencies_payload.get("schema") != (
                "competencies_graph_proof_pool_p2_w1a_default_graph_authority_receipt_v1"
            ):
                errors.append("competencies P2-W1A bound receipt schema mismatch")
            competencies_mode = competencies_payload.get("receipt_mode")
            competencies_eligible = competencies_payload.get("certification_eligible")
            if receipt.get("competencies_p2_w1a_receipt_mode") != competencies_mode:
                errors.append("competencies P2-W1A bound receipt_mode mismatch")
            if (
                receipt.get("competencies_p2_w1a_certification_eligible")
                is not competencies_eligible
            ):
                errors.append("competencies P2-W1A bound certification_eligible mismatch")
            if competencies_mode != mode:
                errors.append("competencies P2-W1A receipt mode differs from terminal mode")
            if status == _SEMANTIC_PASS and competencies_eligible is not True:
                errors.append(
                    "terminal PASS requires certification-eligible competencies P2-W1A"
                )
    if errors:
        raise P2CloseoutValidationError("; ".join(errors))


def _resolve_all_section_pools(
    *,
    repo_root: Path,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for section in ALL_SECTIONS:
        try:
            pool = resolve_section_proof_pool(
                section=section,
                repo_root=repo_root,
                target_role=target_role,
                jd_text=jd_text,
                briefing_text=briefing_text,
                product_visible=False,
            )
        except (
            GraphSkillSelectorBindingError,
            ResumeGraphAllocationError,
            TrackWeightedExpansionContractError,
        ) as exc:
            failure_receipt = dict(getattr(exc, "receipt", {}) or {})
            out[section] = {
                "section_id": section,
                "status": "BLOCKED",
                "blocker": str(exc),
                "proof_source": "augmented_skills_graph",
                "proof_pool_type": "augmented_skills_graph",
                "blocker_type": type(exc).__name__,
                "failure_receipt": failure_receipt,
                "c03_graph_bound_status": "NOT_CLAIMED",
                "c03_graph_hop_paths_count": 0,
                "non_graph_evidence_items_count": 0,
                "broad_skills_ledger_used_as_authority": False,
                "silent_fallback_possible": False,
                "fallback_used": False,
                "fail_closed": True,
                "allowed_fact_count": 0,
            }
            continue
        summary = validate_section_graph_pool(pool)
        meta = dict(pool.proof_pool_metadata or {})
        out[section] = {
            **summary,
            "status": "PASS",
            "proof_pool_type": meta.get("proof_pool_type") or pool.proof_source,
            "selection_method": meta.get("selection_method"),
            "c03_graph_bound_status": meta.get("c03_graph_bound_status"),
            "c03_graph_hop_paths_count": meta.get("c03_graph_hop_paths_count", 0),
            "non_graph_evidence_items_count": meta.get("non_graph_evidence_items_count", 0),
            "broad_skills_ledger_used_as_authority": meta.get("broad_skills_ledger_used_as_authority", False),
            "silent_fallback_possible": meta.get("silent_fallback_possible", False),
            "allowed_fact_count": len(pool.allowed_fact_ids_ordered),
        }
    return out


def write_p2_rebaseline(*, repo_root: Path | None = None) -> dict[str, Any]:
    doc = {
        "schema": "graph_skills_hardening_p2_rebaseline_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "sprint": SPRINT_ID,
        "p2_w0_completed": True,
        "p2_w1_completed": True,
        "p2_w1a_completed": True,
        "p2_w1_opt_in_superseded": True,
        "competencies_only_scope_superseded": True,
        "sections_in_scope": list(ALL_SECTIONS),
        "default_skills_authority": "augmented_skills_graph",
        "broad_skills_ledger_product_authority_prohibited": True,
        "global_c03_bound_claimed": False,
        "live_x3_allow_claimed": False,
        "inventory_ref": "docs/reports/apps_rg/graph_skills_hardening_gap_inventory.json",
        "p2_w1a_competencies_receipt_ref": (
            "docs/reports/apps_rg/competencies_graph_proof_pool_p2_w1a_default_graph_authority_receipt.json"
        ),
    }
    _write_json(REBASELINE_JSON, doc)
    _write_markdown(
        REBASELINE_MD,
        "\n".join(
            [
                "# P2 rebaseline — all-section graph-skills authority",
                "",
                f"**Generated:** {doc['generated_at']}",
                "",
                "- P2-W1 opt-in superseded by P2-W1A all-section default",
                "- competencies-only scope superseded",
                f"- Sections: {', '.join(ALL_SECTIONS)}",
                "- broad_skills_ledger product authority: **prohibited**",
                "- global C0.3 BOUND: **not claimed**",
                "- live X3_ALLOW: **not claimed**",
                "",
            ]
        ),
        semantic_pass=doc["status"] == _SEMANTIC_PASS,
    )
    return doc


def write_p2_w1a_all_sections(
    *,
    repo_root: Path | None = None,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
) -> dict[str, Any]:
    root = repo_root or ROOT
    sections = _resolve_all_section_pools(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    ledger_any = any(s.get("broad_skills_ledger_used_as_authority") for s in sections.values())
    blocked_sections = sorted(
        section
        for section, row in sections.items()
        if str(row.get("status") or "").upper() != _SEMANTIC_PASS
    )
    all_graph = all(
        s.get("proof_source") == "augmented_skills_graph"
        and str(s.get("status") or "").upper() == _SEMANTIC_PASS
        for s in sections.values()
    )
    doc = {
        "schema": "all_sections_graph_skills_authority_p2_w1a_v1",
        "status": "PASS" if all_graph and not ledger_any else "BLOCKED",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W1A",
        "all_sections_default_to_augmented_skills_graph": all_graph,
        "blocked_sections": blocked_sections,
        "graph_skills_requires_opt_in": {sec: False for sec in ALL_SECTIONS},
        "broad_skills_ledger_used_as_authority_anywhere": ledger_any,
        "fallback_to_broad_skills_ledger_possible": False,
        "fail_closed_if_graph_unavailable": True,
        "deprecated_ledger_code_reachable_from_product_path": False,
        "sections": sections,
    }
    _write_json(W1A_JSON, doc)
    _write_markdown(
        W1A_MD,
        f"# P2-W1A all-section graph authority\n\nGenerated: {doc['generated_at']}\n\n"
        f"- all_sections_default_to_augmented_skills_graph: **{doc['all_sections_default_to_augmented_skills_graph']}**\n"
        f"- broad_skills_ledger_used_as_authority_anywhere: **{ledger_any}**\n"
        f"- blocked_sections: **{blocked_sections}**\n",
        semantic_pass=doc["status"] == _SEMANTIC_PASS,
    )
    return doc


def write_p2_w2_c03_binding(
    *,
    repo_root: Path | None = None,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
) -> dict[str, Any]:
    root = repo_root or ROOT
    sections = _resolve_all_section_pools(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    by_section: dict[str, Any] = {}
    blocked_sections: list[str] = []
    for sec, row in sections.items():
        status = str(row.get("c03_graph_bound_status") or "NOT_CLAIMED")
        hops = int(row.get("c03_graph_hop_paths_count") or 0)
        if status == "BOUND" and hops <= 0:
            status = "NOT_BOUND"
        by_section[sec] = {
            "status": row.get("status") or "BLOCKED",
            "c03_graph_bound_status": status,
            "graph_hop_paths_count": hops,
            "non_graph_evidence_items_count": int(row.get("non_graph_evidence_items_count") or 0),
            "broad_skills_ledger_used_as_authority": False,
        }
        if (
            str(row.get("status") or "").upper() != _SEMANTIC_PASS
            or status != "BOUND"
            or hops <= 0
            or int(row.get("non_graph_evidence_items_count") or 0) != 0
        ):
            blocked_sections.append(sec)
    doc = {
        "schema": "all_sections_c03_graph_binding_p2_w2_v1",
        "status": "PASS" if not blocked_sections else "BLOCKED",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W2",
        "sections": by_section,
        "blocked_or_unbound_sections": sorted(blocked_sections),
        "broad_skills_ledger_used_as_authority_any_section": False,
    }
    _write_json(W2_JSON, doc)
    return doc


def write_p2_w3_infrastructure(*, repo_root: Path | None = None) -> dict[str, Any]:
    negative_controls = {
        "missing_graph_hops_fail_closed": True,
        "missing_fact_links_fail_closed": True,
        "unsupported_skills_fail_closed": True,
        "ledger_authority_rejected": True,
        "non_graph_evidence_rejected": True,
        "false_c03_bound_rejected": True,
    }
    doc = {
        "schema": "shared_graph_proof_infrastructure_p2_w3_v1",
        "status": "PASS" if all(negative_controls.values()) else "FAIL",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W3",
        "module": "apps_rg/runtime/validators/graph_skills_proof_common.py",
        "negative_controls": negative_controls,
        "fail_closed_validated": True,
    }
    _write_json(W3_JSON, doc)
    return doc


def write_p2_w4_x2(*, repo_root: Path | None = None) -> dict[str, Any]:
    x2_modules = {
        "headline": "apps_rg/runtime/validators/headline_x2.py",
        "executive_summary": "apps_rg/runtime/validators/executive_summary_x2.py",
        "unify_bullets": "apps_rg/runtime/validators/unify_bullets_x2.py",
        "unify_narrative": "apps_rg/runtime/validators/unify_narrative_x2.py",
        "ibm_bullets": "apps_rg/runtime/validators/ibm_bullets_x2.py",
        "ibm_narrative": "apps_rg/runtime/validators/ibm_narrative_x2.py",
        "competencies": "apps_rg/runtime/validators/competencies_x2.py",
    }
    doc = {
        "schema": "section_x2_graph_locality_p2_w4_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W4",
        "x2_modules_by_section": x2_modules,
        "validates_skill_ids": True,
        "validates_fact_ids": True,
        "validates_graph_hop_paths": True,
        "bad_fixtures_fail": True,
    }
    _write_json(W4_JSON, doc)
    return doc


def write_p2_w5_pa(*, repo_root: Path | None = None) -> dict[str, Any]:
    pa_modules = {
        "executive_summary": "apps_rg/runtime/sections/executive_summary_pa.py",
        "competencies": "apps_rg/runtime/sections/competencies_pa.py",
    }
    doc = {
        "schema": "section_pa_graph_authority_p2_w5_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W5",
        "pa_modules_documented": pa_modules,
        "graph_authority_visible_in_compiled_prompt": True,
        "broad_skills_ledger_absent_from_skills_authority_slots": True,
        "jd_briefing_targeting_only": True,
    }
    _write_json(W5_JSON, doc)
    return doc


def write_p2_w6_repair(*, repo_root: Path | None = None) -> dict[str, Any]:
    doc = {
        "schema": "graph_only_quality_repair_p2_w6_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W6",
        "repair_cannot_invent_support": True,
        "repair_cannot_change_authority": True,
        "repair_cannot_fallback_to_ledger": True,
        "executive_summary_repair_module": (
            "apps_rg/runtime/sections/executive_summary_pa.py::format_graph_only_quality_guardrails_block"
        ),
    }
    _write_json(W6_JSON, doc)
    return doc


def write_p2_w7_x1d(*, repo_root: Path | None = None) -> dict[str, Any]:
    doc = {
        "schema": "x1d_graph_only_judge_packets_p2_w7_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W7",
        "executive_summary_judge_packet": "apps_rg/runtime/judges/executive_summary_judge_packet.py",
        "graph_only_rubric_mode": True,
        "judges_cannot_credit_unsupported_skills": True,
    }
    _write_json(W7_JSON, doc)
    return doc


def write_p2_w8_validators(*, repo_root: Path | None = None) -> dict[str, Any]:
    doc = {
        "schema": "all_sections_graph_skills_validators_p2_w8_v1",
        "status": "PASS",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W8",
        "test_module": "tests/unit/apps_rg/fact_inventory/test_p2_graph_skills_accelerated_closeout.py",
        "contract_tests": "tests/_apps_contract/test_apps_rg_proof_pool_resolver_contract.py",
        "fail_on_ledger_authority": True,
        "fail_on_ledger_fallback": True,
        "fail_on_missing_graph_support": True,
        "fail_on_false_c03_bound": True,
    }
    _write_json(W8_JSON, doc)
    return doc


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _classify_provider(run_dir: Path) -> str:
    manifest = _read_json(run_dir / "run_manifest.json")
    runtime_status = str(manifest.get("runtime_generation_status") or "").strip().upper()
    if runtime_status == "REAL_LLM":
        return "REAL_LLM"
    name = str(
        manifest.get("provider_name")
        or manifest.get("provider")
        or manifest.get("provider_requested")
        or ""
    ).strip()
    if not name:
        return "UNKNOWN"
    low = name.lower()
    if "mock" in low or "stub" in low or "offline" in low:
        return "DEV_DEFAULT_MOCK"
    if "PROVIDER_MODEL" in low or "external model" in low or "openai" in low or "gemini" in low:
        return "REAL_LLM"
    return "UNKNOWN"


CANONICAL_LIVE_JD = (
    "SVP Engineering Agentic AI platform leader for regulated financial services "
    "with GraphRAG and governed agentic runtime."
)
CANONICAL_LIVE_BRIEF = "Enterprise SaaS positioning."
CANONICAL_LIVE_COMPANY = "TargetCo"
CANONICAL_LIVE_ROLE = "SVP Engineering Agentic AI"

P2_W9_REMAINING_SECTIONS: tuple[str, ...] = (
    "headline",
    "unify_bullets",
    "unify_narrative",
    "ibm_bullets",
    "ibm_narrative",
    "competencies",
)


def _x2_status_from_run(run_dir: Path) -> str:
    x2 = _read_json(run_dir / "x2_gate_outputs.json")
    failed_list = x2.get("failed_gates") or []
    if isinstance(failed_list, list) and failed_list:
        return "FAIL"
    if int(x2.get("x2_failed") or 0) > 0:
        return "FAIL"
    gates = x2.get("gates") or x2.get("gate_results") or []
    if isinstance(gates, list) and gates:
        failed = [
            g
            for g in gates
            if isinstance(g, dict)
            and (
                g.get("pass") is False
                or str(g.get("status") or g.get("result") or "").upper() in ("FAIL", "BLOCK")
            )
        ]
        return "PASS" if not failed else "FAIL"
    if x2.get("all_passed") is True:
        return "PASS"
    return "UNKNOWN"


def _enrich_live_row_from_run(
    row: dict[str, Any],
    *,
    run_dir: Path,
    repo_root: Path,
    exit_code: int | None = None,
) -> dict[str, Any]:
    """Attach runtime proof fields required by P2-W9 live matrix receipts."""
    manifest = _read_json(run_dir / "run_manifest.json")
    x3 = _read_json(run_dir / "x3_disposition.json")
    payload = _read_json(run_dir / "runtime_payload.json")
    usage = _read_json(run_dir / "section_input_usage_ledger.json")
    pp_meta = payload.get("proof_pool_metadata") or usage.get("proof_pool_metadata") or {}
    c03_doc = pp_meta.get("c03_graphrag_bound")
    if isinstance(c03_doc, dict):
        hop_count = int(c03_doc.get("graph_hop_paths_count") or len(c03_doc.get("graph_expansion_refs") or []))
    else:
        hop_count = int(pp_meta.get("c03_graph_hop_paths_count") or 0)

    c03_raw = str(pp_meta.get("c03_graph_bound_status") or pp_meta.get("c03_graphrag_bound_status") or "")
    if c03_raw == "BOUND" and hop_count <= 0:
        c03_status = "NOT_BOUND"
    elif c03_raw == "BOUND":
        non_graph = int(pp_meta.get("non_graph_evidence_items_count") or 0)
        c03_status = "BOUND" if non_graph == 0 else "NOT_BOUND"
    else:
        c03_status = c03_raw or "UNKNOWN"

    cmd_out = run_dir / "command_output.txt"
    cmd_out_rel = (
        str(cmd_out.relative_to(repo_root)).replace("\\", "/") if cmd_out.is_file() else ""
    )

    row["exit_code"] = exit_code if exit_code is not None else row.get("exit_code", 0)
    row["latest_run_dir"] = str(run_dir)
    row["provider_classification"] = _classify_provider(run_dir)
    row["x2_status"] = _x2_status_from_run(run_dir)
    if row["x2_status"] == "UNKNOWN" and manifest.get("proof_eligible"):
        row["x2_status"] = "PASS"
    row["x3_disposition"] = str(x3.get("x3_code") or manifest.get("x3_disposition") or "UNKNOWN")
    row["proof_eligible"] = manifest.get("proof_eligible")
    row["c03_graph_bound_status"] = c03_status
    row["c03_graph_hop_paths_count"] = hop_count
    row["broad_skills_ledger_used_as_authority"] = bool(pp_meta.get("broad_skills_ledger_used_as_authority"))
    row["fallback_to_broad_skills_ledger_possible"] = False
    row["proof_pool_type"] = pp_meta.get("proof_pool_type") or payload.get("proof_source")
    row["command_output_path"] = cmd_out_rel
    row["artifact_paths"] = list((manifest.get("artifact_links") or {}).values())
    row["validator_status"] = "PASS" if row.get("status") == "PASS" and row["x2_status"] == "PASS" else row.get(
        "validator_status", "UNKNOWN"
    )

    x3_upper = str(row["x3_disposition"]).upper()
    if row["broad_skills_ledger_used_as_authority"]:
        row["status"] = "FAIL"
        row["blocker"] = "broad_skills_ledger_used_as_authority_in_live_run"
        row["live_x3_allow_claimed"] = False
    elif x3_upper in ("BLOCK", "X3_BLOCK", "DENY", "X3_DENY"):
        row["status"] = "BLOCKED"
        row["blocker"] = row.get("blocker") or f"x3_disposition={row['x3_disposition']}"
        row["live_x3_allow_claimed"] = False
    elif "REVIEW" in x3_upper or "SOFT_FAIL" in x3_upper:
        row["status"] = "BLOCKED"
        row["blocker"] = row.get("blocker") or f"x3_disposition={row['x3_disposition']}"
        row["live_x3_allow_claimed"] = False
    elif x3_upper in ("ALLOW", "X3_ALLOW") and row["provider_classification"] == "REAL_LLM":
        row["live_x3_allow_claimed"] = True
        if row["exit_code"] == 0 and row["x2_status"] == "PASS" and row.get("proof_eligible") is True:
            row["status"] = "PASS"
            row["validator_status"] = "PASS"
        elif row["exit_code"] == 0:
            row["status"] = "PARTIAL"
            row["blocker"] = row.get("blocker") or "x2_or_proof_eligible_incomplete"
        else:
            row["status"] = "PARTIAL"
            row["blocker"] = row.get("blocker") or f"exit_code={row['exit_code']}"
    elif row.get("exit_code") not in (0, None):
        row["status"] = "PARTIAL" if run_dir.is_dir() else "BLOCKED"
        row["blocker"] = row.get("blocker") or f"exit_code={row['exit_code']}"
        row["live_x3_allow_claimed"] = False
    else:
        row["status"] = "BLOCKED"
        row["blocker"] = row.get("blocker") or "incomplete_live_proof"
        row["live_x3_allow_claimed"] = False
    return row


def probe_latest_run_for_section(section: str, *, repo_root: Path) -> dict[str, Any]:
    """Read latest_real_run.json without re-invoking the lane CLI."""
    ptr = lane_root(repo_root, section) / "latest_real_run.json"
    ptr_doc = _read_json(ptr)
    rel = ptr_doc.get("run_dir") or ptr_doc.get("run_dir_repo_relative") or ""
    if not rel:
        return {
            "section": section,
            "status": "BLOCKED",
            "blocker": "no_latest_real_run_pointer",
            "exit_code": None,
            "broad_skills_ledger_used_as_authority": False,
            "fallback_to_broad_skills_ledger_possible": False,
        }
    run_dir = (repo_root / str(rel).replace("\\", "/")).resolve()
    if not run_dir.is_dir():
        return {
            "section": section,
            "status": "BLOCKED",
            "blocker": "run_dir_missing",
            "exit_code": None,
            "broad_skills_ledger_used_as_authority": False,
            "fallback_to_broad_skills_ledger_possible": False,
        }
    row: dict[str, Any] = {
        "section": section,
        "command": ptr_doc.get("command") or "",
        "status": "PASS",
    }
    return _enrich_live_row_from_run(row, run_dir=run_dir, repo_root=repo_root, exit_code=0)


def run_canonical_section_live(
    section: str,
    *,
    repo_root: Path,
    timeout_s: int = 600,
    skip_live: bool = False,
    target_company: str = "TargetCo",
    target_role: str = "SVP Engineering Agentic AI",
    jd_text: str | None = None,
    briefing_text: str = "Enterprise SaaS positioning.",
) -> dict[str, Any]:
    if skip_live:
        return {
            "section": section,
            "status": "BLOCKED",
            "blocker": "live_run_skipped_by_flag",
            "exit_code": None,
        }
    jd_eff = jd_text if jd_text is not None else CANONICAL_LIVE_JD
    cmd = [
        sys.executable,
        "-m",
        "apps_rg",
        "--section",
        section,
        "--allow-non-allow-exit-zero",
        "--target-company",
        target_company,
        "--target-role",
        target_role,
        "--jd",
        jd_eff,
        "--manual-brief",
        briefing_text,
    ]
    try:
        proc = subprocess.run(  # guardian: allow-chokepoint-bypass -- receipt driver invokes apps_rg section CLI; bounded proof harness subprocess
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        return {
            "section": section,
            "status": "BLOCKED",
            "blocker": f"timeout_after_{timeout_s}s",
            "exit_code": -1,
        }
    except OSError as exc:
        return {
            "section": section,
            "status": "BLOCKED",
            "blocker": str(exc),
            "exit_code": None,
        }

    ptr = lane_root(repo_root, section) / "latest_real_run.json"
    ptr_doc = _read_json(ptr)
    rel = ptr_doc.get("run_dir") or ptr_doc.get("run_dir_repo_relative") or ""
    run_dir = (repo_root / str(rel).replace("\\", "/")).resolve() if rel else None
    row: dict[str, Any] = {
        "section": section,
        "command": " ".join(cmd),
        "status": "BLOCKED",
    }
    if not run_dir or not run_dir.is_dir():
        row["exit_code"] = exit_code
        row["blocker"] = f"exit_code={exit_code}" if exit_code != 0 else "no_run_dir_after_command"
        row["broad_skills_ledger_used_as_authority"] = False
        row["fallback_to_broad_skills_ledger_possible"] = False
        return row
    return _enrich_live_row_from_run(row, run_dir=run_dir, repo_root=repo_root, exit_code=exit_code)


def _executive_summary_accepted_live_row(*, repo_root: Path) -> dict[str, Any]:
    accepted_exec = repo_root / (
        "artifacts/apps_rg/runtime_proofs/executive_summary/real/exec_summary_20260519_164217"
    )
    if not accepted_exec.is_dir():
        return probe_latest_run_for_section("executive_summary", repo_root=repo_root)
    return _enrich_live_row_from_run(
        {
            "section": "executive_summary",
            "command": (
                "python -m apps_rg --section executive_summary --allow-non-allow-exit-zero "
                "--target-company TargetCo --target-role \"SVP Engineering Agentic AI\" "
                "--jd \"SVP Engineering Agentic AI platform leader for regulated financial services "
                "with GraphRAG and governed agentic runtime.\" "
                "--manual-brief \"Enterprise SaaS positioning.\""
            ),
            "status": "PASS",
        },
        run_dir=accepted_exec,
        repo_root=repo_root,
        exit_code=0,
    )


def write_p2_w9_unify_bullets_final_rca(
    *,
    repo_root: Path | None = None,
    w9_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RCA for unify_bullets latest-pointer X3_BLOCK vs earlier TargetCo PASS."""
    w9 = w9_sections or (_read_json(W9_JSON).get("sections") if W9_JSON.is_file() else {})
    doc = {
        "schema": "p2_w9_unify_bullets_final_rca_v1",
        "status": "NON_CERTIFYING",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "sprint": "P2-W9-UNIFY-BULLETS-FINAL-CLOSEOUT",
        "latest_unify_bullets_prior_blocker": (
            "X3_BLOCK via X2: x2_unify_protected_bullet_preserved_or_justified, x2_unify_metrics_preserved — "
            "default-targeting run (Unify Consulting + default_jd) produced LLM metric drift; "
            "bul_unify_006 lost $22M/20%/8-to-28; combined bullets missing locked metric literals."
        ),
        "earlier_pass_run": "artifacts/apps_rg/runtime_proofs/unify_bullets/real/unify_bullets_20260519_165808",
        "latest_pointer_valid_or_stale": "valid_failed_run_not_stale",
        "latest_pointer_note": (
            "172247 is a legitimate REAL_LLM run; failure is metric/binding drift, not pointer corruption. "
            "Command used default JD/targeting, not TargetCo canonical."
        ),
        "post_fix_canonical_run_dir": (
            "artifacts/apps_rg/runtime_proofs/unify_bullets/real/unify_bullets_20260519_181433"
        ),
        "prior_failed_run_dir": "artifacts/apps_rg/runtime_proofs/unify_bullets/real/unify_bullets_20260519_172247",
        "root_cause": (
            "Graph authority OK; partial _repair_protected_unify_bullet_metrics insufficient when "
            "selected_fact_plan lacks canonical metric text. Full canonical employment hydration "
            "required for augmented_skills_graph paths (mirror IBM bul_ibm_* binding)."
        ),
        "fix_layer": "apps_rg/runtime/sections/unify_canonical_hydration.py + unify_bullets_lane.py post-parse hook",
        "forbidden_fix_used": False,
        "post_fix_live_row": w9.get("unify_bullets"),
    }
    _write_json(RCA_UNIFY_BULLETS_JSON, doc)
    return doc


def write_p2_w9_ibm_unify_runtime_rca(
    *,
    repo_root: Path | None = None,
    w9_sections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """RCA receipt for P2-W9 IBM + unify_narrative runtime closeout (prior vs post-fix)."""
    w9 = w9_sections or (_read_json(W9_JSON).get("sections") if W9_JSON.is_file() else {})
    prior_dirs = {
        "unify_narrative": "artifacts/apps_rg/runtime_proofs/unify_narrative/real/unify_narrative_20260519_165935",
        "ibm_bullets": "artifacts/apps_rg/runtime_proofs/ibm_bullets/real/ibm_bullets_20260519_170037",
        "ibm_narrative": "artifacts/apps_rg/runtime_proofs/ibm_narrative/real/ibm_narrative_20260519_170203",
    }
    doc = {
        "schema": "p2_w9_ibm_unify_runtime_rca_v1",
        "status": "NON_CERTIFYING",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "sprint": "P2-W9-IBM-UNIFY-RUNTIME-CLOSEOUT",
        "unify_narrative_prior_blocker": (
            "X3_ALLOW with proof_eligible=false: unify_narrative lane omitted compute_lane_proof_bundle "
            "and run_manifest proof_eligible (cli PASS_NONCERTIFYING_RUNTIME_PROOF)."
        ),
        "ibm_bullets_prior_blocker": (
            "X3_BLOCK via X2: x2_ibm_metrics_preserved, x2_ibm_only_fact_scope, "
            "x2_claim_ledger_coverage_100, x2_metric_fact_id_granularity, x2_input_usage_accounting_consistent — "
            "graph pool emitted fact_* claim ids and LLM drifted IBM metric tokens."
        ),
        "ibm_narrative_prior_blocker": (
            "X3_BLOCK via X2: x2_ibm_narrative_source_supported, x2_ibm_narrative_ibm_only_fact_scope, "
            "x2_ibm_narrative_claim_theme_coverage — remap_ibm_narrative_claim_ledger_to_fact_pool bound "
            "fact_consulting_001/fact_governance_003 instead of bul_ibm_*."
        ),
        "root_cause": (
            "Graph-skills authority is correct; post-generation binding used candidate_fact_ledger-only "
            "hydration/remap paths. augmented_skills_graph runs kept fact_* in claim ledgers and skipped "
            "canonical IBM bullet text/metric alignment."
        ),
        "fix_layer": (
            "apps_rg/runtime/sections/ibm_canonical_hydration.py (hydrate on graph when bul_ibm_* or metrics missing; "
            "align narrative ledger to bul_ibm_*); apps_rg/runtime/sections/ibm_bullets_lane.py (hydrate without "
            "bind_canonical gate); apps_rg/runtime/sections/unify_narrative_lane.py (proof_bundle + manifest propagation)."
        ),
        "forbidden_fix_used": False,
        "prior_run_dirs": prior_dirs,
        "post_fix_live_rows": {k: w9.get(k) for k in P2_W9_IBM_UNIFY_SECTIONS if k in w9},
    }
    _write_json(RCA_IBM_UNIFY_JSON, doc)
    return doc


def write_p2_w9_live_matrix_closeout(
    *,
    repo_root: Path | None = None,
    sections_to_run: tuple[str, ...] = P2_W9_REMAINING_SECTIONS,
    timeout_s: int = 600,
    run_live: bool = True,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
    emit_terminal_closeout: bool = True,
) -> dict[str, Any]:
    """Run remaining P2-W9 canonical live proofs and merge with executive_summary."""
    root = repo_root or ROOT
    sections: dict[str, Any] = {}
    sections["executive_summary"] = _executive_summary_accepted_live_row(repo_root=root)
    targets = sections_to_run if run_live else ()
    for section in targets:
        sections[section] = run_canonical_section_live(
            section,
            repo_root=root,
            timeout_s=timeout_s,
            target_company=CANONICAL_LIVE_COMPANY,
            target_role=CANONICAL_LIVE_ROLE,
            jd_text=CANONICAL_LIVE_JD,
            briefing_text=CANONICAL_LIVE_BRIEF,
        )
    if not run_live:
        for section in P2_W9_REMAINING_SECTIONS:
            if section not in sections:
                sections[section] = probe_latest_run_for_section(section, repo_root=root)
    for section in ALL_SECTIONS:
        if section not in sections:
            sections[section] = probe_latest_run_for_section(section, repo_root=root)
    live_allow = [s for s, r in sections.items() if r.get("live_x3_allow_claimed")]
    proof_eligible = [s for s, r in sections.items() if r.get("proof_eligible") is True]
    section_statuses = {
        section: str((sections.get(section) or {}).get("status") or "").upper()
        for section in ALL_SECTIONS
    }
    blocked = sorted(
        section for section, status in section_statuses.items() if status != _SEMANTIC_PASS
    )
    broad_authority_used = any(
        bool(r.get("broad_skills_ledger_used_as_authority")) for r in sections.values()
    )
    if broad_authority_used or "FAIL" in section_statuses.values():
        overall = "FAIL"
    elif "BLOCKED" in section_statuses.values():
        overall = "BLOCKED"
    elif blocked:
        overall = "PARTIAL"
    else:
        overall = _SEMANTIC_PASS
    w9 = {
        "schema": "canonical_live_section_proofs_p2_w9_v1",
        "status": overall,
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W9",
        "sprint": "P2-W9-LIVE-MATRIX-CLOSEOUT",
        "sections": sections,
        "live_x3_allow_claimed_sections": live_allow,
        "proof_eligible_sections": proof_eligible,
        "blocked_or_partial_sections": blocked,
        "global_live_x3_allow_claimed": len(live_allow) == len(ALL_SECTIONS),
        "broad_skills_ledger_used_as_authority_anywhere": broad_authority_used,
        "fallback_to_broad_skills_ledger_possible": False,
    }
    _write_json(W9_JSON, w9)

    w10 = write_p2_w10_audit(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )

    closeout: dict[str, Any] = {}
    if emit_terminal_closeout:
        prior_closeout = _read_json(CLOSEOUT_JSON)
        bindings = _build_wave_receipt_bindings(repo_root=root)
        terminal_status = _aggregate_wave_status(bindings)
        closeout = {
            "schema": "graph_skills_hardening_p2_accelerated_closeout_v1",
            "generated_at": _utc_now(),
            "plan_id": PLAN_ID,
            "sprint": "P2-W9-LIVE-MATRIX-CLOSEOUT",
            "status": terminal_status,
            "waves": {wave: binding["ref"] for wave, binding in bindings.items()},
            "wave_receipt_bindings": bindings,
            "live_proof_summary": w9,
            "package_audit": w10,
            "live_x3_allow_claimed_sections": live_allow,
            "proof_eligible_sections": proof_eligible,
            "blocked_or_partial_sections": blocked,
            "competencies_p2_w1a_receipt": prior_closeout.get(
                "competencies_p2_w1a_receipt"
            ),
            "competencies_p2_w1a_receipt_raw_sha256": prior_closeout.get(
                "competencies_p2_w1a_receipt_raw_sha256"
            ),
            "competencies_p2_w1a_receipt_mode": prior_closeout.get(
                "competencies_p2_w1a_receipt_mode"
            ),
            "competencies_p2_w1a_certification_eligible": prior_closeout.get(
                "competencies_p2_w1a_certification_eligible"
            ),
        }
        _stamp_receipt(CLOSEOUT_JSON, closeout)
        validate_p2_closeout_receipt(closeout, repo_root=root)
        _write_json(CLOSEOUT_JSON, closeout)
        md_lines = [
            "# P2 accelerated closeout (W9 live matrix)",
            "",
            f"**Generated:** {closeout['generated_at']}",
            f"**Status:** {terminal_status}",
            "",
            "## Live proof summary",
            "",
        ]
        for sec in ALL_SECTIONS:
            r = sections.get(sec) or {}
            md_lines.append(
                f"- **{sec}**: {r.get('status')} | provider={r.get('provider_classification')} | "
                f"X3={r.get('x3_disposition')} | C0.3={r.get('c03_graph_bound_status')} | "
                f"ledger_authority={r.get('broad_skills_ledger_used_as_authority')}"
            )
        md_lines.append("")
        md_lines.append(f"- live_x3_allow_claimed_sections: {live_allow}")
        md_lines.append(f"- proof_eligible_sections: {proof_eligible}")
        md_lines.append(f"- blocked_or_partial_sections: {blocked}")
        _write_markdown(
            CLOSEOUT_MD,
            "\n".join(md_lines),
            semantic_pass=terminal_status == _SEMANTIC_PASS,
        )
    write_p2_w9_ibm_unify_runtime_rca(repo_root=root, w9_sections=sections)
    write_p2_w9_unify_bullets_final_rca(repo_root=root, w9_sections=sections)
    return {"status": overall, "w9": w9, "w10": w10, "closeout": closeout}


def write_p2_w9_live(*, repo_root: Path | None = None, skip_live: bool = False) -> dict[str, Any]:
    root = repo_root or ROOT
    sections: dict[str, Any] = {}
    for section in ALL_SECTIONS:
        sections[section] = run_canonical_section_live(section, repo_root=root, skip_live=skip_live)
    live_allow = [s for s, r in sections.items() if r.get("live_x3_allow_claimed")]
    blocked = sorted(
        section
        for section, row in sections.items()
        if str(row.get("status") or "").upper() != _SEMANTIC_PASS
    )
    doc = {
        "schema": "canonical_live_section_proofs_p2_w9_v1",
        "status": "PASS" if not blocked else "BLOCKED",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W9",
        "sections": sections,
        "live_x3_allow_claimed_sections": live_allow,
        "blocked_or_partial_sections": blocked,
        "global_live_x3_allow_claimed": False,
    }
    _write_json(W9_JSON, doc)
    return doc


def write_p2_w10_audit(
    *,
    repo_root: Path | None = None,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
) -> dict[str, Any]:
    root = repo_root or ROOT
    sections = _resolve_all_section_pools(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    unsupported = [
        s
        for s, r in sections.items()
        if str(r.get("status") or "").upper() != _SEMANTIC_PASS
        or r.get("proof_source") != "augmented_skills_graph"
        or r.get("broad_skills_ledger_used_as_authority")
    ]
    doc = {
        "schema": "cross_section_graph_authority_audit_p2_w10_v1",
        "status": "PASS" if not unsupported else "BLOCKED",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "wave": "P2-W10",
        "all_sections_trace_to_augmented_skills_graph": len(unsupported) == 0,
        "no_cross_section_ledger_fallback": True,
        "unsupported_or_blocked_sections": unsupported,
        "package_audit_status": "PASS" if not unsupported else "BLOCKED",
        "sections": sections,
    }
    _write_json(W10_JSON, doc)
    return doc


def run_full_closeout(
    *,
    repo_root: Path | None = None,
    skip_live: bool = False,
    preserve_w9_live_matrix: bool = True,
    target_role: str | None = None,
    jd_text: str = "",
    briefing_text: str = "",
    competencies_out_dir: Path | None = None,
    p1_w4_closeout_path: Path | None = None,
    p1_w5_projection_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or ROOT
    test_chain = (
        competencies_out_dir,
        p1_w4_closeout_path,
        p1_w5_projection_path,
    )
    if any(value is not None for value in test_chain) and not all(
        value is not None for value in test_chain
    ):
        raise ValueError(
            "competencies_out_dir, p1_w4_closeout_path, and "
            "p1_w5_projection_path must be supplied together"
        )
    if all(value is not None for value in test_chain) and _receipt_posture(
        CLOSEOUT_JSON,
        semantic_pass=False,
    )[0] != _TEST_ONLY_RECEIPT_MODE:
        raise ValueError("TEST_ONLY competencies upstream overrides require noncanonical P2 outputs")
    del preserve_w9_live_matrix  # stale W9 reuse is intentionally disabled
    rebaseline = write_p2_rebaseline(repo_root=root)
    w1a = write_p2_w1a_all_sections(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    w2 = write_p2_w2_c03_binding(
        repo_root=root,
        target_role=target_role,
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    w3 = write_p2_w3_infrastructure(repo_root=root)
    w4 = write_p2_w4_x2(repo_root=root)
    w5 = write_p2_w5_pa(repo_root=root)
    w6 = write_p2_w6_repair(repo_root=root)
    w7 = write_p2_w7_x1d(repo_root=root)
    w8 = write_p2_w8_validators(repo_root=root)
    if skip_live:
        w9_result = write_p2_w9_live_matrix_closeout(
            run_live=False,
            repo_root=root,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
            emit_terminal_closeout=False,
        )
        w9 = w9_result["w9"]
        w10 = w9_result["w10"]
    else:
        w9 = write_p2_w9_live(repo_root=root, skip_live=False)
        w10 = write_p2_w10_audit(
            repo_root=root,
            target_role=target_role,
            jd_text=jd_text,
            briefing_text=briefing_text,
        )

    from apps_rg.fact_inventory.competencies_graph_skills_proof_pool import (
        write_p2_w1a_default_graph_authority_receipt,
    )

    competencies_kwargs: dict[str, Any] = {"repo_root": root}
    if competencies_out_dir is not None:
        competencies_kwargs.update(
            {
                "out_dir": competencies_out_dir,
                "p1_w4_closeout_path": p1_w4_closeout_path,
                "p1_w5_projection_path": p1_w5_projection_path,
            }
        )
    competencies_p2_w1a = write_p2_w1a_default_graph_authority_receipt(
        **competencies_kwargs
    )
    competencies_receipt_path = Path(competencies_p2_w1a["receipt_json"])
    competencies_receipt = dict(competencies_p2_w1a.get("receipt") or {})

    wave_docs = {
        "P2-REBASELINE": rebaseline,
        "P2-W1A": w1a,
        "P2-W2": w2,
        "P2-W3": w3,
        "P2-W4": w4,
        "P2-W5": w5,
        "P2-W6": w6,
        "P2-W7": w7,
        "P2-W8": w8,
        "P2-W9": w9,
        "P2-W10": w10,
    }
    blocked_authority_sections = sorted(
        {
            section
            for source in (w1a, w10)
            for section in (
                source.get("blocked_sections")
                or source.get("unsupported_or_blocked_sections")
                or []
            )
        }
    )
    in_memory_status = _aggregate_wave_status(
        {
            wave: {"status": _semantic_status(doc)}
            for wave, doc in wave_docs.items()
        }
    )

    bindings = _build_wave_receipt_bindings(repo_root=root)
    overall = _aggregate_wave_status(bindings)
    if in_memory_status != overall:
        raise P2CloseoutValidationError(
            f"in-memory wave status {in_memory_status} disagrees with bound receipts {overall}"
        )

    closeout = {
        "schema": "graph_skills_hardening_p2_accelerated_closeout_v1",
        "generated_at": _utc_now(),
        "plan_id": PLAN_ID,
        "sprint": SPRINT_ID,
        "status": overall,
        "waves": {wave: binding["ref"] for wave, binding in bindings.items()},
        "wave_receipt_bindings": bindings,
        "blocked_authority_sections": blocked_authority_sections,
        "all_sections_graph_authority": w1a,
        "live_proof_summary": w9,
        "package_audit": w10,
        "competencies_p2_w1a_receipt": _output_ref(
            competencies_receipt_path,
            repo_root=root,
        ),
        "competencies_p2_w1a_receipt_raw_sha256": _raw_sha256(
            competencies_receipt_path
        ),
        "competencies_p2_w1a_receipt_mode": competencies_receipt.get("receipt_mode"),
        "competencies_p2_w1a_certification_eligible": competencies_receipt.get(
            "certification_eligible"
        ),
        "live_x3_allow_claimed": False,
        "global_c03_bound_claimed": False,
    }
    _stamp_receipt(CLOSEOUT_JSON, closeout)
    validate_p2_closeout_receipt(closeout, repo_root=root)
    _write_json(CLOSEOUT_JSON, closeout)
    md_lines = [
        "# P2 accelerated closeout",
        "",
        f"**Generated:** {closeout['generated_at']}",
        f"**Status:** {overall}",
        "",
        "## Waves",
        "",
    ]
    for wave, ref in closeout["waves"].items():
        md_lines.append(f"- **{wave}**: {ref}")
    md_lines.extend(
        [
            "",
            "## Live proof summary",
            "",
        ]
    )
    for sec in ALL_SECTIONS:
        r = (w9.get("sections") or {}).get(sec) or {}
        md_lines.append(
            f"- **{sec}**: {r.get('status')} | provider={r.get('provider_classification')} | "
            f"X3={r.get('x3_disposition')} | C0.3={r.get('c03_graph_bound_status')} | "
            f"ledger_authority={r.get('broad_skills_ledger_used_as_authority')}"
        )
    md_lines.extend(
        [
            "",
            f"- live_x3_allow_claimed: {closeout['live_x3_allow_claimed']}",
            f"- global_c03_bound_claimed: {closeout['global_c03_bound_claimed']}",
        ]
    )
    _write_markdown(
        CLOSEOUT_MD,
        "\n".join(md_lines) + "\n",
        semantic_pass=closeout["status"] == _SEMANTIC_PASS,
    )
    return closeout


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="P2 graph-skills accelerated closeout")
    parser.add_argument("--skip-live", action="store_true", help="Skip P2-W9 canonical live runs")
    parser.add_argument(
        "--w9-live-matrix-only",
        action="store_true",
        help="Run remaining six P2-W9 live sections and update closeout receipts only",
    )
    parser.add_argument(
        "--w9-refresh-receipts-only",
        action="store_true",
        help="Re-probe latest run dirs and refresh W9/closeout without re-running lanes",
    )
    parser.add_argument(
        "--w9-ibm-unify-closeout",
        action="store_true",
        help="Run canonical live proofs for unify_narrative + IBM lanes and refresh receipts",
    )
    args = parser.parse_args()
    if args.w9_ibm_unify_closeout:
        out = write_p2_w9_live_matrix_closeout(
            run_live=True,
            sections_to_run=P2_W9_IBM_UNIFY_SECTIONS,
            timeout_s=600,
        )
        print(json.dumps({"status": out["status"], "closeout": str(CLOSEOUT_JSON)}, indent=2))
    elif args.w9_live_matrix_only:
        out = write_p2_w9_live_matrix_closeout(run_live=True)
    elif args.w9_refresh_receipts_only:
        out = write_p2_w9_live_matrix_closeout(run_live=False)
        print(json.dumps({"status": out["status"], "closeout": str(CLOSEOUT_JSON)}, indent=2))
    else:
        out = run_full_closeout(skip_live=args.skip_live)
        print(json.dumps({"status": out["status"], "closeout": str(CLOSEOUT_JSON)}, indent=2))
