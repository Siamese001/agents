"""Apps RG targeting brief synthesis, repair, sidecar, and X2 judge mixin."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from apps_research.engines.company_brief.shared import _cbe


class _CompanyBriefTargetingBriefMixin:
    """Provides apps_rg targeting markdown synthesis, validation, repair, and X2 judge wiring."""

    _UNSUPPORTED_LEADERSHIP_ROLE_RE = re.compile(
        r"\b(?:ceo|cto|cfo|coo|founder|co-founder|cofounder|president|"
        r"chief|executive|leadership|leader|strategic voice|stakeholder)\b",
        re.IGNORECASE,
    )
    _MARKDOWN_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
    _PERSON_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
    _NON_PERSON_NAME_PHRASES = {
        "Amazon Web Services",
        "Claude Partner Network",
        "Google Cloud",
        "Microsoft Azure",
    }

    def _synthesize_apps_rg_targeting_brief(
        self,
        *,
        topic: str,
        findings: Dict[str, str],
        jd_context: Dict[str, Any],
        jd_anchor: Optional[Path],
        gate_verdict: str = "",
        gate_reason: str = "",
    ) -> Dict[str, Any]:
        """Synthesize the apps_rg briefing packet as a sealed markdown artifact.

        The company is identified strictly from ``company_name`` (falls back to
        ``topic`` only when absent) so the JD/role never pollutes company
        identification. The JD is passed as relevance context only.
        """
        from apps_research.integrations.apps_rg_handoff import (  # noqa: PLC0415
            x2_judge_receipt_passes,
        )
        from apps_research.prompt_assembly.apps_rg_targeting_brief import (  # noqa: PLC0415
            build_targeting_brief_prompt,
            extract_jd_text,
            format_research_findings,
        )
        from apps_research.types.apps_rg_targeting_brief_contract import (  # noqa: PLC0415
            BriefStatus,
            assess_targeting_brief_semantics,
            fit_targeting_brief_to_budget,
            normalize_targeting_brief_text,
            seal_targeting_brief,
        )

        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        company_name = str(jd_context.get("company_name") or "").strip() or topic
        jd_text = extract_jd_text(jd_context=jd_context, jd_anchor=jd_anchor)
        research_notes = format_research_findings(findings)
        has_research = bool(research_notes.strip())
        gate_failed = str(gate_verdict).upper() in {"FAIL", "EMPTY", "CONFLICTED"}
        if not has_research or gate_failed:
            raise unavailable_err(
                f"{company_name}: apps_rg targeting brief blocked: "
                f"{gate_reason or ('c0_support_gate_failed' if gate_failed else 'no_grounded_research_for_company')}"
            )

        prompt = build_targeting_brief_prompt(
            jd_text=jd_text,
            research_notes=research_notes,
            target_entity=company_name,
        )
        markdown = self._call_llm_plain_markdown(prompt).strip()

        if not markdown or markdown.upper().startswith("BLOCKED:"):
            raise unavailable_err(
                f"{company_name}: apps_rg targeting brief synthesis returned "
                f"{markdown[:120] if markdown else 'synthesis_returned_empty'}"
            )

        normalized = normalize_targeting_brief_text(
            markdown,
            jd_text=jd_text,
            profile="apps_rg",
        )
        normalized = self._drop_unsupported_named_leadership_claims(
            normalized,
            research_notes=research_notes,
        )
        brief_for_seal = normalized
        budget_repair: dict[str, Any] = {
            "applied": False,
            "strategy": "preserve_whole_bullets_per_section",
            "before_char_count": len(brief_for_seal),
            "after_char_count": len(brief_for_seal),
        }
        sealed = seal_targeting_brief(
            brief_for_seal,
            company_name=company_name,
            jd_text=jd_text,
            profile="apps_rg",
        )
        if not sealed.is_sealed:
            scrubbed = self._drop_jd_restatement_bullets(brief_for_seal, sealed.violations)
            if scrubbed != brief_for_seal:
                brief_for_seal = scrubbed
                sealed = seal_targeting_brief(
                    brief_for_seal,
                    company_name=company_name,
                    jd_text=jd_text,
                    profile="apps_rg",
                )
        if not sealed.is_sealed:
            fitted = fit_targeting_brief_to_budget(
                brief_for_seal,
                profile="apps_rg",
            )
            if fitted != brief_for_seal:
                budget_repair = {
                    "applied": True,
                    "strategy": "preserve_whole_bullets_per_section",
                    "before_char_count": len(brief_for_seal),
                    "after_char_count": len(fitted),
                }
                brief_for_seal = fitted
                sealed = seal_targeting_brief(
                    brief_for_seal,
                    company_name=company_name,
                    jd_text=jd_text,
                    profile="apps_rg",
                )
        if not sealed.is_sealed:
            repaired = self._repair_apps_rg_targeting_brief_markdown(
                company_name=company_name,
                draft_markdown=brief_for_seal,
                jd_text=jd_text,
                research_notes=research_notes,
                gate_verdict=gate_verdict,
                gate_reason=gate_reason,
                violations=sealed.violations,
            )
            if repaired.strip() and repaired.strip() != normalized:
                repaired_normalized = normalize_targeting_brief_text(
                    repaired,
                    jd_text=jd_text,
                    profile="apps_rg",
                )
                repaired_normalized = self._drop_unsupported_named_leadership_claims(
                    repaired_normalized,
                    research_notes=research_notes,
                )
                repaired_normalized = fit_targeting_brief_to_budget(
                    repaired_normalized,
                    profile="apps_rg",
                )
                sealed = seal_targeting_brief(
                    repaired_normalized,
                    company_name=company_name,
                    jd_text=jd_text,
                    profile="apps_rg",
                )
                if not sealed.is_sealed:
                    scrubbed = self._drop_jd_restatement_bullets(
                        repaired_normalized,
                        sealed.violations,
                    )
                    if scrubbed != repaired_normalized:
                        sealed = seal_targeting_brief(
                            scrubbed,
                            company_name=company_name,
                            jd_text=jd_text,
                            profile="apps_rg",
                        )
        if not sealed.is_sealed:
            violations = ",".join(sealed.violations) if sealed.violations else "none"
            raise unavailable_err(
                f"{company_name}: apps_rg targeting brief rejected: "
                f"{sealed.block_reason or 'contract_validation_failed'}; violations={violations}"
            )
        semantic_assessment = assess_targeting_brief_semantics(
            sealed.company_brief_text,
            jd_text=jd_text,
            research_notes=research_notes,
            source_family_keys=tuple(findings.keys()),
            profile="apps_rg",
        )
        source_register = [
            {
                "family": family,
                "has_content": bool((blob or "").strip()),
                "char_count": len((blob or "").strip()),
            }
            for family, blob in sorted(findings.items(), key=lambda item: item[0])
        ]
        x2_judge_receipt = self._run_apps_rg_handoff_x2_judge(
            brief_text=sealed.company_brief_text,
            jd_text=jd_text,
            research_notes=research_notes,
            source_register=source_register,
        )
        if not x2_judge_receipt_passes(x2_judge_receipt):
            diagnostic_ref = self._persist_x2_blocked_receipt(
                company_name=company_name,
                brief_text=sealed.company_brief_text,
                jd_text=jd_text,
                x2_judge_receipt=x2_judge_receipt,
                source_register=source_register,
            )
            diagnostic_suffix = f"; diagnostic_ref={diagnostic_ref}" if diagnostic_ref else ""
            raise unavailable_err(
                f"{company_name}: apps_rg targeting brief X2 judge failed: "
                f"{x2_judge_receipt.get('status', 'MISSING_RECEIPT')}; "
                f"reason={x2_judge_receipt.get('reason', 'missing_model_backed_pass')}"
                f"{diagnostic_suffix}"
            )
        model_name = str(
            getattr(self, "_last_targeting_generation_model_observed", "") or ""
        ).strip()
        if not model_name:
            raise unavailable_err(
                f"{company_name}: targeting brief generation model was not observed"
            )
        return {
            "synthesis_template": "apps_rg_targeting_brief_synthesis_v1",
            "apps_rg_targeting_brief_markdown": sealed.company_brief_text,
            "apps_rg_targeting_brief_sidecar": self._build_targeting_brief_sidecar(
                company_name=company_name,
                brief_text=sealed.company_brief_text,
                jd_text=jd_text,
                research_notes=research_notes,
                findings=findings,
                gate_verdict=gate_verdict,
                gate_reason=gate_reason,
                model_name=model_name,
                semantic_override=semantic_assessment,
                x2_judge_receipt=x2_judge_receipt,
                source_register=source_register,
                budget_repair=budget_repair,
            ),
            "targeting_brief_disposition": BriefStatus.SEALED.value,
            "targeting_brief_char_count": sealed.char_count,
            "targeting_brief_bullet_count": sealed.bullet_count,
            "targeting_brief_section_count": sealed.section_count,
        }

    def _repair_apps_rg_targeting_brief_markdown(
        self,
        *,
        company_name: str,
        draft_markdown: str,
        jd_text: str,
        research_notes: str,
        gate_verdict: str,
        gate_reason: str,
        violations: tuple[str, ...],
    ) -> str:
        """Bounded second-pass repair for contract-invalid targeting drafts."""
        violation_text = ", ".join(violations[:8]) if violations else "contract_validation_failed"
        prompt = (
            "Repair this apps_rg targeting brief so it seals cleanly.\n"
            f"Company: {company_name}\n"
            f"Gate verdict: {gate_verdict or 'unknown'}\n"
            f"Gate reason: {gate_reason or 'none'}\n"
            f"Violations: {violation_text}\n\n"
            "Rules: preserve the same company and section structure; keep the metadata line; "
            "target 4,000 to 6,500 total characters and never exceed the hard 8,000-character ceiling; "
            "do not restate JD responsibilities or copy any 4-word JD phrase; keep bullets one "
            "level deep; wrap every line to 240 characters or less; remove citations, links, "
            "placeholders, and code fences; do not name specific executives unless the exact "
            "person name appears in the research notes; output markdown only.\n\n"
            f"JD (context only):\n{jd_text}\n\n"
            f"Research notes:\n{research_notes}\n\n"
            f"Draft to repair:\n{draft_markdown}\n"
        )
        repaired = self._call_llm_plain_markdown(prompt).strip()
        if repaired.upper().startswith("BLOCKED:"):
            return ""
        return repaired

    @staticmethod
    def _drop_jd_restatement_bullets(markdown: str, violations: tuple[str, ...]) -> str:
        """Remove bullet lines explicitly identified as JD restatements."""
        snippets = [
            value.split(":", 1)[1].strip().lower()
            for value in violations
            if value.startswith("jd_restatement_in_bullet_text:") and ":" in value
        ]
        if not snippets:
            return markdown

        kept_lines: list[str] = []
        for raw_line in str(markdown or "").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("- "):
                bullet = stripped[2:].strip().lower()
                if any(snippet and snippet in bullet for snippet in snippets):
                    continue
            kept_lines.append(raw_line)
        return "\n".join(kept_lines).strip()

    @classmethod
    def _unsupported_person_names(cls, text: str, *, research_notes: str) -> list[str]:
        notes = str(research_notes or "").lower()
        out: list[str] = []
        for match in cls._PERSON_NAME_RE.finditer(str(text or "")):
            name = match.group(1).strip()
            if name in cls._NON_PERSON_NAME_PHRASES:
                continue
            if name.lower() in notes:
                continue
            if name not in out:
                out.append(name)
        return out

    @classmethod
    def _drop_unsupported_named_leadership_claims(
        cls,
        markdown: str,
        *,
        research_notes: str,
    ) -> str:
        """Remove named leadership claims when the retrieved notes do not contain the name."""
        kept_lines: list[str] = []
        for raw_line in str(markdown or "").splitlines():
            line = raw_line.rstrip()
            if cls._MARKDOWN_HEADER_RE.match(line):
                kept_lines.append(raw_line)
                continue
            if not cls._UNSUPPORTED_LEADERSHIP_ROLE_RE.search(line):
                kept_lines.append(raw_line)
                continue

            sentences = re.split(r"(?<=[.!?])\s+", line)
            kept_sentences: list[str] = []
            for sentence in sentences:
                unsupported = cls._unsupported_person_names(
                    sentence,
                    research_notes=research_notes,
                )
                if unsupported and cls._UNSUPPORTED_LEADERSHIP_ROLE_RE.search(sentence):
                    continue
                kept_sentences.append(sentence)

            rebuilt = " ".join(s.strip() for s in kept_sentences if s.strip()).strip()
            if rebuilt:
                kept_lines.append(rebuilt)
        return "\n".join(kept_lines).strip()

    def _build_targeting_brief_sidecar(
        self,
        *,
        company_name: str,
        brief_text: str,
        jd_text: str,
        research_notes: str,
        findings: Dict[str, str],
        gate_verdict: str,
        gate_reason: str,
        model_name: str,
        semantic_override: Any | None = None,
        x2_judge_receipt: dict[str, Any] | None = None,
        source_register: list[dict[str, Any]] | None = None,
        budget_repair: dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build the structured sidecar carried from apps_research to apps_rg."""
        from apps_research.integrations.apps_rg_handoff import (  # noqa: PLC0415
            APPS_RG_HANDOFF_GENERATION_PROVIDER,
            x2_judge_receipt_passes,
        )
        from apps_research.integrations.search_retrieval import retrieval_config_snapshot  # noqa: PLC0415
        from apps_research.types.apps_rg_targeting_brief_contract import (  # noqa: PLC0415
            assess_targeting_brief_semantics,
            validate_targeting_brief_text,
        )

        brief_model = _cbe("APPS_RESEARCH_BRIEF_MODEL")
        brief_effort = _cbe("APPS_RESEARCH_BRIEF_REASONING_EFFORT")
        max_tokens_fn = _cbe("_resolved_gemini_max_output_tokens")

        semantics = semantic_override or assess_targeting_brief_semantics(
            brief_text,
            jd_text=jd_text,
            research_notes=research_notes,
            source_family_keys=tuple(findings.keys()),
            profile="apps_rg",
        )
        validation = validate_targeting_brief_text(
            brief_text,
            jd_text=jd_text,
            profile="apps_rg",
        )
        resolved_source_register = source_register or [
            {
                "family": family,
                "has_content": bool((blob or "").strip()),
                "char_count": len((blob or "").strip()),
            }
            for family, blob in sorted(findings.items(), key=lambda item: item[0])
        ]
        judge_receipt = dict(x2_judge_receipt or {})
        model_backed_x2_passed = x2_judge_receipt_passes(judge_receipt)
        digest = hashlib.sha256(brief_text.encode("utf-8")).hexdigest() if brief_text else ""
        retrieval_snapshot = retrieval_config_snapshot(query_families=list(findings.keys()))
        semantic_score = judge_receipt.get("score", semantics.score)
        judge_name = judge_receipt.get("judge_name", semantics.judge_name)
        judge_model = judge_receipt.get("judge_model", semantics.judge_model)
        handoff_eligible = bool(semantics.handoff_eligible and model_backed_x2_passed)
        blocked_reason = "ok"
        if not handoff_eligible:
            blocked_reason = (
                "x2_model_backed_judge_not_pass"
                if not model_backed_x2_passed
                else str(getattr(semantics, "reason", "") or "semantic_handoff_not_eligible")
            )
        return {
            "schema_version": "apps_research.apps_rg_targeting_brief_sidecar/v1",
            "company_name": company_name,
            "generation_provider": APPS_RG_HANDOFF_GENERATION_PROVIDER,
            "generation_model_requested": brief_model,
            "generation_model": model_name,
            "generation_reasoning_effort": brief_effort,
            "generation_model_observation_status": "OBSERVED_PROVIDER_RESPONSE",
            "generation_provider_evidence": dict(
                getattr(self, "_last_targeting_generation_provider_receipt", {}) or {}
            ),
            "provider_call_attempted": True,
            "generation_token_budget": max_tokens_fn(),
            "judge_name": judge_name,
            "judge_model": judge_model,
            "briefing_semantic_score": semantic_score,
            "semantic_gate_mode": "model_backed_llm_judge",
            "handoff_eligible": handoff_eligible,
            "reason": blocked_reason,
            "x2_judge_receipt": judge_receipt,
            "deterministic_semantic_assessment": semantics.as_dict(),
            "role_archetype": semantics.role_archetype,
            "evidence_intents": list(semantics.evidence_intents),
            "required_sections_present": list(semantics.required_sections_present),
            "missing_sections": list(semantics.missing_sections),
            "source_families_present": list(semantics.source_families_present),
            "source_families_missing": list(semantics.source_families_missing),
            "signal_terms_present": list(semantics.signal_terms_present),
            "signal_terms_missing": list(semantics.signal_terms_missing),
            "retrieval_config": retrieval_snapshot,
            "source_register": resolved_source_register,
            "gate_verdict": gate_verdict,
            "gate_reason": gate_reason,
            "text_char_count": validation.char_count,
            "bullet_count": validation.bullet_count,
            "section_count": validation.section_count,
            "brief_text_sha256": digest,
            "budget_repair": dict(budget_repair or {}),
        }

    def _run_apps_rg_handoff_x2_judge(
        self,
        *,
        brief_text: str,
        jd_text: str,
        research_notes: str,
        source_register: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from apps_research.integrations.apps_rg_handoff import (  # noqa: PLC0415
            run_apps_rg_handoff_x2_judge,
        )

        return run_apps_rg_handoff_x2_judge(
            brief_text=brief_text,
            jd_text=jd_text,
            research_notes=research_notes,
            source_register=source_register,
        )

    def _persist_x2_blocked_receipt(
        self,
        *,
        company_name: str,
        brief_text: str,
        jd_text: str,
        x2_judge_receipt: dict[str, Any],
        source_register: list[dict[str, Any]],
    ) -> str:
        """Write fail-closed X2 diagnostics without authorizing handoff."""
        root_fn = _cbe("_source_repository_root")
        try:
            repo_root = root_fn()
            out_dir = repo_root / "artifacts" / "apps_research" / "x2_judge_failures"
            out_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(f"{company_name}\n{brief_text}".encode("utf-8")).hexdigest()[:12]
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = out_dir / f"{timestamp}_{digest}.json"
            payload = {
                "schema_version": "apps_research.x2_blocked_receipt.v1",
                "company_name": company_name,
                "emitted_at_utc": datetime.now(timezone.utc).isoformat(),
                "brief_text_sha256": hashlib.sha256(str(brief_text or "").encode("utf-8")).hexdigest(),
                "jd_text_sha256": hashlib.sha256(str(jd_text or "").encode("utf-8")).hexdigest(),
                "handoff_authorized": False,
                "x2_judge_receipt": dict(x2_judge_receipt or {}),
                "source_register": list(source_register or []),
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return str(path)
        except (OSError, TypeError, ValueError) as exc:
            self.logger.warning("[CompanyBriefEngine] failed to persist X2 blocked receipt: %s", exc)
            return ""


__all__ = ["_CompanyBriefTargetingBriefMixin"]
