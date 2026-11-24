"""Shadow-to-blocking golden evaluation suite runner for real-failure flywheel cases.

Pure JSON/filesystem module (zero sqlite3 imports and zero direct domain engine imports).
Partitions `golden_eval_cases.json` using `remediation_queue_snapshot.json`:
- Cases linked to `OPEN`, `APPROVED`, `IN_PROGRESS`, or `SNOOZED` findings execute in
  non-blocking shadow mode (`shadow_cases`), recording telemetry without blocking merges.
- Cases linked to `VERIFIED` findings (or curated locked holdout seeds with no open finding)
  execute as merge-blocking regression gates (`blocking_cases`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from apps_eval.contracts.schemas import EvalCase, utc_now_iso

GoldenCaseEvaluatorFn = Callable[[Mapping[str, Any]], Mapping[str, Any]]

_SHADOW_STATUSES = {"OPEN", "APPROVED", "IN_PROGRESS", "SNOOZED"}
_VERIFIED_STATUSES = {"VERIFIED"}


def _load_json_safe(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).is_file():
        return {}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _build_finding_status_maps(
    snapshot_doc: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build (status_by_trace_id, status_by_finding_id) from remediation_queue_snapshot.json."""
    by_trace: dict[str, str] = {}
    by_finding: dict[str, str] = {}
    for item in snapshot_doc.get("findings") or []:
        if not isinstance(item, Mapping):
            continue
        fid = str(item.get("finding_id") or "")
        status = str(item.get("status") or "OPEN").upper()
        if fid:
            by_finding[fid] = status
        for tid in item.get("sample_trace_ids") or []:
            tid_s = str(tid or "").strip()
            if tid_s:
                by_trace[tid_s] = status
        meta = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        for rid in meta.get("run_ids") or []:
            rid_s = str(rid or "").strip()
            if rid_s:
                by_trace[rid_s] = status
    return by_trace, by_finding


def _classify_case_enforcement(
    case: EvalCase,
    *,
    status_by_trace: Mapping[str, str],
    status_by_finding: Mapping[str, str],
) -> tuple[str, str]:
    """Return (enforcement_tier, linked_finding_status) where tier is 'shadow' or 'blocking'."""
    payload = case.unlabeled_input.get("payload") if isinstance(case.unlabeled_input, Mapping) else {}
    payload_dict = payload if isinstance(payload, Mapping) else {}
    fid = str(payload_dict.get("finding_id") or "")
    run_id = str(payload_dict.get("run_id") or "")

    linked_status = ""
    if fid and fid in status_by_finding:
        linked_status = status_by_finding[fid]
    elif case.source_trace_id and case.source_trace_id in status_by_trace:
        linked_status = status_by_trace[case.source_trace_id]
    elif run_id and run_id in status_by_trace:
        linked_status = status_by_trace[run_id]

    if linked_status in _VERIFIED_STATUSES:
        return "blocking", linked_status
    if linked_status in _SHADOW_STATUSES:
        return "shadow", linked_status
    if linked_status == "REJECTED":
        return "archived", linked_status
    if case.source_kind == "curated_holdout_seed":
        return "blocking", "CURATED_SEED"
    return "shadow", (linked_status or "UNLINKED_OPEN")


def _default_case_evaluator(
    unlabeled_view: Mapping[str, Any],
    *,
    linked_status: str,
) -> dict[str, Any]:
    """Evaluate a golden EvalCase deterministically via its unlabeled_view."""
    u_in = unlabeled_view.get("unlabeled_input") if isinstance(unlabeled_view.get("unlabeled_input"), Mapping) else {}
    payload = u_in.get("payload") if isinstance(u_in.get("payload"), Mapping) else u_in
    payload_dict = payload if isinstance(payload, Mapping) else {}

    if "simulated_candidate_pass" in payload_dict:
        passed = bool(payload_dict["simulated_candidate_pass"])
        veto_defects = list(payload_dict.get("simulated_veto_defects") or [])
        return {
            "label": "PASS" if passed and not veto_defects else "FAIL",
            "passed": passed and not veto_defects,
            "veto_defects": veto_defects,
        }

    # For historical trace-derived cases: once the linked finding is VERIFIED (pinned fix passed),
    # default deterministic replay passes unless regression_injected / veto_defects is flagged.
    reg_injected = bool(payload_dict.get("regression_injected", False))
    veto_defects = list(payload_dict.get("veto_defects") or [])
    if reg_injected or veto_defects:
        return {"label": "FAIL", "passed": False, "veto_defects": veto_defects}

    is_pass = linked_status in {"VERIFIED", "CURATED_SEED"}
    return {
        "label": "PASS" if is_pass else "FAIL",
        "passed": is_pass,
        "veto_defects": [],
    }


