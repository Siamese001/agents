"""Fail-closed W1 provenance preflight for the apps_rg GPU embedding control."""

from __future__ import annotations

import importlib.metadata as metadata
import csv
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from apps_rg.evals.gpu_embedding_baseline_w0 import canonical_sha256, file_sha256

CONTRACT_PATH = Path("tools/apps_rg_standalone/gpu_embedding_environment_w1.json")
PREFLIGHT_MODULE_PATH = Path("src/apps_rg/runtime/gpu_embedding_environment_w1.py")
RECEIPT_SCHEMA = "apps_rg.gpu_embedding_environment_preflight_w1.v1"


class GpuEmbeddingEnvironmentError(RuntimeError):
    """Raised when the W1 contract or its bound sources are invalid."""


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GpuEmbeddingEnvironmentError(f"cannot load JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise GpuEmbeddingEnvironmentError(f"JSON value is not an object: {path}")
    return value


def _within_root(root: Path, relative: str) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise GpuEmbeddingEnvironmentError(
            f"contract path escapes repository: {relative}"
        ) from exc
    return resolved


def _validate_self_digest(payload: Mapping[str, Any], field: str, label: str) -> None:
    unsigned = dict(payload)
    supplied = str(unsigned.pop(field, ""))
    if not supplied or canonical_sha256(unsigned) != supplied:
        raise GpuEmbeddingEnvironmentError(f"{label} self digest mismatch")


def load_environment_contract(repository_root: Path | str) -> dict[str, Any]:
    """Load W1 and validate every tracked file binding before live probing."""

    root = Path(repository_root).resolve()
    contract_path = root / CONTRACT_PATH
    contract = _load_json_object(contract_path)
    if contract.get("schema_version") != "apps_rg.gpu_embedding_environment_w1.v1":
        raise GpuEmbeddingEnvironmentError("W1 environment contract schema mismatch")
    if contract.get("status") != "CONTROL_LOCKED":
        raise GpuEmbeddingEnvironmentError("W1 control environment is not locked")
    _validate_self_digest(contract, "contract_sha256", "W1 environment contract")

    install = contract.get("install") or {}
    lock_path = _within_root(root, str(install.get("lock_path") or ""))
    if not lock_path.is_file() or file_sha256(lock_path) != install.get("lock_sha256"):
        raise GpuEmbeddingEnvironmentError("W1 dependency lock digest mismatch")

    runtime = contract.get("embedding_runtime") or {}
    runtime_path = _within_root(root, str(runtime.get("runtime_contract_path") or ""))
    if not runtime_path.is_file() or file_sha256(runtime_path) != runtime.get(
        "runtime_contract_file_sha256"
    ):
        raise GpuEmbeddingEnvironmentError("C0.3 runtime contract file digest mismatch")
    runtime_contract = _load_json_object(runtime_path)
    _validate_self_digest(runtime_contract, "contract_sha256", "C0.3 runtime contract")

    model = contract.get("model") or {}
    manifest_path = _within_root(root, str(model.get("manifest_path") or ""))
    if not manifest_path.is_file() or file_sha256(manifest_path) != model.get(
        "manifest_file_sha256"
    ):
        raise GpuEmbeddingEnvironmentError("pinned model manifest file digest mismatch")
    model_manifest = _load_json_object(manifest_path)
    if model_manifest.get("artifact_sha256") != model.get("artifact_sha256"):
        raise GpuEmbeddingEnvironmentError("pinned model artifact digest mismatch")
    return contract


def _locked_requirements(root: Path, contract: Mapping[str, Any]) -> dict[str, str]:
    lock_path = _within_root(root, str((contract.get("install") or {})["lock_path"]))
    locked: dict[str, str] = {}
    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "--", "-e ")):
            continue
        requirement = Requirement(line)
        if requirement.url:
            continue
        specs = list(requirement.specifier)
        if len(specs) != 1 or specs[0].operator != "==":
            raise GpuEmbeddingEnvironmentError(
                f"dependency lock is not exact: {requirement.name}"
            )
        locked[canonicalize_name(requirement.name)] = specs[0].version
    return locked


