"""Rubric YAML caching, EvaluationReport model, and rubric configuration base for ExecutiveOutreachJudgePanel."""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from apps_lic.domain.models import (
    AuthoritativeVerdict,
    CandidateProfile,
    OutreachMessageDraft,
    TargetOpportunity,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    EmDashValidator,
    ForbiddenClaimsValidator,
    GroundingValidator,
    MarkdownLinkValidator,
    OutboundPrivacyValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
    SubordinateToneValidator,
    UnsupportedPersonalizationValidator,
)

_log = logging.getLogger(__name__)
_RUBRIC_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_RUBRIC_LOCK = threading.Lock()


def _load_cached_rubric_file(file_path: Path) -> dict[str, Any]:
    """Parse and cache a rubric YAML file, keyed by resolved path and mtime."""
    path_str = str(file_path.resolve())
    mtime: float | None = None
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        mtime = None
    if mtime is None:
        return {}
    with _RUBRIC_LOCK:
        if path_str in _RUBRIC_CACHE:
            cached_mtime, cached_data = _RUBRIC_CACHE[path_str]
            if cached_mtime == mtime:
                return dict(cached_data)
    data: dict[str, Any] = {}
    try:
        parsed = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        _log.warning("Failed parsing rubric file %s: %s", file_path, exc)
    with _RUBRIC_LOCK:
        _RUBRIC_CACHE[path_str] = (mtime, data)
    return dict(data)


@dataclass
class EvaluationReport:
    """Consolidated Stage A deterministic preflight + Stage B report (never masquerades as LLM when deterministic)."""
    passed: bool
    status: str = "PASSED"
    judge_passed: bool = True
    hard_gate_passed: bool = True
    evaluator_kind: str = "deterministic_gate"
    llm_judge_executed: bool = False
    normalized_unit_score: float | None = None
    lens1_altitude_score: float = 1.0
    lens2_grounding_score: float = 1.0
    lens3_resonance_score: float = 1.0
    lens4_cta_score: float = 1.0
    lens5_anti_spam_score: float = 1.0
    lens6_constraints_score: float = 1.0
    composite_score: float = 1.0
    score_band: str = "EXEMPLARY"
    hop1_classifier_score: float = 1.0
    hop2_grounding_score: float = 1.0
    hop6_alignment_score: float = 1.0
    hop8_narrative_score: float = 1.0
    feedback: List[str] = field(default_factory=list)
    remediation_hints: List[str] = field(default_factory=list)
    lens_scores: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "PASSED" if self.passed else "BLOCKED"
        elif not self.passed and self.status == "PASSED":
            self.status = "BLOCKED"
        elif self.passed and self.status == "BLOCKED":
            self.passed = False
        if not self.lens_scores:
            self.lens_scores = {
                "lens1_altitude": self.lens1_altitude_score,
                "lens2_grounding": self.lens2_grounding_score,
                "lens3_resonance": self.lens3_resonance_score,
                "lens4_cta": self.lens4_cta_score,
                "lens5_anti_spam": self.lens5_anti_spam_score,
                "lens6_constraints": self.lens6_constraints_score,
            }

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed, "status": self.status, "judge_passed": self.judge_passed,
            "hard_gate_passed": self.hard_gate_passed, "evaluator_kind": self.evaluator_kind,
            "llm_judge_executed": self.llm_judge_executed, "normalized_unit_score": self.normalized_unit_score,
            "composite_score": self.composite_score, "score_band": self.score_band,
            "lens1_altitude_score": self.lens1_altitude_score, "lens2_grounding_score": self.lens2_grounding_score,
            "lens3_resonance_score": self.lens3_resonance_score, "lens4_cta_score": self.lens4_cta_score,
            "lens5_anti_spam_score": self.lens5_anti_spam_score, "lens6_constraints_score": self.lens6_constraints_score,
            "hop1_classifier_score": self.hop1_classifier_score, "hop2_grounding_score": self.hop2_grounding_score,
            "hop6_alignment_score": self.hop6_alignment_score, "hop8_narrative_score": self.hop8_narrative_score,
            "feedback": list(self.feedback), "remediation_hints": list(self.remediation_hints), "lens_scores": dict(self.lens_scores),
        }


