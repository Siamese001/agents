"""Unified live execution policy and credential enforcement engine.

Central authority for ensuring real API credentials (from env_agents / .env)
are loaded and enforced for live execution, strictly rejecting placeholders,
mock modes, and local dummy endpoints.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class LiveExecutionError(RuntimeError):
    """Raised when production execution violates live execution requirements."""


PLACEHOLDER_VALUES = frozenset({
    "",
    "dummy",
    "fake",
    "test",
    "test-key",
    "test_key",
    "local",
    "sk-local-dev-key",
    "changeme",
    "replace_me",
    "placeholder",
    "none",
    "null",
    "your-api-key",
    "<your_api_key>",
})


def _manual_parse_env_file(path: Path, override: bool = False) -> bool:
    """Fallback parser for .env / env_agents files when python-dotenv is absent."""
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
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


CENTRAL_SSOT_FILE = Path.home() / ".config" / "ai_env" / "common.env"
FALLBACK_SSOT_FILE = Path.home() / "env" / "common.env"


def load_agent_environment(repo_root: Path | None = None, override: bool = False) -> None:
    """Load central workstation SSOT and repo-specific env_agents into os.environ."""
    # 1. Load central workstation SSOT first (shared baseline)
    central_path = CENTRAL_SSOT_FILE if CENTRAL_SSOT_FILE.is_file() else (FALLBACK_SSOT_FILE if FALLBACK_SSOT_FILE.is_file() else None)
    if central_path:
        if load_dotenv is not None:
            try:
                load_dotenv(central_path, override=False)
            except Exception:
                _manual_parse_env_file(central_path, override=False)
        else:
            _manual_parse_env_file(central_path, override=False)

    # 2. Load repo-specific env_agents
    root = repo_root or Path.cwd()
    candidate_files = [
        root / "env_agents",
        root / ".env",
    ]

    for candidate in candidate_files:
        if candidate.is_file():
            if load_dotenv is not None:
                try:
                    load_dotenv(candidate, override=override)
                except Exception:
                    _manual_parse_env_file(candidate, override=override)
            else:
                _manual_parse_env_file(candidate, override=override)


def _clean_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.lower() in PLACEHOLDER_VALUES or any(p in cleaned.lower() for p in ("placeholder", "sk-local-dev-key")):
        return None
    return cleaned


def api_key(provider: str, environ: Mapping[str, str] | None = None) -> str:
    """Retrieve an authenticated, live API key for a specified provider.

    Raises LiveExecutionError if missing or equal to a placeholder.
    """
    env = os.environ if environ is None else environ
    if env is os.environ and not env.get("OPENAI_API_KEY") and not env.get("ANTHROPIC_API_KEY"):
        load_agent_environment()

    aliases = {
        "openai": ("OPENAI_API_KEY",),
        "anthropic": ("ANTHROPIC_API_KEY",),
        "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    }

    p_norm = provider.lower().strip()
    try:
        names = aliases[p_norm]
    except KeyError:
        names = (f"{p_norm.upper()}_API_KEY",)

    for name in names:
        val = _clean_key(env.get(name))
        if val:
            return val

    raise LiveExecutionError(
        f"LIVE_CREDENTIAL_ERROR: Missing live API key for provider '{provider}'. Expected non-placeholder value in {names}."
    )


def key_fingerprint(key: str) -> str:
    """Compute a safe audit digest for receipts and telemetry without leaking the key."""
    if not key:
        return "none"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def reject_mock_environment(environ: Mapping[str, str] | None = None) -> None:
    """Verify that environment does not carry flags that force mock or stub behavior."""
    env = os.environ if environ is None else environ

    prohibited = {
        "APPS_RG_L2_FORCE_STUB": {"1", "true", "yes", "on"},
        "APPS_RG_ALLOW_SINGLE_PATH_SELECTOR_BYPASS": {"1", "true", "yes", "on"},
        "APPS_RG_MOCK_JUDGES": {"1", "true", "yes", "on"},
    }

    for var_name, forbidden_values in prohibited.items():
        val = (env.get(var_name) or "").strip().lower()
        if val in forbidden_values:
            raise LiveExecutionError(
                f"PROHIBITED_MOCK_ENV: {var_name}={val!r} is forbidden during live production execution."
            )

    provider_mode = (env.get("APPS_RG_L2_PROVIDER_MODE") or "").strip().lower()
    if provider_mode in {"stub_only", "stub", "off", "0", "false", "no"}:
        raise LiveExecutionError(
            f"PROHIBITED_MOCK_ENV: APPS_RG_L2_PROVIDER_MODE={provider_mode!r} requests non-live execution."
        )


def require_live_pipeline(providers: Iterable[str], environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Ensure mock environment is clean and all requested providers have live API keys.

    Returns:
        Mapping of provider_name -> key_fingerprint
    """
    reject_mock_environment(environ=environ)
    fingerprints: dict[str, str] = {}
    for p in sorted(set(providers)):
        k = api_key(p, environ=environ)
        fingerprints[p] = key_fingerprint(k)
    return fingerprints
