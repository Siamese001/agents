"""Generic filler, forbidden meta phrases, and synthesis quality voice repairs."""
from __future__ import annotations

import re
from typing import Any

from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES,
    EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE,
    GENERIC_FILLER,
    check_inferred_bridge_claims,
)

from .constants import (
    _BARE_SUBJECTLESS_OPENER_RE,
    _EXTENSIVE_EXPERIENCE_EXEC_RE,
    _EXTENSIVE_EXPERIENCE_RE,
    _FILLER_REPLACEMENTS,
    _FORCED_LINEAGE_BRIDGE_RE,
    _FORMULAIC_S2_RE,
    _FORMULAIC_S3_RE,
    _GENERIC_S1_RE,
    _JUDGE_FAIL_S5_SUBSTRING,
    _JUDGE_FAIL_S6_LOOKING_AHEAD,
    _MATERIAL_METRIC_RE,
    _META_PHRASE_REPLACEMENTS,
    _S1_DISTINCTIVE_REPLACEMENT,
    _S4_PARTICIPIAL_AFTER_COMPLEMENT_RE,
    _S5_CREDENTIAL_DUMP_RE,
    _S5_META_COMMENTARY_RE,
    _S5_STRESS_ECHO_RE,
    _S6_THIN_RECAP_RE,
    _UNIFY_HELD_METRIC_PATTERNS,
)
from .parent_proxy import _p

def _fact_corpus_lower(selected_facts: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for row in selected_facts or []:
        if not isinstance(row, dict):
            continue
        parts.append(str(row.get("claim_text") or ""))
        parts.append(str(row.get("achievement_summary") or ""))
    return " ".join(parts).lower()


def _sentence_has_material_metric(sentence: str) -> bool:
    return bool(_MATERIAL_METRIC_RE.search(str(sentence or "")))


def _sentence_is_credential_inventory_dump(sentence: str) -> bool:
    from apps_rg.runtime.sections.section_authority_repairs import _sentence_fails_credential_dump

    return _sentence_fails_credential_dump(str(sentence or ""))


def _first_percent_from_facts(selected_facts: list[dict[str, Any]] | None) -> str | None:
    corpus = _fact_corpus_lower(selected_facts)
    match = re.search(r"\b(\d+(?:\.\d+)?%)\b", corpus)
    return match.group(1) if match else None


def _facts_mention_fsa(selected_facts: list[dict[str, Any]] | None) -> bool:
    corpus = _fact_corpus_lower(selected_facts)
    if "fsa" in corpus or "fellow of the society of actuaries" in corpus:
        return True
    for row in selected_facts or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("fact_id") or row.get("candidate_fact_id") or "").lower()
        if "quant_hpc_003" in fid or "credentials" in fid:
            return True
    return False


def build_metric_grounded_s5(
    selected_facts: list[dict[str, Any]] | None,
    *,
    avoid_stress_testing_echo: bool = False,
) -> str:
    """S5 with allowed FSA + dollar/percent from proof pool (no derivatives inventory list)."""
    pct = _first_percent_from_facts(selected_facts)
    fsa = _facts_mention_fsa(selected_facts)
    stress_clause = ""
    if pct and not avoid_stress_testing_echo:
        stress_clause = f", including {pct} stress-testing cycle gains"
    elif pct and avoid_stress_testing_echo:
        stress_clause = f", with {pct} regulatory reporting and analytics outcomes"
    if fsa and pct:
        return (
            "On that commercial base, FSA-certified capital modeling and quantitative rigor"
            f"{stress_clause}, inform which platform investments clear governance gates "
            "with measurable regulated outcomes."
        )
    if fsa:
        return (
            "On that commercial base, FSA-certified capital modeling informs which platform "
            "investments clear governance gates fastest while preserving quantitative discipline."
        )
    if pct:
        return (
            f"On that commercial base, quantitative rigor and {pct} analytics outcomes inform "
            "which platform investments clear governance gates with measurable results."
        )
    return (
        "On that commercial base, quantitative capital modeling informs which platform "
        "investments clear governance gates fastest in regulated programs."
    )


def build_forward_s6(selected_facts: list[dict[str, Any]] | None) -> str:
    """Forward synthesis without cover-letter 'Looking ahead' opener."""
    corpus = _fact_corpus_lower(selected_facts)
    lineage = (
        "Basel III lineage controls"
        if "basel" in corpus or "ccar" in corpus
        else "regulatory lineage controls"
    )
    return (
        "Innovation incubation and architecture standards can federate governed platform "
        f"capabilities across autonomous business units without weakening {lineage}."
    )


