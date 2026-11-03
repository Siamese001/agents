"""Fail-closed ownership of Apps RG runtime paths.

The application must never inherit another checkout's cache, model directory,
or runtime root.  This module is intentionally independent of Codex Defender:
the Defender constructs a clean process, while this guard protects direct CLI,
CI, and library-entry execution as well.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

from apps_rg.runtime.runtime_proof_layout import find_repo_root

RUNTIME_BOUNDARY_POLICY_RELATIVE = Path(".antigravity") / "runtime-boundary.json"
RUNTIME_BOUNDARY_RECEIPT_NAME = "apps_rg_runtime_boundary_receipt.json"
RUNTIME_BOUNDARY_MARKER = "APPS_RG_RUNTIME_BOUNDARY_ENFORCED"


class RuntimeBoundaryViolation(ValueError):
    """An inherited process path was not owned by the current Apps RG worktree."""


@dataclass(frozen=True)
class AppsRgRuntimeBoundary:
    repo_root: Path
    policy_path: Path
    effective_paths: dict[str, Path]
    policy_sha256: str

    def receipt_dict(self) -> dict[str, object]:
        return {
            "schema_version": "apps_rg_runtime_boundary_v1",
            "status": "PASS",
            "repo_root": str(self.repo_root),
            "policy_path": str(self.policy_path),
            "policy_sha256": self.policy_sha256,
            "effective_paths": {name: str(path) for name, path in sorted(self.effective_paths.items())},
        }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _canonical(path_text: str) -> Path:
    return Path(path_text).expanduser().resolve()


_SHARED_DATA_ENV_KEYS = frozenset({"CHROMA_PERSIST_DIR", "APPS_RG_EMBEDDING_MODEL_PATH"})


def _resolve_expected_boundary_path(name: str, relative: str, root: Path) -> Path:
    resolved = (root / relative).resolve()
    if not _is_within(resolved, root):
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_ESCAPE:{name}={relative}")
    if name in _SHARED_DATA_ENV_KEYS and not resolved.exists():
        from apps_rg.runtime.worktree_path_resolution import resolve_existing_trusted_rel_path

        resolved = resolve_existing_trusted_rel_path(relative, root)
    return resolved


def _normalize_trusted_pythonpath(raw_value: str, expected: Path, root: Path) -> str | None:
    from apps_rg.runtime.worktree_path_resolution import is_within_trusted_checkout

    parts = [p.strip() for p in raw_value.split(os.pathsep) if p.strip()]
    if not parts:
        return str(expected)
    canon_parts: list[Path] = []
    for part in parts:
        cp = _canonical(part)
        ok, _ = is_within_trusted_checkout(cp, root)
        if not ok:
            return None
        if cp not in canon_parts:
            canon_parts.append(cp)
    if expected not in canon_parts:
        canon_parts.insert(0, expected)
    return os.pathsep.join(str(p) for p in canon_parts)


def _load_policy(*, repo_root: Path, policy_path: Path | None = None) -> tuple[Path, dict[str, object], str]:
    path = (policy_path or repo_root / RUNTIME_BOUNDARY_POLICY_RELATIVE).resolve()
    if not path.is_file():
        alt = (
            repo_root / (".antigravity" if ".codex" in str(path) else ".codex") / "runtime-boundary.json"
        ).resolve()
        if alt.is_file():
            path = alt
        else:
            raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_MISSING:{path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_INVALID:{path}") from exc
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_INVALID:{path}")
    worktree_relative = str(raw.get("worktreeRoot") or "").strip()
    declared_root = (path.parent / worktree_relative).resolve()
    if declared_root != repo_root.resolve():
        raise RuntimeBoundaryViolation(
            f"PATH_AUTHORITY_POLICY_ROOT_MISMATCH:declared={declared_root};actual={repo_root.resolve()}"
        )
    return path, raw, hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def configure_apps_rg_runtime_boundary(
    *,
    repo_root: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
    policy_path: Path | None = None,
) -> AppsRgRuntimeBoundary:
    """Reject foreign path inheritance and materialize the checked-in local paths.

    No directory is created here.  It is a path-authority assertion, not a
    bootstrap action; a missing local model/cache remains a downstream
    fail-closed readiness result instead of falling back to a user cache.
    """

    root = (repo_root or find_repo_root()).resolve()
    env = os.environ if environ is None else environ
    path, raw, policy_sha = _load_policy(repo_root=root, policy_path=policy_path)
    paths = raw.get("environmentPaths")
    if not isinstance(paths, dict) or not paths:
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_INVALID:environmentPaths:{path}")

    effective: dict[str, Path] = {}
    for name, relative in paths.items():
        if not isinstance(name, str) or not isinstance(relative, str) or not name or not relative:
            raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_INVALID:path:{path}")
        effective[name] = _resolve_expected_boundary_path(name, relative, root)

    # Validate all inherited values first.  This gives a direct, deterministic
    # error rather than silently using a stale process variable from a prior
    # checkout.
    normalized_pythonpath: str | None = None
    for name, expected in effective.items():
        inherited = str(env.get(name) or "").strip()
        if name == "PYTHONPATH" and inherited:
            normalized_pythonpath = _normalize_trusted_pythonpath(inherited, expected, root)
            if normalized_pythonpath is None:
                raise RuntimeBoundaryViolation(
                    f"PATH_AUTHORITY_VIOLATION:{name}:inherited={inherited};expected={expected}"
                )
        elif inherited and _canonical(inherited) != expected:
            raise RuntimeBoundaryViolation(
                f"PATH_AUTHORITY_VIOLATION:{name}:inherited={_canonical(inherited)};expected={expected}"
            )

    for name, expected in effective.items():
        if name == "PYTHONPATH" and normalized_pythonpath is not None:
            env[name] = normalized_pythonpath
        else:
            env[name] = str(expected)
    env[RUNTIME_BOUNDARY_MARKER] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env.setdefault("APPS_RG_ANTHROPIC_PROMPT_CACHE", "1")
    env.setdefault("APPS_RG_ANTHROPIC_PROMPT_CACHE_TELEMETRY", "1")
    env.setdefault("APPS_RG_PARALLEL_PHASE1_LANES", "1")
    env.setdefault("APPS_RG_PHASE1_MAX_PARALLEL", "6")
    return AppsRgRuntimeBoundary(
        repo_root=root,
        policy_path=path,
        effective_paths=effective,
        policy_sha256=policy_sha,
    )


def assert_apps_rg_runtime_boundary(
    *,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    policy_path: Path | None = None,
) -> AppsRgRuntimeBoundary:
    """Verify that later bootstrap code did not alter the resolved boundary."""

    root = (repo_root or find_repo_root()).resolve()
    env = os.environ if environ is None else environ
    path, raw, policy_sha = _load_policy(repo_root=root, policy_path=policy_path)
    paths = raw.get("environmentPaths")
    if not isinstance(paths, dict):
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_POLICY_INVALID:environmentPaths:{path}")
    effective: dict[str, Path] = {}
    for name, relative in paths.items():
        expected = _resolve_expected_boundary_path(str(name), str(relative), root)
        observed = str(env.get(str(name)) or "").strip()
        if str(name) == "PYTHONPATH":
            norm_pp = _normalize_trusted_pythonpath(observed, expected, root) if observed else None
            obs_parts = {_canonical(p) for p in observed.split(os.pathsep) if p.strip()}
            if not observed or norm_pp is None or expected not in obs_parts:
                raise RuntimeBoundaryViolation(
                    f"PATH_AUTHORITY_VIOLATION:{name}:observed={observed or '<unset>'};expected={expected}"
                )
        elif not observed or _canonical(observed) != expected:
            raise RuntimeBoundaryViolation(
                f"PATH_AUTHORITY_VIOLATION:{name}:observed={observed or '<unset>'};expected={expected}"
            )
        effective[str(name)] = expected
    if str(env.get(RUNTIME_BOUNDARY_MARKER) or "") != "1":
        raise RuntimeBoundaryViolation("PATH_AUTHORITY_MARKER_MISSING")
    return AppsRgRuntimeBoundary(
        repo_root=root,
        policy_path=path,
        effective_paths=effective,
        policy_sha256=policy_sha,
    )


def write_apps_rg_runtime_boundary_receipt(
    artifact_dir: Path | str,
    boundary: AppsRgRuntimeBoundary,
) -> Path:
    root = Path(artifact_dir).resolve()
    if not _is_within(root, boundary.repo_root):
        raise RuntimeBoundaryViolation(f"PATH_AUTHORITY_ARTIFACT_ESCAPE:{root}")
    root.mkdir(parents=True, exist_ok=True)
    out = root / RUNTIME_BOUNDARY_RECEIPT_NAME
    out.write_text(json.dumps(boundary.receipt_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


__all__ = [
    "AppsRgRuntimeBoundary",
    "RUNTIME_BOUNDARY_MARKER",
    "RUNTIME_BOUNDARY_POLICY_RELATIVE",
    "RUNTIME_BOUNDARY_RECEIPT_NAME",
    "RuntimeBoundaryViolation",
    "assert_apps_rg_runtime_boundary",
    "configure_apps_rg_runtime_boundary",
    "write_apps_rg_runtime_boundary_receipt",
]
