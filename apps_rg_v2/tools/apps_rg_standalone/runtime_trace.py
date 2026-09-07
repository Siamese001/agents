"""Run bounded, migration-only import traces against the frozen source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "apps-rg-runtime-trace/v1"
DEFAULT_TIMEOUT_SECONDS = 30
REQUIRED_SCENARIOS = (
    "cli_import_smoke",
    "apps_research_deterministic_handoff",
    "each_generated_lane",
    "serial_11_lane",
    "product_graph_exact_read",
    "product_graph_not_ready",
    "r1a_miss",
    "r1a_compatible_hit",
    "r1b_disabled",
    "patch_run_dependency_expansion",
    "apps_eval",
    "l5_certification",
    "root_exit_x3",
    "uwg_denied_write",
    "uwg_authorized_write_fixture",
    "l7_reconciliation",
    "l6_post_run_boundary",
)


_RUNNER = r'''
import importlib
import json
import os
from pathlib import Path
import sys
import traceback

root = Path(sys.argv[1]).resolve()
work = Path(sys.argv[2]).resolve()
module_name = sys.argv[3]
trace_path = work / "trace.json"
files = []
subprocesses = []
blocked_write_attempts = []
guard_receipts = []
network_attempts = []
dynamic_imports = []

def _inside(path, parent):
    try:
        Path(path).resolve().relative_to(parent)
        return True
    except (OSError, ValueError):
        return False

def _write_mode(args):
    if len(args) > 1 and isinstance(args[1], str):
        return any(flag in args[1] for flag in "wax+")
    if len(args) > 1 and isinstance(args[1], int):
        flags = args[1]
        return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    return False

def _guard(kind, detail):
    guard_receipts.append({"kind": kind, "detail": detail})

def _audit(event, args):
    if event == "import" and args:
        module_name = str(args[0])
        if "adg" in module_name.split("."):
            _guard("forbidden_legacy_import", module_name)
            raise ImportError("migration trace blocks forbidden legacy imports")
    elif event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
        network_attempts.append({"event": event})
        _guard("network_operation", event)
        raise PermissionError("migration trace blocks network operations")
    elif event == "subprocess.Popen":
        subprocesses.append({"args": [str(item) for item in args]})
        _guard("subprocess", event)
        raise PermissionError("migration trace blocks subprocess creation")
    if event in {"open", "os.open"} and args:
        raw_path = args[0]
        if isinstance(raw_path, (str, bytes, os.PathLike)):
            path = Path(raw_path)
            write = _write_mode(args)
            if _inside(path, root) or _inside(path, work):
                files.append({"path": str(path), "intent": "WRITE" if write else "READ"})
            if write and not _inside(path, work):
                blocked_write_attempts.append(str(path))
                _guard("unauthorized_write", str(path))
                raise PermissionError("migration trace blocks writes outside scenario output")
    elif event in {"os.remove", "os.rename", "os.replace", "os.rmdir"}:
        _guard("destructive_filesystem_operation", event)
        raise PermissionError("migration trace blocks destructive filesystem operations")


def _profile(frame, event, arg):
    """Observe source calls to importlib without replacing the import system."""
    if event != "call" or frame.f_code.co_name != "import_module":
        return
    if frame.f_globals.get("__name__") != "importlib":
        return
    caller = frame.f_back
    if caller is None or not _inside(caller.f_code.co_filename, root):
        return
    dynamic_imports.append({
        "module": str(frame.f_locals.get("name", "<unknown>")),
        "package": frame.f_locals.get("package"),
        "caller_module": str(caller.f_globals.get("__name__", "<unknown>")),
        "caller_path": str(Path(caller.f_code.co_filename).resolve()),
    })


sys.addaudithook(_audit)
sys.path.insert(0, str(root))
sys.setprofile(_profile)
status = "PASS"
error = None
try:
    importlib.import_module(module_name)
except BaseException as exc:
    status = "BLOCKED"
    error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
finally:
    sys.setprofile(None)

local_modules = []
third_party_modules = []
for name, module in sorted(sys.modules.items()):
    module_path = getattr(module, "__file__", None)
    if not module_path:
        continue
    if _inside(module_path, root):
        local_modules.append({"module": name, "path": str(Path(module_path).resolve())})
    elif "site-packages" in str(module_path).replace("\\", "/"):
        third_party_modules.append({"module": name, "path": str(module_path)})

trace_path.write_text(json.dumps({
    "status": status,
    "module": module_name,
    "error": error,
    "local_modules": local_modules,
    "third_party_modules": third_party_modules,
    "files": files,
    "dynamic_imports": dynamic_imports,
    "subprocesses": subprocesses,
    "blocked_write_attempts": blocked_write_attempts,
    "guard_receipts": guard_receipts,
    "network_attempts": network_attempts,
    "network": "blocked",
    "forbidden_legacy_imports": "blocked",
}, indent=2, sort_keys=True), encoding="utf-8")
'''

_PREFLIGHT_COMMAND = "import socket; import asyncio; import redis; print('IMPORT_OK')"
_PREFLIGHT_GUARD_COMMAND = (
    "import socket; import asyncio; import redis; "
    "import sys; "
    "sys.addaudithook(lambda event, args: (_ for _ in ()).throw(PermissionError('trace guard denied operation')) "
    "if event in {'socket.connect', 'socket.connect_ex', 'subprocess.Popen'} else None); "
    "print('IMPORT_OK')"
)
WINDOWS_BOOTSTRAP_KEYS = (
    "SYSTEMROOT",
    "WINDIR",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
)
_SECRET_KEY_TOKENS = (
    "ACCESS_TOKEN",
    "API_KEY",
    "AUTH_TOKEN",
    "CREDENTIAL",
    "PASSWORD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)
_LIVE_SELECTION_TOKENS = (
    "ALL_PROXY",
    "ANTHROPIC_",
    "API_BASE",
    "BASE_URL",
    "ENDPOINT",
    "GOOGLE_API",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NETWORK",
    "OPENAI_",
    "PROVIDER",
    "REDIS_",
)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _case_insensitive_get(environment: dict[str, str], name: str) -> str | None:
    for key, value in environment.items():
        if key.upper() == name.upper():
            return value
    return None


def _case_insensitive_set(environment: dict[str, str], name: str, value: str) -> None:
    for key in tuple(environment):
        if key.upper() == name.upper():
            del environment[key]
    environment[name] = value


def _is_sensitive_key(name: str) -> bool:
    upper = name.upper()
    return any(token in upper for token in _SECRET_KEY_TOKENS) or any(
        token in upper for token in _LIVE_SELECTION_TOKENS
    )


def build_child_environment(trace_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Copy the host environment, then explicitly scrub sensitive selection values."""
    environment = os.environ.copy()
    scrubbed = sorted(key for key in environment if _is_sensitive_key(key))
    for key in scrubbed:
        del environment[key]
    _case_insensitive_set(environment, "HOME", str(trace_dir))
    _case_insensitive_set(environment, "NO_PROXY", "*")
    _case_insensitive_set(environment, "PYTHONDONTWRITEBYTECODE", "1")
    _case_insensitive_set(environment, "PYTHONHASHSEED", "0")
    _case_insensitive_set(environment, "TEMP", str(trace_dir))
    _case_insensitive_set(environment, "TMP", str(trace_dir))
    _case_insensitive_set(environment, "TZ", "UTC")
    _case_insensitive_set(environment, "W1_TRACE_OUTPUT_DIR", str(trace_dir))
    missing = [key for key in WINDOWS_BOOTSTRAP_KEYS if _case_insensitive_get(environment, key) is None]
    if missing:
        raise RuntimeError(f"sanitized environment missing Windows bootstrap keys: {', '.join(missing)}")
    return environment, scrubbed


