"""Executive Voice Repair Agent for executive_summary, headline, and competencies.

Provides a bounded (max 1 pass) intelligent repair loop that receives X1D diagnostic
feedback (findings, cited sentences, and remediation suggestions) and produces targeted
section rewrites while preserving verified C0 fact grounding and format contracts.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import (
    APPROVED_HEADLINE_SENIORITY_PREFIXES,
    COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS,
    COMPETENCIES_TERM_MAX_WORDS,
    COMPETENCIES_TERM_MIN_WORDS,
    HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS,
    HEADLINE_FORBIDDEN_PLUMBING_LABELS,
    HEADLINE_SIGNAL_FLOOR_GOVERNANCE_TOKENS,
    HEADLINE_SIGNAL_FLOOR_PLATFORM_TOKENS,
)
from apps_rg.runtime.judges.x1d_panel_harness import extract_x1d_diagnostic

EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT = True
EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS = 1
from apps_rg.runtime.model_registry import resolve

DEFAULT_REPAIR_MODEL = resolve("repair.executive_voice").model
DEFAULT_AUDITOR_MODEL = resolve("proof_judge.standard.openai_chatgpt").model


@dataclass(frozen=True)
class ExecutiveVoiceRepairReceipt:
    """Audit receipt for an Executive Voice repair attempt."""

    section_id: str
    repair_attempted: bool
    repair_succeeded: bool
    repair_mechanism: str  # "deterministic_fast_path", "llm_repair_agent", or "none"
    diagnostic_summary: dict[str, Any]
    repaired_fields: tuple[str, ...] = field(default_factory=tuple)
    original_snippet: str = ""
    repaired_snippet: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["repaired_fields"] = list(self.repaired_fields)
        return data


def executive_voice_repair_enabled() -> bool:
    """Return whether the executive voice repair agent is active."""
    raw = os.environ.get("APPS_RG_X1_REPAIR_ENABLED", "1").strip().lower()
    return EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT and raw not in ("0", "false", "no", "off")


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences preserving order."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _format_allowed_facts_for_prompt(
    allowed_facts: list[dict[str, Any]] | None,
    *,
    limit: int = 30,
) -> list[str]:
    facts_summary: list[str] = []
    for f in (allowed_facts or [])[:limit]:
        if isinstance(f, dict):
            txt = str(
                f.get("claim_text")
                or f.get("fact_text")
                or f.get("canonical_bullet")
                or ""
            ).strip()
            fid = str(f.get("fact_id") or f.get("assertion_id") or "").strip()
            reb = str(f.get("role_episode_bundle_id") or "").strip()
            if txt:
                prefix = f"[{fid}]" if fid else "[fact]"
                if reb and reb != fid:
                    prefix = f"[{fid} | {reb}]"
                facts_summary.append(f"- {prefix} {txt}")
        elif isinstance(f, str) and f.strip():
            facts_summary.append(f"- {f.strip()}")
    return facts_summary


def _build_executive_summary_repair_prompt(
    current_text: str,
    diagnostic: dict[str, Any],
    allowed_facts: list[dict[str, Any]] | None,
    targeting_context: dict[str, Any] | None,
) -> str:
    sentences = _split_into_sentences(current_text)
    flagged_idx = diagnostic.get("cited_sentence_indexes") or []
    findings = diagnostic.get("findings") or []
    suggestions = diagnostic.get("remediation_suggestions") or []

    facts_summary = _format_allowed_facts_for_prompt(allowed_facts, limit=15)

    t_role = (targeting_context or {}).get("target_role", "Executive")
    t_company = (targeting_context or {}).get("target_company", "Enterprise")

    numbered_sentences = "\n".join(f"[{i + 1}] {s}" for i, s in enumerate(sentences))

    prompt = f"""You are an elite executive resume editor. Your task is to surgically repair an Executive Summary draft based on strict review feedback.

TARGET:
- Role: {t_role}
- Company: {t_company}

CURRENT DRAFT (Numbered by sentence):
{numbered_sentences}

DIAGNOSTIC FEEDBACK FROM ADVERSARIAL JUDGES:
- Findings: {json.dumps(findings)}
- Flagged Sentence Numbers (1-based): {[i + 1 for i in flagged_idx] if flagged_idx else "General voice/flow"}
- Suggested Remediation: {json.dumps(suggestions)}

ALLOWED GROUNDED FACTS (Do NOT introduce external ungrounded metrics or facts):
{chr(10).join(facts_summary) if facts_summary else "Preserve all facts already present in the draft."}

CRITICAL RULES:
1. PRESERVE THE VISUAL LAYOUT BAND: Output 3 to 4 crisp, spoken executive sentences totaling 420 to 680 characters (max 210 chars per sentence, max 110 words overflow cap) in a single cohesive paragraph.
2. SURGICAL EDIT: Modify ONLY the sentences that were flagged or require alignment with the diagnostic. Keep unflagged sentences unchanged.
3. ELIMINATE VOICE & AI-SLOP ISSUES:
   - Remove ALL AI bridge crutches ("In parallel,", "Building on that", "From that commercial base", "Against that", "Across enterprise programs,", "The same platform discipline", "That governed...") and abstract noun soup ("operating-model framing", "governed activation", "durable economics").
   - Vary sentence lengths (>= 4 words spread) and start each sentence with a distinct concrete opener; at most one trailing `-ing` clause.
   - S1: Sharp, authoritative executive hook (zero generic fluff).
   - S2-S3: Concrete technical/platform and commercial/governance proof with grounded numbers.
   - Optional S4: Crisp forward-looking mandate fit grounded in allowed facts (never a recap or cert dump).
4. ABSOLUTELY NO HALLUCINATIONS: Do not introduce company names, numbers, or technologies not present in the draft or allowed facts.

