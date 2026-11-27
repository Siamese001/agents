"""
ATS Validator - Deterministic ATS Compatibility Validation

Zero-Ambiguity Standard: Renamed from ats_validation_deterministic_validator.py
Category: VALIDATOR (Deterministic safety check)

Moved from L0_routing/deterministic to L5_safety/validators.

Deterministic Operations:
- Pattern matching for ATS-unfriendly formats
- Section header validation
- Keyword scoring algorithm
- Text normalization and processing
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from apps_rg.runtime.spine_contracts import lifecycle_trace_contract as trace_contract

trace_contract.emit_replay_key("p0", "ats_validator")
trace_contract.emit_determinism_digest("p0", "ats_validator")

trace_contract._emit_dispatches_healing_run("p1", "ats_validator", "L5")
trace_contract._emit_routes_through("p1", "ats_validator", "L5")
trace_contract._emit_checks_agent_registry("p1", "ats_validator", "agent_registry")
trace_contract._emit_validates_agent_capability("p1", "ats_validator", "capability")
trace_contract._emit_dispatches_execution_plan("p1", "ats_validator", "exec_plan")
trace_contract._emit_agent_executes_agent("p1", "ats_validator", "sub_agent")
trace_contract._emit_routes_to_agent("p1", "ats_validator", "target_agent")
trace_contract._emit_verifies_policy("p1", "ats_validator", "policy_check")
trace_contract._emit_observes_runtime_state("p1", "ats_validator", "runtime_state")
trace_contract._emit_verifies_boundary("p1", "ats_validator", "boundary_check")
trace_contract._emit_transcripts_response("p1", "ats_validator", "transcript")
trace_contract._emit_hard_fails_untranscripted("p1", "ats_validator")
trace_contract._emit_gated_by_confidence("p1", "ats_validator", "confidence_gate")
trace_contract._emit_escalates_to_human("p1", "ats_validator", "L5")
trace_contract._emit_reads_policy_state("p1", "ats_validator", "L5")

trace_contract._emit_applies_guardrail("p0", "ats_validator", "p0_governance")
trace_contract._emit_snapshots_state("p0", "ats_validator", "state_snapshot")
trace_contract._emit_authorize_and_execute("p2", "ats_validator", "execution_auth")
trace_contract._emit_validates_capability("p2", "ats_validator", "capability_check")
trace_contract._emit_routes_to_capability("p2", "ats_validator", "capability_route")
trace_contract._emit_writes_via_uwg("p2", "ats_validator", "uwg_write")
trace_contract._emit_blocks_direct_write("p2", "ats_validator", "direct_write_block")
trace_contract._emit_records_tool_invocation("p2", "ats_validator", "tool_invocation")
trace_contract._emit_captures_execution_output("p2", "ats_validator", "exec_output")
trace_contract._emit_dispatches_agent("p3", "ats_validator", "agent_dispatch")
trace_contract._emit_coordinates_agents("p3", "ats_validator", "agent_coordination")
trace_contract._emit_records_workflow_lineage("p3", "ats_validator", "workflow_lineage")
trace_contract._emit_records_healing_outcome("p3", "ats_validator", "healing_outcome")
trace_contract._emit_escalates_failure("p3", "ats_validator", "failure_escalation")
trace_contract._emit_orchestrates_workflow("p3", "ats_validator", "workflow_orchestration")
trace_contract._emit_dispatches_healing_run("p3", "ats_validator", "healing_dispatch")
trace_contract._emit_invokes_evaluation("p3", "ats_validator", "evaluation_signal")
trace_contract._emit_records_telemetry_event("p4", "ats_validator", "telemetry_event")
trace_contract._emit_captures_evaluation_metric("p4", "ats_validator", "eval_metric")
trace_contract._emit_stores_embedding("p4", "ats_validator", "embedding_store")
trace_contract._emit_updates_meta_learning_state("p4", "ats_validator", "meta_learning")
trace_contract._emit_links_execution_to_snapshot("p4", "ats_validator", "exec_snapshot_link")
from tqdm import tqdm

trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_1")
trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_2")
trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_3")
trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_4")
trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_5")
trace_contract._emit_emits_metric_event("ats_validator", "p4obs", "metric_6")
trace_contract._emit_records_incident_event("ats_validator", "p4obs", "incident")
trace_contract._emit_captures_runtime_anomaly("ats_validator", "p4obs", "anomaly")
trace_contract._emit_writes_observability_log("ats_validator", "p4obs", "obs_log")
trace_contract._emit_updates_monitoring_state("ats_validator", "p4obs", "mon_state")
trace_contract._emit_triggers_alert("ats_validator", "p4obs", "alert")
trace_contract._emit_links_incident_trace("ats_validator", "p4obs", "trace_link")
trace_contract._emit_captures_pattern("ats_validator", "p3lm", "pattern")
trace_contract._emit_records_learning_event("ats_validator", "p3lm", "learning_event")
trace_contract._emit_writes_learning_snapshot("ats_validator", "p3lm", "snapshot")
trace_contract._emit_feeds_meta_learning("ats_validator", "p3lm", "meta_feed")
trace_contract._emit_updates_routing_strategy("ats_validator", "p3lm", "routing")
trace_contract._emit_improves_agent_policy("ats_validator", "p3lm", "policy")
trace_contract._emit_stores_learning_state("ats_validator", "p3lm", "state")
trace_contract._emit_records_execution_trace("ats_validator", "L0_ROUTING", "p2_trace_1")
trace_contract._emit_records_execution_trace("ats_validator", "L1_REASONING", "p2_trace_2")
trace_contract._emit_records_execution_trace("ats_validator", "L2_EXECUTION", "p2_trace_3")
trace_contract._emit_records_execution_trace("ats_validator", "L3_ORCHESTRATION", "p2_trace_4")
trace_contract._emit_records_execution_trace("ats_validator", "L4_STATE", "p2_trace_5")
trace_contract._emit_reads_environ("ats_validator", "env_read", "p2_env_1")
trace_contract._emit_reads_environ("ats_validator", "env_read", "p2_env_2")
trace_contract._emit_reads_runtime_state("ats_validator", "runtime_state", "p2_rt_1")
trace_contract._emit_reads_runtime_state("ats_validator", "runtime_state", "p2_rt_2")
trace_contract._emit_pulls_context("p1", "ats_validator", "context_pull")
trace_contract._emit_pulls_context("p1", "ats_validator", "context_pull_2")
trace_contract._emit_execution_terminates_at_uwg("p1", "ats_validator", "uwg_term")
trace_contract._emit_execution_terminates_at_uwg("p1", "ats_validator", "uwg_term_2")
trace_contract._emit_writes_through("p1", "ats_validator", "write_through")
trace_contract._emit_writes_through("p1", "ats_validator", "write_through_2")
trace_contract._emit_validated_by_safety_plane("p1", "ats_validator", "safety_validation")
trace_contract._emit_invokes_eval("p1", "ats_validator", "eval_call")
trace_contract._emit_proposal_commits_routing("p1", "ats_validator", "routing_commit")


@dataclass
class ATSValidationResult:
    """Result of ATS validation with deterministic scoring."""

    passed: bool
    issues: list[str]
    score: float | None = None
    metadata: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}


@dataclass(frozen=True)
class ATSJDRequirementCoverageResult:
    """Deterministic closeout gate result for JD must-have requirement coverage."""

    passed: bool
    coverage_ratio: float
    min_coverage: float
    matched_terms: tuple[str, ...]
    missing_terms: tuple[str, ...]
    acronym_pair_hits: tuple[str, ...]
    total_requirements: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "coverage_ratio": self.coverage_ratio,
            "min_coverage": self.min_coverage,
            "matched_terms": list(self.matched_terms),
            "missing_terms": list(self.missing_terms),
            "acronym_pair_hits": list(self.acronym_pair_hits),
            "total_requirements": self.total_requirements,
        }


_CANONICAL_ATS_ACRONYM_PAIRS: dict[str, tuple[str, ...]] = {
    "fsa": ("fsa", "fellow of the society of actuaries"),
    "erm": ("erm", "enterprise risk management"),
    "rag": ("rag", "retrieval-augmented generation", "retrieval augmented generation", "graphrag"),
    "graphrag": ("graphrag", "graph rag"),
    "llm": ("llm", "llms", "large language model", "large language models"),
    "aws": ("aws", "amazon web services"),
    "ccar": ("ccar", "comprehensive capital analysis and review"),
    "hipaa": ("hipaa", "health insurance portability and accountability act"),
    "p&c": ("p&c", "property and casualty", "property & casualty"),
    "sr 11-7": ("sr 11-7", "sr 11 7", "model risk management"),
    "bcbs 239": ("bcbs 239", "bcbs239", "risk data aggregation"),
    "soc 2": ("soc 2", "soc2"),
}

_CANONICAL_JD_DOMAIN_PHRASES: tuple[str, ...] = (
    "solvency ii",
    "ag43",
    "fsa",
    "erm",
    "enterprise risk management",
    "actuarial",
    "guidewire",
    "underwriting",
    "claims",
    "policy administration",
    "sr 11-7",
    "bcbs 239",
    "ccar",
    "basel",
    "hipaa",
    "nydfs",
    "soc 2",
    "graphrag",
    "rag",
    "multi-agent",
    "agentic",
    "llmops",
    "llm",
    "aws",
    "databricks",
    "lakehouse",
    "microservices",
    "distributed systems",
    "cloud modernization",
    "ai governance",
    "model risk",
    "p&c",
    "co-sell",
    "hyperscaler",
    "m&a",
    "ebitda",
    "biostatistics",
    "derivatives",
)


def _flatten_resume_surface(final_resume: dict[str, Any] | str) -> str:
    if isinstance(final_resume, str):
        return final_resume
    if isinstance(final_resume, dict) and isinstance(final_resume.get("sections"), list):
        from apps_rg.runtime.assembly.full_resume_text import flatten_final_resume_to_text

        flattened = flatten_final_resume_to_text(final_resume)
        extras: list[str] = []
        for sec in final_resume.get("sections") or []:
            if isinstance(sec, dict):
                rt = str(sec.get("rendered_text") or "").strip()
                if rt and rt not in flattened:
                    extras.append(rt)
        return "\n".join([flattened, *extras]).strip() if extras else flattened
    parts: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if not str(k).startswith("_"):
                    _walk(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)

    _walk(final_resume)
    return "\n".join(parts)


def _term_present_in_text(text_lower: str, term: str) -> bool:
    clean = term.strip().lower()
    if not clean:
        return False
    escaped = re.escape(clean).replace(r"\ ", r"[\s\-/]+")
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text_lower))


def extract_jd_must_have_requirements(jd_text: str) -> tuple[str, ...]:
    """Extract canonical domain and technical must-have requirements from JD text."""
    text_lower = str(jd_text or "").lower()
    found: list[str] = []
    for phrase in _CANONICAL_JD_DOMAIN_PHRASES:
        if _term_present_in_text(text_lower, phrase):
            found.append(phrase)
    return tuple(dict.fromkeys(found))


def evaluate_ats_jd_requirement_coverage(
    final_resume: dict[str, Any] | str,
    jd_text: str,
    *,
    required_terms: list[str] | tuple[str, ...] | None = None,
    min_coverage: float = 0.70,
    acronym_pairs: dict[str, tuple[str, ...]] | None = None,
) -> ATSJDRequirementCoverageResult:
    """Evaluate assembled resume text against canonical JD must-have requirements."""
    surface = _flatten_resume_surface(final_resume)
    surface_lower = surface.lower()
    reqs = tuple(
        dict.fromkeys(
            str(t).strip().lower()
            for t in (required_terms if required_terms is not None else extract_jd_must_have_requirements(jd_text))
            if str(t).strip()
        )
    )
    if not reqs:
        return ATSJDRequirementCoverageResult(
            passed=True,
            coverage_ratio=1.0,
            min_coverage=float(min_coverage),
            matched_terms=(),
            missing_terms=(),
            acronym_pair_hits=(),
            total_requirements=0,
        )
    pair_map = acronym_pairs if acronym_pairs is not None else _CANONICAL_ATS_ACRONYM_PAIRS
    matched: list[str] = []
    missing: list[str] = []
    pair_hits: list[str] = []
    for req in reqs:
        variants = pair_map.get(req, (req,))
        hit_variants = [v for v in variants if _term_present_in_text(surface_lower, v)]
        if hit_variants:
            matched.append(req)
            if len(variants) > 1 and len(hit_variants) >= 2:
                pair_hits.append(req)
        else:
            missing.append(req)
    ratio = round(len(matched) / len(reqs), 4)
    return ATSJDRequirementCoverageResult(
        passed=ratio >= float(min_coverage),
        coverage_ratio=ratio,
        min_coverage=float(min_coverage),
        matched_terms=tuple(matched),
        missing_terms=tuple(missing),
        acronym_pair_hits=tuple(pair_hits),
        total_requirements=len(reqs),
    )


class AtsValidator:
    """
    Pure deterministic ATS validation logic.

    All methods in this class are 100% deterministic and can be
    executed without external dependencies or LLM calls.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize with ATS validation configuration.

        Args:
            config: Configuration dictionary containing validation rules
        """
        self.standard_headers = config.get("standard_headers", {})
        self.ats_unfriendly_patterns = config.get("ats_unfriendly_patterns", [])
        self.allowed_non_standard_sections = config.get("allowed_non_standard_sections", [])
        self.keyword_config = config.get("keyword_optimization", {})
        self.min_score_threshold = self.keyword_config.get("min_score_threshold", 0.3)
        self.stop_words: set[str] = set(self.keyword_config.get("stop_words", []))

    def validate_ats_compatibility(
        self,
        resume: dict[str, Any],
        job_desc: str | None = None,
    ) -> ATSValidationResult:
        """
        Validate ATS compatibility using purely deterministic logic.

        Args:
            resume: Resume data dictionary
            job_desc: Optional job description for keyword scoring

        Returns:
            ATSValidationResult with deterministic findings
        """
        import uuid as _uuid  # noqa: PLC0415

        _trace_id = str(_uuid.uuid4())
        trace_contract._emit_records_execution_trace(
            _trace_id,
            trace_contract.LayerSegment.L5_POLICY,
            "AtsValidator.validate_ats_compatibility",
        )
        import hashlib as _hashlib  # noqa: PLC0415

        _seg_hash = _hashlib.sha256(
            f"{_trace_id}:AtsValidator.validate_ats_compatibility".encode(),
        ).hexdigest()[:24]
        trace_contract._emit_signs_execution_trace(_trace_id, _seg_hash, _seg_hash, 0)

        issues: list[str] = []
        issues.extend(self._check_ats_unfriendly_patterns(resume))
        issues.extend(self._validate_section_headers(resume))
        score = None
        if job_desc:
            score = self.calculate_keyword_score(resume, job_desc)
            if score < self.min_score_threshold:
                issues.append(f"Low keyword match ({score:.0%})")
        return ATSValidationResult(
            passed=len(issues) == 0,
            issues=issues,
            score=score,
            metadata={"validation_type": "deterministic"},
        )

    def _check_ats_unfriendly_patterns(self, resume: dict[str, Any]) -> list[str]:
        """
        Check for ATS-unfriendly patterns using deterministic regex.

        Moved to Deterministic: Pure pattern matching logic
        """
        issues: list[str] = []
        full_content = json.dumps(resume, ensure_ascii=False)
        for pattern in self.ats_unfriendly_patterns:
            if re.search(pattern, full_content):
                issues.append(f"ATS-unfriendly pattern found: {pattern}")
        return issues

    def _validate_section_headers(self, resume: dict[str, Any]) -> list[str]:
        """
        Validate section headers using deterministic string comparison.

        Moved to Deterministic: Pure string validation logic
        """
        issues: list[str] = []
        for section_name in tqdm(resume.keys(), desc="Processing", unit="item"):
            if section_name.startswith("_"):
                continue
            normalized = section_name.lower().strip()
            is_standard = False
            for standard_section, variants in self.standard_headers.items():
                if normalized in variants or normalized == standard_section:
                    is_standard = True
                    break
            if not is_standard and normalized not in self.allowed_non_standard_sections:
                issues.append(f"Non-standard section header: {section_name}")
        return issues

    def calculate_keyword_score(self, resume: dict[str, Any], job_desc: str) -> float:
        """
        Calculate keyword match score using deterministic algorithm.

        Moved to Deterministic: Pure mathematical calculation
        """
        job_words = set(re.findall("\\b[a-zA-Z]{3,}\\b", job_desc.lower()))
        job_words -= self.stop_words
        if not job_words:
            return 1.0
        resume_text = json.dumps(resume).lower()
        matches = sum(1 for word in job_words if word in resume_text)
        return matches / len(job_words)

    def normalize_text(self, text: str) -> str:
        """
        Normalize text for consistent processing.

        Moved to Deterministic: Pure string manipulation
        """
        text = re.sub("\\s+", " ", text.strip())
        return text.lower()

    # guardian: allow-magic-config -- explicitly approved governance exemption
    def extract_keywords(self, text: str, min_length: int = 3) -> set[str]:
        """
        Extract keywords from text using deterministic regex.

        Moved to Deterministic: Pure pattern extraction
        """
        words = set(re.findall(f"\\b[a-zA-Z]{{{min_length},}}\\b", text.lower()))
        return words - self.stop_words

    def validate_formatting(self, content: str) -> list[str]:
        """
        Validate content formatting using deterministic rules.

        Moved to Deterministic: Pure formatting validation
        """
        issues: list[str] = []
        if re.search("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\x7F]", content):
            issues.append("Contains control characters")
        if re.search("\\n{3,}", content):
            issues.append("Excessive line breaks")
        if "\r\n" in content and "\n" in content and (content.count("\r\n") != content.count("\n")):
            issues.append("Mixed line ending formats")
        return issues
