#!/usr/bin/env python3
"""Live Keyless Clean-Slate LLM-as-a-Judge v3 Engine & Grounded Drafter for Agents Graph Hygiene.

Architecture:
- Stage A: Fast deterministic 6-scanner hygiene audit (`tools/audit_graph_hygiene_and_consolidation.py`).
- Stage B Triage (`graph_hygiene:forensic_item_triage`): Single fast IDE Judge v3 (`gemini-4-argon-medium`
  with provider_profiles.yaml quota backups) with content-hash caching; automatically escalates borderline
  verdicts (`0.80 <= score <= 0.90`) to an orthogonal cross-family second judge (`gpt-oss-120b-medium`).
- Stage B Promotion Gate (`graph_hygiene:promotion_release_gate`): Mandatory orthogonal cross-family
  2-judge jury (`gemini-4-argon-high` [argon] + `gpt-oss-120b-medium` [openai], distinct from
  `author_model_family="anthropic"`) sealing a hash-bound receipt at
  `artifacts/eval_harness/judge_receipts/agents_graph_hygiene_receipt.json`.
- Grounded Clone Drafting (`draft_grounded_skill_descriptions`): Evidence-grounded keyless IDE LLM
  rewriting (`claude-sonnet-5-5-medium` / `gemini-4-neon-medium`) strictly bound to verified linked facts,
  locked bullets, and allowed phrases, immediately verified fail-closed by Judge v3.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RGE_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for _p in (str(REPO_ROOT), str(RGE_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps_eval.graders.judge._core_governance_bridge import get_judge_ide_router_v3  # noqa: E402
from apps_eval.graders.judge.blind_protocol import (  # noqa: E402
    infer_provider_family,
    is_borderline_judge_result,
    validate_blind_judge_verdict_provenance,
)
from apps_eval.graders.judge.v3_evaluator import (  # noqa: E402
    JudgeV3ProvenanceError,
    JudgeV3SchemaError,
    JudgeV3Scorecard,
    build_skipped_v3_scorecard,
    build_v3_evaluation_bundle,
    build_v3_response_schema,
    parse_and_seal_v3_verdict,
)
from apps_eval.graders.judge.v3_registry import JudgeRubricRegistryV3  # noqa: E402
from infrastructure.sdks_mcps.agy_cli_transport import (  # noqa: E402
    AgyQuotaExhaustedError,
    AgyResult,
    AgyTransportError,
    discover_agy_bin,
    ide_cli_ready,
    is_agy_model_quota_cooled_down,
    is_agy_quota_error,
    mark_agy_model_quota_exhausted,
    run_agy,
)

TRIAGE_PROFILE_ID = "graph_hygiene:forensic_item_triage"
PROMOTION_PROFILE_ID = "graph_hygiene:promotion_release_gate"
DEFAULT_AUTHOR_FAMILY = "anthropic"
DEFAULT_CACHE_REL = Path("artifacts/governance/graph_hygiene_judge_cache.json")
DEFAULT_RECEIPT_REL = Path("artifacts/eval_harness/judge_receipts/agents_graph_hygiene_receipt.json")
DEFAULT_ARTIFACT_REL = Path("artifacts/eval_harness/judge_receipts/agents_graph_hygiene_artifact.json")
HIGH_RISK_CLUSTERS = frozenset(
    {
        "CLUSTER-01-QUARANTINE-SEARCH-LEAKS",
        "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
        "CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
        "CLUSTER-02C-CAPABILITY-DOMAIN-CONSOLIDATION",
        "CLUSTER-03-STRANDED-VERIFIED-METRICS",
        "CLUSTER-06-INTERNAL-SKILL-PROMOTION-TRIAGE",
    }
)
_TEMPLATE_BOILERPLATE_PREFIXES = (
    "applies ",
    "delivers ",
    "capability domain:",
    "career epoch:",
    "career track ",
    "c0.3 graph-skill granularity node for ",
    "skill:",
    "node:",
)

JudgeCallFn = Callable[[str, str, dict[str, Any], str], AgyResult]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_sha256(obj: Any) -> str:
    encoded = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ghj_", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_graph_hygiene_model_pins(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Resolve approved IDE judge and drafter pins dynamically from config/provider_profiles.yaml."""
    cfg_path = Path(repo_root).resolve() / "config" / "provider_profiles.yaml"
    doc: dict[str, Any] = {}
    if cfg_path.is_file():
        doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    judge_models = doc.get("judge_models") or {}
    ide_judging = doc.get("ide_cli_judging") or {}
    ide_gen = doc.get("ide_cli_generation") or {}
    claude_prof = ((doc.get("profiles") or {}).get("external_claude_generator") or {})

    triage_primary = str((judge_models.get("standard") or {}).get("gemini_pro") or "gemini-4-argon-medium").strip()
    triage_backups = [
        str(m).strip()
        for m in ((ide_judging.get("quota_backup_first_judge_by_tier") or {}).get("standard") or [])
        if str(m).strip()
    ] or ["gemini-4-neon-medium", "gemini-3.8-flash-high"]

    promo_primary = str((judge_models.get("enhanced") or {}).get("gemini_pro") or "gemini-4-argon-high").strip()
    promo_primary_backups = [
        str(m).strip()
        for m in ((ide_judging.get("quota_backup_first_judge_by_tier") or {}).get("enhanced") or [])
        if str(m).strip()
    ] or ["gemini-4-argon-medium", "gemini-4-neon-high"]

    second_primary = str(
        (ide_judging.get("second_judge_by_writer_maker") or {}).get(DEFAULT_AUTHOR_FAMILY)
        or "gpt-oss-120b-medium"
    ).strip()
    second_backups = [
        str(m).strip()
        for m in ((ide_judging.get("quota_backup_second_judge_by_writer_maker") or {}).get(DEFAULT_AUTHOR_FAMILY) or [])
        if str(m).strip()
    ] or ["gemini-4-neon-medium", "gemini-3.8-flash-high"]

    drafter_primary = str(
        (claude_prof.get("model_by_section") or {}).get("competencies") or "claude-sonnet-5-5-medium"
    ).strip()
    drafter_backups = [
        str(m).strip()
        for m in (ide_gen.get("quota_backup_models") or [])
        if str(m).strip()
    ] or ["gemini-4-neon-medium", "gemini-3.8-flash-medium"]

    return {
        "triage_primary": triage_primary,
        "triage_backups": triage_backups,
        "promotion_primary": promo_primary,
        "promotion_primary_backups": promo_primary_backups,
        "second_primary": second_primary,
        "second_backups": second_backups,
        "drafter_primary": drafter_primary,
        "drafter_backups": drafter_backups,
    }


