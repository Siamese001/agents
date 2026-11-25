"""Two-axis IDE LLM-as-a-Judge drift monitor (Human Alignment + Temporal Baseline Stability) & fast receipt gate."""
from __future__ import annotations

import datetime
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from apps_eval.graders.judge.calibration import compute_brier_and_ece, compute_cohens_kappa
from apps_eval.graders.judge.frontier_calibration_stats import (
    classify_cohort_power,
    compute_ppi_calibrated_pass_rate,
    compute_rogan_gladen_prevalence,
    compute_tpr_tnr_balanced_accuracy,
)
from apps_eval.graders.judge.gold_corpus import canonical_sha256, load_external_stakeholder_rubric
from apps_eval.graders.judge.ide_judge_drift_evaluator import compute_quadratic_weighted_kappa

IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION = "apps_eval.ide_judge_drift_receipt.v1"

# Axis 1: Human Validity vs External Stakeholder Rubric (binomial-calibrated on N=24/48)
MIN_PER_ENGINE_KAPPA = 0.75
MIN_POOLED_KAPPA = 0.80
MIN_SPEARMAN_RHO = 0.75
MAX_HARD_FAIL_FALSE_PASSES = 0

# Axis 2: Temporal Stability vs Prior Sealed Baseline on Identical Frozen Inputs
MAX_VERDICT_FLIP_RATE = 2.0 / 24.0 + 1e-6  # <= 8.33% (at most 2/24 flips)
MAX_MEAN_SCORE_SHIFT = 0.25  # on 1-5 stakeholder scale

# Fast Promotion Receipt TTL
MAX_DRIFT_RECEIPT_AGE_DAYS = 30


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


def compute_spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Compute Spearman rank correlation in [-1.0, 1.0] with tie handling."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    mx = sum(rx) / float(len(rx))
    my = sum(ry) / float(len(ry))
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx <= 1e-12 or vy <= 1e-12:
        return 0.0
    return round(max(-1.0, min(1.0, cov / math.sqrt(vx * vy))), 4)


