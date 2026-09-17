"""Proof verifier and validation bundle for mandatory run outputs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .section_lane_tables import *
from .resume_inline import *
from .bcg_forensics import *
from .bcg_inline_output import *

__all__ = ['_validate_row_keys', '_inline_required_output_shape_errors', 'validate_mandatory_output_bundle']

def _validate_row_keys(rows: Any, keys: tuple[str, ...], label: str) -> list[str]:
    if not isinstance(rows, list):
        return [f"{label}.rows_not_list"]
    errors: list[str] = []
    for idx, row in enumerate(rows):
        if not _exact_key_order(row, keys):
            observed = list(row.keys()) if isinstance(row, dict) else type(row).__name__
            errors.append(f"{label}[{idx}].keys={observed}")
    return errors


def _inline_required_output_shape_errors(inline: Any) -> list[str]:
    errors: list[str] = []
    if not _exact_key_order(inline, INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS):
        observed = list(inline.keys()) if isinstance(inline, dict) else type(inline).__name__
        return [f"inline_required_output.keys={observed}"]
    if inline.get("schema_version") != INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION:
        errors.append("schema_version")
    if inline.get("immutable_section_order") != list(INLINE_REQUIRED_OUTPUT_SECTION_ORDER):
        errors.append("immutable_section_order")

    bcg = inline.get("bcg")
    if not _exact_key_order(bcg, BCG_OUTPUT_KEYS):
        observed = list(bcg.keys()) if isinstance(bcg, dict) else type(bcg).__name__
        errors.append(f"bcg.keys={observed}")
    else:
        if bcg.get("title") != "BCG Executive Output - apps_rg Run":
            errors.append("bcg.title")
        if bcg.get("section_order") != list(BCG_LOCKED_SECTION_ORDER):
            errors.append("bcg.section_order")
        recs = bcg.get("p0_p1_px_recommendations")
        if not _exact_key_order(recs, BCG_NESTED_TABLE_KEYS):
            observed = list(recs.keys()) if isinstance(recs, dict) else type(recs).__name__
            errors.append(f"bcg.p0_p1_px_recommendations.keys={observed}")
        else:
            if recs.get("columns") != list(BCG_RECOMMENDATION_COLUMNS):
                errors.append("bcg.p0_p1_px_recommendations.columns")
            errors.extend(
                _validate_row_keys(
                    recs.get("rows"),
                    BCG_RECOMMENDATION_ROW_KEYS,
                    "bcg.p0_p1_px_recommendations.rows",
                )
            )
        board = bcg.get("board_level_readout")
        if not _exact_key_order(board, BCG_NESTED_TABLE_KEYS):
            observed = list(board.keys()) if isinstance(board, dict) else type(board).__name__
            errors.append(f"bcg.board_level_readout.keys={observed}")
        else:
            if board.get("columns") != list(BCG_BOARD_READOUT_COLUMNS):
                errors.append("bcg.board_level_readout.columns")
            errors.extend(
                _validate_row_keys(
                    board.get("rows"),
                    BCG_BOARD_READOUT_ROW_KEYS,
                    "bcg.board_level_readout.rows",
                )
            )
        if not isinstance(bcg.get("executive_answer"), str):
            errors.append("bcg.executive_answer")
        issue_tree = bcg.get("issue_tree")
        if not isinstance(issue_tree, list):
            errors.append("bcg.issue_tree")
        else:
            errors.extend(_validate_row_keys(issue_tree, BCG_ISSUE_TREE_ROW_KEYS, "bcg.issue_tree"))
        next_moves = bcg.get("recommended_next_move")
        if not isinstance(next_moves, list) or not all(isinstance(item, str) for item in next_moves):
            errors.append("bcg.recommended_next_move")
        evidence_map = bcg.get("evidence_map")
        if not isinstance(evidence_map, list):
            errors.append("bcg.evidence_map")
        else:
            errors.extend(_validate_row_keys(evidence_map, BCG_EVIDENCE_MAP_ROW_KEYS, "bcg.evidence_map"))

    lane_table = inline.get("section_lane_summary_table")
    if not _exact_key_order(lane_table, SECTION_LANE_TABLE_KEYS):
        observed = list(lane_table.keys()) if isinstance(lane_table, dict) else type(lane_table).__name__
        errors.append(f"section_lane_summary_table.keys={observed}")
    else:
        if lane_table.get("title") != "Section Lane Summary Table":
            errors.append("section_lane_summary_table.title")
        if lane_table.get("columns") != list(SECTION_LANE_TABLE_COLUMNS):
            errors.append("section_lane_summary_table.columns")
        errors.extend(
            _validate_row_keys(
                lane_table.get("rows"),
                SECTION_LANE_TABLE_COLUMNS,
                "section_lane_summary_table.rows",
            )
        )

    resume = inline.get("resume_docx_full_version_inline")
    if not _exact_key_order(resume, RESUME_DOCX_INLINE_KEYS):
        observed = list(resume.keys()) if isinstance(resume, dict) else type(resume).__name__
        errors.append(f"resume_docx_full_version_inline.keys={observed}")
    else:
        if resume.get("title") != "Resume DOCX Full Version Inline":
            errors.append("resume_docx_full_version_inline.title")
        if not isinstance(resume.get("source"), str) or not resume.get("source"):
            errors.append("resume_docx_full_version_inline.source")
        if not isinstance(resume.get("text"), str) or not resume.get("text").strip():
            errors.append("resume_docx_full_version_inline.text")
    return errors


def validate_mandatory_output_bundle(
    run_root: Path,
    doc: dict[str, Any],
) -> dict[str, Any]:
    """Validate mandatory closeout artifacts and failed-section comparisons."""
    root = Path(run_root).resolve()
    errors: list[str] = []
    # BCG and output_bisect removed from mandatory validation — dead outputs
    # with zero downstream consumers.  Files are still emitted (opt-in removal
    # in a later wave) but their absence no longer blocks the pipeline.
    required_text = {
        MANDATORY_RUN_OUTPUT_MD: ("# apps_rg Mandatory Run Output", "## Section Lane Summary"),
        L7_AUDIT_ABILITY_OUTPUT_MD: ("## 3. L7 Audit Ability Output",),
    }
    for filename, markers in required_text.items():
        path = root / filename
        if not path.is_file() or path.stat().st_size <= 0:
            errors.append(f"missing_or_empty:{filename}")
            continue
        text = _read_text(path)
        for marker in markers:
            if marker not in text:
                errors.append(f"missing_marker:{filename}:{marker}")

    json_path = root / MANDATORY_RUN_OUTPUT_JSON
    if not json_path.is_file() or json_path.stat().st_size <= 0:
        errors.append(f"missing_or_empty:{MANDATORY_RUN_OUTPUT_JSON}")
    elif not _load_json(json_path):
        errors.append(f"malformed_json:{MANDATORY_RUN_OUTPUT_JSON}")

    result_summary = doc.get("result_summary")
    result_summary = result_summary if isinstance(result_summary, dict) else {}
    product_completion_claimed = bool(
        result_summary.get("product_authorized")
        or result_summary.get("outcome_authorized")
    )
    final_output = doc.get("final_resume_output")
    final_output = final_output if isinstance(final_output, dict) else {}
    if final_output.get("required") and product_completion_claimed:
        if final_output.get("status") != "PASS":
            errors.append(
                f"final_resume_output_status:{final_output.get('status') or 'MISSING'}"
            )
        product_contract_paths = {
            "final_resume_json": FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
            "rendered_resume_text": FINAL_RESUME_OUTPUT_TXT,
            "resume_docx": FINAL_RESUME_DOCX_RELPATH,
        }
        for artifact_id, relative in product_contract_paths.items():
            artifact = final_output.get(artifact_id)
            artifact = artifact if isinstance(artifact, dict) else {}
            if (
                artifact.get("exists") is not True
                or not isinstance(artifact.get("bytes"), int)
                or artifact.get("bytes", 0) <= 0
                or not str(artifact.get("sha256") or "").strip()
            ):
                errors.append(f"final_resume_artifact_incomplete:{artifact_id}")
                continue
            if str(artifact.get("relpath") or "") != relative:
                errors.append(f"final_resume_artifact_relpath_mismatch:{artifact_id}")
                continue
            data = (root / relative).read_bytes() if (root / relative).is_file() else b""
            actual_digest = hashlib.sha256(data).hexdigest()
            claimed_digest = str(artifact.get("sha256") or "")
            if claimed_digest not in {actual_digest, f"sha256:{actual_digest}"}:
                errors.append(f"final_resume_artifact_digest_mismatch:{artifact_id}")
            if artifact.get("bytes") != len(data):
                errors.append(f"final_resume_artifact_length_mismatch:{artifact_id}")
        for relative in _PRODUCT_OUTPUT_ARTIFACTS:
            path = root / relative
            if not path.is_file() or path.stat().st_size <= 0:
                errors.append(f"missing_or_empty:{relative}")
        if not _load_json(root / FINAL_RESUME_OUTPUT_JSON):
            errors.append(f"malformed_json:{FINAL_RESUME_OUTPUT_JSON}")
        if not _load_json(root / FINAL_RESUME_ASSEMBLY_JSON_RELPATH):
            errors.append(f"malformed_json:{FINAL_RESUME_ASSEMBLY_JSON_RELPATH}")
        if not _load_json(root / APPS_RG_OUTPUT_MANIFEST):
            errors.append(f"malformed_json:{APPS_RG_OUTPUT_MANIFEST}")

    forensics = doc.get("section_failure_forensics")
    forensics = forensics if isinstance(forensics, dict) else {}
    if forensics.get("required"):
        bisect_text = _read_text(root / OUTPUT_BISECT_MD)
        for marker in (
            "### Layperson RCA",
            "### Underlying Root Cause",
            "### Ingestion-To-Outcome Lineage",
            "### Prior Passing Run",
            "### Current Failing Run",
            "### Full X2 Gate Matrix",
            "### Judge Matrix",
        ):
            if marker not in bisect_text:
                errors.append(f"missing_marker:{OUTPUT_BISECT_MD}:{marker}")
        if forensics.get("pass") is not True:
            errors.append(E2E_SECTION_FORENSICS_GATE_ID)
        artifacts = forensics.get("artifacts")
        artifacts = artifacts if isinstance(artifacts, list) else []
        if not artifacts:
            errors.append("missing:section_failure_forensics_artifacts")
        expected_forensic_files = {
            f"{SECTION_FAILURE_FORENSICS_DIR}/index.json",
            f"{SECTION_FAILURE_FORENSICS_DIR}/index.md",
        }
        for row in artifacts:
            if not isinstance(row, dict):
                errors.append("malformed:section_failure_forensics_row")
                continue
            section_id = str(row.get("section_id") or "unknown")
            safe_id = section_id.replace("/", "_").replace("\\", "_")
            expected_forensic_files.update(
                {
                    f"{SECTION_FAILURE_FORENSICS_DIR}/{safe_id}.json",
                    f"{SECTION_FAILURE_FORENSICS_DIR}/{safe_id}.md",
                }
            )
            json_ref = str(row.get("json_path") or "")
            json_artifact = Path(json_ref)
            if not json_artifact.is_absolute():
                json_artifact = root / SECTION_FAILURE_FORENSICS_DIR / f"{section_id}.json"
            rca = _load_json(json_artifact)
            if not rca:
                errors.append(f"missing_or_malformed:comparison:{section_id}")
                continue
            for error in validate_section_failure_rca(rca):
                errors.append(f"comparison:{section_id}:{error}")
        actual_forensic_files = {
            path.relative_to(root).as_posix()
            for path in (root / SECTION_FAILURE_FORENSICS_DIR).glob("*")
            if path.is_file()
        }
        if actual_forensic_files != expected_forensic_files:
            errors.append(
                "section_failure_forensics_artifact_set_mismatch:"
                f"missing={sorted(expected_forensic_files - actual_forensic_files)},"
                f"extra={sorted(actual_forensic_files - expected_forensic_files)}"
            )

    operational = doc.get("operational_failure_forensics")
    operational = operational if isinstance(operational, dict) else {}
    if operational.get("required"):
        from apps_rg.runtime.e2e_operational_failure import (
            validate_operational_failure_forensics,
        )

        errors.extend(validate_operational_failure_forensics(operational))
        bisect_text = _read_text(root / OUTPUT_BISECT_MD)
        for marker in (
            "### Layperson RCA",
            "### Underlying Root Cause",
            "### Ingestion-To-Outcome Lineage",
            "### Prior Passing Run",
            "### Current Failing Run",
            "### Full X2 Gate Matrix",
            "### Judge Matrix",
        ):
            if marker not in bisect_text:
                errors.append(f"missing_marker:{OUTPUT_BISECT_MD}:{marker}")

    return {
        "gate_id": MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
        "required": True,
        "pass": not errors,
        "errors": errors,
        "required_artifacts": [
            MANDATORY_RUN_OUTPUT_MD,
            L7_AUDIT_ABILITY_OUTPUT_MD,
            MANDATORY_RUN_OUTPUT_JSON,
            *(
                _PRODUCT_OUTPUT_ARTIFACTS
                if final_output.get("required") and product_completion_claimed
                else ()
            ),
        ],
        "product_artifacts_required": bool(
            final_output.get("required") and product_completion_claimed
        ),
        "failed_section_comparison_required": bool(forensics.get("required")),
        "operational_failure_comparison_required": bool(operational.get("required")),
        "failure_reason": "" if not errors else MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
    }

