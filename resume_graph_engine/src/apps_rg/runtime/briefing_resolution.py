"""Resolve apps_rg lane briefing text from filesystem path, https URI, or DEFAULT_SSOT.

U0 passes through ``briefing_artifact_ref`` only; this module is downstream (lanes / modular adapter).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from apps_rg.runtime.briefing_ssot import DEFAULT_TARGETING_BRIEFING_PATH, default_targeting_briefing_text

# Extensions allowed for local briefing artifacts (lowercased suffixes).
ALLOWED_BRIEFING_SUFFIXES: frozenset[str] = frozenset({".txt", ".md", ".json", ".yaml", ".yml", ".markdown"})

class BriefingSource(StrEnum):
    RUN_SPECIFIC = "RUN_SPECIFIC"
    DEFAULT_SSOT = "DEFAULT_SSOT"


class BriefingResolutionError(RuntimeError):
    """Fail-closed briefing load (missing file, disallowed type, empty required ref, etc.)."""


@dataclass(frozen=True, slots=True)
class ResolvedBriefing:
    text: str
    briefing_source: BriefingSource
    briefing_digest: str
    ref_used: str


def _sha256_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _allowed_local_suffix(path: Path) -> None:
    suf = path.suffix.lower()
    if suf not in ALLOWED_BRIEFING_SUFFIXES:
        raise BriefingResolutionError(
            f"briefing artifact extension {suf!r} not in allowed set {sorted(ALLOWED_BRIEFING_SUFFIXES)}"
        )


def _looks_like_filesystem_ref(ref: str) -> bool:
    r = ref.strip()
    if r.startswith(("http://", "https://")):
        return False
    if "/" in r or "\\" in r:
        return True
    low = r.lower()
    return any(low.endswith(s) for s in ALLOWED_BRIEFING_SUFFIXES)


def _fetch_uri(ref: str) -> tuple[str, str | None]:
    raise BriefingResolutionError(
        "remote briefing references are not supported; submit captured text "
        "through the governed input bundle"
    )


import threading

_BRIEFING_CACHE_LOCK = threading.Lock()
_RESOLVED_BRIEFING_CACHE: dict[tuple[str, int], ResolvedBriefing] = {}
_DEFAULT_SSOT_BRIEFING_CACHE: tuple[int, ResolvedBriefing] | None = None


def clear_briefing_cache() -> None:
    """Clear in-memory briefing caches (for testing, hot reload, or cache busting)."""
    global _DEFAULT_SSOT_BRIEFING_CACHE
    with _BRIEFING_CACHE_LOCK:
        _RESOLVED_BRIEFING_CACHE.clear()
        _DEFAULT_SSOT_BRIEFING_CACHE = None


def resolve_briefing_for_lanes(
    *,
    briefing_artifact_ref: str | None,
    require_run_specific: bool = False,
) -> ResolvedBriefing:
    """Load briefing text for modular lanes / dispatch defaults.

    Parameters
    ----------
    briefing_artifact_ref:
        Optional filesystem path, ``https`` ``http`` URI, or inline text (only when not path-like).
    require_run_specific:
        When True, empty ref fails closed (no DEFAULT_SSOT fallback).
    """
    ref = str(briefing_artifact_ref or "").strip()
    if not ref:
        if require_run_specific:
            raise BriefingResolutionError("required briefing_artifact_ref is empty")
        global _DEFAULT_SSOT_BRIEFING_CACHE
        default_p = DEFAULT_TARGETING_BRIEFING_PATH
        mtime = default_p.stat().st_mtime_ns if default_p.is_file() else 0
        with _BRIEFING_CACHE_LOCK:
            if _DEFAULT_SSOT_BRIEFING_CACHE is not None and _DEFAULT_SSOT_BRIEFING_CACHE[0] == mtime:
                return _DEFAULT_SSOT_BRIEFING_CACHE[1]
        text = default_targeting_briefing_text()
        digest = _sha256_utf8(text)
        resolved = ResolvedBriefing(
            text=text,
            briefing_source=BriefingSource.DEFAULT_SSOT,
            briefing_digest=digest,
            ref_used=f"DEFAULT_SSOT:{DEFAULT_TARGETING_BRIEFING_PATH.as_posix()}",
        )
        with _BRIEFING_CACHE_LOCK:
            _DEFAULT_SSOT_BRIEFING_CACHE = (mtime, resolved)
        return resolved

    if ref.startswith(("http://", "https://")):
        body, _ctype = _fetch_uri(ref)
        body = body.strip()
        if not body:
            raise BriefingResolutionError(f"briefing URI returned empty body: {ref!r}")
        return ResolvedBriefing(
            text=body,
            briefing_source=BriefingSource.RUN_SPECIFIC,
            briefing_digest=_sha256_utf8(body),
            ref_used=ref,
        )

    p = Path(ref)
    if p.is_file():
        _allowed_local_suffix(p)
        resolved_str = str(p.resolve())
        mtime = p.stat().st_mtime_ns
        cache_key = (resolved_str, mtime)
        with _BRIEFING_CACHE_LOCK:
            cached = _RESOLVED_BRIEFING_CACHE.get(cache_key)
            if cached is not None:
                return cached
        try:
            text = p.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise BriefingResolutionError(f"cannot read briefing file {p}: {exc}") from exc
        if not text:
            raise BriefingResolutionError(f"briefing file is empty: {p}")
        digest = _sha256_utf8(text)
        resolved = ResolvedBriefing(
            text=text,
            briefing_source=BriefingSource.RUN_SPECIFIC,
            briefing_digest=digest,
            ref_used=resolved_str,
        )
        with _BRIEFING_CACHE_LOCK:
            _RESOLVED_BRIEFING_CACHE[cache_key] = resolved
        return resolved

    if _looks_like_filesystem_ref(ref):
        raise BriefingResolutionError(f"briefing artifact path does not exist or is not a file: {ref!r}")

    return ResolvedBriefing(
        text=ref,
        briefing_source=BriefingSource.RUN_SPECIFIC,
        briefing_digest=_sha256_utf8(ref),
        ref_used="inline:text",
    )


__all__ = [
    "ALLOWED_BRIEFING_SUFFIXES",
    "BriefingResolutionError",
    "BriefingSource",
    "ResolvedBriefing",
    "clear_briefing_cache",
    "resolve_briefing_for_lanes",
]
