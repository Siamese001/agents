"""Wave 4 verification: judge calibration, single-pass repair, parallel SC, and C0 recovery reuse."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from apps_rg.config_root import get_provider_profiles_path

from apps_rg.runtime.assembly.coherence_prompt_compact import (
    MAX_COMPACT_CLAIM_CHARS,
    compact_evidence_packet_for_prompt,
    dispatch_coherence_judges,
    resolve_coherence_judge_effort,
)
from apps_rg.runtime.c0.c0_perf_sync_helpers import (
    RECOVERY_SEALED_C0_MANIFEST_ENV,
    collect_sealed_c0_manifest_for_lanes,
    compute_c0_input_identity,
    try_reuse_recovery_sealed_c0_bridge,
)
from apps_rg.runtime.section_model_limits import (
    runtime_limit_int,
    runtime_limit_mapping,
    runtime_limit_str,
)
from apps_rg.runtime.orchestration.ResumeRunRecoveryAgent import ResumeRunRecoveryAgent
from apps_rg.runtime.reasoning.bullet_pool_sync_helpers import execute_sc_paths_batch
from apps_rg.runtime.sections.executive_summary.stage_remediation import (
    should_skip_unchanged_summary_judge_refresh,
)
from apps_rg.runtime.sections.headline_repair_policy import (
    CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS,
    CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS,
    resolve_content_signal_repair_max_attempts,
)


def test_wave4_judge_effort_and_compact_caps_calibrated() -> None:
    assert runtime_limit_str("judge.gemini_proof_thinking_level") == "high"
    assert runtime_limit_str("judge.openai_proof_reasoning_effort") == "high"
    assert runtime_limit_int("judge.x1d_max_output_tokens") == 4096
    assert runtime_limit_int("judge.x1d_max_output_tokens_hard_cap") == 8192
    assert runtime_limit_int("judge.x1d_max_attempts") == 3

    enhanced = runtime_limit_mapping("judge.runtime_profiles.enhanced_reasoning")
    assert int(enhanced["max_output_tokens"]) == 8192
    assert int(enhanced["max_output_tokens_hard_cap"]) == 8192
    assert int(enhanced["max_attempts"]) == 3

    assert resolve_coherence_judge_effort("high") == "high"
    assert resolve_coherence_judge_effort(None) == "high"
    assert resolve_coherence_judge_effort("low") == "low"


def test_wave4_coherence_compaction_and_daemon_panel_dispatch() -> None:
    long_claim = "X" * 400
    compacted = compact_evidence_packet_for_prompt(
        {
            "schema": "s1",
            "sections": [
                {
                    "section_id": "executive_summary",
                    "selected_candidate_facts": [{"fact_id": "f1", "claim_text": long_claim}],
                    "graph_claim_bindings": [{"fact_ids": ["f1"], "binding_status": "BOUND"}],
                }
            ],
        }
    )
    claim_out = compacted["sections"][0]["selected_candidate_facts"][0]["claim_text"]
    assert len(claim_out) == MAX_COMPACT_CLAIM_CHARS

    barrier = threading.Barrier(2, timeout=3.0)
    thread_daemons: list[bool] = []

    def _eval_fn(key: str) -> str:
        thread_daemons.append(threading.current_thread().daemon)
        barrier.wait()
        return f"ok:{key}"

    t0 = time.monotonic()
    out = dispatch_coherence_judges(["p1", "p2"], mode="live", evaluate_fn=_eval_fn)
    elapsed = time.monotonic() - t0
    assert out == ["ok:p1", "ok:p2"]
    assert all(thread_daemons)
    assert elapsed < 3.0


def test_wave4_skip_unchanged_summary_judge_refresh() -> None:
    import hashlib

    text = "Executive AI Architect leading enterprise platform delivery."
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    judges = [SimpleNamespace(evaluator_mode="MODEL_BACKED"), SimpleNamespace(evaluator_mode="MODEL_BACKED")]

    assert should_skip_unchanged_summary_judge_refresh(
        judges, display_text=f"  {text}\n", prior_display_sha256=sha
    ) is True
    assert should_skip_unchanged_summary_judge_refresh(
        judges, display_text="Modified executive summary text.", prior_display_sha256=sha
    ) is False
    assert should_skip_unchanged_summary_judge_refresh(
        [SimpleNamespace(evaluator_mode="MOCKED")], display_text=text, prior_display_sha256=sha
    ) is False


def test_wave4_live_headline_repair_capped_at_single_pass() -> None:
    assert CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS == 1
    assert CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS == 3
    assert resolve_content_signal_repair_max_attempts({"APPS_RG_PRODUCTION_RUN": "1", "PYTEST_CURRENT_TEST": "t"}) == 1
    assert resolve_content_signal_repair_max_attempts({"APPS_RG_WHOLE_RUN_ENVELOPE": "1", "PYTEST_CURRENT_TEST": "t"}) == 1
    assert resolve_content_signal_repair_max_attempts({}) == 1
    assert resolve_content_signal_repair_max_attempts({"PYTEST_CURRENT_TEST": "offline_rung"}) == 3


def test_wave4_execute_sc_paths_batch_runs_all_paths_concurrently() -> None:
    barrier = threading.Barrier(4, timeout=3.0)
    starts: list[float] = []

    def _run_one(offset: int, temp: float) -> SimpleNamespace:
        starts.append(time.monotonic())
        barrier.wait()
        return SimpleNamespace(path_index=offset, temperature=temp)

    paths = execute_sc_paths_batch(
        [0.35, 0.42, 0.48, 0.55],
        execution_mode="parallel",
        max_parallel=4,
        thread_prefix="test_sc",
        section_lane="unify_bullets",
        run_fn=_run_one,
        zero_output_timeout_fn=lambda _p: False,
    )
    assert [p.path_index for p in paths] == [0, 1, 2, 3]
    assert max(starts) - min(starts) < 0.5


def test_wave4_recovery_reuses_sealed_c0_evidence_and_invalidates_on_jd_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "full_resume_test"
    src_lane = run_dir / "modular_r4" / "sections" / "headline" / "real" / "r1"
    src_lane.mkdir(parents=True)

    pool = SimpleNamespace(
        section="headline",
        allowed_fact_ids_ordered=["f_hl_1"],
        allowed_fact_ids={"f_hl_1"},
        selected_fact_plan={"facts": [{"fact_id": "f_hl_1", "claim_text": "Scaled AI platform"}]},
        facts=[{"fact_id": "f_hl_1", "claim_text": "Scaled AI platform"}],
        proof_pool_metadata={},
        srfs_present=False,
        srfs_ref="",
    )
    jd_text = "Partner Applied AI Architecture role."
    ident = compute_c0_input_identity(
        section_id="headline",
        target_role="Applied AI Lead",
        jd_text=jd_text,
        pool=pool,
    )
    bridge_doc = {
        "schema_version": "c0_fec_bridge_v1",
        "section_id": "headline",
        "c07_handoff_safe": True,
        "c0_input_identity": ident,
        "final_evidence_contract_snapshot": {
            "request_id": "req_1",
            "run_id": "r1",
            "final_evidence_digest": "sha256:abc",
            "support_status": "SUPPORTED",
            "evidence_item_count": 1,
            "allowed_fact_ids": ["f_hl_1"],
        },
    }
    (src_lane / "c0_evidence_room_receipt.json").write_text(
        json.dumps({"bridge_doc": bridge_doc}), encoding="utf-8"
    )
    (src_lane / "final_evidence_contract.json").write_text(
        json.dumps(bridge_doc), encoding="utf-8"
    )

    manifest_lanes = collect_sealed_c0_manifest_for_lanes(
        run_dir,
        ["headline"],
        raw_request={"target_role": "Applied AI Lead", "job_description_text": jd_text},
    )
    assert "headline" in manifest_lanes
    manifest_file = run_dir / "x3_recovery_sealed_c0_manifest.json"
    manifest_file.write_text(json.dumps({"schema_version": 1, "lanes": manifest_lanes}), encoding="utf-8")
    monkeypatch.setenv(RECOVERY_SEALED_C0_MANIFEST_ENV, str(manifest_file))

    patch_lane_dir = run_dir / "modular_r4" / "sections" / "headline" / "real" / "r2_patch"
    runtime_payload: dict[str, object] = {}
    reused = try_reuse_recovery_sealed_c0_bridge(
        artifact_dir=patch_lane_dir,
        section_id="headline",
        target_role="Applied AI Lead",
        jd_text=jd_text,
        pool=pool,
        runtime_payload=runtime_payload,
    )
    assert reused is not None
    assert reused.section_id == "headline"
    assert (patch_lane_dir / "c0_recovery_reuse_receipt.json").is_file()
    assert runtime_payload["fec_bridge_ref"] == "final_evidence_contract.json"

    missed = try_reuse_recovery_sealed_c0_bridge(
        artifact_dir=run_dir / "modular_r4" / "sections" / "headline" / "real" / "r3_miss",
        section_id="headline",
        target_role="Applied AI Lead",
        jd_text="CHANGED JD TEXT",
        pool=pool,
        runtime_payload={},
    )
    assert missed is None


def test_wave4_cli_supports_no_cache_and_fresh_flags() -> None:
    from resume_engine.cli import _build_parser, _normalize_argv

    parser = _build_parser()
    args_nc = parser.parse_args(_normalize_argv(["run", "--no-cache", "--json"]))
    assert args_nc.no_cache is True
    assert args_nc.json is True

    args_fresh = parser.parse_args(_normalize_argv(["--fresh"]))
    assert args_fresh.action == "run"
    assert args_fresh.no_cache is True
    assert ResumeRunRecoveryAgent is not None


def test_inprocess_graph_sqlite_lock_serializes_concurrent_ensure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time
    from apps_rg.fact_inventory.augmented_skills_graph_sqlite import inprocess_graph_sqlite_lock
    from apps_rg.runtime import c03_graph_sqlite_context as ctx_mod
    from apps_rg.runtime.c0.c03_errors import C03GraphProjectionUnavailableError

    db_file = tmp_path / "augmented_skills_graph.sqlite"
    build_count = 0

    def fake_require(root: Path, path: Path | None = None) -> Path:
        target = path or db_file
        if not target.is_file():
            raise C03GraphProjectionUnavailableError("missing")
        return target

    def fake_materialize(**kwargs: object) -> dict[str, object]:
        nonlocal build_count
        time.sleep(0.03)
        build_count += 1
        db_file.write_bytes(b"sqlite")
        return {"sqlite_db_path": str(db_file)}

    monkeypatch.setattr(ctx_mod, "require_c03_graph_sqlite", fake_require)
    monkeypatch.setattr(ctx_mod, "materialize_augmented_skills_graph_sqlite", fake_materialize)

    results: list[Path] = []
    threads = [
        threading.Thread(target=lambda: results.append(ctx_mod.ensure_c03_graph_sqlite(tmp_path, db_file)))
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    assert len(results) == 5
    assert build_count == 1
    assert inprocess_graph_sqlite_lock(db_file) is inprocess_graph_sqlite_lock(db_file)


def test_wave4_compact_overlong_headline_and_ledger() -> None:
    from apps_rg.runtime.sections.headline_lane import (
        headline_resume_native_clarity_report,
        normalize_parsed_output,
    )
    from apps_rg.runtime.validators.headline_x2 import headline_word_count

    overlong = (
        "SVP Engineering | Partner Ecosystem Accelerators Platform | "
        "Governed Agentic Platform Architecture | Distributed Lakehouse Infrastructure Systems"
    )
    assert headline_word_count(overlong) == 14
    parsed = {
        "headline_line": overlong,
        "claim_ledger": [
            {"claim_text": "Partner Ecosystem Accelerators Platform", "source_fact_ids": ["reb_ibm_001"]},
            {"claim_text": "Governed Agentic Platform Architecture", "source_fact_ids": ["reb_unify_001"]},
            {"claim_text": "Distributed Lakehouse Infrastructure Systems", "source_fact_ids": ["reb_unify_002"]},
        ],
        "jd_alignment": {"jd_used_as_proof": False, "briefing_used_as_proof": False},
        "self_check": {"word_count": 13},
    }
    norm = normalize_parsed_output(
        parsed,
        {"target_company": "Anthropic", "selected_fact_plan": {"section_id": "headline", "selection_method": "graph"}},
        {"reb_ibm_001", "reb_unify_001", "reb_unify_002"},
        overlong,
    )
    assert norm is not None
    expected = (
        "SVP Engineering | Partner Ecosystem Accelerators | "
        "Governed Agentic Platform Architecture | Distributed Lakehouse Infrastructure"
    )
    assert norm["headline_line"] == expected
    assert headline_word_count(norm["headline_line"]) == 12
    assert norm["self_check"]["word_count"] == 12
    assert norm["self_check"]["word_count_in_range"] is True
    assert headline_resume_native_clarity_report(norm["headline_line"])["opaque_segments"] == []
    assert [r["claim_text"] for r in norm["claim_ledger"]] == [
        "Partner Ecosystem Accelerators",
        "Governed Agentic Platform Architecture",
        "Distributed Lakehouse Infrastructure",
    ]
    assert [r["source_fact_ids"] for r in norm["claim_ledger"]] == [
        ["reb_ibm_001"],
        ["reb_unify_001"],
        ["reb_unify_002"],
    ]

    from apps_rg.runtime.sections.headline_repair_policy import (
        deterministic_clarity_trim_enabled,
        find_valid_3word_clarity_trim,
    )

    assert deterministic_clarity_trim_enabled({"APPS_RG_PRODUCTION_RUN": "1", "PYTEST_CURRENT_TEST": "t"}) is True
    assert deterministic_clarity_trim_enabled({"PYTEST_CURRENT_TEST": "offline"}) is False
    live_13w = (
        "SVP Engineering | Partner Cloud Ecosystem | Governed Agentic Platform Architecture | "
        "Distributed Databricks Lakehouse Infrastructure"
    )
    trimmed = find_valid_3word_clarity_trim(
        headline_line=live_13w,
        parsed={
            "headline_line": live_13w,
            "claim_ledger": [
                {"claim_text": "Partner Cloud Ecosystem", "source_fact_ids": ["reb_slalom"]},
                {"claim_text": "Governed Agentic Platform Architecture", "source_fact_ids": ["reb_unify_1"]},
                {"claim_text": "Distributed Databricks Lakehouse Infrastructure", "source_fact_ids": ["reb_unify_2"]},
            ],
        },
        runtime_payload={},
        allowed_fact_ids={"reb_slalom", "reb_unify_1", "reb_unify_2"},
        clarity_report_fn=headline_resume_native_clarity_report,
    )
    assert trimmed is not None
    cand_line, fixed_parsed, new_clarity, _, _ = trimmed
    assert cand_line == (
        "SVP Engineering | Partner Cloud Ecosystem | Governed Agentic Platform Architecture | "
        "Distributed Lakehouse Infrastructure"
    )
    assert new_clarity["pass"] is True
    assert fixed_parsed["claim_ledger"][2]["claim_text"] == "Distributed Lakehouse Infrastructure"
