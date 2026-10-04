"""Canonical artifact root paths and src/ write containment guards for apps_rg."""

from __future__ import annotations

import os
from pathlib import Path


def engine_root() -> Path:
    """Return the resume_graph_engine root directory (parent of src/, config/, artifacts/)."""
    return Path(__file__).resolve().parents[3]


def repo_root() -> Path:
    """Return the repository workspace root."""
    eng = engine_root()
    # Check if eng is itself at repo root or one level down
    if (eng / ".git").exists() or (eng.parent / ".git").exists():
        return eng.parent if (eng.parent / ".git").exists() else eng
    return eng.parent


def artifacts_root() -> Path:
    """Return the canonical artifacts directory under resume_graph_engine/artifacts/."""
    return engine_root() / "artifacts"


def run_root(run_id: str, *, category: str = "apps_rg") -> Path:
    """Return the canonical root directory for a specific run under artifacts/."""
    clean_id = str(run_id or "").strip()
    if not clean_id:
        raise ValueError("run_id cannot be empty")
    return artifacts_root() / category / clean_id


def assert_no_write_in_src(target_path: Path | str) -> Path:
    """Fail-closed guard ensuring no artifact writes land inside any src/ tree."""
    resolved = Path(target_path).resolve()
    src_dir = (engine_root() / "src").resolve()

    if resolved == src_dir or src_dir in resolved.parents:
        raise ValueError(
            f"Containment violation: artifact path {resolved} is inside the source tree ({src_dir}). "
            f"Artifacts must be written under {artifacts_root()}."
        )

    # General check: any path element named 'src' before 'artifacts'
    parts = [p.lower() for p in resolved.parts]
    if "src" in parts and "artifacts" in parts:
        src_idx = parts.index("src")
        art_idx = parts.index("artifacts")
        if src_idx < art_idx:
            raise ValueError(
                f"Containment violation: artifact path {resolved} contains 'src' before 'artifacts'."
            )

    return resolved


def guard_artifact_path(path: Path | str) -> Path:
    """Validate containment and return resolved Path."""
    return assert_no_write_in_src(path)
