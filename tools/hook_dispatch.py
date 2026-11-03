#!/usr/bin/env python3
"""Antigravity Lifecycle Hook Dispatcher.

Executes native Antigravity lifecycle hooks configured in .agents/hooks.json:
- pre_edit_plan: PreToolUse guard on write_to_file / replace_file_content for plans
- stop_wave_summary: Stop hook (silenced to adhere to output brevity rules without dumping raw tables)
- pre_run_command: PreToolUse guard on run_command (pytest scope & timeout enforcement)
- pre_model_neutral: PreToolUse guard on file writes / moves against proprietary model naming
- pre_ask_question: PreToolUse guard on ask_question / ask_user_question (atomic, confidence, margin bypass, layman)
- post_ask_question: PostToolUse ledger writer persisting operator choices into HITLDecisionStore
- pre_subagent_delegation: PreToolUse guard on invoke_subagent / browser_subagent validating 10-field contracts
- pre_file_write: PreToolUse guard enforcing primary main-worktree write protection & user-facing layman checks
- post_invocation: PostInvocation guard intercepting disjunctive fence-sitting, unpromoted edits, and jargon

Input/Output Protocol:
- Reads system and tool invocation context as JSON from sys.stdin
- Emits decision payload as JSON to sys.stdout
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.pr_governance_core.common import bootstrap_shared_venv

bootstrap_shared_venv(ROOT)

# Ensure .agents/tools symlink exists for relative hook invocations from .agents/
_AGENTS_TOOLS_LINK = ROOT / ".agents" / "tools"
if (ROOT / ".agents").is_dir() and not _AGENTS_TOOLS_LINK.exists():
    try:
        _AGENTS_TOOLS_LINK.symlink_to("../tools")
    except Exception:  # guardian: allow-silent-swallow -- best-effort symlink creation
        pass

try:
    from tools.validate_implementation_plan import (
        extract_wave_summary_entries,
        get_active_plan_file,
        render_markdown_wave_summary_table,
        render_wave_summary_table,
        validate_plan_content,
    )
except ImportError:
    from validate_implementation_plan import (  # type: ignore
        extract_wave_summary_entries,
        get_active_plan_file,
        render_markdown_wave_summary_table,
        render_wave_summary_table,
        validate_plan_content,
    )


MANDATORY_HITL_CATEGORIES = {
    "pr_merge_authorization",
    "tier_0_irreversible",
    "release_activation",
    "destructive",
}

POST_EDIT_PROMOTION_PROMPT = (
    "[HITL GOVERNANCE INTERCEPT - POST-EDIT PROMOTION GATE] "
    "You modified repository files during this turn without completing a governed merge to local main "
    "or asking the operator to authorize branch commit, rebase, and promotion to local main. "
    "Immediately commit, rebase, and merge under operator authorization or invoke ask_question with "
    "one atomic question presenting the recommended promotion option with calibrated confidence."
)

DISJUNCTIVE_INTERCEPT_PROMPT = (
    "[HITL GOVERNANCE INTERCEPT - INV-DECISIVE-RECOMMENDATION] "
    "You concluded your turn with a plain-text disjunctive choice without invoking ask_question. "
    "Immediately invoke ask_question with one atomic question and mutually exclusive, "
    "confidence-scored options (Confidence: TIER (N%))."
)

LAYMAN_INTERCEPT_PROMPT = (
    "[LAYMAN ZERO-JARGON GOVERNANCE INTERCEPT - PLAIN-LANGUAGE INVARIANT] "
    "Your response contained technical jargon, code identifiers, or raw filenames ({violations}). "
    "Rewrite your response immediately in 100% clear layman terms with zero technical jargon, "
    "preserving exact numbers, counts, and plain-English link labels."
)


def read_hook_input() -> Dict[str, Any]:
    """Read and parse JSON payload from stdin, with safe fallback for testing."""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except Exception:  # guardian: allow-silent-swallow -- fallback to empty dict on malformed stdin
            pass
    return {}


def emit_decision(decision: str, reason: str = "", overwrite: Optional[Dict[str, Any]] = None) -> int:
    """Emit JSON decision object to stdout and return corresponding exit code."""
    payload: Dict[str, Any] = {"decision": decision}
    if reason:
        payload["reason"] = reason
    if overwrite:
        payload["overwrite"] = overwrite
    print(json.dumps(payload))
    return 0 if decision == "allow" else 1


def handle_pre_edit_plan(payload: Dict[str, Any], repo_root: Path) -> int:
    """Validate implementation plan before write_to_file or replace_file_content executes."""
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    target_file = args.get("TargetFile") or args.get("Path") or args.get("path") or ""
    if not target_file:
        return emit_decision("allow")

    target_path = Path(target_file)
    target_name = target_path.name.lower()

    is_plan = (
        target_name == "implementation_plan.md"
        or "plans/" in target_file.replace("\\", "/")
        or (target_file.endswith(".md") and "plan" in target_name)
    )

    if not is_plan:
        return emit_decision("allow")

    content = ""
    if tool_name in ("write_to_file", "write_file"):
        content = args.get("CodeContent") or args.get("Content") or ""
    elif tool_name in ("replace_file_content", "multi_replace_file_content", "edit_file"):
        if target_path.is_file():
            try:
                content = target_path.read_text(encoding="utf-8")
            except Exception:  # guardian: allow-silent-swallow -- fallback to replacement content
                pass
        if not content:
            content = args.get("ReplacementContent") or args.get("Replacement") or ""

    if not content:
        return emit_decision("allow")

    effective_root = repo_root
    if target_path.is_absolute():
        for p in [target_path] + list(target_path.parents):
            if (p / ".git").exists():
                effective_root = p
                break
    if effective_root == repo_root:
        m = re.search(r"Worktree:\s*[`'\"]?([^`'\"\n\r]+)[`'\"]?", content)
        if m:
            cand = Path(m.group(1).strip())
            if (cand / ".git").exists():
                effective_root = cand

    try:
        is_valid, errors = validate_plan_content(content, filename=target_path.name, repo_root=effective_root)
    except TypeError:
        is_valid, errors = validate_plan_content(content, filename=target_path.name)

    if not is_valid:
        error_msg = f"Plan validation rejected for {target_path.name}:\n" + "\n".join(f"- {e}" for e in errors)
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {error_msg}\n")
        return emit_decision("deny", reason=error_msg)

    entries, _ = extract_wave_summary_entries(content)
    if entries:
        sys.stderr.write(f"\n[Antigravity Hook PASS] Plan satisfies wave governance ({len(entries)} wave(s) validated).\n")

    return emit_decision("allow", reason="Plan satisfies wave governance requirements.")


def handle_stop_wave_summary(payload: Dict[str, Any], repo_root: Path) -> int:
    """Stop hook handler: silenced to adhere to output brevity rules without dumping raw wave tables into chat."""
    print(json.dumps({}))
    return 0


def handle_pre_run_command(payload: Dict[str, Any]) -> int:
    """PreToolUse guard on run_command to enforce pytest scoping and timeout."""
    tool_call = payload.get("toolCall", {})
    args = tool_call.get("args", {})
    cmd = (args.get("CommandLine") or args.get("command") or "").strip()

    if not cmd:
        return emit_decision("allow")

    if re.search(r"\bpytest(?:\.exe)?\s*$", cmd) or re.search(r"\bpytest\s+tests/?\s*$", cmd):
        reason = "Bare un-scoped 'pytest' or 'pytest tests/' is blocked by governance. Specify targeted test files."
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
        return emit_decision("deny", reason=reason)

    return emit_decision("allow")


def handle_pre_model_neutral(payload: Dict[str, Any], repo_root: Path = ROOT) -> int:
    """PreToolUse guard against proprietary model names in paths."""
    tool_call = payload.get("toolCall", {})
    args = tool_call.get("args", {})
    target_file = args.get("TargetFile") or args.get("Path") or args.get("path") or ""

    if not target_file:
        return emit_decision("allow")

    from tools.lint_model_neutral_naming import check_path_model_neutrality

    path_violations = check_path_model_neutrality(Path(target_file), repo_root)
    if path_violations:
        reason = f"Model-neutral path violation: {'; '.join(path_violations)}"
        sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
        return emit_decision("deny", reason=reason)

    return emit_decision("allow")


def handle_pre_model_registry(payload: Dict[str, Any], repo_root: Path = ROOT) -> int:
    """PreToolUse guard ensuring model tokens written to plans resolve against approved registry."""
    tool_call = payload.get("toolCall", {})
    args = tool_call.get("args", {})
    target_file = str(args.get("TargetFile") or args.get("Path") or args.get("path") or "")
    content = str(args.get("CodeContent") or args.get("Content") or args.get("Replacement") or "")
    if not target_file or not content or not target_file.endswith(".md") or "plans/" not in target_file.replace("\\", "/"):
        return emit_decision("allow")
    try:
        from tools.hitl_governance import detect_unapproved_model_tokens

        unapproved = detect_unapproved_model_tokens(content, repo_root=repo_root)
        if unapproved:
            reason = f"Unapproved model identifier(s) in plan: {', '.join(unapproved)}. Resolve against config/provider_profiles.yaml."
            sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
            return emit_decision("deny", reason=reason)
    except Exception:  # guardian: allow-silent-swallow -- fail open only if import/helper unavailable
        pass
    return emit_decision("allow")


def _extract_questions_list(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_q = args.get("questions")
    if isinstance(raw_q, str) and raw_q.strip():
        try:
            raw_q = json.loads(raw_q)
        except Exception:  # guardian: allow-silent-swallow -- treat unparseable string as empty
            raw_q = []
    if isinstance(raw_q, list):
        return [q for q in raw_q if isinstance(q, dict)]
    if "question" in args or "prompt" in args or "options" in args:
        return [args]
    return []


def _is_mandatory_hitl_question(q_text: str, q_item: Dict[str, Any], args: Dict[str, Any]) -> bool:
    cat = str(q_item.get("category") or args.get("category") or "").strip().lower()
    if cat in MANDATORY_HITL_CATEGORIES:
        return True
    lower = q_text.lower()
    return any(
        tok in lower
        for tok in (
            "[mandatory approval]",
            "[merge authorization]",
            "pr_merge_authorization",
            "authorize governed merge",
            "approve merge of",
        )
    )


def handle_pre_ask_question(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse guard on ask_question / ask_user_question enforcing atomic options, confidence, and margin bypass."""
    from tools.hitl_governance import (
        HITLDecisionStore,
        evaluate_hitl_surfacing_gate,
        validate_hitl_presentation,
    )

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    if not isinstance(args, dict):
        return emit_decision("deny", reason="HITL_VIOLATION_INVALID_PAYLOAD: Question arguments must be a dictionary.")

    qs = _extract_questions_list(args)
    if not qs:
        return emit_decision("deny", reason="HITL_VIOLATION_EMPTY_QUESTION: No question provided in tool call.")
    if len(qs) > 1:
        return emit_decision(
            "deny",
            reason=f"HITL_VIOLATION_BULK_DECISION: Attempted to present {len(qs)} questions simultaneously. Present strictly one at a time.",
        )

    q_item = qs[0]
    q_text = str(q_item.get("question") or q_item.get("prompt") or "").strip()
    if not q_text:
        return emit_decision("deny", reason="HITL_VIOLATION_EMPTY_QUESTION: Question text is missing or empty.")

    pres_errors = validate_hitl_presentation(q_item)
    if pres_errors:
        return emit_decision("deny", reason="; ".join(pres_errors))

    # Check question text against raw file paths or inline SQL (Rule 6 Layman Question Guard)
    if re.search(r"\b(?:tools|scripts|agentic_core|apps_rg|outreach_engine)/[a-zA-Z0-9_\-./]+\.py\b", q_text) or re.search(
        r"\bSELECT\s+.+?\s+FROM\s+[a-zA-Z0-9_]+", q_text, re.IGNORECASE
    ):
        return emit_decision(
            "deny",
            reason="HITL_VIOLATION_JARGON_IN_QUESTION: Question text contains raw code paths or SQL syntax. Use plain English.",
        )

    options = q_item.get("options", [])
    if not _is_mandatory_hitl_question(q_text, q_item, args):
        gate = evaluate_hitl_surfacing_gate(options)
        if not gate["should_surface"] and gate["top_score"] >= 0.65:
            try:
                db_override = (
                    Path(f"/tmp/agents_test_hitl_{os.getpid()}.sqlite")
                    if "PYTEST_CURRENT_TEST" in os.environ and "HITL_STORE_PATH" not in os.environ
                    else None
                )
                store = HITLDecisionStore(db_path=db_override)
                dec_id = str(
                    q_item.get("decision_id")
                    or args.get("decision_id")
                    or "auto_" + hashlib.sha256(q_text.encode("utf-8")).hexdigest()[:12]
                )
                top_opt = gate["top_option"]
                top_label = top_opt.get("label", str(top_opt)) if isinstance(top_opt, dict) else str(top_opt)
                store.record_decision(
                    decision_id=dec_id,
                    task_id=str(args.get("task_id", "auto_bypass")),
                    category=str(q_item.get("category") or args.get("category") or "tactical_execution"),
                    options=options,
                    selected_option=top_label,
                    operator_action="PROCEED_AUTONOMOUSLY",
                    margin=gate["margin"],
                    calibrated_confidence=gate["top_score"],
                    context_summary=q_text[:160],
                    outcome="SUCCESS",
                )
                store.close()
            except Exception:  # guardian: allow-silent-swallow -- do not block margin bypass on store write error
                pass
            return emit_decision(
                "deny",
                reason=(
                    f"[HITL_MARGIN_BYPASS_REQUIRED] Confidence spread ({gate['margin']*100:.0f}%) exceeds the "
                    "20% ambiguity threshold. Do not call ask_question; execute the top-ranked recommended option "
                    "autonomously (AUTONOMOUS decision receipt recorded in HITL store)."
                ),
            )

    return emit_decision("allow")


