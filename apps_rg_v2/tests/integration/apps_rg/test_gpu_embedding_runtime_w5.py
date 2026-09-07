from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.evals.gpu_embedding_observability_w5 import (
    gpu_integration_readiness,
    run_observability_benchmark,
)

pytestmark = [pytest.mark.gpu, pytest.mark.integration]
ROOT = Path(__file__).resolve().parents[3]


def test_real_gpu_observability_and_w0_regression_contract() -> None:
    ready, reason = gpu_integration_readiness()
    if not ready:
        pytest.skip(reason)

    receipt, path = run_observability_benchmark(repository_root=ROOT)

    assert path.is_file()
    assert receipt["status"] == "PASS"
    assert receipt["runtime"]["model_load_count"] == 1
    assert all(row["passed"] for row in receipt["regressions_against_w0"])
