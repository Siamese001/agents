"""Extract one zero-LLM Apps RG RCA evidence packet from W5 evidence."""

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
EXTRACTOR_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/single_run_rca_w1.py"


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
    parser.add_argument("--integrated-manifest", type=Path, required=True)
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
        replay = _load_module("_apps_rg_w1_replay", REPLAY_MODULE_PATH)
        extractor = _load_module("_apps_rg_single_run_rca_w1", EXTRACTOR_MODULE_PATH)

        def _operation(_source: Path, operation_dir: Path) -> dict[str, Any]:
            packet = extractor.emit_single_run_w1_evidence_packet(
                w0_freeze_path=args.w0_freeze,
                integrated_manifest_path=args.integrated_manifest,
                w5_evidence_root=args.w5_evidence_root,
                output_dir=operation_dir,
            )
            return {"completion": packet, "activity": {"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False}}

        receipt = replay.run_guarded_artifact_replay(
            source_run=args.source_run,
            output_root=args.output_root,
            wave="W1",
            operation=_operation,
            receipt_filename="single_run_w1_zero_provider_guard.json",
            require_clean_import_state=True,
            expected_activity={"apps_eval_executed": False, "l6_executed": False, "uwg_operation_attempted": False},
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "wave": "W1", "error": str(exc)}, sort_keys=True))
        return 1
    packet = receipt["operation_result"]["completion"]
    print(json.dumps({
        "status": receipt["status"], "wave": "W1", "source_run_id": packet["source_run_id"],
        "generation_lanes": packet["extracted_counts"]["generation_lanes"], "judges": packet["extracted_counts"]["judges"],
        "contract_handoffs": packet["extracted_counts"]["contract_handoffs"], "verified_w5_artifacts": len(packet["verified_w5_artifacts"]),
        "packet_path": packet["packet_path"], "guard_receipt_path": receipt["receipt_path"],
        "provider_calls": receipt["provider_calls"], "model_calls": receipt["model_calls"], "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"], "network_attempts": receipt["network_attempts"], "source_unchanged": receipt["source_unchanged"],
        "next_wave_authorized": packet["next_wave_authorized"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
