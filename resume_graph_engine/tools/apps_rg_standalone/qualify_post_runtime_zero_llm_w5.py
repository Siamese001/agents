"""Execute and seal the complete W5 post-runtime path with zero LLM calls."""

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
PIPELINE_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/w5_end_to_end_pipeline.py"
QUALIFICATION_MODULE_PATH = REPO_ROOT / "src/apps_rg/runtime/zero_llm_qualification.py"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _pin_local_src() -> None:
    """Make this checkout authoritative over ambient PYTHONPATH entries."""

    local_src = str(LOCAL_SRC_ROOT)
    if local_src in sys.path:
        sys.path.remove(local_src)
    sys.path.insert(0, local_src)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-run",
        action="append",
        type=Path,
        required=True,
        help="Preserved real source run; provide exactly twice.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Fresh W5 evidence root; short paths are recommended on Windows.",
    )
    args = parser.parse_args(argv)
    if len(args.source_run) != 2:
        parser.error("W5 requires exactly two --source-run values")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _pin_local_src()
        replay = _load_module(
            "_apps_rg_post_runtime_replay_w5",
            REPLAY_MODULE_PATH,
        )
        pipeline = _load_module(
            "_apps_rg_w5_end_to_end_pipeline",
            PIPELINE_MODULE_PATH,
        )
        qualification = _load_module(
            "_apps_rg_zero_llm_qualification_w5",
            QUALIFICATION_MODULE_PATH,
        )
        sources = sorted(
            (path.resolve(strict=True) for path in args.source_run),
            key=lambda path: path.name,
        )
        if len({path.name for path in sources}) != 2:
            raise RuntimeError("W5 source run IDs must be unique")
        output = args.output_root.resolve()
        output.mkdir(parents=True, exist_ok=True)

        integrated = pipeline.execute_integrated_replays(
            source_runs=sources,
            output_dir=output,
        )
        faults = pipeline.execute_production_fault_qualification(
            source_run=sources[0],
            output_dir=output,
        )
        positive = pipeline.execute_positive_control(
            source_run=sources[0],
            output_dir=output,
        )

        def _provider_tripwire_probe() -> dict[str, Any]:
            controlled_guard = replay.ZeroProviderReplayGuard()
            try:
                controlled_guard.block_attempt(
                    "provider",
                    "w5.controlled_provider_tripwire",
                )
            except replay.ProviderExecutionBlocked as exc:
                return {
                    "status": "PASS",
                    "provider_attempt_blocked": True,
                    "exception_type": type(exc).__name__,
                    "controlled_attempt_counters": (
                        controlled_guard.counters.to_dict()
                    ),
                }
            return {
                "status": "FAIL",
                "provider_attempt_blocked": False,
                "exception_type": "",
                "controlled_attempt_counters": (controlled_guard.counters.to_dict()),
            }

        def _qualification_operation(
            _source: Path,
            operation_dir: Path,
        ) -> dict[str, Any]:
            return qualification.emit_w5_zero_llm_qualification(
                integrated_manifest_path=integrated["manifest_path"],
                fault_manifest_path=faults["manifest_path"],
                positive_manifest_path=positive["manifest_path"],
                positive_guard_path=positive["guard_path"],
                run_inputs=integrated["run_inputs"],
                output_dir=operation_dir,
                evidence_root=output,
                source_manifest_builder=replay.build_source_manifest,
                provider_tripwire_probe=_provider_tripwire_probe,
            )

        receipt = replay.run_guarded_artifact_replay(
            source_run=sources[0],
            output_root=output / "q",
            wave="W5",
            operation=_qualification_operation,
            receipt_filename="w5_zero_provider_guard_receipt.json",
            require_clean_import_state=True,
            expected_activity={
                "apps_eval_executed": False,
                "l6_executed": False,
                "uwg_operation_attempted": False,
            },
        )
        operation = receipt["operation_result"]
        completion = operation["completion"]
        valid, errors = qualification.verify_w5_qualification(
            qualification_dir=operation["qualification_dir"],
            evidence_root=output,
            run_inputs=integrated["run_inputs"],
            source_manifest_builder=replay.build_source_manifest,
        )
        if not valid:
            raise RuntimeError("W5 final verification failed:" + ",".join(errors))
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "wave": "W5",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1

    summary = {
        "status": receipt["status"],
        "wave": receipt["wave"],
        "qualification_status": completion["status"],
        "scope_complete": completion["scope_complete"],
        "w6_authorized": completion["w6_authorized"],
        "qualification_mode": completion["qualification_mode"],
        "real_run_ids": completion["real_run_ids"],
        "record_ids": completion["record_ids"],
        "integrated_real_run_count": completion["integrated_real_run_count"],
        "integrated_full_chain_execution_count": completion[
            "integrated_full_chain_execution_count"
        ],
        "apps_eval_records": completion["apps_eval_records"],
        "l6_terminal_closures": completion["l6_terminal_closures"],
        "non_product_terminal_manifests": completion["non_product_terminal_manifests"],
        "historical_saved_judge_results": completion["historical_saved_judge_results"],
        "historical_saved_judge_passes": completion["historical_saved_judge_passes"],
        "historical_actual_claude_judge_results": completion[
            "historical_actual_claude_judge_results"
        ],
        "historical_apps_research_usage_events": completion[
            "historical_apps_research_usage_events"
        ],
        "historical_apps_research_successful_attempts": completion[
            "historical_apps_research_successful_attempts"
        ],
        "historical_apps_research_claude_usage_events": completion[
            "historical_apps_research_claude_usage_events"
        ],
        "historical_apps_rg_generation_lanes": completion[
            "historical_apps_rg_generation_lanes"
        ],
        "historical_apps_rg_target_claude_lanes": completion[
            "historical_apps_rg_target_claude_lanes"
        ],
        "historical_apps_rg_actual_claude_lanes": completion[
            "historical_apps_rg_actual_claude_lanes"
        ],
        "historical_apps_rg_model_mismatch_lanes": completion[
            "historical_apps_rg_model_mismatch_lanes"
        ],
        "historical_apps_rg_recorded_token_budget_failure_lanes": completion[
            "historical_apps_rg_recorded_token_budget_failure_lanes"
        ],
        "historical_apps_rg_recomputed_output_token_budget_failure_lanes": completion[
            "historical_apps_rg_recomputed_output_token_budget_failure_lanes"
        ],
        "historical_apps_rg_token_accounting_false_failure_lanes": completion[
            "historical_apps_rg_token_accounting_false_failure_lanes"
        ],
        "contract_handoff_entries": completion["contract_handoff_entries"],
        "eval_fault_recovered": completion["production_fault_qualification"][
            "eval_recovery_count"
        ]
        == 1,
        "l6_fault_recovered": completion["production_fault_qualification"][
            "l6_recovery_count"
        ]
        == 1,
        "positive_control_status": completion["production_positive_control"]["status"],
        "positive_control_production_validators": completion[
            "production_positive_control"
        ]["production_validator_count"],
        "provider_tripwire_blocked": completion["provider_tripwire"][
            "controlled_provider_attempts"
        ]
        == 1,
        "provider_calls": receipt["provider_calls"],
        "judge_calls": receipt["judge_calls"],
        "embedding_calls": receipt["embedding_calls"],
        "model_calls": receipt["model_calls"],
        "network_attempts": receipt["network_attempts"],
        "subprocess_attempts": receipt["subprocess_attempts"],
        "model_span_delta": receipt["model_span_delta"],
        "source_files_changed": completion["source_files_changed"],
        "new_uwg_operations": completion["new_uwg_operations"],
        "live_generation_executed": completion["live_generation_executed"],
        "live_model_pin_qualified": completion["live_model_pin_qualified"],
        "production_authority_granted": completion["production_authority_granted"],
        "publication_allowed": completion["publication_allowed"],
        "qualification_dir": operation["qualification_dir"],
        "receipt_path": receipt["receipt_path"],
        "semantic_digest": receipt["semantic_digest"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
