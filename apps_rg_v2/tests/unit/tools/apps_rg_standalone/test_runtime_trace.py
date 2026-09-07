from __future__ import annotations

import json
from pathlib import Path

from tools.apps_rg_standalone.runtime_trace import (
    WINDOWS_BOOTSTRAP_KEYS,
    build_child_environment,
    emit_import_smoke_trace,
    emit_trace_harness_preflight,
    redis_transitive_import_record,
    run_trace_harness_preflight,
    trace_import_module,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_trace_import_module_captures_local_module_without_source_writes(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "VALUE = 1\n")

    trace = trace_import_module(tmp_path, "demo")

    assert trace["status"] == "PASS"
    assert {row["module"] for row in trace["local_modules"]} >= {"demo"}
    assert not trace["blocked_write_attempts"]
    assert not trace["dynamic_imports"]


def test_emit_import_smoke_trace_writes_incomplete_scenario_rollup(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "")
    output = tmp_path / "out"

    bundle = emit_import_smoke_trace(
        tmp_path,
        output,
        "demo",
        historical_blocked_import_attempts=1,
    )
    rollup = json.loads((output / "runtime_trace_scenario_rollup.json").read_text(encoding="utf-8"))

    assert bundle["runtime_trace_environment.json"]["source_tree_writes"] == "blocked"
    assert rollup["required_scenario_count"] == 17
    assert rollup["attempted_scenario_count"] == 2
    assert rollup["completed_scenario_count"] == 1
    assert rollup["blocked_scenario_count"] == 1
    assert rollup["executed_scenario_count"] == 1
    assert rollup["marker"] == "W1_RUNTIME_IMPORT_SMOKE_PASS"
    assert rollup["assertions"] == {
        "source_write_count": 0,
        "network_connection_attempt_count": 0,
        "subprocess_launch_count": 0,
        "pass": True,
    }
    assert rollup["status"] == "INCOMPLETE"


def test_trace_harness_preflight_imports_redis_in_all_three_environments(tmp_path: Path) -> None:
    preflight = run_trace_harness_preflight(tmp_path)

    assert preflight["status"] == "PASS"
    assert preflight["marker"] == "W1_TRACE_HARNESS_PREFLIGHT_PASS"
    assert all(probe["import_ok"] for probe in preflight["probes"])
    assert preflight["probes"][2]["command"] != preflight["probes"][1]["command"]


def test_sanitized_environment_preserves_windows_bootstrap_keys_and_hides_secret_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-emit-this-value")

    environment, scrubbed = build_child_environment(tmp_path)
    evidence = json.dumps(emit_trace_harness_preflight(tmp_path, tmp_path / "evidence"), sort_keys=True)

    assert all(any(key.upper() == required for key in environment) for required in WINDOWS_BOOTSTRAP_KEYS)
    assert "OPENAI_API_KEY" in scrubbed
    assert "OPENAI_API_KEY" not in environment
    assert "do-not-emit-this-value" not in evidence


def test_trace_guard_allows_importing_redis_without_a_network_attempt(tmp_path: Path) -> None:
    _write(tmp_path / "demo" / "__init__.py", "import redis\n")

    trace = trace_import_module(tmp_path, "demo")

    assert trace["status"] == "PASS"
    assert not [receipt for receipt in trace["guard_receipts"] if receipt["kind"] == "network_operation"]
    assert not trace["network_attempts"]


def test_redis_transitive_import_does_not_decide_target_dependency() -> None:
    record = redis_transitive_import_record(
        "apps_rg.__main__",
        {
            "local_modules": [{"module": "apps_rg.cache.redis_cache_client"}],
            "third_party_modules": [{"module": "redis"}],
            "network_attempts": [],
        },
    )

    assert record["classification"] == "SOURCE_RUNTIME_TRANSITIVE_IMPORT"
    assert record["importing_chain"][-2:] == ["apps_rg.cache.redis_cache_client", "redis"]
    assert record["network_connection_attempt_count"] == 0
    assert record["target_dependency_disposition"] == "UNDECIDED_PENDING_APPROVED_PRODUCT_SCENARIO"


def test_trace_records_source_dynamic_imports_separately(tmp_path: Path) -> None:
    _write(tmp_path / "dynamic_demo" / "child.py", "VALUE = 1\n")
    _write(
        tmp_path / "dynamic_demo" / "__init__.py",
        "import importlib\nimportlib.import_module('dynamic_demo.child')\n",
    )

    trace = trace_import_module(tmp_path, "dynamic_demo")

    assert trace["status"] == "PASS"
    assert trace["dynamic_imports"] == [
        {
            "module": "dynamic_demo.child",
            "package": None,
            "caller_module": "dynamic_demo",
            "caller_path": str((tmp_path / "dynamic_demo" / "__init__.py").resolve()),
        }
    ]


def test_trace_guard_blocks_outbound_socket_subprocess_and_source_write(tmp_path: Path) -> None:
    _write(
        tmp_path / "socket_demo" / "__init__.py",
        "import socket\nsocket.create_connection(('127.0.0.1', 9), timeout=0.1)\n",
    )
    _write(
        tmp_path / "subprocess_demo" / "__init__.py",
        "import subprocess\nsubprocess.run(['cmd', '/c', 'exit', '0'])\n",
    )
    _write(
        tmp_path / "write_demo" / "__init__.py",
        "from pathlib import Path\n(Path(__file__).parent / 'forbidden.txt').write_text('x')\n",
    )

    socket_trace = trace_import_module(tmp_path, "socket_demo")
    subprocess_trace = trace_import_module(tmp_path, "subprocess_demo")
    write_trace = trace_import_module(tmp_path, "write_demo")

    assert socket_trace["status"] == "BLOCKED"
    assert subprocess_trace["status"] == "BLOCKED"
    assert write_trace["status"] == "BLOCKED"
    assert any(receipt["kind"] == "network_operation" for receipt in socket_trace["guard_receipts"])
    assert any(receipt["kind"] == "subprocess" for receipt in subprocess_trace["guard_receipts"])
    assert any(receipt["kind"] == "unauthorized_write" for receipt in write_trace["guard_receipts"])
    assert not (tmp_path / "write_demo" / "forbidden.txt").exists()


def test_trace_guard_allows_writes_inside_trace_output_directory(tmp_path: Path) -> None:
    _write(
        tmp_path / "output_demo" / "__init__.py",
        "import os\nfrom pathlib import Path\n"
        "(Path(os.environ['W1_TRACE_OUTPUT_DIR']) / 'allowed.txt').write_text('ok')\n",
    )

    trace = trace_import_module(tmp_path, "output_demo")

    assert trace["status"] == "PASS"
    assert any(event["intent"] == "WRITE" for event in trace["files"])
    assert not trace["blocked_write_attempts"]
