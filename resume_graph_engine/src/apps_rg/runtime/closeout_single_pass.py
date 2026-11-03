"""Single-pass closeout hashing, diagnostic redaction, and opt-in archive manifest."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Mapping

REVIEW_BUNDLE_MANIFEST_FILENAME = "review_bundle_manifest.json"
BUILD_REVIEW_ZIP_ENV = "APPS_RG_BUILD_REVIEW_ZIP"

_TEXT_DIAGNOSTICS = frozenset(
    {
        "compiled_prompt.txt",
        "command_output.txt",
        "raw_model_output.txt",
        "raw_model_output_original.txt",
    }
)
_JSON_DIAGNOSTIC_PREFIXES = ("provider_request", "provider_response")
_SENSITIVE_JSON_KEYS = frozenset(
    {
        "content",
        "messages",
        "prompt",
        "raw_model_output",
        "raw_response",
        "request_body",
        "response_body",
    }
)
_SECRET_TOKEN_RE = re.compile(
    r"(?:Bearer\s+[A-Za-z0-9._\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,})"
)


@dataclass(frozen=True, slots=True)
class CachedFileMeta:
    sha256: str
    byte_length: int
    schema_version: str


_CACHE_LOCK = threading.Lock()
_FILE_META_CACHE: dict[tuple[str, int, int], CachedFileMeta] = {}
_DIR_NAME_INDEX: dict[tuple[str, int], dict[str, tuple[str, ...]]] = {}


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _extract_schema_version_from_bytes(path: Path, raw: bytes) -> str:
    if path.suffix.lower() != ".json" or not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(parsed, Mapping):
        return ""
    nested = parsed.get("payload")
    target = nested if isinstance(nested, Mapping) else parsed
    return str(target.get("schema_version") or target.get("schema") or "").strip()


def cached_file_binding_meta(path: Path) -> CachedFileMeta:
    """Read a file at most once per (resolved_path, mtime_ns, size) across closeout."""
    resolved = path.resolve()
    st = resolved.stat()
    key = (str(resolved), int(st.st_mtime_ns), int(st.st_size))
    with _CACHE_LOCK:
        hit = _FILE_META_CACHE.get(key)
        if hit is not None:
            return hit
    raw = resolved.read_bytes()
    meta = CachedFileMeta(
        sha256=_sha256_bytes(raw),
        byte_length=len(raw),
        schema_version=_extract_schema_version_from_bytes(resolved, raw),
    )
    with _CACHE_LOCK:
        if len(_FILE_META_CACHE) > 4096:
            _FILE_META_CACHE.clear()
        _FILE_META_CACHE[key] = meta
    return meta


def cached_file_sha256(path: Path) -> str:
    return cached_file_binding_meta(path).sha256


def _redaction_marker(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        raw = value.encode("utf-8")
        shape = "text"
    else:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        shape = "structured"
    return {
        "redacted": True,
        "content_type": shape,
        "byte_length": len(raw),
        "sha256": _sha256_bytes(raw),
    }


def _redact_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _redaction_marker(item)
            if str(key).lower() in _SENSITIVE_JSON_KEYS
            else _redact_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, str) and _SECRET_TOKEN_RE.search(value):
        return _SECRET_TOKEN_RE.sub("[REDACTED_SECRET]", value)
    return value


def _is_json_diagnostic(name: str) -> bool:
    return name.lower().endswith(".json") and name.startswith(_JSON_DIAGNOSTIC_PREFIXES)


def _is_text_diagnostic(name: str) -> bool:
    return name in _TEXT_DIAGNOSTICS


def scan_and_redact_closeout_directory(
    artifact_dir: Path | str,
    *,
    redact_diagnostics: bool = True,
    hash_all_files: bool = True,
    error_cls: type[RuntimeError] = RuntimeError,
) -> dict[str, Any]:
    """Single walk over ``artifact_dir`` performing hashing, indexing, and redaction together."""
    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        raise error_cls(f"product artifact directory is absent: {root}")

    redactions: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []
    by_name: dict[str, list[str]] = {}

    all_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for fname in sorted(filenames):
            if fname == "review_bundle.zip":
                continue
            fpath = Path(dirpath) / fname
            if fpath.is_symlink() or not fpath.is_file():
                continue
            all_files.append(fpath)

    for path in all_files:
        rel_posix = path.relative_to(root).as_posix()
        fname = path.name
        by_name.setdefault(fname, []).append(rel_posix)
        is_txt_diag = _is_text_diagnostic(fname)
        is_json_diag = _is_json_diagnostic(fname)

        if not hash_all_files and not (redact_diagnostics and (is_txt_diag or is_json_diag)):
            continue

        if redact_diagnostics and (is_txt_diag or is_json_diag):
            before = path.read_bytes()
            final_bytes = before
            if is_txt_diag:
                replacement = (
                    "REDACTED_PRODUCT_DIAGNOSTIC\n"
                    f"sha256={_sha256_bytes(before)}\nbyte_length={len(before)}\n"
                ).encode("utf-8")
                kind = "raw_text_diagnostic"
            else:
                try:
                    parsed = json.loads(before)
                except json.JSONDecodeError as exc:
                    raise error_cls(
                        f"provider diagnostic is invalid JSON: {rel_posix}"
                    ) from exc
                replacement = (
                    json.dumps(_redact_json_value(parsed), indent=2, sort_keys=True) + "\n"
                ).encode("utf-8")
                kind = "provider_transport_diagnostic"
            if replacement != before:
                path.write_bytes(replacement)
                final_bytes = replacement
                redactions.append(
                    {
                        "artifact_ref": rel_posix,
                        "kind": kind,
                        "original_sha256": _sha256_bytes(before),
                        "redacted_sha256": _sha256_bytes(replacement),
                        "original_byte_length": len(before),
                    }
                )
            st = path.stat()
            meta = CachedFileMeta(
                sha256=_sha256_bytes(final_bytes),
                byte_length=len(final_bytes),
                schema_version=_extract_schema_version_from_bytes(path, final_bytes),
            )
            with _CACHE_LOCK:
                _FILE_META_CACHE[(str(path.resolve()), int(st.st_mtime_ns), int(st.st_size))] = meta
        else:
            meta = cached_file_binding_meta(path)

        manifest_entries.append(
            {
                "artifact_ref": rel_posix,
                "sha256": meta.sha256,
                "byte_length": meta.byte_length,
            }
        )

    root_stat = root.stat()
    with _CACHE_LOCK:
        _DIR_NAME_INDEX[(str(root), int(root_stat.st_mtime_ns))] = {
            k: tuple(v) for k, v in by_name.items()
        }

    return {
        "redactions": redactions,
        "manifest_entries": manifest_entries,
        "files_by_name": by_name,
    }


def find_closeout_files_by_name(artifact_dir: Path | str, filename: str) -> list[Path]:
    root = Path(artifact_dir).resolve()
    if not root.is_dir():
        return []
    root_stat = root.stat()
    with _CACHE_LOCK:
        idx = _DIR_NAME_INDEX.get((str(root), int(root_stat.st_mtime_ns)))
    if idx is not None:
        return [root / rel for rel in idx.get(filename, ()) if (root / rel).is_file()]
    scan = scan_and_redact_closeout_directory(root, redact_diagnostics=False, hash_all_files=False)
    return [root / rel for rel in scan["files_by_name"].get(filename, ()) if (root / rel).is_file()]


def should_build_review_zip(run_root: Path, *, explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    env_raw = os.environ.get(BUILD_REVIEW_ZIP_ENV, "").strip().lower()
    if env_raw in ("1", "true", "yes", "on"):
        return True
    if env_raw in ("0", "false", "no", "off"):
        return False
    root = Path(run_root).resolve()
    if (
        os.environ.get("APPS_RG_WHOLE_RUN_ENVELOPE", "").strip() == "1"
        or (root / "spine_run_manifest.json").is_file()
        or (root / "e2e_stage_ledger.json").is_file()
    ):
        return False
    return True


def write_lightweight_review_bundle_manifest(run_root: Path) -> Path:
    root = Path(run_root).resolve()
    scan = scan_and_redact_closeout_directory(root, redact_diagnostics=False, hash_all_files=True)
    out = root / REVIEW_BUNDLE_MANIFEST_FILENAME
    payload = {
        "schema_version": "apps_rg.review_bundle_manifest.v1",
        "zip_built": False,
        "opt_in_env": BUILD_REVIEW_ZIP_ENV,
        "file_count": len(scan["manifest_entries"]),
        "artifacts": scan["manifest_entries"],
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out
