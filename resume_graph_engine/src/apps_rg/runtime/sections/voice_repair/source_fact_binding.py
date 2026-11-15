"""Display-sentence-to-source-fact binding and claim ledger reconstruction."""
from __future__ import annotations

import re
from typing import Any

from .constants import _CANONICAL_DISPLAY_SENTENCES, _GRAPH_OVERRIDE_ANCHOR
from .parent_proxy import _p

def _source_fact_ids_for_display_sentence(sentence: str) -> list[str]:
    low = sentence.lower()
    if low.startswith("technology executive who led ibm-aws alliance co-sell motions"):
        return [
            "reb_ibm_aws_alliance_partner_cosell_gtm",
            "reb_unify_platform_commercialization_leadership",
            "reb_ibm_devsecops_release_resilience",
        ]
    if low.startswith("at ibm, financial-services modernization opportunities were shaped"):
        return [
            "reb_ibm_aws_alliance_partner_cosell_gtm",
            "skill_partner_alliance_gtm_execution",
            "skill_partner_joint_solution_development",
        ]
    if low.startswith("regulated devsecops release governance strengthened"):
        return ["reb_ibm_devsecops_release_resilience"]
    if low.startswith("from that foundation, the leader architects an agentic ai platform control plane"):
        return ["reb_unify_agentic_platform_architecture"]
    if "agentic ai platform control plane" in low and "explicit decision rules" in low:
        return ["reb_unify_agentic_platform_architecture"]
    if (
        ("release automation" in low or "automated release pipeline" in low)
        and ("security scanning" in low or "devsecops" in low)
    ):
        return ["reb_ibm_devsecops_release_resilience"]
    if low.startswith("together, partner solution architecture, regulated delivery"):
        return [
            "reb_ibm_aws_alliance_partner_cosell_gtm",
            "reb_ibm_devsecops_release_resilience",
            "reb_unify_platform_commercialization_leadership",
        ]
    # Metric patterns first — most specific, least ambiguous.
    # $22M IP-led revenue + 20% margin → fact_engineering_platform_006 (commercialization metrics).
    # When the same sentence also names team scale (8→28 from fact_exec_002), cite both.
    has_revenue_metric = bool(re.search(r"\$22m", low)) and ("20%" in low or "gross margin" in low or "revenue" in low)
    has_team_scale = bool(re.search(r"\b8\s+to\s+28\b", sentence, re.I))
    if bool(re.search(r"\$22m", low)):
        is_graph_era_or_multi = (
            "platform commercialization" in low
            or "commercialization leadership" in low
            or "insurtech" in low
            or "policy administration" in low
            or "migration execution" in low
            or "agentic platform" in low
            or "partner channel" in low
            or "dependency graph" in low
            or "regulated delivery foundation" in low
        )
        if is_graph_era_or_multi:
            res: list[str] = ["reb_unify_platform_commercialization_leadership", "metric_unify_22m_ip_led_revenue"]
            if "20%" in low or "gross margin" in low:
                res.append("metric_unify_20pct_gross_margin_expansion")
            if has_team_scale:
                res.append("metric_unify_team_scaled_8_to_28")
            if "agentic ai platform" in low or "agentic platform" in low:
                res.append("reb_unify_agentic_platform_architecture")
            if "insurtech" in low or "policy administration" in low or "migration execution" in low:
                res.append("reb_insurtech_aws_migration_execution")
            if "devsecops" in low or "release automation" in low:
                res.append("reb_ibm_devsecops_release_resilience")
            if "distributed cloud" in low or "databricks" in low:
                res.append("reb_unify_distributed_ecosystem_engineering")
            if "partner channel" in low or "alliance co-sell" in low or "co-sell" in low:
                res.append("reb_unify_partner_channel_cosell")
            if "dependency graph" in low:
                res.extend(["reb_unify_dependency_graph_accelerator", "fact_engineering_platform_002"])
            return list(dict.fromkeys(res))
        if has_revenue_metric and has_team_scale:
            return ["fact_engineering_platform_006", "fact_exec_002"]
        if has_revenue_metric:
            return ["fact_engineering_platform_006"]
        return ["reb_unify_platform_commercialization_leadership", "metric_unify_22m_ip_led_revenue"]
    if (
        "regulated delivery foundation" in low
        and "ip-led" in low
        and "20%" in low
        and "8 to 28" in low
    ):
        return [
            "reb_unify_platform_commercialization_leadership",
            "metric_unify_22m_ip_led_revenue",
            "metric_unify_20pct_gross_margin_expansion",
            "metric_unify_team_scaled_8_to_28",
        ]
    if (
        "that work drove" in low
        and "$22m" in low
        and "ip-led revenue" in low
        and "gross margin expansion" in low
        and "8 to 28" in low
    ):
        return [
            "reb_unify_platform_commercialization_leadership",
            "metric_unify_22m_ip_led_revenue",
            "metric_unify_20pct_gross_margin_expansion",
            "metric_unify_team_scaled_8_to_28",
        ]
    if has_team_scale:
        return ["fact_exec_002"]
    if "basel iii" in low and "40%" in low:
        return ["fact_governance_003"]
    from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import match_legacy_regulated_source_fact_ids
    _leg_fids = match_legacy_regulated_source_fact_ids(low)
    if _leg_fids is not None:
        return _leg_fids
    # Natural dependency graph mention or legacy anchor.
    if _GRAPH_OVERRIDE_ANCHOR in low or "dependency graph" in low:
        if "governed agentic ai platform" in low:
            return ["fact_engineering_platform_002", "fact_engineering_platform_001"]
        return ["fact_engineering_platform_002"]
    if (
        "governed agentic platform architecture" in low
        and "distributed cloud/data engineering" in low
        and "regulated ai delivery patterns" in low
    ):
        return [
            "reb_unify_agentic_platform_architecture",
            "reb_unify_distributed_ecosystem_engineering",
            "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
        ]
    if (
        "partner channel foundation" in low
        and "applied-ai architectures" in low
        and "partner ecosystems" in low
    ):
        return [
            "reb_unify_partner_channel_cosell",
            "reb_ibm_aws_alliance_partner_cosell_gtm",
        ]
    # FSA actuarial — check before generic "AI strategy" phrases.
    if "fsa-chartered actuarial work" in low:
        return ["fact_quant_hpc_003"]
    # Consulting delivery.
    if "directed large-scale regulatory" in low:
        return ["fact_consulting_001"]
    # Platform identity (S1 / generic platform sentences).
    if "agentic ai platform" in low or "platform runtime" in low:
        return ["fact_engineering_platform_001"]
    if (
        "governed cloud modernization" in low
        and (
            (
                "insurance core transformation" in low
                and "regulatory lineage" in low
            )
            or (
                "insurance core architecture" in low
                and "regulatory" in low
            )
            or (
                "enterprise architecture discipline" in low
                and "innovation programs" in low
            )
            or (
                "insurance core architecture" in low
                and "regulatory controls" in low
            )
        )
    ):
        return [
            "reb_ey_insurance_core_modernization",
            "reb_insurtech_aws_guidewire_core_modernization",
            "reb_ibm_aws_modernization_architecture",
        ]
    if (
        "convergence of governed cloud delivery" in low
        and "insurance platform depth" in low
        and "regulatory analytics" in low
        and "federate enterprise architecture standards" in low
    ):
        return [
            "reb_insurtech_aws_migration_execution",
            "reb_insurtech_regulated_aws_control_implementation",
            "reb_ibm_aws_modernization_architecture",
            "reb_unify_distributed_ecosystem_engineering",
            "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
        ]
    if (
        "governed architecture and accelerator foundation" in low
        and "federate innovation programs" in low
        and "standardize interoperability across acquired units" in low
        and "multi-year it strategy roadmap" in low
    ):
        return [
            "reb_ibm_aws_modernization_architecture",
            "reb_ibm_offering_accelerator_management",
            "reb_unify_distributed_ecosystem_engineering",
            "reb_insurtech_aws_migration_execution",
            "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
        ]
    if (
        "convergence of cloud execution" in low
        and "core systems governance" in low
        and "lineage-backed operating models" in low
        and "federate architecture standards" in low
    ):
        return [
            "reb_insurtech_aws_migration_execution",
            "reb_insurtech_regulated_aws_control_implementation",
            "reb_ibm_aws_modernization_architecture",
            "reb_unify_distributed_ecosystem_engineering",
            "reb_insurtech_insurance_regulatory_cloud_adoption_standards",
        ]
    if "enterprise technology leader" in low or "technology strategy executive" in low:
        if "governed ai platform" in low or "agentic ai" in low:
            return ["fact_engineering_platform_001"]
        return ["fact_exec_002"]
    # S6 forward-capstone patterns — federation / lineage discipline / Basel III governance themes.
    # NOTE: do NOT surface fact_engineering_platform_002 here. That fact (software dependency
    # graph) is not included in the SVP IT Strategy SRFS pool, and surfacing it would (a) be
    # orphan-stripped by the lane filter, and (b) cause _align_display_override_anchors_in_resume
    # to incorrectly rewrite S2 to the dependency-graph canonical sentence via its loose
    # `fid[:8] in sent_low` matcher (matches "engineering" in any sentence).
    if "federate governed platform capabilities" in low or "federated platform capabilities" in low:
        if "basel iii" in low:
            return ["fact_engineering_platform_001", "fact_governance_003"]
        return ["fact_engineering_platform_001"]
    if "without weakening basel iii" in low or "preserving lineage discipline" in low or "lineage discipline" in low:
        return ["fact_governance_003"]
    if "federate enterprise architecture standards" in low and (
        "repeatable architecture playbooks" in low
        or "post-merger integration playbooks" in low
    ):
        return [
            "reb_ibm_aws_modernization_architecture",
            "reb_ibm_offering_accelerator_management",
            "reb_unify_distributed_ecosystem_engineering",
        ]
    # Generic S6 capstone fallback — innovation/incubation forward statements anchor to platform identity.
    if ("innovation incubation" in low or "architecture standards" in low) and (
        "platform" in low or "capabilities" in low
    ):
        return ["fact_engineering_platform_001"]
    return []


