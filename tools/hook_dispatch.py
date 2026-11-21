#!/usr/bin/env python3
"""Antigravity Lifecycle Hook Dispatcher for .agents/hooks.json."""
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

from tools.antigravity_sdk_hooks import build_antigravity_sandbox_config, build_antigravity_sdk_hooks
from tools.pr_governance_core.common import bootstrap_shared_venv
from tools.validate_implementation_plan import (
    extract_wave_summary_entries,
    get_active_plan_file,
    render_markdown_wave_summary_table,
    render_wave_summary_table,
    validate_plan_content,
)

bootstrap_shared_venv(ROOT)

_AGENTS_TOOLS_LINK = ROOT / ".agents" / "tools"
if (ROOT / ".agents").is_dir() and not _AGENTS_TOOLS_LINK.exists():
    try:
        _AGENTS_TOOLS_LINK.symlink_to("../tools")
    except OSError:  # guardian: allow-silent-swallow -- best-effort symlink creation
        pass


MANDATORY_HITL_CATEGORIES = {"pr_merge_authorization", "tier_0_irreversible", "release_activation", "destructive"}

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

WORD_BUDGET_INTERCEPT_PROMPT = (
    "[OUTPUT BREVITY GOVERNANCE INTERCEPT - INV-OUTPUT-MAX-WORDS] "
    "Your response exceeded the repository output budget ({issues}). "
    "Cut at least 25% of sentences/bullets and rewrite concisely within {max_words} words and {max_chars} characters "
    "(Evidence & Graph Lineage footer and link URLs are excluded from the count)."
)

ANTI_PLAINTEXT_FALLBACK_DIRECTIVE = (
    "NEVER fall back to printing questions or options as plain text in chat; "
    "immediately invoke ask_question again with ONE atomic plain-English question at a time "
    "(<= 250 chars per option, Confidence: TIER (N%))."
)


def read_hook_input() -> Dict[str, Any]:
    """Read and parse JSON payload from stdin, with safe fallback for testing."""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                return json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):  # guardian: allow-silent-swallow -- fallback to empty dict on malformed stdin
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


def _is_plan_target(target_file: str) -> bool:
    """Return True only for actual implementation plans (never ordinary docs like explanation.md)."""
    if not target_file:
        return False
    norm_target = target_file.replace("\\", "/")
    if "/.agents/rules/" in norm_target or not norm_target.lower().endswith(".md"):
        return False
    target_name = Path(norm_target).name.lower()
    if target_name == "implementation_plan.md":
        return True
    padded = f"/{norm_target.lstrip('./')}"
    return "/plans/" in padded or "/docs/plans/" in padded


def _evaluate_pre_edit_plan(payload: Dict[str, Any], repo_root: Path) -> Tuple[bool, str]:
    """Validate implementation plan content; returns (is_blocked, reason)."""
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    target_file = str(args.get("TargetFile") or args.get("Path") or args.get("path") or "")
    if not _is_plan_target(target_file):
        return False, ""

    target_path = Path(target_file)
    content = ""
    if tool_name in ("write_to_file", "write_file", "create_file"):
        content = str(args.get("CodeContent") or args.get("Content") or args.get("content") or "")
    elif tool_name in ("replace_file_content", "multi_replace_file_content", "edit_file"):
        if target_path.is_file():
            try:
                content = target_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):  # guardian: allow-silent-swallow -- fallback to replacement content
                pass
        if not content:
            content = str(args.get("ReplacementContent") or args.get("Replacement") or "")

    if not content:
        return False, ""

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
        return True, error_msg

    entries, _ = extract_wave_summary_entries(content)
    if entries:
        sys.stderr.write(f"\n[Antigravity Hook PASS] Plan satisfies wave governance ({len(entries)} wave(s) validated).\n")

    return False, "Plan satisfies wave governance requirements."


def handle_pre_edit_plan(payload: Dict[str, Any], repo_root: Path) -> int:
    """Validate implementation plan before write_to_file or replace_file_content executes."""
    blocked, msg = _evaluate_pre_edit_plan(payload, repo_root)
    if blocked:
        return emit_decision("deny", reason=msg)
    return emit_decision("allow", reason=msg)


