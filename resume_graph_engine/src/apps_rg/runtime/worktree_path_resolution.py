"""Worktree-safe checkout path containment, unified section lane lookup, and baseline resolution."""
from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import resolve_repository_path

_WIN_DRIVE_RE = re.compile(r"^[a-zA-Z]:")


@functools.lru_cache(maxsize=16)
def _git_common_checkout_root_str(repo_resolved_str: str) -> str:
    repo = Path(repo_resolved_str)
    dot_git = repo / ".git"
    if dot_git.is_file():
        try:
            first = dot_git.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, IndexError, UnicodeDecodeError):
            first = ""
        if first.startswith("gitdir:"):
            gitdir_raw = first.split(":", 1)[1].strip()
            gitdir = Path(gitdir_raw)
            if not gitdir.is_absolute():
                gitdir = (repo / gitdir).resolve()
            else:
                gitdir = gitdir.resolve()
            commondir_file = gitdir / "commondir"
            if commondir_file.is_file():
                try:
                    rel_common = commondir_file.read_text(encoding="utf-8").strip()
                    common_git = (gitdir / rel_common).resolve()
                    if common_git.name == ".git":
                        return str(common_git.parent.resolve())
                except (OSError, UnicodeDecodeError):
                    pass
    try:
        completed = subprocess.run(
            ["git", "-C", repo_resolved_str, "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    raw = completed.stdout.strip()
    if not raw:
        return ""
    common_git = Path(raw)
    if not common_git.is_absolute():
        common_git = (repo / common_git).resolve()
    else:
        common_git = common_git.resolve()
    if common_git.name == ".git":
        return str(common_git.parent.resolve())
    return ""


def trusted_checkout_roots(repo: Path) -> tuple[Path, ...]:
    """Return ordered trusted checkout roots covering isolated worktrees and standalone sub-packages."""
    primary = Path(repo).resolve()
    roots: list[Path] = [primary]

    def _add(p: Path) -> None:
        rp = p.resolve()
        if rp not in roots:
            roots.append(rp)

    if primary.name == "resume_graph_engine" and (primary.parent / ".git").exists():
        _add(primary.parent)
    if (primary / "resume_graph_engine").is_dir():
        _add(primary / "resume_graph_engine")

    search_base = primary.parent if primary.name == "resume_graph_engine" else primary
    common_str = _git_common_checkout_root_str(str(search_base))
    if common_str:
        common = Path(common_str)
        _add(common)
        if (common / "resume_graph_engine").is_dir():
            _add(common / "resume_graph_engine")
    return tuple(roots)


def assert_no_symlink_escape(candidate: Path, allowed_root: Path) -> None:
    cursor = candidate
    while cursor != allowed_root and cursor.parent != cursor:
        if cursor.exists() and cursor.is_symlink():
            raise ValueError(f"artifact path may not traverse symlink: {cursor}")
        cursor = cursor.parent


def is_within_trusted_checkout(
    candidate: Path,
    repo: Path,
    *,
    subpath: str = "",
    reject_symlinks: bool = False,
) -> tuple[bool, Path | None]:
    """Check whether ``candidate`` resolves inside ``repo`` or its shared git checkout."""
    cand_resolved = Path(candidate).resolve()
    for root in trusted_checkout_roots(repo):
        base = (root / subpath).resolve() if subpath else root
        try:
            cand_resolved.relative_to(base)
        except ValueError:
            continue
        if reject_symlinks:
            assert_no_symlink_escape(Path(candidate).expanduser(), base)
            assert_no_symlink_escape(cand_resolved, base)
        return True, base
    return False, None


def trusted_rel_posix(path: Path, repo: Path) -> str:
    """Return safe POSIX path relative to ``repo`` or a shared checkout root."""
    pr = Path(path).resolve()
    for root in trusted_checkout_roots(repo):
        try:
            rel = pr.relative_to(root).as_posix()
        except ValueError:
            continue
        if not rel or rel.startswith(("/", "\\")) or _WIN_DRIVE_RE.match(rel):
            continue
        if any(part == ".." for part in rel.split("/")):
            continue
        return rel
    raise ValueError(f"path {pr} is not under repo_root {Path(repo).resolve()}")


def resolve_existing_trusted_rel_path(rel: str | Path, repo: Path) -> Path:
    """Resolve a repo-relative path across ``repo`` and shared checkout roots."""
    p = Path(rel)
    if p.is_absolute():
        return p.resolve()
    for root in trusted_checkout_roots(repo):
        cand = (root / p).resolve()
        if cand.exists():
            return cand
    return (Path(repo).resolve() / p).resolve()


def _lane_dir_has_materialized_evidence(path: Path, section_id: str) -> bool:
    if not path.is_dir():
        return False
    markers = (
        path / "l2_output.json",
        path / "resume_display_text.txt",
        path / f"{section_id}_output.txt",
        path / "command_output.txt",
        path / "x2_gate_outputs.json",
        path / "final_resume.json",
    )
    return any(m.is_file() for m in markers) or any(path.glob("*_output.txt"))


def resolve_unified_section_lane_dir(
    section: dict[str, Any],
    repo_root: Path,
    run_root: Path | None = None,
) -> Path | None:
    """Resolve section lane directory uniformly across ``lanes/`` and ``modular_r4/sections/``."""
    section_id = str(section.get("section") or "").strip()
    raw = str(section.get("lane_dir") or "").strip()
    candidates: list[Path] = []
    if raw:
        raw_path = Path(raw)
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            if run_root is not None:
                candidates.append(Path(run_root) / raw_path)
            candidates.append(resolve_existing_trusted_rel_path(raw_path, repo_root))
    if run_root is not None and section_id:
        rr = Path(run_root)
        candidates.extend([rr / "lanes" / section_id, rr / "modular_r4" / "sections" / section_id])
        if section_id == "final_resume_aggregation":
            candidates.append(rr / "modular_r4" / "final_resume_assembly")

    existing_dirs: list[Path] = []
    for cand in candidates:
        if cand.is_dir():
            if _lane_dir_has_materialized_evidence(cand, section_id):
                return cand
            nested = sorted(cand.rglob("resume_display_text.txt"))
            if nested:
                return nested[-1].parent
            existing_dirs.append(cand)
    if existing_dirs:
        return existing_dirs[0]
    return candidates[0] if candidates else None


def resolve_e2e_baseline_paths(
    configured_ref: str,
    default_ref: Path,
    repo_root: Path,
) -> tuple[Path, list[Path]]:
    """Resolve pinned E2E baseline contract file and ordered search roots for ``baseline_run_dir``."""
    roots = list(trusted_checkout_roots(repo_root))
    ref_input = Path(configured_ref) if configured_ref else default_ref
    if ref_input.is_absolute():
        return ref_input, roots
    for root in roots:
        resolved = resolve_repository_path(root, ref_input)
        if resolved.is_file():
            return resolved, roots
        direct = (root / ref_input).resolve()
        if direct.is_file():
            return direct, roots
    pkg_cfg = Path(__file__).resolve().parents[1] / "config" / "e2e_baselines" / default_ref.name
    if not configured_ref and pkg_cfg.is_file():
        return pkg_cfg, roots
    return (Path(repo_root).resolve() / ref_input), roots