def environment_metadata(environment: dict[str, str], scrubbed: Sequence[str]) -> dict[str, Any]:
    return {
        "environment_key_name_digest": _digest(sorted(environment)),
        "environment_key_count": len(environment),
        "scrubbed_key_name_digest": _digest(sorted(scrubbed)),
        "scrubbed_key_names": sorted(scrubbed),
        "windows_bootstrap_key_names": list(WINDOWS_BOOTSTRAP_KEYS),
    }


def _probe_result(name: str, command: str, environment: dict[str, str], *, guarded: bool) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-c", command],
        env=environment,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        check=False,
    )
    diagnostic = (result.stderr or result.stdout).strip()
    match = re.search(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)): ", diagnostic, re.MULTILINE)
    return {
        "probe": name,
        "command": f"{sys.executable} -c {command!r}",
        "guarded": guarded,
        "exit_code": result.returncode,
        "import_ok": result.returncode == 0 and "IMPORT_OK" in result.stdout,
        "exception_type": match.group(1) if match else None,
        "traceback_digest": _digest({"stdout": result.stdout, "stderr": result.stderr}),
        "environment_key_name_digest": _digest(sorted(environment)),
        "guard_configuration_digest": _digest(
            {"audit_operation_guards": guarded, "source_tree_writes": "blocked", "network": "blocked"}
        ),
    }


