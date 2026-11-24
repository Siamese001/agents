"""Base judge infrastructure for `apps_research` (zero cross-subsystem `apps_rg` imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Tuple

from apps_research.engines.judges.v3_brief_judge import evaluate_research_brief_v3

G09_DIMENSIONS = ["source_authority", "citation_quality", "attribution_completeness"]
G10_DIMENSIONS = ["claim_support", "contradiction_resolution", "factual_grounding"]
G22_DIMENSIONS = ["coverage_depth", "injection_quality", "completeness"]
G25_DIMENSIONS = ["cache_compatibility", "downstream_relevance", "semantic_stability"]


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Self-contained `apps_research` judge result contract (decoupled from `apps_rg`)."""

    judge_id: str
    dimension: str
    score: float | None
    confidence: float
    evidence_refs: Tuple[str, ...] = ()
    run_id: str = ""
    judge_version: str = "v3.0.0"
    llm_judge_executed: bool = False


@dataclass(frozen=True, slots=True)
class JudgeEvidence:
    """Evidence produced by a judge evaluation."""

    judge_id: str
    dimension: str
    score: float
    confidence: float
    reasoning: str
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_gate_evidence(self, gate_id: str) -> Dict[str, Any]:
        return {
            "gate_id": gate_id,
            "dimension": self.dimension,
            "score": self.score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence_refs": list(self.evidence_refs),
            "judge_id": self.judge_id,
            "timestamp": self.timestamp,
        }


class BaseResearchJudge:
    """Metadata & Judge v3 adapter base for `apps_research` (honest stub flags, zero fake calibration)."""

    judge_id: str = ""
    dimension: str = ""
    version: str = "v3.0.0"
    IS_STUB: bool = True
    IS_CALIBRATED: bool = False
    v3_profile_token: str = "company_research_brief:company_brief_synthesis"

    def to_judge_result(self, evidence: JudgeEvidence, run_id: str = "") -> JudgeResult:
        return JudgeResult(
            judge_id=self.judge_id,
            dimension=self.dimension,
            score=evidence.score,
            confidence=evidence.confidence,
            evidence_refs=evidence.evidence_refs,
            run_id=run_id,
            judge_version=self.version,
        )

    def evaluate_v3(
        self,
        brief_payload: Mapping[str, Any],
        *,
        artifact_id: str = "research-brief",
        llm_raw_response: Mapping[str, Any] | str | None = None,
        judge_model_id: str | None = None,
    ) -> Any:
        return evaluate_research_brief_v3(
            artifact_id=artifact_id,
            brief_payload=brief_payload,
            profile_token=self.v3_profile_token,
            llm_raw_response=llm_raw_response,
            judge_model_id=judge_model_id,
        )


def map_judge_evidence_to_gate(
    evidence: JudgeEvidence,
    gate_id: str,
    threshold: float = 0.80,
) -> Tuple[str, float, str]:
    _ = gate_id
    score = evidence.score
    result = "PASS" if score >= threshold else ("WARN" if score >= threshold * 0.8 else "FAIL")
    return result, score, f"{evidence.judge_id} scored {evidence.dimension}={score:.2f} (threshold={threshold:.2f})"