def _slug_base(model_slug: str) -> str:
    s = str(model_slug or "").strip()
    for suf in ("-low", "-medium", "-high", "-xhigh", "-max"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def extract_active_ide_judge_pins(repo_root: Path | str) -> dict[str, list[str]]:
    """Extract all active primary and quota-backup IDE judge model slugs from SSOT provider profiles."""
    root = Path(repo_root).resolve()
    pins: dict[str, list[str]] = {"resume_engine": [], "outreach_engine": []}

    def _add(engine: str, raw: Any) -> None:
        if isinstance(raw, str) and raw.strip():
            if raw.strip() not in pins[engine]:
                pins[engine].append(raw.strip())
        elif isinstance(raw, list):
            for x in raw:
                _add(engine, x)
        elif isinstance(raw, dict):
            for v in raw.values():
                _add(engine, v)

    root_cfg = root / "config" / "provider_profiles.yaml"
    if root_cfg.is_file():
        doc = yaml.safe_load(root_cfg.read_text(encoding="utf-8")) or {}
        jm = doc.get("judge_models") or {}
        for tier in ("enhanced", "standard"):
            _add("resume_engine", (jm.get(tier) or {}).get("gemini_pro"))
        ide_j = doc.get("ide_cli_judging") or {}
        _add("resume_engine", ide_j.get("second_judge_by_writer_maker"))
        _add("resume_engine", ide_j.get("quota_backup_first_judge_by_tier"))
        _add("resume_engine", ide_j.get("quota_backup_second_judge_by_writer_maker"))

    lic_cfg = root / "outreach_engine" / "config" / "provider_profiles.yaml"
    if lic_cfg.is_file():
        doc = yaml.safe_load(lic_cfg.read_text(encoding="utf-8")) or {}
        ide_j = doc.get("ide_cli_judging") or {}
        _add("outreach_engine", ide_j.get("primary_judge_model"))
        _add("outreach_engine", ide_j.get("second_judge_by_writer_maker"))
        _add("outreach_engine", ide_j.get("quota_backup_primary_judge"))
        _add("outreach_engine", ide_j.get("quota_backup_second_judge_by_writer_maker"))
        _add("outreach_engine", ide_j.get("rubric_panel_judge_model"))
        _add("outreach_engine", ide_j.get("rubric_panel_quota_backups"))

    return pins


def extract_active_ide_judge_bases(repo_root: Path | str) -> dict[str, list[str]]:
    """Return deduplicated active IDE judge model bases per engine (primary + quota backups)."""
    by_engine = extract_active_ide_judge_pins(repo_root)
    return {
        eng: sorted({_slug_base(m) for m in models if m})
        for eng, models in by_engine.items()
    }


@dataclass(frozen=True)
class ModelDriftEvaluation:
    """Two-axis calibration and temporal drift verdict for one `(engine, model_slug)` pair."""

    engine: str
    model_slug: str
    model_base: str
    sample_size: int
    cohens_kappa: float
    spearman_rho: float
    brier_score: float
    ece: float
    hard_fail_count: int
    hard_fail_false_passes: int
    verdict_flip_rate: float | None
    mean_abs_score_shift: float | None
    mean_signed_score_shift: float | None
    passed: bool
    root_cause_codes: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    weighted_quadratic_kappa: float = 0.0
    tpr: float = 0.0
    tnr: float = 0.0
    balanced_accuracy: float = 0.0
    rogan_gladen_pass_rate: float = 0.0
    rogan_gladen_ci_95: tuple[float, float] = (0.0, 0.0)
    ppi_pass_rate: float = 0.0
    cohort_power_tier: str = "UNDERPOWERED_PILOT"

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "model_slug": self.model_slug,
            "model_base": self.model_base,
            "sample_size": self.sample_size,
            "cohens_kappa": round(self.cohens_kappa, 4),
            "weighted_quadratic_kappa": round(self.weighted_quadratic_kappa, 4),
            "spearman_rho": round(self.spearman_rho, 4),
            "brier_score": round(self.brier_score, 4),
            "ece": round(self.ece, 4),
            "tpr": round(self.tpr, 4),
            "tnr": round(self.tnr, 4),
            "balanced_accuracy": round(self.balanced_accuracy, 4),
            "rogan_gladen_pass_rate": round(self.rogan_gladen_pass_rate, 4),
            "rogan_gladen_ci_95": [round(self.rogan_gladen_ci_95[0], 4), round(self.rogan_gladen_ci_95[1], 4)],
            "ppi_pass_rate": round(self.ppi_pass_rate, 4),
            "cohort_power_tier": self.cohort_power_tier,
            "hard_fail_count": self.hard_fail_count,
            "hard_fail_false_passes": self.hard_fail_false_passes,
            "verdict_flip_rate": round(self.verdict_flip_rate, 4) if self.verdict_flip_rate is not None else None,
            "mean_abs_score_shift": round(self.mean_abs_score_shift, 4) if self.mean_abs_score_shift is not None else None,
            "mean_signed_score_shift": round(self.mean_signed_score_shift, 4)
            if self.mean_signed_score_shift is not None
            else None,
            "passed": self.passed,
            "root_cause_codes": list(self.root_cause_codes),
            "violations": list(self.violations),
        }


