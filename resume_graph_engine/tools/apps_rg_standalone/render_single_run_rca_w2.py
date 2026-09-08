"""Render canonical zero-LLM RCA artifacts for one preserved Apps RG run."""

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
RCA_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w2.py"


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
    parser.add_argument("--w1-packet", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_module("_apps_rg_w2_replay", REPLAY_MODULE_PATH)
        rca = _load_module("_apps_rg_single_run_rca_w2", RCA_MODULE_PATH)

        def _operation(_source: Path, operation_dir: Path) -> dict[str, Any]:
            completion = rca.emit_single_run_w2_canonical_rca(w1_packet_path=args.w1_packet, output_dir=operation_dir)
            return {"completion": completion, "activity": {"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False}}

        receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run, output_root=args.output_root, wave="W2", operation=_operation,
            receipt_filename="single_run_w2_zero_provider_guard.json", require_clean_import_state=True,
            expected_activity={"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False},
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W2", "error": str(exc)}, sort_keys=True))
        return 1
    completion = receipt["operation_result"]["completion"]
    print(json.dumps({
        "status": receipt["status"], "wave": "W2", "source_run_id": completion["source_run_id"],
        "manifest_path": completion["manifest_path"], "summary_path": completion["summary_path"],
        "semantic_digest": completion["semantic_digest"], "provider_calls": receipt["provider_calls"],
        "model_calls": receipt["model_calls"], "judge_calls": receipt["judge_calls"], "embedding_calls": receipt["embedding_calls"],
        "network_attempts": receipt["network_attempts"], "source_unchanged": receipt["source_unchanged"],
        "next_wave_authorized": completion["next_wave_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