def _repair_forbidden_meta_phrases(resume_display_text: str) -> tuple[str, list[str]]:
    """Strip X2-banned meta scaffolding without changing sentence count."""
    from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

    out = str(resume_display_text or "")
    repairs: list[str] = []
    for bad, good in _META_PHRASE_REPLACEMENTS:
        if bad in out.lower():
            pattern = re.compile(re.escape(bad), re.IGNORECASE)
            out = pattern.sub(good, out)
            repairs.append(f"meta_phrase:{bad[:40]}")
    replaced_lower = {bad.lower() for bad, _ in _META_PHRASE_REPLACEMENTS}
    for phrase in EXEC_SUMMARY_FORBIDDEN_META_PHRASES + EXEC_SUMMARY_FORBIDDEN_META_PHRASES_LOOSE:
        if phrase.lower() in replaced_lower:
            continue
        if phrase in out.lower():
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            out = pattern.sub("", out)
            repairs.append(f"meta_phrase_strip:{phrase[:40]}")
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;])", r"\1", out)
    sents = split_sentences(out.strip())
    if sents:
        fixed_sents: list[str] = []
        for s in sents:
            st = s.strip()
            if not st:
                continue
            if _BARE_SUBJECTLESS_OPENER_RE.match(st):
                st = f"That combined technical and commercial foundation {st[:1].lower()}{st[1:]}"
                repairs.append("meta_phrase_subject_restored")
            elif st[:1].isalpha() and st[:1].islower():
                st = st[:1].upper() + st[1:]
                repairs.append("meta_phrase_sentence_capitalized")
            fixed_sents.append(st)
        out = " ".join(fixed_sents)
    return out.strip(), repairs


