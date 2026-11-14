"""Fact utilization, brushstroke coverage, and evidence depth checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.validators.exec_summary_x2.constants import (
    ACTION_VERB_OPENERS,
    ALLOWED_MODELS,
    ALLOWED_TOP_LEVEL_FIELDS,
    CREDENTIAL_CONTEXT_MARKERS,
    EM_DASH,
    EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE,
    EVIDENCE_UTIL_MIN_POOL_FOR_LEDGER_DEPTH,
    EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE,
    EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE,
    EXEC_SUMMARY_MECHANICAL_OPENERS,
    EXEC_SUMMARY_ROBOTIC_TRANSITION_PREFIXES,
    EXECUTIVE_SUMMARY_SECTION_ID,
    EXPECTED_PA_SHELL_TEMPLATE_ID,
    EXPECTED_PROMPT_ID,
    EXPECTED_PROMPT_TEMPLATE_REF,
    FIRST_PERSON_PATTERN,
    FSA_RIGOR_MARKERS,
    FSA_WORD_RE,
    GENERIC_FILLER,
    INDUSTRY_DOMAIN_CLAIMS,
    INFERRED_BRIDGE_PHRASES,
    INLINE_SOURCE_PATTERN,
    MECHANICAL_PROOF_OPENERS,
    NORTH_STAR_SIGNATURE_PHRASES,
    POST_X2_REQUIRED_ARTIFACTS,
    POST_X2_X1D_WIRING_GATE_IDS,
    PRE_X2_REQUIRED_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    REQUIRED_JUDGE_PROVIDER_KEYS,
    REQUIRED_JUDGE_PROVIDERS,
    SOURCE_SENSITIVE_PHRASES,
    VENDOR_NAMED_CERT_LABELS,
    X2GateResult,
    _CROSS_SENTENCE_DEDUP_PATTERNS,
    _FINITE_VERB_RE,
    _GRAPH_EVIDENCE_PERCENT_CAPTURE_RE,
    _GRAPH_EVIDENCE_S1_CONNECTOR_PHRASES,
    _GRAPH_EVIDENCE_S1_CONNECTOR_WORDS,
    _GRAPH_EVIDENCE_S1_MECHANISM_TERMS,
    _PARTICIPIAL_OPENER_RE,
    _SUBJECTLESS_VERB_OPENER_RE,
    resolve_section_generation_model,
    split_sentences,
)
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import _source_fact_base_id

def _pool_too_small_excused(parsed_output: dict[str, Any] | None) -> bool:
    if not isinstance(parsed_output, dict):
        return False
    sc = parsed_output.get("self_check")
    if not isinstance(sc, dict):
        return False
    if sc.get("selected_fact_pool_too_small") is not True:
        return False
    return bool(str(sc.get("selected_fact_pool_too_small_reason") or "").strip())


def _is_cert_fact_id_for_utilization(fact_id: str) -> bool:
    """Credential inventory facts are optional in exec summary; omit from utilization pool size."""
    base = str(fact_id or "").strip().split("_metric_", 1)[0]
    return base.startswith("fact_certs_")


def _selected_fact_pool_size(
    parsed_output: dict[str, Any] | None,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> int:
    if selected_facts is not None:
        return sum(
            1
            for f in selected_facts
            if isinstance(f, dict)
            and str(f.get("fact_id") or "").strip()
            and not _is_cert_fact_id_for_utilization(str(f.get("fact_id") or ""))
        )
    if not isinstance(parsed_output, dict):
        return 0
    plan = parsed_output.get("selected_fact_plan")
    if isinstance(plan, dict):
        facts = plan.get("facts") or []
        return sum(
            1
            for f in facts
            if isinstance(f, dict)
            and str(f.get("fact_id") or "").strip()
            and not _is_cert_fact_id_for_utilization(str(f.get("fact_id") or ""))
        )
    return 0


def _fact_id_base_for_utilization(fid: str) -> str:
    s = str(fid or "").strip()
    return s.split("_metric_", 1)[0] if "_metric_" in s else s


def collect_cited_source_fact_ids(
    claim_ledger: list[dict[str, Any]],
    text_claim_coverage: dict[str, Any] | None = None,
) -> set[str]:
    """Union of fact IDs cited in claim_ledger and text_claim_coverage material claims."""
    cited: set[str] = set()
    for row in claim_ledger:
        if not isinstance(row, dict):
            continue
        for fid in row.get("source_fact_ids") or []:
            s = str(fid).strip()
            if not s:
                continue
            cited.add(s)
            cited.add(_fact_id_base_for_utilization(s))
    if isinstance(text_claim_coverage, dict):
        for sent in text_claim_coverage.get("sentences") or []:
            if not isinstance(sent, dict):
                continue
            for mc in sent.get("material_claims") or []:
                if not isinstance(mc, dict):
                    continue
                for fid in mc.get("source_fact_ids") or []:
                    s = str(fid).strip()
                    if not s:
                        continue
                    cited.add(s)
                    cited.add(_fact_id_base_for_utilization(s))
    return cited


def default_allowed_fact_utilization_waivers(allowed_fact_ids: set[str]) -> frozenset[str]:
    """Credential inventory facts may sit in pool without display weave (I0 / no_credential_dump)."""
    return frozenset(
        fid for fid in allowed_fact_ids if fid and _is_cert_fact_id_for_utilization(str(fid))
    )


def collect_unused_allowed_fact_ids(
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
) -> list[str]:
    cited = collect_cited_source_fact_ids(claim_ledger)
    unused = [fid for fid in sorted(allowed_fact_ids) if fid and fid not in cited]
    return unused


def brushstroke_required_fact_ids_from_composition_plan(
    composition_plan: dict[str, Any] | None,
) -> set[str]:
    """Union of facts the composition's B1..B4 brushstrokes require the summary to weave.

    Sourced from ``brushstrokes[*].required_fact_ids`` plus ``brushstroke_fact_bindings[*].fact_id``.
    This is the curated, form-satisfiable required set for utilization scoping (vs the full pool).
    """
    out: set[str] = set()
    if not isinstance(composition_plan, dict):
        return out
    for b in composition_plan.get("brushstrokes") or []:
        if isinstance(b, dict):
            for fid in b.get("required_fact_ids") or []:
                if str(fid).strip():
                    out.add(str(fid).strip())
    for row in composition_plan.get("brushstroke_fact_bindings") or []:
        if isinstance(row, dict):
            fid = row.get("fact_id") or row.get("source_fact_id")
            if fid and str(fid).strip():
                out.add(str(fid).strip())
    return out


def brushstroke_required_groups_from_composition_plan(
    composition_plan: dict[str, Any] | None,
) -> list[list[str]]:
    """Per-brushstroke required fact-id lists (B1..B4) from the composition plan.

    Each inner list is one brushstroke's ``required_fact_ids``; empty brushstrokes (e.g. a
    business-role-fit brushstroke with no bound facts) are dropped. Used to grade exec_summary
    utilization as brushstroke COVERAGE (>=1 fact cited per required brushstroke) — matching the
    composition's own ``brushstroke_covered_ids`` / ``brushstroke_missing_ids`` notion, which a
    six-sentence summary can satisfy (vs citing every fact in the full promoted pool).
    """
    groups: list[list[str]] = []
    if not isinstance(composition_plan, dict):
        return groups
    brushstrokes = composition_plan.get("brushstrokes")
    if isinstance(brushstrokes, list) and brushstrokes:
        for b in brushstrokes:
            if isinstance(b, dict):
                ids = [str(x).strip() for x in (b.get("required_fact_ids") or []) if str(x).strip()]
                if ids:
                    groups.append(ids)
        if groups:
            return groups
    bindings = composition_plan.get("brushstroke_fact_bindings")
    if isinstance(bindings, list):
        by_role: dict[str, list[str]] = {}
        for row in bindings:
            if isinstance(row, dict):
                fid = row.get("fact_id") or row.get("source_fact_id")
                role = str(row.get("brushstroke_role") or row.get("brushstroke_id") or "")
                if fid and str(fid).strip():
                    by_role.setdefault(role, []).append(str(fid).strip())
        groups = [v for v in by_role.values() if v]
    return groups


def _brushstroke_required_groups_for_gates(
    parsed_output: dict[str, Any] | None,
    artifacts_dir: Path | None,
) -> list[list[str]]:
    """Resolve per-brushstroke required fact groups from parsed_output or the composition-plan artifact."""
    if isinstance(parsed_output, dict):
        g = brushstroke_required_groups_from_composition_plan(parsed_output)
        if g:
            return g
        cp = parsed_output.get("composition_plan")
        if isinstance(cp, dict):
            g = brushstroke_required_groups_from_composition_plan(cp)
            if g:
                return g
    if artifacts_dir is not None:
        try:
            p = Path(artifacts_dir) / "executive_summary_composition_plan.json"
            if p.is_file():
                return brushstroke_required_groups_from_composition_plan(
                    json.loads(p.read_text(encoding="utf-8"))
                )
        except (OSError, ValueError):
            return []
    return []


def check_exec_summary_allowed_fact_utilization(
    claim_ledger: list[dict[str, Any]],
    allowed_fact_ids: set[str],
    *,
    text_claim_coverage: dict[str, Any] | None = None,
    waived_fact_ids: set[str] | None = None,
    required_scope_fact_ids: set[str] | None = None,
    required_brushstroke_groups: list[list[str]] | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Each required brushstroke must be represented in claim_ledger / text_claim_coverage.

    Post graph-era migration the ALLOWED_SOURCE_FACT_IDS pool is the union of every lane's promoted
    facts (~50+), which a six-sentence summary cannot all cite — grading utilization as
    "cite every allowed fact" is unsatisfiable by construction. When the composition's brushstroke
    groups are supplied (``required_brushstroke_groups`` = the per-B1..B4 ``required_fact_ids``),
    utilization is graded as COVERAGE: every non-empty required brushstroke must have >=1 of its
    bound facts cited — the same "covered vs missing" notion the composition itself computes. A
    required brushstroke with zero cited facts still fails the gate, so no required theme can be
    silently dropped. Falls back to the legacy "all non-cert allowed facts" rule (optionally scoped
    by ``required_scope_fact_ids``) when no brushstroke groups are supplied (legacy callers / unit
    tests), preserving prior behavior.
    """
    from apps_rg.runtime.validators.executive_summary_x2 import resolve_utilization_waived_fact_ids
    allowed = {str(x).strip() for x in allowed_fact_ids if str(x).strip()}
    waived = (
        {str(x).strip() for x in waived_fact_ids if str(x).strip()}
        if waived_fact_ids is not None
        else resolve_utilization_waived_fact_ids(allowed)
    )
    cited = collect_cited_source_fact_ids(claim_ledger, text_claim_coverage)

    def _is_cited(fid: str) -> bool:
        return fid in cited or _fact_id_base_for_utilization(fid) in cited

    # Brushstroke COVERAGE mode (preferred): each non-empty required brushstroke must be represented.
    groups: list[list[str]] = []
    for grp in required_brushstroke_groups or []:
        g = [str(x).strip() for x in (grp or []) if str(x).strip() and str(x).strip() not in waived]
        if g:
            groups.append(g)
    if groups:
        uncovered = [g for g in groups if not any(_is_cited(fid) for fid in g)]
        receipt = {
            "waived_fact_ids": sorted(waived),
            "required_brushstroke_group_count": len(groups),
            "cited_fact_ids": sorted(cited),
            "uncovered_brushstroke_groups": uncovered,
            "policy": "brushstroke_coverage",
            "brushstroke_scoped": True,
        }
        if uncovered:
            reps = [g[0] for g in uncovered]
            return False, f"uncovered_required_brushstrokes={reps}", receipt
        return True, "ok", receipt

    # Legacy / flat fallback: every non-waived (optionally scoped) allowed fact must be cited.
    scope: set[str] | None = None
    if required_scope_fact_ids:
        scope = {str(x).strip() for x in required_scope_fact_ids if str(x).strip()} & allowed
    base_required = (scope if scope else allowed) - waived
    missing = [fid for fid in sorted(base_required) if not _is_cited(fid)]
    receipt = {
        "waived_fact_ids": sorted(waived),
        "required_utilization_fact_ids": sorted(base_required),
        "cited_fact_ids": sorted(cited),
        "unused_required_fact_ids": missing,
        "policy": "brushstroke_required_scope" if scope else "cert_facts_waived_by_default",
        "brushstroke_scoped": bool(scope),
    }
    if missing:
        return False, f"unused_required_allowed_facts={missing}", receipt
    return True, "ok", receipt


