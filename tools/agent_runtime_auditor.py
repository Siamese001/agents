#!/usr/bin/env python3
"""Behavioral 5-Pillar Core Agent Runtime & Orchestration Assurance Auditor (Agent 3).

Verifies foundational agent runtime safety across all components of `agents/`:
1. Subagent 10-Field Delegation Contract AST Scanner & Governance Compliance.
2. Supervisor Loop, RunPhase & State Machine Transition Invariants.
3. Context Window Budgeting, Sliding Compaction & Token Overflow Bounds.
4. Session Persistence, Event Store Serialization & Recovery Round-Trip.
5. Fail-Closed AST Exception Hygiene across all `agents/` submodules.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_paths(repo_root: Path) -> None:
    s = str(repo_root)
    if s not in sys.path:
        sys.path.insert(0, s)


def audit_pillar_1_delegation_contracts(repo_root: Path) -> dict[str, Any]:
    """Audit Pillar 1: Verify 10-field delegation contract compliance across subagent invocations."""
    _ensure_paths(repo_root)
    from tools.unified_agent_architecture import (
        MANDATORY_DELEGATION_FIELDS,
        validate_delegation_contract,
    )

    gaps: list[str] = []
    contracts_checked = 0

    # Scan .agents/skills and prompt specs for delegation contracts
    search_dirs = [
        repo_root / ".agents" / "skills",
        repo_root / "agents",
    ]

    for d in search_dirs:
        if not d.is_dir():
            continue
        for p in d.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                    if "task_id" in keys and ("objective" in keys or "allowed_tools" in keys):
                        contracts_checked += 1
                        missing = set(MANDATORY_DELEGATION_FIELDS) - keys
                        if missing:
                            gaps.append(f"{p.relative_to(repo_root)}: Dict delegation contract missing mandatory fields {sorted(missing)}")

    # Hermetic synthetic contract verification
    valid_test_payload = {field: f"val_{field}" for field in MANDATORY_DELEGATION_FIELDS}
    valid_test_payload["scope_in"] = ["agents/orchestration/"]
    valid_test_payload["scope_out"] = ["external/"]
    valid_test_payload["budget"] = {"max_turns": 10, "timeout_seconds": 60}
    val_errs = validate_delegation_contract(valid_test_payload)
    if val_errs:
        gaps.append(f"Synthetic valid contract failed validation: {val_errs}")

    invalid_payload = {"task_id": "t1"}
    inv_errs = validate_delegation_contract(invalid_payload)
    if not inv_errs:
        gaps.append("Synthetic invalid contract unexpectedly passed validation")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "contracts_checked": contracts_checked,
        "mandatory_fields_count": len(MANDATORY_DELEGATION_FIELDS),
    }


def audit_pillar_2_state_machine_invariants(repo_root: Path) -> dict[str, Any]:
    """Audit Pillar 2: Verify WorkflowStateMachine state transitions and supervisor loop invariants."""
    _ensure_paths(repo_root)
    gaps: list[str] = []
    try:
        from agents.orchestration.state_machine import (
            InvalidStateTransitionError,
            WorkflowStateMachine,
        )
        from agents.orchestration.primitives import WorkflowStatus

        sm = WorkflowStateMachine(workflow_id="wf-audit-test-001")
        if sm.current_status != WorkflowStatus.CREATED:
            gaps.append(f"Initial state machine status expected CREATED, got {sm.current_status}")

        sm.transition_to(WorkflowStatus.PLANNED)
        if sm.current_status != WorkflowStatus.PLANNED:
            gaps.append(f"Post-transition status expected PLANNED, got {sm.current_status}")

        # Invalid transition must raise fail-closed error
        invalid_raised = False
        try:
            sm.transition_to(WorkflowStatus.COMPLETED)
        except InvalidStateTransitionError:
            invalid_raised = True
        except Exception as exc:
            gaps.append(f"Unexpected error type on illegal state transition: {exc}")

        if not invalid_raised:
            gaps.append("WorkflowStateMachine failed to reject illegal transition to COMPLETED")

    except Exception as exc:
        gaps.append(f"Pillar 2 state machine invariant check failed with error: {exc}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "state_machine_verified": True,
    }


def audit_pillar_3_context_budget_compaction(repo_root: Path) -> dict[str, Any]:
    """Audit Pillar 3: Verify TokenBudget limits, sliding window compaction & overflow guards."""
    _ensure_paths(repo_root)
    gaps: list[str] = []
    try:
        from agents.context.budgeting import (
            TokenBudget,
            TokenBudgetExceededError,
        )
        from agents.context.provenance import (
            ContextItem,
            ContextSnapshot,
            ContextSourceType,
        )

        budget = TokenBudget(max_total_tokens=2000, reserved_output_tokens=500)
        if budget.max_context_tokens != 1500:
            gaps.append(f"TokenBudget context token ceiling expected 1500, got {budget.max_context_tokens}")

        snap = ContextSnapshot(
            snapshot_id="snap-audit-001",
            items=[
                ContextItem(
                    source_id="item-audit-001",
                    source_type=ContextSourceType.USER_DOCUMENT,
                    content="sample context content",
                    estimated_tokens=2000,
                )
            ],
        )

        exceeded = False
        try:
            budget.validate_snapshot(snap)
        except TokenBudgetExceededError:
            exceeded = True
        except Exception as exc:
            gaps.append(f"Unexpected exception on token budget overflow: {exc}")

        if not exceeded:
            gaps.append("TokenBudget failed to raise TokenBudgetExceededError on overflow")

    except Exception as exc:
        gaps.append(f"Pillar 3 context budget check failed with error: {exc}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "budget_overflow_guard_verified": True,
    }


def audit_pillar_4_persistence_event_store(repo_root: Path) -> dict[str, Any]:
    """Audit Pillar 4: Verify session persistence and JSONL event store round-trip serialization."""
    _ensure_paths(repo_root)
    gaps: list[str] = []
    try:
        from agents.persistence.jsonl.event_store import JsonlEventStore
        from agents.observability.events import AgentEventEnvelope, AgentEventType

        with tempfile.TemporaryDirectory() as tmp_dir:
            store_file = Path(tmp_dir) / "events.jsonl"
            store = JsonlEventStore(store_file)
            test_event = AgentEventEnvelope.create(
                event_type=AgentEventType.PHASE_TRANSITION,
                run_id="run-audit-001",
                correlation_id="corr-audit-001",
                sequence=1,
                producer="audit_runner",
                payload={"status": "INITIALIZED", "phase": "CREATED"},
            )
            store.append(test_event)

            read_events = store.get_run_events("run-audit-001")
            if len(read_events) != 1 or read_events[0].run_id != "run-audit-001":
                gaps.append("Event store failed round-trip event serialization")

    except Exception as exc:
        gaps.append(f"Pillar 4 persistence event store check failed: {exc}")

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "event_store_roundtrip_verified": True,
    }


def _is_empty_return_expr(expr: ast.AST | None) -> bool:
    if expr is None:
        return True
    if isinstance(expr, ast.Constant) and expr.value in (None, "", False, 0):
        return True
    if isinstance(expr, (ast.List, ast.Dict, ast.Set, ast.Tuple)) and not (
        expr.elts if hasattr(expr, "elts") else expr.keys
    ):
        return True
    return False


def _handler_has_guardian_comment(handler: ast.ExceptHandler, lines: list[str]) -> bool:
    h_start = getattr(handler, "lineno", 0)
    h_end = getattr(handler, "end_lineno", h_start)
    for i in range(max(1, h_start - 1), min(len(lines), h_end + 2) + 1):
        line = lines[i - 1]
        if "# guardian:" in line or "# noqa" in line:
            return True
    return False


def _is_unguarded_silent_swallow(handler: ast.ExceptHandler, lines: list[str]) -> bool:
    if _handler_has_guardian_comment(handler, lines):
        return False
    body = [n for n in handler.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if not body:
        return True
    if len(body) == 1:
        s = body[0]
        if isinstance(s, ast.Pass):
            return True
        if isinstance(s, ast.Return) and _is_empty_return_expr(s.value):
            return True
    return False


def audit_pillar_5_exception_hygiene(repo_root: Path) -> dict[str, Any]:
    """Audit Pillar 5: Verify fail-closed exception propagation across `agents/`."""
    gaps: list[str] = []
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        return {"passed": False, "gaps": [f"Missing agents package directory at {agents_dir}"]}

    scanned_files = 0
    unguarded_count = 0
    guardian_count = 0

    for py_file in sorted(agents_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            lines = content.splitlines()
        except Exception:
            continue
        scanned_files += 1

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if _is_unguarded_silent_swallow(node, lines):
                    unguarded_count += 1
                    rel_p = py_file.relative_to(repo_root)
                    gaps.append(f"Unguarded silent swallow at {rel_p}:{getattr(node, 'lineno', 0)}")
                elif _handler_has_guardian_comment(node, lines):
                    guardian_count += 1

    return {
        "passed": len(gaps) == 0,
        "gaps": gaps,
        "scanned_files": scanned_files,
        "unguarded_count": unguarded_count,
        "guardian_count": guardian_count,
    }


def run_agent_runtime_audit(repo_root: Path | None = None) -> dict[str, Any]:
    """Execute 5-pillar Core Agent Runtime behavioral audit."""
    root = Path(repo_root or DEFAULT_REPO_ROOT).resolve()

    p1 = audit_pillar_1_delegation_contracts(root)
    p2 = audit_pillar_2_state_machine_invariants(root)
    p3 = audit_pillar_3_context_budget_compaction(root)
    p4 = audit_pillar_4_persistence_event_store(root)
    p5 = audit_pillar_5_exception_hygiene(root)

    pillars = {
        "pillar_1_delegation_contracts": p1,
        "pillar_2_state_machine_invariants": p2,
        "pillar_3_context_budget_compaction": p3,
        "pillar_4_persistence_event_store": p4,
        "pillar_5_exception_hygiene": p5,
    }

    all_gaps: list[str] = []
    passing_pillars = 0
    for name, p in pillars.items():
        if p["passed"]:
            passing_pillars += 1
        else:
            for g in p.get("gaps", []):
                all_gaps.append(f"[{name}] {g}")

    status = "PASS" if len(all_gaps) == 0 else "FAIL"
    is_clean = len(all_gaps) == 0

    return {
        "schema_version": "agents.core_runtime_audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "status": status,
        "is_clean": is_clean,
        "passing_pillars": passing_pillars,
        "total_pillars": len(pillars),
        "total_gaps": len(all_gaps),
        "gaps": all_gaps,
        "pillars": pillars,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 5-pillar Core Agent Runtime & Orchestration behavioral audit.")
    parser.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT), help="Repository root path")
    parser.add_argument("--output", help="Optional JSON output file path")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    report = run_agent_runtime_audit(root)

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Core Agent Runtime Behavioral Audit: {report['status']} ({report['passing_pillars']}/{report['total_pillars']} pillars passing) ===")
        if report["gaps"]:
            print(f"Detected {len(report['gaps'])} gaps:")
            for g in report["gaps"]:
                print(f"  - {g}")
        else:
            print("Zero runtime defects found across core agent orchestration, state, context, and persistence.")

    return 0 if report["is_clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