def _repair_synthesis_quality_sentences(
    resume_display_text: str,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Rewrite Claude-fail S5/S6 patterns while preserving six-sentence shape."""
    from apps_rg.runtime.validators.executive_summary_sentence_utils import split_sentences

    text = str(resume_display_text or "").strip()
    sentences = split_sentences(text)
    if len(sentences) != 6:
        return text, []

    repairs: list[str] = []
    out_sents = list(sentences)

    if _FORCED_LINEAGE_BRIDGE_RE.search(out_sents[3]):
        # Use a NON-STOCK opener here — "Complementing that" would be the 3rd stock bridge
        # in S2–S4, failing x2_exec_summary_stock_bridge_max_two (max 2 per paragraph).
        out_sents[3] = _FORCED_LINEAGE_BRIDGE_RE.sub(
            "In parallel,",
            out_sents[3],
            count=1,
        )
        repairs.append("forced_lineage_bridge_s4")

    s5 = out_sents[4]
    s5_dump = bool(_S5_CREDENTIAL_DUMP_RE.search(s5)) or _sentence_is_credential_inventory_dump(s5)
    s5_preserve = _sentence_has_material_metric(s5) and not _sentence_is_credential_inventory_dump(s5)
    if s5_dump and not s5_preserve:
        out_sents[4] = build_metric_grounded_s5(
            selected_facts,
            avoid_stress_testing_echo=_S5_STRESS_ECHO_RE.search(out_sents[3]) is not None,
        )
        repairs.append("credential_inventory_s5_metric_grounded")

    s6 = out_sents[5]
    s6_thin = bool(_S6_THIN_RECAP_RE.search(s6)) or (
        "governed platform delivery" in s6.lower() and "extend" in s6.lower()
    )
    if s6_thin or _JUDGE_FAIL_S6_LOOKING_AHEAD.match(s6.strip()):
        out_sents[5] = build_forward_s6(selected_facts)
        repairs.append("thin_recap_s6_forward_grounded")

    if _S4_PARTICIPIAL_AFTER_COMPLEMENT_RE.search(out_sents[3]):
        out_sents[3] = _S4_PARTICIPIAL_AFTER_COMPLEMENT_RE.sub(
            r"\1 re-architected",
            out_sents[3],
            count=1,
        )
        repairs.append("s4_participial_to_finite")
    elif "re-architecting monolithic" in out_sents[3].lower():
        out_sents[3] = re.sub(
            r"\bre-architecting monolithic\b",
            "re-architected monolithic",
            out_sents[3],
            flags=re.IGNORECASE,
        )
        repairs.append("s4_rearchitecting_to_finite")

    if _S5_META_COMMENTARY_RE.search(out_sents[4]):
        out_sents[4] = _S5_META_COMMENTARY_RE.sub(".", out_sents[4]).strip()
        if not out_sents[4].endswith("."):
            out_sents[4] = out_sents[4] + "."
        repairs.append("s5_meta_commentary_strip")

    if _FORMULAIC_S3_RE.match(out_sents[2].strip()):
        out_sents[2] = _FORMULAIC_S3_RE.sub("Within that ecosystem model, ", out_sents[2], count=1)
        repairs.append("formulaic_s3_connective")

    if _FORMULAIC_S2_RE.match(out_sents[1].strip()):
        out_sents[1] = _FORMULAIC_S2_RE.sub("From that platform footprint, ", out_sents[1], count=1)
        repairs.append("formulaic_s2_connective")

    if (
        _S5_STRESS_ECHO_RE.search(out_sents[3])
        and _S5_STRESS_ECHO_RE.search(out_sents[4])
        and not _sentence_has_material_metric(out_sents[4])
    ):
        out_sents[4] = build_metric_grounded_s5(selected_facts, avoid_stress_testing_echo=True)
        repairs.append("s5_stress_testing_echo_s4_metric_grounded")

    joined = " ".join(s.strip() for s in out_sents if s.strip())
    if _JUDGE_FAIL_S5_SUBSTRING.lower() in joined.lower():
        out_sents[4] = build_metric_grounded_s5(selected_facts)
        joined = " ".join(s.strip() for s in out_sents if s.strip())
        repairs.append("s5_judge_fail_guard")

    if not repairs:
        return text, []
    return joined, repairs


def repair_generic_filler_prose(
    resume_display_text: str,
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Strip or rewrite banned recruiter filler without weakening X2 gates."""
    text = str(resume_display_text or "").strip()
    receipt: dict[str, Any] = {
        "schema": "executive_summary_voice_repair_v1",
        "repaired": False,
        "replacements": [],
    }
    if not text:
        return text, receipt

    out = text
    if _GENERIC_S1_RE.search(out):
        out = _GENERIC_S1_RE.sub(_S1_DISTINCTIVE_REPLACEMENT, out, count=1)
        receipt["replacements"].append("generic_s1_opener")
    corpus = _fact_corpus_lower(selected_facts)
    if _EXTENSIVE_EXPERIENCE_EXEC_RE.search(out):
        out = _EXTENSIVE_EXPERIENCE_EXEC_RE.sub("Engineering executive", out)
        receipt["replacements"].append("extensive_experience_exec_opener")
    elif _EXTENSIVE_EXPERIENCE_RE.search(out):
        out = _EXTENSIVE_EXPERIENCE_RE.sub(" who led", out)
        receipt["replacements"].append("extensive_experience_in")
    if "regulated enterprise" in corpus:
        new_out = re.sub(
            r"\bregulated environments\b",
            "regulated enterprise workflows",
            out,
            flags=re.IGNORECASE,
        )
        if new_out != out:
            out = new_out
            receipt["replacements"].append("regulated_environments_to_workflows")
    has_gov_fact = False
    for row in selected_facts or []:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("fact_id") or row.get("candidate_fact_id") or "").strip()
        if fid == "fact_governance_003" or fid.startswith("fact_governance_003_metric"):
            has_gov_fact = True
            break
    if has_gov_fact or "governance framework" in corpus or "basel" in corpus or "ccar" in corpus:
        new_out = re.sub(
            r"\bgovernance frameworks?\b",
            "Basel III/CCAR lineage and validation frameworks",
            out,
            flags=re.IGNORECASE,
        )
        if new_out != out:
            out = new_out
            receipt["replacements"].append("governance_framework_to_basel_lineage")
    for pattern, repl in _FILLER_REPLACEMENTS:
        if pattern.search(out):
            out = pattern.sub(repl, out)
            receipt["replacements"].append(pattern.pattern[:80])

    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;])", r"\1", out)
    if out and out[0].islower():
        out = out[0].upper() + out[1:]

    from apps_rg.runtime.validators.executive_summary_sentence_utils import (
        join_executive_summary_sentences,
        split_sentences,
    )

    meta_opener = re.compile(
        r"^(Additionally|Furthermore|Moreover),?\s+",
        re.IGNORECASE,
    )
    rebuilt: list[str] = []
    for sent in split_sentences(out):
        stripped = meta_opener.sub("", sent.strip()).strip()
        if stripped:
            rebuilt.append(stripped)
    if rebuilt:
        joined = join_executive_summary_sentences(rebuilt)
        if joined != out:
            out = joined
            receipt["replacements"].append("meta_filler_opener_strip")
    out = re.sub(r"\bAdditionally,\s+", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\bFurthermore,\s+", "", out, flags=re.IGNORECASE)
    if out and out[0].islower():
        out = out[0].upper() + out[1:]

    syn_out, syn_repairs = _repair_synthesis_quality_sentences(
        out, selected_facts=selected_facts
    )
    if syn_repairs:
        out = syn_out
        receipt["replacements"].extend(syn_repairs)

    meta_out, meta_repairs = _repair_forbidden_meta_phrases(out)
    if meta_repairs:
        out = meta_out
        receipt["replacements"].extend(meta_repairs)

    filler_hits = [p for p in GENERIC_FILLER if p in out.lower()]
    bridge_ok, bridge_reason = check_inferred_bridge_claims(out, selected_facts)
    receipt["post_repair_filler_hits"] = filler_hits
    receipt["post_repair_bridge_ok"] = bridge_ok
    receipt["post_repair_bridge_reason"] = bridge_reason or ""
    receipt["repaired"] = out != text
    receipt["before_word_count"] = len(text.split())
    receipt["after_word_count"] = len(out.split())
    return out.strip(), receipt


def strip_unsupported_source_sensitive_prose(
    parsed: dict[str, Any],
    *,
    selected_facts: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rewrite or drop SOURCE_SENSITIVE phrases unsupported by allowed facts."""
    from apps_rg.runtime.validators.executive_summary_x2 import (
        SOURCE_SENSITIVE_PHRASES,
        _sensitive_phrase_present,
        check_source_sensitive_phrases,
    )

    out = dict(parsed)
    text = str(out.get("resume_display_text") or "")
    receipt: dict[str, Any] = {
        "schema": "executive_summary_source_sensitive_strip_v1",
        "repaired": False,
        "replacements": [],
    }
    if not text:
        return out, receipt

    facts = list(selected_facts or [])
    supported: set[str] = set()
    corpus_parts: list[str] = []
    for row in facts:
        if not isinstance(row, dict):
            continue
        corpus_parts.append(str(row.get("claim_text") or ""))
        corpus_parts.append(str(row.get("achievement_summary") or ""))
    corpus = " ".join(corpus_parts).lower()
    for phrase in SOURCE_SENSITIVE_PHRASES:
        if _sensitive_phrase_present(corpus, phrase):
            supported.add(phrase)

    rewritten = text
    if "regulated environments" not in supported:
        if "regulated enterprise workflows" in supported or "regulated enterprise" in corpus:
            new = re.sub(
                r"\bregulated environments\b",
                "regulated enterprise workflows",
                rewritten,
                flags=re.IGNORECASE,
            )
            if new != rewritten:
                rewritten = new
                receipt["replacements"].append("regulated_environments_to_workflows")
        else:
            new = re.sub(
                r"\bregulated environments\b",
                "enterprise programs",
                rewritten,
                flags=re.IGNORECASE,
            )
            if new != rewritten:
                rewritten = new
                receipt["replacements"].append("regulated_environments_neutralized")

    if "governance framework" not in supported:
        if "basel" in corpus or "ccar" in corpus or "lineage" in corpus:
            new = re.sub(
                r"\bgovernance frameworks?\b",
                "Basel III/CCAR lineage and validation frameworks",
                rewritten,
                flags=re.IGNORECASE,
            )
            if new != rewritten:
                rewritten = new
                receipt["replacements"].append("governance_framework_to_basel")

    if "audit" not in supported:
        new = re.sub(
            r"\baudit-ready\b",
            lambda m: "traceable" if re.match(r"^\s+lineage\b", rewritten[m.end():], re.I) else "lineage-ready",
            rewritten, flags=re.IGNORECASE,
        )
        new = re.sub(r"\b([Aa])n\s+(?=traceable|lineage-ready)", lambda m: "A " if m.group(1) == "A" else "a ", new)
        if new != rewritten:
            rewritten = new
            receipt["replacements"].append("audit_ready_to_lineage_ready")
        if _sensitive_phrase_present(rewritten.lower(), "audit"):
            new = re.sub(r"\baudit\b", "controls", rewritten, flags=re.IGNORECASE)
            if new != rewritten:
                rewritten = new
                receipt["replacements"].append("audit_to_controls")

    for phrase in ("compliance",):
        if phrase not in supported and _sensitive_phrase_present(rewritten.lower(), phrase):
            new = re.sub(rf"\b{re.escape(phrase)}\b", "controls", rewritten, flags=re.IGNORECASE)
            if new != rewritten:
                rewritten = new
                receipt["replacements"].append(f"{phrase}_to_controls")

    ok, reason = check_source_sensitive_phrases(rewritten, facts)
    receipt["post_check_ok"] = ok
    receipt["post_check_reason"] = reason or ""
    if rewritten != text:
        out["resume_display_text"] = rewritten.strip()
        receipt["repaired"] = True
    return out, receipt
