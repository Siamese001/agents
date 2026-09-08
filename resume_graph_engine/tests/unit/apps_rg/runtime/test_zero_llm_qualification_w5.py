"""Focused contracts for production-path W5 zero-provider qualification."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
QUALIFICATION_PATH = REPO_ROOT / "src/apps_rg/runtime/zero_llm_qualification.py"
PIPELINE_PATH = REPO_ROOT / "src/apps_rg/runtime/w5_end_to_end_pipeline.py"
REPLAY_PATH = REPO_ROOT / "src/apps_rg/runtime/post_runtime_replay.py"
WHOLE_RUN_EXIT_PATH = REPO_ROOT / "src/apps_rg/runtime/whole_run_exit.py"
L2_AUTHORITY_PATH = REPO_ROOT / "src/apps_rg/runtime/section_l2_authority.py"
L2_LANE_INTEGRATION_PATH = (
    REPO_ROOT / "src/apps_rg/runtime/section_l2_lane_integration.py"
)
CLI_PATH = REPO_ROOT / "tools/apps_rg_standalone/qualify_post_runtime_zero_llm_w5.py"
_CLAUDE_GENERATOR_MODEL = "claude-" + "sonnet-5"
_OPENAI_GENERATOR_MODEL = "gpt-5.6-" + "luna"
_RESEARCH_GENERATOR_MODEL = "gpt-5.6-" + "terra"
_GEMINI_MODEL = "gemini-3.6-" + "flash"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


subject = _load("_w5_qualification_unit", QUALIFICATION_PATH)
pipeline_subject = _load("_w5_pipeline_unit", PIPELINE_PATH)
l2_authority_subject = _load("_w5_l2_authority_unit", L2_AUTHORITY_PATH)
l2_lane_subject = _load("_w5_l2_lane_unit", L2_LANE_INTEGRATION_PATH)


def _tripwire_probe() -> dict[str, Any]:
    return {
        "status": "PASS",
        "provider_attempt_blocked": True,
        "exception_type": "ProviderExecutionBlocked",
        "controlled_attempt_counters": {
            "blocked_import_attempts": 0,
            "provider_calls": 1,
            "judge_calls": 0,
            "embedding_calls": 0,
            "model_calls": 0,
            "network_attempts": 0,
            "subprocess_attempts": 0,
        },
    }


def test_w5_tripwire_is_controlled_and_excluded_from_execution_counts(
    tmp_path: Path,
) -> None:
    proof, path = subject._emit_tripwire_proof(
        output=tmp_path,
        probe=_tripwire_probe,
    )

    assert proof["status"] == "PASS"
    assert proof["controlled_attempt_counters"]["provider_calls"] == 1
    assert proof["qualification_attempt_counters_affected"] is False
    assert subject._verify_tripwire(path) == {
        "status": "PASS",
        "controlled_provider_attempts": 1,
        "actual_provider_calls": 0,
    }

    counts, _ = subject._emit_counts(
        output=tmp_path,
        integrated={
            "real_run_count": 2,
            "full_chain_execution_count": 4,
            "apps_eval_record_count": 2,
            "l6_closure_count": 2,
            "terminal_manifest_count": 2,
            "historical_saved_judge_result_count": 42,
            "historical_saved_judge_pass_count": 42,
            "historical_actual_claude_judge_result_count": 0,
            "historical_apps_research_usage_event_count": 34,
            "historical_apps_research_successful_attempt_count": 6,
            "historical_apps_research_claude_usage_event_count": 0,
            "historical_apps_rg_generation_lane_count": 22,
            "historical_apps_rg_target_claude_lane_count": 22,
            "historical_apps_rg_actual_claude_lane_count": 0,
            "historical_apps_rg_model_mismatch_lane_count": 22,
            "historical_apps_rg_recorded_token_budget_failure_lane_count": 22,
            "historical_apps_rg_recomputed_output_token_budget_failure_lane_count": 0,
            "historical_apps_rg_token_accounting_false_failure_lane_count": 22,
            "contract_handoff_entry_count": 42,
        },
        faults={
            "eval_failure_count": 1,
            "eval_recovery_count": 1,
            "l6_failure_count": 1,
            "l6_recovery_count": 1,
            "terminal_recovery_count": 1,
        },
        positive={"production_validator_count": 6},
    )
    subject._verify_counts(counts)
    assert counts["provider_calls"] == 0
    assert counts["historical_saved_judge_results"] == 42
    assert counts["historical_saved_judge_passes"] == 42
    assert counts["historical_actual_claude_judge_results"] == 0
    assert counts["historical_apps_research_usage_events"] == 34
    assert counts["historical_apps_research_successful_attempts"] == 6
    assert counts["historical_apps_research_claude_usage_events"] == 0
    assert counts["historical_apps_rg_generation_lanes"] == 22
    assert counts["historical_apps_rg_target_claude_lanes"] == 22
    assert counts["historical_apps_rg_actual_claude_lanes"] == 0
    assert counts["historical_apps_rg_model_mismatch_lanes"] == 22
    assert counts["historical_apps_rg_recorded_token_budget_failure_lanes"] == 22
    assert (
        counts["historical_apps_rg_recomputed_output_token_budget_failure_lanes"] == 0
    )
    assert counts["historical_apps_rg_token_accounting_false_failure_lanes"] == 22
    assert counts["contract_handoff_entries"] == 42
    assert counts["controlled_tripwire_provider_attempts"] == 1
    assert counts["controlled_tripwire_attempts_excluded_from_execution_counts"] is True


def test_w5_binding_reopens_bytes_and_rejects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
    binding = subject._binding(
        artifact,
        root=tmp_path,
        role="artifact",
    )

    assert (
        subject._resolve_binding(
            binding,
            root=tmp_path,
            label="artifact",
        )
        == artifact.resolve()
    )

    artifact.write_text('{"status":"FAIL"}\n', encoding="utf-8")
    with pytest.raises(
        subject.ZeroLlmQualificationError,
        match=r"artifact_(length|digest)_mismatch",
    ):
        subject._resolve_binding(
            binding,
            root=tmp_path,
            label="artifact",
        )


def test_historical_model_routes_distinguish_real_mismatch_from_false_budget_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    ledger = source / "apps_research/runs/external_model_usage_ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    events: list[dict[str, Any]] = []
    for logical_attempt, provider, model, event_count in (
        (1, "external_openai", _RESEARCH_GENERATOR_MODEL, 5),
        (2, "external_openai", _RESEARCH_GENERATOR_MODEL, 5),
        (3, "google_gemini", _GEMINI_MODEL, 7),
    ):
        for event_index in range(event_count):
            success = event_index == event_count - 1
            events.append(
                {
                    "app_id": "apps_research",
                    "logical_attempt": logical_attempt,
                    "logical_attempt_id": f"attempt:{logical_attempt}",
                    "section_id": (
                        "company_brief_generation" if logical_attempt < 3 else "X2"
                    ),
                    "provider": provider,
                    "model": model,
                    "requested_model": model,
                    "observed_model": model if success else "",
                    "outcome": "SUCCESS" if success else "ATTEMPT_STARTED",
                    "provider_status": "VALIDATED_SUCCESS" if success else "",
                    "model_pin_valid": success,
                    "overall_success": success,
                    "application_output_valid": success,
                    "response_schema_valid": success,
                    "total_tokens": 100 if success else None,
                }
            )
    ledger.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )

    for lane in pipeline_subject.EXPECTED_LANES:
        lane_root = source / "modular_r4/sections" / lane
        lane_root.mkdir(parents=True)
        payloads = {
            "l2_execution_packet.json": {
                "target_model": _CLAUDE_GENERATOR_MODEL,
                "canonical_provider": "openai",
                "allowed_models": [_CLAUDE_GENERATOR_MODEL],
                "budget": {"max_tokens": 4096},
            },
            "attempt_receipt.json": {
                "tokens_used": 5100,
                "local_check_results": {
                    "model_or_tool_name": _CLAUDE_GENERATOR_MODEL,
                    "provider_lane": "openai",
                },
            },
            "provider_request.json": {
                "provider_requested": "external_openai",
                "model": _OPENAI_GENERATOR_MODEL,
                "max_tokens": 4096,
            },
            "provider_response.json": {
                "provider_requested": "external_openai",
                "provider_attempted": True,
                "provider_available": True,
                "runtime_generation_status": "REAL_LLM",
                "model": _OPENAI_GENERATOR_MODEL,
                "stub": False,
                "provider_response": {
                    "transport_response": {
                        "raw_response": {
                            "usage": {
                                "input_tokens": 5000,
                                "output_tokens": 100,
                                "total_tokens": 5100,
                            }
                        }
                    }
                },
            },
            "l2_handoff_receipt.json": {
                "section_id": lane,
                "model_id_used": _OPENAI_GENERATOR_MODEL,
                "provider_lane_used": "openai",
                "tokens_emitted": 5100,
                "checks": {
                    "model_id_matches": False,
                    "token_budget_pass": False,
                },
                "handoff_status": "FAIL",
            },
        }
        for name, payload in payloads.items():
            (lane_root / name).write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    inventory = pipeline_subject._historical_model_route_inventory(source)
    assert inventory["routing_outcome"] == "FAIL_MODEL_PIN_MISMATCH"
    assert inventory["token_accounting_outcome"] == ("FALSE_FAILURE_TOTAL_VS_OUTPUT")
    assert inventory["apps_research"]["claude_usage_event_count"] == 0
    assert inventory["apps_rg_generation"]["model_mismatch_lane_count"] == 11
    assert (
        inventory["apps_rg_generation"]["recorded_token_budget_failure_lane_count"]
        == 11
    )
    assert (
        inventory["apps_rg_generation"][
            "recomputed_output_token_budget_failure_lane_count"
        ]
        == 0
    )
    assert (
        subject._verify_historical_model_routes(
            inventory_raw=inventory,
            source=source,
        )["status"]
        == "PASS"
    )

    response_path = source / "modular_r4/sections/competencies/provider_response.json"
    tampered = json.loads(response_path.read_text(encoding="utf-8"))
    tampered["model"] = "tampered-model"
    response_path.write_text(
        json.dumps(tampered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        subject.ZeroLlmQualificationError,
        match=r"artifact_(length|digest)_mismatch",
    ):
        subject._verify_historical_model_routes(
            inventory_raw=inventory,
            source=source,
        )


def test_l2_authority_binds_routed_model_before_signing() -> None:
    from apps_rg.runtime.section_model_limits import (
        external_openai_generation_model,
        resolve_section_generation_model,
    )

    assert l2_lane_subject._resolve_authority_model_lane(
        section_id="competencies",
        provider_lane="external_claude",
        model_lane=None,
    ) == resolve_section_generation_model("competencies")
    assert l2_lane_subject._resolve_authority_model_lane(
        section_id="unify_narrative",
        provider_lane="external_openai",
        model_lane=None,
    ) == external_openai_generation_model(section_id="unify_narrative")
    assert (
        l2_lane_subject._resolve_authority_model_lane(
            section_id="competencies",
            provider_lane="external_openai",
            model_lane="explicit-model",
        )
        == "explicit-model"
    )


def test_l2_budget_uses_emitted_tokens_not_input_plus_output_total() -> None:
    response = {
        "provider_response": {
            "transport_response": {
                "raw_response": {
                    "usage": {
                        "input_tokens": 5000,
                        "output_tokens": 100,
                        "total_tokens": 5100,
                    }
                }
            }
        }
    }
    assert l2_authority_subject._token_usage(response) == (100, True)
    assert l2_authority_subject._token_usage({"usage": {"total_tokens": 5100}}) == (
        5100,
        True,
    )


def test_w5_positive_control_runs_production_validators_under_guard(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "saved.json").write_text("{}\n", encoding="utf-8")
    output = tmp_path / "out"
    code = r"""