def _distribution_payload_sha256(distribution: metadata.Distribution) -> str | None:
    """Hash wheel-owned payload rows while excluding install-location metadata."""

    record = distribution.read_text("RECORD")
    if not record:
        return None
    stable_rows: list[list[str]] = []
    for row in csv.reader(record.splitlines()):
        relative = row[0].replace("\\", "/")
        if relative.startswith("../../Scripts/") or relative.endswith(
            (
                ".dist-info/REQUESTED",
                ".dist-info/direct_url.json",
                ".dist-info/INSTALLER",
                ".dist-info/RECORD",
            )
        ):
            continue
        stable_rows.append(row)
    return canonical_sha256(sorted(stable_rows))


def _distribution_observation(name: str, binding: Mapping[str, Any]) -> dict[str, Any]:
    try:
        distribution = metadata.distribution(name)
        module_file = Path(
            distribution.locate_file(str(binding["module_relative_path"]))
        ).resolve()
    except (metadata.PackageNotFoundError, KeyError) as exc:
        return {"available": False, "error": str(exc)}
    distribution_root = Path(distribution.locate_file("")).resolve()
    try:
        module_relative = module_file.relative_to(distribution_root).as_posix()
    except ValueError:
        module_relative = f"OUTSIDE_DISTRIBUTION:{module_file}"
    return {
        "available": True,
        "version": distribution.version,
        "payload_sha256": _distribution_payload_sha256(distribution),
        "module_file": str(module_file),
        "module_relative_path": module_relative,
    }


def _git_value(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _apps_rg_source_observation(repository: Path) -> dict[str, Any]:
    """Observe this checkout's Apps RG source tree without package indirection."""

    try:
        repository = Path(repository).resolve()
        module_path = repository / "src" / "apps_rg" / "__init__.py"
        if not module_path.is_file():
            raise OSError(f"Apps RG source module is absent: {module_path}")
        relative = module_path.relative_to(repository).as_posix()
        status = _git_value(
            repository,
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "src/apps_rg",
        )
        return {
            "available": True,
            "source_file": str(module_path),
            "source_relative_path": relative,
            "repository": str(repository),
            "repository_url": _git_value(repository, "remote", "get-url", "origin"),
            "revision": _git_value(repository, "rev-parse", "HEAD"),
            "tree_sha": _git_value(repository, "rev-parse", "HEAD:src/apps_rg"),
            "tracked_or_untracked_source_changes": status.splitlines()
            if status
            else [],
        }
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        return {"available": False, "error": str(exc)}


def _nvidia_smi_observation(index: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={index}",
                "--query-gpu=name,driver_version,memory.total,memory.free,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        values = [
            value.strip() for value in result.stdout.strip().splitlines()[0].split(",")
        ]
        if len(values) != 5:
            raise ValueError("unexpected nvidia-smi field count")
        return {
            "available": True,
            "name": values[0],
            "driver_version": values[1],
            "total_memory_mib": int(values[2]),
            "free_memory_mib": int(values[3]),
            "compute_capability": [int(value) for value in values[4].split(".")],
        }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        return {"available": False, "error": str(exc)}


def _cuda_observation() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False, "error": "torch.cuda.is_available() is false"}
        index = 0
        torch.cuda.set_device(index)
        with torch.inference_mode():
            probe = torch.tensor([1.0, 2.0, 3.0], device="cuda:0")
            checksum = float(torch.sum(probe * probe).item())
        torch.cuda.synchronize(index)
        smi = _nvidia_smi_observation(index)
        return {
            **smi,
            "available": bool(smi.get("available")),
            "device": "cuda:0",
            "torch_cuda_runtime": str(torch.version.cuda),
            "torch_arch_list": list(torch.cuda.get_arch_list()),
            "torch_device_name": str(torch.cuda.get_device_name(index)),
            "torch_compute_capability": list(torch.cuda.get_device_capability(index)),
            "kernel_probe_checksum": checksum,
        }
    except (ImportError, RuntimeError, ValueError) as exc:
        return {"available": False, "error": str(exc)}


