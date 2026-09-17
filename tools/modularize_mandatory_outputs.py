#!/usr/bin/env python3
"""Modularize mandatory_run_outputs.py into apps_rg.runtime.outputs sub-package."""

import ast
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = REPO_ROOT / "resume_graph_engine/src/apps_rg/runtime/mandatory_run_outputs.py"
OUTPUTS_DIR = REPO_ROOT / "resume_graph_engine/src/apps_rg/runtime/outputs"

def main() -> None:
    src_text = subprocess.run(
        ["git", "show", "HEAD:resume_graph_engine/src/apps_rg/runtime/mandatory_run_outputs.py"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=30
    ).stdout
    tree = ast.parse(src_text)
    lines = src_text.splitlines(keepends=True)

    funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])

    if OUTPUTS_DIR.exists():
        shutil.rmtree(OUTPUTS_DIR)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. constants.py
    constants_content = '''"""Constants and schema definitions for mandatory run outputs."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from apps_rg.runtime.final_resume_outputs import (
    build_final_resume_output_contract,
    emit_final_resume_product_outputs,
)
from apps_rg.runtime.full_run_section_status import (
    FINAL_AGGREGATION_LANE,
    LANE_DISPLAY_TXT_CANDIDATES,
    LaneSectionStatusRow,
    collect_full_run_section_status,
)
from apps_rg.runtime.l7_audit_output import emit_l7_audit_ability_output
from apps_rg.runtime.mandatory_outputs import (
    CLOSEOUT_MANDATORY_OUTPUT_PROFILE,
    MANDATORY_OUTPUT_COMMIT_MANIFEST,
    PRODUCT_MANDATORY_OUTPUT_PROFILE,
    apply_mandatory_closeout_state,
    begin_mandatory_output_transaction,
    seal_mandatory_output_bundle,
    validate_mandatory_output_seal,
)
from apps_rg.runtime.output_bisect import render_output_bisect
from apps_rg.runtime.run_output_contract import (
    APPS_RG_MANDATORY_RUN_OUTPUT_JSON,
    APPS_RG_MANDATORY_RUN_OUTPUT_MD,
    BCG_EXECUTIVE_OUTPUT_MD,
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_OUTPUT_JSON,
    FINAL_RESUME_OUTPUT_TXT,
    FULL_RUN_SECTION_STATUS_JSON,
    L7_AUDIT_ABILITY_OUTPUT_MD,
    OUTPUT_BISECT_MD,
    REVIEW_BUNDLE_FILENAME,
)
from apps_rg.runtime.runtime_proof_layout import find_repo_root
from apps_rg.runtime.section_failure_forensics import (
    E2E_SECTION_FORENSICS_GATE_ID,
    SECTION_FAILURE_FORENSICS_DIR,
    emit_section_failure_forensics,
    validate_section_failure_rca,
)
from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff

MANDATORY_RUN_OUTPUT_JSON = APPS_RG_MANDATORY_RUN_OUTPUT_JSON
MANDATORY_RUN_OUTPUT_MD = APPS_RG_MANDATORY_RUN_OUTPUT_MD
MANDATORY_OUTPUT_HARD_STOP_GATE_ID = "APPS_RG_MANDATORY_OUTPUTS_INCOMPLETE"

INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION = "apps_rg.inline_required_output.v1"
INLINE_REQUIRED_OUTPUT_SECTION_ORDER = (
    "bcg",
    "section_lane_summary_table",
    "resume_docx_full_version_inline",
)
BCG_LOCKED_SECTION_ORDER = (
    "executive_answer",
    "p0_p1_px_recommendations",
    "board_level_readout",
    "issue_tree",
    "recommended_next_move",
    "evidence_map",
)
BCG_OUTPUT_KEYS = ("title", "section_order", *BCG_LOCKED_SECTION_ORDER)
SECTION_LANE_TABLE_COLUMNS = (
    "order",
    "section",
    "research_source_class",
    "r1a",
    "r1b",
    "lane_record",
    "provider_call_attempted",
    "primary_provider",
    "primary_model_observed",
    "pooling_selector_llm",
    "secondary_provider",
    "secondary_model_observed",
    "generation_status",
    "judges_run",
    "judge_models_scores",
    "judge_retry_fallback",
    "x2",
    "x3",
    "past_fail_blocker",
    "display_output",
    "l6_evidence",
)
INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS = (
    "schema_version",
    "immutable_section_order",
    "bcg",
    "section_lane_summary_table",
    "resume_docx_full_version_inline",
)
BCG_RECOMMENDATION_COLUMNS = ("priority", "recommendation", "evidence", "gate_outcome")
BCG_BOARD_READOUT_COLUMNS = ("question", "answer")
BCG_RECOMMENDATION_ROW_KEYS = BCG_RECOMMENDATION_COLUMNS
BCG_BOARD_READOUT_ROW_KEYS = BCG_BOARD_READOUT_COLUMNS
BCG_ISSUE_TREE_ROW_KEYS = (
    "section",
    "classification",
    "root_cause",
    "evidence",
    "causal_allocation",
    "required_implementation_plan",
)
BCG_EVIDENCE_MAP_ROW_KEYS = ("label", "path")
BCG_NESTED_TABLE_KEYS = ("columns", "rows")
SECTION_LANE_TABLE_KEYS = ("title", "columns", "rows")
RESUME_DOCX_INLINE_KEYS = ("title", "source", "text")
APPS_RG_OUTPUT_MANIFEST = "apps_rg_output_manifest.json"

_PRODUCT_OUTPUT_ARTIFACTS = (
    FINAL_RESUME_OUTPUT_TXT,
    FINAL_RESUME_OUTPUT_JSON,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    APPS_RG_OUTPUT_MANIFEST,
)

__all__ = [
    "BCG_EXECUTIVE_OUTPUT_MD",
    "APPS_RG_MANDATORY_RUN_OUTPUT_JSON",
    "APPS_RG_MANDATORY_RUN_OUTPUT_MD",
    "FINAL_RESUME_ASSEMBLY_JSON_RELPATH",
    "FINAL_RESUME_DOCX_RELPATH",
    "FINAL_RESUME_OUTPUT_JSON",
    "FINAL_RESUME_OUTPUT_TXT",
    "FULL_RUN_SECTION_STATUS_JSON",
    "L7_AUDIT_ABILITY_OUTPUT_MD",
    "OUTPUT_BISECT_MD",
    "REVIEW_BUNDLE_FILENAME",
    "MANDATORY_RUN_OUTPUT_JSON",
    "MANDATORY_RUN_OUTPUT_MD",
    "MANDATORY_OUTPUT_HARD_STOP_GATE_ID",
    "INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION",
    "INLINE_REQUIRED_OUTPUT_SECTION_ORDER",
    "BCG_LOCKED_SECTION_ORDER",
    "BCG_OUTPUT_KEYS",
    "SECTION_LANE_TABLE_COLUMNS",
    "INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS",
    "BCG_RECOMMENDATION_COLUMNS",
    "BCG_BOARD_READOUT_COLUMNS",
    "BCG_RECOMMENDATION_ROW_KEYS",
    "BCG_BOARD_READOUT_ROW_KEYS",
    "BCG_ISSUE_TREE_ROW_KEYS",
    "BCG_EVIDENCE_MAP_ROW_KEYS",
    "BCG_NESTED_TABLE_KEYS",
    "SECTION_LANE_TABLE_KEYS",
    "RESUME_DOCX_INLINE_KEYS",
    "APPS_RG_OUTPUT_MANIFEST",
    "_PRODUCT_OUTPUT_ARTIFACTS",
    "FINAL_AGGREGATION_LANE",
    "LANE_DISPLAY_TXT_CANDIDATES",
    "LaneSectionStatusRow",
    "collect_full_run_section_status",
    "emit_l7_audit_ability_output",
    "CLOSEOUT_MANDATORY_OUTPUT_PROFILE",
    "MANDATORY_OUTPUT_COMMIT_MANIFEST",
    "PRODUCT_MANDATORY_OUTPUT_PROFILE",
    "apply_mandatory_closeout_state",
    "begin_mandatory_output_transaction",
    "seal_mandatory_output_bundle",
    "validate_mandatory_output_seal",
    "render_output_bisect",
    "find_repo_root",
    "E2E_SECTION_FORENSICS_GATE_ID",
    "SECTION_FAILURE_FORENSICS_DIR",
    "emit_section_failure_forensics",
    "validate_section_failure_rca",
    "build_final_resume_output_contract",
    "emit_final_resume_product_outputs",
    "validate_apps_research_handoff",
]
'''
    (OUTPUTS_DIR / "constants.py").write_text(constants_content, encoding="utf-8")

    # 2. helpers.py
    helper_funcs = [
        "_utc_now", "_load_json", "_repo_rel", "_write_text", "_read_text",
        "_as_list", "_x2_summary_doc", "_score_text", "_first_nonempty",
        "_briefing_blob", "_short_digest", "_payload_dict", "_artifact_input_value",
        "_resolve_input_ref", "_first_existing_json", "_research_handoff_receipt",
        "_research_artifact_dirs", "_research_handoff_v2", "_exact_key_order",
        "_markdown_table_escape",
    ]
    helpers_header = f'''"""Utility and helper functions for mandatory outputs."""
from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import *

__all__ = {helper_funcs!r}

'''
    helpers_code = helpers_header + "\n\n".join(funcs[name] for name in helper_funcs) + "\n"
    (OUTPUTS_DIR / "helpers.py").write_text(helpers_code, encoding="utf-8")

    # 3. judge_parsers.py
    judge_funcs = [
        "_judge_rows_from_blob", "_normalize_judge_record", "_judge_failure_records",
        "_failed_dimension_codes", "_judge_failure_text_from_judges", "_judge_failure_evidence",
        "_resolve_display", "_load_provider_call_records", "_cache_preflight",
        "_judge_model_score_cell", "_judge_retry_fallback_cell", "_provider_cell",
        "_pooling_selector_cell", "_secondary_provider_cell", "_section_lane_abs_dir",
        "_lane_provider_proof", "_lane_provider_attempted", "_lane_primary_provider",
        "_lane_primary_model", "_lane_generation_status", "_generation_ordered_section_ids",
    ]
    judge_header = f'''"""Judge output parsers and normalization for mandatory run outputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *

__all__ = {judge_funcs!r}

'''
    judge_code = judge_header + "\n\n".join(funcs[name] for name in judge_funcs) + "\n"
    (OUTPUTS_DIR / "judge_parsers.py").write_text(judge_code, encoding="utf-8")

    # 4. research_context.py
    research_funcs = [
        "_apps_research_gate_context", "_research_source_class", "_research_x2_cell",
        "_research_x3_cell", "_research_briefing_context", "_research_briefing_row",
        "_research_row",
    ]
    research_header = f'''"""Apps research gate context and briefing parsers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *

__all__ = {research_funcs!r}

'''
    research_code = research_header + "\n\n".join(funcs[name] for name in research_funcs) + "\n"
    (OUTPUTS_DIR / "research_context.py").write_text(research_code, encoding="utf-8")

    # 5. section_lane_tables.py
    section_funcs = [
        "_row_from_single_section", "_status_bucket", "_classify_failure",
        "_section_record_from_row", "_collect_section_records", "_count_sections",
        "_section_by_id", "_build_section_lane_table", "_non_authorized_section_ids",
    ]
    section_header = f'''"""Section lane tables and section records collection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *

__all__ = {section_funcs!r}

'''
    section_code = section_header + "\n\n".join(funcs[name] for name in section_funcs) + "\n"
    (OUTPUTS_DIR / "section_lane_tables.py").write_text(section_code, encoding="utf-8")

    # 6. resume_inline.py
    # Inline gate references _bcg_truth_errors and _inline_required_output_shape_errors
    resume_inline_funcs = [
        "_resume_inline_authorization", "_blocked_resume_inline_text", "_resume_inline_source",
        "_authorized_resume_inline_text", "_resume_inline_text",
    ]
    # We will place _inline_output_gates with lazy import of bcg_truth_errors and shape errors
    inline_gates_func = funcs["_inline_output_gates"]
    inline_gates_patched = inline_gates_func.replace(
        "def _inline_output_gates(doc: dict[str, Any]) -> list[dict[str, Any]]:\n",
        "def _inline_output_gates(doc: dict[str, Any]) -> list[dict[str, Any]]:\n"
        "    from .bcg_forensics import _bcg_truth_errors\n"
        "    from .proof_verifier import _inline_required_output_shape_errors\n",
    )

    resume_inline_header = f'''"""Resume inline authorization and output gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .section_lane_tables import *

__all__ = {resume_inline_funcs + ['_inline_output_gates']!r}

'''
    resume_inline_code = resume_inline_header + "\n\n".join(funcs[name] for name in resume_inline_funcs) + "\n\n" + inline_gates_patched + "\n"
    (OUTPUTS_DIR / "resume_inline.py").write_text(resume_inline_code, encoding="utf-8")

    # 7. causal_plan.py
    causal_plan_funcs = [
        "_root_cause", "_implementation_plan", "_failed_gate_ids",
        "_gate_reason", "_pre_run_reason", "_allocation_row",
        "_validated_plan_items", "_validated_causal_allocation", "_recommended_action",
    ]
    # Patch _top_rca_sections to lazy import _causal_allocation
    top_rca_func = funcs["_top_rca_sections"]
    top_rca_patched = top_rca_func.replace(
        "def _top_rca_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:\n",
        "def _top_rca_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:\n"
        "    from .causal_allocation import _causal_allocation\n",
    )

    causal_plan_header = f'''"""Causal allocation planning and root cause analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *

__all__ = {['_top_rca_sections'] + causal_plan_funcs!r}

'''
    causal_plan_code = causal_plan_header + top_rca_patched + "\n\n" + "\n\n".join(funcs[name] for name in causal_plan_funcs) + "\n"
    (OUTPUTS_DIR / "causal_plan.py").write_text(causal_plan_code, encoding="utf-8")

    # 8. causal_allocation.py
    causal_alloc_funcs = ["_causal_allocation"]
    causal_alloc_header = f'''"""Causal allocation engine for mandatory run outputs."""
from __future__ import annotations

from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *
from .causal_plan import *

__all__ = {causal_alloc_funcs!r}

'''
    causal_alloc_code = causal_alloc_header + "\n\n".join(funcs[name] for name in causal_alloc_funcs) + "\n"
    (OUTPUTS_DIR / "causal_allocation.py").write_text(causal_alloc_code, encoding="utf-8")

    # 9. bcg_forensics.py
    bcg_forensics_funcs = [
        "_bcg_row", "_active_bcg_evidence", "_forensic_gate", "_forensic_artifacts",
        "_output_bisect_sections", "_forensic_artifact_by_section", "_forensic_evidence_map_rows",
        "_truthy_signal", "_clean_pass_hardening_rows", "_build_bcg_recommendations",
        "_build_bcg_recommended_next_moves", "_bcg_truth_errors", "_bcg_forensics_truth_errors",
    ]
    bcg_forensics_header = f'''"""BCG forensics, evidence mapping, and truth validators."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *
from .section_lane_tables import *
from .causal_plan import *
from .causal_allocation import *

__all__ = {bcg_forensics_funcs!r}

'''
    bcg_forensics_code = bcg_forensics_header + "\n\n".join(funcs[name] for name in bcg_forensics_funcs) + "\n"
    (OUTPUTS_DIR / "bcg_forensics.py").write_text(bcg_forensics_code, encoding="utf-8")

    # 10. bcg_inline_output.py
    bcg_inline_funcs = [
        "_build_bcg_issue_tree", "_build_inline_required_output", "_render_locked_bcg_from_inline",
    ]
    bcg_inline_header = f'''"""BCG inline output builder and locked section formatter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *
from .section_lane_tables import *
from .resume_inline import *
from .causal_plan import *
from .causal_allocation import *
from .bcg_forensics import *

__all__ = {bcg_inline_funcs!r}

'''
    bcg_inline_code = bcg_inline_header + "\n\n".join(funcs[name] for name in bcg_inline_funcs) + "\n"
    (OUTPUTS_DIR / "bcg_inline_output.py").write_text(bcg_inline_code, encoding="utf-8")

    # 11. markdown_renderer.py
    md_funcs = [
        "_render_causal_allocation_lines", "_wide_markdown_code_cell",
        "_render_section_lane_table_lines", "_render_resume_inline_lines",
        "_render_mandatory_markdown", "_render_bcg_markdown", "_render_bcg_markdown_locked",
    ]
    md_header = f'''"""Markdown rendering for mandatory outputs and BCG executive readouts."""
from __future__ import annotations

import html
import json
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

__all__ = {md_funcs!r}

'''
    md_code = md_header + "\n\n".join(funcs[name] for name in md_funcs) + "\n"
    (OUTPUTS_DIR / "markdown_renderer.py").write_text(md_code, encoding="utf-8")

    # 12. proof_verifier.py
    proof_funcs = [
        "_validate_row_keys", "_inline_required_output_shape_errors",
        "validate_mandatory_output_bundle",
    ]
    proof_header = f'''"""Proof verifier and validation bundle for mandatory run outputs."""
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

__all__ = {proof_funcs!r}

'''
    proof_code = proof_header + "\n\n".join(funcs[name] for name in proof_funcs) + "\n"
    (OUTPUTS_DIR / "proof_verifier.py").write_text(proof_code, encoding="utf-8")

    # 13. manifest_builder.py
    manifest_funcs = [
        "_result_summary", "_final_resume_output_required", "build_mandatory_run_output",
    ]
    manifest_header = f'''"""Manifest builder for mandatory run output payloads."""
from __future__ import annotations

import json
import os
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

__all__ = {manifest_funcs!r}

'''
    manifest_code = manifest_header + "\n\n".join(funcs[name] for name in manifest_funcs) + "\n"
    (OUTPUTS_DIR / "manifest_builder.py").write_text(manifest_code, encoding="utf-8")

    # 14. evidence_exporter.py
    export_funcs = [
        "_sealed_additional_artifacts", "emit_mandatory_run_outputs", "main",
    ]
    export_header = f'''"""Evidence exporter and output emitter for mandatory apps_rg artifacts."""
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

__all__ = {export_funcs!r}

'''
    export_code = export_header + "\n\n".join(funcs[name] for name in export_funcs) + "\n"
    (OUTPUTS_DIR / "evidence_exporter.py").write_text(export_code, encoding="utf-8")

    # 15. __init__.py
    init_content = '''"""Mandatory run outputs package."""
from __future__ import annotations

from .constants import *
from .helpers import *
from .judge_parsers import *
from .research_context import *
from .section_lane_tables import *
from .resume_inline import *
from .causal_plan import *
from .causal_allocation import *
from .bcg_forensics import *
from .bcg_inline_output import *
from .markdown_renderer import *
from .proof_verifier import *
from .manifest_builder import *
from .evidence_exporter import *

__all__ = [
    "BCG_EXECUTIVE_OUTPUT_MD",
    "MANDATORY_RUN_OUTPUT_JSON",
    "MANDATORY_RUN_OUTPUT_MD",
    "MANDATORY_OUTPUT_HARD_STOP_GATE_ID",
    "build_mandatory_run_output",
    "emit_mandatory_run_outputs",
    "validate_mandatory_output_bundle",
]
'''
    (OUTPUTS_DIR / "__init__.py").write_text(init_content, encoding="utf-8")

    # 16. Re-write mandatory_run_outputs.py as facade
    all_names = list(funcs.keys())
    facade_content = f'''"""Mandatory apps_rg run outputs.

Every apps_rg run must leave numbered human-facing artifacts:

* ``01_BCG_executive_output.md`` - decision-oriented RCA and implementation plan.
* ``02_output_bisect.md`` - prior-pass/current-failure attempt, gate, judge, and causal bisect.
* ``02_section_lane_summary_table.md`` - operational ledger of what ran.

This module is a backward-compatible facade re-exporting from
``apps_rg.runtime.outputs``.
"""
from __future__ import annotations

from apps_rg.runtime.outputs.constants import *
from apps_rg.runtime.outputs.helpers import *
from apps_rg.runtime.outputs.judge_parsers import *
from apps_rg.runtime.outputs.research_context import *
from apps_rg.runtime.outputs.section_lane_tables import *
from apps_rg.runtime.outputs.resume_inline import *
from apps_rg.runtime.outputs.causal_plan import *
from apps_rg.runtime.outputs.causal_allocation import *
from apps_rg.runtime.outputs.bcg_forensics import *
from apps_rg.runtime.outputs.bcg_inline_output import *
from apps_rg.runtime.outputs.markdown_renderer import *
from apps_rg.runtime.outputs.proof_verifier import *
from apps_rg.runtime.outputs.manifest_builder import *
from apps_rg.runtime.outputs.evidence_exporter import *

# Re-export all functions explicitly for backward compatibility
{chr(10).join(f"{name} = {name}" for name in all_names)}

__all__ = [
    "BCG_EXECUTIVE_OUTPUT_MD",
    "MANDATORY_RUN_OUTPUT_JSON",
    "MANDATORY_RUN_OUTPUT_MD",
    "MANDATORY_OUTPUT_HARD_STOP_GATE_ID",
    "build_mandatory_run_output",
    "emit_mandatory_run_outputs",
    "validate_mandatory_output_bundle",
]
'''
    SOURCE_FILE.write_text(facade_content, encoding="utf-8")

    print(f"Decomposition complete! Inspecting line counts:")
    all_ok = True
    for py_file in sorted(OUTPUTS_DIR.glob("*.py")):
        loc = len(py_file.read_text(encoding="utf-8").splitlines())
        status = "OK" if loc <= 600 else "EXCEEDS 600"
        if loc > 600:
            all_ok = False
        print(f"  {py_file.name:25s}: {loc:4d} lines [{status}]")
    facade_loc = len(SOURCE_FILE.read_text(encoding="utf-8").splitlines())
    facade_status = "OK" if facade_loc < 800 else "EXCEEDS 800"
    print(f"  {'mandatory_run_outputs.py':25s}: {facade_loc:4d} lines [{facade_status}]")
    assert all_ok, "Some outputs files exceed 600 LOC!"
    assert facade_loc < 800, "mandatory_run_outputs.py exceeds 800 LOC!"
    print("All file budget assertions passed!")

if __name__ == "__main__":
    main()