OUTPUT FORMAT:
Return a JSON object with this exact schema:
{{
  "repaired_text": "Complete 3-to-4 sentence paragraph here (420 to 680 chars).",
  "changes_made": [
    {{"sentence_number": 3, "rationale": "Replaced AI bridge crutch and abstract noun soup with grounded executive outcome"}}
  ]
}}
"""
    return prompt


def _build_headline_repair_prompt(
    current_headline: str,
    diagnostic: dict[str, Any],
    allowed_facts: list[dict[str, Any]] | None,
    targeting_context: dict[str, Any] | None,
) -> str:
    findings = diagnostic.get("findings") or []
    suggestions = diagnostic.get("remediation_suggestions") or []
    tc = dict(targeting_context or {})
    t_role = str(tc.get("target_title") or tc.get("target_role") or "Executive").strip()
    t_company = str(tc.get("target_company") or "Enterprise").strip()
    jd_excerpt = str(tc.get("jd_text") or "").strip()[:1200]
    briefing_excerpt = str(tc.get("briefing") or "").strip()[:600]
    facts_summary = _format_allowed_facts_for_prompt(allowed_facts, limit=20)

    approved_prefixes_str = ", ".join(APPROVED_HEADLINE_SENIORITY_PREFIXES)
    forbidden_plumbing_str = ", ".join(f"'{lbl}'" for lbl in HEADLINE_FORBIDDEN_PLUMBING_LABELS)
    abstraction_nouns_str = ", ".join(HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS[:-1]) + f", or {HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS[-1]}"
    platform_floor_str = ", ".join(f"'{tok}'" for tok in HEADLINE_SIGNAL_FLOOR_PLATFORM_TOKENS[:-1]) + f", or '{HEADLINE_SIGNAL_FLOOR_PLATFORM_TOKENS[-1]}'"
    governance_floor_str = ", ".join(f"'{tok}'" for tok in HEADLINE_SIGNAL_FLOOR_GOVERNANCE_TOKENS[:-1]) + f", or '{HEADLINE_SIGNAL_FLOOR_GOVERNANCE_TOKENS[-1]}'"

    prompt = f"""You are an elite executive resume editor. Your task is to repair a Headline draft.

TARGETING CONTEXT ONLY — NOT PROOF (evaluate alignment, never cite JD/briefing as candidate experience):
- Target Role: {t_role}
- Target Company: {t_company}
- JD Excerpt: {jd_excerpt or "(none)"}
- Briefing Excerpt: {briefing_excerpt or "(none)"}

ALLOWED GROUNDED FACTS (Every headline claim must trace to these verified candidate facts):
{chr(10).join(facts_summary) if facts_summary else "Preserve only facts already supported in the current draft."}

CURRENT HEADLINE:
"{current_headline}"

DIAGNOSTIC FEEDBACK:
- Findings: {json.dumps(findings)}
- Suggestions: {json.dumps(suggestions)}

RULES:
1. Exact format: "<Approved Seniority Prefix> | <Core Pillar 1> | <Core Pillar 2> | <Differentiating Impact>" (approved prefixes: {approved_prefixes_str}).
2. Must contain exactly 4 pipe-delimited segments.
3. Word count must be strictly between 10 and 13 words total.
4. Avoid noun stacks, buzzword salads, narrow hardware/plumbing labels ({forbidden_plumbing_str}), and clichés.
5. Every X/Y/Z segment (segments 2, 3, and 4) MUST include an executive operating abstraction noun ({abstraction_nouns_str}), with zero digits, $, %, or employer/company names.
6. HARD SIGNAL FLOOR IN SEGMENTS 2..4: At least ONE of segments 2..4 MUST contain {platform_floor_str} (e.g., 'Agentic AI Platforms', 'AI Platform Architecture', or 'Runtime Governance'), AND at least ONE of segments 2..4 MUST contain {governance_floor_str} (e.g., 'Runtime Governance' or 'Governed AI Deployment').
7. Do NOT repeat the token 'AI' in more than 2 of the 4 segments, never invert English modifier ordering (e.g., write 'AI Partner Ecosystems' or 'Platform Commercialization', never 'Licensing AI Platform' or 'Partner AI Ecosystem'), and align segments to the Target Role (e.g., for Applied AI Architecture & Partnerships, pair AI Platform Architecture + Partner Ecosystems + Runtime Governance rather than off-target financial vertical modernization).
8. Ground all terms in the ALLOWED GROUNDED FACTS above and executive engineering leadership.

OUTPUT FORMAT:
Return a JSON object:
{{
  "repaired_headline": "SVP Engineering | ... | ... | ...",
  "rationale": "Explanation of fixes"
}}
"""
    return prompt


def _build_competencies_repair_prompt(
    current_competencies: list[dict[str, Any] | str],
    diagnostic: dict[str, Any],
    allowed_facts: list[dict[str, Any]] | None,
    targeting_context: dict[str, Any] | None,
) -> str:
    findings = diagnostic.get("findings") or []
    suggestions = diagnostic.get("remediation_suggestions") or []
    tc = dict(targeting_context or {})
    t_role = str(tc.get("target_title") or tc.get("target_role") or "Executive").strip()
    t_company = str(tc.get("target_company") or "Enterprise").strip()
    jd_excerpt = str(tc.get("jd_text") or "").strip()[:1500]
    briefing_excerpt = str(tc.get("briefing") or "").strip()[:800]
    facts_summary = _format_allowed_facts_for_prompt(allowed_facts, limit=30)

    comps_str = json.dumps(current_competencies, indent=2)
    forbidden_cred_str = ", ".join(f"'{tok.capitalize()}'" for tok in COMPETENCIES_FORBIDDEN_CREDENTIAL_TOKENS)

    prompt = f"""You are an elite executive resume editor. Your task is to repair the Core Competencies grid.

TARGETING CONTEXT ONLY — NOT PROOF (use for ATS/label prioritization only, never treat JD/briefing as candidate experience):
- Target Role: {t_role}
- Target Company: {t_company}
- JD Excerpt: {jd_excerpt or "(none)"}
- Briefing Excerpt: {briefing_excerpt or "(none)"}

ALLOWED GROUNDED FACTS (All competency terms MUST remain strictly grounded in these facts):
{chr(10).join(facts_summary) if facts_summary else "Preserve only capabilities grounded in the current competencies."}

