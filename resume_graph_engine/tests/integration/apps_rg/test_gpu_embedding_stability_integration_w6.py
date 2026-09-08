from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.evals.gpu_embedding_stability_w6 import (
    gpu_stability_integration_readiness,
    run_stability_benchmark,
)

pytestmark = [pytest.mark.gpu, pytest.mark.integration, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[3]


def test_real_gpu_concurrency_and_sustained_stability_contract() -> None:
    ready, reason = gpu_stability_integration_readiness()
    if not ready:
        pytest.skip(reason)

    receipt, path = run_stability_benchmark(repository_root=ROOT)

    assert path.is_file()
    assert receipt["status"] == "PASS"
    assert receipt["runtime"]["concurrent_acquisition"]["model_load_count"] == 1
    assert all(row["passed"] for row in receipt["workload_stability"])
    assert receipt["memory_stability"]["passed"] is True
