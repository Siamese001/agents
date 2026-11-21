"""Strict length and execution-evidence checks for newly authored wave plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


def _resolve_max_plan_words() -> int:
    """Resolve INV-WAVE-PLAN-MAX-WORDS dynamically from config/governance/policy_registry.yaml."""
    reg_path = Path(__file__).resolve().parents[2] / "config" / "governance" / "policy_registry.yaml"
    if reg_path.is_file():
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            for entry in raw.get("policies", []):
                if isinstance(entry, dict) and entry.get("id") == "INV-WAVE-PLAN-MAX-WORDS":
                    val = entry.get("threshold")
                    if isinstance(val, int) and val >= 0:
                        return val
        except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):  # guardian: allow-silent-swallow -- safe fallback when yaml parser unavailable
            pass
    return 0


MAX_PLAN_WORDS: int = _resolve_max_plan_words()
_GATE_HEADING = re.compile(
    r"^#{3,4}\s+.*(?:receipt|completion\s+gate|exit\s+gate|verification).*",
    re.IGNORECASE,
)
_FIELD_PATTERNS = {
    "Run": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Run(?:\*\*)?\s*:", re.IGNORECASE),
    "Input": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Input(?:\*\*)?\s*:", re.IGNORECASE),
    "Expected": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Expected(?:\*\*)?\s*:", re.IGNORECASE),
    "Verify independently": re.compile(
        r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?(?:Verify independently|Independent check)(?:\*\*)?\s*:",
        re.IGNORECASE,
    ),
    "Fail if": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Fail if(?:\*\*)?\s*:", re.IGNORECASE),
    "Record": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Record(?:\*\*)?\s*:", re.IGNORECASE),
}

# INV-HOLISTIC-PIPELINE-PLANNING patterns
_APPS_RG_LANE_BASENAMES = (
    r"role_episode_lane|ibm_bullets_lane|unify_bullets_lane|"
    r"headline_lane|headline_pa|headline_repair_policy|"
    r"executive_summary_lane|executive_summary_repair_policy|executive_summary_synthesis_contract|"
    r"executive_summary_voice_repair|executive_summary_pa|exec_summary_perf_sync_helpers|"
    r"section_authority_repairs|ibm_bullets_pa|unify_bullets_pa|"
    r"ibm_narrative_lane(?:_[a-z0-9_]+)?|ibm_narrative_pa|ibm_narrative_repair_policy|"
    r"unify_narrative_lane|unify_narrative_pa|"
    r"competencies_lane(?:_[a-z0-9_]+)?|competencies_pa|"
    r"employment_bullet_pool|bullet_pool_claude_selector|employment_bullet_judge_rubric"
)
_SECTION_BULLET_DELIVERABLE_RE = re.compile(
    rf"(?:runtime/sections/(?:{_APPS_RG_LANE_BASENAMES})|"
    rf"\b(?:{_APPS_RG_LANE_BASENAMES})\.py\b)",
    re.IGNORECASE,
)
_UPSTREAM_PRODUCER_RE = re.compile(
    r"(?:runtime/c0/|resume_graph_allocation|c0_fact_anchor|c0_perf_sync_helpers|"
    r"c0_binding|competencies_graph_authority|headline_fact_id_resolution|"
    r"quad_graph_retriever|graph_role_episode_selector|selected_role_fact_set|"
    r"upstream_evidence_block|lane_base_resume|fact_anchor|FactAnchor|"
    r"what\s+stays\s+unchanged|upstream\s+(?:c0|allocation|retrieval|producer))",
    re.IGNORECASE,
)
_DOWNSTREAM_VALIDATOR_RE = re.compile(
    r"(?:cross_section_x2|bullet_quality_floor_x2|bullet_line_discipline_x2|"
    r"narrative_quality_x2|narrative_mechanical_x2|narrative_identity_x2|"
    r"executive_summary_x2|bullet_fact_entailment|"
    r"headline_x2|headline_quality_x2|headline_positioning_x2|headline_x3|"
    r"ibm_bullets_x2|unify_bullets_x2|ibm_narrative_x2|unify_narrative_x2|"
    r"unify_role_episode_x2|competencies_x2|competencies_quality_x2|"
    r"runtime/(?:validators|aggregation|exit)/|\bx2\s+(?:gate|validator|deduplication|floor))",
    re.IGNORECASE,
)

_OUTREACH_INTERMEDIATE_DELIVERABLE_RE = re.compile(
    r"(?:(?:outreach_engine/(?:src/)?)?apps_lic/(?:pipeline/(?:compiler|touch_sequence|orchestrator|coordinator)|"
    r"runtime/(?:outreach_swarm_challenger|dispatch/canonical_dispatch))(?:\.py)?\b|"
    r"\b(?:touch_sequence|outreach_swarm_challenger)\.py\b)",
    re.IGNORECASE,
)
_OUTREACH_UPSTREAM_RE = re.compile(
    r"(?:briefing_resolver|apps_research_bridge|managed_research_delegation|"
    r"research_boundary_policy|research_bridge_support|mission_loader|"
    r"SealedBriefingResolution|GovernedBriefingResolver|"
    r"upstream\s+(?:briefing|research(?:\s+ingestion|\s+bridge)?|apps_lic\s+producer))",
    re.IGNORECASE,
)
_OUTREACH_DOWNSTREAM_RE = re.compile(
    r"(?:(?:outreach_engine/(?:src/)?apps_lic/)?domain/(?:validators|repair)(?:\.py)?\b|"
    r"(?:apps_lic/)?judges/evaluator(?:\.py)?\b|"
    r"DeterministicDraftRepairer|RubricJudgeEvaluator|ExecutiveOutreachJudgePanel|"
    r"(?:ChannelLength|Grounding|SpamTrigger|ForbiddenClaims|SubordinateTone|"
    r"UnsupportedPersonalization|OutboundPrivacy)Validator|"
    r"downstream\s+(?:outreach|apps_lic)\s+(?:validator|validators|repair|judge))",
    re.IGNORECASE,
)

_RESEARCH_INTERMEDIATE_DELIVERABLE_RE = re.compile(
    r"(?:apps_research/(?:engines/(?:company_brief_engine|research_assembly_engine|"
    r"hop_company_brief_engine|hop_research_assembly_engine|role_profile_engine)|"
    r"prompt_assembly/(?:company_brief_prompts|consumer_briefs|research_pa_compiler)|"
    r"reasoning/(?:adaptive_research_loop|enterprise_research_orchestrator|"
    r"ResearchOrchestrator|ResearchHopOrchestrator)|"
    r"orchestration/hop_pipeline)(?:\.py)?\b|"
    r"\b(?:company_brief_engine|research_assembly_engine|hop_company_brief_engine|"
    r"hop_research_assembly_engine|company_brief_prompts|research_pa_compiler)\.py\b)",
    re.IGNORECASE,
)
_RESEARCH_UPSTREAM_RE = re.compile(
    r"(?:search_retrieval|tavily_retrieval|research_retrieval_engine|"
    r"hop_research_retrieval_engine|query_decomposer|query_decomposition_agent|"
    r"jd_intent_coverage|research_query|briefing_evidence_contracts|"
    r"c0_graph_adapter|research_c0_adapter|infer_evidence_intents|"
    r"upstream\s+(?:search|retrieval|jd[\s_\-]*intent|query\s+decomp))",
    re.IGNORECASE,
)
_RESEARCH_DOWNSTREAM_RE = re.compile(
    r"(?:apps_rg_handoff|spine_handoff|apps_rg_targeting_brief_contract|"
    r"apps_rg_targeting_brief|research_brief_uwg_writer|research_exit_fec_producer|"
    r"research_gate_validator|research_source_validator|apps_research_bridge|"
    r"apps_research/engines/judges/|apps_research/outputs/|"
    r"downstream\s+(?:handoff|targeting|brief|apps_rg|apps_lic|consumer\s+brief))",
    re.IGNORECASE,
)

_MONOLITH_SPLIT_TRIGGER_RE = re.compile(
    r"(?:monolith(?:ic)?\s+(?:split|decomposition)|package\s+(?:split|decomposition)|"
    r"re-?export\s+facade|ImportFrom\s+facade|"
    r"into\s+(?:<[a-z0-9_]+>/|[a-z0-9_]+/\s*)?submodules?|"
    r"(?:split(?:ting)?|decompos(?:e|ing|ition)|modulariz(?:e|ing|ation)|factor(?:ing)?)"
    r"\s+[^\n]{0,100}?(?:\.py\b|monoliths?|submodules?|packages?|lanes?|engines?|validators?|helpers?|modules?|"
    r"[a-z0-9_]+(?:_lane|_x2|_engine|_service|_orchestrator|_selector|_repairs?)\b))",
    re.IGNORECASE,
)
_PURE_STRUCTURAL_DECOMP_LINE_RE = re.compile(
    r"(?:clamp\s+[^\n]*file_budgets_ratchet|file_budgets_ratchet\.json|"
    r"into\s+(?:<[a-z0-9_]+>/|[a-z0-9_]+/\s*)?submodules?|"
    r"(?:split(?:ting)?|decompos(?:e|ing|ition)|modulariz(?:e|ing|ation)|factor(?:ing)?)"
    r"\s+[^\n]{0,100}?(?:submodules?|facade|under\s+600\s+lines|<=?\s*600|package)|"
    r"(?:re-?export|ImportFrom)\s+facade)",
    re.IGNORECASE,
)
_MONOLITH_FACADE_RE = re.compile(
    r"(?:re-?export\s+facade|ImportFrom\s+facade|facade\s+shim|public\s+facade|"
    r"stable\s+facade|intact\s+facade|__init__\.py\s+re-?export|backward[- ]compat\s+shim|"
    r"compatibility\s+facade|\bfacade\b)",
    re.IGNORECASE,
)
_MONOLITH_SUBMODULE_RE = re.compile(
    r"(?:submodules?|<=?\s*600[- ]?lines?|under\s+600\s+lines|<[a-z0-9_]+>/|"
    r"package\s+director(?:y|ies)|__init__\.py|extracted\s+module)",
    re.IGNORECASE,
)
_MONOLITH_BOUNDARY_RATCHET_RE = re.compile(
    r"(?:env_lookup_ratchet|centralization_registry|"
    r"ssot_hardcoding_scanner|ssot_boundary_auditor|"
    r"lint_layer_imports|lint_architecture_boundaries|"
    r"lint_model_neutral_naming|retrieval_surface_auditor|cost_token_budget_auditor|"
    r"cost_token_budget_probes|boundary\s+(?:check|alignment|linter|audit)|"
    r"ratchet\s+(?:ceiling|clamp|update))",
    re.IGNORECASE,
)
_MONOLITH_TEST_ALIGNMENT_RE = re.compile(
    r"(?:testing_gaps_auditor|monkeypatch|read_text|public\s+seam|"
    r"module\s+coverage|symbol\s+coverage|test\s+coverage|"
    r"\btests?/[^\s`'\"]*\.py\b|\btest_[a-z0-9_]+\.py\b|"
    r"unit\s+test\s+alignment|test\s+decoupling)",
    re.IGNORECASE,
)

_OBJECTIVE_HEADING_RE = re.compile(
    r"^#{3,4}\s+.*(?:objective|scope).*|^\s*(?:[-*+]\s+)?\*\*(?:.*(?:objective|scope).*?)\*\*",
    re.IGNORECASE,
)
_CRITERIA_HEADING_RE = re.compile(
    r"^#{3,4}\s+.*(?:acceptance\s+criteria|criteria).*|^\s*(?:[-*+]\s+)?\*\*(?:.*(?:acceptance\s+criteria|criteria).*?)\*\*",
    re.IGNORECASE,
)
_NEGATED_STAGE_DISMISSAL_RE = re.compile(
    r"\b(?:without\s+(?:checking|modifying|touching|updating|verifying|realigning|addressing)|"
    r"skip(?:ping)?|ignore|ignoring|omit(?:ting)?|do\s+not\s+(?:check|modify|touch|verify|realign))\b",
    re.IGNORECASE,
)
_DEFENSE_HEADING_RE = re.compile(
    r"^#{2,4}\s+.*(?:architectural\s+defense|what\s+stays\s+unchanged|"
    r"what\s+must\s+be\s+realigned|holistic|spine\s+trace|pipeline\s+contract).*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _HolisticSpineSpec:
    name: str
    trigger_re: re.Pattern[str]
    upstream_re: re.Pattern[str]
    downstream_re: re.Pattern[str]
    lane_noun: str
    upstream_desc: str
    downstream_desc: str


_HOLISTIC_SPINE_SPECS: tuple[_HolisticSpineSpec, ...] = (
    _HolisticSpineSpec(
        name="apps_rg",
        trigger_re=_SECTION_BULLET_DELIVERABLE_RE,
        upstream_re=_UPSTREAM_PRODUCER_RE,
        downstream_re=_DOWNSTREAM_VALIDATOR_RE,
        lane_noun="intermediate section/bullet generation or repair lanes",
        upstream_desc=(
            "Upstream Producer/Allocation stage (e.g., Stage-1 retrieval / Stage-2 C0.3 "
            "resume_graph_allocation.py / FactAnchor contract in Milestones & Deliverables, "
            "Acceptance Criteria, or explicit Architectural Defense)"
        ),
        downstream_desc=(
            "Downstream Cross-Section/X2 Validation stage (e.g., Stage-4 cross_section_x2.py / "
            "headline_x2.py / bullet_quality_floor_x2.py / narrative_quality_x2.py / "
            "bullet_fact_entailment.py in Milestones & Deliverables, Acceptance Criteria, or "
            "explicit Architectural Defense)"
        ),
    ),
    _HolisticSpineSpec(
        name="outreach_engine",
        trigger_re=_OUTREACH_INTERMEDIATE_DELIVERABLE_RE,
        upstream_re=_OUTREACH_UPSTREAM_RE,
        downstream_re=_OUTREACH_DOWNSTREAM_RE,
        lane_noun="intermediate outreach_engine (apps_lic) generation or sequence lanes",
        upstream_desc=(
            "Upstream Briefing/Research stage (e.g., outreach_engine/src/apps_lic/pipeline/"
            "briefing_resolver.py / integrations/apps_research_bridge.py in Milestones & "
            "Deliverables, Acceptance Criteria, or explicit Architectural Defense)"
        ),
        downstream_desc=(
            "Downstream Outreach Validation/Repair stage (e.g., outreach_engine/src/apps_lic/"
            "domain/validators.py / domain/repair.py / judges/evaluator.py in Milestones & "
            "Deliverables, Acceptance Criteria, or explicit Architectural Defense)"
        ),
    ),
    _HolisticSpineSpec(
        name="apps_research",
        trigger_re=_RESEARCH_INTERMEDIATE_DELIVERABLE_RE,
        upstream_re=_RESEARCH_UPSTREAM_RE,
        downstream_re=_RESEARCH_DOWNSTREAM_RE,
        lane_noun="intermediate apps_research synthesis or assembly engines",
        upstream_desc=(
            "Upstream Retrieval/JD-Intent stage (e.g., apps_research/integrations/"
            "search_retrieval.py / types/jd_intent_coverage.py / engines/research_retrieval_engine.py "
            "in Milestones & Deliverables, Acceptance Criteria, or explicit Architectural Defense)"
        ),
        downstream_desc=(
            "Downstream Handoff/Targeting-Brief stage (e.g., apps_research/integrations/"
            "apps_rg_handoff.py / types/apps_rg_targeting_brief_contract.py in Milestones & "
            "Deliverables, Acceptance Criteria, or explicit Architectural Defense)"
        ),
    ),
)

_MONOLITH_REQUIREMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        _MONOLITH_FACADE_RE,
        "re-export facade compatibility (e.g., ImportFrom facade / __init__.py re-export shim)",
    ),
    (
        _MONOLITH_SUBMODULE_RE,
        "bounded submodule layout (e.g., <= 600-line <module>/ submodules)",
    ),
    (
        _MONOLITH_BOUNDARY_RATCHET_RE,
        "SSOT/ratchet/boundary alignment (e.g., centralization_registry.yaml, "
        "env_lookup_ratchet.json, file_budgets_ratchet.json clamping, or boundary/AST auditors)",
    ),
    (
        _MONOLITH_TEST_ALIGNMENT_RE,
        "test coverage/monkeypatch alignment (e.g., testing_gaps_auditor.py coverage and "
        "public-seam test/monkeypatch updates)",
    ),
)


def _extract_wave_subsection_lines(
    wave: object,
    heading_re: re.Pattern[str],
    *,
    include_blank: bool = False,
) -> list[str]:
    lines = getattr(wave, "lines", [])
    active = False
    result: list[str] = []
    for _line_number, line in lines:
        stripped = line.strip()
        if heading_re.search(stripped):
            active = True
            continue
        if active and (
            re.match(r"^\s*#{2,4}\s+", line)
            or re.match(r"^\s*\*\*[^*]+\*\*\s*$", line)
        ):
            break
        if active and (include_blank or stripped):
            result.append(line)
    return result


def _extract_defense_lines(content: str) -> list[str]:
    lines = content.splitlines()
    active = False
    active_level = 0
    extracted: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _DEFENSE_HEADING_RE.match(stripped):
            active = True
            active_level = len(stripped) - len(stripped.lstrip("#"))
            extracted.append(stripped)
            continue
        if active and stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level <= active_level and not _DEFENSE_HEADING_RE.match(stripped):
                active = False
                continue
        if active and stripped:
            extracted.append(stripped)
    return extracted


def _has_affirmative_stage_coverage(
    pattern: re.Pattern[str], candidate_lines: Sequence[str]
) -> bool:
    for line in candidate_lines:
        if pattern.search(line) and not _NEGATED_STAGE_DISMISSAL_RE.search(line):
            return True
    return False


def _wave_triggers_monolith_split(wave: object) -> bool:
    deliv_lines = list(getattr(wave, "deliverable_items", []))
    if any(
        _MONOLITH_SPLIT_TRIGGER_RE.search(line) and not _NEGATED_STAGE_DISMISSAL_RE.search(line)
        for line in deliv_lines
    ):
        return True
    if not any(".py" in line or "file_budgets_ratchet" in line for line in deliv_lines):
        return False
    title = str(getattr(wave, "title", "") or "")
    obj_lines = _extract_wave_subsection_lines(wave, _OBJECTIVE_HEADING_RE)
    header_and_obj = [title, *obj_lines]
    return any(
        _MONOLITH_SPLIT_TRIGGER_RE.search(line) and not _NEGATED_STAGE_DISMISSAL_RE.search(line)
        for line in header_and_obj
    )


def validate_holistic_pipeline_alignment(
    content: str, waves: Sequence[object], filename: str
) -> list[str]:
    """Pipeline bundling and monolith split size requirements are lifted (INV-REFACTOR-EXTENT-UNBOUNDED)."""
    _ = (content, waves, filename)
    return []


def _gate_lines(wave: object) -> list[str]:
    return _extract_wave_subsection_lines(wave, _GATE_HEADING, include_blank=True)


def validate_execution_evidence(content: str, waves: Sequence[object], filename: str) -> list[str]:
    """Require bounded plans and explicit run/evidence fields in each wave gate."""
    from tools.implementation_plan_core.wave_dag import strip_and_validate_shard_manifests

    errors: list[str] = []
    prose_content, manifest_errors = strip_and_validate_shard_manifests(content, filename)
    errors.extend(manifest_errors)
    word_count = len(prose_content.split())
    if MAX_PLAN_WORDS > 0 and word_count > MAX_PLAN_WORDS:
        errors.append(
            f"{filename}: Plan has {word_count} words; newly authored wave plans are capped at "
            f"{MAX_PLAN_WORDS} words."
        )

    for wave in waves:
        gate_lines = _gate_lines(wave)
        if not gate_lines:
            continue  # The structural validator reports the missing gate heading.
        present = {
            label for label, pattern in _FIELD_PATTERNS.items()
            if any(pattern.search(line) for line in gate_lines)
        }
        missing = [label for label in _FIELD_PATTERNS if label not in present]
        if missing:
            number = getattr(wave, "wave_id", getattr(wave, "number", "?"))
            errors.append(
                f"{filename}: Wave {number} completion gate must specify: {', '.join(missing)}. "
                "Receipts document runs; independently observed behavior determines completion."
            )
    errors.extend(validate_holistic_pipeline_alignment(content, waves, filename))
    return errors
