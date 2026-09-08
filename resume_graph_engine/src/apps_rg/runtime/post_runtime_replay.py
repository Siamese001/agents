"""Zero-provider safety boundary for post-runtime artifact replay.

Wave 0 intentionally does not run Apps Eval or L6.  It establishes the
process and filesystem boundary those later replay stages must execute inside:

* the source run is byte-manifested before and after the guarded operation;
* provider credentials are absent while the guard is active;
* provider/model SDK imports, sockets, and subprocess escape paths fail closed;
* all derived evidence is written outside the source run.

The guard is defense in depth for a dedicated replay subprocess.  Later waves
must call :meth:`ZeroProviderReplayGuard.block_attempt` at app-owned provider,
judge, and embedding entry points as an additional explicit tripwire.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import json
import os
import socket
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Iterable, Mapping, Sequence


W0_SOURCE_MANIFEST_SCHEMA = "apps_rg.post_runtime_replay_source_manifest.v1"
W0_RECEIPT_SCHEMA = "apps_rg.post_runtime_zero_provider_preflight.v1"
W0_RECEIPT_FILENAME = "w0_zero_provider_preflight_receipt.json"
W0_SOURCE_MANIFEST_FILENAME = "source_manifest.json"
GUARDED_REPLAY_RECEIPT_SCHEMA = "apps_rg.post_runtime_zero_provider_replay.v1"

NO_PROVIDER_ENV = "APPS_RG_POST_RUNTIME_NO_PROVIDER"

_CREDENTIAL_KEYS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "APPS_RG_ROUTE_HMAC_SECRET",
        "AZURE_OPENAI_API_KEY",
        "COHERE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "MISTRAL_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "TOGETHER_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
    }
)

_FORCED_OFFLINE_ENV: Mapping[str, str] = {
    NO_PROVIDER_ENV: "1",
    "APPS_EVAL_WITH_JUDGE": "0",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
}

DEFAULT_FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "anthropic",
    "openai",
    "litellm",
    "sentence_transformers",
    "transformers",
    "vllm",
    "llama_cpp",
    "google.generativeai",
    "google.genai",
    "apps_research.integrations.llm_client",
    "apps_research.integrations.provider_gateway",
    "apps_research.engines",
    "apps_rg.enforcement.HardenedanthropicexecutorStrategy",
    "apps_rg.cache.r1b_bge_embedding",
    "apps_rg.runtime.providers",
    "apps_rg.runtime.judges",
    "apps_rg.runtime.sections.section_generation",
    "apps_rg.L2_execution.utils.write_gateway",
    "apps_rg.L4_state.uwg",
    "apps_rg.L4_state.enforcement.promotion_write_gateway",
)


class PostRuntimeReplaySafetyError(RuntimeError):
    """Base error for a W0 replay-safety violation."""


class ProviderExecutionBlocked(PostRuntimeReplaySafetyError):
    """Raised before a provider, model, judge, or embedding path can execute."""


class NetworkExecutionBlocked(PostRuntimeReplaySafetyError):
    """Raised before a socket or DNS operation can execute."""


class SubprocessExecutionBlocked(PostRuntimeReplaySafetyError):
    """Raised before a child process can execute."""


class SourceRunMutationDetected(PostRuntimeReplaySafetyError):
    """Raised when the source-run file tree changes during replay."""


@dataclass(slots=True)
class ReplayAttemptCounters:
    provider_calls: int = 0
    model_calls: int = 0
    judge_calls: int = 0
    embedding_calls: int = 0
    network_attempts: int = 0
    subprocess_attempts: int = 0
    blocked_import_attempts: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _filesystem_path(path: Path) -> Path:
    """Return an extended-length path for Windows filesystem operations."""

    absolute = Path(os.path.abspath(path))
    raw = str(absolute)
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        return Path("\\\\?\\" + raw)
    return absolute


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with _filesystem_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    return bool(is_junction and is_junction(path))


def _contained_resolved_path(root: Path, path: Path) -> Path:
    # Every traversed link/junction is rejected separately, so lexical
    # containment is sufficient and avoids Path.resolve() failing on valid
    # historical Windows artifact paths longer than MAX_PATH.
    absolute = Path(os.path.abspath(path))
    if not _is_relative_to(absolute, root):
        raise PostRuntimeReplaySafetyError(
            f"source artifact escapes the source run: {path}"
        )
    filesystem_path = _filesystem_path(absolute)
    if not filesystem_path.exists():
        raise FileNotFoundError(str(absolute))
    return filesystem_path


def build_source_manifest(source_run: Path | str) -> dict[str, Any]:
    """Return a deterministic byte manifest without following links/junctions."""

    root = Path(source_run).resolve(strict=True)
    if not root.is_dir():
        raise PostRuntimeReplaySafetyError(f"source run is not a directory: {root}")
    if _is_link_or_junction(root):
        raise PostRuntimeReplaySafetyError("source run cannot be a link or junction")

    directories: list[str] = []
    files: list[dict[str, Any]] = []
    for current_raw, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(current_raw)
        _contained_resolved_path(root, current)
        relative_current = current.relative_to(root).as_posix()
        if relative_current != ".":
            directories.append(relative_current)

        for dirname in sorted(dirnames):
            candidate = current / dirname
            if _is_link_or_junction(candidate):
                raise PostRuntimeReplaySafetyError(
                    f"source run contains a linked directory: "
                    f"{candidate.relative_to(root).as_posix()}"
                )
        for filename in sorted(filenames):
            candidate = current / filename
            if _is_link_or_junction(candidate):
                raise PostRuntimeReplaySafetyError(
                    f"source run contains a linked file: "
                    f"{candidate.relative_to(root).as_posix()}"
                )
            resolved = _contained_resolved_path(root, candidate)
            files.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "byte_length": resolved.stat().st_size,
                    "sha256": _sha256_file(resolved),
                }
            )

    directories.sort()
    files.sort(key=lambda row: str(row["path"]))
    content = {"directories": directories, "files": files}
    return {
        "schema_version": W0_SOURCE_MANIFEST_SCHEMA,
        "source_run_id": root.name,
        "directory_count": len(directories),
        "file_count": len(files),
        "total_bytes": sum(int(row["byte_length"]) for row in files),
        "content_sha256": _canonical_digest(content),
        **content,
    }


def compare_source_manifests(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Return an explicit source-tree delta suitable for a durable receipt."""

    before_files = {
        str(row.get("path") or ""): row
        for row in before.get("files", [])
        if isinstance(row, Mapping)
    }
    after_files = {
        str(row.get("path") or ""): row
        for row in after.get("files", [])
        if isinstance(row, Mapping)
    }
    before_dirs = {str(item) for item in before.get("directories", [])}
    after_dirs = {str(item) for item in after.get("directories", [])}
    changed = sorted(
        path
        for path in before_files.keys() & after_files.keys()
        if before_files[path] != after_files[path]
    )
    return {
        "unchanged": before.get("content_sha256") == after.get("content_sha256"),
        "before_content_sha256": str(before.get("content_sha256") or ""),
        "after_content_sha256": str(after.get("content_sha256") or ""),
        "added_files": sorted(after_files.keys() - before_files.keys()),
        "removed_files": sorted(before_files.keys() - after_files.keys()),
        "changed_files": changed,
        "added_directories": sorted(after_dirs - before_dirs),
        "removed_directories": sorted(before_dirs - after_dirs),
    }


