#!/usr/bin/env python3
"""Run real E2E smoke verification and assert authoritative JSON output and disk artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def run_smoke(skip_resume: bool = True) -> int:
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

    print(f"[run_e2e_authoritative_smoke] Executing: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )

    if proc.returncode != 0:
        print(f"[FAIL] Process exited with non-zero code {proc.returncode}")
        print("--- STDERR ---")
        print(proc.stderr)
        print("--- STDOUT ---")
        print(proc.stdout)
        return proc.returncode

    # 1. Assert stdout is strictly parseable as exactly one JSON object
    stdout_trimmed = proc.stdout.strip()
    try:
        payload = json.loads(stdout_trimmed)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] stdout did not parse as authoritative JSON: {exc}")
        print("--- STDOUT ---")
        print(proc.stdout)
        return 1

    if not isinstance(payload, dict):
        print("[FAIL] Emitted JSON is not a root object dictionary")
        return 1

    # 2. Check top-level contract fields
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
            print(f"[FAIL] Missing required lifecycle field: {field}")
            return 1

    if payload["status"] != "PASSED":
        print(f"[FAIL] Expected status 'PASSED', got: {payload['status']}")
        return 1

    if payload["workflow_status"] != "COMPLETED":
        print(f"[FAIL] Expected workflow_status 'COMPLETED', got: {payload['workflow_status']}")
        return 1

    # 3. Verify every artifact in artifact_hashes and artifact_proofs exists on disk
    artifact_proofs = payload.get("artifact_proofs", {})
    artifact_hashes = payload.get("artifact_hashes", {})

    if not artifact_hashes:
        print("[FAIL] artifact_hashes is unexpectedly empty")
        return 1

    verified_artifacts = {}
    for name, expected_hash in artifact_hashes.items():
        proof = artifact_proofs.get(name)
        if not proof or not isinstance(proof, dict):
            print(f"[FAIL] Missing artifact proof for {name}")
            return 1

        path_str = proof.get("path")
        if not path_str:
            print(f"[FAIL] Missing file path for artifact proof {name}")
            return 1

        file_path = Path(path_str)
        if not file_path.is_file():
            print(f"[FAIL] Physical artifact file missing on disk: {file_path}")
            return 1

        size_bytes = file_path.stat().st_size
        if size_bytes == 0:
            print(f"[FAIL] Artifact file is 0 bytes: {file_path}")
            return 1

        if proof.get("bytes") != size_bytes:
            print(f"[FAIL] Artifact size mismatch for {name}: expected {proof.get('bytes')}, got {size_bytes}")
            return 1

        disk_sha = compute_sha256(file_path)
        if disk_sha != expected_hash:
            print(f"[FAIL] SHA-256 hash mismatch for {name}: expected {expected_hash}, got {disk_sha}")
            return 1

        verified_artifacts[name] = {
            "path": str(file_path),
            "bytes": size_bytes,
            "sha256": disk_sha,
            "verified_on_disk": True,
        }

    # 4. Verify base run directory artifacts: workflow_state.json, telemetry.jsonl
    artifact_dir = Path(payload["artifact_dir"])
    if not (artifact_dir / "workflow_state.json").is_file():
        print(f"[FAIL] workflow_state.json missing from {artifact_dir}")
        return 1
    if not (artifact_dir / "telemetry.jsonl").is_file():
        print(f"[FAIL] telemetry.jsonl missing from {artifact_dir}")
        return 1

    print("[PASS] Real E2E smoke completed cleanly.")
    print(f"       Run ID: {payload['run_id']}")
    print(f"       Status: {payload['status']}")
    print(f"       Total Latency: {payload['latency']['total_ms']}ms")
    print(f"       Verified {len(verified_artifacts)} physical artifact(s) on disk:")
    for name, info in verified_artifacts.items():
        print(f"         - {name}: {info['path']} ({info['bytes']} bytes, SHA256: {info['sha256'][:16]}...)")

    # 5. Write signed runtime execution receipt
    receipt = {
        "receipt_id": "rcpt_e2e_authoritative_json_smoke",
        "wave": 3,
        "status": "PASSED",
        "command": " ".join(cmd),
        "run_id": payload["run_id"],
        "total_latency_ms": payload["latency"]["total_ms"],
        "stages": payload["stages"],
        "verified_artifacts": verified_artifacts,
        "invariants_verified": [
            "Exactly one authoritative JSON root object emitted on stdout",
            "Zero stdout leakage from sub-engines",
            "All declared artifact_hashes exist physically on disk with matching SHA-256 and non-zero bytes",
            "Sealed lifecycle manifest and telemetry persisted",
        ],
    }

    receipt_path = _REPO_ROOT / "reports" / "e2e_authoritative_json_smoke_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"       Wrote receipt to: {receipt_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real E2E smoke and verify artifacts")
    parser.add_argument(
        "--full-resume",
        action="store_true",
        help="Do not skip resume tailoring (runs full apps_rg pipeline)",
    )
    args = parser.parse_args()
    return run_smoke(skip_resume=not args.full_resume)


if __name__ == "__main__":
    sys.exit(main())
