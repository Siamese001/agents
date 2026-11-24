"""IDE LLM-as-a-Judge External-Rubric Drift Evaluator (DIE Parity).

Compares provenance-verified in-editor Blind Subagent Judge verdicts (`neon`,
`carbon`, `argon`, `gpt-oss`) against human external-rubric gold labels (`1..5` + `PASS`/`FAIL`)
to detect agreement degradation, rank inversion, leniency inflation, severity
collapse, and pairwise position bias.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from apps_eval.graders.judge.blind_protocol import NON_LLM_EVALUATOR_KINDS, is_synthetic_model_id
from apps_eval.graders.judge.calibration import PositionSwapDebiaser, compute_brier_and_ece, compute_cohens_kappa
from apps_eval.graders.judge.external_rubric_store import ExternalHumanLabelRecord, compute_payload_sha256
from apps_eval.graders.judge.frontier_calibration_stats import (
    classify_cohort_power,
    compute_failure_tag_detection_recall,
    compute_ppi_calibrated_pass_rate,
    compute_rogan_gladen_prevalence,
    compute_tpr_tnr_balanced_accuracy,
)

_KNOWN_IDE_FAMILIES: tuple[str, ...] = ("neon", "carbon", "argon", "open_weights", "anthropic", "google", "openai")


def normalize_judge_family(raw_family: str) -> str:
    """Normalize IDE judge family label to a canonical slug (`neon`, `carbon`, `argon`, `open_weights`, etc.)."""
    low = str(raw_family or "").strip().lower()
    if low == "disjoint_jury":
        return "disjoint_jury"
    for tok in ("neon", "carbon", "argon"):
        if tok in low:
            return tok
    if "claude" in low or "anthropic" in low:
        return "carbon"
    if "gemini" in low or "google" in low:
        return "neon"
    if "oss" in low or "openai" in low:
        return "open_weights"
    return low or "neon"


def verify_ide_judge_receipt_provenance(verdict_obj: Mapping[str, Any]) -> list[str]:
    """Verify zero-egress in-editor judge receipt provenance."""
    defects: list[str] = []
    ev_kind = str(verdict_obj.get("evaluator_kind") or "").strip().lower()
    if not ev_kind or ev_kind in NON_LLM_EVALUATOR_KINDS:
        defects.append(f"NON_LLM_EVALUATOR_KIND:{ev_kind or 'missing'}")
    fam_raw = str(
        verdict_obj.get("judge_model_family")
        or verdict_obj.get("primary_model_family")
        or verdict_obj.get("judge_model_id")
        or verdict_obj.get("judge_model_label")
        or ""
    ).strip()
    if not fam_raw or is_synthetic_model_id(fam_raw):
        defects.append(f"SYNTHETIC_OR_MISSING_MODEL_FAMILY:{fam_raw or 'empty'}")
    if int(verdict_obj.get("external_http_call_count") or 0) != 0:
        defects.append("EXTERNAL_HTTP_JUDGE_FORBIDDEN")
    bd = str(verdict_obj.get("bundle_digest") or "").strip()
    if len(bd) < 16:
        defects.append("MISSING_OR_SHORT_BUNDLE_DIGEST")
    return defects


def _average_tie_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and math.isclose(indexed[j + 1][1], indexed[i][1], abs_tol=1e-9):
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Compute tie-adjusted Spearman rank correlation coefficient in [-1.0, 1.0]."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rx = _average_tie_ranks(xs)
    ry = _average_tie_ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    denom = math.sqrt(vx * vy)
    if denom <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, round(cov / denom, 4)))


def compute_quadratic_weighted_kappa(human_bins: Sequence[int], judge_bins: Sequence[int]) -> float:
    """Compute 5-level (1..5) quadratic weighted Cohen's Kappa."""
    if len(human_bins) != len(judge_bins) or not human_bins:
        return 0.0
    n = len(human_bins)
    k = 5
    observed = [[0] * k for _ in range(k)]
    for h, j in zip(human_bins, judge_bins):
        hi = max(0, min(k - 1, int(h) - 1))
        ji = max(0, min(k - 1, int(j) - 1))
        observed[hi][ji] += 1
    hist_h = [sum(observed[r]) for r in range(k)]
    hist_j = [sum(observed[r][c] for r in range(k)) for c in range(k)]
    num = 0.0
    den = 0.0
    scale = float((k - 1) ** 2)
    for r in range(k):
        for c in range(k):
            w = ((r - c) ** 2) / scale
            exp_rc = (hist_h[r] * hist_j[c]) / float(n)
            num += w * observed[r][c]
            den += w * exp_rc
    if den <= 1e-12:
        return 0.0
    return max(-1.0, min(1.0, round(1.0 - (num / den), 4)))