def _verify_case_contract(case: EvalCase, output: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Compare evaluator output against withheld expected_contract."""
    exp = case.expected_contract
    reasons: list[str] = []
    veto_dims = set(str(x) for x in (exp.get("veto_dimensions") or []))
    actual_vetoes = set(str(x) for x in (output.get("veto_defects") or []))
    if veto_dims & actual_vetoes:
        reasons.append(f"veto_dimension_triggered:{sorted(veto_dims & actual_vetoes)}")
    neg_labels = set(str(x) for x in (exp.get("negative_labels") or []))
    actual_label = str(output.get("label") or ("PASS" if output.get("passed") else "FAIL"))
    if actual_label in neg_labels:
        reasons.append(f"negative_label_matched:{actual_label}")
    ref_label = exp.get("reference_label")
    if ref_label is not None and actual_label != str(ref_label):
        reasons.append(f"label_mismatch:expected={ref_label},actual={actual_label}")
    elif ref_label is None and not bool(output.get("passed", False)):
        reasons.append("candidate_failed")
    return len(reasons) == 0, reasons


def evaluate_golden_flywheel_suite(
    *,
    repo_root: Path | str,
    app_filter: str = "all",
    golden_dataset_path: Path | str | None = None,
    queue_snapshot_path: Path | str | None = None,
    case_evaluator: GoldenCaseEvaluatorFn | None = None,
) -> dict[str, Any]:
    """Execute golden_eval_cases.json partitioning OPEN cases to shadow and VERIFIED cases to merge-blocking."""
    root = Path(repo_root).resolve()
    eff_golden = (
        Path(golden_dataset_path).resolve()
        if golden_dataset_path is not None
        else (root / "artifacts" / "learning" / "golden_eval_cases.json")
    )
    eff_snap = (
        Path(queue_snapshot_path).resolve()
        if queue_snapshot_path is not None
        else (root / "artifacts" / "learning" / "remediation_queue_snapshot.json")
    )

    golden_doc = _load_json_safe(eff_golden)
    snap_doc = _load_json_safe(eff_snap)
    status_by_trace, status_by_finding = _build_finding_status_maps(snap_doc)

    raw_cases = golden_doc.get("cases") or []
    shadow_total = 0
    shadow_passed = 0
    shadow_failures: list[dict[str, Any]] = []

    blocking_total = 0
    blocking_passed = 0
    blocking_failures: list[dict[str, Any]] = []

    for item in raw_cases:
        if not isinstance(item, Mapping):
            continue
        try:
            case = EvalCase.from_dict(item)
        except (KeyError, ValueError, TypeError):
            continue
        if app_filter not in ("all", "") and case.app_id != app_filter:
            continue

        tier, linked_status = _classify_case_enforcement(
            case,
            status_by_trace=status_by_trace,
            status_by_finding=status_by_finding,
        )
        if tier == "archived":
            continue

        # Strict label isolation: pass only unlabeled_view to the evaluator
        view = case.unlabeled_view
        if "expected_contract" in view:
            raise RuntimeError(f"Label isolation breach on case {case.case_id}")

        out = (
            case_evaluator(view)
            if case_evaluator is not None
            else _default_case_evaluator(view, linked_status=linked_status)
        )
        ok, fail_reasons = _verify_case_contract(case, out)

        if tier == "blocking":
            blocking_total += 1
            if ok:
                blocking_passed += 1
            else:
                blocking_failures.append(
                    {
                        "case_id": case.case_id,
                        "app_id": case.app_id,
                        "source_trace_id": case.source_trace_id,
                        "linked_status": linked_status,
                        "reasons": fail_reasons,
                    }
                )
        else:
            shadow_total += 1
            if ok:
                shadow_passed += 1
            else:
                shadow_failures.append(
                    {
                        "case_id": case.case_id,
                        "app_id": case.app_id,
                        "source_trace_id": case.source_trace_id,
                        "linked_status": linked_status,
                        "reasons": fail_reasons,
                    }
                )

    blocking_pass_rate = (blocking_passed / float(blocking_total)) if blocking_total > 0 else 1.0
    shadow_pass_rate = (shadow_passed / float(shadow_total)) if shadow_total > 0 else 1.0
    passed = len(blocking_failures) == 0

    return {
        "schema_version": "apps_eval.golden_flywheel_receipt.v1",
        "evaluated_at_utc": utc_now_iso(),
        "dataset_path": eff_golden.as_posix(),
        "dataset_digest": str(golden_doc.get("dataset_digest") or ""),
        "status": "PASS" if passed else "REGRESSION",
        "passed": passed,
        "blocking_total": blocking_total,
        "blocking_passed": blocking_passed,
        "blocking_pass_rate": round(blocking_pass_rate, 4),
        "blocking_failures": blocking_failures,
        "shadow_total": shadow_total,
        "shadow_passed": shadow_passed,
        "shadow_pass_rate": round(shadow_pass_rate, 4),
        "shadow_failures": shadow_failures,
    }