def _graph_era_fact_ids(ids: list[str]) -> bool:
    """True when ids are from the graph-era proof pool rather than legacy fact_* ids."""
    return any(str(fid).strip() and not str(fid).startswith("fact_") for fid in ids)


def _rebind_source_fact_ids_from_prior_rows(
    sentence: str,
    prior_rows: list[dict[str, Any]],
) -> list[str]:
    """Carry over source_fact_ids from the prior ledger row a rewritten sentence derives from.

    Deterministic rewriters (canonical fact-slot injection, bridge connectives, word-budget
    trims) re-phrase a sentence so the anchor heuristics in
    ``_source_fact_ids_for_display_sentence`` no longer match — historically that DROPPED the
    model's source_fact_ids and tripped x2_claim_ledger_orphan_zero. Attribution here is
    token-overlap against the prior rows' claim_text (same tokenizer the materialization gate
    uses). Only a unique, high-confidence best match binds; ids are copied verbatim from that
    prior row (deduped, order preserved) — never fabricated. Ambiguous or weak attribution
    returns [] (fail-open: the row stays orphaned and the gate verdict stands).
    """
    from apps_rg.runtime.validators.executive_summary_x2 import _ledger_claim_tokens

    sent_low = str(sentence or "").lower()
    if not sent_low:
        return []
    best_idx = -1
    best_hits = 0
    best_coverage = 0.0
    second_hits = 0
    for idx, row in enumerate(prior_rows):
        if not isinstance(row, dict):
            continue
        sids = [str(s).strip() for s in (row.get("source_fact_ids") or []) if str(s).strip()]
        if not sids:
            continue
        tokens = _ledger_claim_tokens(str(row.get("claim_text") or ""))
        if not tokens:
            continue
        hits = sum(1 for t in tokens if t in sent_low)
        if hits > best_hits:
            second_hits = best_hits
            best_hits = hits
            best_idx = idx
            best_coverage = hits / len(tokens)
        elif hits > second_hits:
            second_hits = hits
    if best_idx < 0:
        return []
    # Confidence floor: enough absolute overlap, substantial coverage of the prior claim,
    # and a strictly unique best row. Anything weaker is genuinely ambiguous -> no bind.
    if best_hits < 4 or best_coverage < 0.35 or best_hits == second_hits:
        return []
    carried: list[str] = []
    seen: set[str] = set()
    for sid in prior_rows[best_idx].get("source_fact_ids") or []:
        s = str(sid).strip()
        if s and s not in seen:
            seen.add(s)
            carried.append(s)
    return carried