def _emit_turn_trace_safe(
    payload: Dict[str, Any],
    steps: List[Dict[str, Any]],
    repo_root: Path,
    *,
    hook_name: str,
) -> None:
    """Fail-safe observer emitting redacted Antigravity turn traces to RunTraceCollector."""
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("AGENTS_TRACE_IN_PYTEST") != "1":
        return
    try:
        from agents.observability.trace_collector import emit_post_run_trace_safe

        traj_steps: List[Dict[str, Any]] = []
        error_count = 0
        for idx, s in enumerate(steps):
            if not isinstance(s, dict):
                continue
            tcs = s.get("tool_calls") or s.get("toolCalls") or ([] if not s.get("toolCall") else [s["toolCall"]])
            status_str = str(s.get("status") or "SUCCESS").upper()
            if status_str in {"ERROR", "FAILED", "TIMEOUT"}:
                error_count += 1
            for tc in tcs:
                if not isinstance(tc, dict):
                    continue
                traj_steps.append(
                    {
                        "step_index": len(traj_steps),
                        "action_type": "tool_call",
                        "target": str(tc.get("name") or tc.get("tool_name") or "unknown"),
                        "status": "ERROR" if status_str in {"ERROR", "FAILED"} else "SUCCESS",
                        "latency_ms": 0.0,
                        "error_code": status_str if status_str in {"ERROR", "FAILED"} else None,
                    }
                )
        run_id = str(payload.get("conversation_id") or payload.get("conversationId") or f"{hook_name}-turn")
        emit_post_run_trace_safe(
            app_id="antigravity_turn",
            run_id=run_id,
            session_id=run_id,
            terminal_status="FAIL" if error_count > 0 else "PASS",
            raw_input={"hook": hook_name, "step_count": len(steps)},
            output_summary={"error_count": error_count, "tool_calls_observed": len(traj_steps)},
            trajectory_steps=traj_steps,
            repo_root=repo_root,
        )
    except (ImportError, OSError, ValueError, TypeError, RuntimeError):  # guardian: allow-silent-swallow -- observer-only turn trace must never block hooks
        pass


def handle_stop_wave_summary(payload: Dict[str, Any], repo_root: Path) -> int:
    """Stop hook handler: emits fail-safe turn trace while adhering to output brevity rules."""
    steps = _load_turn_steps_from_payload(payload)
    _emit_turn_trace_safe(payload, steps, repo_root, hook_name="stop")
    print(json.dumps({}))
    return 0


def handle_pre_run_command(payload: Dict[str, Any]) -> int:
    """PreToolUse guard on run_command (suite-wide and targeted pytest sweeps allowed; timeouts enforced via pytest.ini)."""
    _ = payload
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
        from tools.hitl_governance import validate_model_token_registry

        is_valid, unapproved, _ = validate_model_token_registry(content, repo_root=repo_root)
        if not is_valid and unapproved:
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
        except (json.JSONDecodeError, TypeError, ValueError):  # guardian: allow-silent-swallow -- treat unparseable string as empty
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
        for tok in ("[mandatory approval]", "[merge authorization]", "pr_merge_authorization", "authorize governed merge", "approve merge of")
    )