_SCORE_KEYS = (
    "normalized_unit_score",
    "overall_score",
    "weighted_overall_score",
    "recomputed_weighted_overall",
    "composite_score",
    "average_relevance_score",
)


def _extract_raw_judge_score(verdict_payload: Mapping[str, Any]) -> float:
    raw_score = next((verdict_payload[k] for k in _SCORE_KEYS if verdict_payload.get(k) is not None), None)
    if raw_score is None or isinstance(raw_score, bool) or not math.isfinite(float(raw_score)):
        raise ValueError("IDE judge verdict is missing a finite numeric score.")
    val = float(raw_score)
    if val < 0.0 or val > 100.0:
        raise ValueError(f"IDE judge score {val} outside supported [0.0, 100.0] range.")
    return val


def _scale_raw_score_to_unit(val: float, verdict_payload: Mapping[str, Any]) -> float:
    if verdict_payload.get("normalized_unit_score") is not None:
        u = float(verdict_payload["normalized_unit_score"])
        if u < 0.0 or u > 1.0:
            raise ValueError(f"Judge v3 normalized_unit_score {u} must lie in [0.0, 1.0].")
        return u
    scale = str(verdict_payload.get("score_scale") or "").strip().lower()
    if scale in {"0_to_1", "unit"}:
        return max(0.0, min(1.0, val))
    if scale == "1_to_5":
        return max(0.0, min(1.0, (val - 1.0) / 4.0))
    if scale == "0_to_5":
        return max(0.0, min(1.0, val / 5.0))
    if val <= 1.0:
        return val
    return val / 10.0 if val <= 10.0 else val / 100.0


def normalize_ide_judge_score(verdict_payload: Mapping[str, Any]) -> tuple[float, str, str]:
    """Normalize an IDE judge score (`0..1`, `0..10`, or `0..100`) onto `[0.0, 1.0]`."""
    val = _extract_raw_judge_score(verdict_payload)
    norm = _scale_raw_score_to_unit(val, verdict_payload)
    raw_verdict = str(verdict_payload.get("verdict") or verdict_payload.get("status") or "").strip().upper()
    verdict = (
        raw_verdict
        if raw_verdict in {"PASS", "FAIL"}
        else ("PASS" if bool(verdict_payload.get("gate_passed")) else "FAIL")
    )
    fam_raw = str(
        verdict_payload.get("judge_model_family")
        or verdict_payload.get("primary_model_family")
        or verdict_payload.get("judge_model_label")
        or verdict_payload.get("judge_model_id")
        or "neon"
    )
    fam = normalize_judge_family(fam_raw)
    return round(norm, 4), verdict, fam


def _quantize_unit_to_likert(unit_score: float) -> int:
    clamped = max(0.0, min(1.0, float(unit_score)))
    return max(1, min(5, int(round(1.0 + 4.0 * clamped))))


@dataclass(frozen=True)
class ExternalRubricDriftReport:
    """Sealed statistical drift report for an IDE LLM-as-a-Judge against human gold."""

    judge_surface: str
    ide_model_family: str
    partition: str
    external_rubric_sha256: str
    evaluated_cases: int
    cohens_kappa: float
    weighted_quadratic_kappa: float
    spearman_rho: float
    signed_leniency_bias: float
    false_acceptance_rate: float
    false_rejection_rate: float
    expected_calibration_error: float
    order_bias_rate: float
    passed: bool
    drift_detected: bool
    drift_codes: tuple[str, ...]
    evaluated_at_utc: str
    receipt_digest: str
    tpr: float = 0.0
    tnr: float = 0.0
    balanced_accuracy: float = 0.0
    rogan_gladen_pass_rate: float = 0.0
    rogan_gladen_ci_95: tuple[float, float] = (0.0, 0.0)
    ppi_pass_rate: float = 0.0
    cohort_power_tier: str = "UNDERPOWERED_PILOT"
    failure_tag_detection_recall: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["drift_codes"] = list(self.drift_codes)
        payload["rogan_gladen_ci_95"] = list(self.rogan_gladen_ci_95)
        return payload