def run_trace_harness_preflight(trace_dir: Path) -> dict[str, Any]:
    """Isolate host, sanitization, and operation-guard import failures."""
    inherited = os.environ.copy()
    child_environment, scrubbed = build_child_environment(trace_dir)
    probes = [
        _probe_result("inherited_environment", _PREFLIGHT_COMMAND, inherited, guarded=False),
        _probe_result("sanitized_environment", _PREFLIGHT_COMMAND, child_environment, guarded=False),
        _probe_result("sanitized_environment_with_trace_guards", _PREFLIGHT_GUARD_COMMAND, child_environment, guarded=True),
    ]
    if not probes[0]["import_ok"]:
        classification = "HOST_PYTHON_ENVIRONMENT_BLOCKER"
    elif not probes[1]["import_ok"]:
        classification = "ENVIRONMENT_SANITIZATION_DEFECT"
    elif not probes[2]["import_ok"]:
        classification = "TRACE_GUARD_IMPLEMENTATION_DEFECT"
    else:
        classification = "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "probes": probes,
        "environment": environment_metadata(child_environment, scrubbed),
        "classification": classification,
        "marker": "W1_TRACE_HARNESS_PREFLIGHT_PASS" if classification == "PASS" else None,
        "status": "PASS" if classification == "PASS" else "BLOCKED",
    }