def handle_pre_ask_question(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse guard on ask_question / ask_user_question enforcing atomic options, confidence, and margin bypass."""
    from tools.hitl_governance import HITLDecisionStore, evaluate_hitl_surfacing_gate, validate_hitl_presentation
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    if not isinstance(args, dict):
        return emit_decision("deny", reason="HITL_VIOLATION_INVALID_PAYLOAD: Question arguments must be a dictionary.")
    qs = _extract_questions_list(args)
    if not qs:
        return emit_decision("deny", reason="HITL_VIOLATION_EMPTY_QUESTION: No question provided in tool call.")
    if len(qs) > 1:
        return emit_decision("deny", reason=f"HITL_VIOLATION_BULK_DECISION: Attempted to present {len(qs)} questions simultaneously. Present strictly one at a time. {ANTI_PLAINTEXT_FALLBACK_DIRECTIVE}")
    q_item = qs[0]
    q_text = str(q_item.get("question") or q_item.get("prompt") or "").strip()
    if not q_text:
        return emit_decision("deny", reason="HITL_VIOLATION_EMPTY_QUESTION: Question text is missing or empty.")
    pres_errors = validate_hitl_presentation(q_item, enforce_visibility_and_jargon=True)
    if pres_errors:
        return emit_decision("deny", reason=f"{'; '.join(pres_errors)} {ANTI_PLAINTEXT_FALLBACK_DIRECTIVE}")

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
        payload.get("toolResult") or payload.get("toolResponse") or payload.get("result")
        or payload.get("response") or payload.get("selected_option") or q_item.get("selected_option")
    )
    if isinstance(raw_res, dict):
        raw_res = (
            raw_res.get("selected_option") or raw_res.get("selected") or raw_res.get("answer")
            or raw_res.get("output") or raw_res.get("content")
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


def _extract_delegation_contract(args: Dict[str, Any], prompt_text: str) -> Optional[Dict[str, Any]]:
    contract = args.get("delegation_contract") or args.get("contract")
    if isinstance(contract, dict):
        return contract
    if any(k in args for k in ("task_id", "parent_task_id", "scope_in", "scope_out", "definition_of_done")):
        return args
    if "delegation_contract" in prompt_text:
        try:
            m = re.search(r"\{[\s\S]*\"delegation_contract\"[\s\S]*\}", prompt_text)
            parsed = json.loads(m.group(0)) if m else None
            inner = parsed.get("delegation_contract", parsed) if isinstance(parsed, dict) else None
            if isinstance(inner, dict):
                return inner
        except (json.JSONDecodeError, TypeError, ValueError):  # guardian: allow-silent-swallow -- ignore non-JSON prose mentions
            pass
    return None


def handle_pre_subagent_delegation(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse guard on invoke_subagent / browser_subagent validating 10-field delegation contracts and scope leases."""
    from tools.prompt_scope_isolation import _sync_teamwork_request_atomic, register_and_check_subagent_scope, resolve_persistent_caller_pid
    from tools.unified_agent_architecture import validate_delegation_contract

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    if not isinstance(args, dict):
        return emit_decision("allow")

    prompt_text = str(args.get("Prompt") or args.get("prompt") or args.get("Task") or "").strip()
    type_name = str(args.get("TypeName") or args.get("type_name") or "").strip().lower()
    workspace_mode = str(args.get("Workspace") or args.get("workspace") or "inherit").strip().lower()
    resolved_contract = _extract_delegation_contract(args, prompt_text)

    cli_owner = resolve_persistent_caller_pid() if payload.get("_cli_invocation") else None
    if resolved_contract is not None and bool(
        resolved_contract.get("enforce_strict_contract")
        or resolved_contract.get("exclusive_lock")
        or resolved_contract.get("enforce_strict_scope")
    ):
        errors = validate_delegation_contract(resolved_contract)
        if errors:
            return emit_decision("deny", reason="; ".join(errors))
        ok, reason, _ = register_and_check_subagent_scope(
            repo_root, resolved_contract, workspace_mode=workspace_mode, owner_pid=cli_owner
        )
        if not ok:
            return emit_decision("deny", reason=reason)
    elif isinstance(resolved_contract, dict) and str(resolved_contract.get("task_id", "")).strip():
        register_and_check_subagent_scope(
            repo_root, resolved_contract, workspace_mode=workspace_mode, owner_pid=cli_owner
        )

    if type_name == "teamwork" and prompt_text:
        _sync_teamwork_request_atomic(repo_root, prompt_text)
    return emit_decision("allow")


def handle_post_subagent_delegation(payload: Dict[str, Any], repo_root: Path) -> int:
    """PostToolUse hook automatically releasing completed subagent scope leases to prevent 30-minute lockouts."""
    from tools.prompt_scope_isolation import release_subagent_scope

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else payload
    if isinstance(args, dict):
        prompt_text = str(args.get("Prompt") or args.get("prompt") or args.get("Task") or "").strip()
        resolved = _extract_delegation_contract(args, prompt_text)
        task_id = str(resolved.get("task_id", "")).strip() if isinstance(resolved, dict) else ""
        if task_id:
            release_subagent_scope(repo_root, task_id)
    print(json.dumps({}))
    return 0


def _is_primary_root_on_main(repo_root: Path) -> bool:
    try:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=repo_root, capture_output=True, text=True, timeout=5, check=False
        ).stdout.strip()
        if "worktrees" in git_dir.replace("\\", "/"):
            return False
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=5, check=False
        ).stdout.strip()
        return branch == "main"
    except (OSError, subprocess.SubprocessError, ValueError):  # guardian: allow-silent-swallow -- default False if git check fails
        return False