def check_exec_summary_evidence_utilization(
    resume_display_text: str,
    parsed_output: dict[str, Any] | None = None,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> tuple[bool, str | None]:
    """Structural density: weave allowed facts into narrative — not a word-count floor."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MIN_SENTENCES
    if _pool_too_small_excused(parsed_output):
        return True, "excused_selected_fact_pool_too_small"
    pool_size = _selected_fact_pool_size(parsed_output, selected_facts=selected_facts)
    if pool_size < EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE:
        return True, "ok_pool_below_utilization_threshold"
    ledger = list((parsed_output or {}).get("claim_ledger") or [])
    ledger_rows = sum(
        1
        for row in ledger
        if isinstance(row, dict) and str(row.get("claim_text") or "").strip()
    )
    sentences = [s for s in split_sentences(resume_display_text) if str(s).strip()]
    failures: list[str] = []
    if pool_size >= EVIDENCE_UTIL_MIN_POOL_FOR_LEDGER_DEPTH and ledger_rows < EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE:
        failures.append(
            f"claim_ledger_rows_{ledger_rows}_with_pool_{pool_size}_need_at_least_{EVIDENCE_UTIL_MIN_LEDGER_ROWS_WHEN_POOL_LARGE}"
        )
    if len(sentences) == EXEC_SUMMARY_MIN_SENTENCES and pool_size >= EVIDENCE_UTIL_MIN_POOL_FOR_THIN_SENTENCE:
        for i, sent in enumerate(sentences):
            wc = len(re.findall(r"\S+", sent))
            if wc < EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR:
                failures.append(
                    f"sentence_{i}_words_{wc}_below_{EVIDENCE_UTIL_MIN_WORDS_PER_SENTENCE_WHEN_FOUR}_with_pool_{pool_size}"
                )
                break
    if failures:
        return False, "; ".join(failures)
    return True, "ok"
