"""Candidate Truth Firewall & compact verified fact packet for executive_summary_v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root as resolve_repository_root
from apps_rg.runtime.c0.c03_allowlist_coherence import (
    assert_pre_l2_allowlist_coherence, build_exec_summary_allowlist_receipt, filter_c03_evidence_to_allowed_pool,
)
from apps_rg.runtime.c0.section_proof_loader import apply_proof_pool_to_usage_ledger, load_section_proof_for_lane
from apps_rg.runtime.ingress.executive_summary_targeting_ingress import prepare_executive_summary_targeting_ingress
from apps_rg.runtime.runtime_proof_layout import prepare_runtime_proof_run_dir
from apps_rg.runtime.section_cli_defaults import coalesce_lane_provider_resolution_source
from apps_rg.runtime.sections.graph_evidence_contract import build_graph_evidence_runtime_payload
from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets

LANE_KEY = "executive_summary"
PROMPT_ID = "executive_summary.generate_scratch_v1"
TARGET_TITLE_DEFAULT = "SVP Engineering, Agentic AI Platforms"
TARGET_COMPANY_DEFAULT = "Enterprise Technology Organization"
JD_TEXT_DEFAULT = "enterprise AI platform leadership, agentic AI systems, runtime governance, LLMOps, retrieval"
BRIEFING_DEFAULT = "regulated enterprise environment, platform modernization, AI governance, scalable delivery"

_NUMERIC_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:%|(?:m|b|k|tb|ms|x)\b|\+))?", re.IGNORECASE)
_BLOCKED_SUPPORT = frozenset({"quarantined_unverified_synthetic", "approved_by_graph_presence", "blocked"})
_FORBIDDEN_SYNTHETIC_TOKENS = frozenset({"confluent", "kafka"})


def _find_apps_rg_checkout_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps_rg" / "resume" / "base").exists():
            return parent
    return Path.cwd()


APPS_RG_SRC_ROOT = _find_apps_rg_checkout_root()
REPO_ROOT = resolve_repository_root(Path(__file__))


@dataclass(frozen=True)
class VerifiedExecutiveSummaryContext:
    args: argparse.Namespace
    artifact_dir: Path
    runtime_payload: dict[str, Any]
    proof_pool_metadata: dict[str, Any]
    targeting_ingress: Any
    pool: Any
    base: dict[str, Any]
    base_path: Path
    base_hash: str
    front_spine: Any
    selected_fact_plan: dict[str, Any]
    allowed_fact_ids: set[str]
    allowed_fact_ids_ordered: list[str]
    compact_verified_facts: list[dict[str, Any]]
    verified_numbers: frozenset[str]
    verified_corpus_lower: str
    provider_resolution_source: str
    apply_proof_pool_to_usage_ledger: Any


def _load_metric_node_index() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in sorted((APPS_RG_SRC_ROOT / "apps_rg" / "fact_inventory").glob("*_role_episode_bundles.json")):
        nodes = json.loads(p.read_text(encoding="utf-8")).get("metric_outcome_nodes") or {}
        items = nodes.items() if isinstance(nodes, dict) else [(m.get("metric_outcome_id"), m) for m in nodes if isinstance(m, dict)]
        for mid, node in items:
            if mid and isinstance(node, dict):
                out[str(mid)] = node
    return out


def verify_and_compact_fact_slice(
    selected_fact_plan: dict[str, Any], allowed_fact_ids: set[str], base_resume: dict[str, Any]
) -> tuple[list[dict[str, Any]], frozenset[str], str]:
    """Enforce provenance + section_eligibility on allocated facts and extract verified allowlists."""
    metric_index = _load_metric_node_index()
    compact_rows: list[dict[str, Any]] = []
    corpus_parts: list[str] = [json.dumps(base_resume.get("facts") or {}, ensure_ascii=False)]
    for fact in [r for r in (selected_fact_plan.get("facts") or []) if isinstance(r, dict)]:
        fid = str(fact.get("fact_id") or fact.get("role_episode_bundle_id") or "").strip()
        if not fid:
            continue
        support = str(fact.get("support_level") or "").strip().lower()
        if support in _BLOCKED_SUPPORT:
            raise RuntimeError(f"Truth firewall blocked unverified bundle/fact in executive_summary: {fid} ({support})")
        verified_metrics: list[str] = []
        verified_metric_ids: list[str] = []
        for mid in [str(m).strip() for m in (fact.get("metric_outcome_ids") or fact.get("selected_metric_ids") or []) if str(m).strip()]:
            mnode = metric_index.get(mid)
            if mnode is not None:
                if mnode.get("approved") is not True or str(mnode.get("support_level") or "").strip().lower() in _BLOCKED_SUPPORT:
                    raise RuntimeError(f"Truth firewall blocked unapproved/quarantined metric in executive_summary: {mid}")
                melig = [str(s).strip() for s in (mnode.get("section_eligibility") or []) if str(s).strip()]
                if melig and LANE_KEY not in melig:
                    raise RuntimeError(f"Truth firewall blocked non-eligible metric in executive_summary: {mid} ({melig})")
                mtext = str(mnode.get("metric") or mnode.get("claim_text") or "").strip()
            else:
                mtext = mid
            if any(tok in mtext.lower() for tok in _FORBIDDEN_SYNTHETIC_TOKENS):
                raise RuntimeError(f"Truth firewall blocked synthetic vendor token in metric {mid}: {mtext}")
            if mtext:
                verified_metrics.append(mtext)
                if mid in allowed_fact_ids:
                    verified_metric_ids.append(mid)
        if not verified_metrics and fact.get("metric_raw"):
            mraw = str(fact.get("metric_raw") or "").strip()
            if mraw and not any(tok in mraw.lower() for tok in _FORBIDDEN_SYNTHETIC_TOKENS):
                verified_metrics.append(mraw)
        claim_text = str(fact.get("claim_text") or "").strip()
        employer = str(fact.get("employer") or fact.get("source_employment") or "").strip()
        cite_ids = [cid for cid in ([fid] + [m for m in verified_metric_ids if m != fid]) if cid in allowed_fact_ids] or [fid]
        compact_rows.append({"fact_id": fid, "citable_ids": cite_ids, "employer": employer, "claim": claim_text[:220], "verified_metrics": verified_metrics[:3]})
        corpus_parts.extend([employer, claim_text, *verified_metrics])
    corpus_lower = " \n ".join(corpus_parts).lower()
    nums: set[str] = set()
    for match in _NUMERIC_RE.findall(corpus_lower):
        cleaned = re.sub(r"\s+", "", match.strip().lower()).rstrip("+")
        if cleaned:
            nums.update({cleaned, cleaned.lstrip("$")})
    return compact_rows[:6], frozenset(nums), corpus_lower


def load_verified_executive_summary_context(
    args: argparse.Namespace, *, artifact_dir_override: Path | None = None
) -> VerifiedExecutiveSummaryContext:
    target_title = str(getattr(args, "target_title", None) or getattr(args, "target_role", None) or TARGET_TITLE_DEFAULT).strip() or TARGET_TITLE_DEFAULT
    target_company = str(getattr(args, "target_company", None) or TARGET_COMPANY_DEFAULT).strip() or TARGET_COMPANY_DEFAULT
    jd_raw = str(getattr(args, "jd_text", None) or getattr(args, "jd", None) or JD_TEXT_DEFAULT).strip() or JD_TEXT_DEFAULT
    targeting_ingress = prepare_executive_summary_targeting_ingress(
        jd_text=jd_raw, briefing_raw=str(getattr(args, "briefing", None) or ""),
        target_role=str(getattr(args, "target_role", "") or ""), target_title=target_title, repo_root=APPS_RG_SRC_ROOT,
    )
    if isinstance(targeting_ingress.briefing_selection_receipt, dict) and targeting_ingress.briefing_selection_receipt.get("fail_closed"):
        raise RuntimeError(str(targeting_ingress.briefing_selection_receipt.get("truncation_or_selection_reason") or "briefing_fail_closed"))
    pool, base, base_path, base_hash, front_spine = load_section_proof_for_lane(
        section_id=LANE_KEY, args=args, repo_root=APPS_RG_SRC_ROOT, collect_employment_bullets_fn=collect_employment_bullets,
        jd_text_override=targeting_ingress.jd_text, briefing_text_override=targeting_ingress.briefing_text_bounded,
    )
    selected_fact_plan, allowed_fact_ids, allowed_fact_ids_ordered = pool.selected_fact_plan, set(pool.allowed_fact_ids), list(pool.allowed_fact_ids_ordered)
    pp_meta = dict(pool.proof_pool_metadata or {})
    if isinstance(c03 := pp_meta.get("c03_graphrag_bound"), dict):
        track_exp = pp_meta.get("track_weighted_graph_expansion")
        c03_claimable, filter_receipt = filter_c03_evidence_to_allowed_pool(c03, allowed_fact_ids, track_expansion=track_exp if isinstance(track_exp, dict) else None)
        pp_meta["c03_graphrag_bound"] = c03_claimable
        pp_meta["exec_summary_allowlist_receipt"] = build_exec_summary_allowlist_receipt(
            allowed_fact_ids=allowed_fact_ids, allowlist_filter_receipt=filter_receipt,
            track_expansion=track_exp if isinstance(track_exp, dict) else None, proof_pool_digest=str(pool.proof_pool_digest or ""), jd_text=targeting_ingress.jd_text,
        )
        pp_meta["c03_filtered_out_fact_ids"] = list(filter_receipt.get("c03_filtered_out_fact_ids") or [])
        pp_meta["c03_context_fact_ids"] = list(filter_receipt.get("c03_context_fact_ids") or [])
        pp_meta["allowlist_mismatch"] = False
    compact_facts, verified_nums, verified_corpus = verify_and_compact_fact_slice(selected_fact_plan, allowed_fact_ids, base)
    provider_res_source = coalesce_lane_provider_resolution_source(explicit=getattr(args, "provider_resolution_source", None), resolved_provider=str(args.provider))
    runtime_payload = build_graph_evidence_runtime_payload(
        run_id_prefix="exec_summary", section_id=LANE_KEY, prompt_id=PROMPT_ID, repo_root=REPO_ROOT,
        base_json_path=base_path, base_hash=base_hash, selected_graph_evidence_plan=selected_fact_plan,
        allowed_graph_evidence_ids=allowed_fact_ids_ordered, target_title=target_title, target_company=target_company,
        jd_text=targeting_ingress.jd_text, briefing=targeting_ingress.briefing_text_bounded, writable_context_scope="executive_summary_only",
        extra_fields={"monolithic_prompt_invoked": False, "strategic_tailor_v1_invoked": False, "engine_version": "executive_summary_v2"},
    )
    runtime_payload.update({"targeting_ingress": targeting_ingress.to_dict(), "briefing_signal_packet": targeting_ingress.briefing_signal_packet, "proof_pool_metadata": pp_meta})
    if targeting_ingress.briefing_selection_receipt is not None:
        runtime_payload["briefing_selection"] = targeting_ingress.briefing_selection_receipt
    if pool.proof_source == "augmented_skills_graph":
        runtime_payload.update({"graph_only_claim_authority": True, "base_resume_claim_authority": False})
    if str(getattr(args, "provider", "") or "").strip().lower() == "mock":
        runtime_payload["product_visible"] = False
    if allowlist_err := assert_pre_l2_allowlist_coherence(allowed_fact_ids=allowed_fact_ids, c03_bound=pp_meta.get("c03_graphrag_bound"), track_expansion=None, runtime_payload=runtime_payload):
        raise RuntimeError(f"Allowlist coherence failed closed: {allowlist_err}")
    artifact_dir = Path(artifact_dir_override) if artifact_dir_override is not None else prepare_runtime_proof_run_dir(APPS_RG_SRC_ROOT, LANE_KEY, args.provider, runtime_payload["run_id"])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return VerifiedExecutiveSummaryContext(
        args=args, artifact_dir=artifact_dir, runtime_payload=runtime_payload, proof_pool_metadata=pp_meta,
        targeting_ingress=targeting_ingress, pool=pool, base=base, base_path=base_path, base_hash=base_hash,
        front_spine=front_spine, selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids,
        allowed_fact_ids_ordered=allowed_fact_ids_ordered, compact_verified_facts=compact_facts,
        verified_numbers=verified_nums, verified_corpus_lower=verified_corpus,
        provider_resolution_source=provider_res_source, apply_proof_pool_to_usage_ledger=apply_proof_pool_to_usage_ledger,
    )


def sha16(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()[:16]