import importlib.util
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("_w5_positive_subprocess", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
result = module.execute_positive_control(
    source_run=Path(sys.argv[2]),
    output_dir=Path(sys.argv[3]),
)
valid, errors = module.verify_production_positive_control(
    result["manifest_path"]
)
manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
guard = json.loads(result["guard_path"].read_text(encoding="utf-8"))
print(json.dumps({
    "valid": valid,
    "errors": errors,
    "fixture_class": manifest["fixture_class"],
    "validator_count": len(manifest["production_validators"]),
    "fixture_product_authorized": manifest["fixture_product_authorized"],
    "fixture_pipeline_complete": manifest["fixture_pipeline_complete"],
    "production_authority_granted": manifest["production_authority_granted"],
    "publication_allowed": manifest["publication_allowed"],
    "guard_status": guard["status"],
    "attempt_counters": guard["attempt_counters"],
}, sort_keys=True))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT / "src"), environment.get("PYTHONPATH", "")))
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(PIPELINE_PATH),
            str(source),
            str(output),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed == {
        "attempt_counters": {
            "blocked_import_attempts": 0,
            "embedding_calls": 0,
            "judge_calls": 0,
            "model_calls": 0,
            "network_attempts": 0,
            "provider_calls": 0,
            "subprocess_attempts": 0,
        },
        "errors": [],
        "fixture_class": "DETERMINISTIC_GOVERNED_SAVED_OUTPUT",
        "fixture_pipeline_complete": True,
        "fixture_product_authorized": True,
        "guard_status": "PASS",
        "production_authority_granted": False,
        "publication_allowed": False,
        "valid": True,
        "validator_count": 6,
    }


