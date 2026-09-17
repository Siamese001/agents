"""Evidence exporter and output emitter for mandatory apps_rg artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *
from .resume_inline import *
from .causal_plan import *
from .causal_allocation import *
from .bcg_forensics import *
from .bcg_inline_output import *
from .markdown_renderer import *
from .proof_verifier import *
from .manifest_builder import *

__all__ = ['_sealed_additional_artifacts', 'emit_mandatory_run_outputs', 'main']

def _sealed_additional_artifacts(
    root: Path,
    doc: dict[str, Any],
    *,
    l7_path: Path,
) -> dict[str, Path]:
    """Return every existing artifact consumed by mandatory closeout authority."""

    additional: dict[str, Path] = {L7_AUDIT_ABILITY_OUTPUT_MD: l7_path}
    for relative in _PRODUCT_OUTPUT_ARTIFACTS:
        path = root / relative
        if path.is_file():
            additional[relative] = path

    forensics = doc.get("section_failure_forensics")
    forensics = forensics if isinstance(forensics, dict) else {}
    if forensics.get("required"):
        relatives = {
            f"{SECTION_FAILURE_FORENSICS_DIR}/index.json",
            f"{SECTION_FAILURE_FORENSICS_DIR}/index.md",
        }
        for row in forensics.get("artifacts") or []:
            if not isinstance(row, dict):
                continue
            section_id = str(row.get("section_id") or "unknown")
            safe_id = section_id.replace("/", "_").replace("\\", "_")
            relatives.update(
                {
                    f"{SECTION_FAILURE_FORENSICS_DIR}/{safe_id}.json",
                    f"{SECTION_FAILURE_FORENSICS_DIR}/{safe_id}.md",
                }
            )
        for relative in sorted(relatives):
            path = root / relative
            if path.is_file():
                additional[relative] = path
    return additional


def emit_mandatory_run_outputs(
    run_root: Path,
    *,
    repo_root: Path | None = None,
    result: dict[str, Any] | None = None,
    section_id: str | None = None,
    print_stdout: bool = False,
    emit_final_outputs: bool = True,
) -> dict[str, Any]:
    """Write mandatory apps_rg run output artifacts."""
    root = Path(run_root).resolve()
    repo = (repo_root or find_repo_root(root)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    begin_mandatory_output_transaction(root)
    pre_summary = _result_summary(result, root)
    final_required = _final_resume_output_required(root, pre_summary)
    if emit_final_outputs:
        emit_final_resume_product_outputs(
            root,
            repo_root=repo,
            required=final_required,
        )
    doc = build_mandatory_run_output(
        root,
        repo_root=repo,
        result=result,
        section_id=section_id,
    )
    json_path = root / MANDATORY_RUN_OUTPUT_JSON
    md_path = root / MANDATORY_RUN_OUTPUT_MD
    bcg_path = root / BCG_EXECUTIVE_OUTPUT_MD
    bisect_path = root / OUTPUT_BISECT_MD
    _write_text(md_path, _render_mandatory_markdown(doc))
    _write_text(bcg_path, _render_bcg_markdown_locked(doc))
    output_bisect = doc.get("output_bisect")
    output_bisect = output_bisect if isinstance(output_bisect, dict) else {}
    bisect_sections = output_bisect.get("sections")
    bisect_sections = bisect_sections if isinstance(bisect_sections, list) else []
    _write_text(bisect_path, render_output_bisect(bisect_sections))
    l7_path = emit_l7_audit_ability_output(root)
    json_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    hard_stop_gate = validate_mandatory_output_bundle(root, doc)
    doc = apply_mandatory_closeout_state(
        doc,
        hard_stop_gate,
        failure_code=MANDATORY_OUTPUT_HARD_STOP_GATE_ID,
    )
    doc["inline_required_output"] = _build_inline_required_output(doc)
    doc["mandatory_inline_output_gates"] = _inline_output_gates(doc)
    doc["mandatory_inline_output_gates"].append(hard_stop_gate)
    final_text = {
        MANDATORY_RUN_OUTPUT_MD: (_render_mandatory_markdown(doc).rstrip() + "\n").encode(
            "utf-8"
        ),
        BCG_EXECUTIVE_OUTPUT_MD: (_render_bcg_markdown_locked(doc).rstrip() + "\n").encode(
            "utf-8"
        ),
        OUTPUT_BISECT_MD: (render_output_bisect(bisect_sections).rstrip() + "\n").encode(
            "utf-8"
        ),
        MANDATORY_RUN_OUTPUT_JSON: (json.dumps(doc, indent=2) + "\n").encode("utf-8"),
    }
    additional_files = _sealed_additional_artifacts(root, doc, l7_path=l7_path)
    required_artifacts = tuple(
        sorted(
            {
                *final_text,
                *(path.resolve().relative_to(root).as_posix() for path in additional_files.values()),
            }
        )
    )
    result_summary = doc.get("result_summary")
    result_summary = result_summary if isinstance(result_summary, dict) else {}
    product_completion_claimed = bool(
        result_summary.get("product_authorized")
        or result_summary.get("outcome_authorized")
    )
    profile_id = (
        PRODUCT_MANDATORY_OUTPUT_PROFILE
        if hard_stop_gate.get("pass") is True and product_completion_claimed
        else CLOSEOUT_MANDATORY_OUTPUT_PROFILE
    )
    seal = seal_mandatory_output_bundle(
        root,
        final_text,
        additional_files=additional_files,
        profile_id=profile_id,
        required_artifacts=required_artifacts,
    )
    seal_valid, seal_errors = validate_mandatory_output_seal(
        root,
        expected_profile_id=profile_id,
        expected_artifacts=required_artifacts,
    )
    if not seal_valid:
        raise RuntimeError(f"mandatory output seal validation failed: {seal_errors}")
    if print_stdout:
        print((bcg_path).read_text(encoding="utf-8"), flush=True)
        print((md_path).read_text(encoding="utf-8"), flush=True)
        sys.stdout.flush()
    return {
        "json_path": json_path,
        "markdown_path": md_path,
        "bcg_markdown_path": bcg_path,
        "output_bisect_path": bisect_path,
        "l7_audit_ability_path": l7_path,
        "mandatory_output_gate": hard_stop_gate,
        "mandatory_output_commit_manifest_path": root / MANDATORY_OUTPUT_COMMIT_MANIFEST,
        "mandatory_output_bundle_digest": str(seal.get("bundle_digest") or ""),
        "payload": doc,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Emit mandatory apps_rg BCG and run-ledger outputs.")
    parser.add_argument("run_dir", help="apps_rg run directory")
    parser.add_argument("--section", default="", help="Section id for a section-only run")
    parser.add_argument("--no-print", action="store_true", help="Do not print generated markdown")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2
    emit_mandatory_run_outputs(
        run_dir,
        section_id=str(args.section or "") or None,
        print_stdout=not bool(args.no_print),
    )
    return 0

