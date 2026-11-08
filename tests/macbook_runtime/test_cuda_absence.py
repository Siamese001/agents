"""Pillar 1: Zero CUDA Invariant on Local MacBook Runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
import torch

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_torch_cuda_is_not_available() -> None:
    """Verifies that CUDA is physically absent and not required by torch."""
    assert torch.cuda.is_available() is False, "CUDA must not be active on Apple Silicon MacBook"
    assert torch.cuda.device_count() == 0, "CUDA device count must be 0"


def test_cuda_env_vars_not_required() -> None:
    """Verifies that default execution environment has no mandatory CUDA environment variables."""
    assert os.getenv("CUDA_VISIBLE_DEVICES") != "0", "CUDA_VISIBLE_DEVICES should not force device 0"


def test_bge_runtime_key_does_not_default_to_cuda_on_darwin(tmp_path: Path) -> None:
    """Verifies that resolve_bge_runtime_key on Darwin resolves to mps or cpu, never hardcoded cuda:0."""
    from apps_rg.runtime.bge_embedding import resolve_bge_runtime_key

    model_path = Path("artifacts/models/BAAI/bge-m3")
    if not model_path.is_dir():
        model_path = tmp_path / "mock_bge"
        model_path.mkdir(parents=True, exist_ok=True)

    key = resolve_bge_runtime_key(model_path=model_path)
    assert not key.device.startswith("cuda"), f"Expected non-CUDA device on Darwin, got: {key.device}"
    assert key.device in {"mps", "cpu", "mps:0"}


def test_fact_vector_hydration_allows_macos_without_cuda(tmp_path: Path) -> None:
    """Verifies that validate_fact_vector_hydration_runtime succeeds on macOS without requiring CUDA."""
    from apps_rg.runtime.fact_vectors_bootstrap import validate_fact_vector_hydration_runtime

    model_path = Path("artifacts/models/BAAI/bge-m3")
    if not model_path.is_dir():
        model_path = tmp_path / "mock_bge"
        model_path.mkdir(parents=True, exist_ok=True)

    receipt = validate_fact_vector_hydration_runtime(
        embedding_model_path=str(model_path),
        require_cuda=False,
    )
    assert "torch_cuda_unavailable" not in receipt["reasons"]
    assert not any(r.startswith("hydration_device_not_cuda") for r in receipt["reasons"])
    if model_path.is_dir() and torch.backends.mps.is_available():
        assert receipt["status"] == "PASS"


def test_config_schemas_support_mps_device() -> None:
    """Verifies that certification veto policy schemas allow 'mps' in device enum."""
    repo_root = Path(__file__).resolve().parents[2]
    schema_paths = [
        repo_root / "config" / "certification" / "veto_policy_schema.json",
        repo_root / "resume_graph_engine" / "config" / "certification" / "veto_policy_schema.json",
    ]
    for p in schema_paths:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            dev_prop = (
                data.get("properties", {})
                .get("cross_encoder_config", {})
                .get("properties", {})
                .get("device", {})
            )
            enum_vals = dev_prop.get("enum", [])
            assert "mps" in enum_vals, f"Schema {p} missing 'mps' in device enum: {enum_vals}"


def test_pytest_markers_modernized() -> None:
    """Verifies that pytest.ini gpu marker includes local acceleration (MPS/Metal)."""
    repo_root = Path(__file__).resolve().parents[2]
    pytest_ini = (repo_root / "pytest.ini").read_text(encoding="utf-8")
    assert "mps" in pytest_ini.lower() or "apple silicon" in pytest_ini.lower() or "metal" in pytest_ini.lower(), (
        "pytest.ini gpu marker should mention MPS, Metal, or Apple Silicon"
    )