def test_whole_run_exit_import_boundary_remains_provider_free() -> None:
    code = r"""
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

replay_path = Path(sys.argv[1]).resolve()
whole_run_exit_path = Path(sys.argv[2]).resolve()
apps_root = whole_run_exit_path.parents[1]
for name, path in {
    "apps_rg": apps_root,
    "apps_rg.runtime": apps_root / "runtime",
}.items():
    module = ModuleType(name)
    module.__package__ = name
    module.__path__ = [path.as_posix()]
    spec = importlib.machinery.ModuleSpec(name, loader=None, is_package=True)
    spec.submodule_search_locations = [path.as_posix()]
    module.__spec__ = spec
    sys.modules[name] = module

spec = importlib.util.spec_from_file_location("_w5_replay_guard", replay_path)
guard_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard_module
spec.loader.exec_module(guard_module)
guard = guard_module.ZeroProviderReplayGuard()
with guard:
    __import__("apps_rg.runtime.whole_run_exit")
blocked = sorted(
    name for name in sys.modules
    if name == "openai"
    or name.startswith("openai.")
    or name == "anthropic"
    or name.startswith("anthropic.")
    or name.startswith("apps_rg_runtime")
)
print(json.dumps({
    "blocked_modules_loaded": blocked,
    "attempt_counters": guard.counters.to_dict(),
}, sort_keys=True))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(REPO_ROOT / "src"), environment.get("PYTHONPATH", "")))
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(REPLAY_PATH),
            str(WHOLE_RUN_EXIT_PATH),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["blocked_modules_loaded"] == []
    assert all(value == 0 for value in observed["attempt_counters"].values())


def test_w5_modules_are_stdlib_only_and_synthetic_emitters_are_removed() -> None:
    code = r"""