class RubricConfigAndTournamentBase:
    """Base judge panel providing rubric configuration loading and persona tournament scoring."""

    def __init__(self, rubrics_dir: Path | str | None = None) -> None:
        if rubrics_dir is None:
            outreach_root = Path(__file__).resolve().parents[4]
            self.rubrics_dir = outreach_root / "config" / "rubrics"
        else:
            self.rubrics_dir = Path(rubrics_dir)
        self._rubrics = self._load_rubrics()
        self._active_rubric = self._resolve_active_rubric()
        self._spam_validator = SpamTriggerValidator()
        self._length_validator = ChannelLengthValidator()
        self._question_validator = QuestionEndingValidator()
        self._grounding_validator = GroundingValidator()
        self._dash_validator = EmDashValidator()
        self._link_validator = MarkdownLinkValidator()
        self._tone_validator = SubordinateToneValidator()
        self._forbidden_validator = ForbiddenClaimsValidator()
        self._unsupported_personalization_validator = UnsupportedPersonalizationValidator()
        self._privacy_validator = OutboundPrivacyValidator()

    @staticmethod
    def requires_human_signoff(top_score: float, runner_up_score: float, margin_threshold: float = 0.15) -> bool:
        """Return True when top two candidate framings score within the margin threshold (default 15%)."""
        return abs(top_score - runner_up_score) <= margin_threshold

    def evaluate_authoritative(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> AuthoritativeVerdict:
        raise NotImplementedError

    def evaluate_persona_tournament(
        self, drafts: List[OutreachMessageDraft], candidate: CandidateProfile,
        opportunity: TargetOpportunity, margin_threshold: float = 0.15,
    ) -> dict[str, Any]:
        """Score competing candidate outreach drafts via archetype skeptic evaluation and determine signoff."""
        if not drafts:
            return {"winner_draft_id": "", "top_score": 0.0, "runner_up_score": 0.0, "margin": 0.0, "requires_human_signoff": False, "rankings": [], "passed": False}
        rankings: list[dict[str, Any]] = []
        for draft in drafts:
            verdict = self.evaluate_authoritative(draft, candidate, opportunity)
            c_score = verdict.composite_score
            if math.isnan(c_score) or math.isinf(c_score):
                c_score = 0.0
            score = round(min(1.0, c_score + (0.02 if draft.grounded_facts_used else 0.0)), 4)
            passed = bool(verdict.passed) if c_score > 0.0 else False
            rankings.append({
                "draft_id": draft.draft_id, "composite_score": c_score,
                "tournament_score": score, "passed": passed,
                "grounded_facts_used": list(draft.grounded_facts_used),
            })

        rankings.sort(
            key=lambda r: (
                -1 if r["passed"] else 0,
                -r["tournament_score"],
                -len(r.get("grounded_facts_used", [])),
                r["draft_id"],
            )
        )

        passing_rankings = [r for r in rankings if r["passed"]]
        if not passing_rankings:
            winner_draft_id = ""
            tournament_passed = False
            top_score = float(rankings[0]["tournament_score"])
            runner_up_score = float(rankings[1]["tournament_score"]) if len(rankings) > 1 else 0.0
            signoff = False
        else:
            winner_draft_id = str(rankings[0]["draft_id"])
            tournament_passed = True
            top_score = float(rankings[0]["tournament_score"])
            if len(passing_rankings) > 1:
                runner_up_score = float(passing_rankings[1]["tournament_score"])
                signoff = self.requires_human_signoff(top_score, runner_up_score, margin_threshold=margin_threshold)
            else:
                runner_up_score = float(rankings[1]["tournament_score"]) if len(rankings) > 1 else 0.0
                signoff = False

        return {
            "winner_draft_id": winner_draft_id,
            "top_score": top_score,
            "runner_up_score": runner_up_score,
            "margin": round(abs(top_score - runner_up_score), 4),
            "requires_human_signoff": signoff,
            "rankings": rankings,
            "passed": tournament_passed,
        }

    def _load_rubrics(self) -> dict[str, dict[str, Any]]:
        rubrics: dict[str, dict[str, Any]] = {}
        if not self.rubrics_dir.is_dir():
            return rubrics
        for f in self.rubrics_dir.glob("*.yaml"):
            data = _load_cached_rubric_file(f)
            if isinstance(data, dict) and isinstance(data.get("rubric_id"), str) and data.get("rubric_id"):
                rubrics[data["rubric_id"]] = data
        return rubrics

    def _resolve_active_rubric(self) -> dict[str, Any]:
        if "executive_outreach_rubric_v3" in self._rubrics:
            return self._rubrics["executive_outreach_rubric_v3"]
        v3_file = self.rubrics_dir / "executive_outreach_rubric_v3.yaml"
        if v3_file.is_file():
            return _load_cached_rubric_file(v3_file)
        return {}

    def get_threshold(self, lens_key: str, default: float) -> float:
        lenses = self._active_rubric.get("lenses")
        if isinstance(lenses, dict) and isinstance(lenses.get(lens_key), dict) and "threshold" in lenses[lens_key]:
            try:
                val = float(lenses[lens_key]["threshold"])
                if not math.isnan(val) and not math.isinf(val):
                    return val
            except (ValueError, TypeError):
                pass
        return default

    def get_lens_weight(self, lens_key: str, default: float) -> float:
        lenses = self._active_rubric.get("lenses")
        if isinstance(lenses, dict) and isinstance(lenses.get(lens_key), dict) and "weight" in lenses[lens_key]:
            try:
                val = float(lenses[lens_key]["weight"])
                if not math.isnan(val) and not math.isinf(val):
                    return val
            except (ValueError, TypeError):
                pass
        return default

    def get_min_composite_score(self, default: float = 0.75) -> float:
        criteria = self._active_rubric.get("passing_criteria")
        if isinstance(criteria, dict) and "min_composite_score" in criteria:
            try:
                val = float(criteria["min_composite_score"])
                if not math.isnan(val) and not math.isinf(val):
                    return val
            except (ValueError, TypeError):
                pass
        return default

    def get_remediation_hint(self, lens_key: str, default: str) -> str:
        lenses = self._active_rubric.get("lenses")
        if not isinstance(lenses, dict):
            return default
        lens_spec = lenses.get(lens_key)
        if isinstance(lens_spec, dict) and "remediation_hint" in lens_spec:
            return str(lens_spec["remediation_hint"])
        return default


__all__ = [
    "AuthoritativeVerdict",
    "EvaluationReport",
    "RubricConfigAndTournamentBase",
    "_RUBRIC_CACHE",
    "_RUBRIC_LOCK",
    "_load_cached_rubric_file",
]
