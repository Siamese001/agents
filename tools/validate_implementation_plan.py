#!/usr/bin/env python3
"""Wave-based implementation plan validator delegating to core-governance with standalone CI fallback."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.hitl_governance import validate_model_token_registry
from tools.implementation_plan_core.evidence_requirements import (
    MAX_PLAN_WORDS,
    validate_holistic_pipeline_alignment,
)
from tools.implementation_plan_core.wave_dag import (
    strip_and_validate_shard_manifests,
    validate_wave_dag_sequence,
)

_PLUGIN_FILE = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp" / "wave_plan_validator.py"
_CACHED_PLUGIN_MOD: ModuleType | None = None


def _load_backend() -> ModuleType:
    """Resolve core-governance wave_plan_validator unless standalone mode is forced or plugin is absent."""
    global _CACHED_PLUGIN_MOD
    if os.environ.get("CORE_GOVERNANCE_FORCE_STANDALONE") != "1" and _PLUGIN_FILE.is_file():
        if _CACHED_PLUGIN_MOD is None:
            mod_name = "_core_governance_wave_plan_validator"
            spec = importlib.util.spec_from_file_location(mod_name, _PLUGIN_FILE)
            if spec is not None and spec.loader is not None:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
                _CACHED_PLUGIN_MOD = mod
        if _CACHED_PLUGIN_MOD is not None:
            return _CACHED_PLUGIN_MOD
    from tools import _standalone_plan_validator

    return _standalone_plan_validator


_BACKEND = _load_backend()

DEFAULT_LEGACY_EXEMPTIONS = {
    "core-judge-panel-harness-f3c8d1.md",
    "live-llm-enforcement-wave1-b7d14e.md",
    "governance-dedup-closeout-e8a4c2.md",
    "runtime-seam-unification-5e8a1b.md",
    "token-optimization-waves-c8d1e4.md",
}

RE_TITLE = _BACKEND.RE_TITLE
RE_WAVE_HEADER = _BACKEND.RE_WAVE_HEADER
RE_OBJECTIVE = _BACKEND.RE_OBJECTIVE
RE_MILESTONES = _BACKEND.RE_MILESTONES
RE_CRITERIA = _BACKEND.RE_CRITERIA
RE_RECEIPT_GATE = _BACKEND.RE_RECEIPT_GATE
RE_ITEM = _BACKEND.RE_ITEM
WaveSection = _BACKEND.WaveSection

VALID_STATUS_TOKENS = (
    "COMPLETED", "COMPLETE", "DONE", "IN_PROGRESS", "IN PROGRESS",
    "PENDING_APPROVAL", "PENDING APPROVAL", "PENDING", "OPEN",
    "BLOCKED", "NOT_STARTED", "NOT STARTED", "PLANNED",
)


def normalize_status(val: str) -> Optional[str]:
    """Normalize and match candidate status text against canonical status tokens."""
    clean = re.sub(r"^[`*#_\[\]\s\W]+", "", val.strip()).strip()
    clean = re.sub(r"[`*_\[\]]+$", "", clean).strip()
    upper = clean.upper()
    for token in VALID_STATUS_TOKENS:
        if upper == token or upper.startswith((token + " ", token + ":", token + "-", token + "(", token + "_")):
            return token
    return None


class MarkdownTable:
    """Represents a parsed markdown table."""

    def __init__(self, headers: List[str], start_line: int):
        self.headers = headers
        self.start_line = start_line
        self.rows: List[Tuple[int, List[str]]] = []


def parse_markdown_tables(lines: List[str]) -> List[MarkdownTable]:
    """Extract all markdown tables from lines of markdown text."""
    tables: List[MarkdownTable] = []
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx].strip()
        if raw_line.count("|") >= 2 and idx + 1 < len(lines):
            sep_raw = lines[idx + 1].strip()
            if sep_raw.count("|") >= 2:
                sep_cells = [c.strip() for c in sep_raw.strip("|").split("|")]
                if sep_cells and all(c and re.match(r"^[\s:\-]+$", c) and "-" in c for c in sep_cells):
                    raw_headers = [c.strip() for c in raw_line.strip("|").split("|")]
                    table = MarkdownTable(headers=raw_headers, start_line=idx + 1)
                    idx += 2
                    while idx < len(lines):
                        row_raw = lines[idx].strip()
                        if row_raw.count("|") >= 2:
                            table.rows.append((idx + 1, [c.strip() for c in row_raw.strip("|").split("|")]))
                            idx += 1
                        else:
                            break
                    tables.append(table)
                    continue
        idx += 1
    return tables


def find_status_table(
    tables: List[MarkdownTable],
) -> Tuple[Optional[MarkdownTable], Optional[dict], List[Tuple[MarkdownTable, List[str]]]]:
    """Locate the optional Implementation Status Table among parsed tables."""
    candidate_diagnostics: List[Tuple[MarkdownTable, List[str]]] = []
    for tbl in tables:
        h_lowers = [h.lower() for h in tbl.headers]
        wave_idx = next((i for i, h in enumerate(h_lowers) if any(k in h for k in ("wave", "component", "phase"))), None)
        desc_idx = next(
            (i for i, h in enumerate(h_lowers) if i != wave_idx and any(k in h for k in ("description", "scope", "objective", "summary", "details"))),
            None,
        )
        status_idx = next(
            (i for i, h in enumerate(h_lowers) if i not in (wave_idx, desc_idx) and any(k in h for k in ("status", "state", "progress"))),
            None,
        )
        missing = [
            name
            for idx_val, name in ((wave_idx, "Wave/Component"), (desc_idx, "Description/Scope"), (status_idx, "Status"))
            if idx_val is None
        ]
        if not missing:
            return tbl, {"wave_idx": wave_idx, "desc_idx": desc_idx, "status_idx": status_idx}, candidate_diagnostics
        if len(missing) < 3 and (wave_idx is not None or status_idx is not None):
            candidate_diagnostics.append((tbl, missing))
    return None, None, candidate_diagnostics


def _validate_optional_status_table(lines: List[str], waves: Sequence[object], filename: str, errors: List[str]) -> None:
    tables = parse_markdown_tables(lines)
    status_table, col_indices, candidates = find_status_table(tables)
    if status_table is None and candidates:
        cand_tbl, missing_cols = candidates[0]
        errors.append(
            f"{filename}: Implementation Status Table at line {cand_tbl.start_line} missing required "
            f"column(s): {', '.join(missing_cols)}. Required columns: 'Wave', 'Description', and 'Status'."
        )
    elif status_table is not None and col_indices is not None:
        wave_idx = col_indices["wave_idx"]
        status_idx = col_indices["status_idx"]
        if not status_table.rows:
            errors.append(f"{filename}: Line {status_table.start_line}: Implementation Status Table has no rows.")
            return
        for row_line, cells in status_table.rows:
            if status_idx >= len(cells):
                errors.append(f"{filename}: Line {row_line}: Implementation Status Table row missing Status cell.")
                continue
            raw_status = cells[status_idx]
            if not normalize_status(raw_status):
                errors.append(
                    f"{filename}: Line {row_line}: Invalid status '{raw_status}' in Implementation Status Table. "
                    "Valid statuses are: COMPLETED, IN_PROGRESS, PENDING, OPEN, BLOCKED, NOT_STARTED, PLANNED."
                )
        for w in waves:
            wid = getattr(w, "wave_id", getattr(w, "number", ""))
            wnum = getattr(w, "number", wid)
            wline = getattr(w, "start_line", 1)
            wave_pattern = re.compile(rf"\b(?:wave\s+)?(?:{wid}|{wnum})\b", re.IGNORECASE)
            if not any(
                wave_pattern.search(cells[wave_idx] if wave_idx < len(cells) else "") or wave_pattern.search(" ".join(cells))
                for _, cells in status_table.rows
            ):
                errors.append(
                    f"{filename}: Wave {wid} (declared at line {wline}) is missing from the Implementation Status Table."
                )


def validate_plan_content(
    content: str,
    filename: str = "plan.md",
    repo_root: Optional[Path | bool] = None,
    strict: bool = True,
) -> Tuple[bool, List[str]]:
    """Validate markdown implementation plan text via core-governance wave_plan_validator + agents extensions."""
    if isinstance(repo_root, bool):
        strict = repo_root
        actual_repo_root: Optional[Path] = None
    else:
        actual_repo_root = repo_root

    effective_root = (actual_repo_root or ROOT).resolve()
    backend = _load_backend()
    prof = backend.load_repo_plan_profile(effective_root)

    stripped_content, manifest_errs = strip_and_validate_shard_manifests(content, filename)
    _ok, core_errs = backend.validate_plan_content(
        stripped_content,
        filename=filename,
        strict=strict,
        require_objective=bool(prof.get("require_objective", True)),
        allow_sharded=bool(prof.get("allow_sharded", True)),
        max_waves=int(prof.get("max_waves", 0)),
        base_max_words=int(prof.get("base_max_words", MAX_PLAN_WORDS)),
        max_scaled_words=int(prof.get("max_scaled_words", 3500)),
    )
    errors: List[str] = [
        e.replace("must contain at least one itemized deliverable.", "must contain at least one itemized output or target file.")
        for e in core_errs
    ]
    waves = backend.extract_waves(stripped_content)
    if not waves:
        return False, errors

    errors.extend(manifest_errs)
    if strict:
        errors.extend(validate_holistic_pipeline_alignment(content, waves, filename))
    else:
        _ = validate_wave_dag_sequence

    _validate_optional_status_table(content.splitlines(), waves, filename, errors)

    is_model_valid, unapproved_tokens, _ = validate_model_token_registry(content, repo_root=effective_root)
    if not is_model_valid:
        for tok in unapproved_tokens:
            errors.append(
                f"{filename}: References unapproved model token '{tok}'. Models in implementation plans must resolve "
                "to canonical approved provider profiles in config/provider_profiles.yaml."
            )

    return len(errors) == 0, errors


def validate_file(
    path: Path,
    legacy_exemptions: Optional[set[str]] = None,
    repo_root: Optional[Path] = None,
    strict: bool = True,
) -> Tuple[bool, List[str]]:
    """Validate a single implementation plan file on disk."""
    effective_root = (repo_root or ROOT).resolve()
    prof = _load_backend().load_repo_plan_profile(effective_root)
    exemptions = set(legacy_exemptions or DEFAULT_LEGACY_EXEMPTIONS) | set(prof.get("legacy_exemptions", ()))
    if path.name in exemptions:
        return True, [f"[EXEMPT] Skipped legacy plan: {path.name}"]

    if not path.is_file():
        return False, [f"File not found: {path}"]

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, [f"Failed reading {path}: {exc}"]

    return validate_plan_content(content, filename=str(path.name), repo_root=effective_root, strict=strict)


def extract_wave_summary_entries(content: str) -> Tuple[List[dict], List[str]]:
    """Extract wave summary records (wave, description, status, check_open) from plan content."""
    lines = content.splitlines()
    tables = parse_markdown_tables(lines)
    status_table, col_indices, _ = find_status_table(tables)
    if not status_table or not col_indices:
        waves: List[dict] = []
        for line in lines:
            m = RE_WAVE_HEADER.match(line.strip())
            if m:
                waves.append({
                    "wave": f"Wave {m.group(2)}{(m.group(3) or '').upper()}",
                    "description": (m.group(4) or "").strip(),
                    "status": "OPEN",
                    "check_open": "[ ] OPEN",
                    "is_checked": False,
                })
        return waves, ["Parsed from wave headers (no status table)"] if waves else ["No waves found"]

    wave_idx = col_indices["wave_idx"]
    desc_idx = col_indices["desc_idx"]
    status_idx = col_indices["status_idx"]
    entries: List[dict] = []
    for line_no, cells in status_table.rows:
        wave_cell = cells[wave_idx] if wave_idx < len(cells) else f"Row {line_no}"
        desc_cell = cells[desc_idx] if desc_idx < len(cells) else ""
        raw_status = cells[status_idx] if status_idx < len(cells) else "UNKNOWN"
        norm_status = normalize_status(raw_status) or raw_status.strip()
        is_checked = norm_status.upper() in ("COMPLETED", "COMPLETE", "DONE")
        m = re.match(r"^(Wave\s+\d+)", wave_cell, re.IGNORECASE)
        entries.append({
            "wave": m.group(1).title() if m else wave_cell.strip(),
            "wave_full": wave_cell.strip(),
            "description": desc_cell.strip(),
            "status": norm_status,
            "check_open": "[x] CHECK" if is_checked else "[ ] OPEN",
            "is_checked": is_checked,
        })
    return entries, []


def render_wave_summary_table(plan_name: str, entries: List[dict]) -> str:
    """Render wave summary table confirming wave number, description, and check/open status."""
    if not entries:
        return f"No wave summary entries found for {plan_name}."
    headers = ["Wave #", "Description / Scope", "Status", "Check/Open"]
    rows = [[e["wave"], e["description"][:62] + "..." if len(e["description"]) > 65 else e["description"], e["status"], e["check_open"]] for e in entries]
    col_widths = [max([len(headers[i]), *(len(r[i]) for r in rows)]) for i in range(len(headers))]
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    out = ["\n" + "=" * 80, f"  MANDATORY WAVE SUMMARY TABLE: {plan_name}", "=" * 80, sep, header_str, sep]
    out.extend("| " + " | ".join(r[i].ljust(col_widths[i]) for i in range(len(headers))) + " |" for r in rows)
    out.append(sep)
    return "\n".join(out)


def render_markdown_wave_summary_table(plan_name: str, entries: List[dict]) -> str:
    """Render wave summary table in standard GitHub-flavored Markdown."""
    if not entries:
        return f"No wave summary entries found for {plan_name}."
    lines = [f"### Wave Summary Table: {plan_name}", "", "| Wave # | Description / Scope | Status | Check/Open |", "| :--- | :--- | :--- | :--- |"]
    for e in entries:
        lines.append(f"| {e['wave']} | {e['description'].replace('|', '\\|')} | {e['status']} | {e['check_open']} |")
    lines.append("")
    return "\n".join(lines)


def _resolve_common_repo_root(root: Path) -> Path:
    try:
        res = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True, check=False, timeout=5)
        raw = res.stdout.strip()
        if res.returncode == 0 and raw:
            common_git = Path(raw) if Path(raw).is_absolute() else (root / raw).resolve()
            if common_git.name == ".git":
                return common_git.parent.resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return root


def _has_wave_header(plan_path: Path) -> bool:
    if plan_path.name in DEFAULT_LEGACY_EXEMPTIONS:
        return True
    try:
        txt = plan_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(RE_WAVE_HEADER.match(ln.strip()) for ln in txt.splitlines())


def get_active_plan_file(repo_root: Optional[Path] = None) -> Optional[Path]:
    """Discover the active implementation plan file on disk, prioritizing workspace and IDE artifacts."""
    root = (repo_root or ROOT).resolve()
    common_root = _resolve_common_repo_root(root)
    explicit_plan = os.environ.get("AGY_PLAN_FILE")
    if explicit_plan and is_git_repo and Path(explicit_plan).is_file():
        return Path(explicit_plan).resolve()
    for env_var in ("ANTIGRAVITY_ARTIFACTS_DIR", "ARTIFACT_DIRECTORY_PATH"):
        val = os.environ.get(env_var)
        if val and (Path(val) / "implementation_plan.md").is_file():
            return Path(val) / "implementation_plan.md"
    if (root / "implementation_plan.md").is_file():
        return root / "implementation_plan.md"
    conv_id = os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    app_data = os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    brain_dirs = [*([Path(app_data) / "brain"] if app_data else []), Path.home() / ".gemini" / "antigravity" / "brain", Path.home() / ".gemini" / "antigravity-ide" / "brain"]
    if conv_id:
        for bdir in brain_dirs:
            if (bdir / conv_id / "implementation_plan.md").is_file():
                return bdir / conv_id / "implementation_plan.md"
    else:
        for bdir in brain_dirs:
            if not bdir.is_dir():
                continue
            for cand in sorted(bdir.glob("*/implementation_plan.md"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    content = cand.read_text(encoding="utf-8")
                    git_matches = re.findall(r"/Git/([^/\s\"'\`\)]+)", content)
                    if git_matches and not any(m in (root.name, common_root.name) for m in git_matches):
                        continue
                    for base_root in (root, common_root):
                        recent = sorted([p for p in get_governed_plan_files(base_root) if _has_wave_header(p)], key=lambda p: p.stat().st_mtime, reverse=True)
                        if recent and recent[0].stat().st_mtime > cand.stat().st_mtime:
                            return recent[0]
                    return cand
                except (OSError, ValueError):
                    continue
    for base_root in (root, common_root):
        recent = sorted([p for p in get_governed_plan_files(base_root) if _has_wave_header(p)], key=lambda p: p.stat().st_mtime, reverse=True)
        if recent:
            return recent[0]
    return None


def get_governed_plan_files(repo_root: Path) -> List[Path]:
    """Return tracked or staged plans under plans/."""
    plans_dir = repo_root / "plans"
    if not plans_dir.is_dir():
        return []
    if (repo_root / ".git").exists():
        try:
            res = subprocess.run(["git", "ls-files", "plans"], cwd=repo_root, capture_output=True, text=True, check=False, timeout=10)
            if res.returncode == 0:
                tracked = {(repo_root / ln.strip()) for ln in res.stdout.splitlines() if ln.strip().endswith(".md") and (repo_root / ln.strip()).is_file()}
                for sp in get_staged_plan_files(repo_root):
                    if sp.parent.resolve() == plans_dir.resolve():
                        tracked.add(sp)
                if tracked:
                    return sorted(tracked)
        except (OSError, subprocess.SubprocessError):
            pass
    return [p for p in sorted(plans_dir.glob("*.md")) if _has_wave_header(p)]


def get_staged_plan_files(repo_root: Path) -> List[Path]:
    """Retrieve staged markdown files matching implementation plan naming patterns."""
    try:
        res = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], cwd=repo_root, capture_output=True, text=True, check=True, timeout=30)
        staged: List[Path] = []
        for line in res.stdout.splitlines():
            clean = line.strip()
            if clean.endswith(".md") and ("implementation_plan" in clean.lower() or clean.startswith("plans/")):
                full_path = repo_root / clean
                if full_path.is_file():
                    staged.append(full_path)
        return staged
    except (OSError, subprocess.SubprocessError):
        return []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate wave-based implementation plans against repository governance invariants.")
    parser.add_argument("--file", type=Path, help="Path to a specific implementation plan file to validate.")
    parser.add_argument("--staged", action="store_true", help="Validate any implementation plan files currently staged in git.")
    parser.add_argument("--all-plans", action="store_true", help="Validate all active plans under plans/.")
    parser.add_argument("--repository-root", type=Path, default=ROOT, help="Repository root directory.")
    parser.add_argument("--markdown", action="store_true", help="Render wave summary table in standard Markdown format.")
    args = parser.parse_args(argv)

    root = args.repository_root.resolve()
    target_files: List[Path] = []
    if args.file:
        target_files.append(args.file if args.file.is_absolute() else root / args.file)
    elif args.staged:
        staged_files = get_staged_plan_files(root)
        if not staged_files:
            print("No implementation plan files currently staged.")
            return 0
        target_files.extend(staged_files)
    elif args.all_plans:
        target_files.extend(get_governed_plan_files(root))
    else:
        active_plan = get_active_plan_file(root)
        if active_plan:
            target_files.append(active_plan)

    if not target_files:
        print("No implementation plan files to validate.")
        return 0

    all_passed = True
    for plan_file in target_files:
        passed, issues = validate_file(plan_file, repo_root=root)
        print(f"{'[PASS]' if passed else '[FAIL]'} {plan_file.name}")
        for err in issues:
            print(f"       - {err}" if not passed else f"       {err}")
        if not passed:
            all_passed = False
        try:
            entries, _ = extract_wave_summary_entries(plan_file.read_text(encoding="utf-8"))
            if entries:
                print(render_markdown_wave_summary_table(plan_file.name, entries) if args.markdown else render_wave_summary_table(plan_file.name, entries))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
