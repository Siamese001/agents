"""LLM synthesis mixin for CompanyBriefEngine."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps_research.engines.company_brief.shared import _cbe


class _CompanyBriefSynthesisMixin:
    """Provides structured JSON synthesis, consumer briefs, and plain-markdown provider calls."""

    def _synthesize(
        self,
        *,
        topic: str,
        findings: Dict[str, str],
        jd_facets: List[str],
        depth: str,
        jd_context: Dict[str, Any] | None = None,
        jd_anchor: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """LLM-synthesize raw research into structured facets.

        The company brief path uses the pinned OpenAI model route for
        synthesis. When ``apps_rg_targeting_brief_enabled`` (env or
        jd_context), emits apps_rg targeting markdown per
        ``apps_rg_targeting_brief_v1.md``.
        """
        from apps_research.prompt_assembly.apps_rg_targeting_brief import (  # noqa: PLC0415
            apps_rg_targeting_brief_enabled,
        )
        from apps_research.prompt_assembly.consumer_briefs import (  # noqa: PLC0415
            consumer_brief_template_id,
        )

        consumer_template_id = consumer_brief_template_id(jd_context=jd_context)
        if apps_rg_targeting_brief_enabled(jd_context=jd_context):
            return self._synthesize_apps_rg_targeting_brief(
                topic=topic,
                findings=findings,
                jd_context=jd_context or {},
                jd_anchor=jd_anchor,
            )
        base_prompt = self._build_synthesis_prompt(topic=topic, findings=findings, jd_facets=jd_facets)
        base_synthesis = self._gemini_synthesize(prompt=base_prompt, topic=topic, jd_facets=jd_facets)
        if consumer_template_id in {
            "downstream_research_substrate_v1",
            "apps_lic_research_substrate_v1",
            "apps_exec_executive_brief_v1",
        }:
            consumer_keys = {
                "downstream_research_substrate_v1": (
                    "downstream_research_substrate_text",
                    "downstream_research_substrate_disposition",
                    "downstream_research_substrate_block_reason",
                ),
                "apps_lic_research_substrate_v1": (
                    "apps_lic_research_substrate_text",
                    "apps_lic_research_substrate_disposition",
                    "apps_lic_research_substrate_block_reason",
                ),
                "apps_exec_executive_brief_v1": (
                    "apps_exec_executive_brief_text",
                    "apps_exec_executive_brief_disposition",
                    "apps_exec_executive_brief_block_reason",
                ),
            }
            consumer_output_key, consumer_disposition_key, consumer_block_reason_key = consumer_keys[
                consumer_template_id
            ]
            consumer = self._synthesize_consumer_brief(
                topic=topic,
                findings=findings,
                jd_context=jd_context or {},
                jd_anchor=jd_anchor,
                template_id=consumer_template_id,
                output_key=consumer_output_key,
                disposition_key=consumer_disposition_key,
                block_reason_key=consumer_block_reason_key,
            )
            return {**base_synthesis, **consumer}

        return base_synthesis

    def _gemini_synthesize(
        self,
        *,
        prompt: str,
        topic: str,
        jd_facets: List[str],
    ) -> Dict[str, Any]:
        """Synthesize via the pinned OpenAI model route.

        Uses the pinned apps_research briefing model. Returns the parsed
        synthesis dict on success and fails closed on transport, empty-response,
        or parse failure.
        """
        enforce_budget = _cbe("_enforce_company_brief_prompt_budget")
        model_name = _cbe("APPS_RESEARCH_BRIEF_MODEL")
        invoke_openai = _cbe("invoke_openai_company_brief")
        system_prompt = _cbe("COMPANY_BRIEF_STATIC_SYSTEM_PROMPT")
        max_tokens_fn = _cbe("_resolved_gemini_max_output_tokens")
        emit_marker = _cbe("_emit_company_brief_marker")
        gateway_err = _cbe("AppsResearchProviderGatewayError")
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)

        enforce_budget(prompt)
        started = time.time()
        try:
            result = invoke_openai(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=max_tokens_fn(),
                application_validator=lambda text: self._parse_synthesis(
                    text,
                    topic=topic,
                    jd_facets=jd_facets,
                ),
            )
        except gateway_err as exc:
            self.logger.info("[CompanyBriefEngine] openai model=%s failed: %s", model_name, exc)
            emit_marker(
                accepted=False,
                model_used=model_name,
                fallback_reason=str(exc.receipt.get("validation_reason") or "openai_exception"),
                latency_ms=(time.time() - started) * 1000.0,
            )
            raise unavailable_err(
                f"{topic}: OpenAI synthesis failed for model={model_name}: {type(exc).__name__}: {exc}"
            ) from exc
        observed_model = str(result.receipt["observed_model"])
        self._last_company_brief_generation_model_observed = observed_model
        self._last_company_brief_generation_provider_receipt = dict(result.receipt)
        emit_marker(
            accepted=True,
            model_used=observed_model,
            fallback_reason="none",
            latency_ms=(time.time() - started) * 1000.0,
        )
        return dict(result.output)

    def _synthesize_consumer_brief(
        self,
        *,
        topic: str,
        findings: Dict[str, str],
        jd_context: Dict[str, Any],
        jd_anchor: Optional[Path],
        template_id: str,
        output_key: str,
        disposition_key: str,
        block_reason_key: str,
        gate_verdict: str = "",
        gate_reason: str = "",
    ) -> Dict[str, Any]:
        """Synthesize a compact downstream consumer brief."""
        from apps_research.prompt_assembly.consumer_briefs import (  # noqa: PLC0415
            build_consumer_brief_prompt,
            extract_jd_text,
            format_research_findings,
        )
        from apps_research.types.apps_rg_targeting_brief_contract import (  # noqa: PLC0415
            normalize_markdown_brief_text,
        )

        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        company_name = str(jd_context.get("company_name") or "").strip() or topic
        jd_text = extract_jd_text(jd_context=jd_context, jd_anchor=jd_anchor)
        research_notes = format_research_findings(findings)
        has_research = bool(research_notes.strip())
        gate_failed = str(gate_verdict).upper() in {"FAIL", "EMPTY", "CONFLICTED"}
        if not has_research or gate_failed:
            raise unavailable_err(
                f"{company_name}: consumer brief blocked: "
                f"{gate_reason or ('c0_support_gate_failed' if gate_failed else 'no_grounded_research_for_company')}"
            )

        prompt = build_consumer_brief_prompt(
            template_id=template_id,
            jd_text=jd_text,
            research_notes=research_notes,
            target_entity=company_name,
        )
        text = self._call_llm_plain_markdown(prompt).strip()
        if not text or text.upper().startswith("BLOCKED:"):
            raise unavailable_err(
                f"{company_name}: consumer brief synthesis returned "
                f"{text[:120] if text else 'synthesis_returned_empty'}"
            )

        brief_profile = "apps_lic" if template_id == "apps_lic_research_substrate_v1" else "apps_rg"
        text = normalize_markdown_brief_text(text, profile=brief_profile)
        return {
            "synthesis_template": template_id,
            "consumer_brief_template_id": template_id,
            "consumer_brief_output_key": output_key,
            output_key: text,
            "company_brief_text": text,
            disposition_key: "SEALED",
        }

    def _call_llm_plain_markdown(self, prompt: str) -> str:
        """OpenAI route for plain-text targeting brief output."""
        text = self._gemini_synthesize_plain(prompt=prompt)
        return text

    def _gemini_synthesize_plain(self, *, prompt: str) -> str:
        from apps_research.prompt_assembly.consumer_briefs import (  # noqa: PLC0415
            CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT,
        )

        enforce_budget = _cbe("_enforce_company_brief_prompt_budget")
        model_name = _cbe("APPS_RESEARCH_BRIEF_MODEL")
        invoke_openai = _cbe("invoke_openai_company_brief")
        max_tokens_fn = _cbe("_resolved_gemini_max_output_tokens")
        gateway_err = _cbe("AppsResearchProviderGatewayError")
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)

        enforce_budget(prompt)
        try:
            result = invoke_openai(
                messages=[
                    {"role": "system", "content": CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=max_tokens_fn(),
                application_validator=lambda text: text,
            )
        except gateway_err as exc:
            self.logger.info(
                "[CompanyBriefEngine] targeting brief openai model=%s failed: %s",
                model_name,
                exc,
            )
            raise unavailable_err(
                f"targeting brief OpenAI synthesis failed for model={model_name}: {type(exc).__name__}: {exc}"
            ) from exc
        observed_model = str(result.receipt["observed_model"])
        self._last_targeting_generation_model_observed = observed_model
        self._last_targeting_generation_provider_receipt = dict(result.receipt)
        return str(result.output)

    @staticmethod
    def _build_synthesis_prompt(
        *, topic: str, findings: Dict[str, str], jd_facets: List[str]
    ) -> str:
        joined = "\n\n".join(
            f"### {facet}\n{(blob or '(no research available)')[:2000]}"
            for facet, blob in findings.items()
        )
        jd_hint = ", ".join(jd_facets[:25]) if jd_facets else "(none provided)"
        return (
            f"Target company: {topic}\n"
            f"Job-description anchor terms (for relevance weighting): {jd_hint}\n\n"
            f"Research notes:\n{joined}\n\n"
            "Synthesize and return the structured JSON company brief matching the required system schema."
        )

    def _parse_synthesis(
        self, text: str, *, topic: str, jd_facets: List[str]
    ) -> Dict[str, Any]:
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        try:
            first = text.find("{")
            last = text.rfind("}")
            if first >= 0 and last > first:
                return json.loads(text[first : last + 1])
        except (json.JSONDecodeError, ValueError) as exc:
            self.logger.warning("[CompanyBriefEngine] could not parse LLM JSON: %s", exc)
        raise unavailable_err(f"{topic}: structured synthesis JSON parse failed")

    @staticmethod
    def _stub_synthesis(*, topic: str, jd_facets: List[str]) -> Dict[str, Any]:
        unavailable_err = _cbe("CompanyBriefUnavailableError", RuntimeError)
        raise unavailable_err(f"{topic}: stub synthesis disabled")

    @staticmethod
    def build_company_brief_system_instructions(
        identity: str = "Company Brief Research Synthesis Engine",
        guidelines: str = "Synthesize grounded company findings into schema-compliant JSON.",
        communication_style: str = "Concise, analytical, zero speculation.",
    ) -> Any:
        """Build Antigravity SDK TemplatedSystemInstructions for company brief synthesis."""
        from tools.unified_agent_architecture import TemplatedSystemInstructions

        return TemplatedSystemInstructions(
            identity=identity,
            guidelines=guidelines,
            communication_style=communication_style,
        )

    @staticmethod
    def build_structured_agent_config(response_schema: Any = None) -> dict[str, Any]:
        """Build LocalAgentConfig dictionary with response_schema for structured synthesis."""
        return {
            "system_instructions": _CompanyBriefSynthesisMixin.build_company_brief_system_instructions(),
            "response_schema": response_schema,
        }


__all__ = ["_CompanyBriefSynthesisMixin"]
