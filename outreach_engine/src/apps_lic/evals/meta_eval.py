"""G6 Judge Meta-Evaluation and Calibration Harness for outreach_engine (apps_lic)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from apps_lic.evals.repeatability import (
    DEFAULT_HOLDOUT_CORPUS_PATH,
    PLANTED_DEFECT_CLASSES,
    detect_item_defect_classes,
    load_outreach_holdout_corpus,
    score_holdout_item_deterministic,
)

G6_MIN_SPEARMAN_RHO: Final[float] = 0.70
G6_MIN_COHENS_KAPPA: Final[float] = 0.65
G6_MAX_CLEAN_FPR: Final[float] = 0.0
G6_MIN_DEFECT_TPR: Final[float] = 0.90


@dataclass(frozen=True)
class PlantDefectCase:
    """Single holdout evaluation case tracking clean control or planted defect detection."""

    case_id: str
    defect_class: str | None = None
    is_defective: bool = False
    detected: bool = False
    detected_classes: tuple[str, ...] = ()
    gold_human_score: float = 0.0
    gold_pass_label: bool = True
    judge_score: float = 0.0
    judge_passed: bool = True

    @property
    def item_id(self) -> str:
        return self.case_id

    @property
    def planted_defect_class(self) -> str | None:
        return self.defect_class

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "defect_class": self.defect_class,
            "is_defective": self.is_defective,
            "detected": self.detected,
            "detected_classes": list(self.detected_classes),
            "gold_human_score": round(self.gold_human_score, 6),
            "gold_pass_label": self.gold_pass_label,
            "judge_score": round(self.judge_score, 6),
            "judge_passed": self.judge_passed,
        }


@dataclass(frozen=True)
class G6MetaEvalReport:
    """Consolidated G6 meta-evaluation and calibration report across the 80-item holdout corpus."""

    passed: bool
    gate_id: str = "G6"
    corpus_size: int = 0
    clean_item_count: int = 0
    defective_item_count: int = 0
    spearman_rho: float = 0.0
    cohens_kappa: float = 0.0
    fpr: float = 0.0
    tpr: float = 0.0
    per_defect_class_tpr: dict[str, float] = field(default_factory=dict)
    defect_classes_evaluated: tuple[str, ...] = PLANTED_DEFECT_CLASSES
    cases: tuple[PlantDefectCase, ...] = ()
    violations: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.passed

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    @property
    def false_positive_rate(self) -> float:
        return self.fpr

    @property
    def true_positive_rate(self) -> float:
        return self.tpr

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "status": self.status,
            "corpus_size": self.corpus_size,
            "clean_item_count": self.clean_item_count,
            "defective_item_count": self.defective_item_count,
            "spearman_rho": round(self.spearman_rho, 6),
            "cohens_kappa": round(self.cohens_kappa, 6),
            "fpr": round(self.fpr, 6),
            "tpr": round(self.tpr, 6),
            "per_defect_class_tpr": {k: round(v, 6) for k, v in self.per_defect_class_tpr.items()},
            "defect_classes_evaluated": list(self.defect_classes_evaluated),
            "cases": [c.to_dict() for c in self.cases],
            "violations": list(self.violations),
        }


def _average_ranks(values: Sequence[float]) -> list[float]:
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def compute_spearman_rho(x: Sequence[float], y: Sequence[float]) -> float:
    """Compute Spearman rank correlation coefficient rho in [-1.0, 1.0] with tie handling."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    rx = _average_ranks(x)
    ry = _average_ranks(y)
    mean_x = sum(rx) / float(len(rx))
    mean_y = sum(ry) / float(len(ry))
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x <= 1e-12 or var_y <= 1e-12:
        return 0.0
    return round(max(-1.0, min(1.0, cov / math.sqrt(var_x * var_y))), 6)


def compute_cohens_kappa(labels_a: Sequence[bool], labels_b: Sequence[bool]) -> float:
    """Compute Cohen's kappa agreement between binary classifications."""
    n = len(labels_a)
    if n == 0 or len(labels_b) != n:
        return 0.0
    tp = sum(1 for a, b in zip(labels_a, labels_b) if a and b)
    tn = sum(1 for a, b in zip(labels_a, labels_b) if not a and not b)
    fp = sum(1 for a, b in zip(labels_a, labels_b) if not a and b)
    fn = sum(1 for a, b in zip(labels_a, labels_b) if a and not b)

    p_o = (tp + tn) / float(n)
    p_yes = ((tp + fn) / float(n)) * ((tp + fp) / float(n))
    p_no = ((tn + fp) / float(n)) * ((tn + fn) / float(n))
    p_e = p_yes + p_no
    if abs(1.0 - p_e) <= 1e-12:
        return 1.0 if abs(p_o - 1.0) <= 1e-12 else 0.0
    return round((p_o - p_e) / (1.0 - p_e), 6)


def detect_planted_defects(item: Mapping[str, Any]) -> tuple[str, ...]:
    """Detect planted defect classes in a holdout sequence item."""
    return detect_item_defect_classes(item)