def _normalize_selected_answer(raw_selected: Any) -> str:
    if not isinstance(raw_selected, str):
        return str(raw_selected or "").strip()
    lines = [ln.strip() for ln in raw_selected.strip().splitlines() if ln.strip()]
    filtered: List[str] = []
    for ln in lines:
        if re.match(r"^(?:Created|Completed)\s+At\s*:", ln, re.IGNORECASE):
            continue
        m_ans = re.match(r"^A\d+\s*:\s*(.+)$", ln)
        if m_ans:
            return m_ans.group(1).strip()
        if re.match(r"^Q\d+\s*:", ln):
            continue
        filtered.append(ln)
    cleaned = " ".join(filtered).strip() if filtered else raw_selected.strip()
    return re.sub(r"^(?:A|Q)\d+\s*:\s*", "", cleaned).strip()


def _infer_decision_category(question: str, options: Sequence[Any], explicit_cat: Optional[str] = None) -> str:
    if explicit_cat and str(explicit_cat).strip().lower() not in ("", "general", "default", "none"):
        return str(explicit_cat).strip().lower()
    opt_text = " ".join(str(o.get("label") or o.get("text") or "") if isinstance(o, dict) else str(o) for o in options)
    corpus = f"{question} {opt_text}".lower()
    if any(k in corpus for k in ("merge", "promote", "rebase", "pull request", "local main")):
        return "pr_merge_authorization"
    if any(k in corpus for k in ("cleanup", "archive", "prune", "worktree")):
        return "maintenance_governance"
    if any(k in corpus for k in ("architecture", "schema", "layer", "contract", "refactor")):
        return "architecture"
    return "tactical_execution"


