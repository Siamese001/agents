"""Regression tests for Wave 3 auditor contract parity, cache isolation, and SSOT centralization."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
for candidate in (str(APPS_RG_SRC), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from apps_rg.config.runtime_env import (  # noqa: E402
    get_runtime_env_flag,
    get_runtime_env_str,
    get_runtime_environ,
)
from tools.ssot_boundary_auditor import run_ssot_boundary_audit  # noqa: E402
from tools.ssot_hardcoding_scanner import run_hardcoding_scan  # noqa: E402
from tools.ssot_sprawl_scanner import run_sprawl_scan  # noqa: E402
from tools.validate_eval_rubrics import (  # noqa: E402
    _validate_data_holdout_surface,
    validate_eval_rubrics,
)


def test_eval_holdout_surface_ignores_wal_and_chroma_cache_but_flags_empty_dataset(
    tmp_path: Path,
) -> None:
    """Order 1/7 WAL truncation under data/cache must not trip Order 5/7 holdout validation."""
    cache_dir = tmp_path / "resume_graph_engine" / "data" / "cache" / "r1b_semantic_cache_chroma_v1"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "chroma.sqlite3-wal").write_bytes(b"")
    (cache_dir / "chroma.sqlite3-shm").write_bytes(b"")
    (cache_dir / "link_lists.bin").write_bytes(b"")

    valid_dir = tmp_path / "data" / "holdout"
    valid_dir.mkdir(parents=True, exist_ok=True)
    (valid_dir / "sample.json").write_text('{"id": "ok"}\n', encoding="utf-8")

    count, _, violations = _validate_data_holdout_surface(tmp_path)
    assert count == 1
    assert violations == []

    # Negative control: real 0-byte dataset file outside cache/ must still fail closed.
    (valid_dir / "broken_empty.json").write_bytes(b"")
    _, _, bad_violations = _validate_data_holdout_surface(tmp_path)
    assert any("broken_empty.json: empty benchmark/holdout data file" in v for v in bad_violations)


def test_apps_rg_runtime_env_helpers_and_zero_centralization_defects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Centralized apps_rg.config.runtime_env honors monkeypatch and clears sprawl/hardcoding scans."""
    monkeypatch.setenv("APPS_RG_TEST_TOGGLE_PROBE", "true")
    assert get_runtime_env_str("APPS_RG_TEST_TOGGLE_PROBE") == "true"
    assert get_runtime_env_flag("APPS_RG_TEST_TOGGLE_PROBE", default=False) is True
    assert get_runtime_environ().get("APPS_RG_TEST_TOGGLE_PROBE") == "true"

    monkeypatch.setenv("APPS_RG_TEST_TOGGLE_PROBE", "off")
    assert get_runtime_env_flag("APPS_RG_TEST_TOGGLE_PROBE", default=True) is False

    sprawl = run_sprawl_scan(REPO_ROOT)
    assert sprawl["is_clean"] is True, f"Unexpected sprawl findings: {sprawl}"
    assert sprawl["total_findings"] == 0

    hardcoding = run_hardcoding_scan(REPO_ROOT)
    assert hardcoding["is_clean"] is True, f"Unexpected hardcoding/env sprawl: {hardcoding}"
    assert hardcoding["total_findings"] == 0


def test_ssot_boundary_auditor_completes_under_budget_cleanly() -> None:
    """Order 2/7 SSOT boundary auditor completes within 15s and reports 0 defects."""
    t0 = time.perf_counter()
    report = run_ssot_boundary_audit(repo_root=REPO_ROOT)
    elapsed = time.perf_counter() - t0

    assert report["status"] == "PASS", f"SSOT boundary audit failed: {report}"
    assert report["is_clean"] is True
    assert report["total_centralization_defects"] == 0
    assert elapsed < 15.0, f"SSOT boundary audit exceeded 15s budget: {elapsed:.2f}s"


def test_eval_rubrics_and_auditor_status_key_parity() -> None:
    """Order 5/7 passes cleanly and Orders 3/7 & 4/7 declare top-level status keys."""
    eval_report = validate_eval_rubrics(REPO_ROOT)
    assert eval_report["status"] == "PASS", f"Eval rubrics failed: {eval_report['violations']}"
    assert eval_report["is_clean"] is True

    for rel_tool in ("tools/e2e_functionality_auditor.py", "tools/retrieval_surface_auditor.py"):
        src = (REPO_ROOT / rel_tool).read_text(encoding="utf-8")
        assert '"status": "PASS" if is_clean else "FAIL"' in src
