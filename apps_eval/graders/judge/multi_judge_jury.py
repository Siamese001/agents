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

from apps_eval.graders.judge._core_governance_bridge import (
    get_judge_disjoint_jury_v3,
    get_judge_ide_router_v3,
)
from apps_eval.graders.judge.blind_protocol import infer_provider_family
from apps_eval.graders.judge.external_rubric_store import compute_payload_sha256
from apps_eval.graders.judge.frontier_calibration_stats import compute_krippendorffs_alpha
from apps_eval.graders.judge.ide_judge_drift_evaluator import (
    normalize_ide_judge_score,
    verify_ide_judge_receipt_provenance,
)

_jury_v3 = get_judge_disjoint_jury_v3()
_ide_rtr = get_judge_ide_router_v3()


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
    pass_threshold: float = 0.80
    critical_veto_triggered: bool = False
    passed: bool = False
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
    author_fam: str,
) -> tuple[str, float, str, str, bool]:
    defects = verify_ide_judge_receipt_provenance(verdict_obj)
    if defects:
        raise ValueError(f"Jury member for '{case_id}' failed provenance verification: {defects}")
    art_sha = str(verdict_obj.get("artifact_sha256") or "").strip().lower()
    if len(art_sha) != 64:
        raise ValueError(f"Jury member for '{case_id}' missing valid 64-char artifact_sha256.")
    if expected_sha and art_sha != expected_sha.strip().lower():
        raise ValueError(f"Jury member artifact_sha256 mismatch for '{case_id}'.")
    unit_score_raw, verdict_norm, family = normalize_ide_judge_score(verdict_obj)
    unit_score, verdict_checked, crit_veto = _jury_v3.extract_verified_v3_unit_score(
        {
            "normalized_unit_score": unit_score_raw,
            "verdict": verdict_norm,
            "score_scale": "0_to_1",
            "critical_veto_triggered": bool(verdict_obj.get("critical_veto_triggered", False)),
            "llm_judge_executed": verdict_obj.get("llm_judge_executed", True),
        }
    )
    member_author = infer_provider_family(str(verdict_obj.get("author_model_family") or ""))
    eff_author = author_fam or (member_author if member_author != "unknown" else "")
    if eff_author and family == eff_author:
        raise ValueError(
            f"Disjoint jury rejected self-grading member family '{family}' == author '{eff_author}' for '{case_id}'."
        )
    return family, unit_score, verdict_checked, art_sha, crit_veto


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
    expected_bundle_digest: str | None = None,
    expected_rubric_sha256: str | None = None,
    author_model_family: str | None = None,
    pass_threshold: float = 0.80,
    tie_breaker_fn: Callable[[Sequence[Mapping[str, Any]]], str] | None = None,
) -> JuryAggregatedVerdict:
    """Delegate disjoint IDE jury consensus to centralized `core-governance` with critical-veto and threshold locks."""
    if len(member_verdicts) < 2:
        raise ValueError("Disjoint multi-judge jury requires at least 2 member verdicts.")
    author_fam = infer_provider_family(author_model_family) if author_model_family else ""
    if author_fam == "unknown":
        author_fam = ""

    families: list[str] = []
    unit_scores: list[float] = []
    verdicts: list[str] = []
    shas: set[str] = set()
    any_crit_veto = False
    bundle_digests: set[str] = set()
    canonical_ide_set = set(_ide_rtr.APPROVED_IDE_FAMILIES) | set(_ide_rtr.APPROVED_OFFLINE_LOCAL_FAMILIES)

    for mv in member_verdicts:
        fam, u_score, verd, sha, crit = _validate_jury_member(case_id, mv, expected_artifact_sha256, author_fam)
        if fam in families:
            raise ValueError(
                f"Disjoint jury rejected duplicate model family '{fam}' for '{case_id}'; members must come from distinct families."
            )
        families.append(fam)
        unit_scores.append(u_score)
        verdicts.append(verd)
        shas.add(sha)
        if crit:
            any_crit_veto = True
        bd = str(mv.get("bundle_digest") or "").strip()
        if len(bd) == 64:
            bundle_digests.add(bd)

    if len(shas) != 1:
        raise ValueError(f"Jury members for '{case_id}' disagree on artifact_sha256.")
    canonical_sha = next(iter(shas))

    shared_bd = expected_bundle_digest or (next(iter(bundle_digests)) if len(bundle_digests) == 1 else "")
    if (
        tie_breaker_fn is None
        and len(shared_bd) == 64
        and all(f in canonical_ide_set for f in families)
        and (not author_fam or author_fam in canonical_ide_set)
    ):
        central_members = [
            {
                "evaluator_kind": "antigravity_ide_blind_subagent_judge",
                "judge_model_family": fam,
                "bundle_digest": shared_bd,
                "artifact_sha256": canonical_sha,
                "rubric_sha256": str(expected_rubric_sha256 or mv.get("rubric_sha256") or ""),
                "score_scale": "0_to_1",
                "normalized_unit_score": u_sc,
                "verdict": v_str,
                "critical_veto_triggered": bool(mv.get("critical_veto_triggered", False)),
                "external_http_call_count": 0,
            }
            for mv, fam, u_sc, v_str in zip(member_verdicts, families, unit_scores, verdicts)
        ]
        central_res = _jury_v3.aggregate_disjoint_v3_jury(
            case_id=case_id,
            expected_bundle_digest=shared_bd,
            expected_artifact_sha256=canonical_sha,
            expected_rubric_sha256=expected_rubric_sha256,
            member_verdicts=central_members,
            author_model_family=author_fam or None,
            pass_threshold=pass_threshold,
            min_disjoint_families=2,
        )
        return JuryAggregatedVerdict(
            case_id=case_id,
            artifact_sha256=canonical_sha,
            member_families=central_res.member_families,
            member_count=central_res.member_count,
            verdict=central_res.verdict,
            overall_score=central_res.normalized_unit_score,
            normalized_unit_score=central_res.normalized_unit_score,
            pass_threshold=central_res.pass_threshold,
            critical_veto_triggered=central_res.critical_veto_triggered,
            passed=central_res.passed,
            inter_judge_alpha=central_res.inter_judge_alpha,
            jury_split_detected=central_res.jury_split_detected,
            evaluator_kind="antigravity_ide_blind_subagent_judge",
            judge_model_family="disjoint_jury",
            bundle_digest=central_res.bundle_digest,
            external_http_call_count=0,
        )

    majority_verdict, split_detected = _resolve_jury_majority(verdicts, member_verdicts, tie_breaker_fn)
    if max(unit_scores) - min(unit_scores) > 0.15:
        split_detected = True
    pooled_unit = round(float(median(unit_scores)), 4)
    passed = (not any_crit_veto) and (majority_verdict == "PASS") and (pooled_unit >= pass_threshold - 1e-9)
    pooled_verdict = "PASS" if passed else "FAIL"
    alpha = compute_krippendorffs_alpha([[v] for v in verdicts], level="nominal")
    digest_payload = {
        "case_id": case_id,
        "artifact_sha256": canonical_sha,
        "member_families": sorted(families),
        "verdict": pooled_verdict,
        "normalized_unit_score": pooled_unit,
    }
    bundle_digest = expected_bundle_digest or compute_payload_sha256(
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
        pass_threshold=pass_threshold,
        critical_veto_triggered=any_crit_veto,
        passed=passed,
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
