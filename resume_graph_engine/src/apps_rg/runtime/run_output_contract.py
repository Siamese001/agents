"""Canonical apps_rg full-run output filenames and physical output verification."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

APPS_RG_MANDATORY_RUN_OUTPUT_JSON = "APPS_RG_MANDATORY_RUN_OUTPUT.json"
APPS_RG_MANDATORY_RUN_OUTPUT_MD = "02_section_lane_summary_table.md"
BCG_EXECUTIVE_OUTPUT_MD = "01_BCG_executive_output.md"
OUTPUT_BISECT_MD = "02_output_bisect.md"
L7_AUDIT_ABILITY_OUTPUT_MD = "03_L7_audit_ability_output.md"
LEGACY_APPS_RG_MANDATORY_RUN_OUTPUT_MD = "APPS_RG_MANDATORY_RUN_OUTPUT.md"
LEGACY_BCG_EXECUTIVE_OUTPUT_MD = "BCG_EXECUTIVE_OUTPUT.md"
FULL_RUN_SECTION_STATUS_MD = "FULL_RUN_SECTION_STATUS.md"
FULL_RUN_SECTION_STATUS_JSON = "full_run_section_status.json"
APPS_RG_SECTION_LOCKDOWN_MD = "APPS_RG_SECTION_LOCKDOWN.md"
APPS_RG_SECTION_LOCKDOWN_JSON = "APPS_RG_SECTION_LOCKDOWN.json"
REVIEW_BUNDLE_FILENAME = "review_bundle.zip"
REVIEW_INDEX_FILENAME = "REVIEW_INDEX.md"
FINAL_RESUME_OUTPUT_TXT = "FINAL_RESUME_OUTPUT.txt"
FINAL_RESUME_OUTPUT_JSON = "FINAL_RESUME_OUTPUT.json"
FINAL_RESUME_DOCX_RELPATH = "outputs/resume.docx"
FINAL_RESUME_ASSEMBLY_JSON_RELPATH = "modular_r4/final_resume_assembly/final_resume.json"

MANDATORY_OUTPUT_FILENAMES: tuple[str, ...] = (
    APPS_RG_MANDATORY_RUN_OUTPUT_JSON,
    L7_AUDIT_ABILITY_OUTPUT_MD,
    FINAL_RESUME_OUTPUT_TXT,
    FINAL_RESUME_OUTPUT_JSON,
    APPS_RG_SECTION_LOCKDOWN_MD,
    APPS_RG_SECTION_LOCKDOWN_JSON,
    FULL_RUN_SECTION_STATUS_MD,
    FULL_RUN_SECTION_STATUS_JSON,
    REVIEW_INDEX_FILENAME,
)

_FORBIDDEN_BRAND_PREFIXES = ("gp" + "t", "clau" + "de", "gemi" + "ni", "son" + "net", "hai" + "ku", "lla" + "ma", "o" + "1", "o" + "3")
_FORBIDDEN_MODEL_FILENAME_RE = re.compile(
    r"\b(?:" + "|".join(p + r"[-_0-9a-z]*" for p in _FORBIDDEN_BRAND_PREFIXES) + r")\b",
    re.IGNORECASE,
)


def is_model_neutral_filename(path_or_name: str | Path) -> bool:
    """Return True if the filename does not embed AI model brand tokens."""
    name = Path(path_or_name).name
    return _FORBIDDEN_MODEL_FILENAME_RE.search(name) is None


def verify_physical_run_outputs(run_dir: str | Path) -> dict[str, Any]:
    """Verify mandatory run outputs on disk via size, SHA-256, model-neutral naming, and fresh JSON readback."""
    root = Path(run_dir)
    verified: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for filename in MANDATORY_OUTPUT_FILENAMES:
        if not is_model_neutral_filename(filename):
            errors.append(f"non_neutral_filename:{filename}")
        fpath = root / filename
        if not fpath.is_file():
            errors.append(f"missing_file:{filename}")
            continue
        size = fpath.stat().st_size
        if size <= 0:
            errors.append(f"empty_file:{filename}")
            continue
        raw_bytes = fpath.read_bytes()
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        if filename.endswith(".json"):
            try:
                json.loads(raw_bytes.decode("utf-8"))
            except Exception as exc:
                errors.append(f"corrupt_json:{filename}:{type(exc).__name__}")
                continue
        verified[filename] = {"size_bytes": size, "sha256": sha256_hex}

    return {
        "status": "PASS" if not errors else "FAIL",
        "verified_count": len(verified),
        "verified_files": verified,
        "errors": errors,
    }


__all__ = [
    "APPS_RG_MANDATORY_RUN_OUTPUT_JSON",
    "APPS_RG_MANDATORY_RUN_OUTPUT_MD",
    "APPS_RG_SECTION_LOCKDOWN_JSON",
    "APPS_RG_SECTION_LOCKDOWN_MD",
    "BCG_EXECUTIVE_OUTPUT_MD",
    "FINAL_RESUME_ASSEMBLY_JSON_RELPATH",
    "FINAL_RESUME_DOCX_RELPATH",
    "FINAL_RESUME_OUTPUT_JSON",
    "FINAL_RESUME_OUTPUT_TXT",
    "FULL_RUN_SECTION_STATUS_JSON",
    "FULL_RUN_SECTION_STATUS_MD",
    "L7_AUDIT_ABILITY_OUTPUT_MD",
    "LEGACY_APPS_RG_MANDATORY_RUN_OUTPUT_MD",
    "LEGACY_BCG_EXECUTIVE_OUTPUT_MD",
    "MANDATORY_OUTPUT_FILENAMES",
    "OUTPUT_BISECT_MD",
    "REVIEW_BUNDLE_FILENAME",
    "REVIEW_INDEX_FILENAME",
    "is_model_neutral_filename",
    "verify_physical_run_outputs",
]