def _rebind_from_canonical_display_sentences(sentence: str) -> list[str]:
    """Attribute a display sentence to the fact whose CANONICAL injected sentence it is a
    trimmed/bridge-stripped variant of.

    ``_enforce_required_fact_slots`` injects ``_CANONICAL_DISPLAY_SENTENCES[fid]`` verbatim,
    then later trim strategies strip openers/adjectives — breaking both the anchor
    heuristics and prior-row rebind (the model never wrote a row for the injected content).
    The injector knows the fact identity by construction, so a high-coverage token match
    against the canon SSOT binds [fid]; anything below the floor stays orphaned (fail-open).
    """
    from apps_rg.runtime.validators.executive_summary_x2 import _ledger_claim_tokens

    sent_low = str(sentence or "").lower()
    if not sent_low:
        return []
    best_fid = ""
    best_coverage = 0.0
    second_coverage = 0.0
    for fid, canon in _CANONICAL_DISPLAY_SENTENCES.items():
        tokens = _ledger_claim_tokens(str(canon or ""))
        if not tokens:
            continue
        coverage = sum(1 for t in tokens if t in sent_low) / len(tokens)
        if coverage > best_coverage:
            second_coverage = best_coverage
            best_coverage = coverage
            best_fid = fid
        elif coverage > second_coverage:
            second_coverage = coverage
    # Trimmed canon variants retain the bulk of the canon's tokens; require a clear margin.
    if best_fid and best_coverage >= 0.55 and best_coverage > second_coverage:
        return [best_fid]
    return []


