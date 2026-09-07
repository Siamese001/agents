"""Seal the final zero-LLM closeout for one Apps RG RCA."""

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
CLOSEOUT_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w5.py"


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
    parser.add_argument("--w2-manifest", type=Path, required=True)
    parser.add_argument("--w3-decision", type=Path, required=True)
    parser.add_argument("--w4-verification", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_module("_apps_rg_w5_replay", REPLAY_MODULE_PATH)
        closeout_module = _load_module("_apps_rg_single_run_rca_w5", CLOSEOUT_MODULE_PATH)

        def _operation(_source: Path, _operation_dir: Path) -> dict[str, Any]:
            return {"completion": {"status": "PASS"}, "activity": {"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False}}

        guard_receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run, output_root=args.output_root, wave="W5", operation=_operation,
            receipt_filename="single_run_w5_zero_provider_guard.json", require_clean_import_state=True,
            expected_activity={"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False},
        )
        finalization_guard = replay.ZeroProviderReplayGuard()
        with finalization_guard:
            closeout = closeout_module.emit_single_run_w5_zero_llm_closeout(
                w2_manifest_path=args.w2_manifest, w3_decision_path=args.w3_decision,
                w4_verification_path=args.w4_verification, w5_guard_receipt_path=Path(guard_receipt["receipt_path"]),
                finalization_counters=finalization_guard.counters.to_dict(), output_dir=Path(guard_receipt["operation_dir"]),
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W5", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({
        "status": closeout["status"], "wave": "W5", "source_run_id": closeout["source_run_id"],
        "scope_complete": closeout["scope_complete"], "closeout_path": closeout["closeout_path"],
        "provider_calls": closeout["zero_llm_runtime"]["primary_guard_counters"]["provider_calls"],
        "model_calls": closeout["zero_llm_runtime"]["primary_guard_counters"]["model_calls"],
        "judge_calls": closeout["zero_llm_runtime"]["primary_guard_counters"]["judge_calls"],
        "embedding_calls": closeout["zero_llm_runtime"]["primary_guard_counters"]["embedding_calls"],
        "network_attempts": closeout["zero_llm_runtime"]["primary_guard_counters"]["network_attempts"],
        "source_unchanged": closeout["zero_llm_runtime"]["source_unchanged"], "w6_authorized": closeout["w6_authorized"],
        "semantic_digest": closeout["semantic_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