def _model_observation(model_path: Path) -> dict[str, Any]:
    try:
        from apps_rg.fact_inventory.c03_skill_embedding_builder import (
            build_local_model_manifest,
        )

        manifest = build_local_model_manifest(model_path)
        return {
            "available": True,
            "path": str(model_path.resolve()),
            "model_id": manifest["model_id"],
            "revision": manifest["revision"],
            "dimension": manifest["dimension"],
            "normalization": manifest["normalization"],
            "artifact_sha256": manifest["artifact_sha256"],
            "file_count": manifest["file_count"],
            "total_bytes": manifest["total_bytes"],
        }
    except (OSError, RuntimeError, KeyError) as exc:
        return {"available": False, "error": str(exc), "path": str(model_path)}


def collect_observations(
    *, repository_root: Path | str, contract: Mapping[str, Any], model_path: Path | str
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    locked = _locked_requirements(root, contract)
    installed: dict[str, str | None] = {}
    for name in locked:
        try:
            installed[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed[name] = None
    critical = {
        name: _distribution_observation(name, binding)
        for name, binding in (contract.get("critical_distributions") or {}).items()
    }
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "machine": platform.machine(),
            "operating_system": platform.system(),
            "executable": sys.executable,
        },
        "locked_packages": locked,
        "installed_locked_packages": installed,
        "critical_distributions": critical,
        "apps_rg_source": _apps_rg_source_observation(root),
        "cuda": _cuda_observation(),
        "model": _model_observation(Path(model_path).resolve()),
        "offline_environment": {
            name: os.environ.get(name)
            for name in contract.get("offline_environment") or {}
        },
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return ()


def evaluate_observations(
    contract: Mapping[str, Any], observations: Mapping[str, Any]
) -> list[str]:
    """Return stable issue codes for every control mismatch."""

    issues: list[str] = []
    expected_python = contract.get("platform") or {}
    observed_python = observations.get("python") or {}
    for expected_key, observed_key in (
        ("python_implementation", "implementation"),
        ("python_version", "version"),
        ("operating_system", "operating_system"),
        ("machine", "machine"),
    ):
        if observed_python.get(observed_key) != expected_python.get(expected_key):
            issues.append(f"PYTHON_{expected_key.upper()}_MISMATCH")

    installed = observations.get("installed_locked_packages") or {}
    for name, expected_version in (observations.get("locked_packages") or {}).items():
        if installed.get(name) != expected_version:
            issues.append(f"LOCKED_PACKAGE_MISMATCH::{name}")

    critical_observed = observations.get("critical_distributions") or {}
    for name, expected in (contract.get("critical_distributions") or {}).items():
        observed = critical_observed.get(name) or {}
        if observed.get("available") is not True:
            issues.append(f"CRITICAL_DISTRIBUTION_UNAVAILABLE::{name}")
            continue
        for field in ("version", "payload_sha256", "module_relative_path"):
            if observed.get(field) != expected.get(field):
                issues.append(f"CRITICAL_DISTRIBUTION_{field.upper()}::{name}")

    expected_source = contract.get("apps_rg_source") or {}
    observed_source = observations.get("apps_rg_source") or {}
    if observed_source.get("available") is not True:
        issues.append("APP_SOURCE_UNAVAILABLE")
    else:
        for field in (
            "source_relative_path",
        ):
            if observed_source.get(field) != expected_source.get(field):
                issues.append(f"APP_SOURCE_{field.upper()}_MISMATCH")
        if expected_source.get(
            "tracked_source_tree_must_be_clean"
        ) is True and observed_source.get("tracked_or_untracked_source_changes"):
            issues.append("APP_SOURCE_TREE_DIRTY")

    expected_runtime = contract.get("embedding_runtime") or {}
    expected_gpu = contract.get("gpu") or {}
    observed_cuda = observations.get("cuda") or {}
    if observed_cuda.get("available") is not True:
        issues.append("CUDA_UNAVAILABLE")
    else:
        if observed_cuda.get("device") != expected_runtime.get("device"):
            issues.append("CUDA_DEVICE_MISMATCH")
        if observed_cuda.get("torch_cuda_runtime") != expected_runtime.get(
            "cuda_runtime"
        ):
            issues.append("CUDA_RUNTIME_MISMATCH")
        if expected_runtime.get("compiled_architecture_required") not in (
            observed_cuda.get("torch_arch_list") or []
        ):
            issues.append("CUDA_COMPILED_ARCHITECTURE_MISSING")
        if observed_cuda.get("name") != expected_gpu.get("name"):
            issues.append("GPU_NAME_MISMATCH")
        if observed_cuda.get("compute_capability") != expected_gpu.get(
            "compute_capability"
        ):
            issues.append("GPU_COMPUTE_CAPABILITY_MISMATCH")
        if _version_tuple(
            str(observed_cuda.get("driver_version") or "")
        ) < _version_tuple(str(expected_gpu.get("minimum_driver_version") or "")):
            issues.append("GPU_DRIVER_TOO_OLD")
        if int(observed_cuda.get("total_memory_mib") or 0) < int(
            expected_gpu.get("minimum_total_memory_mib") or 0
        ):
            issues.append("GPU_TOTAL_MEMORY_INSUFFICIENT")
        if int(observed_cuda.get("free_memory_mib") or 0) < int(
            expected_gpu.get("minimum_free_memory_mib") or 0
        ):
            issues.append("GPU_FREE_MEMORY_INSUFFICIENT")
        if observed_cuda.get("kernel_probe_checksum") != 14.0:
            issues.append("CUDA_KERNEL_PROBE_FAILED")

    expected_model = contract.get("model") or {}
    observed_model = observations.get("model") or {}
    if observed_model.get("available") is not True:
        issues.append("MODEL_UNAVAILABLE")
    else:
        for field in (
            "model_id",
            "revision",
            "dimension",
            "normalization",
            "artifact_sha256",
        ):
            if observed_model.get(field) != expected_model.get(field):
                issues.append(f"MODEL_{field.upper()}_MISMATCH")

    expected_offline = contract.get("offline_environment") or {}
    observed_offline = observations.get("offline_environment") or {}
    for name, expected_value in expected_offline.items():
        if observed_offline.get(name) != expected_value:
            issues.append(f"OFFLINE_ENVIRONMENT_MISMATCH::{name}")
    return sorted(set(issues))


def build_preflight_receipt(
    *,
    repository_root: Path | str,
    contract: Mapping[str, Any],
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    issues = evaluate_observations(contract, observations)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "source": {
            "contract": {
                "path": CONTRACT_PATH.as_posix(),
                "sha256": file_sha256(root / CONTRACT_PATH),
                "contract_sha256": contract["contract_sha256"],
            },
            "preflight_module": {
                "path": PREFLIGHT_MODULE_PATH.as_posix(),
                "sha256": file_sha256(root / PREFLIGHT_MODULE_PATH),
            },
        },
        "scope": {
            "environment_identity_verified": not issues,
            "embedding_execution_benchmarked": False,
            "retrieval_quality_measured": False,
            "production_promotion_authorized": False,
            "release_authorizing": False,
        },
        "observations": dict(observations),
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    validate_preflight_receipt(receipt)
    return receipt


def validate_preflight_receipt(receipt: Mapping[str, Any]) -> None:
    issues: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        issues.append("schema_version")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        issues.append("status")
    reported = receipt.get("issues")
    if not isinstance(reported, list):
        issues.append("issues")
    elif (receipt.get("status") == "PASS") != (len(reported) == 0):
        issues.append("status_issue_consistency")
    scope = receipt.get("scope") or {}
    for field in (
        "embedding_execution_benchmarked",
        "retrieval_quality_measured",
        "production_promotion_authorized",
        "release_authorizing",
    ):
        if scope.get(field) is not False:
            issues.append(f"scope.{field}")
    unsigned = dict(receipt)
    supplied = unsigned.pop("receipt_sha256", None)
    if canonical_sha256(unsigned) != supplied:
        issues.append("receipt_sha256")
    if issues:
        raise GpuEmbeddingEnvironmentError(
            f"invalid W1 environment receipt: {sorted(set(issues))}"
        )


def write_preflight_receipt(path: Path | str, receipt: Mapping[str, Any]) -> None:
    validate_preflight_receipt(receipt)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    staging = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    staging.write_bytes(data)
    os.replace(staging, destination)


__all__ = [
    "GpuEmbeddingEnvironmentError",
    "build_preflight_receipt",
    "collect_observations",
    "evaluate_observations",
    "load_environment_contract",
    "validate_preflight_receipt",
    "write_preflight_receipt",
]
