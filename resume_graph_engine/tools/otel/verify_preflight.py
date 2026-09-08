"""Prove a fresh Apps RG OTel marker reaches the configured local collector."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _runtime_functions():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from apps_model_telemetry.otel_runtime import (
        configure_otel_runtime,
        resolve_otel_environment,
        verify_live_collector_receipt,
    )
    from apps_rg.runtime.env_bootstrap import bootstrap_apps_rg_env

    return (
        bootstrap_apps_rg_env,
        configure_otel_runtime,
        resolve_otel_environment,
        verify_live_collector_receipt,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()

    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (
        bootstrap_apps_rg_env,
        configure_otel_runtime,
        resolve_otel_environment,
        verify_live_collector_receipt,
    ) = _runtime_functions()
    dotenv = bootstrap_apps_rg_env(repo_root=REPO_ROOT)
    environment = resolve_otel_environment()
    runtime = configure_otel_runtime(
        service_name="apps_rg_otel_preflight",
        artifact_dir=artifact_dir,
    )
    receipt = verify_live_collector_receipt(artifact_dir=artifact_dir)
    payload = {
        "runtime_active": runtime.active,
        "runtime_reason": runtime.reason,
        "collector_status": receipt.get("status"),
        "collector_reason": receipt.get("reason"),
        "dotenv_source": dotenv.dotenv_source,
        "environment_errors": list(environment.errors),
        "artifact_dir": str(artifact_dir),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if runtime.active and receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
