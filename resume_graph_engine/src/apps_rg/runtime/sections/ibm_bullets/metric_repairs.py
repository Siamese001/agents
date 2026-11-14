"""IBM metric canonicalization, foreign/hold scrubbing, and proof-packet alignment."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    HOLD_METRIC_TEXT_RE,
    IBM_FOREIGN_METRIC_SCRUB_RE,
)
from .frozen_allocation import _normalize_fact_id_list
from .lane_constants import sha16

_IBM_FOREIGN_METRIC_SCRUB_RE = IBM_FOREIGN_METRIC_SCRUB_RE
_HOLD_METRIC_TEXT_RE = HOLD_METRIC_TEXT_RE

IBM_LOCKED_METRIC_CANONICAL: dict[str, str] = {
    "bul_ibm_004": "20%",
    "bul_ibm_002": "weeks to hours",
    "bul_ibm_005": "20%",
}

def _scrub_foreign_ibm_metric_tokens(text: str, own_root: str) -> str:
    """Remove locked IBM metric tokens owned by other bullets (granularity gate hygiene)."""
    from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_METRIC_ANCHOR_RULES

    out = str(text or "")
    for needles, root in IBM_METRIC_ANCHOR_RULES:
        if root == own_root:
            continue
        if {root, own_root} <= {"bul_ibm_004", "bul_ibm_005"} and any("20%" in n for n in needles):
            continue
        for needle in needles:
            out = re.sub(re.escape(needle), "", out, flags=re.IGNORECASE)
    for pat in _IBM_FOREIGN_METRIC_SCRUB_RE:
        out = pat.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([,.])", r"\1", out)
    return out.strip(" ,.")


def inject_ibm_locked_metric_anchors(
    parsed: dict[str, Any],
    *,
    plan_facts: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> None:
    """Inject locked IBM metric tokens per ``IBM_METRIC_ANCHOR_RULES`` when model output omits them.

    Only stable graph-approved visible metrics are eligible for deterministic insertion.
    If the active plan fact carries a different metric, the plan metric wins; if it
    carries no metric, this helper does not fabricate one.
    """
    from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_METRIC_ANCHOR_RULES
    from apps_rg.runtime.validators.bullet_line_discipline_x2 import DEFAULT_BULLET_MAX_CHARS

    def _append_metric_clause(base_text: str, clause_core: str) -> str:
        """Inject the metric as an IN-SENTENCE clause (W5, apps-rg-aig-remaining-lanes-closeout-d4e1f7).

        The previous ``"{base}. Delivered {token} at enterprise scale."`` style appended a SECOND
        sentence, deterministically failing ``x2_ibm_bullet_single_thought`` (and often the
        320-char paragraph cap) on every injected bullet. Convert the trailing terminator to a
        comma clause instead, with a shorter fallback when the long clause would break the cap.
        """
        base = (base_text or "").rstrip().rstrip(".!?").rstrip()
        if not base:
            return f"Delivered {clause_core} at enterprise scale."
        long_form = f"{base}, delivering {clause_core} at enterprise scale."
        if len(long_form) <= DEFAULT_BULLET_MAX_CHARS:
            return long_form
        return f"{base}, delivering {clause_core}."

    bullets = list(parsed.get("bullets") or [])
    if not bullets:
        return
    plan_by_bid = {str(f.get("fact_id") or "").strip(): f for f in plan_facts or [] if isinstance(f, dict)}
    changelog = parsed.setdefault("change_log", [])
    if not isinstance(changelog, list):
        changelog = []
        parsed["change_log"] = changelog
    repaired_any = False
    for needles, root in IBM_METRIC_ANCHOR_RULES:
        bullet = next((b for b in bullets if str(b.get("bullet_id")) == root), None)
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("bullet_text") or "").strip()
        tl = text.lower()
        token = IBM_LOCKED_METRIC_CANONICAL[root]
        has_own = any(n.lower() in tl for n in needles)
        foreign = any(
            n.lower() in tl
            for other_needles, other_root in IBM_METRIC_ANCHOR_RULES
            if other_root != root
            for n in other_needles
        )
        if has_own and not foreign:
            continue

        plan_fact = plan_by_bid.get(root) or {}
        plan_metric = str(plan_fact.get("metric_raw") or "").strip()
        plan_has_metric = bool(plan_fact.get("has_metric") or plan_metric)
        canonical_aligns_with_plan = plan_metric and any(
            n.lower() in plan_metric.lower() for n in needles
        )

        if plan_fact and not canonical_aligns_with_plan:
            # Graph-selector reassigned this slot to a fact with its own metric.
            #   (a) plan_metric exists but conflicts with canonical -> surface the PLAN fact's
            #       own metric token (it is genuinely fact-backed) so the bullet owns a metric
            #       anchor without fabricating the canonical figure. This closes the case where
            #       the model omitted its own approved graph metric and
            #       x2_ibm_metric_anchor_bullet_ownership fails for *_missing_metric_token.
            #   (b) plan_metric is empty/has_metric is false -> the graph fact has no metric to
            #       claim; forcing any metric token would fabricate an unsupported claim, so skip.
            plan_token = _plan_metric_display_token(plan_metric)
            already_has_plan_metric = bool(plan_token) and plan_token.lower() in tl
            if plan_has_metric and plan_token and not already_has_plan_metric:
                cleaned = _scrub_foreign_ibm_metric_tokens(text, root)
                base_text = cleaned or text
                bullet["bullet_text"] = _append_metric_clause(base_text, plan_token)
                bullet["has_metric"] = True
                bullet["metric_raw"] = plan_metric
                src = list(bullet.get("source_fact_ids") or [])
                if root not in src:
                    src.insert(0, root)
                bullet["source_fact_ids"] = src
                repaired_any = True
                changelog.append(
                    {
                        "operation": "inject_ibm_plan_fact_metric",
                        "reason": f"surface_plan_metric:{root}:{plan_token}",
                    }
                )
                continue
            reason_detail = (
                f"plan_fact_metric_does_not_match_canonical:{root} "
                f"(canonical={token}, plan_metric={plan_metric!r}, has_metric={plan_has_metric})"
            )
            changelog.append(
                {
                    "operation": "skip_ibm_locked_metric_anchor",
                    "reason": (
                        f"{reason_detail} \u2014 graph selector chose this fact intentionally; "
                        "do not append canonical-metric suffix"
                    ),
                }
            )
            continue

        cleaned = _scrub_foreign_ibm_metric_tokens(text, root)
        bullet["bullet_text"] = _append_metric_clause(cleaned, f"{token} outcomes")
        bullet["has_metric"] = True
        bullet["metric_raw"] = token
        src = list(bullet.get("source_fact_ids") or [])
        if root not in src:
            src.insert(0, root)
        bullet["source_fact_ids"] = src
        repaired_any = True
        changelog.append(
            {
                "operation": "inject_ibm_locked_metric_anchors",
                "reason": f"inject_metric_token:{root}",
            }
        )
    for f in plan_facts or []:
        if not isinstance(f, dict):
            continue
        bid = str(f.get("fact_id") or "").strip()
        if not bid or any(bid == r for _, r in IBM_METRIC_ANCHOR_RULES):
            continue
        plan_metric = str(f.get("metric_raw") or "").strip()
        if not plan_metric:
            continue
        plan_token = _plan_metric_display_token(plan_metric)
        if not plan_token:
            continue
        bullet = next((b for b in bullets if str(b.get("bullet_id")) == bid), None)
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("bullet_text") or "").strip()
        tl = text.lower()
        if plan_token.lower() in tl:
            continue
        cleaned = _scrub_foreign_ibm_metric_tokens(text, bid)
        base_text = cleaned or text
        bullet["bullet_text"] = _append_metric_clause(base_text, plan_token)
        bullet["has_metric"] = True
        bullet["metric_raw"] = plan_metric
        src = list(bullet.get("source_fact_ids") or [])
        if bid not in src:
            src.insert(0, bid)
        bullet["source_fact_ids"] = src
        repaired_any = True
        changelog.append(
            {
                "operation": "inject_ibm_plan_fact_metric",
                "reason": f"surface_plan_metric:{bid}:{plan_token}",
            }
        )
    if repaired_any:
        align_ibm_claim_ledger_from_canonical_facts(
            parsed,
            plan_facts=plan_facts,
            allowed_fact_ids=allowed_fact_ids,
        )


def demote_gated_ibm_metrics(parsed: dict[str, Any]) -> None:
    """Demote metric IDs that are not approved by the IBM graph allow-list."""
    if not isinstance(parsed, dict):
        return
    changelog = parsed.get("change_log")
    if not isinstance(changelog, list):
        return
    from apps_rg.runtime.sections.ibm_role_episode_evidence import PROMOTABLE_METRIC_OUTCOME_IDS

    allowed = set(PROMOTABLE_METRIC_OUTCOME_IDS)
    demoted_bullet_ids: set[str] = set()
    for entry in changelog:
        if not isinstance(entry, dict):
            continue
        ids = [str(x) for x in (entry.get("metric_outcome_ids") or [])]
        approved_ids = [x for x in ids if x in allowed]
        rejected_ids = [x for x in ids if x not in allowed and x.startswith("metric_ibm_")]
        if rejected_ids:
            bid = str(entry.get("bullet_id") or "").strip()
            if bid and not approved_ids:
                demoted_bullet_ids.add(bid)
            entry["metric_outcome_ids"] = approved_ids
            entry.setdefault("change_notes", [])
            if isinstance(entry["change_notes"], list):
                entry["change_notes"].append("demoted_unapproved_ibm_metric_to_qualitative")
    if not demoted_bullet_ids:
        return
    for bullet in parsed.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        if str(bullet.get("bullet_id") or "").strip() not in demoted_bullet_ids:
            continue
        bullet["metric_raw"] = ""
        bullet["has_metric"] = False


def demote_hold_metrics(parsed: dict[str, Any]) -> None:
    """Strip HOLD/DO_NOT_PROMOTE figures (25/30/35/40%, $15M, $30M) to qualitative prose.

    W5 (plan apps-rg-aig-remaining-lanes-closeout-d4e1f7): sibling of
    ``demote_gated_ibm_metrics`` — the PA forbids these figures, but when a generation path
    still surfaces one, this deterministic backstop removes the unpromotable figure so the
    bullet reads qualitatively. Graph-approved IBM metrics are never touched.
    """
    if not isinstance(parsed, dict):
        return
    from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

    for bullet in parsed.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("bullet_text") or "")
        if not _HOLD_METRIC_TEXT_RE.search(text):
            continue
        # Sentence-aware demotion: when the bullet has multiple sentences, DROP the sentence
        # carrying the HOLD figure (also restores single-thought shape); when it is the only
        # sentence, strip just the figure in place.
        sentences = split_sentences(text)
        if len(sentences) > 1:
            kept = [s for s in sentences if not _HOLD_METRIC_TEXT_RE.search(s)]
            new_text = " ".join(kept).strip() if kept else _HOLD_METRIC_TEXT_RE.sub("", text)
        else:
            new_text = _HOLD_METRIC_TEXT_RE.sub("", text)
        new_text = re.sub(r"\s{2,}", " ", new_text).replace(" ,", ",").replace(" .", ".").strip()
        if new_text and not new_text.rstrip().endswith((".", "!", "?")):
            new_text = new_text.rstrip() + "."
        bullet["bullet_text"] = new_text
        mr = str(bullet.get("metric_raw") or "")
        if _HOLD_METRIC_TEXT_RE.search(mr):
            bullet["metric_raw"] = ""
            bullet["has_metric"] = bool(re.search(r"[\$\d]", new_text))


def scrub_cross_slot_plan_metrics(parsed: dict[str, Any], plan_facts: list[dict[str, Any]]) -> None:
    """Remove a slot's plan-fact metric token from every OTHER slot's bullet text.

    W4-residual (plan apps-rg-aig-remaining-lanes-closeout-d4e1f7): the gemini X1D judge
    decisive-failed ibm_bullets because a bullet carried ANOTHER slot's metric. The canonical-anchor scrub
    only covers IBM_METRIC_ANCHOR_RULES tokens; plan-fact metrics (graph-selected) were not
    scrubbed cross-slot. A metric claim not supported by the slot's own source fact is
    unsupported by construction — remove it deterministically.
    """
    if not isinstance(parsed, dict):
        return
    tokens_by_root: dict[str, str] = {}
    for f in plan_facts or []:
        if not isinstance(f, dict):
            continue
        tok = _plan_metric_display_token(str(f.get("metric_raw") or ""))
        if tok:
            tokens_by_root[str(f.get("fact_id") or "").strip()] = tok
    if not tokens_by_root:
        return
    for bullet in parsed.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        own = str(bullet.get("bullet_id") or "").strip()
        text = str(bullet.get("bullet_text") or "")
        changed = False
        for root, tok in tokens_by_root.items():
            if root == own or not tok or tok.lower() not in text.lower():
                continue
            # Clause-aware removal: strip the token plus its dangling verb/prepositional shell.
            clause = re.compile(
                r"(?:,?\s*(?:and\s+)?(?:generating|delivering|driving|producing|securing|adding)\s+)?"
                + re.escape(tok)
                + r"(?:\s+(?:in|of)\s+[A-Za-z -]{0,40}?)?(?=$|[,.;)])",
                re.IGNORECASE,
            )
            new = clause.sub("", text)
            text = new if new != text else re.sub(re.escape(tok), "", text, flags=re.IGNORECASE)
            changed = True
            if str(bullet.get("metric_raw") or "").strip().lower().startswith(tok.lower()):
                bullet["metric_raw"] = ""
                bullet["has_metric"] = False
        if changed:
            text = re.sub(r"\s{2,}", " ", text)
            text = re.sub(r"\s+([,.])", r"\1", text).strip().strip(",")
            if text and not text.rstrip().endswith((".", "!", "?")):
                text = text.rstrip() + "."
            bullet["bullet_text"] = text


def _plan_metric_display_token(plan_metric: str) -> str:
    """Extract a single display-case numeric token from a plan fact's metric_raw.

    Mirrors the X2 gate's accepted-chunk regex (``[\\$\\d][\\$\\d.,%a-z-]*``) so the injected token
    is recognized by ``x2_ibm_metric_anchor_bullet_ownership``. Returns the first numeric/currency
    token from the first ``|``-delimited metric segment. Empty when no numeric token is present.
    """
    seg = str(plan_metric or "").split("|")[0].strip()
    if "weeks to hours" in seg.lower():
        return "weeks to hours"
    m = re.search(r"[\$\d][\$\d.,%]*[A-Za-z%]?", seg)
    return m.group(0).strip() if m else ""


def repair_ibm_bullet_metric_anchors_from_plan(
    parsed: dict[str, Any],
    *,
    plan_facts: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> None:
    """Compat alias — deterministic metric injection supersedes plan-paste repair."""
    inject_ibm_locked_metric_anchors(
        parsed,
        plan_facts=plan_facts,
        allowed_fact_ids=allowed_fact_ids,
    )


def align_ibm_claim_ledger_from_canonical_facts(
    parsed: dict[str, Any],
    *,
    plan_facts: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> None:
    """Map claim_ledger source_fact_ids onto graph-plan bul_ibm_* + metric ids (no base-resume paste)."""
    by_bid = {str(f.get("fact_id")): f for f in plan_facts if f.get("fact_id")}
    allowed = set(allowed_fact_ids)
    ledger: list[dict[str, Any]] = []
    for bullet in parsed.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        bid = str(bullet.get("bullet_id") or "")
        plan_row = by_bid.get(bid) or {}
        text = str(bullet.get("bullet_text") or plan_row.get("claim_text") or "").strip()
        if not text:
            continue
        src = _normalize_fact_id_list(bullet.get("source_fact_ids") or [bid])
        if bid not in src:
            src.insert(0, bid)
        metric_raw = str(plan_row.get("metric_raw") or bullet.get("metric_raw") or "")
        if metric_raw:
            mid = f"{bid}_metric_{sha16(metric_raw)[:8]}"
            if mid in allowed and mid not in src:
                src.append(mid)
        src = [s for s in src if str(s).startswith("bul_ibm_")]
        if bid not in src:
            src.insert(0, bid)
        ledger.append({"claim_text": text, "source_fact_ids": src})
    if ledger:
        parsed["claim_ledger"] = ledger


def build_ibm_bullets_allowed_fact_packet(
    *,
    ibm_facts: list[dict[str, Any]],
    ibm_header: dict[str, Any],
    proof_pool_ref: str,
    proof_pool_digest: str,
    approved_metric_evidence: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Primary evidence slice for X1D judges (fixes null allowed_fact_packet on base-resume pool).

    ``approved_metric_evidence`` surfaces approved, promotable, section-eligible
    metric_outcome nodes so the X1D grader can support a bullet's graph-approved metric
    claim (e.g. the alliance "20% joint revenue growth") even when the per-bundle metric
    was capped out of the proof-pool contribution by section display budgeting — without
    changing selection, the X2 allowed-fact scope, or generation.
    """
    packet: list[dict[str, Any]] = []
    for row in ibm_facts:
        if isinstance(row, dict):
            packet.append(dict(row))
    for row in approved_metric_evidence or []:
        if isinstance(row, dict):
            packet.append(dict(row))
    if isinstance(ibm_header, dict) and ibm_header:
        packet.append(
            {
                "fact_id": str(ibm_header.get("fact_id") or "exp_ibm_001"),
                "kind": "employment_header",
                "employer": ibm_header.get("employer"),
                "title": ibm_header.get("title"),
                "location": ibm_header.get("location"),
                "start_date": ibm_header.get("start_date"),
                "end_date": ibm_header.get("end_date"),
            },
        )
    if proof_pool_ref:
        packet.append(
            {
                "fact_id": "__proof_pool_anchor__",
                "kind": "proof_pool_anchor",
                "proof_pool_ref": proof_pool_ref.replace("\\", "/"),
                "proof_pool_digest": proof_pool_digest,
            },
        )
    return packet