def _git_value(repo_root: Path, args: Sequence[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def trace_import_module(
    repo_root: Path,
    module_name: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Trace one import without modifying the frozen source tree."""
    root = repo_root.resolve()
    with tempfile.TemporaryDirectory(prefix="apps-rg-runtime-trace-") as temp_dir:
        work = Path(temp_dir)
        environment, scrubbed = build_child_environment(work)
        result = subprocess.run(
            [sys.executable, "-I", "-c", _RUNNER, str(root), str(work), module_name],
            cwd=work,
            env=environment,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
        trace_path = work / "trace.json"
        if trace_path.is_file():
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        else:
            trace = {
                "status": "BLOCKED",
                "module": module_name,
                "error": {
                    "type": "TraceRunnerFailure",
                    "message": result.stderr or result.stdout or "trace runner produced no result",
                },
                "local_modules": [],
                "third_party_modules": [],
                "files": [],
                "dynamic_imports": [],
                "subprocesses": [],
                "blocked_write_attempts": [],
                "network_attempts": [],
            }
        trace["subprocess_returncode"] = result.returncode
        trace["subprocess_stdout"] = result.stdout
        trace["subprocess_stderr"] = result.stderr
        trace["environment"] = environment_metadata(environment, scrubbed)
        trace["guard_configuration"] = {
            "forbidden_legacy_imports": "blocked",
            "network_operations": "blocked",
            "source_tree_writes": "blocked",
            "subprocesses": "blocked",
        }
        return trace


def emit_trace_harness_preflight(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    """Emit host/sanitized/guarded import probes without importing product modules."""
    del repo_root
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    preflight = run_trace_harness_preflight(output)
    (output / "runtime_trace_preflight.json").write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return preflight


def redis_transitive_import_record(module_name: str, trace: dict[str, Any]) -> dict[str, Any]:
    """Keep a source runtime Redis import distinct from a target dependency decision."""
    loaded_modules = {str(row["module"]) for row in trace["local_modules"]}
    redis_loaded = any(str(row["module"]) == "redis" for row in trace["third_party_modules"])
    source_client_loaded = "apps_rg.cache.redis_cache_client" in loaded_modules
    loaded = redis_loaded and source_client_loaded
    return {
        "loaded": loaded,
        "classification": "SOURCE_RUNTIME_TRANSITIVE_IMPORT" if loaded else "NOT_LOADED",
        "importing_chain": (
            [
                module_name,
                "apps_rg.runtime.orchestration.canonical_dispatch",
                "apps_rg.cache.redis_cache_client",
                "redis",
            ]
            if loaded and module_name == "apps_rg.__main__"
            else []
        ),
        "network_connection_attempt_count": len(trace["network_attempts"]),
        "target_dependency_disposition": "UNDECIDED_PENDING_APPROVED_PRODUCT_SCENARIO",
        "rationale": "Importing redis initializes no connection; target ownership depends on a later approved behavior scenario.",
    }


def emit_import_smoke_trace(
    repo_root: Path,
    output_dir: Path,
    module_name: str,
    *,
    historical_blocked_import_attempts: int = 0,
) -> dict[str, Any]:
    """Emit the first bounded runtime-trace evidence bundle for the CLI import path."""
    if historical_blocked_import_attempts < 0:
        raise ValueError("historical_blocked_import_attempts must not be negative")
    root = repo_root.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    trace = trace_import_module(root, module_name)
    redis_import = redis_transitive_import_record(module_name, trace)
    scenario_status = str(trace["status"])
    file_reads = [row for row in trace["files"] if row["intent"] == "READ"]
    source_writes = [
        row
        for row in trace["files"]
        if row["intent"] == "WRITE" and Path(str(row["path"])).resolve().is_relative_to(root)
    ]
    assertions = {
        "source_write_count": len(source_writes),
        "network_connection_attempt_count": len(trace["network_attempts"]),
        "subprocess_launch_count": len(trace["subprocesses"]),
        "pass": scenario_status == "PASS"
        and not source_writes
        and not trace["network_attempts"]
        and not trace["subprocesses"],
    }
    scenario_records = [
        {
            "scenario": "cli_import_smoke",
            "status": scenario_status,
            "module": module_name,
            "blocker": trace.get("error"),
        }
    ]
    scenario_records.extend(
        {
            "scenario": scenario,
            "status": "PENDING_NOT_EXECUTED",
            "blocker": {"type": "ContinuationRequired", "message": "scenario fixture not selected yet"},
        }
        for scenario in REQUIRED_SCENARIOS
        if scenario != "cli_import_smoke"
    )
    bundle = {
        "runtime_trace_environment.json": {
            "schema_version": SCHEMA_VERSION,
            "source_commit": _git_value(root, ("rev-parse", "HEAD")),
            "source_tree": _git_value(root, ("rev-parse", "HEAD^{tree}")),
            "fixed_environment": trace["environment"],
            "network": "blocked",
            "forbidden_legacy_imports": "blocked",
            "source_tree_writes": "blocked",
            "status": "PASS",
        },
        "runtime_module_trace.json": {
            "schema_version": SCHEMA_VERSION,
            "method": "isolated_import_smoke_trace",
            "status": "INCOMPLETE",
            "runs": [
                {
                    "scenario": "cli_import_smoke",
                    "status": scenario_status,
                    "local_modules": trace["local_modules"],
                    "third_party_modules": trace["third_party_modules"],
                    "dynamic_imports": trace["dynamic_imports"],
                    "network_connection_attempts": trace["network_attempts"],
                    "redis_transitive_import": redis_import,
                    "error": trace.get("error"),
                    "guard_receipts": trace.get("guard_receipts", []),
                }
            ],
        },
        "runtime_asset_trace.json": {
            "schema_version": SCHEMA_VERSION,
            "status": "INCOMPLETE",
            "runs": [
                {
                    "scenario": "cli_import_smoke",
                    "file_reads": file_reads,
                    "source_writes": source_writes,
                    "blocked_write_attempts": trace["blocked_write_attempts"],
                }
            ],
        },
        "runtime_subprocess_trace.json": {
            "schema_version": SCHEMA_VERSION,
            "status": "INCOMPLETE",
            "runs": [{"scenario": "cli_import_smoke", "subprocesses": trace["subprocesses"]}],
        },
        "runtime_trace_scenario_rollup.json": {
            "schema_version": SCHEMA_VERSION,
            "required_scenario_count": len(REQUIRED_SCENARIOS),
            "attempted_scenario_count": 1 + historical_blocked_import_attempts,
            "completed_scenario_count": 1 if scenario_status == "PASS" else 0,
            "passed_scenario_count": 1 if scenario_status == "PASS" else 0,
            "blocked_scenario_count": historical_blocked_import_attempts + (0 if scenario_status == "PASS" else 1),
            "pending_scenario_count": len(REQUIRED_SCENARIOS) - 1,
            "executed_scenario_count": 1 if scenario_status == "PASS" else 0,
            "historical_blocked_import_attempt_count": historical_blocked_import_attempts,
            "assertions": assertions,
            "marker": "W1_RUNTIME_IMPORT_SMOKE_PASS" if assertions["pass"] else None,
            "scenarios": scenario_records,
            "status": "INCOMPLETE",
        },
    }
    for name, payload in bundle.items():
        (output / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--module", default="apps_rg.__main__")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--historical-blocked-import-attempts", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    preflight = emit_trace_harness_preflight(args.repo_root, args.output_dir)
    if args.preflight_only or preflight["status"] != "PASS":
        print(json.dumps({"preflight": preflight["status"], "classification": preflight["classification"]}, sort_keys=True))
        return 0
    bundle = emit_import_smoke_trace(
        args.repo_root,
        args.output_dir,
        args.module,
        historical_blocked_import_attempts=args.historical_blocked_import_attempts,
    )
    print(
        json.dumps(
            {
                "scenario": "cli_import_smoke",
                "status": bundle["runtime_module_trace.json"]["runs"][0]["status"],
                "marker": bundle["runtime_trace_scenario_rollup.json"]["marker"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