import importlib.util
import json
import sys
from pathlib import Path

for index, raw in enumerate(sys.argv[1:]):
    path = Path(raw).resolve()
    spec = importlib.util.spec_from_file_location(f"_w5_import_{index}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
blocked = sorted(
    name for name in sys.modules
    if name == "openai"
    or name.startswith("openai.")
    or name == "anthropic"
    or name.startswith("anthropic.")
    or name.startswith("apps_rg_runtime")
)
print(json.dumps({"blocked_modules_loaded": blocked}, sort_keys=True))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(QUALIFICATION_PATH),
            str(PIPELINE_PATH),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"blocked_modules_loaded": []}

    qualification_source = QUALIFICATION_PATH.read_text(encoding="utf-8")
    assert "def _emit_positive_control(" not in qualification_source
    assert "def _emit_fault_matrix(" not in qualification_source
    assert "SYNTHETIC_SAVED_OUTPUT" not in qualification_source


def test_w5_cli_pins_this_checkout_ahead_of_ambient_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _load("_w5_cli_path_unit", CLI_PATH)
    local_src = str(REPO_ROOT / "src")
    monkeypatch.setattr(sys, "path", list(sys.path))
    sys.path[:] = [item for item in sys.path if item != local_src]
    sys.path.insert(0, str(REPO_ROOT.parent / "foreign-checkout"))

    cli._pin_local_src()

    assert sys.path[0] == local_src