def evaluate_model_drift(
    *,
    engine: str,
    model_slug: str,
    human_gold_items: Mapping[str, Mapping[str, Any]],
    judge_predictions: Mapping[str, Mapping[str, Any]],
    baseline_predictions: Mapping[str, Mapping[str, Any]] | None = None,
    min_kappa: float = MIN_PER_ENGINE_KAPPA,
    min_spearman: float = MIN_SPEARMAN_RHO,
    max_hard_fail_false_passes: int = MAX_HARD_FAIL_FALSE_PASSES,
    max_flip_rate: float = MAX_VERDICT_FLIP_RATE,
    max_mean_shift: float = MAX_MEAN_SCORE_SHIFT,
) -> ModelDriftEvaluation:
    """Evaluate a single IDE judge model against human gold truth (Axis 1) and prior sealed baseline (Axis 2)."""
    common_ids = sorted(set(human_gold_items.keys()) & set(judge_predictions.keys()))
    if not common_ids:
        return ModelDriftEvaluation(
            engine=engine,
            model_slug=model_slug,
            model_base=_slug_base(model_slug),
            sample_size=0,
            cohens_kappa=0.0,
            spearman_rho=0.0,
            brier_score=1.0,
            ece=1.0,
            hard_fail_count=0,
            hard_fail_false_passes=0,
            verdict_flip_rate=None,
            mean_abs_score_shift=None,
            mean_signed_score_shift=None,
            passed=False,
            root_cause_codes=("EMPTY_ALIGNMENT_SET",),
            violations=(f"{engine}::{model_slug}: zero overlapping items between human gold and judge predictions.",),
        )

    y_true: list[int] = []
    y_pred: list[int] = []
    h_scores: list[float] = []
    j_scores: list[float] = []
    j_probs: list[float] = []
    hard_fail_count = 0
    hard_fail_fp = 0

    for cid in common_ids:
        h = human_gold_items[cid]
        j = judge_predictions[cid]
        h_pass = bool(h["human_pass"])
        j_pass = bool(j["judge_pass"])
        h_sc = (
            float(h["human_score_1_5"])
            if "human_score_1_5" in h
            else (1.0 + 4.0 * float(h.get("normalized_human_score", 1.0 if h_pass else 0.0)))
        )
        if "judge_score_1_5" in j:
            j_sc = float(j["judge_score_1_5"])
            j_unit = max(0.0, min(1.0, (j_sc - 1.0) / 4.0))
        else:
            j_unit = max(0.0, min(1.0, float(j.get("normalized_unit_score", j.get("judge_unit_score", 1.0 if j_pass else 0.0)))))
            j_sc = 1.0 + 4.0 * j_unit
        y_true.append(1 if h_pass else 0)
        y_pred.append(1 if j_pass else 0)
        h_scores.append(h_sc)
        j_scores.append(j_sc)
        j_probs.append(j_unit)
        if bool(h.get("hard_fail_any", False)):
            hard_fail_count += 1
            if j_pass:
                hard_fail_fp += 1

    kappa = round(compute_cohens_kappa(y_true, y_pred), 4)
    h_bins = [max(1, min(5, int(round(s)))) for s in h_scores]
    j_bins = [max(1, min(5, int(round(s)))) for s in j_scores]
    w_kappa = compute_quadratic_weighted_kappa(h_bins, j_bins)
    h_v_strs = ["PASS" if y == 1 else "FAIL" for y in y_true]
    j_v_strs = ["PASS" if y == 1 else "FAIL" for y in y_pred]
    cm = compute_tpr_tnr_balanced_accuracy(h_v_strs, j_v_strs)
    q_obs = sum(y_pred) / float(len(y_pred))
    rg = compute_rogan_gladen_prevalence(
        q_obs, cm["tpr"], cm["tnr"], human_verdicts=h_v_strs, judge_verdicts=j_v_strs
    )
    ppi = compute_ppi_calibrated_pass_rate(h_v_strs, j_v_strs)
    rho = compute_spearman_rho(h_scores, j_scores)
    brier, ece = compute_brier_and_ece(y_true, j_probs)

    flip_rate: float | None = None
    mean_abs_shift: float | None = None
    mean_signed_shift: float | None = None
    if baseline_predictions:
        base_ids = sorted(set(common_ids) & set(baseline_predictions.keys()))
        if base_ids:
            flips = 0
            abs_diffs: list[float] = []
            signed_diffs: list[float] = []
            for cid in base_ids:
                cur_p = bool(judge_predictions[cid]["judge_pass"])
                old_p = bool(baseline_predictions[cid]["judge_pass"])
                if cur_p != old_p:
                    flips += 1
                cur_sc = (
                    float(judge_predictions[cid]["judge_score_1_5"])
                    if "judge_score_1_5" in judge_predictions[cid]
                    else (1.0 + 4.0 * float(judge_predictions[cid].get("normalized_unit_score", 0.0)))
                )
                old_sc = (
                    float(baseline_predictions[cid]["judge_score_1_5"])
                    if "judge_score_1_5" in baseline_predictions[cid]
                    else (1.0 + 4.0 * float(baseline_predictions[cid].get("normalized_unit_score", 0.0)))
                )
                diff = cur_sc - old_sc
                abs_diffs.append(abs(diff))
                signed_diffs.append(diff)
            flip_rate = round(flips / float(len(base_ids)), 4)
            mean_abs_shift = round(sum(abs_diffs) / float(len(abs_diffs)), 4)
            mean_signed_shift = round(sum(signed_diffs) / float(len(signed_diffs)), 4)

    violations: list[str] = []
    causes: list[str] = []
    if hard_fail_fp > max_hard_fail_false_passes:
        causes.append("HARD_FAIL_FALSE_PASS")
        violations.append(
            f"{engine}::{model_slug}: {hard_fail_fp}/{hard_fail_count} human hard-fail defects received judge PASS."
        )
    if kappa < min_kappa:
        causes.append("RUBRIC_CONSTRUCT_GAP")
        violations.append(f"{engine}::{model_slug}: Cohen's kappa {kappa:.4f} < floor {min_kappa:.2f}.")
    if rho < min_spearman:
        causes.append("RANK_ORDER_DRIFT")
        violations.append(f"{engine}::{model_slug}: Spearman rho {rho:.4f} < floor {min_spearman:.2f}.")
    if flip_rate is not None and flip_rate > max_flip_rate:
        causes.append("MODEL_SLUG_SHIFT")
        violations.append(f"{engine}::{model_slug}: temporal verdict flip rate {flip_rate:.4f} > ceiling {max_flip_rate:.4f}.")
    if mean_abs_shift is not None and mean_abs_shift > max_mean_shift:
        causes.append("MODEL_SLUG_SHIFT")
        violations.append(
            f"{engine}::{model_slug}: temporal mean abs score shift {mean_abs_shift:.4f} > ceiling {max_mean_shift:.2f}."
        )

    return ModelDriftEvaluation(
        engine=engine,
        model_slug=model_slug,
        model_base=_slug_base(model_slug),
        sample_size=len(common_ids),
        cohens_kappa=kappa,
        spearman_rho=rho,
        brier_score=round(brier, 4),
        ece=round(ece, 4),
        hard_fail_count=hard_fail_count,
        hard_fail_false_passes=hard_fail_fp,
        verdict_flip_rate=flip_rate,
        mean_abs_score_shift=mean_abs_shift,
        mean_signed_score_shift=mean_signed_shift,
        passed=len(violations) == 0,
        root_cause_codes=tuple(sorted(set(causes))),
        violations=tuple(violations),
        weighted_quadratic_kappa=w_kappa,
        tpr=cm["tpr"],
        tnr=cm["tnr"],
        balanced_accuracy=cm["balanced_accuracy"],
        rogan_gladen_pass_rate=rg["corrected_pass_rate"],
        rogan_gladen_ci_95=(rg["ci_95"][0], rg["ci_95"][1]),
        ppi_pass_rate=ppi["ppi_pass_rate"],
        cohort_power_tier=classify_cohort_power(len(common_ids)),
    )


