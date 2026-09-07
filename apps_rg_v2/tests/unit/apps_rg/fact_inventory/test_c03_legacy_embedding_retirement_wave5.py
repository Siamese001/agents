from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apps_rg.fact_inventory.c03_legacy_embedding_retirement_wave5 import (
    LegacyEmbeddingRetirementWave5Error,
    frozen_legacy_inventory,
    validate_retirement_contract,
    validate_retirement_marker,
    validate_w5_receipt,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import file_sha256
from apps_rg.fact_inventory.c03_skill_embedding_builder import (
    SkillEmbeddingBuildError,
    build_assertion_embedding_generation,
)
from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
    GraphSkillEmbeddingAllocationError,
    load_graph_skill_embedding_authority,
    load_legacy_graph_skill_embedding_retirement,
)

ROOT = Path(__file__).resolve().parents[4]
W4_COMMIT = "3e2fcaf47d37789688ad4fd6b2cc7ce2972423b4"
GRAPH_PATH = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
REGISTRY_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "graph_evidence_cluster_registry.v1.json"
)
W4_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave4_cluster_registry_receipt.json"
)
CONTRACT_PATH = ROOT / (
    "src/apps_rg/fact_inventory/" "c03_legacy_embedding_retirement_contract.v1.json"
)
MARKER_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "legacy_graph_skill_embedding_retirement.v1.json"
)
W5_RECEIPT_PATH = ROOT / (
    "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
    "wave5_legacy_artifact_retirement_receipt.json"
)
LEGACY_DIR = ROOT / "artifacts/apps_rg/c03/graph_skill_embeddings"
CLI_PATH = ROOT / ("tools/apps_rg_standalone/c03_legacy_embedding_retirement_wave5.py")


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _git_bytes(relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{W4_COMMIT}:{relative_path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def test_w5_contract_marker_and_receipt_are_valid_and_fail_closed() -> None:
    contract = _load(CONTRACT_PATH)
    marker = _load(MARKER_PATH)
    receipt = _load(W5_RECEIPT_PATH)

    validate_retirement_contract(contract)
    validate_retirement_marker(marker)
    validate_w5_receipt(receipt)
    assert marker["status"] == "RETIRED"
    assert marker["retired_lane"] == "one_vector_per_skill_assertion"
    assert marker["retired_artifact_count"] == 13
    assert marker["retired_total_size_bytes"] == 1_531_396
    assert set(marker["runtime_disposition"].values()) == {"FAIL_CLOSED_RETIRED"}
    assert receipt["scope"] == {
        "legacy_artifacts_retired": True,
        "claim_authority_expanded": False,
        "replacement_vectors_generated": False,
        "cluster_embedding_activation_created": False,
        "production_promotion_authorized": False,
    }


def test_w5_deletes_exact_w4_inventory_and_no_other_artifacts() -> None:
    w4_receipt = _load(W4_RECEIPT_PATH)
    marker = _load(MARKER_PATH)
    frozen = frozen_legacy_inventory(w4_receipt)

    assert len(frozen) == 13
    assert marker["retired_artifacts"] == [
        record
        | {
            "w4_git_blob_sha1": subprocess.run(
                ["git", "rev-parse", f"{W4_COMMIT}:{record['path']}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        }
        for record in frozen
    ]
    assert not LEGACY_DIR.exists()
    assert all(not (ROOT / record["path"]).exists() for record in frozen)


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json",
        (
            "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
            "graph_evidence_cluster_registry.v1.json"
        ),
        (
            "artifacts/apps_rg/c03/graph_evidence_cluster_embeddings/"
            "wave4_cluster_registry_receipt.json"
        ),
    ],
)
def test_w5_preserves_w4_graph_registry_and_receipt_bytes(relative_path: str) -> None:
    assert (ROOT / relative_path).read_bytes() == _git_bytes(relative_path)


def test_w5_runtime_loader_rejects_retired_lane_before_manifest_access(
    tmp_path: Path,
) -> None:
    marker_destination = tmp_path / MARKER_PATH.relative_to(ROOT)
    marker_destination.parent.mkdir(parents=True)
    shutil.copyfile(MARKER_PATH, marker_destination)
    malformed_manifest = tmp_path / (
        "artifacts/apps_rg/c03/graph_skill_embeddings/"
        "graph_skill_embedding_manifest.json"
    )
    malformed_manifest.parent.mkdir(parents=True)
    malformed_manifest.write_text("not-json", encoding="utf-8")

    loaded_marker = load_legacy_graph_skill_embedding_retirement(tmp_path)
    assert loaded_marker is not None
    with pytest.raises(GraphSkillEmbeddingAllocationError, match="lane is retired"):
        load_graph_skill_embedding_authority(tmp_path)


def test_w5_low_level_per_skill_builder_rejects_before_source_or_model_access(
    tmp_path: Path,
) -> None:
    with pytest.raises(SkillEmbeddingBuildError, match="generation is retired"):
        build_assertion_embedding_generation(
            repository_root=ROOT,
            graph_path=tmp_path / "missing-graph.json",
            candidate_fact_path=tmp_path / "missing-facts.json",
            base_resume_path=tmp_path / "missing-resume.json",
            model_path=tmp_path / "missing-model",
            output_dir=tmp_path / "must-not-be-created",
            device="cpu",
        )

    assert not (tmp_path / "must-not-be-created").exists()


def test_w5_marker_validator_rejects_tampering() -> None:
    marker = _load(MARKER_PATH)
    tampered = copy.deepcopy(marker)
    tampered["scope_guards"]["replacement_vectors_generated"] = True

    with pytest.raises(
        LegacyEmbeddingRetirementWave5Error,
        match="scope_guards",
    ):
        validate_retirement_marker(tampered)


def test_w5_receipt_opens_only_cluster_generation_wave() -> None:
    receipt = _load(W5_RECEIPT_PATH)

    assert receipt["wave_exit_gates"] == {
        "node_semantic_hardening": "PASS_W1",
        "edge_assertion_hardening": "PASS_W2",
        "authority_reconciliation": "PASS_W3",
        "cluster_registry_materialization": "PASS_W4",
        "legacy_artifact_retirement": "PASS_W5",
        "cluster_embedding_generation": "OPEN_W6",
        "production_promotion": "NOT_AUTHORIZED",
    }
    assert receipt["next_wave"] == (
        "C03_CLUSTER_EMBEDDING_W6_CLUSTER_VECTOR_GENERATION"
    )


def test_w5_cli_check_is_deterministic_and_non_mutating() -> None:
    graph_before = file_sha256(GRAPH_PATH)
    registry_before = file_sha256(REGISTRY_PATH)
    marker_before = file_sha256(MARKER_PATH)
    receipt_before = file_sha256(W5_RECEIPT_PATH)

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = json.loads(result.stdout)
    assert output["status"] == "PASS"
    assert output["deleted_artifact_count"] == 13
    assert output["remaining_legacy_file_count"] == 0
    assert output["replacement_vectors_generated"] is False
    assert file_sha256(GRAPH_PATH) == graph_before
    assert file_sha256(REGISTRY_PATH) == registry_before
    assert file_sha256(MARKER_PATH) == marker_before
    assert file_sha256(W5_RECEIPT_PATH) == receipt_before
