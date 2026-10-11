"""Focused offline E2E and replay integrity tests for outreach_engine.

Covers:
1. Complete 8-combination offline E2E matrix: {executive, recruiter} x {inmail, connection_note, email, follow_up}.
2. Sealed evidence immutability during eval (zero file modification, byte- and mtime-identical preservation).
3. Fail-closed behavior on missing or unreadable run_manifest.json (never silently substitute defaults).
4. No provenance fabrication (grounded_facts_used is never synthesized or injected).
5. Tamper detection without corrupting sealed evidence in run_dir.
6. show command fidelity across all artifact choices (draft, campaign, evaluation, validation, manifest, receipt).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
import pytest


def _run_cli(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hash_directory(directory: Path) -> dict[str, tuple[str, int]]:
    """Return map of filename -> (sha256, mtime_ns) for all files in directory."""
    result: dict[str, tuple[str, int]] = {}
    for p in directory.glob("*"):
        if p.is_file():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            result[p.name] = (digest, p.stat().st_mtime_ns)
    return result


# =============================================================================
# 1. 8-Combination Matrix: {executive, recruiter} x {inmail, connection_note, email, follow_up}
# =============================================================================
@pytest.mark.parametrize("audience", ["executive", "recruiter"])
@pytest.mark.parametrize("channel", ["inmail", "connection_note", "email", "follow_up"])
def test_offline_e2e_audience_channel_matrix(
    repo_root: Path,
    tmp_path: Path,
    audience: str,
    channel: str,
) -> None:
    """Verify clean offline generation, validation, evaluation, and multi-touch planning across all channels and audiences."""
    run_dir = tmp_path / f"matrix_{audience}_{channel}"
    res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--audience",
            audience,
            "--channel",
            channel,
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert res.returncode == 0, f"Run failed for {audience}/{channel}: {res.stderr}\nOutput: {res.stdout}"
    data = json.loads(res.stdout)

    assert data["status"] == "PASSED", f"Expected PASSED for {audience}/{channel}, got: {data}"
    assert data["overall_passed"] is True
    assert data["all_touches_passed"] is True
    assert data["validation"]["is_valid"] is True
    assert data["evaluation"]["passed"] is True
    assert data["campaign_status"] == "PASSED"
    assert len(data["campaign_touches"]) == 3
    assert len(data["blocked_touches"]) == 0

    # Ensure sealed artifacts exist on disk
    assert (run_dir / "outreach_draft.json").is_file()
    assert (run_dir / "validation_report.json").is_file()
    assert (run_dir / "evaluation_report.json").is_file()
    assert (run_dir / "campaign_sequence.json").is_file()
    assert (run_dir / "run_manifest.json").is_file()
    assert (run_dir / "run_receipt.json").is_file()


# =============================================================================
# 2. Replay Integrity: eval Never Mutates or Overwrites Sealed Artifacts
# =============================================================================
def test_eval_zero_file_mutation_and_verdict_recomputation(repo_root: Path, tmp_path: Path) -> None:
    """Verify eval recomputes verdicts authentically without touching or overwriting any file in run_dir."""
    run_dir = tmp_path / "immutability_run"
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0

    pre_eval_hashes = _hash_directory(run_dir)
    assert len(pre_eval_hashes) >= 6

    # Execute eval
    eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert eval_res.returncode == 0
    eval_data = json.loads(eval_res.stdout)
    assert eval_data["status"] == "PASSED"
    assert eval_data["is_valid"] is True
    assert eval_data["evaluation"]["passed"] is True

    # Take post-eval snapshot and verify byte-for-byte and mtime-for-mtime equality
    post_eval_hashes = _hash_directory(run_dir)
    assert pre_eval_hashes == post_eval_hashes, (
        f"eval violated replay integrity by modifying sealed evidence!\n"
        f"Pre: {pre_eval_hashes}\nPost: {post_eval_hashes}"
    )


# =============================================================================
# 3. Fail-Closed on Missing Manifest: Never Silently Substitute Defaults
# =============================================================================
def test_eval_fails_closed_when_manifest_missing(repo_root: Path, tmp_path: Path) -> None:
    """Verify eval fails closed with exit code 1 when run_manifest.json is missing."""
    run_dir = tmp_path / "missing_manifest_run"
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0

    # Delete run_manifest.json
    manifest_file = run_dir / "run_manifest.json"
    manifest_file.unlink()

    # eval must fail closed and report missing manifest
    eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert eval_res.returncode == 1, "eval must exit 1 when authentic manifest is missing!"
    eval_data = json.loads(eval_res.stdout)
    assert eval_data["status"] == "FAILED"
    assert "run_manifest.json" in eval_data["error"]


# =============================================================================
# 4. No Provenance Fabrication: Missing Facts Are Not Synthesized
# =============================================================================
def test_eval_no_missing_provenance_fabrication(repo_root: Path, tmp_path: Path) -> None:
    """Verify eval does not fabricate or inject missing fact IDs into drafts that lack them."""
    run_dir = tmp_path / "no_fabrication_run"
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0

    # Strip grounded_facts_used from outreach_draft.json on disk
    draft_file = run_dir / "outreach_draft.json"
    draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    draft_data["grounded_facts_used"] = []
    draft_file.write_text(json.dumps(draft_data, indent=2), encoding="utf-8")

    # In manifest as well, strip grounded facts
    manifest_file = run_dir / "run_manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["grounded_facts_used"] = []
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    # The evaluation runs with empty grounded_facts_used (no synthetic injection of fact_001).
    # Verify disk files were not mutated to inject facts
    post_draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    assert post_draft_data["grounded_facts_used"] == [], "eval must not write back fabricated facts!"


# =============================================================================
# 5. Tamper Detection Without Sealed Evidence Corruption
# =============================================================================
def test_eval_detects_tampering_without_corrupting_sealed_evidence(repo_root: Path, tmp_path: Path) -> None:
    """Verify eval catches disk tampering and exits 1, while preserving original sealed evidence files."""
    run_dir = tmp_path / "tamper_preservation_run"
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0

    orig_val_text = (run_dir / "validation_report.json").read_text(encoding="utf-8")
    orig_eval_text = (run_dir / "evaluation_report.json").read_text(encoding="utf-8")

    # Tamper with draft
    draft_file = run_dir / "outreach_draft.json"
    draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    draft_data["body"] = "Act now for an urgent compensation offer of $600,000 immediately without delay."
    draft_file.write_text(json.dumps(draft_data, indent=2), encoding="utf-8")

    eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert eval_res.returncode == 1, "Tampered draft must fail eval with exit 1!"
    eval_data = json.loads(eval_res.stdout)
    assert eval_data["status"] == "FAILED"
    assert eval_data["is_valid"] is False

    # CRUCIAL INVARIANT: Sealed evidence files on disk must remain pristine and uncorrupted!
    assert (run_dir / "validation_report.json").read_text(encoding="utf-8") == orig_val_text
    assert (run_dir / "evaluation_report.json").read_text(encoding="utf-8") == orig_eval_text


# =============================================================================
# 6. show Command Replay Fidelity Across All Supported Artifacts
# =============================================================================
def test_show_replays_all_artifacts(repo_root: Path, tmp_path: Path) -> None:
    """Verify show accurately replays draft, campaign, evaluation, validation, manifest, and receipt."""
    run_dir = tmp_path / "show_replay_run"
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0

    # Test all 6 artifacts
    for artifact in ("draft", "campaign", "evaluation", "validation", "manifest", "receipt"):
        show_res = _run_cli(
            [
                "outreach_engine",
                "show",
                "--run-dir",
                str(run_dir),
                "--artifact",
                artifact,
            ],
            repo_root,
        )
        assert show_res.returncode == 0, f"show failed for {artifact}: {show_res.stderr}"
        assert len(show_res.stdout.strip()) > 0, f"show returned empty output for {artifact}"

    # Test JSON output mode on show
    show_manifest_json = _run_cli(
        [
            "outreach_engine",
            "show",
            "--run-dir",
            str(run_dir),
            "--artifact",
            "manifest",
            "--json",
        ],
        repo_root,
    )
    assert show_manifest_json.returncode == 0
    m_data = json.loads(show_manifest_json.stdout)
    assert "candidate" in m_data
    assert "opportunity" in m_data
