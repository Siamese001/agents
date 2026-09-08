"""Record local-only acceptance of a zero-LLM Apps RG RCA evidence chain."""

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
ACCEPTANCE_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w6.py"


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
    parser.add_argument("--w5-closeout", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--pre-acceptance-head", required=True)
    parser.add_argument("--verified-commit", action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        local_src = str(LOCAL_SRC_ROOT)
        if local_src in sys.path:
            sys.path.remove(local_src)
        sys.path.insert(0, local_src)
        replay = _load_module("_apps_rg_w6_replay", REPLAY_MODULE_PATH)
        acceptance_module = _load_module("_apps_rg_single_run_rca_w6", ACCEPTANCE_MODULE_PATH)

        def _operation(_source: Path, operation_dir: Path) -> dict[str, Any]:
            completion = acceptance_module.emit_single_run_w6_local_acceptance(
                w5_closeout_path=args.w5_closeout, branch_name=args.branch, pre_acceptance_head=args.pre_acceptance_head,
                verified_commit_ids=args.verified_commit, output_dir=operation_dir,
            )
            return {"completion": completion, "activity": {"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False}}

        receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run, output_root=args.output_root, wave="W6", operation=_operation,
            receipt_filename="single_run_w6_zero_provider_guard.json", require_clean_import_state=True,
            expected_activity={"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False},
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W6", "error": str(exc)}, sort_keys=True))
        return 1
    acceptance = receipt["operation_result"]["completion"]
    print(json.dumps({
        "status": receipt["status"], "wave": "W6", "source_run_id": acceptance["source_run_id"],
        "acceptance_status": acceptance["acceptance_status"], "acceptance_path": acceptance["acceptance_path"],
        "guard_receipt_path": receipt["receipt_path"], "branch": acceptance["local_branch"]["name"],
        "pre_acceptance_head": acceptance["local_branch"]["pre_acceptance_head"],
        "provider_calls": receipt["provider_calls"], "model_calls": receipt["model_calls"], "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"], "network_attempts": receipt["network_attempts"], "source_unchanged": receipt["source_unchanged"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