def _default_judge_call(prompt: str, model: str, json_schema: dict[str, Any], effort: str) -> AgyResult:
    agy_bin = discover_agy_bin(allow_default_app_bundle=True)
    return run_agy(
        prompt,
        model=model,
        json_schema=json_schema,
        effort=effort,
        timeout_s=240,
        agy_bin=agy_bin,
    )


def _is_retryable_capacity_or_quota_error(exc: BaseException | str) -> bool:
    """Return True on 429 quota exhaustion OR 503 transient server capacity errors."""
    if is_agy_quota_error(exc):
        return True
    low = str(exc or "").lower()
    return any(
        tok in low
        for tok in (
            "unavailable",
            "code 503",
            " 503",
            "no capacity available",
            "high traffic",
            "overloaded",
            "timed out",
        )
    )


def _is_retryable_model_quirk(exc: BaseException | str) -> bool:
    """Return True when a candidate model attempts a denied tool call or emits unparseable output."""
    low = str(exc or "").lower()
    return any(
        tok in low
        for tok in (
            "tool calls attempted despite deny-all settings",
            "empty response",
            "did not return valid json",
        )
    )


def _call_with_quota_failover(
    *,
    prompt: str,
    candidate_models: Sequence[str],
    json_schema: dict[str, Any],
    effort: str,
    exclude_families: Sequence[str] = (),
    call_fn: JudgeCallFn | None = None,
) -> tuple[str, AgyResult]:
    runner = call_fn or _default_judge_call
    excluded = {infer_provider_family(f) for f in exclude_families if str(f).strip()}
    last_err: Exception | None = None
    tried: list[str] = []

    for slug in candidate_models:
        model = str(slug or "").strip()
        if not model or model in tried:
            continue
        if excluded and infer_provider_family(model) in excluded:
            continue
        if call_fn is None and is_agy_model_quota_cooled_down(model):
            continue
        tried.append(model)
        try:
            res = runner(prompt, model, json_schema, effort)
            return model, res
        except (AgyQuotaExhaustedError, AgyTransportError) as exc:
            last_err = exc
            if _is_retryable_capacity_or_quota_error(exc):
                mark_agy_model_quota_exhausted(model, str(exc))
                continue
            if _is_retryable_model_quirk(exc):
                continue
            raise
    if last_err is not None:
        raise last_err
    raise AgyTransportError(
        f"No eligible IDE model available from {list(candidate_models)} (excluded_families={sorted(excluded)})"
    )


def _load_cache(cache_path: Path) -> dict[str, Any]:
    if cache_path.is_file():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema_version": "agents.graph_hygiene_judge_cache.v1", "entries": {}}


def _save_cache_entry(cache_path: Path, cache_key: str, entry: Mapping[str, Any]) -> None:
    doc = _load_cache(cache_path)
    doc["entries"][cache_key] = dict(entry)
    doc["updated_at_utc"] = _utc_now_iso()
    _atomic_write_json(cache_path, doc)


def _sanitize_item_for_blind_triage(cluster_id: str, item: Mapping[str, Any]) -> dict[str, Any]:
    """Build cold-reader item packet stripped of rule-based recommended/confidence priming."""
    clean_options: list[dict[str, Any]] = []
    for opt in item.get("options") or []:
        if not isinstance(opt, Mapping):
            continue
        clean_options.append(
            {
                "option_id": str(opt.get("option_id") or ""),
                "label": str(opt.get("label") or ""),
                "action_kind": str(opt.get("action_kind") or ""),
                "impact": str(opt.get("impact") or ""),
            }
        )

    evidence: dict[str, Any] = {}
    for k in (
        "item_key",
        "reason",
        "shared_label",
        "survivor_node_id",
        "survivor_label",
        "retired_node_id",
        "retired_label",
        "shared_description_prefix",
        "member_ids",
        "member_labels",
        "metric_id",
        "label",
        "employer",
        "candidate_skill_ids",
        "node_id",
        "node_type",
        "activation_status",
        "support_level",
        "fact_edges",
        "bullet_edges",
        "metric_edges",
        "edge_count",
        "target_relpath",
        "suggested_label",
        "path_exists",
        "sibling_links_count",
        "sibling_links_per_node",
        "kind",
        "disposition",
    ):
        if k in item and item[k] is not None:
            evidence[k] = item[k]

    for prof_key in ("survivor_profile", "retired_profile", "node_profile", "metric_profile"):
        prof = item.get(prof_key)
        if isinstance(prof, Mapping):
            evidence[prof_key] = {
                pk: prof.get(pk)
                for pk in (
                    "node_id",
                    "node_type",
                    "label",
                    "description",
                    "activation_status",
                    "support_level",
                    "external_eligible",
                    "employer",
                    "pillar",
                    "subpillar",
                    "domain_id",
                    "visibility_rule",
                    "external_claim_policy",
                    "allowed_phrases",
                    "linked_fact_details",
                    "linked_metric_details",
                )
                if prof.get(pk) not in (None, "", [])
            }

    for list_prof_key in ("member_profiles", "candidate_skill_profiles"):
        profs = item.get(list_prof_key)
        if isinstance(profs, list) and profs:
            evidence[list_prof_key] = [
                {
                    pk: p.get(pk)
                    for pk in (
                        "node_id",
                        "label",
                        "description",
                        "support_level",
                        "pillar",
                        "subpillar",
                        "domain_id",
                        "allowed_phrases",
                        "linked_fact_details",
                    )
                    if p.get(pk) not in (None, "", [])
                }
                for p in profs
                if isinstance(p, Mapping)
            ]

    return {
        "cluster_id": str(cluster_id),
        "item_key": str(item.get("item_key") or item.get("node_id") or item.get("metric_id") or "item"),
        "evidence": evidence,
        "available_options": clean_options,
    }


