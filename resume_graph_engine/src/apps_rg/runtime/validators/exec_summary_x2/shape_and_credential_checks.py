"""Word budgets, credential dump guards, prompt authority, and graph-evidence shape checks."""

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

def check_exec_summary_paragraph_max_words(
    resume_display_text: str,
    parsed_output: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Overflow guard only — no paragraph word minimum (fit_to_evidence + exactly six sentences)."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_WORDS
    _ = parsed_output
    wc = _resume_word_count(resume_display_text)
    if wc > EXEC_SUMMARY_MAX_WORDS:
        return False, f"executive summary word count {wc} exceeds maximum {EXEC_SUMMARY_MAX_WORDS}"
    return True, "ok"


def check_exec_summary_no_bloated_sentence(resume_display_text: str) -> tuple[bool, str | None]:
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE
    for i, sent in enumerate(split_sentences(resume_display_text)):
        wc = len(re.findall(r"\S+", sent))
        if wc > EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE:
            return False, f"sentence {i} has {wc} words (max {EXEC_SUMMARY_MAX_WORDS_PER_SENTENCE})"
    return True, None


def check_exec_summary_no_mechanism_inventory(
    resume_display_text: str,
    parsed_output: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    from apps_rg.runtime.sections.executive_summary_composition import is_mechanism_inventory_sentence

    diag = (parsed_output or {}).get("c0_graph_diagnostics") if isinstance(parsed_output, dict) else {}
    if not isinstance(diag, dict):
        diag = {}
    for i, sent in enumerate(split_sentences(resume_display_text)):
        inv, reason = is_mechanism_inventory_sentence(sent)
        if inv:
            dom_fact = str(diag.get("dominant_source_fact_id") or "unknown")
            refs = diag.get("dominant_claim_support_graph_refs") or []
            suppressed = diag.get("dominant_suppressed_skill_refs") or []
            ref_tail = ",".join(str(r) for r in refs[:6])
            sup_tail = ",".join(str(r) for r in suppressed[:6])
            return (
                False,
                f"sentence {i}: {reason}; dominant_source_fact={dom_fact}; "
                f"claim_support_graph_refs=[{ref_tail}]; suppressed_skills=[{sup_tail}]",
            )
    return True, None


def _vendor_named_cert_hits(low: str) -> int:
    return sum(1 for m in VENDOR_NAMED_CERT_LABELS if m in low)


def _sentence_has_fsa_rigor(low: str) -> bool:
    if any(m in low for m in FSA_RIGOR_MARKERS):
        return True
    return bool(FSA_WORD_RE.search(low))


def _sentence_fsa_rigor_only(low: str) -> bool:
    """FSA-only sentence: allowed once per summary (C0.3 phase-1), unlike vendor cert dumps."""
    return _sentence_has_fsa_rigor(low) and _vendor_named_cert_hits(low) == 0


def check_exec_summary_no_credential_dump(resume_display_text: str) -> tuple[bool, str | None]:
    from apps_rg.runtime.sections.competencies_certification_contract import is_credential_competency_term

    sentences = split_sentences(resume_display_text)
    fsa_only_indexes = [i for i, s in enumerate(sentences) if _sentence_fsa_rigor_only(s.lower())]
    if len(fsa_only_indexes) > 1:
        return (
            False,
            f"at most one FSA rigor mention allowed (C0.3 phase-1); found sentences {fsa_only_indexes}",
        )

    for i, sent in enumerate(sentences):
        low = sent.lower()
        vendor_hits = _vendor_named_cert_hits(low)
        context_hits = sum(1 for m in CREDENTIAL_CONTEXT_MARKERS if m in low)
        fsa_only = _sentence_fsa_rigor_only(low)

        if fsa_only:
            if vendor_hits >= 1:
                return False, f"sentence {i}: FSA rigor mention mixed with vendor cert labels"
            continue

        if vendor_hits >= 2:
            return False, f"sentence {i}: vendor certification inventory ({vendor_hits} labels)"
        if context_hits >= 3:
            return False, f"sentence {i}: credential or certification inventory block ({context_hits} markers)"
        if is_credential_competency_term(sent) and vendor_hits >= 1:
            return False, f"sentence {i}: vendor cert label in executive summary"
        if is_credential_competency_term(sent):
            return False, f"sentence {i}: named cert label in executive summary"
        if re.search(r"\bcredentials?\s+reinforce\b", low) and (
            vendor_hits >= 1 or _sentence_has_fsa_rigor(low)
        ):
            return False, f"sentence {i}: credential-block closing pattern"
        if i >= 3 and vendor_hits >= 1:
            return False, f"sentence {i}: named vendor cert label in closing band (S4-S6)"
    return True, None


def check_exec_summary_no_competencies_duplication(resume_display_text: str) -> tuple[bool, str | None]:
    low = resume_display_text.lower()
    forbidden = (
        "engineering & platform competencies",
        "platform competencies:",
        "competencies section",
        "category_label",
    )
    hits = [p for p in forbidden if p in low]
    if hits:
        return False, f"competencies section duplication markers: {hits}"
    return True, None


def check_exec_summary_no_certifications_section_duplication(resume_display_text: str) -> tuple[bool, str | None]:
    low = resume_display_text.lower()
    if "certifications & credentials" in low or "certifications and credentials section" in low:
        return False, "certifications section heading duplicated in executive summary"
    return True, None


def check_prompt_template_authority(
    artifacts_dir: Path | None,
    *,
    expected_template_ref: str = EXPECTED_PROMPT_TEMPLATE_REF,
    expected_prompt_id: str = EXPECTED_PROMPT_ID,
) -> tuple[bool, str | None]:
    if artifacts_dir is None:
        return False, "artifacts_dir missing for prompt template authority"
    trace_path = artifacts_dir / "prompt_selection_trace.json"
    artifact_path = artifacts_dir / "compiled_prompt_artifact.json"
    if not trace_path.is_file():
        return False, "prompt_selection_trace.json missing"
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"prompt_selection_trace unreadable: {exc}"
    if not isinstance(trace, dict):
        return False, "prompt_selection_trace must be object"
    ref = str(
        trace.get("apps_rg_prompt_template_ref") or trace.get("contract_template_ref") or ""
    ).strip()
    prompt_id = str(trace.get("prompt_id") or "").strip()
    shell_id = str(trace.get("compiler_template_id") or trace.get("selected_template_id") or "").strip()
    if ref != expected_template_ref:
        return False, f"apps_rg_prompt_template_ref {ref!r} != expected {expected_template_ref!r}"
    if prompt_id != expected_prompt_id and not prompt_id.endswith(expected_prompt_id):
        return False, f"prompt_id {prompt_id!r} != expected {expected_prompt_id!r}"
    if shell_id and shell_id != EXPECTED_PA_SHELL_TEMPLATE_ID:
        return False, f"PA shell template_id {shell_id!r} != expected {EXPECTED_PA_SHELL_TEMPLATE_ID!r}"
    if artifact_path.is_file():
        try:
            art = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # guardian: allow-pass -- optional cross-check
            art = None
        if isinstance(art, dict):
            art_ref = str(
                art.get("apps_rg_prompt_template_ref") or art.get("contract_template_ref") or ""
            ).strip()
            if art_ref and art_ref != expected_template_ref:
                return False, f"compiled_prompt_artifact ref mismatch: {art_ref!r}"
            art_prompt = str(art.get("selected_template_id") or art.get("compiler_template_id") or "").strip()
            if art_prompt and art_prompt != EXPECTED_PA_SHELL_TEMPLATE_ID:
                return False, f"compiled_prompt_artifact shell {art_prompt!r} != {EXPECTED_PA_SHELL_TEMPLATE_ID!r}"
    return True, None


def _resume_word_count(resume_display_text: str) -> int:
    return len(re.findall(r"\S+", str(resume_display_text or "").strip()))


def _graph_evidence_lane_no_commercial_org_cred(s: str, label: str) -> str | None:
    """Shared S2/S3 lane: no $, revenue, margin, org scale, credential language, credential-led openers."""
    sl = s.lower()
    if "$" in s:
        return f"{label}: $ forbidden"
    if re.search(r"\brevenue\b", sl):
        return f"{label}: revenue forbidden"
    if re.search(r"\b(margin|margins)\b", sl):
        return f"{label}: margin language forbidden"
    if re.search(r"\b8\s+to\s+28\b", sl):
        return f"{label}: team span 8-to-28 forbidden"
    if "specialist" in sl:
        return f"{label}: specialist/team-scale language forbidden"
    if re.search(r"\bfellow\b", sl):
        return f"{label}: Fellow/credential language forbidden"
    if "certification" in sl or re.search(r"\bcertified\b", sl):
        return f"{label}: certification language forbidden"
    st = s.strip()
    if not st:
        return f"{label}: empty"
    for bad_start in ("fellow of", "holds", "certified", "credentials"):
        if st.lower().startswith(bad_start):
            return f"{label}: must not start with credential-led opener {bad_start!r}"
    return None


def _graph_evidence_outcomes_sentence_opener_ok(s: str) -> str | None:
    """Outcomes (or combined outcomes+cred) sentence must not lead with credential inventory."""
    st = s.strip()
    if not st:
        return "outcomes sentence empty"
    sl = st.lower()
    for bad_start in ("fellow of", "holds", "certified", "credentials"):
        if sl.startswith(bad_start):
            return f"outcomes sentence must not lead with {bad_start!r}"
    return None


def _graph_evidence_credibility_sentence_opener_ok(s: str) -> str | None:
    st = s.strip()
    if not st:
        return "credibility sentence empty"
    sl = st.lower()
    if sl.startswith("holds certifications"):
        return "S5 must not start with Holds certifications"
    if sl.startswith("credentials"):
        return "S5 must not start with Credentials"
    return None



def check_graph_evidence_sentence_responsibility_shape(
    resume_display_text: str,
    proof_pool_metadata: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Graph painting-plan sentence arc."""
    from apps_rg.runtime.sections.executive_summary_composition import (
        check_graph_painting_sentence_responsibility_shape,
    )

    return check_graph_painting_sentence_responsibility_shape(
        resume_display_text, proof_pool_metadata
    )


def _exec_summary_painting_mode_active(
    proof_pool_metadata: dict[str, Any] | None = None,
) -> bool:
    return isinstance(proof_pool_metadata, dict) and bool(
        proof_pool_metadata.get("graph_skills_proof_pool")
    )


def _claim_row_uses_resume_fact_id(fid: str) -> bool:
    s = str(fid or "").strip()
    if not s:
        return False
    if s.upper() == "JD_ONLY":
        return False
    base = s.split("_metric_", 1)[0] if "_metric_" in s else s
    return base.startswith("fact_")