def evaluate_main_worktree_write(target_path_str: str, repo_root: Path) -> Tuple[bool, str]:
    """Return (is_blocked, reason) if target_path writes directly to primary repo root on branch main."""
    if not target_path_str:
        return False, ""
    if any(os.environ.get(k) for k in ("AGY_SWARM_WORKER", "ANTIGRAVITY_SWARM_ROLE", "AGY_SUBAGENT_TASK_ID")):
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


def _is_technical_engineering_artifact(target_file: str) -> bool:
    """Return True for Rule 6 engineering deliverables where full technical precision is permitted."""
    norm = str(target_file or "").replace("\\", "/").lower()
    basename = Path(norm).name if norm else ""
    if basename in {"implementation_plan.md", "learning_proposal.md", "walkthrough.md", "task.md"}:
        return True
    if any(basename.endswith(s) for s in ("_plan.md", "_assessment.md", "_rca.md", "_audit.md", "_walkthrough.md")):
        return True
    return "/plans/" in f"/{norm}" or "/docs/plans/" in f"/{norm}"


def handle_pre_file_write(payload: Dict[str, Any], repo_root: Path) -> int:
    """PreToolUse combined file-write guard: main-branch isolation + stage/subagent telemetry."""
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else payload
    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else (tool_call if isinstance(tool_call, dict) else {})
    target_file = str(args.get("TargetFile") or args.get("Path") or args.get("path") or "").strip()

    blocked, reason = evaluate_main_worktree_write(target_file, repo_root)
    if blocked:
        return emit_decision("deny", reason=reason)

    if target_file:
        from tools.prompt_scope_isolation import (
            evaluate_active_subagent_write_scope,
            evaluate_prompt_stage_write_scope,
            is_subagent_turn,
        )

        scope_blocked, scope_reason = evaluate_prompt_stage_write_scope(target_file, repo_root)
        if scope_blocked:
            return emit_decision("deny", reason=scope_reason)
        sub_caller = is_subagent_turn(_load_raw_steps_from_payload(payload), payload)
        sub_blocked, sub_reason = evaluate_active_subagent_write_scope(
            target_file, repo_root, is_subagent_caller=sub_caller
        )
        if sub_blocked:
            return emit_decision("deny", reason=sub_reason)

        # AI-SDLC self-referential fail-closed guard on risk_lanes_policy.json
        norm_target = target_file.replace("\\", "/")
        if norm_target.endswith("config/governance/risk_lanes_policy.json"):
            content_blob = str(args.get("Content") or args.get("CodeContent") or args.get("Replacement") or "")
            if '"default_unrecognized_lane"' in content_blob and '"default_unrecognized_lane": 2' not in content_blob:
                return emit_decision(
                    "deny",
                    reason=(
                        "[Antigravity Hook BLOCK] config/governance/risk_lanes_policy.json "
                        "must preserve fail-closed 'default_unrecognized_lane: 2' (INV-RISK-TIERED-CHANGE-LANES)."
                    ),
                )

        # Consolidated single-process checks (formerly 3 separate PreToolUse subprocesses):
        # 1. Model-neutral artifact path guard
        from tools.lint_model_neutral_naming import check_path_model_neutrality

        path_violations = check_path_model_neutrality(Path(target_file), repo_root)
        if path_violations:
            reason = f"Model-neutral path violation: {'; '.join(path_violations)}"
            sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
            return emit_decision("deny", reason=reason)

        # 2. Implementation plan wave validation guard
        plan_blocked, plan_reason = _evaluate_pre_edit_plan(payload, repo_root)
        if plan_blocked:
            return emit_decision("deny", reason=plan_reason)

        # 3. Plan model-registry conformance guard
        content_blob = str(args.get("CodeContent") or args.get("Content") or args.get("Replacement") or "")
        if content_blob and norm_target.endswith(".md") and "plans/" in norm_target:
            try:
                from tools.hitl_governance import validate_model_token_registry

                is_valid, unapproved, _ = validate_model_token_registry(content_blob, repo_root=repo_root)
                if not is_valid and unapproved:
                    reason = f"Unapproved model identifier(s) in plan: {', '.join(unapproved)}. Resolve against config/provider_profiles.yaml."
                    sys.stderr.write(f"\n[Antigravity Hook BLOCK] {reason}\n")
                    return emit_decision("deny", reason=reason)
            except Exception:  # guardian: allow-silent-swallow -- fail open only if import/helper unavailable
                pass

    return emit_decision("allow")


