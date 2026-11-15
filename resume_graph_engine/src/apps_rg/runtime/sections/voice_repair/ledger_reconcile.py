"""Claim ledger reconciliation and allowed-pool orphan citation stripping."""
from __future__ import annotations

from typing import Any

from .filler_and_meta import repair_generic_filler_prose
from .parent_proxy import _p

def reconcile_claim_ledger_after_voice_repair(parsed: dict[str, Any]) -> dict[str, Any]:
    """Keep claim_ledger aligned with repaired display text (materialized_or_gap gate)."""
    from apps_rg.runtime.validators.executive_summary_x2 import (
        _ledger_claim_tokens,
        ledger_row_materialized_in_display,
        split_sentences,
    )

    out = dict(parsed)
    text = str(out.get("resume_display_text") or "")
    ledger = [dict(r) for r in (out.get("claim_ledger") or []) if isinstance(r, dict)]
    if not ledger or not text:
        return out
    sentences = split_sentences(text)
    gaps = list(out.get("gap_notes") or [])
    for i, row in enumerate(ledger):
        if ledger_row_materialized_in_display(row, text):
            continue
        prior = str(row.get("claim_text") or "")
        tokens = _ledger_claim_tokens(prior)
        best_sent: str | None = None
        best_hits = 0
        for sent in sentences:
            sl = sent.lower()
            hits = sum(1 for t in tokens if t in sl)
            if hits > best_hits:
                best_hits = hits
                best_sent = sent
        if best_sent and best_hits >= max(1, min(3, len(tokens))):
            row["claim_text"] = best_sent.strip()
            ledger[i] = row
            continue
        sids = [str(s) for s in (row.get("source_fact_ids") or []) if str(s).strip()]
        gaps.append(
            "voice_repair_drift: claim idx="
            f"{i} source_fact_ids={','.join(sids)} not materialized after display repair"
        )
    out["claim_ledger"] = ledger
    if gaps:
        out["gap_notes"] = gaps
    return out


def _strip_claim_ledger_source_fact_ids_not_in_allowed_pool(
    parsed: dict[str, Any],
    *,
    allowed_fact_ids: set[str] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Drop orphan source_fact_ids that are outside the active allowlist."""
    out = dict(parsed)
    allowed = {str(x).strip() for x in (allowed_fact_ids or []) if str(x).strip()}
    if not allowed:
        return out, []

    raw_ledger = list(out.get("claim_ledger") or [])
    ledger = [dict(r) for r in raw_ledger if isinstance(r, dict)]
    if not ledger:
        return out, []

    stripped: list[str] = []
    filtered: list[Any] = []
    for row in raw_ledger:
        if not isinstance(row, dict):
            filtered.append(row)
            continue
        raw_ids = [str(x).strip() for x in (row.get("source_fact_ids") or []) if str(x).strip()]
        kept = [x for x in raw_ids if x in allowed or x.split("_metric_", 1)[0] in allowed]
        if kept != raw_ids:
            stripped.extend(x for x in raw_ids if x not in kept)
        row["source_fact_ids"] = kept
        filtered.append(row)

    if stripped:
        out["claim_ledger"] = filtered
    return out, sorted(set(stripped))


def apply_voice_repair_to_parsed(
    parsed: dict[str, Any],
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply filler repair to ``resume_display_text`` in-place copy of parsed output."""
    out = dict(parsed)
    text, receipt = _p("repair_generic_filler_prose", repair_generic_filler_prose)(
        str(out.get("resume_display_text") or ""),
        selected_facts=selected_facts,
    )
    out["resume_display_text"] = text
    if receipt.get("repaired"):
        out = _p("reconcile_claim_ledger_after_voice_repair", reconcile_claim_ledger_after_voice_repair)(out)
        receipt["claim_ledger_reconciled"] = True
    return out, receipt