CURRENT COMPETENCIES:
{comps_str}

DIAGNOSTIC FEEDBACK:
- Findings: {json.dumps(findings)}
- Suggestions: {json.dumps(suggestions)}

RULES:
1. Maintain 6 to 8 competency categories in target-relevance order (keep Cloud & Partner Ecosystems / Partner Applied AI Architecture FIRST for partnerships/alliances roles).
2. Each category must have a crisp category label and 3 to 5 specific grounded competency noun phrases, and EVERY competency term MUST be {COMPETENCIES_TERM_MIN_WORDS} to {COMPETENCIES_TERM_MAX_WORDS} words (STRICT HARD MAX: {COMPETENCIES_TERM_MAX_WORDS} words per term — any {COMPETENCIES_TERM_MAX_WORDS + 1}+ word phrase fails x2_competency_term_compact_word_count!).
3. No em-dashes (—) in labels; use clean colons or commas, NEVER use certification words ({forbidden_cred_str}), and ensure NO non-stopword repeats >3 times across the entire table.
4. Replace generic table-stakes phrases (like 'stakeholder alignment across delivery teams') with concrete SVP-level AI/cloud architecture mechanisms grounded in ALLOWED GROUNDED FACTS.
5. Preserve any existing allocation_claim_unit_id, source_skill_ids, competency_bundle_id, and frozen graph bindings when present.

