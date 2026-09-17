"""Context assembly, targeting, and proof loading helpers for executive summary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from .lane_constants import *

__all__ = ['_reconcile_final_plan_c03_allowlist', '_args_target_title', '_strip_targeting_cap_notice', '_args_jd_text', 'truncate_briefing_for_exec_summary_external_model', 'sha16', 'write_json', 'load_base_resume', 'extract_allowed_facts', 'build_selected_fact_plan', 'build_runtime_payload', '_finalize_executive_summary_l7_binding', '_first_sentence_from_prose', '_fact_body_for_mock_synthesis', '_proof_pool_mode_from_payload', 'build_mock_output', 'resolve_provider_model_name', 'write_x2_gate_outputs']

def _reconcile_final_plan_c03_allowlist(
    proof_pool_metadata: dict[str, Any],
    *,
    allowed_fact_ids: set[str],
    proof_pool_digest: str,
    jd_text: str,
) -> dict[str, Any]:
    """Reconcile the early graph-targeting view with the sealed final plan.

    C0 may inspect a wider, non-claimable graph neighborhood before the
    whole-resume allocator seals this section's finite fact set.  Once that
    allocation exists, the lane must carry forward only its claimable C0.3
    evidence while retaining the wider neighborhood exclusively as recorded
    targeting context.  The returned filter receipt is later checked by X2;
    it is not an allowlist expansion or a fallback.
    """

    c03 = proof_pool_metadata.get("c03_graphrag_bound")
    if not isinstance(c03, dict):
        return proof_pool_metadata

    from apps_rg.runtime.c0.c03_allowlist_coherence import (
        build_exec_summary_allowlist_receipt,
        filter_c03_evidence_to_allowed_pool,
    )

    track_expansion = proof_pool_metadata.get("track_weighted_graph_expansion")
    c03_claimable, filter_receipt = filter_c03_evidence_to_allowed_pool(
        c03,
        allowed_fact_ids,
        track_expansion=track_expansion if isinstance(track_expansion, dict) else None,
    )
    out = dict(proof_pool_metadata)
    out["c03_graphrag_bound"] = c03_claimable
    out["exec_summary_allowlist_receipt"] = build_exec_summary_allowlist_receipt(
        allowed_fact_ids=allowed_fact_ids,
        allowlist_filter_receipt=filter_receipt,
        track_expansion=track_expansion if isinstance(track_expansion, dict) else None,
        proof_pool_digest=proof_pool_digest,
        jd_text=jd_text,
    )
    out["c03_filtered_out_fact_ids"] = list(
        filter_receipt.get("c03_filtered_out_fact_ids") or []
    )
    out["c03_context_fact_ids"] = list(filter_receipt.get("c03_context_fact_ids") or [])
    out["c03_expansion_surplus_fact_ids"] = list(
        filter_receipt.get("c03_expansion_surplus_fact_ids") or []
    )
    out["allowlist_mismatch"] = False
    return out


def _args_target_title(args: argparse.Namespace) -> str:
    return (
        str(getattr(args, "target_title", None) or getattr(args, "target_role", None) or TARGET_TITLE_DEFAULT)
        .strip()
        or TARGET_TITLE_DEFAULT
    )


def _strip_targeting_cap_notice(text: str) -> str:
    """Remove the exec-only _CAP_NOTICE sentinel so cross-lane input digests compare the
    same canonical text (aggregation preflight x2_preflight_*_digest_coherence)."""
    from apps_rg.runtime.sections.executive_summary_targeting_cap import _CAP_NOTICE

    return str(text or "").replace(_CAP_NOTICE, "\n").replace(_CAP_NOTICE.strip(), "")


def _args_jd_text(args: argparse.Namespace) -> str:
    return (
        str(getattr(args, "jd_text", None) or getattr(args, "jd", None) or JD_TEXT_DEFAULT).strip()
        or JD_TEXT_DEFAULT
    )


def truncate_briefing_for_exec_summary_external_model(
    briefing: str,
    *,
    role_family_key: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Prepare briefing via ranked section selection (see executive_summary_briefing)."""
    from apps_rg.runtime.sections.executive_summary_briefing import (
        prepare_briefing_for_executive_summary,
    )

    selected, receipt = prepare_briefing_for_executive_summary(
        briefing,
        role_family_key=role_family_key,
    )
    if receipt.get("fail_closed"):
        return selected, receipt
    if receipt.get("briefing_excluded_chars", 0) == 0 and receipt.get("briefing_original_chars", 0) == len(
        str(briefing or "")
    ):
        return selected, None
    return selected, receipt


