"""The sole public Apps RG whole-resume command.

Use one command surface only:

``python -m apps_rg run``
``python -m apps_rg eval``
``python -m apps_rg show``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from apps_rg.runtime.orchestration.canonical_dispatch import (
    run_canonical_apps_rg_from_cli_primitives,
)
from apps_rg.runtime.runtime_boundary import RuntimeBoundaryViolation

DEFAULT_TARGET_COMPANY = "Anthropic"
DEFAULT_TARGET_ROLE = "Manager of Applied AI Architecture, Partnerships"
_PACKAGE_ROOT = Path(__file__).resolve().parent
_DEFAULT_JD_PATH = _PACKAGE_ROOT / "config" / "targeting" / "anthropic_manager_applied_ai_architecture_partnerships_jd.txt"
_DEFAULT_RESUME_PATH = _PACKAGE_ROOT / "resume" / "base" / "amit_ayer_base_resume_v1.json"

__all__ = ["_build_parser", "main"]


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target-company", default=DEFAULT_TARGET_COMPANY)
    parser.add_argument("--target-role", default=DEFAULT_TARGET_ROLE)
    parser.add_argument(
        "--jd",
        default="",
        help="Optional JD file path or inline text. Defaults to the canonical Anthropic JD.",
    )
    parser.add_argument(
        "--resume",
        default="",
        help="Optional base-resume JSON, Markdown, or text path. Defaults to the canonical base resume.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="",
        help=(
            "Optional fresh output directory beneath artifacts/apps_rg/runtime_proofs. "
            "The governed product run rejects any other destination."
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apps_rg",
        description=(
            "The single Apps RG governed resume pipeline. Run the full live product flow, "
            "inspect a completed run, or print an exact output artifact."
        ),
    )
    subparsers = parser.add_subparsers(dest="action", metavar="ACTION")

    run = subparsers.add_parser("run", help="run the canonical resume pipeline")
    _add_run_arguments(run)

    evaluate = subparsers.add_parser("eval", help="re-evaluate an existing run without a provider call")
    evaluate.add_argument("--run-dir", required=True, help="Completed run directory.")

    show = subparsers.add_parser("show", help="print an exact output artifact from a completed run")
    show.add_argument("--run-dir", required=True, help="Completed run directory.")
    show.add_argument(
        "--artifact",
        required=True,
        choices=("resume", "email", "research", "summary", "evaluation"),
        help="Artifact to print exactly.",
    )
    return parser


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["run"]
    if values[0] in {"-h", "--help"}:
        return values
    actions = {"run", "eval", "show"}
    if values[0] not in actions and values[0].startswith("-"):
        return ["run", *values]
    return values


def _completed_run_path(result: dict[str, Any]) -> Path | None:
    raw = str(result.get("artifact_dir") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _read_input_text(value: str, *, default_path: Path, label: str) -> str:
    """Resolve CLI-owned input into immutable text before governed product entry."""

    raw = str(value or "").strip()
    path = Path(raw).expanduser() if raw else default_path
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read {label}: {type(exc).__name__}: {exc}") from exc
    if raw:
        return raw
    raise ValueError(f"default {label} is unavailable: {default_path}")


def _read_first_artifact(
    result: dict[str, Any],
    candidates: Sequence[str],
) -> tuple[str | None, str | None]:
    run_dir = _completed_run_path(result)
    if run_dir is None:
        return None, "run artifact directory is unavailable"
    for relative_path in candidates:
        path = run_dir / relative_path
        if not path.is_file():
            continue
        try:
            return path.read_text(encoding="utf-8"), None
        except OSError as exc:
            return None, f"cannot read {relative_path}: {type(exc).__name__}: {exc}"
    return None, f"required artifact was not written: {', '.join(candidates)}"


def _read_json_artifact(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _x3_disposition(receipt: dict[str, Any] | None) -> str:
    """Read either the current whole-run receipt or the nested legacy receipt."""

    payload = (receipt or {}).get("payload")
    nested = payload if isinstance(payload, dict) else {}
    return str(
        (receipt or {}).get("x3_disposition")
        or (receipt or {}).get("disposition")
        or (receipt or {}).get("x3_code")
        or nested.get("x3_disposition")
        or nested.get("disposition")
        or nested.get("x3_code")
        or ""
    )


def _evaluate_product_run(run_dir: Path) -> dict[str, Any]:
    """Summarize real product evaluation receipts without another provider call."""

    completion_ref = "apps_rg_pipeline_completion_receipt.json"
    completion = _read_json_artifact(run_dir / completion_ref)
    if completion is None:
        completion_ref = "apps_rg_post_x3_completion_receipt.json"
        completion = _read_json_artifact(run_dir / completion_ref)
    authorization = _read_json_artifact(run_dir / "apps_rg_product_authorization_receipt.json")
    x3_ref = "x3_disposition_receipt.json"
    x3 = _read_json_artifact(run_dir / x3_ref)
    x3_disposition = _x3_disposition(x3)
    if not x3_disposition:
        x3_ref = "apps_rg_whole_run_exit_review_packet.json"
        x3 = _read_json_artifact(run_dir / x3_ref)
        x3_disposition = _x3_disposition(x3)
    eval_records = [
        _read_json_artifact(path)
        for path in sorted((run_dir / "apps_eval").glob("**/eval_record.json"))
        if path.is_file()
    ]
    eval_records = [record for record in eval_records if record is not None]

    # Validate candidate manifest if present
    candidate_manifest_path = run_dir / "candidate_evaluation_manifest.v2.json"
    candidate_manifest_errors: list[str] = []
    if candidate_manifest_path.is_file():
        from apps_rg.runtime.evaluation_manifest import validate_candidate_evaluation_manifest

        _, candidate_manifest_errors = validate_candidate_evaluation_manifest(run_dir)

    l6_audit = _read_json_artifact(run_dir / "l6_evaluation_audit.v2.json")

    completed = bool(completion and completion.get("pipeline_complete"))
    authorized = bool(authorization and authorization.get("authorized"))

    # Check if a complete evaluation_decision was persisted in the completion receipt
    saved_decision = None
    if isinstance(completion, dict):
        saved_decision = completion.get("evaluation_decision")
        if not isinstance(saved_decision, dict):
            payload = completion.get("payload")
            if isinstance(payload, dict):
                saved_decision = payload.get("evaluation_decision")

    evals_passed = bool(eval_records) and all(
        str(record.get("status") or record.get("verdict") or "PASS").upper()
        not in {"FAIL", "BLOCKED"}
        for record in eval_records
    )

    l6_pass = l6_audit.get("l6_integrity_status") == "PASS" if l6_audit else True
    manifest_pass = not candidate_manifest_errors

    if isinstance(saved_decision, dict):
        execution_status = str(saved_decision.get("execution_status") or "PASS")
        package_integrity_status = str(saved_decision.get("package_integrity_status") or "PASS")
        evaluation_validity = (
            "INVALID"
            if not manifest_pass
            else str(saved_decision.get("evaluation_validity") or "INVALID")
        )
        deterministic_product_status = str(
            saved_decision.get("deterministic_product_status") or "FAIL"
        )
        l6_integrity_status = str(saved_decision.get("l6_integrity_status") or "PASS")
        evaluation_status = str(saved_decision.get("evaluation_status") or "PASS")
        if candidate_manifest_errors and evaluation_status == "PASS":
            evaluation_status = "EVALUATION_INVALID"
    else:
        execution_status = "PASS" if bool(eval_records) else "ERROR"
        package_integrity_status = "PASS" if bool(eval_records) else "INVALID"
        evaluation_validity = (
            "PASS" if (manifest_pass and l6_pass and bool(eval_records)) else "INVALID"
        )
        deterministic_product_status = (
            "PASS" if (evals_passed and x3_disposition == "X3D_ALLOW_FINISH") else "FAIL"
        )
        l6_integrity_status = str(
            (l6_audit.get("l6_integrity_status") or "PASS") if l6_audit else "PASS"
        )
        evaluation_status = (
            "PASS"
            if (
                completed
                and authorized
                and evaluation_validity == "PASS"
                and deterministic_product_status == "PASS"
            )
            else "EVALUATION_INVALID"
            if evaluation_validity != "PASS"
            else "PRODUCT_FAIL"
        )

    status = (
        "PASS"
        if (
            completed
            and authorized
            and x3_disposition == "X3D_ALLOW_FINISH"
            and evals_passed
            and evaluation_status == "PASS"
        )
        else "BLOCKED"
    )

    from apps_rg.runtime.cli_exit_codes import exit_code_from_evaluation_decision

    exit_code = (
        0
        if status == "PASS"
        else exit_code_from_evaluation_decision(
            {
                "evaluation_status": evaluation_status,
                "execution_status": execution_status,
                "evaluation_validity": evaluation_validity,
                "deterministic_product_status": deterministic_product_status,
                "pipeline_complete": completed,
            }
        )
    )

    return {
        "schema_version": "apps_rg.public_cli_product_evaluation.v1",
        "status": status,
        "evaluation_status": evaluation_status,
        "execution_status": execution_status,
        "package_integrity_status": package_integrity_status,
        "evaluation_validity": evaluation_validity,
        "deterministic_product_status": deterministic_product_status,
        "l6_integrity_status": l6_integrity_status,
        "semantic_factuality_status": "PENDING_CALIBRATION",
        "quality_advisory_status": "PENDING_CALIBRATION",
        "pipeline_complete": completed,
        "product_authorized": authorized,
        "x3_disposition": x3_disposition,
        "exit_code": exit_code,
        "candidate_manifest_errors": candidate_manifest_errors,
        "completion_receipt_ref": completion_ref if completion is not None else "",
        "x3_receipt_ref": x3_ref if x3 is not None else "",
        "apps_eval_record_count": len(eval_records),
        "apps_eval_records": eval_records,
    }


def _inline_evaluations(result: dict[str, Any]) -> dict[str, Any]:
    """Return full product evaluation evidence without issuing another provider call."""
    run_dir = _completed_run_path(result)
    if run_dir is None:
        return {"status": "UNAVAILABLE", "reason": "run artifact directory is unavailable"}
    return _evaluate_product_run(run_dir)


def _runtime_details(result: dict[str, Any]) -> dict[str, Any]:
    """Render the operational receipt without duplicating the full resume."""
    keys = (
        "pipeline",
        "command",
        "run_id",
        "status",
        "mode",
        "outcome_label",
        "failure_stage",
        "error",
        "repository",
        "target_company",
        "target_role",
        "inputs",
        "outputs",
        "provider_call_count",
        "providers",
        "stages",
        "delivery",
        "finished_at_utc",
    )
    return {key: result[key] for key in keys if key in result}


def _print_inline_run_outputs(result: dict[str, Any]) -> None:
    """Always print the product, evaluations, and execution receipt after ``run``."""
    run_dir = _completed_run_path(result)
    resume_status = (
        _read_json_artifact(run_dir / "FINAL_RESUME_OUTPUT.json") if run_dir is not None else None
    )
    if resume_status is not None and str(resume_status.get("status") or "") != "PASS":
        resume = None
        resume_error = (
            "no authorized final resume; "
            f"FINAL_RESUME_OUTPUT.status={resume_status.get('status')!r}"
        )
    else:
        resume, resume_error = _read_first_artifact(
            result,
            ("FINAL_RESUME_OUTPUT.txt", "outputs/resume.md", "resume.md"),
        )
    print("FULL_RESUME", flush=True)
    print("```markdown", flush=True)
    print(resume.rstrip() if resume is not None else f"UNAVAILABLE: {resume_error}", flush=True)
    print("```", flush=True)

    print("EVALS", flush=True)
    print("```json", flush=True)
    print(json.dumps(_inline_evaluations(result), ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    print("```", flush=True)

    print("RUNTIME_DETAILS", flush=True)
    print("```json", flush=True)
    print(json.dumps(_runtime_details(result), ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    print("```", flush=True)


def _print_result(result: dict[str, Any]) -> None:
    print(
        "APPS_RG "
        f"status={result.get('status', 'FAIL')} "
        f"mode={result.get('mode', '')} "
        f"outcome={result.get('outcome_label', '')} "
        f"run_dir={result.get('artifact_dir', '')}",
        flush=True,
    )
    repository = result.get("repository")
    if isinstance(repository, dict):
        print(
            "CODE "
            f"root={repository.get('repository_root', '')} "
            f"branch={repository.get('branch', '')} "
            f"commit={repository.get('commit_sha', '')} "
            f"on_local_main={repository.get('head_is_ancestor_of_local_main', False)} "
            f"dirty={repository.get('worktree_dirty', False)}",
            flush=True,
        )
    for stage in result.get("stages", []):
        if not isinstance(stage, dict):
            continue
        line = f"{stage.get('stage', '?')} {stage.get('status', '?')}"
        if stage.get("error"):
            line += f" {stage['error']}"
        print(line, flush=True)
    for name, provider in (result.get("providers") or {}).items():
        if not isinstance(provider, dict):
            continue
        print(
            f"PROVIDER {name} {provider.get('provider', '')} "
            f"{provider.get('observed_model', '')} {provider.get('status', '')}",
            flush=True,
        )
    evaluation = result.get("evaluation")
    if isinstance(evaluation, dict):
        print(
            f"EVALUATION {evaluation.get('verdict', '')} score={evaluation.get('score', '')}",
            flush=True,
        )
    if result.get("error"):
        print(f"APPS_RG_ERROR {result['error']}", file=sys.stderr, flush=True)
    _print_inline_run_outputs(result)


def _print_evaluation(report: dict[str, Any]) -> None:
    print(f"APPS_RG_EVAL status={report.get('status', 'FAIL')} run_dir={report.get('run_dir', '')}")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def _read_product_artifact(run_dir: Path, artifact: str) -> str:
    artifacts = {
        "resume": ("FINAL_RESUME_OUTPUT.txt", "outputs/resume.md", "resume.md"),
        "email": ("outputs/outreach_email.md", "outreach_email.md"),
        "research": ("research/delegated_briefing.json", "research.md"),
        "summary": ("apps_rg_e2e_terminal_manifest.json", "run_summary.json"),
    }
    if artifact == "evaluation":
        return json.dumps(_evaluate_product_run(run_dir), ensure_ascii=False, indent=2, sort_keys=True)
    for candidate in artifacts[artifact]:
        path = run_dir / candidate
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise ValueError(f"artifact {artifact!r} was not written for {run_dir}")


def _run_product_from_cli(args: argparse.Namespace) -> dict[str, Any]:
    jd_text = _read_input_text(args.jd, default_path=_DEFAULT_JD_PATH, label="job description")
    resume_text = _read_input_text(args.resume, default_path=_DEFAULT_RESUME_PATH, label="base resume")
    result = run_canonical_apps_rg_from_cli_primitives(
        target_company=args.target_company,
        target_role=args.target_role,
        jd=jd_text,
        job_description_text=jd_text,
        source_resume_text=resume_text,
        artifact_dir=args.artifact_dir,
    )
    out = dict(result)
    product_evaluation = _inline_evaluations(out)
    # The post-X3 completion receipt, bound whole-run X3 result, and Apps Eval
    # record are the final product authority.  The dispatch return is an
    # intermediate transport summary and can retain an earlier advisory state
    # (for example, an L6 observation) after the final authority artifacts
    # have authorized the product.
    success = product_evaluation.get("status") == "PASS"
    if success:
        out["canonical_exit_status"] = out.get("exit_status")
        out["canonical_outcome_authorized"] = out.get("outcome_authorized")
        out["exit_status"] = "success"
        out["outcome_authorized"] = True
        out["pipeline_complete"] = True
        out["product_authorized"] = True
        out["authority_source"] = "post_x3_completion_and_apps_eval"
    out["status"] = "SUCCESS" if success else "BLOCKED"
    out["mode"] = "live"
    out["outcome_label"] = (
        "GOVERNED_PRODUCT_AUTHORIZED" if success else "GOVERNED_PRODUCT_NOT_AUTHORIZED"
    )
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the sole supported Apps RG resume workflow or its inspection actions."""
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--patch-run" or arg.startswith("--patch-run=") for arg in raw_argv):
        from apps_rg.runtime.orchestration.patch_run import main as patch_main

        patch_args: list[str] = []
        skip_next = False
        for i, a in enumerate(raw_argv):
            if skip_next:
                skip_next = False
                continue
            if a == "--patch-run":
                if i + 1 < len(raw_argv):
                    patch_args.append(raw_argv[i + 1])
                    skip_next = True
            elif a.startswith("--patch-run="):
                patch_args.append(a.split("=", 1)[1])
            else:
                patch_args.append(a)
        return patch_main(patch_args)

    parser = _build_parser()
    args = parser.parse_args(_normalize_argv(argv))
    action = args.action or "run"
    try:
        if action == "run":
            result = _run_product_from_cli(args)
            _print_result(result)
            return 0 if result.get("status") == "SUCCESS" else 1
        if action == "eval":
            report = _evaluate_product_run(Path(args.run_dir).expanduser().resolve())
            report["run_dir"] = str(Path(args.run_dir).expanduser().resolve())
            _print_evaluation(report)
            return 0 if report.get("status") == "PASS" else 1
        if action == "show":
            sys.stdout.write(
                _read_product_artifact(Path(args.run_dir).expanduser().resolve(), args.artifact)
            )
            return 0
    except RuntimeBoundaryViolation as exc:
        print(f"APPS_RG_PATH_AUTHORITY_BLOCK {exc}", file=sys.stderr, flush=True)
        return 1
    except ValueError as exc:
        print(f"APPS_RG_ERROR {exc}", file=sys.stderr, flush=True)
        return 1
    parser.error(f"unsupported action: {action!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
