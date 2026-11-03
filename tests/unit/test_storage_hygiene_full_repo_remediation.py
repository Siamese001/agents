"""Behavioral counterfactual tests for full-repository storage hygiene bloat detection and remediation."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from tools.storage_worktree_hygiene import run_six_pillar_hygiene_audit
from tools.validate_sidecar_separation import DEFAULT_SIDECARS_ROOT, REPO_ROOT


def _init_sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "full_bloat_sandbox"
    (sandbox / "automations" / "prompts").mkdir(parents=True)
    for md_file in (REPO_ROOT / "automations" / "prompts").glob("*.md"):
        (sandbox / "automations" / "prompts" / md_file.name).write_text(
            md_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    subprocess.run(["git", "init", "-b", "main", str(sandbox)], check=True, capture_output=True, timeout=30)
    return sandbox


def test_storage_hygiene_deduplicates_models_and_prunes_unretained_runtime_proofs(tmp_path: Path) -> None:
    """Verify Pillar 4 detects and remediates duplicate model directories, unretained full_resume_* runs, and __pycache__."""
    sandbox = _init_sandbox(tmp_path)

    # 1. Seed identical canonical and duplicate model directories
    canon_model = sandbox / "artifacts" / "models" / "BAAI" / "bge-m3"
    dup_model = sandbox / "resume_graph_engine" / "artifacts" / "models" / "BAAI" / "bge-m3"
    canon_model.mkdir(parents=True)
    dup_model.mkdir(parents=True)
    weights_payload = b"w" * (256 * 1024)
    (canon_model / "model.safetensors").write_bytes(weights_payload)
    (dup_model / "model.safetensors").write_bytes(weights_payload)

    # 2. Seed 3 full_resume_* directories: 1 pointer-protected, 1 newest active, 1 stale unreferenced
    rp_dir = sandbox / "resume_graph_engine" / "artifacts" / "apps_rg" / "runtime_proofs"
    pointer_dir = rp_dir / "headline"
    pointer_dir.mkdir(parents=True)
    (pointer_dir / "latest_successful_real_run.json").write_text(
        json.dumps({"run_dir": "artifacts/apps_rg/runtime_proofs/full_resume_protected"}),
        encoding="utf-8",
    )

    now = time.time()
    for idx, (name, age_offset) in enumerate(
        [
            ("full_resume_protected", -3600),
            ("full_resume_stale_old", -7200),
            ("full_resume_newest", -60),
        ]
    ):
        r_dir = rp_dir / name
        r_dir.mkdir(parents=True)
        payload_fp = r_dir / "payload.json"
        payload_fp.write_bytes(b"x" * (200 * 1024))
        ts = now + age_offset
        os.utime(payload_fp, (ts, ts))
        os.utime(r_dir, (ts, ts))

    # 3. Seed 2 .runtime/tests runs (1 newest, 1 old) and a __pycache__ dir
    for name, age_offset in [("w8c_old", -5000), ("w8c_newest", -30)]:
        rt_dir = sandbox / "resume_graph_engine" / ".runtime" / "tests" / name
        rt_dir.mkdir(parents=True)
        f = rt_dir / "out.json"
        f.write_bytes(b"t" * (128 * 1024))
        ts = now + age_offset
        os.utime(f, (ts, ts))
        os.utime(rt_dir, (ts, ts))

    pycache = sandbox / "agents" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "mod.cpython-312.pyc").write_bytes(b"c" * 4096)

    pre = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=False)
    assert pre["status"] == "FINDINGS"
    assert pre["pillar_status"]["pillar_4_artifact_sprawl"] == "FINDINGS"
    assert pre["sprawl"]["duplicate_models_mb"] > 0.2
    assert pre["sprawl"]["unretained_full_resume_count"] == 1
    assert pre["sprawl"]["unretained_runtime_tests_count"] == 1
    assert pre["sprawl"]["pycache_dir_count"] == 1

    post = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=True)
    assert post["status"] == "PASS", post
    assert post["is_clean"] is True
    assert post["pillar_status"]["pillar_4_artifact_sprawl"] == "PASS"

    dup_models_root = sandbox / "resume_graph_engine" / "artifacts" / "models"
    assert dup_models_root.is_symlink()
    assert (dup_models_root / "BAAI" / "bge-m3" / "model.safetensors").is_file()
    assert (rp_dir / "full_resume_protected").is_dir()
    assert (rp_dir / "full_resume_newest").is_dir()
    assert not (rp_dir / "full_resume_stale_old").exists()
    assert (sandbox / "resume_graph_engine" / ".runtime" / "tests" / "w8c_newest").is_dir()
    assert not (sandbox / "resume_graph_engine" / ".runtime" / "tests" / "w8c_old").exists()
    assert not pycache.exists()


def test_storage_hygiene_flags_pycache_bloat_even_when_total_sprawl_below_500mb(tmp_path: Path) -> None:
    """Verify Pillar 4 flags __pycache__ directories even when total sprawl is under 500 MB."""
    sandbox = _init_sandbox(tmp_path)
    pycache = sandbox / "agents" / "__pycache__"
    pycache.mkdir(parents=True)
    (pycache / "mod.cpython-312.pyc").write_bytes(b"p" * 2048)

    pre = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=False)
    assert pre["sprawl"]["total_mb"] < 500.0
    assert pre["sprawl"]["pycache_dir_count"] == 1
    assert pre["pillar_status"]["pillar_4_artifact_sprawl"] == "FINDINGS"
    assert pre["status"] == "FINDINGS"

    post = run_six_pillar_hygiene_audit(repo_root=sandbox, sidecars_root=DEFAULT_SIDECARS_ROOT, remediate=True)
    assert post["pillar_status"]["pillar_4_artifact_sprawl"] == "PASS"
    assert post["status"] == "PASS"
    assert not pycache.exists()