_POST_INVOCATION_INTERCEPT_MARKERS = (
    "[HITL GOVERNANCE INTERCEPT", "[LAYMAN ZERO-JARGON GOVERNANCE INTERCEPT",
    "[OUTPUT BREVITY GOVERNANCE INTERCEPT", "[AUTONOMOUS LEARN INTERCEPT",
)


def _load_raw_steps_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load all transcript steps from inline 'steps' or 'transcriptPath' JSONL file."""
    inline_steps = payload.get("steps")
    if isinstance(inline_steps, list):
        return [s for s in inline_steps if isinstance(s, dict)]
    raw_steps: List[Dict[str, Any]] = []
    transcript_path = payload.get("transcriptPath")
    if isinstance(transcript_path, str) and transcript_path.strip() and os.path.exists(transcript_path):
        try:
            with open(transcript_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    if raw_line.strip():
                        try:
                            parsed = json.loads(raw_line.strip())
                            if isinstance(parsed, dict):
                                raw_steps.append(parsed)
                        except (json.JSONDecodeError, TypeError, ValueError):  # guardian: allow-silent-swallow -- skip malformed transcript lines
                            continue
        except OSError:  # guardian: allow-silent-swallow -- fallback to empty steps if transcript unreadable
            return []
    return raw_steps


def _load_turn_steps_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load current turn steps from inline 'steps' or 'transcriptPath' JSONL file."""
    raw_steps = _load_raw_steps_from_payload(payload)
    last_user_idx = -1
    for idx, step in enumerate(raw_steps):
        step_type, source = str(step.get("type") or "").upper(), str(step.get("source") or "").upper()
        content = str(step.get("content") or "")
        if (step_type == "USER_INPUT" or source == "USER_EXPLICIT") and not any(m in content for m in _POST_INVOCATION_INTERCEPT_MARKERS):
            last_user_idx = idx
    return raw_steps[last_user_idx + 1 :] if last_user_idx >= 0 else raw_steps