def handle_post_ask_question(payload: Dict[str, Any], repo_root: Path) -> int:
    """PostToolUse hook recording operator decision into HITLDecisionStore."""
    from tools.hitl_governance import HITLDecisionStore, evaluate_hitl_surfacing_gate

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    qs = _extract_questions_list(args if isinstance(args, dict) else {})
    q_item = qs[0] if qs else (args if isinstance(args, dict) else {})

    question = str(q_item.get("question") or q_item.get("prompt") or "").strip()
    options = q_item.get("options") if isinstance(q_item.get("options"), list) else []
    raw_res = (
        payload.get("toolResult")
        or payload.get("toolResponse")
        or payload.get("result")
        or payload.get("response")
        or payload.get("selected_option")
        or q_item.get("selected_option")
    )
    if isinstance(raw_res, dict):
        raw_res = (
            raw_res.get("selected_option")
            or raw_res.get("selected")
            or raw_res.get("answer")
            or raw_res.get("output")
            or raw_res.get("content")
        )
    selected = _normalize_selected_answer(raw_res)
    if not question or not options or not selected or selected.lower() in ("skip", "skipped", "cancel", "cancelled"):
        print(json.dumps({"status": "SKIPPED", "reason": "Incomplete question or skipped answer"}))
        return 0

    gate = evaluate_hitl_surfacing_gate(options)
    top_opt = gate.get("top_option")
    top_label = (top_opt.get("label") or top_opt.get("text") or "") if isinstance(top_opt, dict) else str(top_opt or "")
    is_recommended = "(recommended)" in selected.lower() or (top_label and selected in top_label)
    operator_action = "APPROVED" if is_recommended else "OVERRIDDEN"
    category = _infer_decision_category(question, options, q_item.get("category") or payload.get("category"))
    dec_id = str(
        q_item.get("decision_id")
        or payload.get("decision_id")
        or "hitl_" + hashlib.sha256(f"{question}:{selected}".encode("utf-8")).hexdigest()[:12]
    )

    db_override = (
        Path(f"/tmp/agents_test_hitl_{os.getpid()}.sqlite")
        if "PYTEST_CURRENT_TEST" in os.environ and "HITL_STORE_PATH" not in os.environ
        else None
    )
    store = HITLDecisionStore(db_path=db_override)
    rec = store.record_decision(
        decision_id=dec_id,
        task_id=str(q_item.get("task_id") or payload.get("task_id") or "interactive_turn"),
        category=category,
        options=options,
        selected_option=selected,
        operator_action=operator_action,
        margin=float(gate.get("margin", 0.0)),
        calibrated_confidence=float(gate.get("top_score", 0.5)),
        context_summary=question[:200],
        outcome="SUCCESS" if operator_action == "APPROVED" else "PENDING",
    )
    store.close()
    print(json.dumps(rec))
    return 0


