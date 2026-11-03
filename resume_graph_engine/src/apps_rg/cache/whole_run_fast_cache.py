"""Wave 5 pre-research whole-run fast cache materialization and R1A stamping helpers."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from apps_rg.cache.r1a_adapter import compute_r1a_key, stamp_r1a_cache

_PRESERVED_TARGET_NAMES = frozenset(
    {
        "validated_input_bundle.v1.json",
        "validated_inputs",
        "e2e_preflight_receipt.json",
        "e2e_preflight_product_entry_receipt.json",
        "e2e_preflight_continuation_receipt.json",
        "e2e_preflight_continuation_consumption_receipt.json",
        "e2e_preflight_non_product_compatibility_receipt.json",
        "apps_rg_runtime_boundary_receipt.json",
        "runtime_independence_receipt.json",
        "e2e_stage_ledger.json",
        "e2e_stage_ledger_preidentity_non_product.json",
        "e2e_stage_ledger_seal_receipt.json",
        "e2e_ledger_receipts",
        "candidate_evaluation_manifest.v2.json",
        "r1a_stamp.json",
        "r1a_key.txt",
    }
)

_MATERIALIZE_ITEMS = (
    "outputs",
    "apps_eval",
    "research",
    "FINAL_RESUME_OUTPUT.json",
    "FINAL_RESUME_OUTPUT.txt",
    "01_BCG_executive_output.md",
    "02_section_lane_summary_table.md",
    "FULL_RUN_SECTION_STATUS.md",
    "apps_rg_pipeline_completion_receipt.json",
    "apps_rg_post_x3_completion_receipt.json",
    "apps_rg_product_authorization_receipt.json",
    "x3_disposition_receipt.json",
    "apps_rg_whole_run_exit_review_packet.json",
    "runtime_identity_envelope.json",
    "l6_evaluation_audit.v2.json",
    "run_manifest.json",
    "apps_rg_output_manifest.json",
    "apps_rg_mandatory_output_commit_manifest.json",
    "APPS_RG_MANDATORY_RUN_OUTPUT.json",
    "generated_resume.json",
)


def is_no_cache_requested(environ: Any = None) -> bool:
    env = os.environ if environ is None else environ
    for key in ("APPS_RG_NO_CACHE", "APPS_RG_REQUIRE_FRESH_RUN"):
        if str(env.get(key) or "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


def _link_or_copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _link_or_copy_tree(src_dir: Path, dst_dir: Path) -> None:
    for item in src_dir.rglob("*"):
        rel = item.relative_to(src_dir)
        target = dst_dir / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _link_or_copy_file(item, target)


def _source_run_is_authorized(source_dir: Path, *, require_product_auth: bool) -> bool:
    if not source_dir.is_dir():
        return False
    has_resume = (source_dir / "outputs" / "generated_resume.json").is_file() or (
        source_dir / "generated_resume.json"
    ).is_file()
    if not has_resume:
        return False
    if not require_product_auth:
        return True
    from apps_rg.__main__ import _evaluate_product_run

    eval_report = _evaluate_product_run(source_dir)
    return str(eval_report.get("status") or "") == "PASS"


def stamp_authorized_whole_run_r1a(
    *,
    raw_request: dict[str, Any],
    artifact_dir: Path,
) -> bool:
    art = Path(artifact_dir)
    if not (
        (art / "outputs" / "generated_resume.json").is_file()
        or (art / "generated_resume.json").is_file()
    ):
        return False
    r_hash = str(raw_request.get("resume_hash") or "").strip()
    co = str(raw_request.get("target_company") or "").strip()
    ro = str(raw_request.get("target_role") or "").strip()
    if not (r_hash and co and ro):
        return False
    jd_hash = str(raw_request.get("jd_hash") or "").strip()
    caller_brief_hash = str(
        raw_request.get("caller_brief_hash") or raw_request.get("brief_hash") or ""
    ).strip()
    primary_key = compute_r1a_key(
        source_resume_hash=r_hash,
        target_company=co,
        target_role=ro,
        jd_hash=jd_hash,
        briefing_hash=caller_brief_hash,
    )
    legacy_key = compute_r1a_key(
        source_resume_hash=r_hash,
        target_company=co,
        target_role=ro,
    )
    extra = [legacy_key] if legacy_key != primary_key else []
    stamp_r1a_cache(
        primary_key,
        run_dir=art,
        policy_hash=str(raw_request.get("policy_hash") or os.environ.get("APPS_RG_POLICY_HASH") or "") or None,
        blueprint_hash=str(raw_request.get("blueprint_hash") or os.environ.get("APPS_RG_BLUEPRINT_HASH") or "") or None,
        jd_hash=jd_hash or None,
        briefing_hash=caller_brief_hash or None,
        extra_keys=extra,
    )
    return True


def _materialize_warm_whole_run_hit(
    *,
    source_dir: Path,
    art: Path,
    preflight: Any,
    evidence: dict[str, Any],
    stage_ledger: Any,
) -> dict[str, Any]:
    from apps_rg.cache.cache_preflight_evidence import write_cache_hit_receipt
    from apps_rg.cache.whole_run_entrypoint_preflight import build_cache_hit_dispatch_result

    write_cache_hit_receipt(art, preflight, evidence)
    for rel_name in _MATERIALIZE_ITEMS:
        if rel_name in _PRESERVED_TARGET_NAMES:
            continue
        src = source_dir / rel_name
        dst = art / rel_name
        if src.is_dir():
            _link_or_copy_tree(src, dst)
        elif src.is_file():
            _link_or_copy_file(src, dst)

    provenance = {
        "schema_version": "apps_rg.whole_run_cache_hit_provenance.v1",
        "cache_outcome": preflight.outcome,
        "source_run_dir": str(source_dir.resolve()),
        "target_run_dir": str(art.resolve()),
        "provider_call_count": 0,
        "materialized_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (art / "cache_hit_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if stage_ledger is not None:
        try:
            stage_ledger.record(
                stage_id="CLOSEOUT",
                status="PASS",
                reason_code="WHOLE_RUN_CACHE_HIT_SERVED",
                output_refs={"cache_hit_provenance": "cache_hit_provenance.json"},
            )
        except Exception:  # guardian: allow-silent-swallow -- ledger may already be sealed
            pass

    res = build_cache_hit_dispatch_result(preflight)
    res.update(
        {
            "artifact_dir": str(art),
            "source_cache_artifact_dir": str(source_dir.resolve()),
            "cache_hit": True,
            "product_authorized": True,
            "pipeline_complete": True,
            "completion_status": "PASS",
            "observability_repair_required": False,
            "provider_call_count": 0,
            "e2e_stage_ledger": str(stage_ledger.path) if stage_ledger is not None else "",
        }
    )
    return res


def compute_caller_brief_hash(manual_brief: str) -> str:
    from apps_rg.runtime.orchestration.canonical_dispatch import _read_optional_brief, _sha16
    import hashlib

    brief_text = _read_optional_brief(manual_brief)
    return hashlib.sha256(brief_text.encode("utf-8")).hexdigest() if brief_text else _sha16("no_brief")


def try_serve_pre_research_whole_run_cache_hit(
    *,
    art: Path,
    target_company: str,
    target_role: str,
    target_level: str,
    jd: str,
    job_description_ref: str,
    job_description_text: str,
    manual_brief: str,
    resume_path: str,
    source_resume_text: str,
    generation_mode: str,
    require_fresh_preflight: bool,
    stage_ledger: Any,
) -> dict[str, Any] | None:
    if is_no_cache_requested():
        return None
    from apps_rg.cache.cache_preflight_evidence import (
        build_cache_preflight_evidence,
        write_whole_run_cache_preflight_artifact,
    )
    from apps_rg.cache.whole_run_entrypoint_preflight import (
        ENTRYPOINT_CANONICAL_DISPATCH,
        run_whole_run_cache_preflight,
    )
    from apps_rg.runtime.orchestration.canonical_dispatch import build_raw_request_for_r4

    pre_req = build_raw_request_for_r4(
        target_company=target_company,
        target_role=target_role,
        target_level=target_level,
        jd=jd,
        job_description_ref=job_description_ref,
        job_description_text=job_description_text,
        manual_brief=manual_brief,
        resume_path=resume_path,
        source_resume_text=source_resume_text,
        generation_mode=generation_mode,
    )
    pre_req["caller_brief_hash"] = str(pre_req.get("brief_hash") or "")
    preflight = run_whole_run_cache_preflight(
        entrypoint=ENTRYPOINT_CANONICAL_DISPATCH,
        raw_request=pre_req,
        target_company=target_company,
        target_role=target_role,
        artifact_dir=art,
        runs_dir=art.parent,
        policy_hash=os.environ.get("APPS_RG_POLICY_HASH"),
        blueprint_hash=os.environ.get("APPS_RG_BLUEPRINT_HASH"),
        section="",
    )
    if preflight.generation_required:
        return None
    return serve_post_research_whole_run_cache_hit(
        art=art,
        preflight=preflight,
        evidence=build_cache_preflight_evidence(preflight, artifact_dir=art),
        require_fresh_preflight=require_fresh_preflight,
        stage_ledger=stage_ledger,
        write_preflight_artifact_fn=write_whole_run_cache_preflight_artifact,
    )


def serve_post_research_whole_run_cache_hit(
    *,
    art: Path,
    preflight: Any,
    evidence: dict[str, Any],
    require_fresh_preflight: bool,
    stage_ledger: Any,
    write_preflight_artifact_fn: Any = None,
) -> dict[str, Any] | None:
    if preflight.generation_required or is_no_cache_requested():
        return None
    cand = str(preflight.r1a_artifact_dir or "").strip()
    if not cand and preflight.r1b_result is not None:
        cand = str(
            getattr(preflight.r1b_result, "artifact_dir", "")
            or getattr(preflight.r1b_result, "run_dir", "")
            or ""
        ).strip()
    if not cand:
        return None
    source_dir = Path(cand)
    if source_dir.resolve() == art.resolve():
        return None
    if not _source_run_is_authorized(source_dir, require_product_auth=require_fresh_preflight):
        return None
    if write_preflight_artifact_fn is not None:
        write_preflight_artifact_fn(art, preflight, evidence)
    return _materialize_warm_whole_run_hit(
        source_dir=source_dir,
        art=art,
        preflight=preflight,
        evidence=evidence,
        stage_ledger=stage_ledger,
    )