def _source_fact_ids_from_row(row: dict[str, Any] | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for sid in row.get("source_fact_ids") or []:
        s = str(sid).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _rebuild_claim_ledger_from_display(parsed: dict[str, Any]) -> dict[str, Any]:
    from apps_rg.runtime.validators.executive_summary_x2 import split_sentences

    out = dict(parsed)
    prior_rows = [r for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
    sentences = split_sentences(str(out.get("resume_display_text") or ""))
    ledger: list[dict[str, Any]] = []
    for sent in sentences:
        s = str(sent or "").strip()
        if not s:
            continue
        fids = []
        prior_row = prior_rows[len(ledger)] if len(ledger) < len(prior_rows) else None
        prior_fids = _p("_source_fact_ids_from_row", _source_fact_ids_from_row)(prior_row)
        anchor_fids = _p("_source_fact_ids_for_display_sentence", _source_fact_ids_for_display_sentence)(s)
        if prior_fids:
            # Slot-aligned narrative rewrites must keep the row's existing proof ids.
            # Display heuristics normally only fill rows that started empty. When a
            # live graph-era phrase now maps to a more precise required fact, prefer
            # that bounded anchor set so brushstroke coverage cannot be lost by a
            # stale provider row.
            from apps_rg.runtime.sections.executive_summary_synthesis_contract import DEPENDENCY_GRAPH_FACT_ID
            _anchor_override = {
                "reb_unify_platform_commercialization_leadership", "reb_ibm_devsecops_release_resilience",
                "reb_unify_agentic_platform_architecture", "reb_ey_erm_risk_governance",
                "reb_insurtech_aws_migration_execution", DEPENDENCY_GRAPH_FACT_ID,
            }
            needs_anchor = bool(_anchor_override & set(anchor_fids)) and not bool(_anchor_override & set(prior_fids))
            is_legacy_profile = any(f.startswith("fact_") for f in prior_fids) and not any(f.startswith("reb_") for f in prior_fids)
            fids = list(dict.fromkeys(prior_fids + anchor_fids)) if (needs_anchor and not is_legacy_profile) else prior_fids
        else:
            fids = anchor_fids
            if not fids:
                prior_fids = _p("_rebind_source_fact_ids_from_prior_rows", _rebind_source_fact_ids_from_prior_rows)(s, prior_rows)
                if prior_fids and (not fids or _p("_graph_era_fact_ids", _graph_era_fact_ids)(prior_fids)):
                    # Live graph-era pools use reb_*/metric_*/skill_* ids. The legacy anchor
                    # heuristics can match the prose but return fact_* ids that are not in the
                    # active allowlist; when the model's own row still overlaps, preserve it.
                    fids = prior_fids
                if not fids:
                    # Anchor heuristics missed (rewritten/bridged sentence) — re-bind the ids from
                    # the prior ledger row this sentence derives from instead of dropping them.
                    fids = prior_fids
        if not fids:
            # The chain's OWN injected canonical sentence has no prior model row to bind to
            # (live: exec_summary_20260611_162322 row 1 — the required-fact-slot bridge,
            # bridge-stripped by the word trim so the anchor missed). The injector's SSOT
            # knows the fact identity by construction: a trimmed variant still shares the
            # bulk of its canon's tokens.
            fids = _p("_rebind_from_canonical_display_sentences", _rebind_from_canonical_display_sentences)(s)
        ledger.append(
            {
                "claim": s[:80],
                "claim_text": s,
                "source_fact_ids": fids,
            }
        )
    if ledger:
        out["claim_ledger"] = ledger
    return out
