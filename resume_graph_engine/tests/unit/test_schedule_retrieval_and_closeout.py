"""Wave 3 verification: 3-stage schedule, 6-worker cap, shared retrieval, and single-pass closeout."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
import time
import zipfile

import pytest

from apps_rg.l2_recipe.modular_resume_generation import ModularResumeProfile
from apps_rg.runtime.c0.c0_perf_sync_helpers import (
    c06_bindings_changed,
    encode_queries_with_shared_cache,
    get_or_open_verified_collection,
    get_or_scan_fact_vectors_collection,
    reset_c0_shared_retrieval_caches_for_tests,
)
from apps_rg.runtime.c0.sparse_sidecar import AppsRgSparseIndex, upsert_documents
from apps_rg.runtime.closeout_single_pass import REVIEW_BUNDLE_MANIFEST_FILENAME
from apps_rg.runtime.evaluation_manifest import (
    EXPECTED_LANES,
    emit_candidate_evaluation_manifest,
    validate_candidate_evaluation_manifest,
)
from apps_rg.runtime.full_resume_review_bundle import (
    REVIEW_BUNDLE_FILENAME,
    REVIEW_INDEX_FILENAME,
    emit_full_resume_review_bundle,
)
from apps_rg.runtime.orchestration.managed_section_lane_dispatcher import (
    dispatch_phase1_lanes_managed,
)
from apps_rg.runtime.orchestration.section_lane_concurrency import (
    assert_section_dag_wave_order,
    build_phase1_waves,
    load_section_dag_manifest,
    resolve_max_parallel,
    section_dag_dependencies,
)
from apps_rg.runtime.orchestration.section_lane_executor import LaneExecutionContext
from apps_rg.runtime.product_artifact_privacy import (
    REDACTION_RECEIPT,
    redact_product_diagnostics,
)


def test_three_stage_schedule_and_six_worker_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("APPS_RG_PHASE1_MAX_PARALLEL", raising=False)
    load_section_dag_manifest.cache_clear()
    manifest = load_section_dag_manifest()
    assert_section_dag_wave_order(manifest)

    waves = build_phase1_waves()
    assert len(waves) == 3, f"expected 3-stage schedule, got {len(waves)}: {waves}"
    assert waves[0].wave_id == 0
    assert waves[0].max_parallel == 6
    assert ModularResumeProfile().phase1_max_parallel == 6
    assert resolve_max_parallel() == 6

    assert set(waves[0].lanes) == {
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
    }
    assert set(waves[1].lanes) == {
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
    }
    assert waves[2].lanes == ("executive_summary", "headline")
    assert waves[2].max_parallel == 2

    deps = section_dag_dependencies()
    assert "executive_summary" not in deps["headline"]

    # Prove all 5 Stage 0 lanes start concurrently within <2.0s and Stage 2 runs headline with summary
    start_times: dict[str, float] = {}
    end_times: dict[str, float] = {}
    lock = threading.Lock()
    stage0_barrier = threading.Barrier(5, timeout=2.0)
    stage2_barrier = threading.Barrier(2, timeout=2.0)
    t0 = time.monotonic()

    def _runner(**kwargs: object) -> dict[str, object]:
        lane = str(kwargs.get("section") or "")
        with lock:
            start_times[lane] = time.monotonic() - t0
        if lane in waves[0].lanes:
            stage0_barrier.wait()
        elif lane in ("executive_summary", "headline"):
            stage2_barrier.wait()
        else:
            time.sleep(0.02)
        with lock:
            end_times[lane] = time.monotonic() - t0
        return {"section": lane, "exit_status": "ok", "x3_disposition": "X3D_ALLOW_FINISH"}

    ctx = LaneExecutionContext(
        sections_root=str(tmp_path / "lanes"),
        target_company="ExampleCorp",
        target_role="Principal AI Architect",
        job_description_ref="",
        job_description_text="Build governed multi-agent systems.",
        manual_brief="",
        lane_provider="mock_provider",
        lane_x1d_judges="",
        lane_mock_judges=True,
    )
    results = dispatch_phase1_lanes_managed(
        EXPECTED_LANES,
        ctx,
        max_parallel=6,
        parallel=True,
        dispatch_fn=_runner,
    )
    assert set(results.keys()) == set(EXPECTED_LANES)
    stage0_span = max(start_times[lane] for lane in waves[0].lanes) - min(
        start_times[lane] for lane in waves[0].lanes
    )
    assert stage0_span < 2.0
    # Headline must start before executive_summary finishes (co-scheduled in Stage 2)
    assert start_times["headline"] <= end_times["executive_summary"]


def test_shared_retrieval_handles_and_single_flight_query_vectors(tmp_path: Path) -> None:
    reset_c0_shared_retrieval_caches_for_tests()

    encode_calls = 0
    encode_lock = threading.Lock()

    class _FakeEmbeddingRuntime:
        key = "bge_local:/models/bge-m3:cpu:float32"

        def encode(self, texts: list[str], *, batch_size: int = 8) -> list[list[float]]:
            nonlocal encode_calls
            time.sleep(0.05)
            with encode_lock:
                encode_calls += 1
            return [[0.25, 0.75, float(len(t) % 7)] for t in texts]

    open_calls = 0
    parity_calls = 0
    scan_calls = 0
    handle_lock = threading.Lock()

    class _FakeCollection:
        metadata = {"hnsw:space": "cosine"}

        def get(self, limit: int = 100, include: list[str] | None = None) -> dict[str, object]:
            nonlocal scan_calls
            with handle_lock:
                scan_calls += 1
            return {
                "metadatas": [
                    {
                        "source_document_id": "bul_unify_1",
                        "embedding_model_id": "BAAI/bge-m3",
                        "embedding_dim": "1024",
                        "source_class": "project_evidence",
                        "tier": "canonical",
                    }
                ]
            }

    fake_client = object()
    fake_collection = _FakeCollection()

    def _ensure_client(_path: str) -> object:
        return fake_client

    def _open_col(_client: object, _name: str) -> _FakeCollection:
        nonlocal open_calls
        with handle_lock:
            open_calls += 1
        return fake_collection

    def _assert_parity(_col: object) -> None:
        nonlocal parity_calls
        with handle_lock:
            parity_calls += 1

    sparse_dir = tmp_path / "sparse"
    upsert_documents(
        "fact_vectors",
        [
            {
                "id": f"fact_{idx}",
                "document": f"Architected governed enterprise AI platform outcome {idx}",
                "metadata": {"source_class": "project_evidence"},
            }
            for idx in range(25)
        ],
        sparse_dir=sparse_dir,
    )

    emb_runtime = _FakeEmbeddingRuntime()
    shared_jd = "Enterprise AI Architecture role requiring RAG, governance, and distributed systems."
    chroma_dir = tmp_path / "chromadb"
    chroma_dir.mkdir()

    def _lane_retrieval(lane_id: str) -> float:
        started = time.perf_counter()
        col = get_or_open_verified_collection(
            chroma_path=str(chroma_dir),
            collection_name="fact_vectors",
            ensure_client_fn=_ensure_client,
            open_collection_fn=_open_col,
            assert_parity_fn=_assert_parity,
        )
        get_or_scan_fact_vectors_collection(
            chroma_path=str(chroma_dir),
            collection=col,
            count=1,
            limit=10,
            metadata_counter_fn=lambda metas, key, fallback_key="": {str(m.get(key, "")): 1 for m in metas},
        )
        vecs = encode_queries_with_shared_cache(
            embedding_runtime=emb_runtime,
            queries=[shared_jd],
            batch_size_fn=lambda _wid, n: n,
        )
        assert len(vecs) == 1 and len(vecs[0]) == 3
        hits = AppsRgSparseIndex("fact_vectors", sparse_dir=sparse_dir).search(
            "governed enterprise platform", top_k=5
        )
        assert hits, f"expected sparse hits for {lane_id}"
        return time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=6) as pool:
        durations = list(pool.map(_lane_retrieval, EXPECTED_LANES))

    assert encode_calls == 1, f"expected single-flight JD query encode across 11 lanes, got {encode_calls}"
    assert open_calls == 1
    assert parity_calls == 1
    assert scan_calls == 1
    assert max(durations) < 3.5


def test_c06_skip_unchanged_bindings() -> None:
    initial_bindings = [{"fact_id": "f1", "graph_support_strength": "DIRECT"}]
    assert c06_bindings_changed(
        initial_bindings,
        {"bindings": [{"fact_id": "f1", "graph_support_strength": "DIRECT"}]},
        {"attempted": False, "pass": True},
    ) is False
    assert c06_bindings_changed(
        initial_bindings,
        {"bindings": [{"fact_id": "f1", "graph_support_strength": "DIRECT"}]},
        {"attempted": True, "pass": True},
    ) is False
    assert c06_bindings_changed(
        initial_bindings,
        {"bindings": [{"fact_id": "f1", "graph_support_strength": "DIRECT"}, {"fact_id": "f2"}]},
        {"attempted": True, "pass": True},
    ) is True


def test_single_pass_closeout_hashing_redaction_and_opt_in_zip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_root = tmp_path / "full_resume_wave3"
    run_root.mkdir()

    (run_root / "spine_run_manifest.json").write_text('{"schema_version":"v1"}\n', encoding="utf-8")
    (run_root / "e2e_stage_ledger.json").write_text('{"schema_version":"v2"}\n', encoding="utf-8")
    (run_root / "runtime_exhaust_bundle.json").write_text('{"schema_version":"v1"}\n', encoding="utf-8")
    (run_root / "runtime_identity_envelope.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "payload": {"parent_run_id": "p_wave3", "child_run_id": "c_wave3"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_root / "outputs").mkdir()
    (run_root / "outputs" / "generated_resume.json").write_text(
        '{"schema_version":"apps_rg.generated_resume.v1","ok":true}\n', encoding="utf-8"
    )
    (run_root / "FINAL_RESUME_OUTPUT.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "final_resume_json": {"relpath": "outputs/generated_resume.json"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for fname in (
        "FINAL_RESUME_OUTPUT.txt",
        "RUN_BUNDLE_INDEX.json",
        "e2e_preflight_product_entry_receipt.json",
        "apps_rg_product_authorization_receipt.json",
        "apps_rg_whole_run_exit_review_packet.json",
        "x3_disposition_receipt.json",
        "u0_receipt.json",
        "route_contract.json",
        "full_run_section_status.json",
        "commit_request.json",
        "uwg_validation_receipt.json",
        "uwg_commit_receipt.json",
    ):
        (run_root / fname).write_text(
            '{"schema_version":"v1"}\n' if fname.endswith(".json") else "RESUME TEXT\n",
            encoding="utf-8",
        )
    asm_dir = run_root / "modular_r4" / "final_resume_assembly"
    asm_dir.mkdir(parents=True)
    (asm_dir / "cross_section_x2_gate_outputs.json").write_text('{"schema_version":"v1"}\n', encoding="utf-8")
    (asm_dir / "final_resume_x2_gate_outputs.json").write_text('{"schema_version":"v1"}\n', encoding="utf-8")

    for lane_id in EXPECTED_LANES:
        ldir = run_root / "lanes" / lane_id
        ldir.mkdir(parents=True)
        (ldir / "l2_output.json").write_text(
            json.dumps({"schema_version": "v1", "section_attempt_id": f"att_{lane_id}"}) + "\n",
            encoding="utf-8",
        )
        for req_file in (
            "runtime_payload.json",
            "x2_gate_outputs.json",
            "x1d_llm_judge_outputs.json",
            "x3_disposition.json",
            "l6_shadow_eval_package.json",
        ):
            (ldir / req_file).write_text('{"schema_version":"v1"}\n', encoding="utf-8")
        (ldir / "compiled_prompt.txt").write_text(f"raw prompt {lane_id}", encoding="utf-8")
        (ldir / "provider_request.json").write_text(
            json.dumps(
                {
                    "endpoint": "https://api.example.com",
                    "auth_header": "Bearer secret_token_1234567890abcdefghij",
                    "messages": [{"content": "confidential prompt"}],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.delenv("APPS_RG_BUILD_REVIEW_ZIP", raising=False)
    t0 = time.perf_counter()
    redaction_path = redact_product_diagnostics(run_root)
    cand_manifest = emit_candidate_evaluation_manifest(run_root)
    zip_result = emit_full_resume_review_bundle(run_root)
    elapsed = time.perf_counter() - t0

    assert elapsed < 4.0, f"expected single-pass closeout <4.0s, took {elapsed:.3f}s"
    assert redaction_path == run_root / REDACTION_RECEIPT
    assert cand_manifest.is_file()
    _payload, manifest_errors = validate_candidate_evaluation_manifest(run_root)
    assert manifest_errors == []

    # Default whole-run closeout skips review_bundle.zip and writes lightweight manifest
    assert zip_result is None
    assert not (run_root / REVIEW_BUNDLE_FILENAME).exists()
    assert (run_root / REVIEW_INDEX_FILENAME).is_file()
    assert (run_root / REVIEW_BUNDLE_MANIFEST_FILENAME).is_file()

    sample_req = json.loads(
        (run_root / "lanes" / "headline" / "provider_request.json").read_text(encoding="utf-8")
    )
    assert sample_req["messages"]["redacted"] is True
    assert "secret_token_1234567890abcdefghij" not in json.dumps(sample_req)

    # Opt-in zip mode builds review_bundle.zip cleanly
    monkeypatch.setenv("APPS_RG_BUILD_REVIEW_ZIP", "1")
    built_zip = emit_full_resume_review_bundle(run_root)
    assert built_zip == run_root / REVIEW_BUNDLE_FILENAME
    assert built_zip.is_file()
    with zipfile.ZipFile(built_zip) as zf:
        assert REVIEW_INDEX_FILENAME in zf.namelist()
