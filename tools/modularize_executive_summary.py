#!/usr/bin/env python3
"""Modularize executive_summary_lane.py into apps_rg.runtime.sections.executive_summary sub-package."""

import ast
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = REPO_ROOT / "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py"
PKG_DIR = REPO_ROOT / "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary"

def main() -> None:
    src_text = subprocess.run(
        ["git", "show", "HEAD:resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_lane.py"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=30
    ).stdout
    tree = ast.parse(src_text)
    lines = src_text.splitlines(keepends=True)

    funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])

    # Clean up obsolete experimental files if present
    for obsolete_file in ["stage_remediation_attempt.py", "stage_remediation_eval.py"]:
        p = PKG_DIR / obsolete_file
        if p.exists():
            p.unlink()

    # 1. lane_constants.py
    constants_content = '''"""Constants and module-level SSOT configuration for executive summary lane."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from apps_rg.repository_layout import repository_root as resolve_repository_root

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # guardian: allow-silent-swallow -- P2 burndown: fail-soft optional boundary
    pass  # dotenv not installed, rely on system env

from apps_rg.runtime.w3_execution_path_labels import (
    BUCKET_DECLARED_TEMPORARY_SLICE,
    PLAN_SLUG,
    validate_bucket,
)

W3_EXECUTION_PATH_BUCKET = BUCKET_DECLARED_TEMPORARY_SLICE
W3_EXECUTION_PATH_PLAN_SLUG = PLAN_SLUG
validate_bucket(W3_EXECUTION_PATH_BUCKET, context=__name__)

from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    classify_ledger_parse_state,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.sections.executive_summary_pa import compile_executive_summary_prompt
from apps_rg.runtime.sections.executive_summary_context_limits import (
    resolve_scratch_max_output_tokens,
)
from apps_rg.runtime.section_proof.mock_runtime_proof_policy import (
    attach_lane_proof_bundle_fields,
    compute_lane_proof_bundle,
)
from apps_rg.runtime.sections.prompt_trace_reasoning import attach_reasoning_to_prompt_trace
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.sections.section_generation import (
    build_section_request,
    generate_section,
    tag_reasoning_lane,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_MAX_WORDS,
    build_sentence_claim_coverage,
    run_x2_gates,
)
from apps_rg.runtime.judges.executive_summary_judge_packet import (
    build_executive_summary_judge_packet,
    write_executive_summary_judge_packet,
)
from apps_rg.runtime.judges.executive_summary_x1d import run_llm_judges
from apps_rg.runtime.exit.executive_summary_x3 import aggregate_x3 as _aggregate_executive_summary_x3
from apps_rg.runtime.offline_contract_status import OFFLINE_CONTRACT_STUB_RUNTIME_STATUS
from apps_rg.runtime.runtime_proof_layout import (
    finalize_runtime_proof_run,
    prepare_runtime_proof_run_dir,
    rel_posix,
)
from apps_rg.runtime.section_cli_defaults import coalesce_lane_provider_resolution_source
from apps_rg.runtime.section_proof.section_input_usage_ledger import build_section_input_usage_ledger_v1
from apps_rg.runtime.shadow.executive_summary_l6 import build_l6_shadow_package
from apps_rg.runtime.shadow.l6_shadow_learning import build_l6_shadow_learning_record
from apps_rg.runtime.sections.executive_summary_proof_bundle import (
    emit_executive_summary_post_x3_proof_artifacts,
    write_executive_summary_artifact_inventory,
)
from apps_rg.runtime.sections.graph_evidence_contract import (
    build_graph_evidence_runtime_payload,
    build_selected_graph_evidence_plan,
    merge_graph_evidence_reporting_into_dict,
)
from apps_rg.runtime.sections.executive_summary_evidence_capsule import _capsule_enabled
from apps_rg.runtime.sections.executive_summary_targeting_context import (
    freeze_executive_summary_targeting_context,
)
from apps_rg.runtime.targeting_context_authority import (
    generation_material_context_from_compiled_prompt,
)
from apps_rg.runtime.sections.executive_summary_targeting_publish import (
    audit_judge_packet_targeting_digests,
    parity_allows_judge_regen,
    publish_targeting_parity_and_usage_ledger,
    resolve_judge_packet_for_parity,
)
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    write_x1d_dimension_matrix_artifact,
)

PROMPT_ID = "executive_summary.generate_scratch_v1"
EXEC_SUMMARY_TEMP_DEFAULT = 0.45
EXEC_SUMMARY_TEMP_RANGE = (0.35, 0.55)
TARGET_TITLE_DEFAULT = "SVP Engineering, Agentic AI Platforms"
TARGET_COMPANY_DEFAULT = "Synthetic Enterprise Corp."
JD_TEXT_DEFAULT = (
    "enterprise AI platform leadership, agentic AI systems, runtime governance, "
    "LLMOps, retrieval, production reliability, engineering leadership"
)
BRIEFING_DEFAULT = "regulated enterprise environment, platform modernization, AI governance, scalable delivery"

def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps_rg" / "resume" / "base").exists():
            return parent
    return Path.cwd()

REPO_ROOT = _find_repo_root()
CHECKOUT_ROOT = resolve_repository_root(Path(__file__))
BASE_POINTER = REPO_ROOT / "apps_rg" / "resume" / "base" / "active_base_resume_pointer.json"
BASE_JSON_DEFAULT = REPO_ROOT / "apps_rg" / "resume" / "base" / "amit_ayer_base_resume_v1.json"
LANE_KEY = "executive_summary"
PROMPT_TEMPLATE = REPO_ROOT / "apps_rg" / "prompt_assembly" / "templates" / "executive_summary.generate_scratch_v1.yaml"

__all__ = [name for name in list(globals().keys()) if not name.startswith("__")] + ["_wg"]
'''
    (PKG_DIR / "lane_constants.py").write_text(constants_content, encoding="utf-8")

    # 2. context_assembler.py
    ctx_funcs = [
        "_reconcile_final_plan_c03_allowlist",
        "_args_target_title",
        "_strip_targeting_cap_notice",
        "_args_jd_text",
        "truncate_briefing_for_exec_summary_external_model",
        "sha16",
        "write_json",
        "load_base_resume",
        "extract_allowed_facts",
        "build_selected_fact_plan",
        "build_runtime_payload",
        "_finalize_executive_summary_l7_binding",
        "_first_sentence_from_prose",
        "_fact_body_for_mock_synthesis",
        "_proof_pool_mode_from_payload",
        "build_mock_output",
        "resolve_provider_model_name",
        "write_x2_gate_outputs",
    ]
    ctx_header = f'''"""Context assembly, targeting, and proof loading helpers for executive summary."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from apps_rg.runtime.core_io import write_gateway as _wg
from .lane_constants import *

__all__ = {ctx_funcs!r}

'''
    ctx_code = ctx_header + "\n\n".join(funcs[name] for name in ctx_funcs) + "\n"
    (PKG_DIR / "context_assembler.py").write_text(ctx_code, encoding="utf-8")

    # 3. prompt_builder.py
    prompt_funcs = [
        "check_l2_resume_voice",
        "check_executive_summary_narrative_shape",
        "build_prompt_messages",
        "salvage_truncated_executive_summary_json",
        "parse_model_json",
        "_split_compound_sentence",
        "coerce_resume_display_sentence_count_band",
        "reconcile_claim_ledger_to_sentence_count",
        "_repair_speculative_exec_summary_capstone",
        "normalize_executive_summary_llm_output",
        "prune_exec_summary_claim_ledger_orphans",
        "infer_product_quality",
        "enrich_parsed_for_x2",
    ]
    prompt_header = f'''"""Prompt generation, json salvage, and LLM output normalization."""
from __future__ import annotations

import json
import re
from typing import Any

from .lane_constants import *
from .context_assembler import *

L2_BRIDGE_PHRASE_PATTERN = re.compile(
    r"\\bthis (?:was|is) achieved (?:while|through|by)\\b",
    re.IGNORECASE,
)
L2_PASSIVE_CYCLE_PATTERN = re.compile(
    r"\\b(?:lab-to-production\\s+)?cycle time was reduced\\b",
    re.IGNORECASE,
)
_EXEC_SUMMARY_TARGET_SENTENCES = 6

_CLAUSE_SPLIT_PATTERNS: tuple[tuple[str, str], ...] = (
    (", informing ", "That foundation informs "),
    (", enabling ", "That capability enables "),
    (", improving ", "That work improves "),
    (", reducing ", "That discipline reduces "),
    (", driving ", "That foundation drives "),
    (", positioning ", "That foundation positions "),
    ("; ", "Building on that, "),
    (", and ", "In parallel, "),
    (", which ", "That work "),
)

__all__ = {prompt_funcs + ["L2_BRIDGE_PHRASE_PATTERN", "L2_PASSIVE_CYCLE_PATTERN", "_EXEC_SUMMARY_TARGET_SENTENCES", "_CLAUSE_SPLIT_PATTERNS"]!r}

'''
    prompt_code = prompt_header + "\n\n".join(funcs[name] for name in prompt_funcs) + "\n"
    (PKG_DIR / "prompt_builder.py").write_text(prompt_code, encoding="utf-8")

    # 4. synthesis_shape_repair.py
    synth_shape_funcs = [
        "_synthesis_shape_reject_reason",
        "_shape_failure_count",
        "_regen_candidate_preferred",
        "_build_synthesis_repair_user",
    ]
    synth_shape_header = f'''"""Synthesis shape rejection and user repair message builder."""
from __future__ import annotations

import json
import re
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

__all__ = {synth_shape_funcs!r}

'''
    synth_shape_code = synth_shape_header + "\n\n".join(funcs[name] for name in synth_shape_funcs) + "\n"
    (PKG_DIR / "synthesis_shape_repair.py").write_text(synth_shape_code, encoding="utf-8")

    # 5. synthesis_retry.py
    synth_retry_funcs = [
        "retry_provider_for_synthesis",
    ]
    synth_retry_header = f'''"""Provider retry loop for executive summary synthesis."""
from __future__ import annotations

import json
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *

__all__ = {synth_retry_funcs!r}

'''
    synth_retry_code = synth_retry_header + "\n\n".join(funcs[name] for name in synth_retry_funcs) + "\n"
    (PKG_DIR / "synthesis_retry.py").write_text(synth_retry_code, encoding="utf-8")

    # 6. synthesis_repair.py facade
    synth_repair_facade = '''"""Backward-compatible synthesis repair facade."""
from __future__ import annotations

from .synthesis_shape_repair import *
from .synthesis_retry import *

__all__ = [
    "_synthesis_shape_reject_reason",
    "_shape_failure_count",
    "_regen_candidate_preferred",
    "_build_synthesis_repair_user",
    "retry_provider_for_synthesis",
]
'''
    (PKG_DIR / "synthesis_repair.py").write_text(synth_repair_facade, encoding="utf-8")

    # 7. word_budget_repair.py
    wb_funcs = [
        "_write_x1d_judge_artifacts",
        "_emit_dimension_upstream_triangulation",
        "_build_word_budget_repair_user",
        "apply_exec_summary_word_budget_repair",
        "set_word_budget_repair_authoritative_after_x2",
    ]
    wb_header = f'''"""Word budget repair and X1D judge artifact emitters."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

WORD_BUDGET_REPAIR_RECEIPT_FILENAME = "exec_summary_word_budget_repair_receipt.json"

__all__ = {wb_funcs + ["WORD_BUDGET_REPAIR_RECEIPT_FILENAME"]!r}

'''
    wb_code = wb_header + "\n\n".join(funcs[name] for name in wb_funcs) + "\n"
    (PKG_DIR / "word_budget_repair.py").write_text(wb_code, encoding="utf-8")

    # 8. Stage partitioning of run_executive_summary_execution
    runner_src = funcs["run_executive_summary_execution"]
    r_lines = runner_src.splitlines(keepends=True)
    r_tree = ast.parse(runner_src)
    r_func = r_tree.body[0]

    # Stage 1: Ingress (Stmt 1 to 90)
    stage1_stmts = r_func.body[1:91]
    stage1_body = "".join(r_lines[stage1_stmts[0].lineno - 1:stage1_stmts[-1].end_lineno])
    stage1_code = f'''"""Stage 1: Ingress, targeting preparation, and initial model generation dispatch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

def run_ingress_stage(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {{"args": args}}
{stage1_body}
    ctx["artifact_dir"] = artifact_dir
    ctx["runtime_payload"] = runtime_payload
    ctx["proof_pool_metadata"] = proof_pool_metadata
    ctx["targeting_ingress"] = targeting_ingress
    ctx["messages"] = messages
    ctx["req"] = req
    ctx["scratch_max_tokens"] = scratch_max_tokens
    ctx["token_budget_receipt"] = token_budget_receipt
    ctx["usage_doc"] = usage_doc
    ctx["briefing_text_bounded"] = targeting_ingress.briefing_text_bounded
    ctx["pool"] = pool
    ctx["base_path"] = base_path
    ctx["base_hash"] = base_hash
    ctx["base"] = base
    ctx["selected_fact_plan"] = selected_fact_plan
    ctx["allowed_fact_ids"] = allowed_fact_ids
    ctx["allowed_fact_ids_ordered"] = allowed_fact_ids_ordered
    ctx["result"] = result
    return ctx
'''
    (PKG_DIR / "stage_ingress.py").write_text(stage1_code, encoding="utf-8")

    # Stage 2: Generation (Stmt 91 to 149)
    stage2_stmts = r_func.body[91:150]
    stage2_body = "".join(r_lines[stage2_stmts[0].lineno - 1:stage2_stmts[-1].end_lineno])
    stage2_code = f'''"""Stage 2: Model output parsing, voice repair, and word budget polish."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *

def run_generation_stage(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    req = ctx["req"]
    scratch_max_tokens = ctx["scratch_max_tokens"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    briefing_text_bounded = ctx["briefing_text_bounded"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    result = ctx["result"]

{stage2_body}

    ctx["provider_result_data"] = provider_result_data
    ctx["raw_output"] = raw_output
    ctx["runtime_generation_status"] = runtime_generation_status
    ctx["parsed"] = parsed
    ctx["parse_error"] = parse_error
    ctx["resume_display_text"] = resume_display_text
    ctx["claim_ledger"] = claim_ledger
    ctx["_word_budget_repair_accepted"] = _word_budget_repair_accepted
    ctx["_word_budget_repair_audit"] = _word_budget_repair_audit
    ctx["_composition_plan_early"] = _composition_plan_early
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["x2"] = x2
    ctx["_generation_material"] = _generation_material
    ctx["_bundle_mat"] = _bundle_mat
    ctx["_targeting_parity"] = _targeting_parity
    ctx["usage_doc"] = usage_doc
'''
    (PKG_DIR / "stage_generation.py").write_text(stage2_code, encoding="utf-8")

    # Stage 3: Initial X2 & Judge loop preparation (Stmt 150 to 157)
    stage3a_stmts = r_func.body[150:158]
    stage3a_body = "".join(r_lines[stage3a_stmts[0].lineno - 1:stage3a_stmts[-1].end_lineno])

    # stmt 158 setup: sub-stmts 0..8
    stmt158 = r_func.body[158]
    stmt158_setup = stmt158.body[0:9]
    stmt158_setup_body = "".join(r_lines[stmt158_setup[0].lineno - 1:stmt158_setup[-1].end_lineno])

    # sub-stmt 9 is if_stmt: if judge_remediation_regen_allowed() and _regen_ok:
    # Setup for remediation cycles: lines 3137 to 3206 (dedent by 8 spaces)
    cycles_setup = lines[3137:3206]
    cycles_setup_dedented = "".join(l[8:] if l.startswith("        ") else (l.lstrip() if l.strip() else "\n") for l in cycles_setup)

    # In cycle loop:
    # lines 3207 to 3321 (dedent by 8 spaces to fit inside 4-space for loop)
    loop_before_s28 = lines[3207:3321]
    loop_before_s28_dedented = "".join(l[8:] if l.startswith("        ") else (l.lstrip() if l.strip() else "\n") for l in loop_before_s28)

    # Draft processing: lines 3322 to 3835 (s28_lines)
    s28_lines = lines[3322:3835]
    draft_transformed = []
    for l in s28_lines:
        indent = l[:len(l) - len(l.lstrip())]
        new_indent = indent[16:] if len(indent) >= 16 else ""
        content = l.strip()
        if content == "break":
            draft_transformed.append(new_indent + 'return "break"\n')
        elif content == "continue":
            draft_transformed.append(new_indent + 'return "continue"\n')
        elif not content:
            draft_transformed.append("\n")
        else:
            draft_transformed.append(new_indent + content + "\n")

    remediation_draft_code = f'''"""Processing of parsed or prefiltered draft candidate during remediation."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *

def process_remediation_draft(ctx: dict[str, Any]) -> str | None:
    args, artifact_dir, runtime_payload, proof_pool_metadata = ctx["args"], ctx["artifact_dir"], ctx["runtime_payload"], ctx["proof_pool_metadata"]
    targeting_ingress, messages, req, scratch_max_tokens = ctx["targeting_ingress"], ctx["messages"], ctx["req"], ctx["scratch_max_tokens"]
    token_budget_receipt, usage_doc, briefing_text_bounded, pool = ctx["token_budget_receipt"], ctx["usage_doc"], ctx["briefing_text_bounded"], ctx["pool"]
    base_path, base_hash, base, selected_fact_plan = ctx["base_path"], ctx["base_hash"], ctx["base"], ctx["selected_fact_plan"]
    allowed_fact_ids, allowed_fact_ids_ordered, result, provider_result_data = ctx["allowed_fact_ids"], ctx["allowed_fact_ids_ordered"], ctx["result"], ctx["provider_result_data"]
    raw_output, runtime_generation_status, parsed, parse_error = ctx["raw_output"], ctx["runtime_generation_status"], ctx["parsed"], ctx["parse_error"]
    resume_display_text, claim_ledger = ctx["resume_display_text"], ctx["claim_ledger"]
    _word_budget_repair_accepted, _word_budget_repair_audit = ctx["_word_budget_repair_accepted"], ctx["_word_budget_repair_audit"]
    _composition_plan_early, parsed_for_x2, x2 = ctx["_composition_plan_early"], ctx["parsed_for_x2"], ctx["x2"]
    _generation_material, _bundle_mat, _targeting_parity = ctx["_generation_material"], ctx["_bundle_mat"], ctx["_targeting_parity"]
    x1d, x2_failed_initial, _judge_prompt_x1d = ctx["x1d"], ctx["x2_failed_initial"], ctx["_judge_prompt_x1d"]
    _gtc_lane_dict, _pool_publish_applied, _max_judge_cycles = ctx["_gtc_lane_dict"], ctx["_pool_publish_applied"], ctx["_max_judge_cycles"]
    _cycle_idx, _prior_regen_output_hash, _cycles_receipt = ctx["_cycle_idx"], ctx["_prior_regen_output_hash"], ctx["_cycles_receipt"]
    _candidate_pool, _wg, _cycle_record, _draft_parse_ok = ctx["_candidate_pool"], ctx["_wg"], ctx["_cycle_record"], ctx["_draft_parse_ok"]
    _j_receipt, _pre_parsed, _pre_raw, _pre_resume = ctx["_j_receipt"], ctx["_pre_parsed"], ctx["_pre_raw"], ctx["_pre_resume"]
    _pre_ledger, _pre_x2, _pre_wc, _pre_ledger_rows = ctx["_pre_ledger"], ctx["_pre_x2"], ctx["_pre_wc"], ctx["_pre_ledger_rows"]
    _x1d_before_regen, _scores_before_regen, _cycle_delta_class = ctx["_x1d_before_regen"], ctx["_scores_before_regen"], ctx["_cycle_delta_class"]
    selected_facts_for_x2, _regen_messages, provider_payload = ctx["selected_facts_for_x2"], ctx["_regen_messages"], ctx["provider_payload"]
    model_name, prompt_hash, compiled_prompt, temperature = ctx["model_name"], ctx["prompt_hash"], ctx["compiled_prompt"], ctx["temperature"]
    pp_x2, proof_pool_x2_active, input_payload_hash = ctx["pp_x2"], ctx["proof_pool_x2_active"], ctx["input_payload_hash"]
    _judge_jd, _reject_gate = ctx["_judge_jd"], ctx["_reject_gate"]

{"".join(draft_transformed)}
    ctx["x1d"] = x1d
    ctx["x2"] = x2
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["parsed"] = parsed
    ctx["claim_ledger"] = claim_ledger
    ctx["resume_display_text"] = resume_display_text
    ctx["raw_output"] = raw_output
    ctx["_prior_regen_output_hash"] = _prior_regen_output_hash
    if "_last_regen_candidate" in locals():
        ctx["_last_regen_candidate"] = _last_regen_candidate
    return None
'''
    (PKG_DIR / "stage_remediation_draft.py").write_text(remediation_draft_code, encoding="utf-8")

    # Candidate pool finalization: lines 3853 to 4009
    p3_lines = lines[3852:4009]
    p3_dedented = "".join(l[8:] if l.startswith("        ") else (l.lstrip() if l.strip() else "\n") for l in p3_lines)

    remediation_pool_code = f'''"""Candidate pool final resolution and judge remediation receipt finalization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *

def finalize_remediation_candidate_pool(ctx: dict[str, Any]) -> None:
    artifact_dir = ctx["artifact_dir"]
    _cycles_receipt = ctx["_cycles_receipt"]
    _candidate_pool = ctx["_candidate_pool"]
    _scratch_digest = ctx["_scratch_digest"]
    _published_digest = ctx["_published_digest"]
    _generation_material = ctx["_generation_material"]
    _targeting_parity = ctx["_targeting_parity"]
    usage_doc = ctx["usage_doc"]
    runtime_payload = ctx["runtime_payload"]
    raw_output = ctx["raw_output"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    parsed = ctx["parsed"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    coverage = ctx.get("coverage", {{}})
    x2 = ctx["x2"]
    x1d = ctx["x1d"]
    args = ctx["args"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    pool = ctx["pool"]
    _gtc_lane_dict = ctx["_gtc_lane_dict"]
    _pool_publish_applied = ctx["_pool_publish_applied"]
    _wg = ctx["_wg"]

{p3_dedented}

    ctx["x1d"] = x1d
    ctx["x2"] = x2
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["parsed"] = parsed
    ctx["claim_ledger"] = claim_ledger
    ctx["resume_display_text"] = resume_display_text
    ctx["raw_output"] = raw_output
    ctx["usage_doc"] = usage_doc
    ctx["_cycles_receipt"] = _cycles_receipt
'''
    (PKG_DIR / "stage_remediation_pool.py").write_text(remediation_pool_code, encoding="utf-8")

    # Else branch of s28: lines 3835 to 3851 (dedent by 8 spaces to fit inside 4-space for loop)
    p1_else = lines[3835:3851]
    p1_else_dedented = "".join(l[8:] if l.startswith("        ") else (l.lstrip() if l.strip() else "\n") for l in p1_else)

    remediation_cycles_coord_code = f'''"""Coordinator for remediation retry cycles across attempt, evaluation, and pool selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .stage_remediation_draft import process_remediation_draft
from .stage_remediation_pool import finalize_remediation_candidate_pool

def run_remediation_cycles(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    messages = ctx["messages"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]
    x1d = ctx["x1d"]
    _judge_prompt_x1d = ctx["_judge_prompt_x1d"]
    _gtc_lane_dict = ctx["_gtc_lane_dict"]
    _pool_publish_applied = ctx["_pool_publish_applied"]
    token_budget_receipt = ctx["token_budget_receipt"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    selected_fact_plan = ctx["selected_fact_plan"]
    pool = ctx["pool"]

{cycles_setup_dedented}

    for _cycle_idx in range(_max_judge_cycles):
{loop_before_s28_dedented}
        if _draft_parse_ok or _j_receipt.get("prefilter_applied"):
            ctx["_cycle_idx"] = _cycle_idx
            ctx["_max_judge_cycles"] = _max_judge_cycles
            ctx["_regen_messages"] = _regen_messages
            ctx["_prior_regen_output_hash"] = _prior_regen_output_hash
            ctx["_cycles_receipt"] = _cycles_receipt
            ctx["_candidate_pool"] = _candidate_pool
            ctx["_scratch_digest"] = _scratch_digest
            ctx["_published_digest"] = _published_digest
            ctx["_wg"] = _wg
            ctx["_cycle_record"] = _cycle_record
            ctx["_draft_parse_ok"] = _draft_parse_ok
            ctx["_j_receipt"] = _j_receipt
            ctx["_pre_parsed"] = _pre_parsed
            ctx["_pre_raw"] = _pre_raw
            ctx["_pre_resume"] = _pre_resume
            ctx["_pre_ledger"] = _pre_ledger
            ctx["_pre_x2"] = _pre_x2
            ctx["_pre_wc"] = _pre_wc
            ctx["_pre_ledger_rows"] = _pre_ledger_rows
            ctx["_x1d_before_regen"] = _x1d_before_regen
            ctx["_scores_before_regen"] = _scores_before_regen
            ctx["_cycle_delta_class"] = _cycle_delta_class
            ctx["selected_facts_for_x2"] = selected_facts_for_x2
            ctx["provider_payload"] = provider_payload
            ctx["model_name"] = model_name
            ctx["prompt_hash"] = prompt_hash
            ctx["compiled_prompt"] = compiled_prompt
            ctx["temperature"] = temperature
            ctx["pp_x2"] = pp_x2
            ctx["proof_pool_x2_active"] = proof_pool_x2_active
            ctx["input_payload_hash"] = input_payload_hash
            ctx["_judge_jd"] = _judge_jd
            ctx["_reject_gate"] = _reject_gate
            ctx["raw_output"] = raw_output
            ctx["parsed"] = parsed
            ctx["parsed_for_x2"] = parsed_for_x2
            ctx["resume_display_text"] = resume_display_text
            ctx["claim_ledger"] = claim_ledger
            ctx["x1d"] = x1d
            ctx["x2"] = x2

            action = process_remediation_draft(ctx)
            x1d = ctx["x1d"]
            x2 = ctx["x2"]
            parsed_for_x2 = ctx["parsed_for_x2"]
            parsed = ctx["parsed"]
            claim_ledger = ctx["claim_ledger"]
            resume_display_text = ctx["resume_display_text"]
            raw_output = ctx["raw_output"]
            _prior_regen_output_hash = ctx["_prior_regen_output_hash"]

            if action == "break":
                break
            elif action == "continue":
                continue
{p1_else_dedented}

    ctx["_cycles_receipt"] = _cycles_receipt
    ctx["_candidate_pool"] = _candidate_pool
    ctx["_scratch_digest"] = _scratch_digest
    ctx["_published_digest"] = _published_digest
    ctx["_generation_material"] = _generation_material
    ctx["_targeting_parity"] = _targeting_parity
    ctx["raw_output"] = raw_output
    ctx["parsed_for_x2"] = parsed_for_x2
    ctx["parsed"] = parsed
    ctx["resume_display_text"] = resume_display_text
    ctx["claim_ledger"] = claim_ledger
    ctx["x2"] = x2
    ctx["x1d"] = x1d
    ctx["_wg"] = _wg

    finalize_remediation_candidate_pool(ctx)
'''
    (PKG_DIR / "stage_remediation_cycles.py").write_text(remediation_cycles_coord_code, encoding="utf-8")

    # Stage 3: Initial X2 & Judge loop preparation
    orelse_code = lines[4009:4027]
    orelse_dedented = "".join(orelse_code)

    stage3_code = f'''"""Stage 3: Initial X2/X1D evaluation and judge remediation coordination."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *
from .stage_remediation_cycles import run_remediation_cycles

def run_remediation_stage(ctx: dict[str, Any]) -> None:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    req = ctx["req"]
    scratch_max_tokens = ctx["scratch_max_tokens"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    briefing_text_bounded = ctx["briefing_text_bounded"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    result = ctx["result"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    _word_budget_repair_accepted = ctx["_word_budget_repair_accepted"]
    _word_budget_repair_audit = ctx["_word_budget_repair_audit"]
    _composition_plan_early = ctx["_composition_plan_early"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]

{stage3a_body}

    ctx["x1d"] = x1d
    ctx["x2"] = x2
    ctx["x2_failed_initial"] = x2_failed_initial
    if "judge_packet" in locals():
        ctx["judge_packet"] = judge_packet
    if "judge_packet_ref" in locals():
        ctx["judge_packet_ref"] = judge_packet_ref

    if runtime_generation_status == "REAL_LLM" and not x2_failed_initial and parsed_for_x2:
{stmt158_setup_body}
        ctx["_judge_prompt_x1d"] = _judge_prompt_x1d
        ctx["_gtc_lane_dict"] = _gtc_lane_dict
        ctx["_pool_publish_applied"] = _pool_publish_applied

        if judge_remediation_regen_allowed() and _regen_ok:
            run_remediation_cycles(ctx)
{orelse_dedented}
'''
    (PKG_DIR / "stage_remediation.py").write_text(stage3_code, encoding="utf-8")

    # Stage 4: Closeout (Stmt 159 to end)
    stage4_stmts = r_func.body[159:]
    stage4_body = "".join(r_lines[stage4_stmts[0].lineno - 1:stage4_stmts[-1].end_lineno])

    stage4_code = f'''"""Stage 4: Post-repair validation, product quality inference, X3 aggregation, and return."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .word_budget_repair import *

def run_closeout_stage(ctx: dict[str, Any]) -> dict[str, Any]:
    args = ctx["args"]
    artifact_dir = ctx["artifact_dir"]
    runtime_payload = ctx["runtime_payload"]
    proof_pool_metadata = ctx["proof_pool_metadata"]
    targeting_ingress = ctx["targeting_ingress"]
    messages = ctx["messages"]
    req = ctx["req"]
    scratch_max_tokens = ctx["scratch_max_tokens"]
    token_budget_receipt = ctx["token_budget_receipt"]
    usage_doc = ctx["usage_doc"]
    briefing_text_bounded = ctx["briefing_text_bounded"]
    pool = ctx["pool"]
    base_path = ctx["base_path"]
    base_hash = ctx["base_hash"]
    base = ctx["base"]
    selected_fact_plan = ctx["selected_fact_plan"]
    allowed_fact_ids = ctx["allowed_fact_ids"]
    allowed_fact_ids_ordered = ctx["allowed_fact_ids_ordered"]
    result = ctx["result"]
    provider_result_data = ctx["provider_result_data"]
    raw_output = ctx["raw_output"]
    runtime_generation_status = ctx["runtime_generation_status"]
    parsed = ctx["parsed"]
    parse_error = ctx["parse_error"]
    resume_display_text = ctx["resume_display_text"]
    claim_ledger = ctx["claim_ledger"]
    _word_budget_repair_accepted = ctx["_word_budget_repair_accepted"]
    _word_budget_repair_audit = ctx["_word_budget_repair_audit"]
    _composition_plan_early = ctx["_composition_plan_early"]
    parsed_for_x2 = ctx["parsed_for_x2"]
    x2 = ctx["x2"]
    _generation_material = ctx["_generation_material"]
    _bundle_mat = ctx["_bundle_mat"]
    _targeting_parity = ctx["_targeting_parity"]
    x1d = ctx["x1d"]
    x2_failed_initial = ctx["x2_failed_initial"]
    judge_packet = ctx.get("judge_packet", {{}})
    judge_packet_ref = ctx.get("judge_packet_ref", "")
    _cycles_receipt = ctx.get("_cycles_receipt", {{}})

{stage4_body}
'''
    (PKG_DIR / "stage_closeout.py").write_text(stage4_code, encoding="utf-8")

    # 9. lane_runner.py
    lane_runner_code = '''"""Executive summary lane runner orchestrating the execution stages."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from apps_rg.runtime.sections.executive_summary_context_limits import (
    resolve_scratch_max_output_tokens,
)
from .stage_ingress import run_ingress_stage
from .stage_generation import run_generation_stage
from .stage_remediation import run_remediation_stage
from .stage_closeout import run_closeout_stage

def run_executive_summary_execution(
    args: argparse.Namespace,
    *,
    artifact_dir_override: Path | None = None,
) -> dict[str, Any]:
    """Single end-to-end executive_summary run: artifacts + X2/X1D/X3."""
    _ = resolve_scratch_max_output_tokens
    ctx = run_ingress_stage(args, artifact_dir_override=artifact_dir_override)
    run_generation_stage(ctx)
    run_remediation_stage(ctx)
    return run_closeout_stage(ctx)

__all__ = ["run_executive_summary_execution", "resolve_scratch_max_output_tokens"]
'''
    (PKG_DIR / "lane_runner.py").write_text(lane_runner_code, encoding="utf-8")

    # 10. Re-export in __init__.py
    init_content = '''"""Executive Summary Modular Sub-Package.

Modularized stage handlers, context assembler, prompt builders, and repair engines.
"""
from __future__ import annotations

from .lane_constants import *
from .context_assembler import *
from .prompt_builder import *
from .synthesis_shape_repair import *
from .synthesis_retry import *
from .synthesis_repair import *
from .word_budget_repair import *
from .lane_runner import run_executive_summary_execution
from .parsing import count_words, extract_bullets, tokenize_sentences
from .policy import VoiceRepairPolicy
from .repair import ExecutiveSummaryRepairEngine, RepairAuditEntry, RepairResult
from .rules import DEFAULT_REPAIR_RULES, RepairRule
from .validation import ExecutiveSummaryValidator, ValidationOutcome

__all__ = [
    "run_executive_summary_execution",
    "VoiceRepairPolicy",
    "RepairRule",
    "DEFAULT_REPAIR_RULES",
    "ExecutiveSummaryRepairEngine",
    "RepairAuditEntry",
    "RepairResult",
    "ExecutiveSummaryValidator",
    "ValidationOutcome",
    "tokenize_sentences",
    "extract_bullets",
    "count_words",
]
'''
    (PKG_DIR / "__init__.py").write_text(init_content, encoding="utf-8")

    # 11. Write executive_summary_lane.py facade
    exported: dict[str, str] = {}
    for p in sorted(PKG_DIR.glob("*.py")):
        if p.name in ("__init__.py", "stage_remediation_attempt.py", "stage_remediation_eval.py"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                exported[node.name] = p.stem
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id != "__all__":
                        exported[target.id] = p.stem

    module_imports: dict[str, list[str]] = {}
    for name, mod in sorted(exported.items()):
        module_imports.setdefault(mod, []).append(name)

    import_blocks = []
    for mod, names in sorted(module_imports.items()):
        joined = ",\n    ".join(names)
        import_blocks.append(f"from apps_rg.runtime.sections.executive_summary.{mod} import (\n    {joined},\n)")
    imports_str = "\n".join(import_blocks)

    facade_content = f'''"""Executive summary section lane — ``python -m apps_rg --section executive_summary``.

Lane-scoped modular runtime (proof pool → section graph binding shim → PA → L2 → section X2/X3/L6).
**Not** the integrated R4 governed spine (U0→L1→L0→C0→PA→L2→Exit). Invoked from
``apps_rg.runtime.orchestration.canonical_dispatch`` section branch only.

This module is a backward-compatible facade re-exporting from
``apps_rg.runtime.sections.executive_summary``.
"""
from __future__ import annotations

if __name__ == "__main__":
    raise ImportError(
        "This module is not an operator CLI entrypoint. "
        "Use the sole canonical public command: python -m apps_rg run"
    )

# Product shape rules, "this individual", and synthesis_regen_receipt.json compatibility
from apps_rg.runtime.sections.executive_summary_context_limits import (
    resolve_scratch_max_output_tokens,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    check_exec_summary_paragraph_max_words,
)

{imports_str}

__all__ = [
    "run_executive_summary_execution",
    "resolve_scratch_max_output_tokens",
    "check_exec_summary_paragraph_max_words",
    "LANE_KEY",
    "REPO_ROOT",
    "CHECKOUT_ROOT",
    "TARGET_TITLE_DEFAULT",
    "TARGET_COMPANY_DEFAULT",
    "JD_TEXT_DEFAULT",
    "BRIEFING_DEFAULT",
    "EXEC_SUMMARY_TEMP_DEFAULT",
    "EXEC_SUMMARY_TEMP_RANGE",
    "BASE_POINTER",
    "BASE_JSON_DEFAULT",
    "PROMPT_TEMPLATE",
    "PROMPT_ID",
]
'''
    SOURCE_FILE.write_text(facade_content, encoding="utf-8")

    print("Executive summary decomposition complete! Inspecting line counts:")
    all_ok = True
    for py_file in sorted(PKG_DIR.glob("*.py")):
        loc = len(py_file.read_text(encoding="utf-8").splitlines())
        status = "OK" if loc <= 600 else "EXCEEDS 600"
        if loc > 600:
            all_ok = False
        print(f"  {py_file.name:30s}: {loc:4d} lines [{status}]")
    facade_loc = len(SOURCE_FILE.read_text(encoding="utf-8").splitlines())
    facade_status = "OK" if facade_loc < 600 else "EXCEEDS 600"
    print(f"  {'executive_summary_lane.py':30s}: {facade_loc:4d} lines [{facade_status}]")
    assert all_ok, "Some executive_summary files exceed 600 LOC!"
    assert facade_loc < 600, "executive_summary_lane.py exceeds 600 LOC!"
    print("All file budget assertions passed!")

if __name__ == "__main__":
    main()
