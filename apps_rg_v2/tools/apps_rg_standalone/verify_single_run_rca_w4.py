"""Verify the complete zero-LLM single-run Apps RG RCA chain."""

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
VERIFY_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w4.py"


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
    parser.add_argument("--w0-freeze", type=Path, required=True)
    parser.add_argument("--w1-packet", type=Path, required=True)
    parser.add_argument("--w2-manifest", type=Path, required=True)
    parser.add_argument("--w3-decision", type=Path, required=True)
    parser.add_argument("--w5-evidence-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_module("_apps_rg_w4_replay", REPLAY_MODULE_PATH)
        verify = _load_module("_apps_rg_single_run_rca_w4", VERIFY_MODULE_PATH)

        def _operation(source: Path, operation_dir: Path) -> dict[str, Any]:
            completion = verify.verify_single_run_w4(
                source_run=source, w0_freeze_path=args.w0_freeze, w1_packet_path=args.w1_packet,
                w2_manifest_path=args.w2_manifest, w3_decision_path=args.w3_decision,
                w5_evidence_root=args.w5_evidence_root, output_dir=operation_dir,
                source_manifest_builder=replay.build_source_manifest,
            )
            return {"completion": completion, "activity": {"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False}}

        receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run, output_root=args.output_root, wave="W4", operation=_operation,
            receipt_filename="single_run_w4_zero_provider_guard.json", require_clean_import_state=True,
            expected_activity={"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False},
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W4", "error": str(exc)}, sort_keys=True))
        return 1
    completion = receipt["operation_result"]["completion"]
    print(json.dumps({
        "status": receipt["status"], "wave": "W4", "source_run_id": completion["source_run_id"],
        "checks_passed": len(completion["checks"]), "verified_w5_artifacts": completion["verified_w5_artifact_count"],
        "verification_path": completion["verification_path"], "guard_receipt_path": receipt["receipt_path"],
        "provider_calls": receipt["provider_calls"], "model_calls": receipt["model_calls"], "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"], "network_attempts": receipt["network_attempts"], "source_unchanged": receipt["source_unchanged"],
        "next_wave_authorized": completion["next_wave_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