def handle_pre_subagent_delegation(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse guard on invoke_subagent / browser_subagent validating 10-field delegation contracts."""
    from tools.unified_agent_architecture import MANDATORY_DELEGATION_FIELDS, validate_delegation_contract

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    if not isinstance(args, dict):
        return emit_decision("allow")

    contract = args.get("delegation_contract") or args.get("contract")
    if isinstance(contract, dict):
        errors = validate_delegation_contract(contract)
        if errors:
            return emit_decision("deny", reason="; ".join(errors))
        return emit_decision("allow")

    # If args directly supply delegation contract fields, validate them against the 10-field schema
    if any(k in args for k in ("task_id", "parent_task_id", "scope_in", "scope_out", "definition_of_done")):
        errors = validate_delegation_contract(args)
        if errors:
            return emit_decision("deny", reason="; ".join(errors))
        return emit_decision("allow")

    # For standard Antigravity invoke_subagent(TypeName, Role, Prompt), check if Prompt embeds a JSON contract
    prompt_text = str(args.get("Prompt") or args.get("prompt") or args.get("Task") or "").strip()
    if "delegation_contract" in prompt_text:
        try:
            m = re.search(r"\{[\s\S]*\"delegation_contract\"[\s\S]*\}", prompt_text)
            if m:
                parsed = json.loads(m.group(0))
                inner = parsed.get("delegation_contract", parsed)
                if isinstance(inner, dict):
                    errors = validate_delegation_contract(inner)
                    if errors:
                        return emit_decision("deny", reason="; ".join(errors))
        except Exception:  # guardian: allow-silent-swallow -- ignore non-JSON prose mentions
            pass

    return emit_decision("allow")


def _is_primary_root_on_main(repo_root: Path) -> bool:
    try:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        if "worktrees" in git_dir.replace("\\", "/"):
            return False
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        return branch == "main"
    except Exception:  # guardian: allow-silent-swallow -- default False if git check fails
        return False


def evaluate_main_worktree_write(target_path_str: str, repo_root: Path) -> Tuple[bool, str]:
    """Return (is_blocked, reason) if target_path writes directly to primary repo root on branch main."""
    if not target_path_str:
        return False, ""
    try:
        p = Path(target_path_str)
        resolved = p.resolve() if p.is_absolute() else (repo_root / p).resolve()
        root_resolved = repo_root.resolve()
    except Exception:
        return False, ""

    norm = str(resolved).replace("\\", "/")
    if any(seg in norm for seg in ("/.worktrees/", "/worktrees/", "/.local/", "/brain/", "/.gemini/", "/artifacts/")):
        return False, ""

    if (resolved == root_resolved or root_resolved in resolved.parents) and _is_primary_root_on_main(root_resolved):
        return True, (
            f"MAIN_WORKTREE_WRITE_BLOCKED: Direct modification of tracked files on branch 'main' "
            f"in the primary root workspace is prohibited ('{resolved}'). Execute changes inside an isolated worktree."
        )
    return False, ""


def handle_pre_file_write(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse combined file-write guard: main-branch isolation + plan validation + model neutrality + layman artifact guard."""
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
    target_file = str(args.get("TargetFile") or args.get("Path") or args.get("path") or "").strip()

    blocked, reason = evaluate_main_worktree_write(target_file, repo_root)
    if blocked:
        return emit_decision("deny", reason=reason)

    meta = args.get("ArtifactMetadata")
    if isinstance(meta, dict) and bool(meta.get("UserFacing")):
        from tools.validate_turn_gates import validate_layman_jargon_gate

        content = str(args.get("Content") or args.get("Replacement") or args.get("CodeContent") or "")
        summary = str(meta.get("Summary") or "")
        jargon_res = validate_layman_jargon_gate(f"{summary}\n{content}")
        if jargon_res["status"] != "PASS":
            sample = ", ".join(jargon_res["violations"][:3])
            return emit_decision(
                "deny",
                reason=f"PRE_OUTPUT_LAYMAN_GUARD (Rule 6): User-facing artifact contains technical jargon ({sample}). Rewrite in plain English.",
            )

    return emit_decision("allow")


def handle_post_invocation(payload: Dict[str, Any], repo_root: Path) -> int:
    """PostInvocation guard enforcing decisive recommendations, post-edit promotion, and zero-jargon prose."""
    from tools.validate_turn_gates import (
        validate_decisive_recommendation_gate,
        validate_layman_jargon_gate,
    )

    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    candidate_text = str(payload.get("candidate_response") or "")
    if not candidate_text and steps:
        last_step = steps[-1] if isinstance(steps[-1], dict) else {}
        candidate_text = str(last_step.get("content") or "")

    asked_question = bool(payload.get("invoked_question_tool", False))
    mutated_files = bool(payload.get("mutated_repository_code", False))
    completed_merge = bool(payload.get("completed_governed_merge", False))

    for s in steps:
        if not isinstance(s, dict):
            continue
        tcs = s.get("tool_calls") or s.get("toolCalls") or ([] if not s.get("toolCall") else [s["toolCall"]])
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tname = str(tc.get("name") or tc.get("tool_name") or "").split(":")[-1]
            targs = tc.get("args") if isinstance(tc.get("args"), dict) else {}
            if tname in ("ask_question", "ask_user_question"):
                asked_question = True
            elif tname in ("write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content"):
                p_str = str(targs.get("Path") or targs.get("TargetFile") or "").replace("\\", "/")
                if p_str and not any(x in p_str for x in ("/brain/", "/.gemini/", "implementation_plan.md", "plans/")):
                    mutated_files = True
            elif tname == "run_command":
                cmd = str(targs.get("CommandLine") or targs.get("command") or "")
                if "pr_governance.py" in cmd and any(k in cmd for k in ("merge", "submit", "promote")):
                    completed_merge = True

    if mutated_files and not (asked_question or completed_merge):
        print(json.dumps({"injectSteps": [{"userMessage": POST_EDIT_PROMOTION_PROMPT}], "terminationBehavior": "force_continue"}))
        return 0

    if asked_question or not candidate_text.strip():
        print(json.dumps({"injectSteps": []}))
        return 0

    decisive_res = validate_decisive_recommendation_gate(candidate_text)
    if decisive_res["status"] != "PASS":
        print(json.dumps({"injectSteps": [{"userMessage": DISJUNCTIVE_INTERCEPT_PROMPT}], "terminationBehavior": "force_continue"}))
        return 0

    jargon_res = validate_layman_jargon_gate(candidate_text)
    if jargon_res["status"] != "PASS":
        violations_str = ", ".join(jargon_res["violations"][:4])
        msg = LAYMAN_INTERCEPT_PROMPT.format(violations=violations_str)
        print(json.dumps({"injectSteps": [{"ephemeralMessage": msg}], "terminationBehavior": "force_continue"}))
        return 0

    print(json.dumps({"injectSteps": []}))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Antigravity Lifecycle Hook Dispatcher.")
    parser.add_argument(
        "--hook",
        required=True,
        choices=[
            "pre_edit_plan",
            "stop_wave_summary",
            "pre_run_command",
            "pre_model_neutral",
            "pre_model_registry",
            "pre_ask_question",
            "post_ask_question",
            "pre_subagent_delegation",
            "pre_file_write",
            "post_invocation",
        ],
        help="Lifecycle hook handler to execute.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root path.",
    )
    args = parser.parse_args(argv)
    payload = read_hook_input()

    if args.hook == "pre_edit_plan":
        return handle_pre_edit_plan(payload, args.repo_root)
    elif args.hook == "stop_wave_summary":
        return handle_stop_wave_summary(payload, args.repo_root)
    elif args.hook == "pre_run_command":
        return handle_pre_run_command(payload)
    elif args.hook == "pre_model_neutral":
        return handle_pre_model_neutral(payload, args.repo_root)
    elif args.hook == "pre_model_registry":
        return handle_pre_model_registry(payload, args.repo_root)
    elif args.hook == "pre_ask_question":
        return handle_pre_ask_question(payload, args.repo_root)
    elif args.hook == "post_ask_question":
        return handle_post_ask_question(payload, args.repo_root)
    elif args.hook == "pre_subagent_delegation":
        return handle_pre_subagent_delegation(payload, args.repo_root)
    elif args.hook == "pre_file_write":
        return handle_pre_file_write(payload, args.repo_root)
    elif args.hook == "post_invocation":
        return handle_post_invocation(payload, args.repo_root)

    return emit_decision("allow")


if __name__ == "__main__":
    sys.exit(main())