def sha16(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()[:16]


def write_json(path: Path, data: Any) -> None:
    _wg.ensure_dir(path.parent)
    _wg.write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_base_resume() -> tuple[dict[str, Any], Path, str]:
    if BASE_POINTER.exists():
        pointer = json.loads(BASE_POINTER.read_text(encoding="utf-8"))
        ref = pointer.get("active_resume_path") or pointer.get("base_resume_json_ref") or "apps_rg/resume/base/amit_ayer_base_resume_v1.json"
        path = REPO_ROOT / ref
    else:
        path = BASE_JSON_DEFAULT
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw), path, hashlib.sha256(raw.encode()).hexdigest()


def extract_allowed_facts(base_resume: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    """Collect bullets in résumé order; no hard-coded bullet IDs or employer filters."""
    facts_obj = base_resume.get("facts", base_resume)
    selected: list[dict[str, Any]] = []
    for emp in facts_obj.get("employment", []):
        employer = emp.get("employer", "")
        for bullet in emp.get("bullets", []):
            bid = bullet.get("bullet_id")
            if not bid:
                continue
            selected.append(
                {
                    "fact_id": bid,
                    "claim_text": bullet.get("text", ""),
                    "source_employment": employer,
                    "metric_raw": bullet.get("metric_raw", "") if bullet.get("has_metric") else "",
                    "domain": bullet.get("domain", ""),
                    "technologies": bullet.get("technologies", []),
                }
            )
    allowed = {row["fact_id"] for row in selected}
    for row in selected:
        if row.get("metric_raw"):
            allowed.add(f"{row['fact_id']}_metric_{sha16(row['metric_raw'])[:8]}")
    return selected, allowed


def build_selected_fact_plan(selected_facts: list[dict[str, Any]]) -> dict[str, Any]:
    top = selected_facts[:4]
    return build_selected_graph_evidence_plan(
        section_id="executive_summary",
        selection_method="resume_document_order_top_n",
        facts=top,
        required_fact_ids=[row["fact_id"] for row in top],
    )


def build_runtime_payload(
    *,
    base_json_path: Path,
    base_hash: str,
    selected_fact_plan: dict[str, Any],
    target_title: str,
    target_company: str,
    jd_text: str,
    briefing: str,
    allowed_fact_ids_ordered: list[str] | None = None,
) -> dict[str, Any]:
    ids = allowed_fact_ids_ordered if allowed_fact_ids_ordered is not None else list(selected_fact_plan.get("required_fact_ids") or [])
    return build_graph_evidence_runtime_payload(
        run_id_prefix="exec_summary",
        section_id="executive_summary",
        prompt_id=PROMPT_ID,
        repo_root=CHECKOUT_ROOT,
        base_json_path=base_json_path,
        base_hash=base_hash,
        selected_graph_evidence_plan=selected_fact_plan,
        allowed_graph_evidence_ids=ids,
        target_title=target_title,
        target_company=target_company,
        jd_text=jd_text,
        briefing=briefing,
        writable_context_scope="executive_summary_only",
        extra_fields={
            "monolithic_prompt_invoked": False,
            "strategic_tailor_v1_invoked": False,
        },
    )


def _finalize_executive_summary_l7_binding(
    artifact_dir: Path,
    runtime_payload: dict[str, Any],
) -> Path:
    """Package lane evidence relative to the standalone checkout root."""
    from apps_rg.runtime.section_l7_binding_lane_integration import finalize_section_l7_binding

    return finalize_section_l7_binding(
        artifact_dir,
        section_id="executive_summary",
        runtime_payload=runtime_payload,
        repo_root=CHECKOUT_ROOT,
        command_surface="python -m apps_rg --section executive_summary",
    )


def _first_sentence_from_prose(chunk: str, *, min_len: int = 40, max_len: int = 320) -> str:
    """One sentence for stub glue: split on first strong period after min_len, else hard-cap."""
    c = " ".join(str(chunk).split()).strip()
    if not c:
        return c
    for i, ch in enumerate(c):
        if ch == "." and i + 1 >= min_len:
            return c[: i + 1].strip()
    if len(c) <= max_len:
        return c if c.endswith((".", "!", "?")) else c + "."
    return c[:max_len].rstrip() + "..."


def _fact_body_for_mock_synthesis(claim_text: str) -> str:
    """Use résumé bullet body without leading ``Label:`` clause so stub prose avoids X2 colon-stitch failures."""
    t = str(claim_text).strip()
    if ": " in t and not t.lower().startswith("http"):
        return t.split(": ", 1)[1].strip()
    return t


def _proof_pool_mode_from_payload(runtime_payload: dict[str, Any]) -> str:
    from apps_rg.runtime.dispatch.input_authority_prompt_block import proof_pool_mode_from_metadata

    pp = runtime_payload.get("proof_pool_metadata") or {}
    return proof_pool_mode_from_metadata(pp if isinstance(pp, dict) else None)


def build_mock_output(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    """Offline-contract stub: five- or six-sentence executive paragraph (same product shape as live)."""
    facts = list(runtime_payload["selected_fact_plan"]["facts"])
    claims: list[dict[str, Any]] = []
    for f in facts:
        bid = str(f["fact_id"])
        ids: list[str] = [bid]
        if f.get("metric_raw"):
            ids.append(f"{bid}_metric_{sha16(str(f['metric_raw']))[:8]}")
        raw_ct = str(f.get("claim_text") or "").strip() or bid
        body = _fact_body_for_mock_synthesis(raw_ct) or raw_ct
        claims.append({"claim_text": body, "source_fact_ids": ids})

    if claims:
        s2 = _first_sentence_from_prose(claims[min(1, len(claims) - 1)]["claim_text"])
        s3 = _first_sentence_from_prose(claims[min(2, len(claims) - 1)]["claim_text"])
        s4 = _first_sentence_from_prose(claims[-1]["claim_text"])
        text = (
            "Engineering executive accountable for governed AI platform delivery, deterministic runtime controls, "
            "and production-grade reliability across enterprise programs. "
            f"{s2} "
            f"{s3} "
            f"{s4}"
        )
    else:
        text = (
            "Engineering executive focused on governed AI platforms and deterministic runtime controls for enterprise programs. "
            "The operating model binds architecture, delivery governance, and measurable platform outcomes for regulated enterprises. "
            "Traceability, policy gating, and repeatable execution remain the operational through-line across modernization programs. "
            "Commercial and technical leadership stay aligned as teams scale governed agentic capabilities into production."
        )

    return {
        "executive_strategy_thesis": (
            "Enterprise technology leader who operationalizes governed AI platforms and audit-ready "
            "delivery for regulated enterprise programs."
        ),
        "resume_display_text": text,
        "claim_ledger": claims,
        "jd_alignment": {
            "targeting_only": True,
            "jd_used_as_proof": False,
            "briefing_used_as_proof": False,
            "companion_context_used_as_proof": False,
        },
        "gap_notes": [],
        "change_log": [{"operation": "offline_contract_stub", "reason": "APPS_RG_PROVIDER_MODEL_OFFLINE_CONTRACT_STUB"}],
        "self_check": {"no_first_person": True, "no_inline_source_tags": True, "fit_to_evidence": True},
    }


def resolve_provider_model_name(
    provider_request_data: dict[str, Any] | None,
    provider_result_data: dict[str, Any] | None,
) -> str | None:
    if provider_result_data:
        model = provider_result_data.get("model")
        if model:
            return model
    if provider_request_data:
        model = provider_request_data.get("model")
        if model:
            return model
    return None


def write_x2_gate_outputs(
    path: Path,
    gates: list[dict[str, Any]],
    *,
    section_id: str | None = None,
) -> None:
    if section_id:
        from apps_rg.runtime.sections.section_x2_gate_outputs import (
            write_section_x2_gate_outputs,
        )

        write_section_x2_gate_outputs(path.parent, section_id, gates)
        return
    failed = [g["gate_id"] for g in gates if not g["pass"]]
    passed_count = sum(1 for g in gates if g["pass"])
    failed_count = len(failed)
    write_json(
        path,
        {
            "gates": gates,
            "failed_gates": failed,
            "x2_passed": passed_count,
            "x2_failed": failed_count,
            "total_x2_gates": len(gates),
        },
    )

