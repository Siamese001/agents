"""Domain-general Clean-Slate Judge v3 Runner & Output Model for `apps_rg` (`<= 240L`)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Mapping

from apps_eval.graders.judge.v3_evaluator import JudgeV3SchemaError, build_v3_response_schema
from apps_eval.graders.judge.v3_registry import (
    JudgeProfileV3,
    JudgeRubricRegistryV3,
    UnknownJudgeProfileError,
    render_v3_rubric_prompt,
)

JUDGE_RUBRIC_VERSION = "judge_v3_atomic_binary"
DEFAULT_THRESHOLD = 0.80
V3_JUDGE_SYSTEM_PROMPT = (
    "You are an independent blind hiring-committee judge. Answer cold_read_takeaway first, "
    "then answer YES or NO for each atomic check, quoting a verbatim evidence_span whenever a check is NO."
)


@dataclass
class JudgeOutput:
    judge_id: str
    provider_name: str
    provider_key: str
    evaluator_mode: str
    provider_status: str
    model_name: str
    provider_available: bool
    provider_blocked: bool
    exact_provider_error: str | None
    raw_response_ref: str | None = None
    original_model: str | None = None
    fallback_model: str | None = None
    rubric_version: str = JUDGE_RUBRIC_VERSION
    input_hash: str = ""
    output_hash: str = ""
    score: float | None = None
    score_scale: str | None = None
    normalized_score: float | None = None
    threshold: float = DEFAULT_THRESHOLD
    normalized_threshold: float | None = None
    pass_: bool = False
    decisive_failure: bool = False
    findings: list[str] = field(default_factory=list)
    cited_sentence_indexes: list[int] = field(default_factory=list)
    remediation_suggestions: list[str] = field(default_factory=list)
    model_requested: str | None = None
    model_actual: str | None = None
    reasoning_effort: str | None = None
    judge_packet_hash: str | None = None
    judge_packet_ref: str | None = None
    candidate_output_ref: str | None = None
    allowed_fact_packet_ref: str | None = None
    rubric_ref: str | None = None
    rationale: str | None = None
    fail_reasons: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    dimension_verdicts: dict[str, Any] | None = None
    dimension_verdicts_inferred: bool = False
    mocked: bool = False
    advisory_only: bool = False
    model_tier: str | None = None
    proof_eligible_judge: bool = False
    fallback_used: bool = False
    section_id: str | None = None
    transport: str = "ide_cli"
    usage: dict[str, Any] | None = None
    conversation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["pass"] = data.pop("pass_")
        data["model_actual"] = data.get("model_actual") or data.get("model_name")
        data["model_requested"] = data.get("model_requested") or data.get("model_name")
        data["mocked"] = data.get("evaluator_mode") == "MOCKED"
        if data.get("fallback_model"):
            data["fallback_used"] = True
        if self.provider_key == "gemini_pro" and self.reasoning_effort:
            data["thinking_level"] = self.reasoning_effort
        return data


def resolve_apps_rg_v3_profile_id(section_id: str | None) -> str:
    clean = str(section_id or "").strip().lower()
    if not clean:
        raise UnknownJudgeProfileError("apps_rg section_id cannot be empty.")
    if clean in {"headline", "resume_headline"}:
        return "resume_sections:headline"
    if clean in {"executive_summary", "resume_executive_summary"}:
        return "resume_sections:executive_summary"
    if clean in {"competencies", "resume_competencies"}:
        return "resume_sections:competencies"
    if clean in {"employment_bullets", "resume_employment_bullets"} or clean.endswith("_bullets"):
        return "resume_sections:employment_bullets"
    if clean in {"role_narrative", "role_episode", "resume_role_narrative"} or clean.endswith("_narrative"):
        return "resume_sections:role_narrative"
    if clean in {"full_resume_coherence", "whole_resume_coherence", "full_resume", "resume_whole_coherence"}:
        return "resume_whole_coherence:full_resume"
    raise UnknownJudgeProfileError(f"Unknown apps_rg section_id {section_id!r}; fail-closed.")


def get_apps_rg_v3_profile(section_id: str | None) -> JudgeProfileV3:
    return JudgeRubricRegistryV3.load().get_profile(resolve_apps_rg_v3_profile_id(section_id))


def render_section_v3_rubric(section_id: str | None) -> str:
    return render_v3_rubric_prompt(get_apps_rg_v3_profile(section_id))


def build_section_v3_response_schema(section_id: str | None) -> dict[str, Any]:
    return build_v3_response_schema(get_apps_rg_v3_profile(section_id))


def evaluate_v3_judge_response_to_dict(raw_parsed: Mapping[str, Any], *, section_id: str | None) -> dict[str, Any]:
    profile = get_apps_rg_v3_profile(section_id)
    if "checks" not in raw_parsed and "score_scale" in raw_parsed:
        return dict(raw_parsed)
    takeaway = str(raw_parsed.get("cold_read_takeaway") or "").strip()
    if len(takeaway) < 5:
        raise JudgeV3SchemaError("Judge v3 response requires non-empty 'cold_read_takeaway' first.")
    raw_checks = raw_parsed.get("checks")
    if not isinstance(raw_checks, Mapping):
        raise JudgeV3SchemaError("Judge v3 response missing 'checks' mapping.")

    dim_verdicts: dict[str, dict[str, Any]] = {}
    findings: list[str] = []
    passed_weight = 0.0
    critical_veto = False
    for spec in profile.checks:
        entry = raw_checks.get(spec.id)
        if not isinstance(entry, Mapping):
            raise JudgeV3SchemaError(f"Missing atomic check '{spec.id}' in Judge v3 response.")
        verdict = str(entry.get("verdict") or "").strip().upper()
        if verdict not in {"YES", "NO"}:
            raise JudgeV3SchemaError(f"Check '{spec.id}' verdict must be 'YES' or 'NO', got {verdict!r}.")
        span = str(entry.get("evidence_span") or "").strip()
        if verdict == "NO":
            if len(span) < 3:
                raise JudgeV3SchemaError(f"Check '{spec.id}' answered NO without a verbatim evidence_span.")
            dim_verdicts[spec.id] = {"pass": False, "severity": "major" if spec.critical else "minor", "codes": [spec.failure_tag]}
            findings.append(f"{spec.id} [{spec.failure_tag}]: {span}")
            if spec.critical:
                critical_veto = True
        else:
            passed_weight += spec.weight
            dim_verdicts[spec.id] = {"pass": True, "severity": "none", "codes": []}

    unit_score = round(min(1.0, max(0.0, passed_weight)), 4)
    passed = (not critical_veto) and (unit_score >= profile.pass_threshold)
    unsupported = [
        str(raw_checks[c.id].get("evidence_span") or "")
        for c in profile.checks
        if c.failure_tag == "HALLUCINATED_FACT" and str(raw_checks[c.id].get("verdict") or "").upper() == "NO"
    ]
    return {
        "rationale": takeaway,
        "cold_read_takeaway": takeaway,
        "score_scale": "0_to_1",
        "score": unit_score,
        "normalized_unit_score": unit_score,
        "threshold": profile.pass_threshold,
        "pass": passed,
        "decisive_failure": critical_veto or (not passed),
        "findings": findings,
        "cited_sentence_indexes": [1] if findings else [],
        "remediation_suggestions": [],
        "fail_reasons": list(findings),
        "unsupported_claims": unsupported,
        "quality_flags": list(raw_parsed.get("failure_tags") or []),
        "dimension_verdicts": dim_verdicts,
        "dimension_verdicts_inferred": False,
        "checks": json.loads(json.dumps(dict(raw_checks))),
    }