OUTPUT FORMAT:
Return a JSON object:
{{
  "repaired_competencies": [
    {{
      "category_label": "Agentic Control Plane & Orchestration",
      "competency_bundle_id": "ccb_agentic_platforms",
      "terms": [
        {{"term": "Multi-agent orchestration control planes", "source_fact_id": "fact_engineering_platform_001", "source_fact_ids": ["fact_engineering_platform_001"], "allocation_claim_unit_id": "competencies:skill:01"}},
        {{"term": "Deterministic agentic workflow routing", "source_fact_id": "fact_slalom_007", "source_fact_ids": ["fact_slalom_007"]}},
        {{"term": "Sandboxed agent tool execution", "source_fact_id": "fact_slalom_009", "source_fact_ids": ["fact_slalom_009"]}}
      ]
    }}
  ],
  "rationale": "Explanation of fixes"
}}
"""
    return prompt


def _mock_repair(
    section_id: str,
    candidate_data: dict[str, Any],
    diagnostic: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """Deterministic fast-path repair when LLM is unavailable or for testing."""
    sec = section_id.lower()
    updated = dict(candidate_data)

    if sec == "executive_summary":
        text = str(candidate_data.get("resume_display_text") or "").strip()
        sentences = _split_into_sentences(text)
        flagged = diagnostic.get("cited_sentence_indexes") or []
        findings_str = " ".join(diagnostic.get("findings") or []).lower()

        while len(sentences) < 3:
            sentences.append(
                "Delivered measurable engineering leverage and operational velocity across enterprise platforms."
            )
        sentences = sentences[:4]

        if (3 in flagged or 4 in flagged or "credential dump" in findings_str) and len(sentences) >= 3:
            sentences[-1] = (
                "Orchestrated cross-functional operational improvements delivering measurable savings and resilience across enterprise platforms."
            )
        if 0 in flagged or 1 in flagged or "dynamic" in sentences[0].lower() or "generic" in findings_str:
            sentences[0] = (
                "Technology strategy executive who aligns large-scale platform engineering with enterprise business objectives."
            )

        updated["resume_display_text"] = " ".join(sentences)
        return updated, True, "deterministic_fast_path"

    elif sec == "headline":
        repaired = "SVP Engineering | Enterprise Platform Architecture | Cloud Systems | Global Delivery"
        updated["headline_line"] = repaired
        return updated, True, "deterministic_fast_path"

    elif sec == "competencies":
        comps = candidate_data.get("competencies")
        if isinstance(comps, list) and comps:
            cleaned = []
            for item in comps:
                if isinstance(item, dict):
                    disp_label = str(item.get("resume_display_label") or "").replace("—", ":").strip()
                    cat = str(
                        item.get("category_label")
                        or item.get("display_label")
                        or item.get("category")
                        or item.get("name")
                        or ""
                    ).replace("—", ":").strip()
                    cleaned_item = dict(item)
                    cleaned_item["category"] = cat
                    cleaned_item["category_label"] = cat
                    if "resume_display_label" in cleaned_item:
                        cleaned_item["resume_display_label"] = disp_label or cat
                    raw_terms = item.get("terms") or item.get("skills") or item.get("items") or []
                    cleaned_terms = []
                    for t in raw_terms:
                        if isinstance(t, dict):
                            t_copy = dict(t)
                            if "term" in t_copy:
                                t_copy["term"] = str(t_copy["term"]).replace("—", ":").strip()
                            if "text" in t_copy:
                                t_copy["text"] = str(t_copy["text"]).replace("—", ":").strip()
                            cleaned_terms.append(t_copy)
                        else:
                            cleaned_terms.append(str(t).replace("—", ":").strip())
                    cleaned_item["terms"] = cleaned_terms
                    cleaned_item["skills"] = [
                        str(t.get("term") or t.get("text") if isinstance(t, dict) else t)
                        .replace("—", ":")
                        .strip()
                        for t in cleaned_terms
                    ]
                    cleaned.append(cleaned_item)
                elif isinstance(item, str):
                    cleaned.append(item.replace("—", ":").strip())
            while len(cleaned) < 6:
                cleaned.append({"category": "Strategic Leadership", "category_label": "Strategic Leadership", "terms": ["Executive Alignment", "Talent Governance"], "skills": ["Executive Alignment", "Talent Governance"]})
            cleaned = cleaned[:8]
            updated["competencies"] = cleaned
        else:
            updated["competencies"] = [
                {"category": "Enterprise Architecture", "category_label": "Enterprise Architecture", "skills": ["Cloud Infrastructure", "Distributed Systems"], "terms": ["Cloud Infrastructure", "Distributed Systems"]},
                {"category": "Strategic AI Delivery", "category_label": "Strategic AI Delivery", "skills": ["LLM Evaluation", "Agentic Systems"], "terms": ["LLM Evaluation", "Agentic Systems"]},
                {"category": "Engineering Operations", "category_label": "Engineering Operations", "skills": ["DevOps Governance", "FinOps Optimization"], "terms": ["DevOps Governance", "FinOps Optimization"]},
                {"category": "Executive Leadership", "category_label": "Executive Leadership", "skills": ["Talent Density", "Board Communications"], "terms": ["Talent Density", "Board Communications"]},
                {"category": "Security & Resilience", "category_label": "Security & Resilience", "skills": ["Zero-Trust Posture", "SOC2 Governance"], "terms": ["Zero-Trust Posture", "SOC2 Governance"]},
                {"category": "Product Alignment", "category_label": "Product Alignment", "skills": ["Technical Roadmapping", "Commercial Velocity"], "terms": ["Technical Roadmapping", "Commercial Velocity"]},
            ]
        return updated, True, "deterministic_fast_path"

    return candidate_data, False, "none"


def _parse_ide_cli_json_response(cli_res: Any) -> dict[str, Any] | None:
    """Parse a JSON object from an `agy -p` AgyResult (structured_output, fenced, or prose-wrapped)."""
    structured = getattr(cli_res, "structured_output", None)
    if isinstance(structured, dict):
        return structured
    raw = str(getattr(cli_res, "response", None) or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    candidates = [fenced.group(1).strip()] if fenced else []
    clean = re.sub(r"^```(?:json)?\s*", "", raw)
    clean = re.sub(r"\s*```$", "", clean).strip()
    candidates.append(clean)
    first_brace = raw.find("{")
    last_brace = raw.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(raw[first_brace : last_brace + 1].strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            continue
    return None


def _call_llm_repair(
    section_id: str,
    prompt: str,
    model: str = DEFAULT_REPAIR_MODEL,
) -> dict[str, Any] | None:
    """Call Claude (drafter) or cross-family OpenAI (auditor) model for repair pass via standard transport."""
    from apps_rg.runtime.providers.ide_cli_generation import (
        ide_cli_generation_unavailable_reason,
        resolve_ide_cli_generation_slug,
        uses_ide_cli_generation,
    )

    is_openai_auditor = str(model).startswith("gpt-") or model == DEFAULT_AUDITOR_MODEL
    if is_openai_auditor:
        from apps_rg.runtime.judges.x1d_ide_cli import (
            ide_cli_unavailable_reason,
            second_judge_model,
            uses_ide_cli_judges,
        )

        if uses_ide_cli_judges(os.environ) and not ide_cli_unavailable_reason(os.environ):
            try:
                from apps_rg.runtime.providers.agy_cli_transport import run_agy

                drafter_ide_slug = resolve_ide_cli_generation_slug(DEFAULT_REPAIR_MODEL)
                auditor_ide_slug, _ = second_judge_model(section_id)
                if auditor_ide_slug == drafter_ide_slug:
                    auditor_ide_slug, _ = second_judge_model("executive_summary")
                cli_res = run_agy(
                    f"{prompt}\n\nReturn ONLY valid JSON with no markdown fences and no tool calls.",
                    model=auditor_ide_slug,
                    timeout_s=120,
                )
                return _parse_ide_cli_json_response(cli_res)
            except Exception:  # guardian: allow-broad-exception -- optional voice repair auditor returns None on CLI or parse failure
                return None
    if not is_openai_auditor and uses_ide_cli_generation(os.environ, model=model):
        if ide_cli_generation_unavailable_reason(os.environ):
            return None
        try:
            from apps_rg.runtime.model_capabilities import try_model_capabilities
            from apps_rg.runtime.providers.agy_cli_transport import (
                AgyTransportError,
                is_agy_model_quota_cooled_down,
                is_agy_quota_error,
                mark_agy_model_quota_exhausted,
                run_agy,
            )
            from apps_rg.runtime.providers.ide_cli_generation import ide_cli_generation_quota_backups

            def _prep_rep_slug(pin_s: str) -> tuple[str, str | None]:
                c = try_model_capabilities(pin_s)
                if c is not None and "low" in (c.reasoning_efforts or ()):
                    return (f"{pin_s[:-7]}-low" if pin_s.endswith("-medium") else pin_s, "low")
                return pin_s, None

            rep_cands: list[tuple[str, str | None]] = [_prep_rep_slug(resolve_ide_cli_generation_slug(model))]
            for b_pin in ide_cli_generation_quota_backups():
                b_slug, b_eff = _prep_rep_slug(b_pin)
                if all(x[0] != b_slug for x in rep_cands):
                    rep_cands.append((b_slug, b_eff))
            ordered_rep = [x for x in rep_cands if not is_agy_model_quota_cooled_down(x[0])] + [
                x for x in rep_cands if is_agy_model_quota_cooled_down(x[0])
            ]
            for idx_r, (cand_s, cand_e) in enumerate(ordered_rep):
                try:
                    cli_res = run_agy(
                        f"{prompt}\n\nReturn ONLY valid JSON with no markdown fences and no tool calls.",
                        model=cand_s,
                        effort=cand_e,
                        timeout_s=120,
                    )
                    return _parse_ide_cli_json_response(cli_res)
                except AgyTransportError as exc_r:
                    if is_agy_quota_error(exc_r) and idx_r + 1 < len(ordered_rep):
                        mark_agy_model_quota_exhausted(cand_s, str(exc_r))
                        continue
                    return None
        except Exception:  # guardian: allow-broad-exception -- optional voice repair returns None on CLI or parse failure
            return None
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        if is_openai_auditor
        else os.environ.get("ANTHROPIC_API_KEY")
    )
    if not api_key:
        return None

    try:
        import hashlib, urllib.request
        from apps_rg.runtime.model_registry import resolve
        from apps_rg.runtime.model_token_governor import reserve_apps_rg_model_tokens

        resolved = resolve("proof_judge.standard.openai_chatgpt" if is_openai_auditor else "repair.executive_voice")
        max_tokens = int(resolved.params.get("max_tokens", 512 if is_openai_auditor else 1024))
        reservation = reserve_apps_rg_model_tokens(
            artifact_dir=None,
            provider="openai_chatgpt" if is_openai_auditor else "external_claude",
            model=model,
            request_digest=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            prompt_text=prompt,
            max_output_tokens=max_tokens,
            stage="repair",
            section_id=section_id,
        )
        if not reservation.allowed:
            return None

        if is_openai_auditor:
            headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            body = {
                "model": model,
                "max_completion_tokens": max_tokens,
                "reasoning_effort": "low",
                "messages": [{"role": "user", "content": prompt}],
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
        else:
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
            body = {"model": model, "max_tokens": max_tokens, "temperature": 0.2, "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

        def _repair_http_timeout() -> int:
            try:
                from apps_rg.runtime.section_model_limits import runtime_limit_int

                return runtime_limit_int("bare_pipeline.http_timeout_seconds")
            except Exception:
                return 30  # ssot: exempt(HARDCODED_TIMEOUT)

        from apps_rg.runtime.providers.external_provider import urlopen_provider_request

        with urlopen_provider_request(req, timeout=_repair_http_timeout()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else {}
                raw_text = str((msg or {}).get("content") or "").strip()
            else:
                content_blocks = data.get("content", [])
                raw_text = "".join(
                    b.get("text", "") for b in content_blocks if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
            clean = raw_text
            if clean.startswith("```"):
                clean = re.sub(r"^```(?:json)?\s*", "", clean)
                clean = re.sub(r"\s*```$", "", clean)
            return json.loads(clean)
    except Exception:  # guardian: allow-broad-exception -- optional voice repair returns None on transport or parse failure so caller falls back safely
        return None


class ExecutiveVoiceRepairAgent:
    """Autonomous agent that diagnoses and repairs semantic voice flaws in key resume sections."""

    def __init__(self, model: str = DEFAULT_REPAIR_MODEL) -> None:
        self.model = model

    def repair(
        self,
        *,
        section_id: str,
        candidate_data: dict[str, Any],
        diagnostic: dict[str, Any],
        allowed_facts: list[dict[str, Any]] | None = None,
        targeting_context: dict[str, Any] | None = None,
        mock_mode: bool = False,
        artifact_dir: Path | None = None,
    ) -> tuple[dict[str, Any], ExecutiveVoiceRepairReceipt]:
        return repair_section_with_executive_voice_agent(
            section_id=section_id,
            candidate_data=candidate_data,
            diagnostic=diagnostic,
            allowed_facts=allowed_facts,
            targeting_context=targeting_context,
            mock_mode=mock_mode,
            artifact_dir=artifact_dir,
        )


def repair_section_with_executive_voice_agent(
    *,
    section_id: str,
    candidate_data: dict[str, Any],
    diagnostic: dict[str, Any],
    allowed_facts: list[dict[str, Any]] | None = None,
    targeting_context: dict[str, Any] | None = None,
    mock_mode: bool = False,
    artifact_dir: Path | None = None,
) -> tuple[dict[str, Any], ExecutiveVoiceRepairReceipt]:
    """Execute bounded executive voice repair for executive_summary, headline, or competencies."""
    sec = str(section_id).strip().lower()
    if sec not in {"executive_summary", "headline", "competencies"}:
        return candidate_data, ExecutiveVoiceRepairReceipt(
            section_id=sec, repair_attempted=False, repair_succeeded=False,
            repair_mechanism="none", diagnostic_summary=diagnostic,
            notes=f"section {sec!r} not in Executive Voice repair scope",
        )
    if not executive_voice_repair_enabled():
        return candidate_data, ExecutiveVoiceRepairReceipt(
            section_id=sec, repair_attempted=False, repair_succeeded=False,
            repair_mechanism="none", diagnostic_summary=diagnostic,
            notes="Executive voice repair disabled via configuration",
        )
    if not diagnostic.get("repair_needed", False):
        return candidate_data, ExecutiveVoiceRepairReceipt(
            section_id=sec, repair_attempted=False, repair_succeeded=True,
            repair_mechanism="none", diagnostic_summary=diagnostic,
            notes="Section already passes X1D; no repair needed",
        )

    original_snippet = ""
    if sec == "executive_summary":
        original_snippet = str(candidate_data.get("resume_display_text") or "")[:200]
    elif sec == "headline":
        original_snippet = str(candidate_data.get("headline_line") or "")
    elif sec == "competencies":
        comps = candidate_data.get("competencies") or []
        original_snippet = f"{len(comps)} categories"

    from apps_rg.runtime.env_bootstrap import get_env_str, is_pytest_or_test_harness_env
    from apps_rg.runtime.providers.ide_cli_generation import (
        ide_cli_generation_unavailable_reason,
        uses_ide_cli_generation,
    )

    is_test = is_pytest_or_test_harness_env() or ("pytest" in sys.modules)
    is_ide_cli_ready = uses_ide_cli_generation(model=DEFAULT_REPAIR_MODEL) and not ide_cli_generation_unavailable_reason()
    is_live_key_present = bool(get_env_str("ANTHROPIC_API_KEY")) or is_ide_cli_ready

    if not mock_mode and not is_live_key_present and not is_test:
        raise RuntimeError(
            f"LIVE_REPAIR_KEY_REQUIRED: ANTHROPIC_API_KEY is not configured (and IDE CLI transport is unavailable) for ExecutiveVoiceRepairAgent on '{sec}'. "
            "Silent mock degradation is strictly forbidden in production runtime."
        )

    if mock_mode or (not is_live_key_present and is_test):
        updated_data, ok, mech = _mock_repair(sec, candidate_data, diagnostic)
        repaired_snippet = ""
        if sec == "executive_summary":
            repaired_snippet = str(updated_data.get("resume_display_text") or "")[:200]
        elif sec == "headline":
            repaired_snippet = str(updated_data.get("headline_line") or "")
        elif sec == "competencies":
            comps = updated_data.get("competencies") or []
            repaired_snippet = f"{len(comps)} categories"

        receipt = ExecutiveVoiceRepairReceipt(
            section_id=sec,
            repair_attempted=True,
            repair_succeeded=ok,
            repair_mechanism=mech,
            diagnostic_summary=diagnostic,
            repaired_fields=(
                ("resume_display_text",)
                if sec == "executive_summary"
                else ("headline_line",)
                if sec == "headline"
                else ("competencies",)
            ),
            original_snippet=original_snippet,
            repaired_snippet=repaired_snippet,
            notes="Deterministic mock repair executed successfully",
        )
        from apps_rg.runtime.providers.wallclock_http_guard import is_lane_or_dir_cancelled
        if artifact_dir and not is_lane_or_dir_cancelled(artifact_dir):
            try:
                (artifact_dir / "x1_repair_receipt.json").write_text(
                    json.dumps(receipt.to_dict(), indent=2), encoding="utf-8"
                )
            except OSError:
                pass
        return updated_data, receipt

    updated_data = dict(candidate_data)
    ok = False
    mech = "llm_repair_agent"

    if sec == "executive_summary":
        prompt = _build_executive_summary_repair_prompt(
            str(candidate_data.get("resume_display_text") or ""), diagnostic, allowed_facts, targeting_context,
        )
        resp = _call_llm_repair(sec, prompt, model=DEFAULT_REPAIR_MODEL)
        if resp and isinstance(resp.get("repaired_text"), str):
            proposed_text = resp["repaired_text"].strip()
            auditor_prompt = (
                f"You are a strict cross-family factual auditor. Audit the candidate revision against ALLOWED FACTS: {json.dumps(allowed_facts or [])}.\n"
                f"Candidate Draft:\n{proposed_text}\n\n"
                'Return ONLY a JSON object with this exact schema:\n{"disposition": "PASS" | "FAIL", "violated_facts": [], "repair_hint": ""}'
            )
            audit_resp = _call_llm_repair(sec, auditor_prompt, model=DEFAULT_AUDITOR_MODEL)
            if isinstance(audit_resp, dict) and str(audit_resp.get("disposition", "")).upper() == "PASS" and not audit_resp.get("violated_facts"):
                repaired_sents = _split_into_sentences(proposed_text)
                if 3 <= len(repaired_sents) <= 4:
                    updated_data["resume_display_text"] = proposed_text
                    prior_ledger = updated_data.get("claim_ledger")
                    if isinstance(prior_ledger, list) and prior_ledger:
                        all_prior_ids: list[str] = []
                        for row in prior_ledger:
                            if isinstance(row, dict):
                                for fid in row.get("source_fact_ids") or []:
                                    s = str(fid).strip()
                                    if s and s not in all_prior_ids:
                                        all_prior_ids.append(s)
                        synced_ledger: list[dict[str, Any]] = []
                        for idx, sent in enumerate(repaired_sents):
                            base_row = (
                                dict(prior_ledger[idx])
                                if idx < len(prior_ledger) and isinstance(prior_ledger[idx], dict)
                                else {"source_fact_ids": list(all_prior_ids)}
                            )
                            base_row["claim_text"] = sent
                            base_row["claim"] = sent[:80]
                            synced_ledger.append(base_row)
                        updated_data["claim_ledger"] = synced_ledger
                    ok = True
                    mech = "a2a_socratic_repair_loop"
            else:
                mech = "a2a_socratic_repair_loop_failed_audit"

    elif sec == "headline":
        from apps_rg.runtime.validators.headline_x2 import (
            HEADLINE_WORD_MAX,
            HEADLINE_WORD_MIN,
            has_valid_headline_prefix,
            headline_word_count,
        )

        prompt = _build_headline_repair_prompt(
            str(candidate_data.get("headline_line") or ""), diagnostic, allowed_facts, targeting_context,
        )
        resp = _call_llm_repair(sec, prompt, model=DEFAULT_REPAIR_MODEL)
        if resp and isinstance(resp.get("repaired_headline"), str):
            hl = resp["repaired_headline"].strip()
            parts = [p.strip() for p in hl.split("|")]
            wc = headline_word_count(hl)
            if (
                len(parts) == 4
                and has_valid_headline_prefix(hl)
                and HEADLINE_WORD_MIN <= wc <= HEADLINE_WORD_MAX
            ):
                updated_data["headline_line"] = hl
                ok = True

    elif sec == "competencies":
        comps_in = list(candidate_data.get("competencies") or [])
        prompt = _build_competencies_repair_prompt(comps_in, diagnostic, allowed_facts, targeting_context)
        resp = _call_llm_repair(sec, prompt, model=DEFAULT_REPAIR_MODEL)
        repaired_list = resp.get("repaired_competencies") if isinstance(resp, dict) else None
        if isinstance(repaired_list, list) and 6 <= len(repaired_list) <= 8:
            has_structured_terms = any(
                isinstance(t, dict)
                for c in comps_in
                if isinstance(c, dict)
                for t in (c.get("terms") or [])
            )
            if has_structured_terms:
                def _norm_label(val: Any) -> str:
                    return re.sub(r"[^a-z0-9]+", " ", str(val or "").lower()).strip()

                orig_dicts = [c for c in comps_in if isinstance(c, dict)]
                allowed_fact_id_pool: list[str] = []
                for af in allowed_facts or []:
                    if isinstance(af, dict):
                        fid = str(af.get("fact_id") or af.get("assertion_id") or "").strip()
                        if fid and fid not in allowed_fact_id_pool:
                            allowed_fact_id_pool.append(fid)
                all_orig_fact_ids: list[str] = []
                for oc in orig_dicts:
                    for fid in oc.get("source_fact_ids") or []:
                        sf = str(fid).strip()
                        if sf and sf not in all_orig_fact_ids:
                            all_orig_fact_ids.append(sf)
                    for ot in oc.get("terms") or []:
                        if isinstance(ot, dict):
                            for fid in ot.get("source_fact_ids") or ([ot.get("source_fact_id")] if ot.get("source_fact_id") else []):
                                sf = str(fid or "").strip()
                                if sf and sf not in all_orig_fact_ids:
                                    all_orig_fact_ids.append(sf)
                allowed_ids_set = set(allowed_fact_id_pool) | set(all_orig_fact_ids)
                fallback_fact_pool = all_orig_fact_ids or allowed_fact_id_pool

                by_bundle_id: dict[str, tuple[int, dict[str, Any]]] = {}
                by_label: dict[str, tuple[int, dict[str, Any]]] = {}
                for o_idx, oc in enumerate(orig_dicts):
                    for k in ("competency_bundle_id", "category_id"):
                        v = str(oc.get(k) or "").strip()
                        if v and v not in by_bundle_id:
                            by_bundle_id[v] = (o_idx, oc)
                    for k in ("category_label", "category", "resume_display_label", "label"):
                        nl = _norm_label(oc.get(k))
                        if nl and nl not in by_label:
                            by_label[nl] = (o_idx, oc)

                used_orig_indices: set[int] = set()
                merged_comps: list[dict[str, Any]] = []
                if not all(isinstance(rep_cat, dict) for rep_cat in repaired_list):
                    repaired_list_valid = False
                else:
                    repaired_list_valid = True
                if repaired_list_valid:
                    matched_indices: list[int | None] = [None] * len(repaired_list)
                    matched_identity_flags: list[bool] = [False] * len(repaired_list)
                    # Pass 1a: match by explicit competency_bundle_id / category_id first
                    for idx_c, rep_cat in enumerate(repaired_list):
                        for k in ("competency_bundle_id", "category_id"):
                            v = str(rep_cat.get(k) or "").strip()
                            if v and v in by_bundle_id and by_bundle_id[v][0] not in used_orig_indices:
                                m_idx = by_bundle_id[v][0]
                                matched_indices[idx_c] = m_idx
                                matched_identity_flags[idx_c] = True
                                used_orig_indices.add(m_idx)
                                break
                    # Pass 1b: match remaining entries by normalized category label
                    for idx_c, rep_cat in enumerate(repaired_list):
                        if matched_indices[idx_c] is not None:
                            continue
                        for k in ("category_label", "category", "resume_display_label", "label"):
                            nl = _norm_label(rep_cat.get(k))
                            if nl and nl in by_label and by_label[nl][0] not in used_orig_indices:
                                m_idx = by_label[nl][0]
                                matched_indices[idx_c] = m_idx
                                matched_identity_flags[idx_c] = True
                                used_orig_indices.add(m_idx)
                                break
                    # Pass 2: positional fallback only over remaining unused orig_dicts (matched_identity=False)
                    remaining_unused = [i for i in range(len(orig_dicts)) if i not in used_orig_indices]
                    for idx_c in range(len(repaired_list)):
                        if matched_indices[idx_c] is not None:
                            continue
                        if idx_c < len(orig_dicts) and idx_c not in used_orig_indices:
                            matched_indices[idx_c] = idx_c
                            remaining_unused.remove(idx_c)
                            used_orig_indices.add(idx_c)
                        elif remaining_unused:
                            pick = remaining_unused.pop(0)
                            matched_indices[idx_c] = pick
                            used_orig_indices.add(pick)
                for idx_c, rep_cat in enumerate(repaired_list if repaired_list_valid else []):
                    m_idx = matched_indices[idx_c]
                    orig_cat = orig_dicts[m_idx] if m_idx is not None else {}
                    matched_identity = matched_identity_flags[idx_c]

                    cat_label = (
                        str(
                            rep_cat.get("category")
                            or rep_cat.get("category_label")
                            or rep_cat.get("label")
                            or orig_cat.get("category_label")
                            or orig_cat.get("category")
                            or ""
                        )
                        .replace("—", ":")
                        .strip()
                    )
                    parsed_skills: list[tuple[str, dict[str, Any] | None]] = []
                    for s in (rep_cat.get("skills") or rep_cat.get("terms") or []):
                        raw_txt = (s.get("term") or s.get("text") or "") if isinstance(s, dict) else s
                        cleaned_txt = str(raw_txt or "").replace("—", ":").strip()
                        if cleaned_txt:
                            parsed_skills.append((cleaned_txt, s if isinstance(s, dict) else None))
                    orig_terms = [t for t in (orig_cat.get("terms") or []) if isinstance(t, dict)]

                    rep_cat_fact_ids = [
                        str(fid).strip()
                        for fid in (rep_cat.get("source_fact_ids") or [])
                        if str(fid).strip() and (not allowed_ids_set or str(fid).strip() in allowed_ids_set)
                    ]
                    orig_cat_fact_ids: list[str] = []
                    for ot in orig_terms:
                        for fid in ot.get("source_fact_ids") or ([ot.get("source_fact_id")] if ot.get("source_fact_id") else []):
                            sf = str(fid or "").strip()
                            if sf and sf not in orig_cat_fact_ids:
                                orig_cat_fact_ids.append(sf)
                    for fid in orig_cat.get("source_fact_ids") or []:
                        sf = str(fid).strip()
                        if sf and sf not in orig_cat_fact_ids:
                            orig_cat_fact_ids.append(sf)

                    cat_fact_ids = rep_cat_fact_ids or orig_cat_fact_ids or list(fallback_fact_pool[:2])
                    if not cat_label or not parsed_skills or not cat_fact_ids:
                        merged_comps = []
                        break

                    rebuilt_terms: list[dict[str, Any]] = []
                    for idx_t, (skill_str, rep_term_dict) in enumerate(parsed_skills[:4]):
                        template_t = dict(orig_terms[idx_t]) if (matched_identity and idx_t < len(orig_terms)) else {}
                        template_t["term"] = skill_str
                        template_t["text"] = skill_str
                        rep_t_sids: list[str] = []
                        if rep_term_dict is not None:
                            rep_alloc_uid = str(rep_term_dict.get("allocation_claim_unit_id") or "").strip()
                            if rep_alloc_uid:
                                template_t["allocation_claim_unit_id"] = rep_alloc_uid
                            if isinstance(rep_term_dict.get("source_skill_ids"), list) and rep_term_dict.get("source_skill_ids"):
                                template_t["source_skill_ids"] = [str(x) for x in rep_term_dict["source_skill_ids"] if str(x).strip()]
                            raw_t_sids = list(rep_term_dict.get("source_fact_ids") or [])
                            if rep_term_dict.get("source_fact_id"):
                                raw_t_sids = [rep_term_dict.get("source_fact_id"), *raw_t_sids]
                            for fid in raw_t_sids:
                                sf = str(fid or "").strip()
                                if sf and (not allowed_ids_set or sf in allowed_ids_set) and sf not in rep_t_sids:
                                    rep_t_sids.append(sf)
                        if rep_t_sids:
                            t_sids = rep_t_sids
                        else:
                            t_sids = [
                                str(fid).strip()
                                for fid in (template_t.get("source_fact_ids") or [])
                                if str(fid).strip()
                            ]
                            if not t_sids:
                                t_sids = list(cat_fact_ids[:2])
                        template_t["source_fact_ids"] = t_sids
                        template_t["source_fact_id"] = t_sids[0]
                        rebuilt_terms.append(template_t)

                    from apps_rg.runtime.sections.competencies_v3_contract import (
                        resolve_approved_category_label,
                    )
                    from apps_rg.runtime.sections.competency_capability_evidence import (
                        visible_graph_surface_taxonomy_for_bundle,
                    )

                    updated_cat = dict(orig_cat) if (orig_cat and matched_identity) else {}
                    if not matched_identity:
                        for id_key in ("competency_bundle_id", "category_id"):
                            id_val = str(rep_cat.get(id_key) or "").strip()
                            if id_val:
                                updated_cat[id_key] = id_val
                    eff_bundle_id = str(
                        updated_cat.get("competency_bundle_id")
                        or rep_cat.get("competency_bundle_id")
                        or (orig_cat.get("competency_bundle_id") if matched_identity else "")
                        or ""
                    ).strip()
                    tax_id, tax_lbl = (
                        visible_graph_surface_taxonomy_for_bundle(eff_bundle_id)
                        if eff_bundle_id
                        else ("", "")
                    )
                    approved_lbl = (
                        resolve_approved_category_label(cat_label)
                        or tax_lbl
                        or (
                            resolve_approved_category_label(str(orig_cat.get("category_label") or ""))
                            if matched_identity
                            else None
                        )
                        or cat_label
                    )
                    if eff_bundle_id:
                        updated_cat["competency_bundle_id"] = eff_bundle_id
                    if tax_id and not updated_cat.get("category_id"):
                        updated_cat["category_id"] = tax_id
                    if tax_id and not updated_cat.get("taxonomy_category_id"):
                        updated_cat["taxonomy_category_id"] = tax_id
                    updated_cat["category"] = approved_lbl
                    updated_cat["category_label"] = approved_lbl
                    if "resume_display_label" in updated_cat or cat_label != approved_lbl:
                        updated_cat["resume_display_label"] = cat_label
                    updated_cat["terms"] = rebuilt_terms
                    updated_cat["skills"] = [t["term"] for t in rebuilt_terms]
                    updated_cat["source_fact_ids"] = list(cat_fact_ids)
                    merged_comps.append(updated_cat)
                if merged_comps:
                    updated_data["competencies"] = merged_comps
                    ok = True
                    mech = "llm_repair_agent"
            elif not has_structured_terms:
                updated_data["competencies"] = repaired_list
                ok = True
                mech = "llm_repair_agent"

    if not ok:
        if mock_mode or is_test:
            updated_data, ok, mech = _mock_repair(sec, candidate_data, diagnostic)
        else:
            mech, updated_data = "llm_repair_unresolved", dict(candidate_data)

    repaired_snippet = (
        str(updated_data.get("resume_display_text") or "")[:200] if sec == "executive_summary"
        else str(updated_data.get("headline_line") or "") if sec == "headline"
        else f"{len(updated_data.get('competencies') or [])} categories"
    )
    receipt = ExecutiveVoiceRepairReceipt(
        section_id=sec, repair_attempted=True, repair_succeeded=ok, repair_mechanism=mech,
        diagnostic_summary=diagnostic,
        repaired_fields=(("resume_display_text",) if sec == "executive_summary" else ("headline_line",) if sec == "headline" else ("competencies",)),
        original_snippet=original_snippet, repaired_snippet=repaired_snippet,
        notes="LLM repair pass executed" if mech == "llm_repair_agent" else "Fallback repair executed",
    )
    from apps_rg.runtime.providers.wallclock_http_guard import is_lane_or_dir_cancelled
    if artifact_dir and not is_lane_or_dir_cancelled(artifact_dir):
        try:
            (artifact_dir / "x1_repair_receipt.json").write_text(json.dumps(receipt.to_dict(), indent=2), encoding="utf-8")
        except OSError:
            pass
    return updated_data, receipt


X1RepairAgent, X1RepairReceipt = ExecutiveVoiceRepairAgent, ExecutiveVoiceRepairReceipt
repair_section_with_x1_agent, x1_repair_enabled = repair_section_with_executive_voice_agent, executive_voice_repair_enabled
X1_REPAIR_MAX_ATTEMPTS, X1_REPAIR_AGENT_ENABLED_DEFAULT = EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS, EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT

__all__ = [
    "DEFAULT_AUDITOR_MODEL", "DEFAULT_REPAIR_MODEL", "ExecutiveVoiceRepairAgent", "ExecutiveVoiceRepairReceipt",
    "EXECUTIVE_VOICE_REPAIR_AGENT_ENABLED_DEFAULT", "EXECUTIVE_VOICE_REPAIR_MAX_ATTEMPTS",
    "repair_section_with_executive_voice_agent", "executive_voice_repair_enabled", "_split_into_sentences",
    "X1RepairAgent", "X1RepairReceipt", "X1_REPAIR_AGENT_ENABLED_DEFAULT", "X1_REPAIR_MAX_ATTEMPTS",
    "repair_section_with_x1_agent", "x1_repair_enabled",
]

