#!/usr/bin/env python3
"""Mechanical enforcement validator for wave-based implementation plans.

Enforces governance rules defined in AGENTS.md and docs/refactoring-wave-protocol.md:
1. Every implementation plan must be wave-based (decomposed into sequential numbered waves).
2. Wave numbering must start at 0 or 1 and increment consecutively without gaps.
3. Every wave must declare explicit milestones & deliverables, acceptance criteria,
   and a runtime receipt or completion gate.
4. Each wave must specify at least one concrete deliverable or target file.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from tools.hitl_governance import validate_model_token_registry
except ImportError:
    from hitl_governance import validate_model_token_registry  # type: ignore

# Historical / frozen plans grandfathered from strict wave schema
DEFAULT_LEGACY_EXEMPTIONS = {
    "core-judge-panel-harness-f3c8d1.md",
    "live-llm-enforcement-wave1-b7d14e.md",
    "governance-dedup-closeout-e8a4c2.md",
    "runtime-seam-unification-5e8a1b.md",
}

# Regex patterns for wave parsing
RE_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
RE_WAVE_HEADER = re.compile(r"^(#{2,3})\s+Wave\s+(\d+)(?:[:\s\-]+(.*))?$", re.IGNORECASE)

# Patterns for required wave subsections
RE_MILESTONES = re.compile(
    r"(?:^#{3,4}\s+.*(?:milestone|deliverable).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:milestone|deliverable).*?)\*\*)",
    re.IGNORECASE,
)
RE_CRITERIA = re.compile(
    r"(?:^#{3,4}\s+.*(?:acceptance\s+criteria|criteria).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:acceptance\s+criteria|criteria).*?)\*\*)",
    re.IGNORECASE,
)
RE_RECEIPT_GATE = re.compile(
    r"(?:^#{3,4}\s+.*(?:receipt|completion\s+gate|exit\s+gate|verification).*)|(?:^\s*(?:[-*+]\s+)?\*\*(?:.*(?:receipt|completion\s+gate|exit\s+gate|verification).*?)\*\*)",
    re.IGNORECASE,
)
RE_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.+)$")

VALID_STATUS_TOKENS = (
    "COMPLETED", "COMPLETE", "DONE", "IN_PROGRESS", "IN PROGRESS",
    "PENDING_APPROVAL", "PENDING APPROVAL", "PENDING", "OPEN",
    "BLOCKED", "NOT_STARTED", "NOT STARTED", "PLANNED",
)



def normalize_status(val: str) -> Optional[str]:
    """Normalize and match candidate status text against canonical status tokens."""
    clean = val.strip()
    # Strip leading/trailing markdown decorators, backticks, asterisks, brackets, emojis
    clean = re.sub(r"^[`*#_\[\]\s\W]+", "", clean).strip()
    clean = re.sub(r"[`*_\[\]]+$", "", clean).strip()
    upper = clean.upper()
    for token in VALID_STATUS_TOKENS:
        if (
            upper == token
            or upper.startswith(token + " ")
            or upper.startswith(token + ":")
            or upper.startswith(token + "-")
            or upper.startswith(token + "(")
            or upper.startswith(token + "_")
        ):
            return token
    return None


class MarkdownTable:
    """Represents a parsed markdown table."""

    def __init__(self, headers: List[str], start_line: int):
        self.headers = headers
        self.start_line = start_line
        self.rows: List[Tuple[int, List[str]]] = []  # (line_number, cell_values)


def parse_markdown_tables(lines: List[str]) -> List[MarkdownTable]:
    """Extract all markdown tables from lines of markdown text."""
    tables: List[MarkdownTable] = []
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx].strip()
        if raw_line.count("|") >= 2:
            if idx + 1 < len(lines):
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
                                cells = [c.strip() for c in row_raw.strip("|").split("|")]
                                table.rows.append((idx + 1, cells))
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
    """Locate the Implementation Status Table among parsed tables."""
    candidate_diagnostics: List[Tuple[MarkdownTable, List[str]]] = []
    for tbl in tables:
        h_lowers = [h.lower() for h in tbl.headers]
        wave_idx = next(
            (i for i, h in enumerate(h_lowers) if any(k in h for k in ("wave", "component", "phase"))),
            None,
        )
        desc_idx = next(
            (
                i
                for i, h in enumerate(h_lowers)
                if i != wave_idx and any(k in h for k in ("description", "scope", "objective", "summary", "details"))
            ),
            None,
        )
        status_idx = next(
            (
                i
                for i, h in enumerate(h_lowers)
                if i not in (wave_idx, desc_idx) and any(k in h for k in ("status", "state", "progress"))
            ),
            None,
        )

        missing: List[str] = []
        if wave_idx is None:
            missing.append("Wave/Component")
        if desc_idx is None:
            missing.append("Description/Scope")
        if status_idx is None:
            missing.append("Status")

        if not missing:
            return tbl, {"wave_idx": wave_idx, "desc_idx": desc_idx, "status_idx": status_idx}, candidate_diagnostics
        elif len(missing) < 3 and (wave_idx is not None or status_idx is not None):
            candidate_diagnostics.append((tbl, missing))

    return None, None, candidate_diagnostics


class WaveSection:
    """Represents a parsed wave block within an implementation plan."""

    def __init__(self, number: int, title: str, start_line: int, header_level: int = 2):
        self.number = number
        self.title = title
        self.start_line = start_line
        self.header_level = header_level
        self.lines: List[Tuple[int, str]] = []  # (line_number, line_text)
        self.has_milestones = False
        self.has_criteria = False
        self.has_receipt_gate = False
        self.deliverable_items: List[str] = []

    def analyze(self) -> None:
        """Inspect contents of the wave block for required governance sections."""
        current_sub: Optional[str] = None
        for line_no, line in self.lines:
            stripped = line.strip()
            if not stripped:
                continue

            if RE_MILESTONES.search(stripped):
                self.has_milestones = True
                current_sub = "milestones"
                continue
            elif RE_CRITERIA.search(stripped):
                self.has_criteria = True
                current_sub = "criteria"
                continue
            elif RE_RECEIPT_GATE.search(stripped):
                self.has_receipt_gate = True
                current_sub = "receipt"
                continue
            elif stripped.startswith("### ") or stripped.startswith("## "):
                current_sub = "other"
                continue

            item_match = RE_ITEM.match(stripped)
            if item_match:
                content = item_match.group(1).strip()
                if current_sub == "milestones":
                    self.deliverable_items.append(content)
                elif current_sub is None and any(
                    k in content.lower() for k in ("deliverable", "milestone", "[new]", "[modify]", "[delete]")
                ):
                    self.deliverable_items.append(content)


def validate_plan_content(
    content: str,
    filename: str = "plan.md",
    repo_root: Optional[Path] = None,
) -> Tuple[bool, List[str]]:
    """Validate markdown implementation plan text against wave-based governance schema.

    Returns:
        (is_compliant: bool, errors: list[str])
    """
    errors: List[str] = []
    lines = content.splitlines()

    # 1. Document Title Verification
    has_title = False
    for line in lines:
        if line.startswith("# ") and line[2:].strip():
            has_title = True
            break
    if not has_title:
        errors.append(f"{filename}: Missing required top-level title ('# <Plan Title>').")

    # 2. Extract Wave Sections
    waves: List[WaveSection] = []
    current_wave: Optional[WaveSection] = None

    for idx, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        wave_match = RE_WAVE_HEADER.match(stripped)
        if wave_match:
            hashes = wave_match.group(1)
            wave_num = int(wave_match.group(2))
            wave_title = (wave_match.group(3) or "").strip()
            current_wave = WaveSection(wave_num, wave_title, idx, header_level=len(hashes))
            waves.append(current_wave)
            continue

        if current_wave is not None and stripped.startswith("#"):
            # Check if this heading closes the current wave
            heading_hashes = len(stripped) - len(stripped.lstrip("#"))
            if heading_hashes <= current_wave.header_level:
                current_wave = None

        if current_wave is not None:
            current_wave.lines.append((idx, raw_line))

    if not waves:
        errors.append(
            f"{filename}: Implementation plan must be wave-based. Found 0 wave sections ('## Wave <N>'). "
            "Flat or unstructured plans are strictly prohibited."
        )
        return False, errors

    # 3. Validate Sequential Wave Numbering
    start_num = waves[0].number
    if start_num not in (0, 1):
        errors.append(
            f"{filename}: First wave must be numbered Wave 0 or Wave 1. Found Wave {start_num} at line {waves[0].start_line}."
        )

    expected_num = start_num
    for w in waves:
        if w.number != expected_num:
            errors.append(
                f"{filename}: Non-sequential wave numbering at line {w.start_line}. "
                f"Expected Wave {expected_num}, found Wave {w.number}."
            )
            expected_num = w.number + 1
        else:
            expected_num += 1

    # 4. Validate Required Subsections and Deliverables per Wave
    for w in waves:
        w.analyze()
        prefix = f"{filename}: Line {w.start_line} (Wave {w.number})"

        if not w.has_milestones:
            errors.append(
                f"{prefix}: Missing required 'Milestones & Deliverables' section "
                f"(expected '### Milestones & Deliverables' or '**Milestones**')."
            )
        elif not w.deliverable_items:
            errors.append(
                f"{prefix}: 'Milestones & Deliverables' must contain at least one itemized output or target file."
            )

        if not w.has_criteria:
            errors.append(
                f"{prefix}: Missing required 'Acceptance Criteria' section "
                f"(expected '### Acceptance Criteria' or '**Acceptance Criteria**')."
            )

        if not w.has_receipt_gate:
            errors.append(
                f"{prefix}: Missing required 'Runtime Receipt & Completion Gate' section "
                f"(expected '### Runtime Receipt & Completion Gate', '### Exit Gate', or '**Runtime Receipt**')."
            )

    # 5. Validate Mandatory Implementation Status Table
    tables = parse_markdown_tables(lines)
    status_table, col_indices, candidates = find_status_table(tables)

    if status_table is None:
        if candidates:
            cand_tbl, missing_cols = candidates[0]
            errors.append(
                f"{filename}: Implementation Status Table at line {cand_tbl.start_line} missing required "
                f"column(s): {', '.join(missing_cols)}. Required columns: 'Wave', 'Description', and 'Status'."
            )
        else:
            errors.append(
                f"{filename}: Missing mandatory Implementation Status Table. Plans must include a markdown "
                "table with columns for Wave/Component, Description/Scope, and Status (e.g. COMPLETED, IN_PROGRESS, PENDING, OPEN, BLOCKED)."
            )
    else:
        wave_idx = col_indices["wave_idx"]
        status_idx = col_indices["status_idx"]

        if not status_table.rows:
            errors.append(f"{filename}: Line {status_table.start_line}: Implementation Status Table has no rows.")
        else:
            # Check valid status in each row
            for row_line, cells in status_table.rows:
                if status_idx >= len(cells):
                    errors.append(f"{filename}: Line {row_line}: Implementation Status Table row missing Status cell.")
                    continue
                raw_status = cells[status_idx]
                norm_status = normalize_status(raw_status)
                if not norm_status:
                    errors.append(
                        f"{filename}: Line {row_line}: Invalid status '{raw_status}' in Implementation Status Table. "
                        "Valid statuses are: COMPLETED, IN_PROGRESS, PENDING, OPEN, BLOCKED, NOT_STARTED, PLANNED."
                    )

            # Check that all declared waves are represented in the status table
            for w in waves:
                wave_pattern = re.compile(rf"\b(?:wave\s+)?{w.number}\b", re.IGNORECASE)
                matched = False
                for _, cells in status_table.rows:
                    wave_cell = cells[wave_idx] if wave_idx < len(cells) else ""
                    if wave_pattern.search(wave_cell) or wave_pattern.search(" ".join(cells)):
                        matched = True
                        break
                if not matched:
                    errors.append(
                        f"{filename}: Wave {w.number} (declared at line {w.start_line}) is missing from the "
                        "Implementation Status Table."
                    )

    # 6. Model Provider Registry Conformance
    is_model_valid, unapproved_tokens, _ = validate_model_token_registry(content, repo_root=repo_root or ROOT)
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
) -> Tuple[bool, List[str]]:
    """Validate a single implementation plan file on disk."""
    exemptions = legacy_exemptions or DEFAULT_LEGACY_EXEMPTIONS
    if path.name in exemptions:
        return True, [f"[EXEMPT] Skipped legacy plan: {path.name}"]

    if not path.is_file():
        return False, [f"File not found: {path}"]

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, [f"Failed reading {path}: {exc}"]

    return validate_plan_content(content, filename=str(path.name), repo_root=repo_root or ROOT)


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
                w_num = f"Wave {m.group(2)}"
                w_title = (m.group(3) or "").strip()
                waves.append({
                    "wave": w_num,
                    "description": w_title,
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
        check_open = "[x] CHECK" if is_checked else "[ ] OPEN"

        m = re.match(r"^(Wave\s+\d+)", wave_cell, re.IGNORECASE)
        wave_num = m.group(1).title() if m else wave_cell.strip()

        entries.append({
            "wave": wave_num,
            "wave_full": wave_cell.strip(),
            "description": desc_cell.strip(),
            "status": norm_status,
            "check_open": check_open,
            "is_checked": is_checked,
        })
    return entries, []


def render_wave_summary_table(plan_name: str, entries: List[dict]) -> str:
    """Render mandatory wave summary table confirming wave number, description, and check/open status."""
    if not entries:
        return f"No wave summary entries found for {plan_name}."

    headers = ["Wave #", "Description / Scope", "Status", "Check/Open"]
    rows = []
    for e in entries:
        desc = e["description"]
        if len(desc) > 65:
            desc = desc[:62] + "..."
        rows.append([e["wave"], desc, e["status"], e["check_open"]])

    col_widths = [len(h) for h in headers]
    for r in rows:
        for i, val in enumerate(r):
            col_widths[i] = max(col_widths[i], len(val))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_str = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    lines = [
        f"\n================================================================================",
        f"  MANDATORY WAVE SUMMARY TABLE: {plan_name}",
        f"================================================================================",
        sep,
        header_str,
        sep,
    ]
    for r in rows:
        row_str = "| " + " | ".join(r[i].ljust(col_widths[i]) for i in range(len(headers))) + " |"
        lines.append(row_str)
    lines.append(sep)
    return "\n".join(lines)


def render_markdown_wave_summary_table(plan_name: str, entries: List[dict]) -> str:
    """Render mandatory wave summary table in standard GitHub-flavored Markdown for chat responses."""
    if not entries:
        return f"No wave summary entries found for {plan_name}."

    lines = [
        f"### Wave Summary Table: {plan_name}",
        "",
        "| Wave # | Description / Scope | Status | Check/Open |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for e in entries:
        desc = e["description"].replace("|", "\\|")
        lines.append(f"| {e['wave']} | {desc} | {e['status']} | {e['check_open']} |")
    lines.append("")
    return "\n".join(lines)


def get_active_plan_file(repo_root: Optional[Path] = None) -> Optional[Path]:
    """Discover the active implementation plan file on disk, prioritizing workspace and IDE artifacts."""
    root = (repo_root or ROOT).resolve()

    # 1. Check workspace repo root implementation_plan.md
    imp_plan = root / "implementation_plan.md"
    if imp_plan.is_file():
        return imp_plan

    # 2. Check explicit environment variables
    for env_var in ("ANTIGRAVITY_ARTIFACTS_DIR", "ARTIFACT_DIRECTORY_PATH"):
        val = os.environ.get(env_var)
        if val:
            cand = Path(val) / "implementation_plan.md"
            if cand.is_file():
                return cand

    # 3. Check Antigravity IDE brain artifacts directory (~/.gemini/antigravity-ide/brain/*)
    ide_brain_dir = Path.home() / ".gemini" / "antigravity-ide" / "brain"
    if ide_brain_dir.is_dir():
        recent_brain_plans = sorted(
            ide_brain_dir.glob("*/implementation_plan.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if recent_brain_plans:
            latest_brain = recent_brain_plans[0]
            # Compare with repo plans; if brain plan is more recent, prefer it
            plans_dir = root / "plans"
            if plans_dir.is_dir():
                recent_plans = sorted(plans_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
                if recent_plans and recent_plans[0].stat().st_mtime > latest_brain.stat().st_mtime:
                    return recent_plans[0]
            return latest_brain

    # 4. Fall back to plans/ directory
    plans_dir = root / "plans"
    if plans_dir.is_dir():
        recent_plans = sorted(plans_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if recent_plans:
            return recent_plans[0]
    return None


def get_staged_plan_files(repo_root: Path) -> List[Path]:
    """Retrieve staged markdown files matching implementation plan naming patterns."""
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        staged: List[Path] = []
        for line in res.stdout.splitlines():
            clean = line.strip()
            if not clean.endswith(".md"):
                continue
            lower = clean.lower()
            if "implementation_plan" in lower or (clean.startswith("plans/") and lower.endswith(".md")):
                full_path = repo_root / clean
                if full_path.is_file():
                    staged.append(full_path)
        return staged
    except Exception:
        return []


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate wave-based implementation plans against repository governance invariants."
    )
    parser.add_argument("--file", type=Path, help="Path to a specific implementation plan file to validate.")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Validate any implementation plan files currently staged in git.",
    )
    parser.add_argument(
        "--all-plans",
        action="store_true",
        help="Validate all active plans under plans/.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
        help="Repository root directory.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render wave summary table in standard Markdown format for chat responses.",
    )
    args = parser.parse_args(argv)

    root = args.repository_root.resolve()
    target_files: List[Path] = []

    if args.file:
        target_files.append(args.file if args.file.is_absolute() else root / args.file)
    elif args.staged:
        staged_files = get_staged_plan_files(root)
        if staged_files:
            target_files.extend(staged_files)
        else:
            active_plan = get_active_plan_file(root)
            if active_plan:
                print(f"[Pre-Commit] Validating active plan: {active_plan.name}")
                target_files.append(active_plan)
            else:
                print("No implementation plan files currently staged or active.")
                return 0
    elif args.all_plans:
        plans_dir = root / "plans"
        if plans_dir.is_dir():
            target_files.extend(sorted(plans_dir.glob("*.md")))
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
        prefix = "[PASS]" if passed else "[FAIL]"
        print(f"{prefix} {plan_file.name}")
        for err in issues:
            print(f"       - {err}" if not passed else f"       {err}")
        if not passed:
            all_passed = False
        try:
            entries, _ = extract_wave_summary_entries(plan_file.read_text(encoding="utf-8"))
            if entries:
                if args.markdown:
                    print(render_markdown_wave_summary_table(plan_file.name, entries))
                else:
                    print(render_wave_summary_table(plan_file.name, entries))
        except Exception:
            pass

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())