def _classify_forbidden_import(fullname: str) -> str:
    model_markers = (
        "sentence_transformers",
        "transformers",
        "vllm",
        "llama_cpp",
    )
    return "model" if fullname.startswith(model_markers) else "provider"


class _ForbiddenImportFinder(importlib.abc.MetaPathFinder):
    def __init__(self, guard: "ZeroProviderReplayGuard") -> None:
        self._guard = guard

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: object | None = None,
    ) -> None:
        del path, target
        if self._guard.import_is_forbidden(fullname):
            importers: list[str] = []
            frame = sys._getframe(1)
            while frame is not None:
                module_name = str(frame.f_globals.get("__name__") or "")
                module_location = (
                    f"{module_name}:{frame.f_lineno}@{frame.f_code.co_filename}"
                )
                if (
                    module_name
                    and not module_name.startswith("importlib")
                    and not module_name.startswith("_frozen_importlib")
                    and module_location not in importers
                ):
                    importers.append(module_location)
                    if len(importers) == 20:
                        break
                frame = frame.f_back
            importer = ">".join(importers) or "unknown"
            self._guard.counters.blocked_import_attempts += 1
            self._guard.block_attempt(
                _classify_forbidden_import(fullname),
                f"import:{fullname}:requested_by:{importer}",
            )
        return None


