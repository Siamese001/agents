"""Calibrated confidence and evidence linking for graph edges and nodes (Wave 2).

Provides:
- score_claim_bearing_edge: Noisy-OR over independent evidence, capped by source node score.
- calibrate_edge_confidence: Assigns confidence_score, confidence_tier, and confidence_method.
- extract_edge_evidence: Resolves evidence rows for claim-bearing and rule-backed edges.
- compute_node_confidence: Computes calibrated confidence for graph_nodes and splits BLOCKED into activation_status.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

CLAIM_BEARING_ASSERTION_TYPES = frozenset(
    {
        "EVIDENTIAL_SUPPORT",
        "METRIC_BINDING",
    }
)

RULE_BACKED_ASSERTION_TYPES = frozenset(
    {
        "POLICY_ELIGIBILITY",
        "POLICY_RESTRICTION",
        "TAXONOMIC_ATTRIBUTION",
        "STRUCTURAL_CONTAINMENT",
        "ASSOCIATIVE_BRIDGE",
        "TEMPORAL_SEQUENCE",
        "CROSS_ARC_CONTINUITY",
        "CREDENTIAL_VALIDATION",
    }
)


def _quote_sha256(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def load_verbatim_quote_index(repo_root: Path | None = None) -> dict[str, tuple[str, str, str]]:
    """Index canonical source documents into node_id -> (source_doc, span, quote_sha256)."""
    from apps_rg.fact_inventory.metric_outcome_materializer import (
        discover_role_episode_bundle_files,
    )
    from apps_rg.repository_layout import (
        repository_root,
        resolve_apps_rg_path,
        resolve_repository_path,
    )
    from .constants import CANDIDATE_LEDGER_REL_PATH

    root = repository_root(repo_root or Path(__file__))
    index: dict[str, tuple[str, str, str]] = {}

    def _rel(p: Path) -> str:
        return p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()

    # 1. Candidate facts ledger
    cand_path = resolve_repository_path(root, CANDIDATE_LEDGER_REL_PATH)
    if cand_path.is_file():
        try:
            cand_data = json.loads(cand_path.read_text(encoding="utf-8"))
            rel_cand = _rel(cand_path)
            for idx, cf in enumerate(cand_data.get("candidate_facts") or []):
                if not isinstance(cf, dict):
                    continue
                fid = str(cf.get("candidate_fact_id") or "").strip()
                quote = str(cf.get("claim_text") or cf.get("verbatim_quote") or "").strip()
                if fid and quote:
                    index[fid] = (rel_cand, f"candidate_facts[{idx}].claim_text", _quote_sha256(quote))
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    # 2. Base resume JSON (employments, locked bullets, certifications, education)
    br_path = resolve_apps_rg_path(root, "resume", "base", "amit_ayer_base_resume_v1.json")
    if br_path.is_file():
        try:
            br_data = json.loads(br_path.read_text(encoding="utf-8"))
            rel_br = _rel(br_path)
            br_facts = br_data.get("facts") if isinstance(br_data, dict) else {}
            if isinstance(br_facts, dict):
                for e_idx, emp in enumerate(br_facts.get("employment") or []):
                    if not isinstance(emp, dict):
                        continue
                    fid = str(emp.get("fact_id") or "").strip()
                    narr = str(emp.get("role_narrative") or emp.get("mandate_line") or "").strip()
                    if fid and narr:
                        sha = _quote_sha256(narr)
                        index[fid] = (rel_br, f"facts.employment[{e_idx}].role_narrative", sha)
                        index[f"employment_{fid}"] = (rel_br, f"facts.employment[{e_idx}].role_narrative", sha)
                    for b_idx, bul in enumerate(emp.get("bullets") or []):
                        if not isinstance(bul, dict):
                            continue
                        bid = str(bul.get("bullet_id") or "").strip()
                        btxt = str(bul.get("text") or "").strip()
                        if bid and btxt:
                            index[bid] = (
                                rel_br,
                                f"facts.employment[{e_idx}].bullets[{b_idx}].text",
                                _quote_sha256(btxt),
                            )
                for c_idx, cert in enumerate(br_facts.get("certifications") or []):
                    if not isinstance(cert, dict):
                        continue
                    cid = str(cert.get("fact_id") or "").strip()
                    cname = str(cert.get("name") or "").strip()
                    if cid and cname:
                        index[cid] = (rel_br, f"facts.certifications[{c_idx}].name", _quote_sha256(cname))
                for d_idx, edu in enumerate(br_facts.get("education") or []):
                    if not isinstance(edu, dict):
                        continue
                    did = str(edu.get("fact_id") or "").strip()
                    deg = f"{edu.get('degree') or ''}, {edu.get('institution') or ''}".strip(", ")
                    if did and deg:
                        index[did] = (rel_br, f"facts.education[{d_idx}].degree", _quote_sha256(deg))
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    # 3. Role episode bundles (engagements and metric outcomes)
    for bpath in discover_role_episode_bundle_files(root):
        if not bpath.is_file():
            continue
        try:
            bdata = json.loads(bpath.read_text(encoding="utf-8"))
            rel_b = _rel(bpath)
            for b_idx, bundle in enumerate(bdata.get("bundles") or []):
                if not isinstance(bundle, dict):
                    continue
                reb_id = str(bundle.get("bundle_id") or "").strip()
                b_summary = str(
                    bundle.get("story_anchor")
                    or bundle.get("summary")
                    or bundle.get("role_episode_title")
                    or reb_id
                ).strip()
                if reb_id and b_summary:
                    index[reb_id] = (rel_b, f"bundles[{b_idx}].story_anchor", _quote_sha256(b_summary))
                for m_idx, metric in enumerate(bundle.get("metrics") or []):
                    if not isinstance(metric, dict):
                        continue
                    mid = str(metric.get("metric_id") or "").strip()
                    mtxt = str(
                        metric.get("approved_claim_text")
                        or metric.get("metric_text")
                        or metric.get("value_display")
                        or ""
                    ).strip()
                    if mid and mtxt:
                        msha = _quote_sha256(mtxt)
                        index[mid] = (rel_b, f"bundles[{b_idx}].metrics[{m_idx}].metric_text", msha)
                        index[f"metric_outcome_{mid}"] = (
                            rel_b,
                            f"bundles[{b_idx}].metrics[{m_idx}].metric_text",
                            msha,
                        )
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    return index

CONFIDENCE_TIERS = frozenset({"HIGH", "MEDIUM", "LOW", "UNSCORED", "NOT_APPLICABLE"})

ALLOWED_EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "fact",
        "locked_bullet",
        "repo_evidence",
        "employment",
        "certification",
        "concept",
        "metric_outcome",
        "bundle",
        "policy_rule",
        "edge_contract",
        "skill_row_field",
        "operator_confirmation",
    }
)


def _map_evidence_kind(raw_kind: str) -> str:
    k = str(raw_kind or "").strip().lower()
    if k in ALLOWED_EVIDENCE_KINDS:
        return k
    if k == "skill":
        return "skill_row_field"
    if k in ("metric", "metric_bucket"):
        return "metric_outcome"
    if k in ("policy", "policy_rule"):
        return "policy_rule"
    return "concept"


def score_claim_bearing_edge(
    *,
    evidence_rows: list[dict[str, Any]],
    source_node_score: float | None = None,
    correlation_rho: float = 0.0,
) -> tuple[float | None, str, str]:
    """Calculate calibrated confidence score and tier for a claim-bearing edge.

    Uses decorrelated Noisy-OR over independent evidence items:
        When correlation_rho == 0.0 (default): noisy_or = 1.0 - product(1.0 - s_i)
        When correlation_rho > 0.0: shared-source items apply exponent (1 - rho)
        to avoid duplicate-document confidence inflation.
    Capped by the source node's confidence score (if known).
    """
    independent_rows = [
        r for r in evidence_rows if int(r.get("is_independent") or 0) == 1
    ]
    if not independent_rows:
        return None, "UNSCORED", "no_independent_evidence"

    product = 1.0
    doc_counts: dict[str, int] = {}
    rho = max(0.0, min(0.85, float(correlation_rho)))
    for r in independent_rows:
        s = float(r.get("evidence_strength") if r.get("evidence_strength") is not None else 1.0)
        clamped = max(0.0, min(1.0, s))
        doc = str(r.get("source_doc") or "").strip()
        seen_n = doc_counts.get(doc, 0)
        if doc:
            doc_counts[doc] = seen_n + 1
        eff_weight = (1.0 - rho) if (rho > 0.0 and doc and seen_n > 0) else 1.0
        eff_s = 1.0 - ((1.0 - clamped) ** eff_weight)
        product *= (1.0 - eff_s)
    raw_score = 1.0 - product

    # Cap by source node score if provided
    if source_node_score is not None:
        capped_score = min(raw_score, max(0.0, min(1.0, float(source_node_score))))
    else:
        capped_score = raw_score

    score = round(capped_score, 4)
    if score >= 0.80:
        tier = "HIGH"
    elif score >= 0.55:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    method = "bayesian_noisy_or_compounding_v1" if rho > 0.0 else "noisy_or_independent_evidence"
    return score, tier, method


def compute_compounding_skill_confidence(
    node: Mapping[str, Any],
    *,
    skill_row: Mapping[str, Any] | None = None,
    fact_count: int = 0,
    quote_backed_facts: int = 0,
    distinct_employers: int = 1,
    distinct_epochs: int = 1,
    has_credential: bool = False,
    has_locked_bullet: bool = False,
    human_confirmed: bool = False,
    metric_count: int = 0,
) -> tuple[float, str, str]:
    """Compute continuous Bayesian career-compounding confidence (zero age decay).

    Combines base evidence grade prior with log-odds increments from verified facts,
    verbatim quote custody, multi-employer/multi-epoch recurrence, credentials,
    locked bullets, HITL confirmation, and linked metric outcomes.
    """
    import math

    base_score, base_tier, act_status = compute_node_confidence(dict(node), skill_row=dict(skill_row) if skill_row else None)
    if act_status in ("BLOCKED", "RETIRED", "QUARANTINED_UNVERIFIED_SYNTHETIC") or base_score == 0.0:
        return 0.0, "LOW", act_status

    raw_conf = str(node.get("confidence") or (skill_row.get("confidence_grade") if skill_row else "") or "").strip().upper()
    if raw_conf == "HIGH":
        logit = 0.70
    elif raw_conf == "MEDIUM":
        logit = 0.25
    elif raw_conf == "LOW":
        logit = -0.35
    else:
        logit = 0.20

    # Career-compounding evidence accumulation (strictly monotonic, zero age decay)
    logit += 0.28 * min(5, max(0, int(fact_count)))
    logit += 0.14 * min(4, max(0, int(quote_backed_facts)))
    logit += 0.22 * min(4, max(0, int(distinct_employers) - 1))
    logit += 0.20 * min(5, max(0, int(distinct_epochs) - 1))
    logit += 0.10 * min(4, max(0, int(metric_count)))
    if has_credential:
        logit += 0.30
    if has_locked_bullet:
        logit += 0.25
    if human_confirmed:
        logit += 0.18

    prob = 1.0 / (1.0 + math.exp(-logit))
    # Preserve operator hold caps for portfolio/internal skills
    hold_mode = str((skill_row or {}).get("operator_hold_mode") or "").strip().upper()
    if hold_mode == "INTERNAL_ONLY":
        prob = min(prob, 0.54)
    elif hold_mode == "PORTFOLIO_ONLY":
        prob = min(prob, 0.78)
    score = round(max(0.35, min(0.99, prob)), 4)
    if score >= 0.80:
        tier = "HIGH"
    elif score >= 0.55:
        tier = "MEDIUM"
    else:
        tier = "LOW"
    return score, tier, act_status


def calibrate_edge_confidence(
    edge_row: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    *,
    source_node_score: float | None = None,
    target_node_status: str = "",
    correlation_rho: float = 0.0,
) -> dict[str, Any]:
    """Attach calibrated confidence_score, confidence_tier, and confidence_method to edge_row.

    Decouples confidence from validation_status by mirroring confidence_tier to
    the legacy confidence column. Forces 0.0 LOW on edges targeting quarantined/blocked/retired nodes.
    """
    assertion_type = str(edge_row.get("assertion_type") or "").strip()
    if str(target_node_status or "").strip().upper() in (
        "QUARANTINED_UNVERIFIED_SYNTHETIC",
        "BLOCKED",
        "RETIRED",
    ):
        if assertion_type in CLAIM_BEARING_ASSERTION_TYPES:
            score: float | None = 0.0
            tier = "LOW"
            method = "quarantined_endpoint_zeroed"
        else:
            score = None
            tier = "NOT_APPLICABLE"
            method = "rule_governed"
        edge_row["traversable"] = 0
        edge_row["lifecycle_disposition"] = "HELD_NON_ACTIVE_ENDPOINT"
    elif assertion_type in CLAIM_BEARING_ASSERTION_TYPES:
        score, tier, method = score_claim_bearing_edge(
            evidence_rows=evidence_rows,
            source_node_score=source_node_score,
            correlation_rho=correlation_rho,
        )
    else:
        score = None
        tier = "NOT_APPLICABLE"
        method = "rule_governed"

    edge_row["confidence_score"] = score
    edge_row["confidence_tier"] = tier
    edge_row["confidence_method"] = method
    # Legacy confidence column mirrors confidence_tier (decoupled from validation_status)
    edge_row["confidence"] = tier
    return edge_row


def compute_node_confidence(
    node: dict[str, Any],
    *,
    skill_row: dict[str, Any] | None = None,
) -> tuple[float | None, str, str]:
    """Calculate calibrated confidence score and tier for a graph node.

    Splits BLOCKED out of legacy confidence into activation_status='BLOCKED'.
    Returns:
        (confidence_score, confidence_tier, updated_activation_status)
    """
    ntype = str(node.get("node_type") or "").strip()
    raw_conf = str(node.get("confidence") or "").strip().upper()
    act_status = str(node.get("activation_status") or "").strip()

    # Preserve explicit operator hold/retirement modes before BLOCKED splitting
    if ntype == "skill" and act_status == "RETIRED":
        return 0.0, "LOW", "RETIRED"
    if ntype == "skill" and skill_row is not None:
        hold_mode = str(skill_row.get("operator_hold_mode") or "").strip().upper()
        if hold_mode == "RETIRED":
            return 0.0, "LOW", "RETIRED"
        if hold_mode == "PORTFOLIO_ONLY":
            return 0.75, "MEDIUM", act_status if act_status and act_status != "BLOCKED" else "ACTIVE"
        if hold_mode == "INTERNAL_ONLY":
            return 0.50, "LOW", act_status if act_status and act_status != "BLOCKED" else "ACTIVE"

    # Split BLOCKED from confidence into activation_status
    if raw_conf == "BLOCKED" or act_status == "BLOCKED":
        return 0.0, "LOW", "BLOCKED"

    if ntype == "skill":
        # Grade from skill_row or confidence column
        grade = raw_conf or (str(skill_row.get("confidence_grade") or "").upper() if skill_row else "")
        if grade == "HIGH":
            return 0.90, "HIGH", act_status or "ACTIVE"
        elif grade == "MEDIUM":
            return 0.75, "MEDIUM", act_status or "ACTIVE"
        elif grade == "LOW":
            return 0.50, "LOW", act_status or "ACTIVE"
        return 0.75, "MEDIUM", act_status or "ACTIVE"

    if ntype in ("fact", "locked_bullet", "repo_evidence", "certification"):
        if act_status == "ACTIVE_CONFIRMED" or str(node.get("support_level") or "") == "DIRECT_FROM_RESUME_ARCHIVE":
            return 0.95, "HIGH", act_status or "ACTIVE_CONFIRMED"
        if act_status in ("ACTIVE", "APPROVED_GRAPH_SSOT"):
            return 0.90, "HIGH", act_status
        return 0.85, "HIGH", act_status or "ACTIVE"

    if ntype in ("metric", "metric_outcome", "metric_bucket"):
        if act_status.upper() in ("QUARANTINED_UNVERIFIED_SYNTHETIC", "BLOCKED", "RETIRED"):
            return 0.0, "LOW", act_status
        return 0.90, "HIGH", act_status or "APPROVED_GRAPH_SSOT"

    # Reference / structural nodes
    return None, "NOT_APPLICABLE", act_status or "ACTIVE"


def extract_edge_evidence(
    edge_row: dict[str, Any],
    *,
    node_types_by_id: dict[str, str] | None = None,
    connecting_facts_by_pair: dict[tuple[str, str], list[str]] | None = None,
    quote_index: Mapping[str, tuple[str, str, str]] | None = None,
    metric_to_facts: Mapping[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Extract and build edge_evidence rows for an edge with verbatim quote lineage."""
    types_map = node_types_by_id or {}
    qindex = quote_index or {}
    m2f = metric_to_facts or {}
    eid = str(edge_row.get("edge_id") or "")
    et = str(edge_row.get("edge_type") or "")
    src = str(edge_row.get("source_node_id") or "")
    tgt = str(edge_row.get("target_node_id") or "")
    assertion_type = str(edge_row.get("assertion_type") or "")
    rule_id = str(edge_row.get("derivation_rule_id") or "")

    evidence_rows: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    def _lookup_quote(nid: str) -> tuple[str, str, str]:
        if not nid:
            return "", "", ""
        hit = qindex.get(nid)
        if hit:
            return hit
        if nid.startswith("metric_outcome_"):
            hit = qindex.get(nid.removeprefix("metric_outcome_"))
            if hit:
                return hit
        return "", "", ""

    def _add_evidence(
        *,
        evidence_ref: str,
        evidence_node_id: str,
        evidence_kind: str,
        is_independent: int,
        evidence_strength: float = 1.0,
        human_confirmed: int = 0,
        source_doc: str = "",
        span: str = "",
        quote_sha256: str = "",
    ) -> None:
        ref_s = str(evidence_ref).strip()
        if not ref_s or ref_s in seen_refs:
            return
        # Ensure evidence_node_id resolves to graph_nodes or is empty
        if evidence_node_id and evidence_node_id not in types_map:
            evidence_node_id = ""
        if not source_doc or not quote_sha256:
            q_doc, q_span, q_sha = _lookup_quote(evidence_node_id)
            if not q_sha and ref_s.startswith(("fact:", "node:", "metric:", "base_resume:")):
                q_doc, q_span, q_sha = _lookup_quote(ref_s.split(":", 1)[1])
            source_doc = source_doc or q_doc
            span = span or q_span
            quote_sha256 = quote_sha256 or q_sha
        seen_refs.add(ref_s)
        evidence_rows.append(
            {
                "edge_id": eid,
                "evidence_ref": ref_s,
                "evidence_node_id": evidence_node_id,
                "evidence_kind": _map_evidence_kind(evidence_kind),
                "is_independent": is_independent,
                "source_doc": source_doc,
                "span": span,
                "quote_sha256": quote_sha256,
                "human_confirmed": human_confirmed,
                "evidence_strength": round(max(0.0, min(1.0, evidence_strength)), 4),
            }
        )

    # 1. Claim-bearing edges: must link to resolvable evidence node(s) in graph_nodes
    if assertion_type == "EVIDENTIAL_SUPPORT":
        # Target node is the supporting evidence
        target_kind = types_map.get(tgt, "fact")
        is_human = 1 if str(edge_row.get("validation_status") or "") == "validated" else 0
        strength = 0.95 if is_human else 0.85
        _add_evidence(
            evidence_ref=f"node:{tgt}",
            evidence_node_id=tgt,
            evidence_kind=target_kind,
            is_independent=1,
            evidence_strength=strength,
            human_confirmed=is_human,
        )

    elif assertion_type == "METRIC_BINDING":
        if et == "skill_surfaces_metric_outcome":
            # Connecting facts from proof chain serve as independent third-party evidence
            cfacts = connecting_facts_by_pair.get((src, tgt), []) if connecting_facts_by_pair else []
            for fid in cfacts:
                _add_evidence(
                    evidence_ref=f"fact:{fid}",
                    evidence_node_id=fid,
                    evidence_kind="fact",
                    is_independent=1,
                    evidence_strength=0.90,
                )
            # Target metric node is independent only if no connecting fact witness exists
            _add_evidence(
                evidence_ref=f"metric:{tgt}",
                evidence_node_id=tgt,
                evidence_kind="metric_outcome" if types_map.get(tgt) == "metric_outcome" else "metric",
                is_independent=0 if cfacts else 1,
                evidence_strength=0.85,
            )
        elif et in ("fact_has_metric_outcome", "locked_bullet_has_metric_outcome"):
            # Source fact/bullet node is document-backed evidence
            _add_evidence(
                evidence_ref=f"fact:{src}",
                evidence_node_id=src,
                evidence_kind=types_map.get(src, "fact"),
                is_independent=1,
                evidence_strength=0.90,
            )
        elif et == "skill_can_surface_metric":
            _add_evidence(
                evidence_ref=f"metric:{tgt}",
                evidence_node_id=tgt,
                evidence_kind="metric_outcome" if types_map.get(tgt) == "metric_outcome" else "fact",
                is_independent=1,
                evidence_strength=0.85,
            )
        elif et in ("metric_outcome_anchors_bundle", "metric_outcome_bound_to_employer"):
            # Prefer backing fact witness over self-referential metric endpoint
            backing_facts = m2f.get(src, [])
            for fid in backing_facts:
                _add_evidence(
                    evidence_ref=f"fact:{fid}",
                    evidence_node_id=fid,
                    evidence_kind=types_map.get(fid, "fact"),
                    is_independent=1,
                    evidence_strength=0.90,
                )
            node_id = src if src in types_map else tgt
            kind = types_map.get(node_id, "metric_outcome")
            _add_evidence(
                evidence_ref=f"node:{node_id}",
                evidence_node_id=node_id,
                evidence_kind=kind,
                is_independent=0 if backing_facts else 1,
                evidence_strength=0.90,
            )

    # 2. Rule-backed / non-claim-bearing edges: must cite policy_rule or edge_contract
    elif assertion_type in ("POLICY_ELIGIBILITY", "POLICY_RESTRICTION"):
        ref_rule = rule_id or f"rule_{et}"
        _add_evidence(
            evidence_ref=f"policy_rule:{ref_rule}",
            evidence_node_id="",
            evidence_kind="policy_rule",
            is_independent=0,
            evidence_strength=1.0,
        )
    elif assertion_type in ("CROSS_ARC_CONTINUITY", "CREDENTIAL_VALIDATION"):
        _add_evidence(
            evidence_ref=f"contract:edge_types/{et}",
            evidence_node_id="",
            evidence_kind="edge_contract",
            is_independent=0,
            evidence_strength=1.0,
        )
        if assertion_type == "CREDENTIAL_VALIDATION" and src in types_map:
            _add_evidence(
                evidence_ref=f"node:{src}",
                evidence_node_id=src,
                evidence_kind=types_map.get(src, "certification"),
                is_independent=1,
                evidence_strength=0.95,
                human_confirmed=1,
            )
    else:
        # Taxonomic, Structural, Associative, Temporal
        _add_evidence(
            evidence_ref=f"contract:edge_types/{et}",
            evidence_node_id="",
            evidence_kind="edge_contract",
            is_independent=0,
            evidence_strength=1.0,
        )
        if assertion_type in ("ASSOCIATIVE_BRIDGE", "TEMPORAL_SEQUENCE"):
            _add_evidence(
                evidence_ref=f"operator_confirmation:{eid}",
                evidence_node_id="",
                evidence_kind="operator_confirmation",
                is_independent=0,
                evidence_strength=0.94,
                human_confirmed=1,
            )

    # 3. Ingest any explicit assertion_basis_refs from ledger/contract
    raw_refs = edge_row.get("assertion_basis_refs")
    if not raw_refs and edge_row.get("assertion_basis_refs_json"):
        try:
            raw_refs = json.loads(edge_row["assertion_basis_refs_json"])
        except (ValueError, TypeError):
            raw_refs = []

    if isinstance(raw_refs, list):
        for ref_str in raw_refs:
            r = str(ref_str).strip()
            if not r or r in seen_refs:
                continue
            # Parse ref structure; prevent self-endpoint refs from inflating independent evidence
            if r.startswith("ledger:graph_nodes/") or r.startswith("baseline:graph_nodes/"):
                nid = r.split("/")[-1]
                is_self_endpoint = nid in (src, tgt)
                if nid in types_map:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id=nid,
                        evidence_kind=types_map.get(nid, "fact"),
                        is_independent=0 if is_self_endpoint else 1,
                        evidence_strength=0.85,
                    )
                else:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id="",
                        evidence_kind="fact",
                        is_independent=0,
                        evidence_strength=1.0,
                    )
            elif any(r.startswith(p) for p in ("fact:", "metric:", "node:", "employment:", "skill:")):
                prefix, nid = r.split(":", 1)
                is_self_endpoint = nid in (src, tgt)
                if nid in types_map:
                    _add_evidence(
                        evidence_ref=r,
                        evidence_node_id=nid,
                        evidence_kind=types_map.get(nid, prefix),
                        is_independent=0 if is_self_endpoint else 1,
                        evidence_strength=0.90,
                    )
            elif r.startswith("contract:edge_types/"):
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="edge_contract",
                    is_independent=0,
                    evidence_strength=1.0,
                )
            elif r.startswith("policy:") or "policy" in r:
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="policy_rule",
                    is_independent=0,
                    evidence_strength=1.0,
                )
            elif r.startswith("reb_") or "bundle" in r:
                _add_evidence(
                    evidence_ref=r,
                    evidence_node_id="",
                    evidence_kind="bundle",
                    is_independent=0,
                    evidence_strength=1.0,
                )

    return evidence_rows
