"""Judge-alignment structural polish, dependency graph dedupe, and fact slot enforcement."""
from __future__ import annotations

import re
from typing import Any

from .constants import (
    _AI_PARTNERSHIP_COHERENCE_COMPACTION,
    _AI_PARTNERSHIP_DEVSECOPS_S5,
    _AI_PARTNERSHIP_DISTINCT_S2,
    _AI_PARTNERSHIP_EVIDENCE_LED_S6,
    _AI_PARTNERSHIP_META_S6_RE,
    _AI_PARTNERSHIP_PAST_TENSE_S1,
    _AI_PARTNERSHIP_PLATFORM_CONTROL_S2,
    _AI_PARTNERSHIP_S4_REPEAT_RE,
    _AI_PARTNERSHIP_S4_SENTENCE,
    _AI_PARTNERSHIP_S6_SENTENCE,
    _CANONICAL_DISPLAY_SENTENCES,
    _CANONICAL_FACT_SLOT,
    _GRAPH_OVERRIDE_ANCHOR,
    _STOCK_BRIDGE_OPENERS,
    _STOCK_BRIDGE_PREFIX_RE,
)
from .parent_proxy import _p
from .source_fact_binding import _source_fact_ids_for_display_sentence

def _dedupe_dependency_graph_sentences(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
) -> list[str]:
    """Keep one forward-modal graph sentence; repurpose duplicates for team scale or capstone."""
    from apps_rg.runtime.sections.exec_summary_graph_only_quality import (
        _strategic_closer_sentence,
    )
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
        DEPENDENCY_GRAPH_FACT_ID,
    )

    graph_idxs = [i for i, s in enumerate(sentences) if "dependency graph" in s.lower()]
    if len(graph_idxs) <= 1:
        return sentences

    keep = graph_idxs[0]
    allowed = {
        str(f.get("fact_id") or "").strip()
        for f in selected_facts or []
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    need_team = "fact_exec_002" in allowed and not re.search(
        r"\b8\s+to\s+28\b", " ".join(sentences), re.I
    )
    out = list(sentences)
    for idx in graph_idxs:
        if idx == keep:
            continue
        if need_team:
            out[idx] = (
                "In parallel, the ML engineering organization grew from 8 to 28 specialists, "
                "including senior engineers and platform leads."
            )
            need_team = False
            continue
        out[idx] = _strategic_closer_sentence("")
    return out


def _weave_exec_002_team_metric_if_missing(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
) -> list[str]:
    if re.search(r"\b8\s+to\s+28\b", " ".join(sentences), re.I):
        return sentences
    allowed = {
        str(f.get("fact_id") or "").strip()
        for f in selected_facts or []
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    if "fact_exec_002" not in allowed:
        return sentences
    team = (
        "In parallel, the ML engineering organization grew from 8 to 28 specialists, "
        "including senior engineers and platform leads."
    )
    out = list(sentences)
    if len(out) >= 6:
        out[5] = team
        return out
    for idx in range(len(out) - 1, -1, -1):
        low = out[idx].lower()
        if "basel iii" in low or "dependency graph" in low:
            continue
        if "directed large-scale regulatory" in low:
            continue
        out[idx] = team
        return out
    return out


def _soften_consulting_fact_echo(sentences: list[str]) -> list[str]:
    out = list(sentences)
    for idx, sent in enumerate(out):
        low = sent.lower().strip()
        if low.startswith("directed large-scale regulatory it transformations"):
            out[idx] = (
                "Against that delivery foundation, directed large-scale regulatory IT "
                "transformations and legacy-modernization programs for major financial "
                "institutions across risk, compliance, data, cloud, and architecture domains."
            )
            break
    return out


def _selected_fact_authority_ids(
    selected_facts: list[dict[str, Any]] | None,
) -> set[str]:
    """Expand graph-root plan rows to their sealed leaf/source authority IDs."""
    ids: set[str] = set()
    for fact in selected_facts or []:
        if not isinstance(fact, dict):
            continue
        for value in (
            fact.get("fact_id"),
            fact.get("candidate_fact_id"),
            *list(fact.get("linked_identity_fact_ids") or []),
            *list(fact.get("linked_source_fact_ids") or []),
            *list(fact.get("allowed_graph_evidence_ids") or []),
            *list(fact.get("graph_skill_node_ids") or []),
            *list(fact.get("metric_outcome_ids") or []),
        ):
            text = str(value or "").strip()
            if text:
                ids.add(text)
    return ids


def _ensure_dependency_graph_display_override(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
    cited_fact_ids: set[str] | None = None,
) -> list[str]:
    """Allow natural synthesis for fact_engineering_platform_002 without forced canned override."""
    return sentences


def _weave_agentic_platform_body_bridge(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
) -> list[str]:
    """Bridge thesis platform claim into S1 without bloating the graph DISPLAY_OVERRIDE sentence."""
    allowed = {
        str(f.get("fact_id") or "").strip()
        for f in selected_facts or []
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    if "fact_engineering_platform_001" not in allowed or not sentences:
        return sentences
    out = list(sentences)
    sent = out[0]
    low = sent.lower()
    if "governed ai platforms" in low and "agentic" not in low:
        out[0] = sent.replace("governed AI platforms", "a governed agentic AI platform", 1)
    return out


def _repair_ai_partnership_judge_findings(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
) -> list[str]:
    """Repair live AI-partnership judge findings without relaxing the X1D panel.

    The failure shape is specific: S4 repeats cloud-modernization phrasing while its
    ledger cites agentic-platform/distributed-ecosystem facts, and S6 uses cover-letter
    meta narration ("This leadership profile can translate..."). Replace both with
    proof-shaped sentences from the selected graph-era facts.
    """
    if len(sentences) != 6:
        return sentences
    allowed = {
        str(f.get("fact_id") or "").strip()
        for f in selected_facts or []
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    has_platform_evidence = {
        "reb_unify_agentic_platform_architecture",
        "reb_unify_distributed_ecosystem_engineering",
    } <= allowed
    has_partner_evidence = bool(
        {
            "reb_unify_partner_channel_cosell",
            "reb_ibm_aws_alliance_partner_cosell_gtm",
        }
        & allowed
    )
    has_ibm_alliance_evidence = "reb_ibm_aws_alliance_partner_cosell_gtm" in allowed
    has_devsecops_evidence = "reb_ibm_devsecops_release_resilience" in allowed
    has_commercialization_evidence = (
        "reb_unify_platform_commercialization_leadership" in allowed
    )
    out = list(sentences)
    # The final whole-resume judge found a real readability failure in this
    # otherwise grounded shape: six sentences repeated internal execution and
    # proof-lineage vocabulary, hid the commercial outcome, and used the
    # indirect phrase "the leader."  Keep each existing sentence slot and its
    # source lineage, but replace only that verified surface pattern with six
    # concise, evidence-bound résumé sentences.
    if (
        {
            "reb_ibm_devsecops_release_resilience",
            "reb_unify_agentic_platform_architecture",
            "reb_unify_platform_commercialization_leadership",
        }
        <= allowed
        and any(
            marker in " ".join(out).lower()
            for marker in ("proof-bundle lineage", "execution surface", "gate-verdict")
        )
    ):
        compacted = list(_AI_PARTNERSHIP_COHERENCE_COMPACTION)
        if not has_partner_evidence:
            compacted[4] = compacted[4].replace(
                "into partner ecosystems.",
                "across regulated enterprise programs.",
            )
        s5_has_22m = len(out) > 4 and bool(re.search(r"\$22m", out[4], re.I))
        s6_has_22m = len(out) > 5 and bool(re.search(r"\$22m", out[5], re.I))
        if s5_has_22m and not s6_has_22m:
            compacted[4], compacted[5] = compacted[5], compacted[4]
        if "automated release pipelines and devsecops scanning" in " ".join(out).lower():
            compacted[0] = (
                "From that commercial base, embedding automated release pipelines and "
                "DevSecOps scanning into modernization delivery paths gave platform teams "
                "a repeatable deployment blueprint."
            )
        return compacted
    if (
        has_ibm_alliance_evidence
        and has_commercialization_evidence
        and "who leads ibm-aws alliance" in out[0].lower()
    ):
        out[0] = _AI_PARTNERSHIP_PAST_TENSE_S1
    if (
        has_ibm_alliance_evidence
        and out[1].lower().startswith("from that alliance base")
    ):
        out[1] = _AI_PARTNERSHIP_DISTINCT_S2
    if "reb_unify_agentic_platform_architecture" in allowed:
        from apps_rg.runtime.sections.executive_summary_composition import (
            is_mechanism_inventory_sentence,
        )

        is_inventory, _ = is_mechanism_inventory_sentence(out[1])
        if is_inventory:
            # This selected root authorizes the platform-control claim, but a
            # live variation expanded it into a routing/policy catalog. Keep
            # the executive brushstroke while eliminating the mechanism list.
            out[1] = _AI_PARTNERSHIP_PLATFORM_CONTROL_S2
    if (
        has_partner_evidence
        and "dependency graph intelligence" in out[2].lower()
        and "partner-platform" not in out[2].lower()
        # The DISPLAY_OVERRIDE sentence is canonical authority and must remain
        # byte-for-byte materialized.  Prefixing it lowercased its first token
        # and made the later exact override contract fail (Retry10 replay).
        and _GRAPH_OVERRIDE_ANCHOR not in out[2].lower()
    ):
        out[2] = f"Within that partner-platform model, {out[2][:1].lower()}{out[2][1:]}"
    if has_platform_evidence and _AI_PARTNERSHIP_S4_REPEAT_RE.search(out[3]):
        out[3] = _AI_PARTNERSHIP_S4_SENTENCE
    if has_partner_evidence and (
        _AI_PARTNERSHIP_META_S6_RE.search(out[5])
        or "partner-led applied ai architecture" in out[5].lower()
    ):
        out[5] = _AI_PARTNERSHIP_S6_SENTENCE
    if (
        has_devsecops_evidence
        and out[4].lower().count(" through ") >= 2
        and "secure delivery" in out[4].lower()
    ):
        out[4] = _AI_PARTNERSHIP_DEVSECOPS_S5
    if (
        has_partner_evidence
        and has_devsecops_evidence
        and has_commercialization_evidence
        and out[5].lower().startswith("future partner-led platform decisions")
    ):
        out[5] = _AI_PARTNERSHIP_EVIDENCE_LED_S6
    from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import repair_legacy_regulated_partnership_arc
    return repair_legacy_regulated_partnership_arc(
        out, allowed=allowed, has_partner_evidence=has_partner_evidence,
        has_devsecops_evidence=has_devsecops_evidence, has_platform_evidence=has_platform_evidence,
    )


def _reduce_formulaic_bridge_echo(sentences: list[str]) -> list[str]:
    """Lower stock-bridge density without touching facts or metric anchors.

    x2_exec_summary_stock_bridge_max_two caps stock-bridge openers in S2–S5 at 2. When
    PROVIDER_MODEL + canonical sentence injection collectively exceed that cap, rewrite the latest
    stock-bridge S2–S5 opener to a non-stock alternative.
    """
    out = list(sentences)
    for idx, sent in enumerate(out):
        low = sent.lower()
        # "Through that operating model, Basel…" → "Applied across enterprise programs, Basel…"
        if low.startswith("through that operating model") and "basel" in low:
            out[idx] = re.sub(
                r"^Through that operating model,\s*",
                "Applied across enterprise programs, ",
                sent,
                count=1,
                flags=re.IGNORECASE,
            )

    # Count stock-bridge openers across S2–S5 (indices 1..4 when 6 sentences present)
    body_idxs = [i for i in range(1, min(5, len(out)))]
    bridge_hits: list[int] = []
    for i in body_idxs:
        low = out[i].lower().lstrip()
        if any(low.startswith(b) for b in _STOCK_BRIDGE_OPENERS):
            bridge_hits.append(i)
    # If 3+ stock bridges, rewrite later ones to non-stock alternatives.
    if len(bridge_hits) >= 3:
        non_stock_alternatives = (
            "In parallel,",
            "Commercially,",
        )
        for offset, i in enumerate(bridge_hits[2:]):
            alt = non_stock_alternatives[offset % len(non_stock_alternatives)]
            sent = out[i]
            # Strip whatever stock opener exists (up to first comma) and prepend alt.
            stripped = _STOCK_BRIDGE_PREFIX_RE.sub("", sent, count=1)
            if stripped and stripped != sent:
                # Capitalize first letter of remaining sentence if not already.
                first = stripped[:1]
                rest = stripped[1:]
                if first.isalpha() and first.islower():
                    stripped = first.lower() + rest
                out[i] = f"{alt} {stripped}"
    return out


def _enforce_required_fact_slots(
    sentences: list[str],
    *,
    selected_facts: list[dict[str, Any]] | None,
) -> list[str]:
    """Single-pass: guarantee every non-waived allowed fact is cited in the display.

    Replaces all the individual _ensure_X_in_display functions that fought each other.
    Iterates over missing facts in canonical-slot order and fills the best available
    slot without displacing another still-uncovered required fact.
    """
    from apps_rg.runtime.validators.executive_summary_x2 import (
        collect_cited_source_fact_ids,
        resolve_utilization_waived_fact_ids,
    )

    if len(sentences) != 6:
        return sentences

    allowed = {
        str(f.get("fact_id") or "").strip()
        for f in selected_facts or []
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    waived = resolve_utilization_waived_fact_ids(allowed)
    required = allowed - waived

    def _cited(sents: list[str]) -> set[str]:
        ledger = [
            {"claim_text": s, "source_fact_ids": _p("_source_fact_ids_for_display_sentence", _source_fact_ids_for_display_sentence)(s)}
            for s in sents
        ]
        return collect_cited_source_fact_ids(ledger)

    # Iterate in canonical slot order so each fact gets its preferred slot first.
    facts_by_slot = sorted(
        (fid for fid in required if fid in _CANONICAL_FACT_SLOT),
        key=lambda f: _CANONICAL_FACT_SLOT[f],
    )
    # Facts without a canonical slot go last.
    unslotted = [fid for fid in sorted(required) if fid not in _CANONICAL_FACT_SLOT]

    out = list(sentences)
    for fid in facts_by_slot + unslotted:
        if fid in _cited(out):
            continue
        canon = _CANONICAL_DISPLAY_SENTENCES.get(fid)
        if not canon:
            continue

        preferred_slot = _CANONICAL_FACT_SLOT.get(fid)
        # Build candidate replacement slots: preferred first, then non-required slots, then any.
        candidate_slots: list[int] = []
        if preferred_slot is not None and preferred_slot > 0:
            candidate_slots.append(preferred_slot)
        for idx in range(1, len(out)):
            if idx not in candidate_slots:
                if not (set(_p("_source_fact_ids_for_display_sentence", _source_fact_ids_for_display_sentence)(out[idx])) & required):
                    candidate_slots.append(idx)
        for idx in range(len(out) - 1, 0, -1):
            if idx not in candidate_slots:
                candidate_slots.append(idx)

        for slot in candidate_slots:
            displaced = set(_p("_source_fact_ids_for_display_sentence", _source_fact_ids_for_display_sentence)(out[slot])) & required
            if displaced:
                # Only safe to displace if those facts are covered by other slots.
                covered = all(
                    any(
                        f in set(_p("_source_fact_ids_for_display_sentence", _source_fact_ids_for_display_sentence)(out[i]))
                        for i in range(len(out))
                        if i != slot
                    )
                    for f in displaced
                )
                if not covered:
                    continue
            out[slot] = canon
            break

    return out