def evaluate_g6_meta_calibration(
    corpus: Sequence[Mapping[str, Any]] | Path | str | None = None,
    *,
    min_spearman_rho: float = G6_MIN_SPEARMAN_RHO,
    min_cohens_kappa: float = G6_MIN_COHENS_KAPPA,
    max_fpr: float = G6_MAX_CLEAN_FPR,
    min_tpr: float = G6_MIN_DEFECT_TPR,
    judge_fn: Callable[[Mapping[str, Any]], tuple[float, bool, tuple[str, ...]]] | None = None,
) -> G6MetaEvalReport:
    """Evaluate judge calibration and 8-class defect sensitivity across the 80-item holdout corpus."""
    if corpus is None or isinstance(corpus, (Path, str)):
        items: Sequence[Mapping[str, Any]] = load_outreach_holdout_corpus(corpus)
    else:
        items = list(corpus)

    violations: list[str] = []
    if not items:
        violations.append("Holdout corpus is empty; G6 meta-eval requires >= 1 item.")
        return G6MetaEvalReport(passed=False, violations=tuple(violations))

    cases: list[PlantDefectCase] = []
    gold_scores: list[float] = []
    judge_scores: list[float] = []
    gold_labels: list[bool] = []
    judge_labels: list[bool] = []

    class_totals: dict[str, int] = {cls_name: 0 for cls_name in PLANTED_DEFECT_CLASSES}
    class_hits: dict[str, int] = {cls_name: 0 for cls_name in PLANTED_DEFECT_CLASSES}

    clean_count = 0
    false_positives = 0
    defective_count = 0
    true_positives = 0

    for idx, item in enumerate(items, start=1):
        case_id = str(item.get("item_id") or item.get("holdout_id") or f"lic_holdout_{idx:03d}")
        gold_sc = float(item.get("gold_human_score", 0.0))
        gold_lbl = bool(item.get("gold_pass_label", False))
        planted_cls_raw = item.get("planted_defect_class")
        planted_cls = str(planted_cls_raw) if planted_cls_raw else None

        if judge_fn is not None:
            j_score, j_pass, det_classes = judge_fn(item)
        else:
            j_score, j_pass, det_classes = score_holdout_item_deterministic(
                item, run_index=0, jitter_scale=0.0
            )

        is_defective = (planted_cls is not None) or (not gold_lbl)
        if is_defective:
            defective_count += 1
            detected = (not j_pass) and (
                len(det_classes) > 0 and (planted_cls is None or planted_cls in det_classes)
            )
            if detected:
                true_positives += 1
            if planted_cls in class_totals:
                class_totals[planted_cls] += 1
                if detected:
                    class_hits[planted_cls] += 1
        else:
            clean_count += 1
            fp_triggered = (not j_pass) or (len(det_classes) > 0)
            detected = fp_triggered
            if fp_triggered:
                false_positives += 1

        gold_scores.append(gold_sc)
        judge_scores.append(j_score)
        gold_labels.append(gold_lbl)
        judge_labels.append(j_pass)

        cases.append(
            PlantDefectCase(
                case_id=case_id,
                defect_class=planted_cls,
                is_defective=is_defective,
                detected=detected,
                detected_classes=tuple(det_classes),
                gold_human_score=gold_sc,
                gold_pass_label=gold_lbl,
                judge_score=j_score,
                judge_passed=j_pass,
            )
        )

    rho = compute_spearman_rho(gold_scores, judge_scores)
    kappa = compute_cohens_kappa(gold_labels, judge_labels)
    fpr = (false_positives / float(clean_count)) if clean_count > 0 else 0.0
    tpr = (true_positives / float(defective_count)) if defective_count > 0 else 0.0

    per_class_tpr: dict[str, float] = {}
    for cls_name in PLANTED_DEFECT_CLASSES:
        tot = class_totals[cls_name]
        if tot == 0:
            per_class_tpr[cls_name] = 0.0
            violations.append(f"Missing planted defect class '{cls_name}' in holdout evaluation.")
        else:
            c_tpr = class_hits[cls_name] / float(tot)
            per_class_tpr[cls_name] = round(c_tpr, 6)
            if c_tpr < min_tpr:
                violations.append(
                    f"Planted defect class '{cls_name}' TPR {c_tpr:.3f} below floor {min_tpr:.3f}."
                )

    if rho < min_spearman_rho:
        violations.append(
            f"Spearman rank correlation {rho:.4f} below minimum {min_spearman_rho:.4f}."
        )
    if kappa < min_cohens_kappa:
        violations.append(f"Cohen's kappa {kappa:.4f} below minimum {min_cohens_kappa:.4f}.")
    if fpr > max_fpr:
        violations.append(f"Clean-item false positive rate {fpr:.4f} exceeds ceiling {max_fpr:.4f}.")
    if tpr < min_tpr:
        violations.append(f"Defective-item true positive rate {tpr:.4f} below floor {min_tpr:.4f}.")

    passed = (
        len(violations) == 0
        and rho >= min_spearman_rho
        and kappa >= min_cohens_kappa
        and fpr <= max_fpr
        and tpr >= min_tpr
    )
    return G6MetaEvalReport(
        passed=passed,
        corpus_size=len(cases),
        clean_item_count=clean_count,
        defective_item_count=defective_count,
        spearman_rho=rho,
        cohens_kappa=kappa,
        fpr=round(fpr, 6),
        tpr=round(tpr, 6),
        per_defect_class_tpr=per_class_tpr,
        defect_classes_evaluated=PLANTED_DEFECT_CLASSES,
        cases=tuple(cases),
        violations=tuple(violations),
    )


__all__ = [
    " DEFAULT_HOLDOUT_CORPUS_PATH".strip(),
    "G6MetaEvalReport",
    "G6_MAX_CLEAN_FPR",
    "G6_MIN_COHENS_KAPPA",
    "G6_MIN_DEFECT_TPR",
    "G6_MIN_SPEARMAN_RHO",
    "PLANTED_DEFECT_CLASSES",
    "PlantDefectCase",
    "compute_cohens_kappa",
    "compute_spearman_rho",
    "detect_planted_defects",
    "evaluate_g6_meta_calibration",
]
