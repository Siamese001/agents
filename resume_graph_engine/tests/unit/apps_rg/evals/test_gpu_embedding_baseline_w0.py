from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apps_rg.evals.gpu_embedding_baseline_w0 import (
    GpuEmbeddingBaselineError,
    build_workloads,
    canonical_sha256,
    percentile,
    resolve_output_path,
    validate_receipt,
)

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "tools/apps_rg_standalone/gpu_embedding_baseline_w0.py"


def test_workloads_bind_current_production_shapes_and_tracked_inputs() -> None:
    workloads = build_workloads(ROOT)

    assert [workload.workload_id for workload in workloads] == [
        "frozen_six_query",
        "whole_resume_eleven_section",
        "c02_section_retrieval_representative",
        "r1b_projection_representative",
    ]
    assert [len(workload.texts) for workload in workloads] == [6, 11, 7, 8]
    assert [workload.batch_size for workload in workloads] == [6, 11, 1, 64]
    assert workloads[0].source_bindings["query_manifest_sha256"] == (
        "4d8ce879651426c6d6103a72b3dda0354cca8de4aaffdec4f06c1fd6e6edd2c6"
    )
    assert workloads[1].source_bindings["ordered_section_ids"] == [
        "competencies",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
        "executive_summary",
        "headline",
    ]
    assert workloads[2].source_bindings["production_batch_shape"] == (
        "one_query_per_section"
    )
    assert workloads[3].source_bindings["batch_shape"] == (
        "intent_plus_seven_resume_chunks"
    )
    assert all(text.strip() for workload in workloads for text in workload.texts)


def test_receipt_output_is_confined_to_ignored_runtime_tree(tmp_path: Path) -> None:
    accepted = resolve_output_path(ROOT, Path(".runtime/w0-test"))
    assert accepted == (ROOT / ".runtime/w0-test/receipt.json").resolve()

    with pytest.raises(GpuEmbeddingBaselineError, match="must remain beneath"):
        resolve_output_path(ROOT, ROOT / "artifacts/apps_rg/c03/w0.json")
    with pytest.raises(GpuEmbeddingBaselineError, match="must remain beneath"):
        resolve_output_path(ROOT, tmp_path / "w0.json")


def test_percentile_uses_existing_nearest_rank_rule() -> None:
    values = [5.0, 1.0, 3.0, 2.0, 4.0]

    assert percentile(values, 0.50) == 3.0
    assert percentile(values, 0.95) == 5.0


def test_receipt_validator_enforces_no_authority_and_no_fallback() -> None:
    workload_ids = [
        "frozen_six_query",
        "whole_resume_eleven_section",
        "c02_section_retrieval_representative",
        "r1b_projection_representative",
    ]
    receipt = {
        "schema_version": "apps_rg.gpu_embedding_baseline_w0.v1",
        "status": "PASS",
        "source": {"harness": {"sha256": "a" * 64}},
        "scope": {
            "embedding_execution_measured": True,
            "retrieval_quality_measured": False,
            "qrels_read": False,
            "graph_projection_opened": False,
            "chroma_opened": False,
            "canonical_artifacts_written": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
        "runtime": {
            "local_files_only": True,
            "network_allowed": False,
            "fallback_allowed": False,
            "fallback_used": False,
            "gpu": {"device": "cuda:0"},
        },
        "model": {
            "model_id": "BAAI/bge-m3",
            "revision": "5617a9f61b028005a4858fdac845db406aefb181",
            "dimension": 1024,
            "normalization": "l2",
        },
        "workload_count": 4,
        "workloads": [
            {
                "workload_id": value,
                "text_count": 1,
                "batch_size": 1,
                "token_lengths": {"over_model_max_count": 0},
                "warm": {"repetitions": 3, "vector_digest_stable": True},
                "vector_proof": {
                    "dimension": 1024,
                    "finite": True,
                    "l2_normalized": True,
                },
            }
            for value in workload_ids
        ],
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)

    validate_receipt(receipt)
    receipt["scope"]["retrieval_quality_measured"] = True
    receipt["receipt_sha256"] = canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    with pytest.raises(GpuEmbeddingBaselineError, match="retrieval_quality_measured"):
        validate_receipt(receipt)


def test_standalone_cli_help_needs_no_preconfigured_pythonpath() -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["APPS_RG_SKIP_DOTENV_AUTOLOAD"] = "1"

    result = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "four governed apps_rg BGE-M3 workload shapes" in result.stdout


def test_runtime_contract_and_model_manifest_remain_offline_pinned() -> None:
    contract = json.loads(
        (
            ROOT / "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
        ).read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (
            ROOT
            / (
                "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
                "bge_m3_model_manifest.38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263.json"
            )
        ).read_text(encoding="utf-8")
    )

    assert contract["promoted_device"] == "cuda:0"
    assert contract["network_allowed"] is False
    assert contract["fallback_allowed"] is False
    assert manifest["revision"] == contract["model"]["revision"]
    assert manifest["dimension"] == 1024
