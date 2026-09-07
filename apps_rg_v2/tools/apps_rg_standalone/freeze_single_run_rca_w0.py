"""Freeze one preserved Apps RG run for zero-LLM RCA work."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_SRC_ROOT = REPO_ROOT / "src"
REPLAY_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/post_runtime_replay.py"
FREEZE_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w0.py"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--w5-completion", type=Path, required=True)
    parser.add_argument("--integrated-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_module("_apps_rg_w0_replay", REPLAY_MODULE_PATH)
        freeze = _load_module("_apps_rg_single_run_rca_w0", FREEZE_MODULE_PATH)

        def _operation(source: Path, operation_dir: Path) -> dict[str, Any]:
            completion = freeze.emit_single_run_w0_freeze(
                source_run=source,
                w5_completion_path=args.w5_completion,
                integrated_manifest_path=args.integrated_manifest,
                output_dir=operation_dir,
                source_manifest_builder=replay.build_source_manifest,
            )
            return {
                "completion": completion,
                "activity": {
                    "apps_eval_executed": False,
                    "l6_executed": False,
                    "uwg_operation_attempted": False,
                },
            }

        receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run,
            output_root=args.output_root,
            wave="W0",
            operation=_operation,
            receipt_filename="single_run_w0_zero_provider_guard.json",
            require_clean_import_state=True,
            expected_activity={
                "apps_eval_executed": False,
                "l6_executed": False,
                "uwg_operation_attempted": False,
            },
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W0", "error": str(exc)}, sort_keys=True))
        return 1

    completion = receipt["operation_result"]["completion"]
    print(json.dumps({
        "status": receipt["status"],
        "wave": "W0",
        "source_run_id": completion["source_run_id"],
        "source_manifest_sha256": completion["source_manifest_sha256"],
        "freeze_path": completion["receipt_path"],
        "guard_receipt_path": receipt["receipt_path"],
        "provider_calls": receipt["provider_calls"],
        "model_calls": receipt["model_calls"],
        "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"],
        "network_attempts": receipt["network_attempts"],
        "source_unchanged": receipt["source_unchanged"],
        "next_wave_authorized": completion["next_wave_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
