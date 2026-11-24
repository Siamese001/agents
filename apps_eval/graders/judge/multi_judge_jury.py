"""Disjoint Multi-Judge Jury Aggregator (2025-2026 Zero-Egress Consensus Panel, DIE Parity).

Implements 2025-2026 Anthropic multi-judge consensus ("Demystifying Evals for AI
Agents") and OpenAI HealthBench (2025) meta-evaluation alignment across disjoint
Antigravity IDE subagent model families (`neon`, `carbon`, `argon`, `gpt-oss`) with zero
commercial API egress (`$0.00`).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median
from typing import Any, Callable, Mapping, Sequence

from apps_eval.graders.judge.external_rubric_store import compute_payload_sha256
from apps_eval.graders.judge.frontier_calibration_stats import compute_krippendorffs_alpha
from apps_eval.graders.judge.ide_judge_drift_evaluator import (
    normalize_ide_judge_score,
    verify_ide_judge_receipt_provenance,
)


@dataclass(frozen=True)
class JuryAggregatedVerdict:
    """Provenance-sealed verdict pooled across >= 2 disjoint IDE model families."""

    case_id: str
    artifact_sha256: str
    member_families: tuple[str, ...]
    member_count: int
    verdict: str
    overall_score: float
    inter_judge_alpha: float
    jury_split_detected: bool
    evaluator_kind: str
    judge_model_family: str
    bundle_digest: str
    normalized_unit_score: float = 0.0
    external_http_call_count: int = 0

    def to_verdict_dict(self) -> dict[str, Any]:
        """Serialize as a drift-evaluator-compatible IDE judge verdict receipt."""
        out = asdict(self)
        out["member_families"] = list(self.member_families)
        return out


def _validate_jury_member(
    case_id: str,
    verdict_obj: Mapping[str, Any],
    expected_sha: str | None,
) -> tuple[str, float, str, str]:
    defects = verify_ide_judge_receipt_provenance(verdict_obj)
    if defects:
        raise ValueError(f"Jury member for '{case_id}' failed provenance verification: {defects}")
    art_sha = str(verdict_obj.get("artifact_sha256") or "").strip().lower()
    if len(art_sha) != 64:
        raise ValueError(f"Jury member for '{case_id}' missing valid 64-char artifact_sha256.")
    if expected_sha and art_sha != expected_sha.strip().lower():
        raise ValueError(f"Jury member artifact_sha256 mismatch for '{case_id}'.")
    unit_score, verdict, family = normalize_ide_judge_score(verdict_obj)
    return family, unit_score, verdict, art_sha


def _resolve_jury_majority(
    verdicts: Sequence[str],
    member_verdicts: Sequence[Mapping[str, Any]],
    tie_breaker_fn: Callable[[Sequence[Mapping[str, Any]]], str] | None,
) -> tuple[str, bool]:
    pass_votes = sum(1 for v in verdicts if v == "PASS")
    fail_votes = sum(1 for v in verdicts if v == "FAIL")
    split = pass_votes > 0 and fail_votes > 0
    if pass_votes > fail_votes:
        return "PASS", split
    if fail_votes > pass_votes:
        return "FAIL", split
    if tie_breaker_fn is not None:
        tb = str(tie_breaker_fn(member_verdicts)).strip().upper()
        return (tb if tb in {"PASS", "FAIL"} else "FAIL"), split
    return "FAIL", split


def aggregate_disjoint_ide_jury_verdicts(
    case_id: str,
    member_verdicts: Sequence[Mapping[str, Any]],
    *,
    expected_artifact_sha256: str | None = None,
    tie_breaker_fn: Callable[[Sequence[Mapping[str, Any]]], str] | None = None,
) -> JuryAggregatedVerdict:
    """Pool >= 2 disjoint IDE model-family judge receipts via majority vote and median score."""
    if len(member_verdicts) < 2:
        raise ValueError("Disjoint multi-judge jury requires at least 2 member verdicts.")
    families: list[str] = []
    unit_scores: list[float] = []
    verdicts: list[str] = []
    shas: set[str] = set()
    for mv in member_verdicts:
        fam, u_score, verd, sha = _validate_jury_member(case_id, mv, expected_artifact_sha256)
        if fam in families:
            raise ValueError(
                f"Disjoint jury rejected duplicate model family '{fam}' for '{case_id}'; members must come from distinct families."
            )
        families.append(fam)
        unit_scores.append(u_score)
        verdicts.append(verd)
        shas.add(sha)
    if len(shas) != 1:
        raise ValueError(f"Jury members for '{case_id}' disagree on artifact_sha256.")
    canonical_sha = next(iter(shas))
    pooled_verdict, split_detected = _resolve_jury_majority(verdicts, member_verdicts, tie_breaker_fn)
    pooled_unit = round(float(median(unit_scores)), 4)
    alpha = compute_krippendorffs_alpha([[v] for v in verdicts], level="nominal")
    digest_payload = {
        "case_id": case_id,
        "artifact_sha256": canonical_sha,
        "member_families": sorted(families),
        "verdict": pooled_verdict,
        "normalized_unit_score": pooled_unit,
    }
    bundle_digest = compute_payload_sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    )
    return JuryAggregatedVerdict(
        case_id=case_id,
        artifact_sha256=canonical_sha,
        member_families=tuple(families),
        member_count=len(families),
        verdict=pooled_verdict,
        overall_score=pooled_unit,
        normalized_unit_score=pooled_unit,
        inter_judge_alpha=alpha,
        jury_split_detected=split_detected,
        evaluator_kind="antigravity_ide_blind_subagent_judge",
        judge_model_family="disjoint_jury",
        bundle_digest=bundle_digest,
        external_http_call_count=0,
    )


__all__ = [
    "JuryAggregatedVerdict",
    "aggregate_disjoint_ide_jury_verdicts",
]
