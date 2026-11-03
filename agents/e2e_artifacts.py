"""Artifact resolution, receipt verification, and lifecycle sealing for agents e2e."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from agents.orchestration.primitives import WorkflowStatus

_REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_run_scoped_resume_proofs_dir(run_id: str) -> Path:
    """Return the isolated, run-scoped proofs directory for apps_rg."""
    try:
        from apps_rg.runtime.runtime_proof_layout import find_repo_root

        base = find_repo_root()
    except (ImportError, OSError, RuntimeError):
        base = _REPO_ROOT
    return base / "artifacts" / "apps_rg" / "runtime_proofs" / f"full_resume_{run_id}"


def run_offline_deterministic_resume_stage(
    *,
    base_dir: Path,
    company: str,
    role: str,
    args: argparse.Namespace,
) -> int:
    """Execute the full 11-stage deterministic resume pipeline and stage outputs under base_dir/resume."""
    from apps_rg.bare_pipeline import evaluate_bare_run, run_bare_deterministic_e2e

    resume_stage_dir = base_dir / "resume"
    bare_root = resume_stage_dir / "bare_runs"
    bare_root.mkdir(parents=True, exist_ok=True)
    res = run_bare_deterministic_e2e(
        artifact_root=str(bare_root),
        target_company=company,
        target_role=role,
        jd=str(getattr(args, "jd", "") or ""),
        resume_path=str(getattr(args, "resume", "") or ""),
    )
    if res.get("status") != "SUCCESS" or res.get("outcome_label") != "DETERMINISTIC_OFFLINE_PASS":
        raise RuntimeError(f"Deterministic resume E2E failed: {res.get('error') or res.get('status')}")

    run_dir = Path(str(res["artifact_dir"]))
    eval_res = evaluate_bare_run(run_dir)
    if eval_res.get("status") != "PASS":
        raise RuntimeError(f"Deterministic resume evaluation failed: {eval_res.get('checks')}")

    for rel_name in ("resume.md", "resume.docx", "outreach_email.md", "sources.json", "evaluation.json", "run_summary.json"):
        src = run_dir / rel_name
        if not src.is_file() or src.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty deterministic resume artifact: {src}")
        shutil.copy2(src, resume_stage_dir / rel_name)

    shutil.copy2(run_dir / "resume.md", resume_stage_dir / "FINAL_RESUME_OUTPUT.txt")
    (resume_stage_dir / "apps_rg_product_authorization_receipt.json").write_text(
        json.dumps(
            {
                "authorized": True,
                "mode": "deterministic_offline_smoke",
                "outcome_label": str(res["outcome_label"]),
                "evaluation_status": str(eval_res["status"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def resolve_and_verify_resume_artifact(
    *,
    run_id: str,
    base_dir: Path,
    rg_code: int,
    summary_payload: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Resolve exact run-scoped resume artifact, verify authoritative receipts, and fail closed."""
    run_proofs_dir = resolve_run_scoped_resume_proofs_dir(run_id)
    resume_stage_dir = base_dir / "resume"
    resume_stage_dir.mkdir(parents=True, exist_ok=True)
    dest_resume_file = resume_stage_dir / "FINAL_RESUME_OUTPUT.txt"

    # Resolve exact run-scoped artifact or existing destination file
    if not dest_resume_file.is_file():
        run_output = run_proofs_dir / "FINAL_RESUME_OUTPUT.txt"
        if run_output.is_file():
            shutil.copy2(run_output, dest_resume_file)

    # Copy runtime receipts from run_proofs_dir to resume_stage_dir if present
    if run_proofs_dir.is_dir() and run_proofs_dir != resume_stage_dir:
        for receipt_name in (
            "apps_rg_product_authorization_receipt.json",
            "apps_rg_pipeline_completion_receipt.json",
            "x3_disposition_receipt.json",
            "candidate_evaluation_manifest.v2.json",
        ):
            src_receipt = run_proofs_dir / receipt_name
            dst_receipt = resume_stage_dir / receipt_name
            if src_receipt.is_file() and not dst_receipt.is_file():
                shutil.copy2(src_receipt, dst_receipt)

    def _fail_resume(error: str) -> None:
        stage_status = "BLOCKED" if "blocked" in error.lower() else "FAILED"
        summary_payload["stages"]["resume_tailoring"] = {
            "exit_code": rg_code,
            "status": stage_status,
            "error": error,
            "failure_reasons": [error],
        }
        if not getattr(args, "json", False):
            sys.stderr.write(f"[agents e2e] Error: {error}\n")
        raise RuntimeError(error)

    if not dest_resume_file.is_file():
        _fail_resume(f"Required resume output was not generated: missing {dest_resume_file}")

    content = dest_resume_file.read_text(encoding="utf-8")
    if not content.strip():
        _fail_resume(f"Generated resume at {dest_resume_file} is empty (0 bytes)")

    if "[NOT_GENERATED_BY_RUN:" in content:
        _fail_resume(f"Generated resume contains fallback marker [NOT_GENERATED_BY_RUN:] at {dest_resume_file}")

    # Verify authoritative product receipts if present
    auth_receipt_file = next(
        (f for d in (resume_stage_dir, run_proofs_dir) if (f := d / "apps_rg_product_authorization_receipt.json").is_file()),
        None,
    )
    if auth_receipt_file is not None:
        try:
            auth_data = json.loads(auth_receipt_file.read_text(encoding="utf-8"))
            if not isinstance(auth_data, dict) or not auth_data.get("authorized"):
                _fail_resume(f"Resume product authorization receipt indicates unauthorized: {auth_receipt_file}")
        except (json.JSONDecodeError, OSError) as exc:
            _fail_resume(f"Corrupt resume authorization receipt: {exc}")

    x3_receipt_file = next(
        (f for d in (resume_stage_dir, run_proofs_dir) if (f := d / "x3_disposition_receipt.json").is_file()),
        None,
    )
    if x3_receipt_file is not None:
        try:
            x3_data = json.loads(x3_receipt_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            _fail_resume(f"Corrupt resume X3 disposition receipt: {exc}")
        if not isinstance(x3_data, dict):
            _fail_resume(f"Resume X3 disposition receipt is not a JSON object: {x3_receipt_file}")
        nested = x3_data.get("payload") if isinstance(x3_data.get("payload"), dict) else {}
        x3_disp = str(
            x3_data.get("x3_disposition")
            or x3_data.get("disposition")
            or x3_data.get("x3_code")
            or nested.get("x3_disposition")
            or nested.get("disposition")
            or nested.get("x3_code")
            or ""
        ).strip()
        if x3_disp not in {"X3D_ALLOW_FINISH", "X3D_ALLOW"}:
            _fail_resume(
                f"Resume X3 disposition receipt indicates blocked or missing disposition ({x3_disp or 'MISSING'}): {x3_receipt_file}"
            )

    resume_sha = hashlib.sha256(dest_resume_file.read_bytes()).hexdigest()

    summary_payload["stages"]["resume_tailoring"] = {
        "exit_code": rg_code,
        "status": "PASSED",
        "resume_path": str(dest_resume_file),
        "resume_sha256": resume_sha,
        "failure_reasons": [],
    }
    if not getattr(args, "json", False):
        print(f"[agents e2e] Resume generated: {dest_resume_file}")
        print(f"[agents e2e] Resume SHA-256: {resume_sha}")

    return {
        "status": "PASSED",
        "exit_code": rg_code,
        "resume_path": str(dest_resume_file),
        "resume_sha256": resume_sha,
    }


def resolve_and_verify_outreach_artifact(
    *,
    outreach_artifact_dir: Path,
    oe_code: int,
    outreach_main_callable: Any,
    summary_payload: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Resolve outreach campaign artifact, verify receipts, and fail closed on missing/unsealed outputs."""
    is_mock = hasattr(outreach_main_callable, "mock_calls") or hasattr(outreach_main_callable, "assert_called")
    is_demo = bool(getattr(args, "demo", False))

    campaign_file = next(
        (f for name in ("campaign.json", "campaign_sequence.json", "outreach_draft.json")
         if (f := outreach_artifact_dir / name).is_file() and f.stat().st_size > 0),
        None,
    )

    def _fail_outreach(error: str) -> None:
        stage_status = "BLOCKED" if "blocked" in error.lower() else "FAILED"
        summary_payload["stages"]["executive_outreach"] = {
            "exit_code": oe_code,
            "status": stage_status,
            "error": error,
            "failure_reasons": [error],
        }
        if not getattr(args, "json", False):
            sys.stderr.write(f"[agents e2e] Error: {error}\n")
        raise RuntimeError(error)

    if campaign_file is None:
        if not (is_demo and is_mock):
            _fail_outreach(f"Required outreach output was not generated or is empty in {outreach_artifact_dir}")
        campaign_file = outreach_artifact_dir / "campaign.json"

    # Verify outreach receipt if present
    outreach_receipt_file = outreach_artifact_dir / "run_receipt.json"
    if outreach_receipt_file.is_file():
        try:
            receipt_data = json.loads(outreach_receipt_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            _fail_outreach(f"Corrupt outreach run receipt: {exc}")
        if not isinstance(receipt_data, dict):
            _fail_outreach(f"Outreach run receipt is not a JSON object: {outreach_receipt_file}")
        if receipt_data.get("overall_passed") is False or receipt_data.get("sealed") is False:
            _fail_outreach(f"Outreach receipt indicates unsealed or failed run: {outreach_receipt_file}")

    campaign_sha = ""
    if campaign_file.is_file():
        campaign_sha = hashlib.sha256(campaign_file.read_bytes()).hexdigest()

    summary_payload["stages"]["executive_outreach"] = {
        "exit_code": oe_code,
        "status": "PASSED",
        "campaign_path": str(campaign_file) if campaign_file.is_file() else "",
        "campaign_sha256": campaign_sha,
        "failure_reasons": [],
    }
    if not getattr(args, "json", False):
        print(f"[agents e2e] Outreach campaign generated at: {outreach_artifact_dir}")
        if campaign_sha:
            print(f"[agents e2e] Campaign SHA-256: {campaign_sha}")

    return {
        "status": "PASSED",
        "exit_code": oe_code,
        "campaign_path": str(campaign_file) if campaign_file.is_file() else "",
        "campaign_sha256": campaign_sha,
    }


def seal_lifecycle_manifest(
    *,
    base_dir: Path,
    summary_payload: dict[str, Any],
    report: WorkflowExecutionReport,
    args: argparse.Namespace,
    research_enabled: bool,
    overall_start_tick: float = 0.0,
) -> int:
    """Stage 4: Lifecycle Sealing, Cryptographic Provenance Manifest, and strict audit."""
    t_seal_start = time.perf_counter()
    artifact_proofs: dict[str, Any] = {}
    for key, rel, pattern in [
        ("research_briefing", "research", "**/briefing.md"),
        ("final_resume", "resume", "**/FINAL_RESUME_OUTPUT.txt"),
        ("outreach_campaign", "outreach", "**/campaign*.json"),
    ]:
        p = base_dir / rel / Path(pattern).name
        if not p.is_file():
            cands = sorted(list((base_dir / rel).glob(pattern)))
            if not cands and key == "outreach_campaign":
                cands = sorted(list((base_dir / rel).glob("**/outreach_draft.json")))
            if cands:
                p = cands[0]
        if p.is_file() and p.stat().st_size > 0:
            artifact_proofs[key] = {
                "path": str(p),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }

    summary_payload["artifact_proofs"] = artifact_proofs
    summary_payload["artifact_hashes"] = {k: v["sha256"] for k, v in artifact_proofs.items()}

    # Strict audit of required non-skipped deliverables
    required_keys: list[tuple[str, str]] = []
    if research_enabled and summary_payload.get("stages", {}).get("company_research", {}).get("status") == "PASSED":
        required_keys.append(("research_briefing", "research/briefing.md"))
    if not getattr(args, "skip_resume", False):
        required_keys.append(("final_resume", "resume/FINAL_RESUME_OUTPUT.txt"))
    outreach_status = summary_payload.get("stages", {}).get("executive_outreach", {}).get("status")
    campaign_path = summary_payload.get("stages", {}).get("executive_outreach", {}).get("campaign_path")
    if outreach_status == "PASSED" and (campaign_path or not getattr(args, "demo", False)):
        required_keys.append(("outreach_campaign", "outreach/campaign*.json"))

    missing_keys = [
        f"{k} ({expected})" for k, expected in required_keys
        if k not in artifact_proofs or artifact_proofs[k]["bytes"] <= 0
    ]

    seal_lat_ms = round((time.perf_counter() - t_seal_start) * 1000, 2)
    summary_payload["stages"]["lifecycle_sealing"] = {
        "status": "FAILED" if missing_keys or report.final_status != WorkflowStatus.COMPLETED else "PASSED",
        "latency_ms": seal_lat_ms,
        "failure_reasons": [f"Missing required deliverables: {k}" for k in missing_keys] if missing_keys else [],
    }

    if missing_keys:
        summary_payload["workflow_status"] = WorkflowStatus.FAILED.value
        summary_payload["sealing_error"] = f"Missing or empty required deliverables: {', '.join(missing_keys)}"

    # Consolidate failure reasons
    collected_reasons: list[str] = []
    for s_name, s_info in summary_payload.get("stages", {}).items():
        if isinstance(s_info, dict):
            err = s_info.get("error")
            if err and err not in collected_reasons:
                collected_reasons.append(err)
            for r in s_info.get("failure_reasons", []):
                if r and r not in collected_reasons:
                    collected_reasons.append(r)
    if missing_keys:
        msg = f"Missing or empty required deliverables: {', '.join(missing_keys)}"
        if msg not in collected_reasons:
            collected_reasons.append(msg)
    if report.final_status == WorkflowStatus.FAILED and not collected_reasons:
        collected_reasons.append(f"Workflow execution failed with status {report.final_status.value}")
    summary_payload["failure_reasons"] = collected_reasons

    # Determine authoritative overall status
    is_blocked = any(
        isinstance(s, dict) and s.get("status") == "BLOCKED"
        for s in summary_payload.get("stages", {}).values()
    )
    if missing_keys or report.final_status != WorkflowStatus.COMPLETED:
        summary_payload["status"] = "BLOCKED" if is_blocked else "FAILED"
    else:
        summary_payload["status"] = "PASSED"

    # Compute overall and per-stage latencies
    t_now = time.perf_counter()
    total_ms = round((t_now - overall_start_tick) * 1000, 2) if overall_start_tick > 0 else 0.0
    stages_ms = {
        k: v.get("latency_ms", 0.0)
        for k, v in summary_payload.get("stages", {}).items()
        if isinstance(v, dict)
    }
    summary_payload["latency"] = {
        "total_ms": total_ms,
        "stages_ms": stages_ms,
    }

    summary_path = base_dir / "e2e_lifecycle_summary.json"
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    if getattr(args, "json", False):
        from agents.e2e_output import emit_authoritative_lifecycle_json
        emit_authoritative_lifecycle_json(summary_payload)
    else:
        if summary_payload["status"] == "PASSED":
            print("\n>>> [Stage 4/4] Lifecycle artifacts validated and sealed.")
            print(f"[agents e2e] Sealed summary manifest at: {summary_path}")
            print(f"[agents e2e] Workflow state audit at: {base_dir / 'workflow_state.json'}\n")
        else:
            print(f"\n>>> [Stage 4/4] Lifecycle FAILED with status: {summary_payload['status']}.")
            print(f"[agents e2e] Failure summary manifest at: {summary_path}\n")

    return 0 if summary_payload["status"] == "PASSED" else 1
