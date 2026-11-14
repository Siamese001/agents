"""Credential-dump, target-tailoring, shape validation, and orphan-fact repairs."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    CITATION_REPAIR_STOPWORDS as _CITATION_REPAIR_STOPWORDS,
    SOURCE_FACT_TOKEN_STOPWORDS as _SOURCE_FACT_TOKEN_STOPWORDS,
    TOKEN_RE as _TOKEN_RE,
    citation_repair_tokens as _citation_repair_tokens,
)
from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

def _sentence_fails_credential_dump(sentence: str) -> bool:
    from apps_rg.runtime.sections.competencies_certification_contract import (
        is_credential_competency_term,
    )

    markers = (
        "aws certified",
        "databricks",
        "fellow of the society of actuaries",
        "society of actuaries",
        "fsa",
        "basel iii",
        "ccar",
        "certified solutions architect",
        "lakehouse fundamentals",
    )
    low = sentence.lower()
    hits = sum(1 for m in markers if m in low)
    if hits >= 3:
        return True
    if is_credential_competency_term(sentence) and hits >= 2:
        return True
    if re.search(r"\bcredentials?\s+reinforce\b", low) and hits >= 2:
        return True
    return False


def strip_target_company_tailoring_sentences(
    resume_display_text: str,
    target_company: str,
) -> tuple[str, list[str]]:
    """Remove sentences that name TARGET_COMPANY as employer/alignment (x2_target_company_as_experience_zero)."""
    company = str(target_company or "").strip()
    if not company:
        return resume_display_text, []
    co_pat = re.escape(company)
    employer_hit = re.compile(rf"\b(?:at|for|with)\s+{co_pat}\b", re.IGNORECASE)
    align_hit = re.compile(rf"align\s+with\s+{co_pat}\b", re.IGNORECASE)
    sents = split_sentences(str(resume_display_text or "").strip())
    if not sents:
        return resume_display_text, []
    kept: list[str] = []
    removed: list[str] = []
    for sent in sents:
        if employer_hit.search(sent) or align_hit.search(sent):
            removed.append(sent[:120])
        else:
            kept.append(sent)
    if not kept or len(kept) == len(sents):
        return resume_display_text, removed
    return " ".join(kept).strip(), removed


def strip_exec_summary_credential_dump_sentences(resume_display_text: str) -> tuple[str, list[str]]:
    """Remove credential-inventory sentences so x2_exec_summary_no_credential_dump can pass."""
    sents = split_sentences(str(resume_display_text or "").strip())
    if not sents:
        return resume_display_text, []
    kept: list[str] = []
    removed: list[str] = []
    for sent in sents:
        if _sentence_fails_credential_dump(sent):
            removed.append(sent[:120])
        else:
            kept.append(sent)
    if not kept:
        return resume_display_text, removed
    return " ".join(kept).strip(), removed


def _exec_summary_shape_ok(resume_display_text: str, parsed: dict[str, Any]) -> tuple[bool, str]:
    from apps_rg.runtime.validators.executive_summary_x2 import (
        check_exec_summary_meta_filler_patterns,
        check_exec_summary_no_credential_dump,
        check_exec_summary_no_mechanism_inventory,
        check_exec_summary_paragraph_max_words,
        check_exec_summary_sentence_count_6,
    )

    failures: list[str] = []
    bounds_ok, bounds_reason = check_exec_summary_paragraph_max_words(resume_display_text, parsed)
    if not bounds_ok and bounds_reason:
        failures.append(bounds_reason)
    meta_ok, meta_reason = check_exec_summary_meta_filler_patterns(resume_display_text)
    if not meta_ok and meta_reason:
        failures.append(meta_reason)
    cred_ok, cred_reason = check_exec_summary_no_credential_dump(resume_display_text)
    if not cred_ok and cred_reason:
        failures.append(cred_reason)
    mech_ok, mech_reason = check_exec_summary_no_mechanism_inventory(
        resume_display_text,
        parsed,
    )
    if not mech_ok and mech_reason:
        failures.append(mech_reason)
    sent_ok, sent_reason = check_exec_summary_sentence_count_6(resume_display_text)
    if not sent_ok and sent_reason:
        failures.append(sent_reason)
    if failures:
        return False, "; ".join(failures)
    return True, ""


def _first_sentence_of_claim(claim_text: str) -> str:
    """Return the first display sentence of a fact claim, normalized to one period-terminated unit."""
    raw = str(claim_text or "").strip()
    if not raw:
        return ""
    sents = [s for s in split_sentences(raw) if str(s).strip()]
    out = sents[0].strip() if sents else raw
    if out and not out.rstrip().endswith((".", "!", "?")):
        out = out.rstrip() + "."
    return out


def _fact_support_text(fact: dict[str, Any]) -> str:
    parts = [
        str(fact.get("claim_text") or ""),
        str(fact.get("achievement_summary") or ""),
        str(fact.get("domain") or ""),
        str(fact.get("fact_id") or "").replace("_", " "),
    ]
    for value in fact.get("metric_values") or []:
        parts.append(str(value or ""))
    return " ".join(parts)


def repair_exec_summary_orphan_rows_with_unused_required_facts(
    parsed: dict[str, Any],
    *,
    allowed_fact_ids: set[str],
    plan_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace orphan ledger-row sentences with unused required-fact claims (in place).

    Closes the dominant executive_summary X3_BLOCK cascade on non-strategy lanes where the model
    emits a generic, uncited bridge sentence (e.g. "That foundation informs data governance and AI
    strategy at scale") while leaving a required allowed fact (e.g. fact_engineering_platform_006,
    the $22M IP-led revenue / 20% margin / team 8->28 platform-commercialization fact) unused. One
    honest repair simultaneously:
      * fills the orphan row's ``source_fact_ids`` (clears orphan/coverage/unsupported gates),
      * lengthens the under-length bridge sentence (clears evidence_utilization), and
      * materializes the unused required fact (clears allowed_fact_utilization).
    No fabricated content: the replacement sentence is the fact's own ``claim_text``. Returns the
    list of applied repair records (empty when nothing was repairable).
    """
    repairs: list[dict[str, Any]] = []
    if not isinstance(parsed, dict):
        return repairs
    text = str(parsed.get("resume_display_text") or "").strip()
    ledger = parsed.get("claim_ledger")
    if not text or not isinstance(ledger, list) or not ledger:
        return repairs
    sentences = [s for s in split_sentences(text) if str(s).strip()]
    if len(sentences) != len(ledger):
        return repairs  # only repair when rows map 1:1 to sentences

    allowed = {str(x).strip() for x in (allowed_fact_ids or []) if str(x).strip()}
    fact_by_id = {
        str(f.get("fact_id") or "").strip(): f
        for f in (plan_facts or [])
        if isinstance(f, dict) and str(f.get("fact_id") or "").strip()
    }
    cited: set[str] = set()
    for row in ledger:
        if isinstance(row, dict):
            for sid in row.get("source_fact_ids") or []:
                cited.add(str(sid).split("_metric_", 1)[0])
    unused_required = [
        fid for fid in allowed if fid in fact_by_id and fid not in cited
    ]
    eligible_fids = [fid for fid in fact_by_id if fid in allowed]
    if not unused_required and not eligible_fids:
        return repairs

    for idx, row in enumerate(ledger):
        if not isinstance(row, dict):
            continue
        if [str(x) for x in (row.get("source_fact_ids") or []) if str(x).strip()]:
            continue  # row already cited
        if unused_required:
            fid = unused_required.pop(0)
            fact = fact_by_id.get(fid) or {}
            from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import try_preserve_non_orphan_sentence_for_unused_fact
            if try_preserve_non_orphan_sentence_for_unused_fact(
                idx=idx, row=row, fid=fid, fact=fact, sentences=sentences, ledger=ledger,
                eligible_fids=eligible_fids, fact_by_id=fact_by_id,
                tokens_fn=_citation_repair_tokens, support_text_fn=_fact_support_text, repairs=repairs,
            ):
                continue
            replacement = _first_sentence_of_claim(str(fact.get("claim_text") or ""))
            if not replacement:
                continue
            sentences[idx] = replacement
            row["source_fact_ids"] = [fid]
            row["claim"] = replacement
            row["claim_text"] = str(fact.get("claim_text") or replacement)
            repairs.append(
                {
                    "operation": "repair_orphan_row_with_unused_required_fact",
                    "reason": f"orphan_row_{idx + 1}_materialized_fact:{fid}",
                }
            )
        elif eligible_fids:
            from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import bind_orphan_row_to_best_allocated_root
            bind_orphan_row_to_best_allocated_root(
                idx=idx, row=row, sentence=sentences[idx], eligible_fids=eligible_fids,
                fact_by_id=fact_by_id, tokens_fn=_citation_repair_tokens, support_text_fn=_fact_support_text, repairs=repairs,
            )

    if repairs:
        parsed["resume_display_text"] = " ".join(sentences).strip()
        clog = list(parsed.get("change_log") or [])
        clog.extend(repairs)
        parsed["change_log"] = clog
    return repairs