def handle_post_invocation(payload: Dict[str, Any], repo_root: Path) -> int:
    """PostInvocation guard enforcing decisive recommendations while never forcing swarm/prose/promotion rewrites."""
    from tools.prompt_scope_isolation import is_subagent_turn
    from tools.validate_turn_gates import (
        load_policy_registry,
        validate_decisive_recommendation_gate,
        validate_word_budget_gate,
    )

    raw_steps = _load_raw_steps_from_payload(payload)
    if is_subagent_turn(raw_steps, payload):
        print(json.dumps({"injectSteps": []}))
        return 0
    steps = _load_turn_steps_from_payload(payload)
    candidate_text = str(payload.get("candidate_response") or "")
    if not candidate_text and steps:
        last_step = steps[-1] if isinstance(steps[-1], dict) else {}
        s_type, s_src = str(last_step.get("type") or "").upper(), str(last_step.get("source") or "").upper()
        tcs = last_step.get("tool_calls") or last_step.get("toolCalls") or ([] if not last_step.get("toolCall") else [last_step["toolCall"]])
        is_final_reply = s_type in ("PLANNER_RESPONSE", "ASSISTANT", "MODEL_RESPONSE", "") and s_src in ("MODEL", "") and not tcs
        if not is_final_reply:
            print(json.dumps({"injectSteps": []}))
            return 0
        candidate_text = str(last_step.get("content") or "").strip()

    asked_question = bool(payload.get("invoked_question_tool", False))
    is_swarm_or_subagent = any(
        os.environ.get(k) for k in ("AGY_SWARM_WORKER", "AGY_WORKFLOW_RUN", "ANTIGRAVITY_SWARM_ROLE", "AGY_SUBAGENT_TASK_ID")
    )
    disjunctive_retries = 0
    model_replies: List[str] = []

    for s in steps:
        if not isinstance(s, dict):
            continue
        s_content = str(s.get("content") or "")
        if "[HITL GOVERNANCE INTERCEPT - INV-DECISIVE-RECOMMENDATION]" in s_content:
            disjunctive_retries += 1
        if "tool call denied by pre-tool hook" in s_content or "HITL_VIOLATION_" in s_content or "PRE_OUTPUT_LAYMAN_GUARD" in s_content:
            asked_question = False
        tcs = s.get("tool_calls") or s.get("toolCalls") or ([] if not s.get("toolCall") else [s["toolCall"]])
        if not tcs and str(s.get("type") or "").upper() in ("PLANNER_RESPONSE", "ASSISTANT", "MODEL_RESPONSE") and s_content.strip():
            model_replies.append(s_content.strip())
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tname = str(tc.get("name") or tc.get("tool_name") or "").split(":")[-1]
            if tname in ("ask_question", "ask_user_question"):
                asked_question = True
            elif tname == "send_message":
                is_swarm_or_subagent = True

    if (
        is_swarm_or_subagent
        or "@coordinator" in candidate_text.lower()
        or re.search(r"^\s*\[(?:done|blocked|status)\]", candidate_text, re.IGNORECASE | re.MULTILINE)
        or disjunctive_retries >= 1
        or (len(model_replies) >= 2 and model_replies[-1] == model_replies[-2])
    ):
        print(json.dumps({"injectSteps": []}))
        return 0

    if asked_question or not candidate_text.strip():
        print(json.dumps({"injectSteps": []}))
        return 0

    try:
        policies = load_policy_registry(repo_root)
        max_words = int(policies.get("INV-OUTPUT-MAX-WORDS", {}).get("threshold", 450) or 450)
        max_chars = int(policies.get("INV-OUTPUT-MAX-CHARS", {}).get("threshold", 5000) or 5000)
        _ = validate_word_budget_gate(candidate_text, max_words=max_words, max_chars=max_chars)
    except Exception:  # guardian: allow-silent-swallow -- non-blocking telemetry evaluation
        pass

    decisive_res = validate_decisive_recommendation_gate(candidate_text)
    if decisive_res["status"] != "PASS" and disjunctive_retries < 1:
        print(json.dumps({"injectSteps": [{"userMessage": DISJUNCTIVE_INTERCEPT_PROMPT}], "terminationBehavior": "force_continue"}))
        return 0

    print(json.dumps({"injectSteps": []}))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Antigravity Lifecycle Hook Dispatcher.")
    choices = [
        "pre_edit_plan", "stop_wave_summary", "pre_run_command", "pre_model_neutral", "pre_model_registry",
        "pre_ask_question", "post_ask_question", "pre_subagent_delegation", "post_subagent_delegation",
        "pre_file_write", "post_invocation",
    ]
    parser.add_argument("--hook", required=True, choices=choices, help="Lifecycle hook handler to execute.")
    parser.add_argument("--repo-root", type=Path, default=ROOT, help="Repository root path.")
    args = parser.parse_args(argv)
    payload = read_hook_input()
    if isinstance(payload, dict):
        payload["_cli_invocation"] = True
    handlers = {
        "pre_edit_plan": handle_pre_edit_plan, "stop_wave_summary": handle_stop_wave_summary,
        "pre_run_command": lambda p, _r: handle_pre_run_command(p),
        "pre_model_neutral": handle_pre_model_neutral, "pre_model_registry": handle_pre_model_registry,
        "pre_ask_question": handle_pre_ask_question, "post_ask_question": handle_post_ask_question,
        "pre_subagent_delegation": handle_pre_subagent_delegation,
        "post_subagent_delegation": handle_post_subagent_delegation,
        "pre_file_write": handle_pre_file_write, "post_invocation": handle_post_invocation,
    }
    handler = handlers.get(args.hook)
    return handler(payload, args.repo_root) if handler else emit_decision("allow")


if __name__ == "__main__":
    sys.exit(main())
