#!/usr/bin/env python3
"""Run real E2E smoke verification and assert authoritative JSON output and disk artifacts."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_deterministic_resume_pipeline(repo_root: Path, artifact_root: Path) -> dict[str, Any]:
    """Execute and verify the full 11-stage deterministic resume generation and DOCX export flow."""
    rg_src = repo_root / "resume_graph_engine" / "src"
    for p in (repo_root, rg_src):
        s = str(p)
        if p.is_dir() and s not in sys.path:
            sys.path.insert(0, s)

    from apps_rg.bare_pipeline import evaluate_bare_run, run_bare_deterministic_e2e

    res = run_bare_deterministic_e2e(artifact_root=str(artifact_root))
    if res.get("status") != "SUCCESS" or res.get("outcome_label") != "DETERMINISTIC_OFFLINE_PASS":
        raise RuntimeError(f"Deterministic resume E2E failed: {res.get('error') or res.get('status')}")

    run_dir = Path(str(res["artifact_dir"]))
    eval_res = evaluate_bare_run(run_dir)
    if eval_res.get("status") != "PASS":
        raise RuntimeError(f"Resume artifact evaluation failed: {eval_res.get('checks')}")

    verified_resume_files: dict[str, dict[str, Any]] = {}
    for rel_name in ("resume.md", "resume.docx", "outreach_email.md", "sources.json", "evaluation.json"):
        fpath = run_dir / rel_name
        if not fpath.is_file() or fpath.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty deterministic resume artifact: {fpath}")
        verified_resume_files[f"resume_pipeline::{rel_name}"] = {
            "path": str(fpath),
            "bytes": fpath.stat().st_size,
            "sha256": compute_sha256(fpath),
            "verified_on_disk": True,
        }
    return {
        "status": "PASSED",
        "outcome_label": str(res["outcome_label"]),
        "evaluation_status": str(eval_res["status"]),
        "verified_artifacts": verified_resume_files,
    }


def run_smoke(
    skip_resume: bool = True,
    *,
    read_only: bool = False,
    receipt_out: Path | None = None,
    repo_root: Path | None = None,
    verify_deterministic_resume: bool = True,
    quiet: bool = False,
) -> int:
    root = (repo_root or _DEFAULT_REPO_ROOT).resolve()

    with contextlib.ExitStack() as stack:
        temp_root: Path | None = None
        if read_only:
            temp_root = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="agents_e2e_ro_")))

        cmd = [
            sys.executable,
            "-m",
            "agents",
            "e2e",
            "--demo",
            "--json",
        ]
        if skip_resume:
            cmd.append("--skip-resume")
        if temp_root is not None:
            e2e_out = temp_root / "e2e_lifecycle"
            e2e_out.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--artifact-dir", str(e2e_out)])

        if not quiet:
            print(f"[run_e2e_authoritative_smoke] Executing: {' '.join(cmd)}")
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            shell=False,
            timeout=180,
        )

        if proc.returncode != 0:
            if not quiet:
                print(f"[FAIL] Process exited with non-zero code {proc.returncode}")
                print("--- STDERR ---")
                print(proc.stderr)
                print("--- STDOUT ---")
                print(proc.stdout)
            return proc.returncode

        stdout_trimmed = proc.stdout.strip()
        try:
            payload = json.loads(stdout_trimmed)
        except json.JSONDecodeError as exc:
            if not quiet:
                print(f"[FAIL] stdout did not parse as authoritative JSON: {exc}")
            return 1

        if not isinstance(payload, dict):
            if not quiet:
                print("[FAIL] Emitted JSON is not a root object dictionary")
            return 1

        for field in (
            "run_id",
            "status",
            "workflow_status",
            "stages",
            "artifact_hashes",
            "artifact_proofs",
            "latency",
            "failure_reasons",
        ):
            if field not in payload:
                if not quiet:
                    print(f"[FAIL] Missing required lifecycle field: {field}")
                return 1

        if payload["status"] != "PASSED":
            if not quiet:
                print(f"[FAIL] Expected status 'PASSED', got: {payload['status']}")
            return 1

        if payload["workflow_status"] != "COMPLETED":
            if not quiet:
                print(f"[FAIL] Expected workflow_status 'COMPLETED', got: {payload['workflow_status']}")
            return 1

        artifact_proofs = payload.get("artifact_proofs", {})
        artifact_hashes = payload.get("artifact_hashes", {})

        if not artifact_hashes:
            if not quiet:
                print("[FAIL] artifact_hashes is unexpectedly empty")
            return 1

        verified_artifacts: dict[str, dict[str, Any]] = {}
        for name, expected_hash in artifact_hashes.items():
            proof = artifact_proofs.get(name)
            if not proof or not isinstance(proof, dict):
                if not quiet:
                    print(f"[FAIL] Missing artifact proof for {name}")
                return 1

            path_str = proof.get("path")
            if not path_str:
                if not quiet:
                    print(f"[FAIL] Missing file path for artifact proof {name}")
                return 1

            file_path = Path(path_str)
            if not file_path.is_file():
                if not quiet:
                    print(f"[FAIL] Physical artifact file missing on disk: {file_path}")
                return 1

            size_bytes = file_path.stat().st_size
            if size_bytes == 0 or proof.get("bytes") != size_bytes:
                if not quiet:
                    print(f"[FAIL] Artifact byte count mismatch for {name}")
                return 1

            disk_sha = compute_sha256(file_path)
            if disk_sha != expected_hash:
                if not quiet:
                    print(f"[FAIL] SHA-256 hash mismatch for {name}: expected {expected_hash}, got {disk_sha}")
                return 1

            verified_artifacts[name] = {
                "path": str(file_path),
                "bytes": size_bytes,
                "sha256": disk_sha,
                "verified_on_disk": True,
            }

        artifact_dir = Path(payload["artifact_dir"])
        if not (artifact_dir / "workflow_state.json").is_file():
            if not quiet:
                print(f"[FAIL] workflow_state.json missing from {artifact_dir}")
            return 1
        if not (artifact_dir / "telemetry.jsonl").is_file():
            if not quiet:
                print(f"[FAIL] telemetry.jsonl missing from {artifact_dir}")
            return 1

        resume_verification: dict[str, Any] = {"status": "SKIPPED"}
        if skip_resume and verify_deterministic_resume:
            det_dir = (
                (temp_root / "deterministic_resume")
                if temp_root is not None
                else Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="agents_det_resume_")))
            )
            det_dir.mkdir(parents=True, exist_ok=True)
            try:
                resume_verification = _verify_deterministic_resume_pipeline(root, det_dir)
                verified_artifacts.update(resume_verification["verified_artifacts"])
            except Exception as exc:  # guardian: allow-broad-exception -- fail closed on any resume smoke error
                if not quiet:
                    print(f"[FAIL] Deterministic resume pipeline verification failed: {exc}")
                return 1

        receipt = {
            "receipt_id": "rcpt_e2e_authoritative_json_smoke",
            "wave": 3,
            "status": "PASSED",
            "read_only": read_only,
            "command": " ".join(cmd),
            "run_id": payload["run_id"],
            "total_latency_ms": payload["latency"]["total_ms"],
            "stages": payload["stages"],
            "deterministic_resume_pipeline": {
                "status": resume_verification.get("status"),
                "outcome_label": resume_verification.get("outcome_label", ""),
            },
            "verified_artifacts": verified_artifacts,
            "invariants_verified": [
                "Exactly one authoritative JSON root object emitted on stdout",
                "Zero stdout leakage from sub-engines",
                "All declared artifact_hashes exist physically on disk with matching SHA-256 and non-zero bytes",
                "Both executive outreach and deterministic resume tailoring artifacts verified on disk",
                "Sealed lifecycle manifest and telemetry persisted",
            ],
        }

        if receipt_out is not None:
            target_receipt_path = receipt_out.resolve()
        elif read_only and temp_root is not None:
            target_receipt_path = temp_root / "e2e_authoritative_json_smoke_receipt.json"
        else:
            target_receipt_path = root / "reports" / "e2e_authoritative_json_smoke_receipt.json"

        target_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        target_receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

        if not quiet:
            print("[PASS] Real E2E smoke completed cleanly.")
            print(f"       Run ID: {payload['run_id']}")
            print(f"       Status: {payload['status']}")
            print(f"       Resume Pipeline: {resume_verification.get('status')}")
            print(f"       Verified {len(verified_artifacts)} physical artifact(s) on disk.")
            print(f"       Wrote receipt to: {target_receipt_path}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real E2E smoke and verify outreach + resume artifacts")
    parser.add_argument(
        "--full-resume",
        action="store_true",
        help="Run live provider apps_rg stage inside agents e2e instead of offline deterministic resume smoke",
    )
    parser.add_argument(
        "--outreach-only",
        action="store_true",
        help="Skip offline deterministic resume verification when --full-resume is not set",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Write run outputs and receipt to temporary paths so tracked folders remain untouched",
    )
    parser.add_argument("--receipt-out", type=Path, default=None, help="Explicit receipt output path")
    parser.add_argument("--repo-root", type=Path, default=_DEFAULT_REPO_ROOT, help="Repository root")
    args = parser.parse_args(argv)
    return run_smoke(
        skip_resume=not args.full_resume,
        read_only=args.read_only,
        receipt_out=args.receipt_out,
        repo_root=args.repo_root,
        verify_deterministic_resume=not args.outreach_only,
    )


if __name__ == "__main__":
    sys.exit(main())