class ZeroProviderReplayGuard:
    """Process-local, fail-closed boundary for a dedicated replay subprocess."""

    def __init__(
        self,
        *,
        forbidden_import_prefixes: Iterable[str] = DEFAULT_FORBIDDEN_IMPORT_PREFIXES,
        allowed_subprocess_commands: Iterable[Sequence[str]] = (),
    ) -> None:
        self.forbidden_import_prefixes = tuple(
            sorted(
                {
                    str(prefix).strip()
                    for prefix in forbidden_import_prefixes
                    if str(prefix).strip()
                }
            )
        )
        self.allowed_subprocess_commands = {
            tuple(str(item) for item in command)
            for command in allowed_subprocess_commands
        }
        self.counters = ReplayAttemptCounters()
        self.credentials_scrubbed: list[str] = []
        self.preloaded_forbidden_modules: list[str] = []
        self._saved_environment: dict[str, str | None] = {}
        self._saved_functions: dict[str, Any] = {}
        self._finder = _ForbiddenImportFinder(self)
        self._active = False

    def import_is_forbidden(self, fullname: str) -> bool:
        return any(
            fullname == prefix or fullname.startswith(prefix + ".")
            for prefix in self.forbidden_import_prefixes
        )

    def block_attempt(self, category: str, component: str) -> None:
        normalized = str(category).strip().lower()
        counter_by_category = {
            "provider": "provider_calls",
            "model": "model_calls",
            "judge": "judge_calls",
            "embedding": "embedding_calls",
        }
        counter = counter_by_category.get(normalized)
        if counter is None:
            raise ValueError(f"unknown zero-provider attempt category: {category!r}")
        setattr(self.counters, counter, getattr(self.counters, counter) + 1)
        raise ProviderExecutionBlocked(
            f"{normalized} execution is forbidden during post-runtime replay: {component}"
        )

    def _block_network(self, component: str) -> None:
        self.counters.network_attempts += 1
        raise NetworkExecutionBlocked(
            f"network execution is forbidden during post-runtime replay: {component}"
        )

    def _command_allowed(self, command: object, *, shell: bool) -> bool:
        if shell or isinstance(command, (str, bytes)):
            return False
        try:
            normalized = tuple(str(item) for item in command)  # type: ignore[arg-type]
        except TypeError:
            return False
        return normalized in self.allowed_subprocess_commands

    def _install_environment(self) -> None:
        touched = set(_CREDENTIAL_KEYS) | set(_FORCED_OFFLINE_ENV)
        self._saved_environment = {key: os.environ.get(key) for key in touched}
        self.credentials_scrubbed = sorted(
            key for key in _CREDENTIAL_KEYS if str(os.environ.get(key) or "").strip()
        )
        for key in _CREDENTIAL_KEYS:
            os.environ.pop(key, None)
        for key, value in _FORCED_OFFLINE_ENV.items():
            os.environ[key] = value

    def _restore_environment(self) -> None:
        for key, value in self._saved_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _install_execution_blocks(self) -> None:
        self._saved_functions = {
            "socket.socket.connect": socket.socket.connect,
            "socket.socket.connect_ex": socket.socket.connect_ex,
            "socket.create_connection": socket.create_connection,
            "socket.getaddrinfo": socket.getaddrinfo,
            "subprocess.Popen": subprocess.Popen,
            "os.system": os.system,
            "os.popen": os.popen,
        }
        guard = self

        def blocked_connect(_socket: socket.socket, address: object) -> None:
            guard._block_network(f"socket.connect:{address!r}")

        def blocked_connect_ex(_socket: socket.socket, address: object) -> int:
            guard._block_network(f"socket.connect_ex:{address!r}")
            return 1  # pragma: no cover - block always raises

        def blocked_create_connection(*args: Any, **kwargs: Any) -> socket.socket:
            del kwargs
            address = args[0] if args else "<unknown>"
            guard._block_network(f"socket.create_connection:{address!r}")
            raise AssertionError("unreachable")  # pragma: no cover

        def blocked_getaddrinfo(*args: Any, **kwargs: Any) -> list[Any]:
            del kwargs
            host = args[0] if args else "<unknown>"
            guard._block_network(f"socket.getaddrinfo:{host!r}")
            return []  # pragma: no cover - block always raises

        original_popen = subprocess.Popen

        class GuardedPopen(original_popen):
            """Subclass-compatible Popen tripwire for import-time consumers."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                command = args[0] if args else kwargs.get("args")
                shell = bool(kwargs.get("shell"))
                if not guard._command_allowed(command, shell=shell):
                    guard.counters.subprocess_attempts += 1
                    raise SubprocessExecutionBlocked(
                        "subprocess execution is forbidden during post-runtime "
                        f"replay: {command!r}"
                    )
                super().__init__(*args, **kwargs)

        def blocked_os_process(*args: Any, **kwargs: Any) -> Any:
            del kwargs
            command = args[0] if args else "<unknown>"
            guard.counters.subprocess_attempts += 1
            raise SubprocessExecutionBlocked(
                f"shell execution is forbidden during post-runtime replay: {command!r}"
            )

        socket.socket.connect = blocked_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = blocked_connect_ex  # type: ignore[method-assign]
        socket.create_connection = blocked_create_connection
        socket.getaddrinfo = blocked_getaddrinfo
        subprocess.Popen = GuardedPopen  # type: ignore[assignment]
        os.system = blocked_os_process  # type: ignore[assignment]
        os.popen = blocked_os_process  # type: ignore[assignment]

    def _restore_execution_blocks(self) -> None:
        socket.socket.connect = self._saved_functions["socket.socket.connect"]
        socket.socket.connect_ex = self._saved_functions["socket.socket.connect_ex"]
        socket.create_connection = self._saved_functions["socket.create_connection"]
        socket.getaddrinfo = self._saved_functions["socket.getaddrinfo"]
        subprocess.Popen = self._saved_functions["subprocess.Popen"]
        os.system = self._saved_functions["os.system"]
        os.popen = self._saved_functions["os.popen"]

    def __enter__(self) -> "ZeroProviderReplayGuard":
        if self._active:
            raise PostRuntimeReplaySafetyError(
                "zero-provider replay guard is already active"
            )
        self.preloaded_forbidden_modules = sorted(
            name for name in sys.modules if self.import_is_forbidden(name)
        )
        # Repository test bootstrap may import an SDK for type/fixture setup.
        # Presence is evidence, not execution.  Calls remain blocked by the
        # credential, socket, subprocess, and explicit entry-point tripwires;
        # new forbidden imports are blocked by the meta-path finder below.
        self._install_environment()
        self._install_execution_blocks()
        sys.meta_path.insert(0, self._finder)
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        if self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)
        self._restore_execution_blocks()
        self._restore_environment()
        self._active = False


def _validate_disjoint_roots(source_run: Path, output_root: Path) -> None:
    if _is_relative_to(output_root, source_run):
        raise PostRuntimeReplaySafetyError(
            "replay output root must not be inside the immutable source run"
        )
    if _is_relative_to(source_run, output_root):
        raise PostRuntimeReplaySafetyError(
            "replay output root must not contain the immutable source run"
        )


def _safe_component(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value
    ).strip("_")
    return normalized or "run"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:12]}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def run_guarded_artifact_replay(
    *,
    source_run: Path | str,
    output_root: Path | str,
    wave: str,
    operation: Callable[[Path, Path], Mapping[str, Any]],
    receipt_filename: str,
    require_clean_import_state: bool = False,
    expected_activity: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Run one deterministic artifact callback inside the W0 safety boundary.

    The callback receives the immutable source root and a derived-output
    directory outside that root.  Provider, judge, embedding, network, and
    subprocess escape paths remain blocked.  Deterministic Eval or later
    artifact-only stages must declare their expected activity explicitly.
    """

    source = Path(source_run).resolve(strict=True)
    output = Path(output_root).resolve()
    _validate_disjoint_roots(source, output)
    before = build_source_manifest(source)
    content_digest = str(before["content_sha256"])
    replay_id = (
        f"{_safe_component(source.name)}_{content_digest.removeprefix('sha256:')[:16]}"
    )
    normalized_wave = _safe_component(wave).upper()
    replay_dir = output / replay_id
    operation_dir = replay_dir / normalized_wave.lower()

    guard = ZeroProviderReplayGuard()
    operation_error: BaseException | None = None
    operation_result: Mapping[str, Any] = {}
    try:
        with guard:
            operation_result = operation(source, operation_dir)
            if not isinstance(operation_result, Mapping):
                raise PostRuntimeReplaySafetyError(
                    "guarded artifact operation must return a mapping"
                )
    except BaseException as exc:  # noqa: BLE001 - receipt must preserve any failure
        operation_error = exc

    after = build_source_manifest(source)
    source_delta = compare_source_manifests(before, after)
    counters = guard.counters.to_dict()
    zero_attempts = all(value == 0 for value in counters.values())
    clean_import_state = not guard.preloaded_forbidden_modules
    completion = operation_result.get("completion")
    completion = dict(completion) if isinstance(completion, Mapping) else {}
    operation_pass = completion.get("status") == "PASS"
    default_activity = {
        "apps_eval_executed": False,
        "l6_executed": False,
        "uwg_operation_attempted": False,
    }
    expected = {
        **default_activity,
        **{
            key: bool(value)
            for key, value in dict(expected_activity or {}).items()
            if key in default_activity
        },
    }
    raw_activity = operation_result.get("activity")
    raw_activity = dict(raw_activity) if isinstance(raw_activity, Mapping) else {}
    observed_activity = {
        key: bool(raw_activity.get(key, False)) for key in default_activity
    }
    activity_matches = observed_activity == expected
    status = (
        "PASS"
        if (
            operation_error is None
            and operation_pass
            and source_delta["unchanged"]
            and zero_attempts
            and activity_matches
            and (clean_import_state or not require_clean_import_state)
        )
        else "FAIL"
    )
    receipt: dict[str, Any] = {
        "schema_version": GUARDED_REPLAY_RECEIPT_SCHEMA,
        "wave": normalized_wave,
        "status": status,
        "replay_id": replay_id,
        "replay_mode": "POST_RUNTIME_ARTIFACT_ONLY",
        "source_run": source.as_posix(),
        "source_run_id": source.name,
        "source_manifest_ref": f"../{W0_SOURCE_MANIFEST_FILENAME}",
        "source_manifest_sha256": content_digest,
        "source_file_count": int(before["file_count"]),
        "source_total_bytes": int(before["total_bytes"]),
        "source_unchanged": bool(source_delta["unchanged"]),
        "source_delta": source_delta,
        "credentials_scrubbed": guard.credentials_scrubbed,
        "forced_offline_environment": dict(_FORCED_OFFLINE_ENV),
        "forbidden_import_prefixes": list(guard.forbidden_import_prefixes),
        "preloaded_forbidden_modules": guard.preloaded_forbidden_modules,
        "clean_import_state_required": require_clean_import_state,
        "clean_import_state": clean_import_state,
        "attempt_counters": counters,
        "provider_calls": counters["provider_calls"],
        "judge_calls": counters["judge_calls"],
        "embedding_calls": counters["embedding_calls"],
        "model_calls": counters["model_calls"],
        "network_attempts": counters["network_attempts"],
        "subprocess_attempts": counters["subprocess_attempts"],
        "model_span_delta": 0,
        "model_span_delta_source": "zero_provider_process_guard",
        "activity_expectation": expected,
        "activity_observed": observed_activity,
        "activity_matches": activity_matches,
        "apps_eval_executed": observed_activity["apps_eval_executed"],
        "l6_executed": observed_activity["l6_executed"],
        "uwg_operation_attempted": observed_activity[
            "uwg_operation_attempted"
        ],
        "operation_completion_status": str(completion.get("status") or ""),
        "operation_completion_semantic_digest": str(
            completion.get("semantic_digest") or ""
        ),
        "scope_complete": status == "PASS",
        "next_wave_authorized": status == "PASS",
        "operation_error": (
            {
                "type": type(operation_error).__name__,
                "message": str(operation_error)[:2000],
            }
            if operation_error is not None
            else None
        ),
    }
    receipt["semantic_digest"] = _canonical_digest(receipt)
    _atomic_write_json(replay_dir / W0_SOURCE_MANIFEST_FILENAME, before)
    _atomic_write_json(operation_dir / receipt_filename, receipt)

    if not source_delta["unchanged"]:
        raise SourceRunMutationDetected(
            f"source run changed during {normalized_wave} replay: {source_delta}"
        )
    if operation_error is not None:
        raise PostRuntimeReplaySafetyError(
            f"{normalized_wave} guarded operation failed: "
            f"{type(operation_error).__name__}: {operation_error}"
        ) from operation_error
    if require_clean_import_state and not clean_import_state:
        raise PostRuntimeReplaySafetyError(
            f"{normalized_wave} replay process preloaded forbidden modules: "
            + ",".join(guard.preloaded_forbidden_modules[:20])
        )
    if not zero_attempts:
        raise PostRuntimeReplaySafetyError(
            f"{normalized_wave} zero-provider counters were non-zero: {counters}"
        )
    if not activity_matches:
        raise PostRuntimeReplaySafetyError(
            f"{normalized_wave} activity mismatch: expected={expected} "
            f"observed={observed_activity}"
        )
    if not operation_pass:
        raise PostRuntimeReplaySafetyError(
            f"{normalized_wave} artifact operation did not complete: {completion}"
        )
    return {
        **receipt,
        "receipt_path": (operation_dir / receipt_filename).as_posix(),
        "operation_dir": operation_dir.as_posix(),
        "operation_result": dict(operation_result),
    }