def build_drift_flywheel_escalation_payload(
    *,
    receipt: Mapping[str, Any],
    violations: Sequence[str],
) -> dict[str, Any]:
    """Build fail-closed Tier B/C flywheel escalation payload without ever auto-lowering judge floors."""
    causes: set[str] = set()
    for row in receipt.get("per_model_results") or []:
        if isinstance(row, Mapping):
            for c in row.get("root_cause_codes") or []:
                causes.add(str(c))
    finding_digest = canonical_sha256({"violations": list(violations), "causes": sorted(causes)})
    return {
        "schema_version": "apps_eval.judge_drift_escalation.v1",
        "remediation_tier": "TIER_B_OR_C_ATOMIC_HITL",
        "auto_apply_permitted": False,
        "never_auto_lower_judge_floors": True,
        "protected_floors": {"resume_engine_x1d": 0.80, "outreach_engine_x1d": 0.85},
        "root_cause_codes": sorted(causes),
        "finding_digest": finding_digest,
        "violations": list(violations),
    }


def evaluate_full_drift_suite(
    *,
    human_gold_by_engine: Mapping[str, Mapping[str, Mapping[str, Any]]],
    judge_predictions_by_engine_model: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Any]]]],
    human_chain_hashes: Mapping[str, str],
    repo_root: Path | str,
    baseline_predictions_by_engine_model: Mapping[str, Mapping[str, Mapping[str, Mapping[str, Any]]]] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Compute consolidated two-axis drift receipt across both engines and all evaluated IDE judge pins."""
    root = Path(repo_root).resolve()
    now_iso = generated_at_utc or datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    rubric_hashes = {
        eng: load_external_stakeholder_rubric(eng, repo_root=root)[1]
        for eng in ("resume_engine", "outreach_engine")
    }
    active_bases = extract_active_ide_judge_bases(root)
    per_model: list[dict[str, Any]] = []
    violations: list[str] = []

    # Track pooled primary predictions across both engines (48 items)
    pooled_true: list[int] = []
    pooled_pred: list[int] = []

    for eng in ("resume_engine", "outreach_engine"):
        gold_map = human_gold_by_engine.get(eng) or {}
        models_map = judge_predictions_by_engine_model.get(eng) or {}
        base_models_map = (baseline_predictions_by_engine_model or {}).get(eng) or {}
        evaluated_bases: set[str] = set()
        first_model_pooled = False

        for model_slug, preds in sorted(models_map.items()):
            ev = evaluate_model_drift(
                engine=eng,
                model_slug=model_slug,
                human_gold_items=gold_map,
                judge_predictions=preds,
                baseline_predictions=base_models_map.get(model_slug),
            )
            per_model.append(ev.to_dict())
            evaluated_bases.add(ev.model_base)
            violations.extend(ev.violations)
            if not first_model_pooled:
                first_model_pooled = True
                for cid in sorted(set(gold_map.keys()) & set(preds.keys())):
                    pooled_true.append(1 if bool(gold_map[cid]["human_pass"]) else 0)
                    pooled_pred.append(1 if bool(preds[cid]["judge_pass"]) else 0)

        missing_bases = sorted(set(active_bases.get(eng, [])) - evaluated_bases)
        if missing_bases:
            violations.append(
                f"{eng}: active IDE judge model bases missing calibration/drift proof: {missing_bases}"
            )

    pooled_kappa = round(compute_cohens_kappa(pooled_true, pooled_pred), 4) if pooled_true else 0.0
    if pooled_true and pooled_kappa < MIN_POOLED_KAPPA:
        violations.append(
            f"pooled_48_item_kappa {pooled_kappa:.4f} < floor {MIN_POOLED_KAPPA:.2f} (n={len(pooled_true)})."
        )

    pooled_cm = (
        compute_tpr_tnr_balanced_accuracy(
            ["PASS" if y == 1 else "FAIL" for y in pooled_true],
            ["PASS" if y == 1 else "FAIL" for y in pooled_pred],
        )
        if pooled_true
        else {"fpr": 0.0}
    )
    v2_rub_path = root / "config" / "governance" / "external_judge_rubric_v2.json"
    v2_raw_sha = ""
    if v2_rub_path.is_file():
        import hashlib

        v2_raw_sha = hashlib.sha256(v2_rub_path.read_bytes()).hexdigest()

    passed = len(violations) == 0
    receipt: dict[str, Any] = {
        "schema_version": IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION,
        "generated_at_utc": now_iso,
        "status": "PASS" if passed else "DRIFT_BLOCKED",
        "passed": passed,
        "drift_detected": not passed,
        "cohens_kappa": pooled_kappa,
        "false_acceptance_rate": pooled_cm["fpr"],
        "external_rubric_sha256": v2_raw_sha,
        "rubric_sha256": rubric_hashes,
        "human_chain_sha256": dict(human_chain_hashes),
        "active_ide_judge_bases": active_bases,
        "thresholds": {
            "min_per_engine_kappa": MIN_PER_ENGINE_KAPPA,
            "min_pooled_kappa": MIN_POOLED_KAPPA,
            "min_spearman_rho": MIN_SPEARMAN_RHO,
            "max_hard_fail_false_passes": MAX_HARD_FAIL_FALSE_PASSES,
            "max_verdict_flip_rate": round(MAX_VERDICT_FLIP_RATE, 4),
            "max_mean_score_shift": MAX_MEAN_SCORE_SHIFT,
            "max_receipt_age_days": MAX_DRIFT_RECEIPT_AGE_DAYS,
        },
        "pooled_summary": {
            "sample_size": len(pooled_true),
            "cohens_kappa": pooled_kappa,
        },
        "per_model_results": per_model,
        "violations": violations,
    }
    if not passed:
        receipt["flywheel_escalation"] = build_drift_flywheel_escalation_payload(
            receipt=receipt, violations=violations
        )
    receipt["receipt_sha256"] = canonical_sha256(
        {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    )
    return receipt


def verify_ide_judge_drift_receipt(
    receipt_path: Path | str,
    *,
    repo_root: Path | str,
    now_utc: datetime.datetime | None = None,
    max_age_days: int = MAX_DRIFT_RECEIPT_AGE_DAYS,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Fast (<100ms) offline promotion gate checking drift receipt freshness, pin lockstep, rubric hashes, and PASS status."""
    fp = Path(receipt_path)
    root = Path(repo_root).resolve()
    violations: list[str] = []
    if not fp.is_file():
        return False, [f"DRIFT_RECEIPT_MISSING: {fp}"], {"status": "BLOCKED"}

    try:
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"DRIFT_RECEIPT_MALFORMED: {exc}"], {"status": "BLOCKED"}

    if doc.get("schema_version") != IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION:
        violations.append(f"Unexpected drift receipt schema_version {doc.get('schema_version')!r}")

    expected_sha = canonical_sha256({k: v for k, v in doc.items() if k != "receipt_sha256"})
    if str(doc.get("receipt_sha256") or "") != expected_sha:
        violations.append("DRIFT_RECEIPT_TAMPERED: receipt_sha256 mismatch")

    if str(doc.get("status") or "") != "PASS" or not bool(doc.get("passed", False)):
        violations.append(f"DRIFT_BLOCKED: receipt status is {doc.get('status')!r}")

    # Freshness check (<= 30 days)
    gen_raw = str(doc.get("generated_at_utc") or "").strip()
    age_days: float | None = None
    if not gen_raw:
        violations.append("DRIFT_RECEIPT_MISSING_TIMESTAMP")
    else:
        try:
            gen_dt = datetime.datetime.fromisoformat(gen_raw.replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=datetime.timezone.utc)
            ref_now = now_utc or datetime.datetime.now(datetime.timezone.utc)
            age_days = round((ref_now - gen_dt.astimezone(datetime.timezone.utc)).total_seconds() / 86400.0, 3)
            if age_days > float(max_age_days):
                violations.append(
                    f"DRIFT_RECEIPT_STALE: age {age_days:.1f}d exceeds ceiling {max_age_days}d; rerun live drift sweep."
                )
        except ValueError:
            violations.append(f"DRIFT_RECEIPT_INVALID_TIMESTAMP: {gen_raw!r}")

    # External stakeholder rubric hash lockstep
    rec_rubrics = doc.get("rubric_sha256") or {}
    for eng in ("resume_engine", "outreach_engine"):
        _, cur_sha = load_external_stakeholder_rubric(eng, repo_root=root)
        if str(rec_rubrics.get(eng) or "") != cur_sha:
            violations.append(f"DRIFT_RUBRIC_HASH_MISMATCH:{eng}")

    # Active primary + quota-backup IDE judge pin coverage lockstep
    cur_bases = extract_active_ide_judge_bases(root)
    passed_bases_by_engine: dict[str, set[str]] = {"resume_engine": set(), "outreach_engine": set()}
    for row in doc.get("per_model_results") or []:
        if isinstance(row, Mapping) and bool(row.get("passed", False)):
            eng = str(row.get("engine") or "")
            base = str(row.get("model_base") or _slug_base(str(row.get("model_slug") or "")))
            if eng in passed_bases_by_engine and base:
                passed_bases_by_engine[eng].add(base)

    for eng, required in cur_bases.items():
        missing = sorted(set(required) - passed_bases_by_engine.get(eng, set()))
        if missing:
            violations.append(f"DRIFT_UNQUALIFIED_JUDGE_PIN:{eng}:{missing}")

    # Human chain hash presence check
    chain_hashes = doc.get("human_chain_sha256") or {}
    for eng in ("resume_engine", "outreach_engine"):
        h = str(chain_hashes.get(eng) or "").strip()
        if len(h) != 64 or h == ("0" * 64):
            violations.append(f"DRIFT_MISSING_HUMAN_GOLD_CHAIN:{eng}")

    return len(violations) == 0, violations, {
        "status": "PASS" if not violations else "DRIFT_BLOCKED",
        "age_days": age_days,
        "pooled_kappa": (doc.get("pooled_summary") or {}).get("cohens_kappa"),
        "violations": violations,
    }


__all__ = [
    "IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION",
    "MAX_DRIFT_RECEIPT_AGE_DAYS",
    "MAX_HARD_FAIL_FALSE_PASSES",
    "MAX_MEAN_SCORE_SHIFT",
    "MAX_VERDICT_FLIP_RATE",
    "MIN_PER_ENGINE_KAPPA",
    "MIN_POOLED_KAPPA",
    "MIN_SPEARMAN_RHO",
    "ModelDriftEvaluation",
    "build_drift_flywheel_escalation_payload",
    "compute_spearman_rho",
    "evaluate_full_drift_suite",
    "evaluate_model_drift",
    "extract_active_ide_judge_bases",
    "extract_active_ide_judge_pins",
    "verify_ide_judge_drift_receipt",
]
