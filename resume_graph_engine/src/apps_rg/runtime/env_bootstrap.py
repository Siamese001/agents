"""Canonical apps_rg environment bootstrap.

Loads the ``.env`` SSOT into the current Python process before any provider
readiness or credential preflight reads ``os.environ``.

Worktree resilience (multi-worktree SSOT)
-----------------------------------------
``git worktree add`` only materializes *tracked* files, and ``.env`` is
gitignored — so a fresh worktree has no repo-root ``.env`` and every provider
call fails closed on missing credentials. To make one SSOT serve every
worktree, ``.env`` is resolved in this order (first existing file wins):

1. ``$APPS_RG_DOTENV`` — explicit operator override (a single absolute path).
2. ``<repo_root>/.env`` — back-compat / intentional per-worktree override.
3. ``~/env/.env`` — canonical relocated SSOT outside any repo (survives
   worktree reaps, re-clones, and the primary checkout moving). Deliberately
   app-neutral: one credentials file serves every worktree and branch.

``override=False`` preserves already-exported shell credentials in all cases.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

from apps_rg.runtime.runtime_proof_layout import find_repo_root

#: Env var naming an explicit ``.env`` SSOT path (highest precedence).
APPS_RG_DOTENV_ENV_VAR = "APPS_RG_DOTENV"


def canonical_home_dotenv() -> Path:
    """Repo-independent SSOT default: ``~/env/.env`` (final fallback)."""
    return Path.home() / "env" / ".env"


@dataclass(frozen=True)
class AppsRgEnvBootstrapResult:
    repo_root: str
    dotenv_path: str
    dotenv_path_existed: bool
    dotenv_loaded: bool
    #: Which candidate supplied the file: ``env_override`` | ``repo_root`` | ``home_ssot`` | ``none``.
    dotenv_source: str = "none"


def _candidate_dotenv_paths(root: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    override = os.environ.get(APPS_RG_DOTENV_ENV_VAR, "").strip()
    if override:
        candidates.append(("env_override", Path(override).expanduser()))
    candidates.append(("repo_root", root / ".env"))
    candidates.append(("repo_root_agents", root / "env_agents"))
    # Also check parent directory if in a worktree or subpackage
    candidates.append(("parent_agents", root.parent / "env_agents"))
    candidates.append(("home_ssot", canonical_home_dotenv()))
    return candidates


def _manual_load_env(path: Path, override: bool = False) -> bool:
    """Fallback parser for .env / env_agents files when python-dotenv is not present."""
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        loaded_any = False
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k and (override or k not in os.environ):
                os.environ[k] = v
                loaded_any = True
        return loaded_any
    except Exception:
        return False


def bootstrap_apps_rg_env(
    *,
    repo_root: Path | None = None,
    override: bool = False,
) -> AppsRgEnvBootstrapResult:
    """Load the ``.env`` / ``env_agents`` SSOT for process-env provider checks.

    Resolution order: ``$APPS_RG_DOTENV`` → ``<repo_root>/.env`` → ``<repo_root>/env_agents`` → ``~/env/.env``.
    ``override=False`` preserves already-exported shell credentials, matching the
    historical CLI behavior while making that behavior available outside
    ``python -m apps_rg``.
    """
    root = (repo_root or find_repo_root()).resolve()
    chosen_path = root / ".env"
    source = "none"
    loaded = False
    existed = False
    for src, candidate in _candidate_dotenv_paths(root):
        if candidate.is_file():
            chosen_path = candidate
            source = src
            existed = True
            try:
                from dotenv import load_dotenv
            except ImportError:
                loaded = _manual_load_env(candidate, override=override)
                source = f"{src}:manual_fallback" if loaded else f"{src}:dotenv_import_unavailable"
            else:
                loaded = bool(load_dotenv(dotenv_path=candidate, override=override))
                if not loaded:
                    # Fall back to manual parsing if python-dotenv failed on specific formatting
                    loaded = _manual_load_env(candidate, override=override)
            break
    return AppsRgEnvBootstrapResult(
        repo_root=str(root),
        dotenv_path=str(chosen_path),
        dotenv_path_existed=existed,
        dotenv_loaded=loaded,
        dotenv_source=source,
    )


_PLACEHOLDER_SUBSTRINGS = frozenset(
    {"placeholder", "dummy", "replace_me", "sk-local-dev-key", "none", "null", "test_key"}
)


def assert_live_credentials_present(
    providers: Sequence[str] = ("openai",),
    environ: Mapping[str, str] | None = None,
) -> None:
    """Validate that real API credentials exist for specified providers without placeholders."""
    env = os.environ if environ is None else environ
    # Ensure bootstrap is executed first
    if env is os.environ:
        bootstrap_apps_rg_env()

    provider_keys = {
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    }

    missing_or_invalid: list[str] = []
    for p in providers:
        p_norm = p.lower().strip()
        candidate_keys = provider_keys.get(p_norm, (f"{p_norm.upper()}_API_KEY",))
        val = None
        used_key = ""
        for ck in candidate_keys:
            candidate_val = env.get(ck, "").strip()
            if candidate_val:
                val = candidate_val
                used_key = ck
                break
        if not val:
            missing_or_invalid.append(f"{p_norm} (checked {', '.join(candidate_keys)}: missing or empty)")
            continue
        val_lower = val.lower()
        if any(sub in val_lower for sub in _PLACEHOLDER_SUBSTRINGS):
            missing_or_invalid.append(f"{p_norm} ({used_key} contains invalid placeholder: {val[:8]}...)")

    if missing_or_invalid:
        raise ValueError(
            "LIVE_EXECUTION_CREDENTIAL_ERROR: Real API credentials required for live execution; "
            + "; ".join(missing_or_invalid)
            + ". Ensure env_agents or .env is populated with authorized keys."
        )


def bootstrap_process_env_if_needed(environ: object) -> AppsRgEnvBootstrapResult | None:
    """Bootstrap only for the real process env, not injected test mappings."""
    if environ is os.environ:
        return bootstrap_apps_rg_env()
    return None


@contextmanager
def temporary_env_override(updates: Mapping[str, str | None]) -> Iterator[None]:
    """Context manager to temporarily override environment variables and cleanly restore original state."""
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in updates}
    try:
        for k, v in updates.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


__all__ = [
    "APPS_RG_DOTENV_ENV_VAR",
    "AppsRgEnvBootstrapResult",
    "assert_live_credentials_present",
    "bootstrap_apps_rg_env",
    "bootstrap_process_env_if_needed",
    "canonical_home_dotenv",
    "temporary_env_override",
]
