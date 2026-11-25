"""CompanyBriefEngine — apps_research --mode company.

Produces a CompanyBrief conforming to apps_rg/schemas/company_research.schema.json.
Driven by SearXNG research (when available) plus a synthesizing LLM call.
Fails closed when grounding or synthesis dependencies cannot produce a real brief.

Plan: docs/archive/windsurf/legacy-tree/plans/apps-rg-narrative-and-company-research-e3f8c1.md (P1.2).
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Final, List, Optional

from apps_model_telemetry.token_budget_governor import TokenBudgetPolicy, estimate_input_tokens
from apps_research.config.model_pins import (
    AppsResearchModelPinError,
    company_brief_generation_pin,
)
from apps_research.engines.base_research_engine import BaseResearchEngine
from apps_research.engines.company_brief import (
    _CompanyBriefC0BundleMixin,
    _CompanyBriefRetrievalLegacyMixin,
    _CompanyBriefRetrievalV2Mixin,
    _CompanyBriefSynthesisMixin,
    _CompanyBriefTargetingBriefMixin,
)
from apps_research.engines.query_decomposer import (  # noqa: F401
    _COVERAGE_FAMILY_CATALOG,
    _DEPTH_PARAM_MAP,
    _DEPTH_PROFILES,
    _PROFILE_REQUIRED_FAMILIES,
    QueryPlan,
    _resolve_depth_profile,
    decompose_coverage_families,
    describe_jd_retrieval_contract,
)
from apps_research.integrations.provider_gateway import (
    AppsResearchProviderGatewayError,
    invoke_openai_company_brief,
)
from apps_research.prompt_assembly.company_brief_prompts import COMPANY_BRIEF_STATIC_SYSTEM_PROMPT
from apps_research.reasoning.adaptive_research_loop import (  # noqa: F401
    build_adaptive_research_revision,
)
from apps_research.types.jd_intent_coverage import (  # noqa: F401
    infer_evidence_intents,
    required_families_for_intents,
)
from infrastructure.config.env_loader import get_env_bool, get_env_str
from infrastructure.types.metric_lexical_primitives import WORD_RE

# Plan §P1.4 — V2 retrieval pipeline behind feature flag.
_RETRIEVAL_V2_FLAG = "APPS_RESEARCH_RETRIEVAL_V2"
_SAME_RUN_RECOVERY_SIGNAL_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "competitive_landscape": re.compile(
        r"\b(?:competitors?|competitive|market\s+(?:positioning|share)|"
        r"peer\s+(?:companies|group|set))\b",
        re.IGNORECASE,
    ),
    "adoption_motion": re.compile(
        r"\b(?:adoption|deploy(?:ed|ment|ing)?|implementation|pilot(?:s)?|"
        r"production|rollout|enablement)\b",
        re.IGNORECASE,
    ),
}
CompanyBriefProviderProfileError = AppsResearchModelPinError


def _company_brief_primary_openai_model() -> str:
    """Resolve the runtime synthesis model from the provider-profile SSOT."""
    pin = company_brief_generation_pin()
    if pin.provider != "external_openai":
        raise CompanyBriefProviderProfileError(
            "CompanyBriefEngine currently supports only approved_model_lanes.primary.provider="
            f"external_openai; got {pin.provider!r}"
        )
    return pin.model


APPS_RESEARCH_BRIEF_MODEL: Final[str] = _company_brief_primary_openai_model()
APPS_RESEARCH_BRIEF_REASONING_EFFORT: Final[str] = company_brief_generation_pin().reasoning_effort


def _v2_enabled() -> bool:
    """True when the V2 retrieval pipeline is opted-in via env flag."""
    return get_env_bool(_RETRIEVAL_V2_FLAG, False)


def _source_repository_root(start: Path | None = None) -> Path:
    """Resolve the enclosing checkout in standalone and monorepo layouts."""
    current = Path(start) if start is not None else Path(__file__)
    current = current.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / "src" / "apps_research" / "__init__.py").is_file():
            return candidate
        if (candidate / "apps_research" / "__init__.py").is_file() and (
            candidate / ".git"
        ).exists():
            return candidate
    raise FileNotFoundError(f"could not locate repository root from {current}")


def _company_identity_matches(*, company_name: str, document: dict[str, Any]) -> bool:
    """Return whether a retrieved document unambiguously names the company."""
    identity = " ".join(str(company_name or "").casefold().split())
    tokens = WORD_RE.findall(identity)
    if not tokens:
        return False

    haystack = " ".join(
        str(document.get(field) or "") for field in ("title", "url", "snippet")
    ).casefold()
    if len(tokens) == 1:
        pattern = rf"(?<![a-z0-9]){re.escape(tokens[0])}(?![a-z0-9])"
    elif "&" in identity or re.search(r"\band\b", identity):
        pattern = (
            r"(?<![a-z0-9])"
            + r"\s*(?:&|and)\s*".join(re.escape(token) for token in tokens)
            + r"(?![a-z0-9])"
        )
    else:
        pattern = (
            r"(?<![a-z0-9])"
            + r"(?:[\s\-_/,.]+)".join(re.escape(token) for token in tokens)
            + r"(?![a-z0-9])"
        )
    return bool(re.search(pattern, haystack))


_log = logging.getLogger(__name__)


def _emit_company_brief_marker(
    *,
    accepted: bool,
    model_used: str,
    fallback_reason: str,
    latency_ms: float = 0.0,
    scorecard: Any = None,
) -> str:
    """Best-effort ``JUDGE_DECISION`` emission with real Judge v3 provenance (never fake composite=0.0)."""
    rubric_id = getattr(scorecard, "profile_id", None) or "company_research_brief:company_brief_synthesis"
    rubric_hash = (getattr(scorecard, "rubric_sha256", "") or "judge_v3")[:16]
    llm_exec = bool(getattr(scorecard, "llm_judge_executed", False))
    unit_sc = getattr(scorecard, "normalized_unit_score", None)
    failed_gates = list(getattr(scorecard, "preflight_failed_gates", ()) or getattr(scorecard, "failed_check_ids", ()) or ())
    first_gate = failed_gates[0] if failed_gates else "none"
    score_tok = f"{float(unit_sc):.4f}" if unit_sc is not None else "null"
    payload = (
        "JUDGE_DECISION: type=judge_decision, "
        "app_name=apps_research.company_brief, "
        f"rubric_id={rubric_id}, "
        f"rubric_hash={rubric_hash}, "
        f"accepted={accepted}, "
        f"llm_judge_executed={llm_exec}, "
        f"normalized_unit_score={score_tok}, "
        f"model_used={model_used}, "
        f"fallback_reason={fallback_reason}, "
        f"first_failed_gate={first_gate}, "
        f"latency_ms={latency_ms:.1f}"
    )
    try:
        from tools.capture.append_marker import append_marker  # noqa: PLC0415

        append_marker(payload, session_hint="apps_research.company_brief")
    except (ImportError, OSError, PermissionError):
        pass
    return payload


def _company_brief_prompt_token_cap() -> int:
    """Hard guard for a single research synthesis request, not a text rewrite."""
    raw = get_env_str("APPS_RESEARCH_MAX_INPUT_TOKENS", "").strip()
    if raw:
        try:
            return max(1_024, min(int(raw), 48_000))
        except ValueError:
            pass
    return 24_000


def _enforce_company_brief_prompt_budget(prompt: str) -> None:
    """Reject prompts whose preflight estimated token count exceeds the configured ceiling."""
    cap = _company_brief_prompt_token_cap()
    chars_est, safety_mult = 3, 1.12
    try:
        from apps_rg.runtime.section_model_limits import runtime_limit_float, runtime_limit_int

        chars_est = runtime_limit_int("model_token_governor.chars_per_token_estimate", 3)
        safety_mult = runtime_limit_float("model_token_governor.safety_multiplier", 1.12)
    except (ImportError, OSError, ValueError, TypeError):
        pass
    estimated = estimate_input_tokens(
        prompt,
        policy=TokenBudgetPolicy(
            chars_per_token_estimate=chars_est,
            safety_multiplier=safety_mult,
            max_input_tokens_per_attempt=cap,
            max_reserved_tokens_per_run=cap,
        ),
    )
    if estimated > cap:
        raise CompanyBriefUnavailableError(
            "apps_research company-brief input exceeds the preflight cap: "
            f"estimated_input_tokens={estimated}; max_input_tokens={cap}"
        )


class CompanyBriefUnavailableError(RuntimeError):
    """Raised when company brief synthesis cannot produce a real brief."""


def _resolved_gemini_max_output_tokens() -> int:
    """Canonical apps_research output-token budget for synthesis calls."""
    raw = get_env_str("APPS_RESEARCH_MAX_OUTPUT_TOKENS", "").strip()
    if raw:
        try:
            return max(512, int(raw))
        except ValueError:
            pass
    return 4096


class CompanyBriefEngine(
    _CompanyBriefRetrievalV2Mixin,
    _CompanyBriefRetrievalLegacyMixin,
    _CompanyBriefSynthesisMixin,
    _CompanyBriefTargetingBriefMixin,
    _CompanyBriefC0BundleMixin,
    BaseResearchEngine,
):
    """Generates a CompanyBrief for a target company.

    Inputs:
        topic: company name (e.g., "Blend360")
        jd_anchor: optional path to job_description.json for facet weighting
        depth: shallow | standard | deep

    Output: dict matching the CompanyBrief schema. The caller is responsible
    for persisting and validating against pydantic.
    """

    AGENT_ID = "apps_research.company_brief_engine"

    _FACET_QUERIES = [
        ("overview", '{company} company overview tagline founding "core offerings"'),
        ("strategic_priorities", '{company} strategic priorities 2025 2026 announcements roadmap'),
        ("customer_profile", '{company} customers verticals industries case studies'),
        ("tech_stack_signals", '{company} technology stack platforms partners "we use"'),
        ("commercial_motion", '{company} commercial motion revenue sales partner-led product-led services-led'),
        ("partner_ecosystem", '{company} partners alliances co-sell ecosystem channel ISV GSI'),
        ("adoption_motion", '{company} adoption deployment implementation pilot production enablement'),
        ("leadership", '{company} leadership team CEO CTO executives'),
        ("competitive_set", '{company} competitors alternatives "vs"'),
        ("recent_moves", '{company} news 2025 acquisition partnership launch'),
    ]

    def execute(self, input_data: Any) -> Dict[str, Any]:
        """Run end-to-end company brief retrieval, synthesis, C0 bundle, and assembly."""
        _t0 = time.perf_counter()
        _sub_stages: list[dict[str, Any]] = []
        topic: str = self._extract(input_data, "topic")
        if not topic or not isinstance(topic, str):
            raise ValueError("CompanyBriefEngine requires non-empty 'topic' (company name)")

        raw_depth = str(self._extract(input_data, "depth", default="standard"))
        depth_profile = _resolve_depth_profile(raw_depth)

        _t_intake = time.perf_counter()
        jd_context: Dict[str, Any] = self._resolve_jd_context(input_data)
        _sub_stages.append({
            "sub_stage_id": "research.intake",
            "sub_stage_name": "Intake + JD Resolution",
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - _t_intake) * 1000, 3),
            "meta": {"topic": topic, "depth": depth_profile},
        })

        _t_research = time.perf_counter()
        if _v2_enabled():
            research_findings = self._run_research_v2(
                topic=topic,
                depth_profile=depth_profile,
                jd_context=jd_context,
                retrieval_receipt_path=self._resolve_retrieval_receipt_path(jd_context),
            )
        else:
            research_findings = self._run_research_adaptive(
                topic=topic, depth_profile=depth_profile, jd_context=jd_context
            )
        retrieval_contract = describe_jd_retrieval_contract(jd_context or None)
        _sub_stages.append({
            "sub_stage_id": "research.fetch",
            "sub_stage_name": "Evidence Retrieval",
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - _t_research) * 1000, 3),
            "meta": {
                "v2": _v2_enabled(),
                "query_families": list(research_findings.keys()),
                "jd_intents": retrieval_contract.get("intent_ids", []),
            },
        })

        _t_jd = time.perf_counter()
        jd_anchor: Optional[Path] = None
        raw_anchor = self._extract(input_data, "jd_anchor", default=None)
        if raw_anchor:
            jd_anchor = Path(raw_anchor) if not isinstance(raw_anchor, Path) else raw_anchor
        jd_facets = self._load_jd_facets(jd_anchor)
        _sub_stages.append({
            "sub_stage_id": "research.jd_facets",
            "sub_stage_name": "JD Facet Extraction",
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - _t_jd) * 1000, 3),
            "meta": {"facets_count": len(jd_facets)},
        })

        _t_synth = time.perf_counter()
        profile_cfg = _DEPTH_PROFILES[depth_profile]
        synthesized = self._synthesize(
            topic=topic,
            findings=research_findings,
            jd_facets=jd_facets,
            depth=depth_profile,
            jd_context=jd_context,
            jd_anchor=jd_anchor,
        )
        _sub_stages.append({
            "sub_stage_id": "research.synthesize",
            "sub_stage_name": "LLM Synthesis",
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - _t_synth) * 1000, 3),
            "meta": {"facets": len(synthesized)},
        })

        _t_c0 = time.perf_counter()
        c0_bundle = self._build_c0_bundle(
            topic=topic,
            depth_profile=depth_profile,
            profile_cfg=profile_cfg,
            findings=research_findings,
            synthesis=synthesized,
            jd_context=jd_context,
            retrieval_contract=retrieval_contract,
        )
        gate_verdict, gate_caveat, degraded_reason = self._evaluate_c0_pa_gate(
            c0_bundle=c0_bundle, depth_profile=depth_profile
        )
        c0_bundle["synthesis_guidance"]["gate_verdict"] = gate_verdict
        c0_bundle["synthesis_guidance"]["gate_caveat"] = gate_caveat
        c0_bundle["synthesis_guidance"]["degraded_packet_reason"] = degraded_reason
        _sub_stages.append({
            "sub_stage_id": "research.c0_gate",
            "sub_stage_name": "C0 Bundle + Gate Evaluation",
            "status": "PASS" if gate_verdict == "PASS" else "FAIL",
            "duration_ms": round((time.perf_counter() - _t_c0) * 1000, 3),
            "meta": {"gate_verdict": gate_verdict},
        })

        _t_assemble = time.perf_counter()
        brief = self._assemble_brief(topic=topic, synthesis=synthesized)
        brief["_c0_bundle"] = c0_bundle
        brief["_depth_profile"] = depth_profile
        brief["_gate_verdict"] = gate_verdict
        brief["_sub_stages"] = _sub_stages
        if jd_context:
            brief["_jd_context"] = dict(jd_context)
        targeting_disposition = str(synthesized.get("targeting_brief_disposition") or "").strip()
        if targeting_disposition:
            targeting_md = str(synthesized.get("apps_rg_targeting_brief_markdown") or "").strip()
            targeting_sidecar = synthesized.get("apps_rg_targeting_brief_sidecar") or {}
            gate_blocks = not self._targeting_c0_gate_allows_handoff(
                c0_bundle=c0_bundle,
                gate_verdict=gate_verdict,
            )
            if targeting_md and not gate_blocks and targeting_disposition == "SEALED":
                brief["apps_rg_targeting_brief_text"] = targeting_md
                brief["company_brief_text"] = targeting_md
                brief["targeting_brief_disposition"] = "SEALED"
                if str(gate_verdict).upper() == "WEAK_WITH_CAVEATS":
                    brief["targeting_brief_c0_disposition"] = "CAVEATED_JD_COMPLETE"
                    brief["targeting_brief_c0_caveat"] = gate_caveat
            else:
                brief["targeting_brief_disposition"] = "BLOCKED" if gate_blocks else targeting_disposition
                brief["targeting_brief_block_reason"] = (
                    f"c0_support_gate={gate_verdict}"
                    if gate_blocks
                    else str(synthesized.get("targeting_brief_block_reason") or "")
                )
                if synthesized.get("targeting_brief_violations"):
                    brief["targeting_brief_violations"] = list(synthesized["targeting_brief_violations"])
            if targeting_sidecar:
                brief["apps_rg_targeting_brief_sidecar"] = dict(targeting_sidecar)
        _sub_stages.append({
            "sub_stage_id": "research.assemble",
            "sub_stage_name": "Brief Assembly",
            "status": "PASS",
            "duration_ms": round((time.perf_counter() - _t_assemble) * 1000, 3),
            "meta": {},
        })

        _t_judge = time.perf_counter()
        from apps_research.engines.judges.v3_brief_judge import (  # noqa: PLC0415
            RESEARCH_JUDGE_TRANSPORT_ENV,
            evaluate_research_brief_v3,
            run_research_brief_ide_cli_judge,
        )

        judge_transport = get_env_str(RESEARCH_JUDGE_TRANSPORT_ENV, "").strip().lower()
        public_brief_view = {k: v for k, v in brief.items() if not str(k).startswith("_")}
        if judge_transport == "ide_cli":
            _, brief_scorecard = run_research_brief_ide_cli_judge(
                artifact_id=f"company_brief:{topic}",
                brief_payload=public_brief_view,
                profile_token="company_research_brief:company_brief_synthesis",
                author_model_family="openai",
            )
        else:
            _, brief_scorecard = evaluate_research_brief_v3(
                artifact_id=f"company_brief:{topic}",
                brief_payload=public_brief_view,
                profile_token="company_research_brief:company_brief_synthesis",
                author_model_family="openai",
                llm_raw_response=None,
            )
        brief["_judge_v3_scorecard"] = brief_scorecard.to_dict()

        if brief.get("targeting_brief_disposition") == "SEALED" and brief.get("apps_rg_targeting_brief_text"):
            t_payload = {
                "company_name": topic,
                "targeting_brief_text": brief.get("apps_rg_targeting_brief_text"),
                "sidecar": brief.get("apps_rg_targeting_brief_sidecar") or {},
            }
            if judge_transport == "ide_cli":
                _, t_card = run_research_brief_ide_cli_judge(
                    artifact_id=f"targeting_brief:{topic}",
                    brief_payload=t_payload,
                    profile_token="company_research_brief:targeting_brief_handoff",
                    author_model_family="openai",
                )
            else:
                _, t_card = evaluate_research_brief_v3(
                    artifact_id=f"targeting_brief:{topic}",
                    brief_payload=t_payload,
                    profile_token="company_research_brief:targeting_brief_handoff",
                    author_model_family="openai",
                    llm_raw_response=None,
                )
            brief["_targeting_judge_v3_scorecard"] = t_card.to_dict()

        _emit_company_brief_marker(
            accepted=str(gate_verdict).upper() == "PASS",
            model_used=getattr(self, "_last_company_brief_generation_model_observed", APPS_RESEARCH_BRIEF_MODEL),
            fallback_reason="none",
            latency_ms=(time.perf_counter() - _t_judge) * 1000.0,
            scorecard=brief_scorecard,
        )
        _sub_stages.append({
            "sub_stage_id": "research.judge_v3",
            "sub_stage_name": "Clean-Slate Judge v3 Evaluation",
            "status": "PASS" if (not brief_scorecard.llm_judge_executed or brief_scorecard.passed) else "FAIL",
            "duration_ms": round((time.perf_counter() - _t_judge) * 1000, 3),
            "meta": {
                "profile_id": brief_scorecard.profile_id,
                "llm_judge_executed": brief_scorecard.llm_judge_executed,
                "normalized_unit_score": brief_scorecard.normalized_unit_score,
            },
        })

        self.record_pass(
            f"CompanyBrief assembled for {topic} [{depth_profile}] gate={gate_verdict}",
            data={
                "facets_synthesized": len(synthesized),
                "depth_profile": depth_profile,
                "gate_verdict": gate_verdict,
                "jd_present": bool(jd_context),
                "total_ms": round((time.perf_counter() - _t0) * 1000, 1),
            },
        )
        return brief

    @staticmethod
    def _extract(payload: Any, key: str, *, default: Any = None) -> Any:
        if hasattr(payload, key):
            return getattr(payload, key)
        if isinstance(payload, dict):
            return payload.get(key, default)
        return default

    def _load_jd_facets(self, jd_anchor: Optional[Path]) -> List[str]:
        if not jd_anchor or not jd_anchor.exists():
            return []
        try:
            data = json.loads(jd_anchor.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("[CompanyBriefEngine] JD anchor unreadable: %s", exc)
            return []
        facets: List[str] = []
        for key in ("must_have", "nice_to_have", "responsibilities", "keywords"):
            v = data.get(key)
            if isinstance(v, list):
                facets.extend(str(x) for x in v if x)
        return facets


__all__ = [
    "APPS_RESEARCH_BRIEF_MODEL",
    "APPS_RESEARCH_BRIEF_REASONING_EFFORT",
    "COMPANY_BRIEF_STATIC_SYSTEM_PROMPT",
    "CompanyBriefEngine",
]