def run_w0_zero_provider_preflight(
    *,
    source_run: Path | str,
    output_root: Path | str,
    require_clean_import_state: bool = False,
) -> dict[str, Any]:
    """Prove the W0 replay boundary without executing Apps Eval or L6."""

    source = Path(source_run).resolve(strict=True)
    output = Path(output_root).resolve()
    _validate_disjoint_roots(source, output)
    before = build_source_manifest(source)
    content_digest = str(before["content_sha256"])
    replay_id = (
        f"{_safe_component(source.name)}_{content_digest.removeprefix('sha256:')[:16]}"
    )
    replay_dir = output / replay_id

    guard = ZeroProviderReplayGuard()
    operation_error: BaseException | None = None
    try:
        with guard:
            # W0 deliberately performs no post-runtime operation.  W2/W3 will
            # execute deterministic Apps Eval/L6 callbacks inside this guard.
            pass
    except BaseException as exc:  # noqa: BLE001 - persist any safety-boundary failure
        operation_error = exc

    after = build_source_manifest(source)
    source_delta = compare_source_manifests(before, after)
    counters = guard.counters.to_dict()
    zero_attempts = all(value == 0 for value in counters.values())
    clean_import_state = not guard.preloaded_forbidden_modules
    status = (
        "PASS"
        if (
            operation_error is None
            and source_delta["unchanged"]
            and zero_attempts
            and (clean_import_state or not require_clean_import_state)
        )
        else "FAIL"
    )
    manifest_path = replay_dir / W0_SOURCE_MANIFEST_FILENAME
    receipt_path = replay_dir / W0_RECEIPT_FILENAME
    receipt: dict[str, Any] = {
        "schema_version": W0_RECEIPT_SCHEMA,
        "wave": "W0",
        "status": status,
        "replay_id": replay_id,
        "replay_mode": "POST_RUNTIME_ARTIFACT_ONLY",
        "source_run": source.as_posix(),
        "source_run_id": source.name,
        "source_manifest_ref": W0_SOURCE_MANIFEST_FILENAME,
        "source_manifest_sha256": content_digest,
        "source_file_count": int(before["file_count"]),
        "source_total_bytes": int(before["total_bytes"]),
        "source_unchanged": bool(source_delta["unchanged"]),
        "source_delta": source_delta,
        "credentials_scrubbed": guard.credentials_scrubbed,
        "forced_offline_environment": dict(_FORCED_OFFLINE_ENV),
        "forbidden_import_prefixes": list(guard.forbidden_import_prefixes),
        "preloaded_forbidden_modules": guard.preloaded_forbidden_modules,
        "clean_import_state_required": require_clean_import_state,
        "clean_import_state": clean_import_state,
        "attempt_counters": counters,
        "provider_calls": counters["provider_calls"],
        "judge_calls": counters["judge_calls"],
        "embedding_calls": counters["embedding_calls"],
        "model_calls": counters["model_calls"],
        "network_attempts": counters["network_attempts"],
        "subprocess_attempts": counters["subprocess_attempts"],
        "model_span_delta": 0,
        "model_span_delta_source": "zero_provider_process_guard",
        "apps_eval_executed": False,
        "l6_executed": False,
        "w0_scope_complete": status == "PASS",
        "next_wave_authorized": status == "PASS",
        "operation_error": (
            {
                "type": type(operation_error).__name__,
                "message": str(operation_error)[:2000],
            }
            if operation_error is not None
            else None
        ),
    }
    semantic_body = dict(receipt)
    receipt["semantic_digest"] = _canonical_digest(semantic_body)
    _atomic_write_json(manifest_path, before)
    _atomic_write_json(receipt_path, receipt)

    if not source_delta["unchanged"]:
        raise SourceRunMutationDetected(
            f"source run changed during W0 replay preflight: {source_delta}"
        )
    if operation_error is not None:
        raise PostRuntimeReplaySafetyError(
            f"W0 zero-provider boundary failed: {type(operation_error).__name__}: "
            f"{operation_error}"
        ) from operation_error
    if require_clean_import_state and not clean_import_state:
        raise PostRuntimeReplaySafetyError(
            "W0 replay process preloaded forbidden provider/model modules: "
            + ",".join(guard.preloaded_forbidden_modules[:20])
        )
    if not zero_attempts:
        raise PostRuntimeReplaySafetyError(
            f"W0 zero-provider attempt counters were non-zero: {counters}"
        )
    return {**receipt, "receipt_path": receipt_path.as_posix()}


__all__ = [
    "DEFAULT_FORBIDDEN_IMPORT_PREFIXES",
    "GUARDED_REPLAY_RECEIPT_SCHEMA",
    "NetworkExecutionBlocked",
    "NO_PROVIDER_ENV",
    "PostRuntimeReplaySafetyError",
    "ProviderExecutionBlocked",
    "ReplayAttemptCounters",
    "SourceRunMutationDetected",
    "SubprocessExecutionBlocked",
    "W0_RECEIPT_FILENAME",
    "W0_RECEIPT_SCHEMA",
    "W0_SOURCE_MANIFEST_FILENAME",
    "ZeroProviderReplayGuard",
    "build_source_manifest",
    "compare_source_manifests",
    "run_guarded_artifact_replay",
    "run_w0_zero_provider_preflight",
]
