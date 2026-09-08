from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from apps_rg.evals.gpu_embedding_baseline_w0 import canonical_sha256
from apps_rg.runtime.gpu_embedding_environment_w1 import (
    GpuEmbeddingEnvironmentError,
    build_preflight_receipt,
    evaluate_observations,
    load_environment_contract,
    validate_preflight_receipt,
)

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = ROOT / "tools/apps_rg_standalone/gpu_embedding_environment_w1.json"
LOCK_PATH = ROOT / "tools/apps_rg_standalone/gpu_embedding_environment_w1.lock.txt"
CLI_PATH = ROOT / "tools/apps_rg_standalone/gpu_embedding_preflight_w1.py"


def _passing_observations(contract: dict) -> dict:
    locked = {
        "sentence-transformers": "5.2.3",
        "transformers": "5.2.0",
    }
    critical = {
        name: {
            "available": True,
            "version": binding["version"],
            "payload_sha256": binding["payload_sha256"],
            "module_relative_path": binding["module_relative_path"],
        }
        for name, binding in contract["critical_distributions"].items()
    }
    source = contract["apps_rg_source"]
    gpu = contract["gpu"]
    runtime = contract["embedding_runtime"]
    model = contract["model"]
    return {
        "python": {
            "implementation": contract["platform"]["python_implementation"],
            "version": contract["platform"]["python_version"],
            "operating_system": contract["platform"]["operating_system"],
            "machine": contract["platform"]["machine"],
        },
        "locked_packages": locked,
        "installed_locked_packages": dict(locked),
        "critical_distributions": critical,
        "apps_rg_source": {
            "available": True,
            "source_relative_path": source["source_relative_path"],
            "tracked_or_untracked_source_changes": [],
        },
        "cuda": {
            "available": True,
            "device": runtime["device"],
            "torch_cuda_runtime": runtime["cuda_runtime"],
            "torch_arch_list": [runtime["compiled_architecture_required"]],
            "name": gpu["name"],
            "compute_capability": gpu["compute_capability"],
            "driver_version": gpu["minimum_driver_version"],
            "total_memory_mib": gpu["minimum_total_memory_mib"],
            "free_memory_mib": gpu["minimum_free_memory_mib"],
            "kernel_probe_checksum": 14.0,
        },
        "model": {
            "available": True,
            "model_id": model["model_id"],
            "revision": model["revision"],
            "dimension": model["dimension"],
            "normalization": model["normalization"],
            "artifact_sha256": model["artifact_sha256"],
        },
        "offline_environment": dict(contract["offline_environment"]),
    }


def test_contract_binds_lock_runtime_model_and_direct_hashed_torch_wheel() -> None:
    contract = load_environment_contract(ROOT)
    lock = LOCK_PATH.read_text(encoding="utf-8")

    assert contract["status"] == "CONTROL_LOCKED"
    assert contract["install"]["torch_wheel_size_bytes"] == 2796931922
    assert contract["install"]["torch_wheel_sha256"] == (
        "674f46f71f9175edd8ba9db9c8c1b20b3e434dc48a00a889acd4334fee9ff236"
    )
    assert contract["install"]["torch_wheel_url"] in lock
    assert f"#sha256={contract['install']['torch_wheel_sha256']}" in lock
    assert contract["embedding_runtime"]["network_allowed"] is False
    assert contract["embedding_runtime"]["fallback_allowed"] is False


def test_contract_rejects_lock_digest_drift(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    bad_lock = tmp_path / "bad.lock.txt"
    bad_lock.write_text("torch==0\n", encoding="utf-8")
    contract["install"]["lock_path"] = bad_lock.as_posix()
    unsigned = dict(contract)
    unsigned.pop("contract_sha256")
    contract["contract_sha256"] = canonical_sha256(unsigned)

    with pytest.raises(GpuEmbeddingEnvironmentError, match="escapes repository"):
        # A lock outside the repository is rejected before its digest is considered.
        from apps_rg.runtime import gpu_embedding_environment_w1 as module

        original = module.CONTRACT_PATH
        local_contract = ROOT / ".runtime/w1-test-contract.json"
        local_contract.parent.mkdir(parents=True, exist_ok=True)
        local_contract.write_text(json.dumps(contract), encoding="utf-8")
        try:
            module.CONTRACT_PATH = local_contract.relative_to(ROOT)
            load_environment_contract(ROOT)
        finally:
            module.CONTRACT_PATH = original


@pytest.mark.parametrize(
    ("mutate", "expected_issue"),
    [
        (
            lambda value: value["installed_locked_packages"].__setitem__(
                "transformers", "0"
            ),
            "LOCKED_PACKAGE_MISMATCH::transformers",
        ),
        (
            lambda value: value["critical_distributions"]["torch"].__setitem__(
                "payload_sha256", "0" * 64
            ),
            "CRITICAL_DISTRIBUTION_PAYLOAD_SHA256::torch",
        ),
        (
            lambda value: value["apps_rg_source"].__setitem__(
                "source_relative_path", "src/apps_rg/not_init.py"
            ),
            "APP_SOURCE_SOURCE_RELATIVE_PATH_MISMATCH",
        ),
        (
            lambda value: value["apps_rg_source"].__setitem__(
                "tracked_or_untracked_source_changes", [" M src/apps_rg/x.py"]
            ),
            "APP_SOURCE_TREE_DIRTY",
        ),
        (
            lambda value: value["cuda"].__setitem__("torch_arch_list", ["sm_90"]),
            "CUDA_COMPILED_ARCHITECTURE_MISSING",
        ),
        (
            lambda value: value["cuda"].__setitem__("free_memory_mib", 1),
            "GPU_FREE_MEMORY_INSUFFICIENT",
        ),
        (
            lambda value: value["model"].__setitem__("artifact_sha256", "0" * 64),
            "MODEL_ARTIFACT_SHA256_MISMATCH",
        ),
        (
            lambda value: value["offline_environment"].__setitem__(
                "HF_HUB_OFFLINE", "0"
            ),
            "OFFLINE_ENVIRONMENT_MISMATCH::HF_HUB_OFFLINE",
        ),
    ],
)
def test_preflight_fails_closed_on_control_drift(mutate, expected_issue: str) -> None:
    contract = load_environment_contract(ROOT)
    observations = _passing_observations(contract)
    mutate(observations)

    assert expected_issue in evaluate_observations(contract, observations)


def test_passing_receipt_is_non_authoritative_and_digest_bound() -> None:
    contract = load_environment_contract(ROOT)
    observations = _passing_observations(contract)

    receipt = build_preflight_receipt(
        repository_root=ROOT,
        contract=contract,
        observations=observations,
    )

    validate_preflight_receipt(receipt)
    assert receipt["status"] == "PASS"
    assert receipt["issues"] == []
    assert receipt["scope"] == {
        "environment_identity_verified": True,
        "embedding_execution_benchmarked": False,
        "retrieval_quality_measured": False,
        "production_promotion_authorized": False,
        "release_authorizing": False,
    }


def test_standalone_cli_help_needs_no_preconfigured_pythonpath() -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["APPS_RG_SKIP_DOTENV_AUTOLOAD"] = "1"

    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "--help"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "wheel payloads" in result.stdout