def _build_sealed_report(**fields: Any) -> ExternalRubricDriftReport:
    draft = ExternalRubricDriftReport(**fields, receipt_digest="0" * 64)
    digest_body = {k: v for k, v in draft.to_dict().items() if k != "receipt_digest"}
    digest_hex = compute_payload_sha256(
        json.dumps(digest_body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    )
    return ExternalRubricDriftReport(**fields, receipt_digest=digest_hex)


class IDEJudgeDriftEvaluator:
    """Evaluates IDE Blind Subagent Judge drift against human external-rubric labels."""

    def __init__(
        self,
        *,
        min_kappa: float = 0.82,
        min_weighted_kappa: float = 0.80,
        min_spearman_rho: float = 0.80,
        max_abs_leniency_bias: float = 0.08,
        max_false_acceptance_rate: float = 0.05,
        max_false_rejection_rate: float = 0.15,
        max_ece: float = 0.15,
        max_order_bias_rate: float = 0.05,
    ) -> None:
        self.min_kappa = min_kappa
        self.min_weighted_kappa = min_weighted_kappa
        self.min_spearman_rho = min_spearman_rho
        self.max_abs_leniency_bias = max_abs_leniency_bias
        self.max_false_acceptance_rate = max_false_acceptance_rate
        self.max_false_rejection_rate = max_false_rejection_rate
        self.max_ece = max_ece
        self.max_order_bias_rate = max_order_bias_rate

    @staticmethod
    def _verify_single_verdict_binding(
        human_rec: ExternalHumanLabelRecord,
        judge_verdict: Mapping[str, Any] | None,
    ) -> list[str]:
        if judge_verdict is None:
            return [f"MISSING_JUDGE_RECEIPT:{human_rec.case_id}"]
        codes = verify_ide_judge_receipt_provenance(judge_verdict)
        obs_sha = str(judge_verdict.get("artifact_sha256") or "").strip().lower()
        if not obs_sha or obs_sha != human_rec.artifact_sha256:
            codes.append(f"ARTIFACT_SHA256_MISMATCH:{human_rec.case_id}")
        return codes

    def _collect_threshold_drift_codes(
        self,
        *,
        human_verdicts: Sequence[str],
        judge_verdicts: Sequence[str],
        kappa: float,
        w_kappa: float,
        rho: float,
        signed_bias: float,
        far: float,
        frr: float,
        ece: float,
        order_bias: float,
    ) -> list[str]:
        codes: list[str] = []
        if len(set(human_verdicts)) < 2 or len(set(judge_verdicts)) < 2:
            codes.append("SINGLE_CLASS_COLLAPSE")
        if kappa < self.min_kappa:
            codes.append(f"COHENS_KAPPA_BELOW_FLOOR:{kappa:.4f}<{self.min_kappa:.2f}")
        if w_kappa < self.min_weighted_kappa:
            codes.append(f"WEIGHTED_KAPPA_BELOW_FLOOR:{w_kappa:.4f}<{self.min_weighted_kappa:.2f}")
        if rho < self.min_spearman_rho:
            codes.append(f"SPEARMAN_RHO_BELOW_FLOOR:{rho:.4f}<{self.min_spearman_rho:.2f}")
        if signed_bias > self.max_abs_leniency_bias:
            codes.append(f"LENIENCY_INFLATION_DRIFT:{signed_bias:+.4f}>{self.max_abs_leniency_bias:.2f}")
        elif signed_bias < -self.max_abs_leniency_bias:
            codes.append(f"SEVERITY_COLLAPSE_DRIFT:{signed_bias:+.4f}<-{self.max_abs_leniency_bias:.2f}")
        if far > self.max_false_acceptance_rate:
            codes.append(f"FALSE_ACCEPTANCE_RATE_EXCEEDED:{far:.4f}>{self.max_false_acceptance_rate:.2f}")
        if frr > self.max_false_rejection_rate:
            codes.append(f"FALSE_REJECTION_RATE_EXCEEDED:{frr:.4f}>{self.max_false_rejection_rate:.2f}")
        if ece > self.max_ece:
            codes.append(f"ECE_EXCEEDED:{ece:.4f}>{self.max_ece:.2f}")
        if order_bias > self.max_order_bias_rate:
            codes.append(f"POSITION_SWAP_ORDER_BIAS:{order_bias:.4f}>{self.max_order_bias_rate:.2f}")
        return codes

    def _pair_cohort_records(
        self,
        human_records: Sequence[ExternalHumanLabelRecord],
        judge_verdicts_by_case: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[float], list[float], list[str], list[str], list[str], list[str]]:
        prov_codes: list[str] = []
        h_scores: list[float] = []
        j_scores: list[float] = []
        h_verdicts: list[str] = []
        j_verdicts: list[str] = []
        families: list[str] = []
        for rec in human_records:
            verdict_obj = judge_verdicts_by_case.get(rec.case_id)
            item_codes = self._verify_single_verdict_binding(rec, verdict_obj)
            if item_codes or verdict_obj is None:
                prov_codes.extend(item_codes)
                continue
            j_norm, j_verd, fam = normalize_ide_judge_score(verdict_obj)
            h_scores.append(rec.normalized_human_score())
            j_scores.append(j_norm)
            h_verdicts.append(rec.human_verdict)
            j_verdicts.append(j_verd)
            families.append(fam)
        if len(set(families)) > 1:
            prov_codes.append("MIXED_IDE_MODEL_FAMILIES_IN_COHORT")
        return h_scores, j_scores, h_verdicts, j_verdicts, families, prov_codes

    @staticmethod
    def _failure_report(
        judge_surface: str,
        dom_family: str,
        partition: str,
        rubric_sha: str,
        evaluated_cases: int,
        codes: Sequence[str],
        now_utc: str,
    ) -> ExternalRubricDriftReport:
        return _build_sealed_report(
            judge_surface=judge_surface,
            ide_model_family=dom_family,
            partition=partition,
            external_rubric_sha256=rubric_sha,
            evaluated_cases=evaluated_cases,
            cohens_kappa=0.0,
            weighted_quadratic_kappa=0.0,
            spearman_rho=0.0,
            signed_leniency_bias=0.0,
            false_acceptance_rate=1.0,
            false_rejection_rate=1.0,
            expected_calibration_error=1.0,
            order_bias_rate=0.0,
            passed=False,
            drift_detected=True,
            drift_codes=tuple(dict.fromkeys(codes)),
            evaluated_at_utc=now_utc,
        )

    def _compute_order_bias(
        self,
        swap_pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]] | None,
        pairwise_judge_fn: Callable[[dict[str, Any], dict[str, Any]], tuple[str, float]] | None,
    ) -> float:
        if not swap_pairs or pairwise_judge_fn is None:
            return 0.0
        debiaser = PositionSwapDebiaser(max_order_bias_rate=self.max_order_bias_rate)
        results = [
            debiaser.evaluate_pair(pair_id=f"pair_{idx}", candidate_a=a, candidate_b=b, judge_fn=pairwise_judge_fn)
            for idx, (a, b) in enumerate(swap_pairs)
        ]
        _, summary = debiaser.evaluate_batch_gate(results)
        return float(summary.get("order_bias_rate", 0.0))

    def evaluate(
        self,
        human_records: Sequence[ExternalHumanLabelRecord],
        judge_verdicts_by_case: Mapping[str, Mapping[str, Any]],
        *,
        judge_surface: str = "resume_engine",
        partition: str = "final_holdout",
        swap_pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]] | None = None,
        pairwise_judge_fn: Callable[[dict[str, Any], dict[str, Any]], tuple[str, float]] | None = None,
    ) -> ExternalRubricDriftReport:
        """Evaluate IDE judge drift fail-closed against human external-rubric records."""
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not human_records:
            return self._failure_report(
                judge_surface, "unknown", partition, "", 0, ("EMPTY_DRIFT_COHORT",), now_utc
            )
        h_scores, j_scores, h_verdicts, j_verdicts, families, prov_codes = self._pair_cohort_records(
            human_records, judge_verdicts_by_case
        )
        rubric_sha = human_records[0].external_rubric_sha256
        dom_family = families[0] if families else "unknown"
        if prov_codes or not h_scores:
            return self._failure_report(
                judge_surface,
                dom_family,
                partition,
                rubric_sha,
                len(h_scores),
                prov_codes or ["NO_VALID_PAIRED_VERDICTS"],
                now_utc,
            )
        h_bins = [_quantize_unit_to_likert(x) for x in h_scores]
        j_bins = [_quantize_unit_to_likert(x) for x in j_scores]
        kappa = round(
            compute_cohens_kappa(
                [1 if v == "PASS" else 0 for v in h_verdicts],
                [1 if v == "PASS" else 0 for v in j_verdicts],
            ),
            4,
        )
        w_kappa = compute_quadratic_weighted_kappa(h_bins, j_bins)
        rho = compute_spearman_rho(h_scores, j_scores)
        signed_bias = round(sum(j - h for j, h in zip(j_scores, h_scores)) / len(h_scores), 4)
        cm = compute_tpr_tnr_balanced_accuracy(h_verdicts, j_verdicts)
        far, frr = cm["fpr"], cm["fnr"]
        q_obs = sum(1 for v in j_verdicts if v == "PASS") / len(j_verdicts)
        rg = compute_rogan_gladen_prevalence(
            q_obs, cm["tpr"], cm["tnr"], human_verdicts=h_verdicts, judge_verdicts=j_verdicts
        )
        ppi = compute_ppi_calibrated_pass_rate(h_verdicts, j_verdicts)
        tag_recall = compute_failure_tag_detection_recall(human_records, judge_verdicts_by_case)
        _, ece_raw = compute_brier_and_ece([1 if v == "PASS" else 0 for v in h_verdicts], j_scores)
        ece = round(ece_raw, 4)
        order_bias = self._compute_order_bias(swap_pairs, pairwise_judge_fn)
        drift_codes = self._collect_threshold_drift_codes(
            human_verdicts=h_verdicts,
            judge_verdicts=j_verdicts,
            kappa=kappa,
            w_kappa=w_kappa,
            rho=rho,
            signed_bias=signed_bias,
            far=far,
            frr=frr,
            ece=ece,
            order_bias=order_bias,
        )
        drift_detected = len(drift_codes) > 0
        return _build_sealed_report(
            judge_surface=judge_surface,
            ide_model_family=dom_family,
            partition=partition,
            external_rubric_sha256=rubric_sha,
            evaluated_cases=len(h_scores),
            cohens_kappa=kappa,
            weighted_quadratic_kappa=w_kappa,
            spearman_rho=rho,
            signed_leniency_bias=signed_bias,
            false_acceptance_rate=far,
            false_rejection_rate=frr,
            expected_calibration_error=ece,
            order_bias_rate=order_bias,
            passed=not drift_detected,
            drift_detected=drift_detected,
            drift_codes=tuple(drift_codes),
            evaluated_at_utc=now_utc,
            tpr=cm["tpr"],
            tnr=cm["tnr"],
            balanced_accuracy=cm["balanced_accuracy"],
            rogan_gladen_pass_rate=rg["corrected_pass_rate"],
            rogan_gladen_ci_95=(rg["ci_95"][0], rg["ci_95"][1]),
            ppi_pass_rate=ppi["ppi_pass_rate"],
            cohort_power_tier=classify_cohort_power(len(h_scores)),
            failure_tag_detection_recall=tag_recall,
        )


def save_drift_receipt(report: ExternalRubricDriftReport, output_path: Path) -> Path:
    """Atomically write a sealed `ExternalRubricDriftReport` JSON receipt."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out


def verify_drift_receipt_digest(receipt_payload: Mapping[str, Any]) -> bool:
    """Verify tamper-evident `receipt_digest` on a persisted drift receipt."""
    observed = str(receipt_payload.get("receipt_digest") or "").strip().lower()
    if len(observed) != 64:
        return False
    body = {k: v for k, v in receipt_payload.items() if k != "receipt_digest"}
    expected = compute_payload_sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    )
    return observed == expected


__all__ = [
    "ExternalRubricDriftReport",
    "IDEJudgeDriftEvaluator",
    "compute_quadratic_weighted_kappa",
    "compute_spearman_rho",
    "normalize_ide_judge_score",
    "normalize_judge_family",
    "save_drift_receipt",
    "verify_drift_receipt_digest",
    "verify_ide_judge_receipt_provenance",
]
