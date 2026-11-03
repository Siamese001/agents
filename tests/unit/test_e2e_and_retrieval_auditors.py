"""Behavioral and fault-injection tests for Wave 2 E2E and Retrieval Surface Auditors."""

from __future__ import annotations

import json
from pathlib import Path

from tools.e2e_functionality_auditor import (
    main as e2e_main,
    scan_unguarded_silent_swallows,
)
from tools.retrieval_surface_auditor import (
    main as retrieval_main,
    scan_untyped_public_retrieval_callables,
)
from tools.verify_pipeline_latency_caching import (
    verify_compiler_cache_alignment,
    verify_live_cache_probes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_e2e_functionality_auditor_passes_read_only_without_dirtying_reports(tmp_path: Path) -> None:
    tracked_receipt = REPO_ROOT / "reports" / "e2e_authoritative_json_smoke_receipt.json"
    before_mtime = tracked_receipt.stat().st_mtime_ns if tracked_receipt.exists() else None

    out_path = tmp_path / "e2e_audit_receipt.json"
    rc = e2e_main(["--repo-root", str(REPO_ROOT), "--read-only", "--output", str(out_path)])
    assert rc == 0
    assert out_path.is_file()

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["is_clean"] is True, f"Unexpected E2E audit gaps: {report['gaps']}"
    assert report["passing_pillars"] == 6
    assert report["total_gaps"] == 0

    after_mtime = tracked_receipt.stat().st_mtime_ns if tracked_receipt.exists() else None
    assert before_mtime == after_mtime, "Read-only E2E audit mutated tracked reports/ receipt!"


def test_retrieval_surface_auditor_passes_live_without_static_receipt(tmp_path: Path) -> None:
    out_path = tmp_path / "retrieval_audit_receipt.json"
    rc = retrieval_main(["--repo-root", str(REPO_ROOT), "--read-only", "--output", str(out_path)])
    assert rc == 0
    assert out_path.is_file()

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["is_clean"] is True, f"Unexpected retrieval audit gaps: {report['gaps']}"
    assert report["passing_pillars"] == 7
    assert report["total_gaps"] == 0

    live_cache = verify_live_cache_probes(REPO_ROOT, quiet=True)
    assert live_cache["passed"] is True
    assert live_cache["openai_prefix_ok"] is True
    assert live_cache["anthropic_breakpoint_ok"] is True
    assert live_cache["exact_and_briefing_ok"] is True


def test_fault_injection_unguarded_broad_except_empty_return_detected(tmp_path: Path) -> None:
    bad_mod = tmp_path / "agents" / "orchestration" / "faulty_handoff.py"
    bad_mod.parent.mkdir(parents=True, exist_ok=True)
    bad_mod.write_text(
        "def run_handoff(payload: dict) -> dict | None:\n"
        "    try:\n"
        "        return payload['data']\n"
        "    except Exception:\n"
        "        return None\n",
        encoding="utf-8",
    )
    swallows = scan_unguarded_silent_swallows(tmp_path)
    assert len(swallows) == 1
    assert swallows[0]["file"] == "agents/orchestration/faulty_handoff.py"


def test_fault_injection_untyped_public_retrieval_callable_detected(tmp_path: Path) -> None:
    bad_ret = tmp_path / "apps_research" / "integrations" / "faulty_retrieval.py"
    bad_ret.parent.mkdir(parents=True, exist_ok=True)
    bad_ret.write_text(
        "def fetch_ranked_chunks(query: str):\n"
        "    return [query]\n",
        encoding="utf-8",
    )
    untyped = scan_untyped_public_retrieval_callables(tmp_path)
    assert len(untyped) == 1
    assert untyped[0]["callable"] == "fetch_ranked_chunks"


def test_fault_injection_broken_compiler_cache_slot_order_detected(tmp_path: Path) -> None:
    comp_file = tmp_path / "resume_graph_engine" / "src" / "apps_rg" / "prompt_assembly" / "compiler.py"
    comp_file.parent.mkdir(parents=True, exist_ok=True)
    comp_file.write_text(
        'CANONICAL_SLOT_ORDER = ("S0", "I0", "C0", "R0", "E0", "U0")\n'
        'CACHE_ALIGNED_SLOT_ORDER = ("S0", "I0", "C0", "R0", "E0", "U0")\n',
        encoding="utf-8",
    )
    res = verify_compiler_cache_alignment(tmp_path, quiet=True)
    assert res["passed"] is False