def _triage_response_schema(profile: Any) -> dict[str, Any]:
    schema = build_v3_response_schema(profile)
    props = dict(schema.get("properties") or {})
    props["recommended_option_id"] = {
        "type": "string",
        "description": "Option ID from available_options best supported by the observed evidence, or empty string if none apply.",
    }
    props["forensic_rationale"] = {
        "type": "string",
        "description": "Concise 1-to-2 sentence evidence-backed explanation for the operator.",
    }
    schema["properties"] = props
    req = list(schema.get("required") or [])
    for k in ("recommended_option_id", "forensic_rationale"):
        if k not in req:
            req.append(k)
    schema["required"] = req
    return schema


def compute_item_cache_key(
    *,
    cluster_id: str,
    item: Mapping[str, Any],
    rubric_sha256: str,
    profile_id: str = TRIAGE_PROFILE_ID,
) -> str:
    packet = _sanitize_item_for_blind_triage(cluster_id, item)
    return _canonical_sha256(
        {
            "profile_id": profile_id,
            "rubric_sha256": rubric_sha256,
            "packet": packet,
        }
    )


def hydrate_audit_report_with_cached_judges(
    report: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    """Attach cached live Judge v3 verdicts onto matching audit items without making network/CLI calls."""
    resolved_root = Path(repo_root).resolve()
    cpath = Path(cache_path).resolve() if cache_path is not None else (resolved_root / DEFAULT_CACHE_REL)
    cache_doc = _load_cache(cpath)
    entries = cache_doc.get("entries") or {}
    if not entries:
        return report

    try:
        reg = JudgeRubricRegistryV3.load(resolved_root / "config/governance/judge_rubrics_v3.json")
        rsha = reg.rubric_sha256
    except (OSError, ValueError):
        return report

    by_item_key: dict[str, dict[str, Any]] = {}
    for entry in entries.values():
        if isinstance(entry, dict) and entry.get("item_key") and entry.get("rubric_sha256") == rsha:
            by_item_key[str(entry["item_key"])] = entry

    for cluster in report.get("hitl_clusters") or []:
        cid = str(cluster.get("cluster_id") or "")
        judged_count = 0
        for item in cluster.get("items") or []:
            ck = compute_item_cache_key(cluster_id=cid, item=item, rubric_sha256=rsha)
            hit = entries.get(ck) or by_item_key.get(str(item.get("item_key") or ""))
            if isinstance(hit, dict) and hit.get("llm_judge_executed"):
                item["judge_verdict"] = {**hit, "cache_hit": True}
                judged_count += 1
        meta = cluster.setdefault("judge_metadata", {})
        if isinstance(meta, dict):
            meta["judged_item_count"] = judged_count
    return report


def evaluate_hygiene_item_v3(
    *,
    cluster_id: str,
    item: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    escalate_borderline: bool = True,
    call_fn: JudgeCallFn | None = None,
) -> dict[str, Any]:
    """Run Stage B live keyless IDE Judge v3 forensic evaluation on one graph hygiene item (with cache)."""
    resolved_root = Path(repo_root).resolve()
    reg = JudgeRubricRegistryV3.load(resolved_root / "config/governance/judge_rubrics_v3.json")
    packet = _sanitize_item_for_blind_triage(cluster_id, item)
    item_key = packet["item_key"]
    cpath = Path(cache_path).resolve() if cache_path is not None else (resolved_root / DEFAULT_CACHE_REL)
    cache_key = compute_item_cache_key(cluster_id=cluster_id, item=item, rubric_sha256=reg.rubric_sha256)

    if not force_refresh:
        cached = (_load_cache(cpath).get("entries") or {}).get(cache_key)
        if isinstance(cached, dict) and cached.get("llm_judge_executed") is True:
            return {**cached, "cache_hit": True}

    bundle, profile, base_prompt = build_v3_evaluation_bundle(
        profile_token=TRIAGE_PROFILE_ID,
        artifact_id=item_key,
        raw_input=packet,
        author_model_family=DEFAULT_AUTHOR_FAMILY,
        registry=reg,
        repo_root=resolved_root,
    )
    triage_instruction = (
        "\nTASK: Evaluate this evidence-graph hygiene item strictly from the facts, locked bullets, "
        "descriptions, and edges inside BLIND_EVALUATION_PACKET. Do NOT call any tools or write files; "
        "return ONLY strict JSON matching the schema, selecting the single cleanest option_id from "
        "available_options (if provided) in `recommended_option_id` and a concise 1-to-2 sentence "
        "`forensic_rationale`. Every NO check MUST include a verbatim substring copied directly from "
        "BLIND_EVALUATION_PACKET in `evidence_span`.\n"
    )
    prompt = base_prompt + triage_instruction
    schema = _triage_response_schema(profile)
    corpus = json.dumps(bundle.payload, ensure_ascii=False, sort_keys=True)

    if call_fn is None:
        ok, reason = ide_cli_ready(allow_default_app_bundle=True)
        if not ok:
            skipped = build_skipped_v3_scorecard(
                bundle=bundle,
                profile=profile,
                rubric_sha256=reg.rubric_sha256,
                reason=f"BLOCKED_IDE_CLI_UNAVAILABLE:{reason}",
            )
            return {
                **skipped.to_dict(),
                "item_key": item_key,
                "cluster_id": cluster_id,
                "cache_hit": False,
                "escalated_to_jury": False,
                "recommended_option_id": "",
                "forensic_rationale": reason,
            }

    pins = load_graph_hygiene_model_pins(resolved_root)
    effort = str(
        get_judge_ide_router_v3().select_ide_reasoning_effort(
            profile.archetype,
            assurance_tier=profile.assurance_tier,
            profile_reasoning=profile.reasoning_effort,
        )
    )

    def _run_one(models: Sequence[str], *, exclude_fams: Sequence[str] = ()) -> tuple[JudgeV3Scorecard, dict[str, Any]]:
        used_slug, res = _call_with_quota_failover(
            prompt=prompt,
            candidate_models=models,
            json_schema=schema,
            effort=effort,
            exclude_families=exclude_fams,
            call_fn=call_fn,
        )
        raw_obj = res.structured_output if isinstance(res.structured_output, dict) else res.response
        parsed_raw = raw_obj if isinstance(raw_obj, dict) else json.loads(str(raw_obj))
        card = parse_and_seal_v3_verdict(
            parsed_raw,
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            judge_model_id=res.model_reported or used_slug,
            verify_verbatim_in=corpus,
            conversation_id=res.conversation_id,
            usage=res.usage,
        )
        return card, parsed_raw

    primary_card, primary_raw = _run_one(
        [pins["triage_primary"], *pins["triage_backups"]],
        exclude_fams=[DEFAULT_AUTHOR_FAMILY],
    )
    cards = [primary_card]
    escalated = False

    if (
        escalate_borderline
        and primary_card.normalized_unit_score is not None
        and is_borderline_judge_result(primary_card.normalized_unit_score, profile=profile)
    ):
        try:
            second_card, _ = _run_one(
                [pins["second_primary"], *pins["second_backups"]],
                exclude_fams=[DEFAULT_AUTHOR_FAMILY, primary_card.judge_model_family],
            )
            cards.append(second_card)
            escalated = True
        except (AgyTransportError, JudgeV3SchemaError, JudgeV3ProvenanceError, ValueError):
            escalated = False

    distinct_fams = sorted({c.judge_model_family for c in cards if c.judge_model_family})
    scores = [float(c.normalized_unit_score) for c in cards if c.normalized_unit_score is not None]
    agg_score = round(min(scores), 4) if scores else None
    agg_passed = all(c.passed for c in cards)
    agg_veto = any(c.critical_veto_triggered for c in cards)

    out: dict[str, Any] = {
        **primary_card.to_dict(),
        "item_key": item_key,
        "cluster_id": cluster_id,
        "rubric_sha256": reg.rubric_sha256,
        "passed": agg_passed,
        "verdict": "PASS" if agg_passed else "FAIL",
        "status": "PASSED" if agg_passed else "FAILED",
        "normalized_unit_score": agg_score,
        "overall_score": agg_score,
        "critical_veto_triggered": agg_veto,
        "judge_model_families": distinct_fams,
        "distinct_families": len(distinct_fams),
        "escalated_to_jury": escalated,
        "jury_scorecards": [c.to_dict() for c in cards],
        "recommended_option_id": str(primary_raw.get("recommended_option_id") or "").strip(),
        "forensic_rationale": str(primary_raw.get("forensic_rationale") or primary_card.cold_read_takeaway).strip(),
        "evaluated_at_utc": _utc_now_iso(),
        "cache_key": cache_key,
        "cache_hit": False,
    }
    _save_cache_entry(cpath, cache_key, out)
    return out


def evaluate_hygiene_cluster_v3(
    *,
    cluster: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    max_items: int | None = None,
    max_workers: int = 4,
    call_fn: JudgeCallFn | None = None,
) -> list[dict[str, Any]]:
    """Evaluate items in one graph hygiene cluster via live cached Judge v3 with bounded concurrency."""
    cid = str(cluster.get("cluster_id") or "")
    items = list(cluster.get("items") or [])
    if max_items is not None and max_items > 0:
        items = items[:max_items]
    if not items:
        return []

    results_by_idx: dict[int, dict[str, Any]] = {}
    worker_count = max(1, min(int(max_workers), len(items)))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_map = {
            pool.submit(
                evaluate_hygiene_item_v3,
                cluster_id=cid,
                item=it,
                repo_root=repo_root,
                cache_path=cache_path,
                force_refresh=force_refresh,
                call_fn=call_fn,
            ): idx
            for idx, it in enumerate(items)
        }
        for fut in as_completed(future_map):
            idx = future_map[fut]
            results_by_idx[idx] = fut.result()
    return [results_by_idx[i] for i in range(len(items))]


def evaluate_hygiene_promotion_jury_v3(
    *,
    diff_packet: Mapping[str, Any],
    repo_root: Path = REPO_ROOT,
    receipt_path: Path | None = None,
    artifact_path: Path | None = None,
    call_fn: JudgeCallFn | None = None,
) -> dict[str, Any]:
    """Mandatory orthogonal cross-family 2-judge promotion gate sealing a hash-bound PR receipt."""
    resolved_root = Path(repo_root).resolve()
    target_receipt = Path(receipt_path).resolve() if receipt_path is not None else (resolved_root / DEFAULT_RECEIPT_REL)
    target_artifact = Path(artifact_path).resolve() if artifact_path is not None else (resolved_root / DEFAULT_ARTIFACT_REL)

    artifact_payload = {
        "schema_version": "agents.graph_hygiene_promotion_artifact.v1",
        "generated_at_utc": _utc_now_iso(),
        "diff_packet": dict(diff_packet),
    }
    _atomic_write_json(target_artifact, artifact_payload)

    reg = JudgeRubricRegistryV3.load(resolved_root / "config/governance/judge_rubrics_v3.json")
    bundle, profile, base_prompt = build_v3_evaluation_bundle(
        profile_token=PROMOTION_PROFILE_ID,
        artifact_id="agents_graph_hygiene_promotion",
        raw_input=artifact_payload,
        author_model_family=DEFAULT_AUTHOR_FAMILY,
        registry=reg,
        artifact_path=target_artifact,
        repo_root=resolved_root,
    )
    promo_instruction = (
        "\nTASK: Perform an independent release-critical forensic audit of the applied evidence-graph hygiene "
        "mutations in BLIND_EVALUATION_PACKET. Check strictly for fabricated provenance anchors, ungrounded "
        "skill descriptions, unintended node loss, and quarantine leaks. Do NOT invoke any tools or write "
        "files; output ONLY the JSON object matching the schema. Every NO verdict MUST include a verbatim "
        "substring copied directly from BLIND_EVALUATION_PACKET in `evidence_span`.\n"
    )
    prompt = base_prompt + promo_instruction
    schema = build_v3_response_schema(profile)
    corpus = json.dumps(bundle.payload, ensure_ascii=False, sort_keys=True)

    if call_fn is None:
        ok, reason = ide_cli_ready(allow_default_app_bundle=True)
        if not ok:
            failed = build_skipped_v3_scorecard(
                bundle=bundle,
                profile=profile,
                rubric_sha256=reg.rubric_sha256,
                reason=f"BLOCKED_IDE_CLI_UNAVAILABLE:{reason}",
            )
            fail_receipt = {
                **failed.to_dict(),
                "status": "FAIL",
                "verdict": "FAIL",
                "passed": False,
                "judge_model_families": [],
                "distinct_families": 0,
                "artifact_path": str(target_artifact),
                "receipt_path": str(target_receipt),
                "evaluated_at_utc": _utc_now_iso(),
            }
            _atomic_write_json(target_receipt, fail_receipt)
            return fail_receipt

    pins = load_graph_hygiene_model_pins(resolved_root)
    effort = str(
        get_judge_ide_router_v3().select_ide_reasoning_effort(
            profile.archetype,
            assurance_tier=profile.assurance_tier,
            profile_reasoning=profile.reasoning_effort,
        )
    )

    def _run_jury_member(models: Sequence[str], *, exclude_fams: Sequence[str]) -> JudgeV3Scorecard:
        used_slug, res = _call_with_quota_failover(
            prompt=prompt,
            candidate_models=models,
            json_schema=schema,
            effort=effort,
            exclude_families=exclude_fams,
            call_fn=call_fn,
        )
        raw_obj = res.structured_output if isinstance(res.structured_output, dict) else res.response
        return parse_and_seal_v3_verdict(
            raw_obj,
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            judge_model_id=res.model_reported or used_slug,
            artifact_disk_path=target_artifact,
            verify_verbatim_in=corpus,
            conversation_id=res.conversation_id,
            usage=res.usage,
        )

    primary_fam_expected = infer_provider_family(pins["promotion_primary"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(
            _run_jury_member,
            [pins["promotion_primary"], *pins["promotion_primary_backups"]],
            exclude_fams=[DEFAULT_AUTHOR_FAMILY],
        )
        f2 = pool.submit(
            _run_jury_member,
            [pins["second_primary"], *pins["second_backups"]],
            exclude_fams=[DEFAULT_AUTHOR_FAMILY, primary_fam_expected],
        )
        card_1 = f1.result()
        card_2 = f2.result()

    if card_2.judge_model_family == card_1.judge_model_family:
        card_2 = _run_jury_member(
            [pins["second_primary"], *pins["second_backups"]],
            exclude_fams=[DEFAULT_AUTHOR_FAMILY, card_1.judge_model_family],
        )

    cards = [card_1, card_2]
    distinct_fams = sorted({c.judge_model_family for c in cards if c.judge_model_family})
    scores = [float(c.normalized_unit_score) for c in cards if c.normalized_unit_score is not None]
    min_score = round(min(scores), 4) if scores else 0.0
    all_passed = all(c.passed for c in cards) and len(distinct_fams) >= 2
    any_veto = any(c.critical_veto_triggered for c in cards)

    receipt: dict[str, Any] = {
        "schema_version": "agents.graph_hygiene_promotion_judge_receipt.v1",
        "surface_id": "agents_graph_hygiene",
        "profile_id": PROMOTION_PROFILE_ID,
        "rubric_sha256": reg.rubric_sha256,
        "artifact_id": bundle.artifact_id,
        "artifact_sha256": bundle.artifact_sha256,
        "artifact_path": str(target_artifact),
        "receipt_path": str(target_receipt),
        "bundle_digest": bundle.bundle_digest,
        "author_model_family": bundle.author_model_family,
        "judge_model_id": card_1.judge_model_id,
        "judge_model_family": card_1.judge_model_family,
        "judge_model_families": distinct_fams,
        "distinct_families": len(distinct_fams),
        "evaluator_kind": "llm_judge",
        "llm_judge_executed": True,
        "deterministic_priming_stripped": bundle.deterministic_priming_stripped,
        "judge_input_keys": list(bundle.judge_input_keys),
        "external_http_call_count": 0,
        "normalized_unit_score": min_score,
        "overall_score": min_score,
        "pass_threshold": profile.pass_threshold,
        "critical_veto_triggered": any_veto,
        "passed": all_passed,
        "verdict": "PASS" if all_passed else "FAIL",
        "status": "PASS" if all_passed else "FAIL",
        "cold_read_takeaway": card_1.cold_read_takeaway,
        "failed_check_ids": sorted({cid for c in cards for cid in c.failed_check_ids}),
        "failure_tags": sorted({tag for c in cards for tag in c.failure_tags}),
        "jury_scorecards": [c.to_dict() for c in cards],
        "evaluated_at_utc": _utc_now_iso(),
    }

    prov_ok, prov_reasons = validate_blind_judge_verdict_provenance(
        receipt,
        expected_bundle_digest=bundle.bundle_digest,
        expected_artifact_sha256=bundle.artifact_sha256,
        artifact_disk_path=target_artifact,
        require_no_deterministic_priming=True,
        allow_external_http=False,
        min_distinct_families=2,
    )
    receipt["provenance_verified"] = prov_ok
    receipt["provenance_reasons"] = prov_reasons
    if not prov_ok:
        receipt["passed"] = False
        receipt["verdict"] = "FAIL"
        receipt["status"] = "FAIL"

    _atomic_write_json(target_receipt, receipt)
    return receipt


_INTERNAL_ID_RE = re.compile(r"\b(?:fact|bul|skill|domain|metric|repo|section)_[a-z0-9_]+\b", re.IGNORECASE)
_META_EVIDENCE_PHRASES = (
    "archive-verified",
    "backed by evidence",
    "supported by evidence",
    "tied to archive",
    "grounded in fact_",
)


def _load_candidate_fact_claims() -> dict[str, str]:
    try:
        from apps_rg.fact_inventory.candidate_fact_ledger import load_master_candidate_fact_ledger  # noqa: E402

        raw = load_master_candidate_fact_ledger()
        out: dict[str, str] = {}
        for f in (raw.get("candidate_facts") or []) if isinstance(raw, Mapping) else []:
            if not isinstance(f, Mapping):
                continue
            fid = str(f.get("candidate_fact_id") or f.get("fact_id") or "").strip()
            claim = str(f.get("claim_text") or f.get("summary") or "").strip()
            if fid and claim:
                out[fid] = claim
        return out
    except (ImportError, OSError, ValueError):
        return {}


def _collect_skill_evidence_packet(
    ledger: Mapping[str, Any],
    skill_ids: Sequence[str],
) -> list[dict[str, Any]]:
    row_by_id = {
        str(r.get("skill_id") or ""): r
        for r in (ledger.get("skill_rows") or [])
        if isinstance(r, dict) and r.get("skill_id")
    }
    node_by_id = {
        str(n.get("node_id") or ""): n
        for n in (ledger.get("graph_nodes") or [])
        if isinstance(n, dict) and n.get("node_id")
    }
    edges = [e for e in (ledger.get("graph_edges") or []) if isinstance(e, dict)]
    candidate_fact_claims = _load_candidate_fact_claims()

    packets: list[dict[str, Any]] = []
    for sid in skill_ids:
        row = row_by_id.get(sid) or {}
        node = node_by_id.get(sid) or {}
        fact_ids = list(dict.fromkeys([str(x).strip() for x in (row.get("fact_id_links") or []) if str(x).strip()]))
        bullet_ids: list[str] = []
        for e in edges:
            if str(e.get("source_node_id") or "") != sid:
                continue
            et = str(e.get("edge_type") or "")
            tgt = str(e.get("target_node_id") or "").strip()
            if et == "skill_supported_by_fact" and tgt and tgt not in fact_ids:
                fact_ids.append(tgt)
            elif et == "skill_supported_by_locked_bullet" and tgt and tgt not in bullet_ids:
                bullet_ids.append(tgt)

        fact_texts: list[str] = []
        for fid in fact_ids[:6]:
            nd = node_by_id.get(fid) or {}
            text = str(nd.get("description") or nd.get("label") or candidate_fact_claims.get(fid) or "").strip()
            if text and not _INTERNAL_ID_RE.fullmatch(text):
                fact_texts.append(text)
        bullet_texts: list[str] = []
        for bid in bullet_ids[:6]:
            nd = node_by_id.get(bid) or {}
            text = str(nd.get("description") or nd.get("label") or "").strip()
            if text and not _INTERNAL_ID_RE.fullmatch(text):
                bullet_texts.append(text)
        raw_cur_desc = str(node.get("description") or row.get("description") or "").strip()
        if _INTERNAL_ID_RE.search(raw_cur_desc) or any(p in raw_cur_desc.lower() for p in _META_EVIDENCE_PHRASES):
            raw_cur_desc = ""
        packets.append(
            {
                "skill_id": sid,
                "label": str(node.get("label") or row.get("capability") or sid).strip(),
                "current_description": raw_cur_desc,
                "pillar": str(row.get("pillar") or "").strip(),
                "subpillar": str(row.get("subpillar") or "").strip(),
                "domain_id": str(row.get("domain_id") or "").strip(),
                "allowed_phrases": [str(p).strip() for p in (row.get("allowed_phrases") or [])[:8] if str(p).strip()],
                "linked_facts": fact_texts,
                "linked_locked_bullets": bullet_texts,
            }
        )
    return packets


def _validate_drafted_descriptions(
    draft_list: list[Any],
    *,
    target_ids: Sequence[str],
    used_descriptions: set[str],
) -> tuple[dict[str, str], list[str]]:
    drafted: dict[str, str] = {}
    errors: list[str] = []
    seen_norms = set(used_descriptions)
    for row in draft_list:
        if not isinstance(row, Mapping):
            continue
        sid = str(row.get("skill_id") or "").strip()
        desc = " ".join(str(row.get("description") or "").replace("\u2014", ": ").replace("\u2013", "-").split())
        if sid not in target_ids:
            continue
        norm = desc.lower()
        if len(desc) < 36:
            errors.append(f"{sid}: too short ({len(desc)} chars)")
            continue
        if any(norm.startswith(pfx) for pfx in _TEMPLATE_BOILERPLATE_PREFIXES):
            errors.append(f"{sid}: forbidden template boilerplate prefix")
            continue
        id_match = _INTERNAL_ID_RE.search(desc)
        if id_match:
            errors.append(f"{sid}: leaked raw internal ID {id_match.group(0)!r}")
            continue
        meta_hit = next((p for p in _META_EVIDENCE_PHRASES if p in norm), None)
        if meta_hit:
            errors.append(f"{sid}: robotic meta-evidence boilerplate {meta_hit!r}")
            continue
        if norm in seen_norms:
            errors.append(f"{sid}: collided with an existing skill description")
            continue
        seen_norms.add(norm)
        drafted[sid] = desc

    missing = [sid for sid in target_ids if sid not in drafted]
    if missing:
        errors.append(f"omitted skill_id(s): {missing}")
    return drafted, errors


def draft_grounded_skill_descriptions(
    *,
    ledger: Mapping[str, Any],
    skill_ids: Sequence[str],
    used_descriptions: set[str],
    repo_root: Path = REPO_ROOT,
    draft_call_fn: JudgeCallFn | None = None,
    judge_call_fn: JudgeCallFn | None = None,
    verify_with_judge: bool = True,
) -> dict[str, str]:
    """Draft distinct, evidence-grounded descriptions via keyless IDE LLM and verify fail-closed with Judge v3."""
    target_ids = [str(s).strip() for s in skill_ids if str(s).strip()]
    if not target_ids:
        return {}

    resolved_root = Path(repo_root).resolve()
    packets = _collect_skill_evidence_packet(ledger, target_ids)
    pins = load_graph_hygiene_model_pins(resolved_root)

    draft_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["descriptions"],
        "properties": {
            "descriptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["skill_id", "description"],
                    "properties": {
                        "skill_id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            }
        },
    }
    base_prompt = (
        "Write one distinct, concrete, plain-English, evidence-grounded description (1 to 2 sentences, 40 to 260 characters) "
        "for each skill in SKILL_EVIDENCE_PACKETS so that no two skills share identical or near-identical text.\n"
        "RULES:\n"
        "1. Use ONLY capabilities, concepts, tools, and facts explicitly present in each skill's own packet.\n"
        "2. Do NOT invent employers, metrics, dates, certifications, or unmentioned technologies.\n"
        "3. NEVER cite raw internal IDs (such as fact_*, bul_*, skill_*, domain_*, metric_*) or meta-phrases like "
        "'archive-verified', 'backed by evidence in', 'supported by evidence in', or 'tied to archive-verified'.\n"
        "4. Do NOT use em-dashes, en-dashes, AI buzzwords, or rigid template openers like 'Applies X across Y in the Z domain'.\n"
        "5. Return strict JSON matching the schema with an entry for every requested skill_id.\n\n"
        f"SKILL_EVIDENCE_PACKETS:\n{json.dumps(packets, indent=2, ensure_ascii=False)}\n"
    )

    drafted: dict[str, str] = {}
    last_errors: list[str] = []
    for attempt in range(2):
        prompt = base_prompt
        if attempt > 0 and last_errors:
            prompt += (
                "\nPREVIOUS ATTEMPT REJECTED. Fix every violation below and rewrite cleanly in natural plain English:\n- "
                + "\n- ".join(last_errors)
                + "\n"
            )
        _, res = _call_with_quota_failover(
            prompt=prompt,
            candidate_models=[pins["drafter_primary"], *pins["drafter_backups"]],
            json_schema=draft_schema,
            effort="medium",
            call_fn=draft_call_fn,
        )
        raw_obj = res.structured_output if isinstance(res.structured_output, dict) else json.loads(str(res.response))
        draft_list = raw_obj.get("descriptions") if isinstance(raw_obj, Mapping) else None
        if not isinstance(draft_list, list):
            raise ValueError("Grounded clone drafter returned malformed payload missing 'descriptions' list.")
        drafted, last_errors = _validate_drafted_descriptions(
            draft_list,
            target_ids=target_ids,
            used_descriptions=used_descriptions,
        )
        if not last_errors:
            break
    if last_errors:
        raise ValueError(f"Grounded clone drafter failed validation: {'; '.join(last_errors)}")

    if verify_with_judge:
        verify_item = {
            "item_key": f"draft_verify::{'+'.join(sorted(target_ids))}",
            "member_ids": target_ids,
            "member_profiles": [
                {**p, "proposed_description": drafted[p["skill_id"]]}
                for p in packets
            ],
            "options": [
                {
                    "option_id": "accept_grounded_drafts",
                    "label": "Accept evidence-grounded distinct skill descriptions",
                    "action_kind": "differentiate_skill_descriptions",
                    "impact": "Replaces identical descriptions with verified distinct descriptions.",
                }
            ],
        }
        verdict = evaluate_hygiene_item_v3(
            cluster_id="CLUSTER-02B-VERBATIM-CLONE-SKILL-GROUPS",
            item=verify_item,
            repo_root=resolved_root,
            force_refresh=True,
            escalate_borderline=False,
            call_fn=judge_call_fn,
        )
        if not verdict.get("passed"):
            raise ValueError(
                f"Judge v3 vetoed drafted skill descriptions (failed_checks={verdict.get('failed_check_ids')}, "
                f"takeaway={verdict.get('cold_read_takeaway')!r})"
            )

    return drafted


def _fetch_sqlite_item_enrichment(db_path: Path, item: dict[str, Any]) -> dict[str, Any]:
    """Hydrate minimal node/fact/bullet details from SQLite when CLI is called directly on raw audit output."""
    if not db_path.is_file():
        return item
    ids: set[str] = set()
    for k in ("survivor_node_id", "retired_node_id", "node_id", "metric_id", "root_node_id", "target_node_id"):
        if item.get(k):
            ids.add(str(item[k]))
    for lk in ("member_ids", "candidate_skill_ids"):
        for v in item.get(lk) or []:
            if v:
                ids.add(str(v))
    if not ids:
        return item

    enriched = dict(item)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        ph = ",".join("?" for _ in ids)
        nodes = {
            str(r["node_id"]): dict(r)
            for r in conn.execute(
                f"SELECT node_id, node_type, label, description, activation_status, support_level, external_eligible, employer "
                f"FROM graph_nodes WHERE node_id IN ({ph})",
                sorted(ids),
            ).fetchall()
        }
        for nid, prof in nodes.items():
            facts = [
                {"id": str(er["target_node_id"]), "text": str(er["description"] or er["label"] or er["target_node_id"])}
                for er in conn.execute(
                    "SELECT e.target_node_id, gn.label, gn.description FROM graph_edges e "
                    "JOIN graph_nodes gn ON gn.node_id = e.target_node_id "
                    "WHERE e.source_node_id = ? AND e.edge_type IN ('skill_supported_by_fact', 'skill_supported_by_locked_bullet') "
                    "LIMIT 8",
                    (nid,),
                ).fetchall()
            ]
            prof["linked_fact_details"] = facts

        if enriched.get("survivor_node_id") and "survivor_profile" not in enriched:
            enriched["survivor_profile"] = nodes.get(str(enriched["survivor_node_id"]))
        if enriched.get("retired_node_id") and "retired_profile" not in enriched:
            enriched["retired_profile"] = nodes.get(str(enriched["retired_node_id"]))
        if enriched.get("node_id") and "node_profile" not in enriched:
            enriched["node_profile"] = nodes.get(str(enriched["node_id"]))
        if enriched.get("metric_id") and "metric_profile" not in enriched:
            enriched["metric_profile"] = nodes.get(str(enriched["metric_id"]))
        if enriched.get("member_ids") and "member_profiles" not in enriched:
            enriched["member_profiles"] = [nodes.get(str(m), {"node_id": str(m)}) for m in enriched["member_ids"]]
        if enriched.get("candidate_skill_ids") and "candidate_skill_profiles" not in enriched:
            enriched["candidate_skill_profiles"] = [
                nodes.get(str(s), {"node_id": str(s)}) for s in enriched["candidate_skill_ids"]
            ]
    finally:
        conn.close()
    return enriched


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Keyless Judge v3 Forensic Evaluator for Agents Graph Hygiene.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--mode", choices=("item", "cluster", "promotion"), required=True)
    parser.add_argument("--cluster-id", type=str, default="")
    parser.add_argument("--item-key", type=str, default="")
    parser.add_argument("--item-json", type=Path, default=None, help="Optional enriched item JSON file.")
    parser.add_argument("--diff-json", type=Path, default=None, help="Post-apply diff JSON file for promotion mode.")
    parser.add_argument("--cache-path", type=Path, default=None)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--artifact-out", type=Path, default=None)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    resolved_root = Path(args.repo_root).resolve()

    if args.mode == "promotion":
        if args.diff_json is None or not args.diff_json.is_file():
            raise SystemExit("ERROR: --mode promotion requires an existing --diff-json file.")
        diff_packet = json.loads(args.diff_json.read_text(encoding="utf-8"))
        res = evaluate_hygiene_promotion_jury_v3(
            diff_packet=diff_packet,
            repo_root=resolved_root,
            receipt_path=args.receipt_out,
            artifact_path=args.artifact_out,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("status") == "PASS" else 1

    from tools.audit_graph_hygiene_and_consolidation import DEFAULT_GRAPH_REL, run_graph_hygiene_audit  # noqa: E402

    db_path = Path(args.db).resolve() if args.db is not None else (resolved_root / DEFAULT_GRAPH_REL)

    if args.mode == "item":
        if args.item_json is not None and args.item_json.is_file():
            item_obj = json.loads(args.item_json.read_text(encoding="utf-8"))
            cid = args.cluster_id or str(item_obj.get("cluster_id") or "")
        else:
            audit = run_graph_hygiene_audit(repo_root=resolved_root, db_path=db_path)
            target_cluster = next(
                (c for c in audit["hitl_clusters"] if not args.cluster_id or c["cluster_id"] == args.cluster_id),
                None,
            )
            if target_cluster is None or not target_cluster.get("items"):
                raise SystemExit(f"ERROR: No matching cluster/items found for cluster_id={args.cluster_id!r}")
            cid = str(target_cluster["cluster_id"])
            if args.item_key:
                matched = [
                    it
                    for it in target_cluster["items"]
                    if args.item_key in (
                        str(it.get("item_key") or ""),
                        str(it.get("node_id") or ""),
                        str(it.get("metric_id") or ""),
                        str(it.get("retired_node_id") or ""),
                        str(it.get("survivor_node_id") or ""),
                    )
                ]
                if not matched:
                    raise SystemExit(f"ERROR: Item {args.item_key!r} not found in {cid}")
                item_obj = matched[0]
            else:
                item_obj = target_cluster["items"][0]
            item_obj = _fetch_sqlite_item_enrichment(db_path, item_obj)
            if args.item_key and not item_obj.get("item_key"):
                item_obj["item_key"] = args.item_key

        verdict = evaluate_hygiene_item_v3(
            cluster_id=cid,
            item=item_obj,
            repo_root=resolved_root,
            cache_path=args.cache_path,
            force_refresh=bool(args.force_refresh),
        )
        if args.receipt_out is not None:
            _atomic_write_json(args.receipt_out, verdict)
        print(json.dumps(verdict, indent=2))
        return 0 if verdict.get("llm_judge_executed") else 1

    # cluster mode
    audit = run_graph_hygiene_audit(repo_root=resolved_root, db_path=db_path)
    target_cluster = next((c for c in audit["hitl_clusters"] if c["cluster_id"] == args.cluster_id), None)
    if target_cluster is None:
        raise SystemExit(f"ERROR: Cluster not found: {args.cluster_id!r}")
    enriched_cluster = dict(target_cluster)
    enriched_cluster["items"] = [_fetch_sqlite_item_enrichment(db_path, dict(it)) for it in target_cluster.get("items") or []]
    verdicts = evaluate_hygiene_cluster_v3(
        cluster=enriched_cluster,
        repo_root=resolved_root,
        cache_path=args.cache_path,
        force_refresh=bool(args.force_refresh),
        max_items=(args.max_items if args.max_items > 0 else None),
    )
    payload = {
        "cluster_id": args.cluster_id,
        "evaluated_count": len(verdicts),
        "passed_count": sum(1 for v in verdicts if v.get("passed")),
        "verdicts": verdicts,
    }
    if args.receipt_out is not None:
        _atomic_write_json(args.receipt_out, payload)
    print(json.dumps(payload, indent=2))
    return 0 if all(v.get("llm_judge_executed") for v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
