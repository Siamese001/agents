"""Strict length and execution-evidence checks for newly authored wave plans."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence


def _resolve_max_plan_words() -> int:
    """Resolve INV-WAVE-PLAN-MAX-WORDS dynamically from config/governance/policy_registry.yaml."""
    reg_path = Path(__file__).resolve().parents[2] / "config" / "governance" / "policy_registry.yaml"
    if reg_path.is_file():
        try:
            import yaml  # type: ignore

            raw = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
            for entry in raw.get("policies", []):
                if isinstance(entry, dict) and entry.get("id") == "INV-WAVE-PLAN-MAX-WORDS":
                    val = entry.get("threshold")
                    if isinstance(val, int) and val > 0:
                        return val
        except Exception:  # guardian: allow-silent-swallow -- safe fallback when yaml parser unavailable
            pass
    return 1000


MAX_PLAN_WORDS: int = _resolve_max_plan_words()
_GATE_HEADING = re.compile(
    r"^#{3,4}\s+.*(?:receipt|completion\s+gate|exit\s+gate|verification).*",
    re.IGNORECASE,
)
_FIELD_PATTERNS = {
    "Run": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Run(?:\*\*)?\s*:", re.IGNORECASE),
    "Input": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Input(?:\*\*)?\s*:", re.IGNORECASE),
    "Expected": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Expected(?:\*\*)?\s*:", re.IGNORECASE),
    "Verify independently": re.compile(
        r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?(?:Verify independently|Independent check)(?:\*\*)?\s*:",
        re.IGNORECASE,
    ),
    "Fail if": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Fail if(?:\*\*)?\s*:", re.IGNORECASE),
    "Record": re.compile(r"^\s*(?:[-*+]|\d+\.)?\s*(?:\*\*)?Record(?:\*\*)?\s*:", re.IGNORECASE),
}


def _gate_lines(wave: object) -> list[str]:
    lines = getattr(wave, "lines", [])
    active = False
    result: list[str] = []
    for _line_number, line in lines:
        if _GATE_HEADING.search(line.strip()):
            active = True
            continue
        if active and re.match(r"^\s*#{2,4}\s+", line):
            break
        if active:
            result.append(line)
    return result


def validate_execution_evidence(content: str, waves: Sequence[object], filename: str) -> list[str]:
    """Require bounded plans and explicit run/evidence fields in each wave gate."""
    errors: list[str] = []
    word_count = len(content.split())
    if word_count > MAX_PLAN_WORDS:
        errors.append(
            f"{filename}: Plan has {word_count} words; newly authored wave plans are capped at "
            f"{MAX_PLAN_WORDS} words (target 500–800)."
        )

    for wave in waves:
        gate_lines = _gate_lines(wave)
        if not gate_lines:
            continue  # The structural validator reports the missing gate heading.
        present = {
            label for label, pattern in _FIELD_PATTERNS.items()
            if any(pattern.search(line) for line in gate_lines)
        }
        missing = [label for label in _FIELD_PATTERNS if label not in present]
        if missing:
            number = getattr(wave, "number", "?")
            errors.append(
                f"{filename}: Wave {number} completion gate must specify: {', '.join(missing)}. "
                "Receipts document runs; independently observed behavior determines completion."
            )
    return errors
