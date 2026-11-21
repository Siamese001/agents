---
trigger: always_on
---

> See `AGENTS.md` for shared retrieval / enforcement guidance.

# Constitutional Floor

> ⛔ Applies every task, every tier, every session. No exceptions.

## Hard Constraints

0. **Subprocess timeout required.** `subprocess.run(argv, shell=False, timeout=30)`. (§14 alias retained for numbering.)
1. **No test skipping.** No `pytest.mark.skip`, no `xfail` without `strict=True`.
2. **Root-cause bug resolution without artificial barriers.** Trace and fix discovered bugs across all impacted files, contracts, and tests immediately without file-count or blast-radius caps (keeping directional inter-subsystem and storage import boundaries intact).
3. **Clean dead-code retirement.** Dead or superseded modules/agents with zero live callers may be retired cleanly once reference checks pass.
4. **Tier 1 & Tier 2 verification.** `python tools/verify_commit.py` and `python tools/verify_main_readiness.py`.
5. **Structural dependency tracing.** Use ADG (`adg_sqlite`), AST analysis, and unconstrained file/text search to inspect full upstream/downstream ripple impact across the repository.
6. **Ambiguity-gated HITL (`ask_question`).** Surface one atomic plain-English question via `ask_question` only when genuine ambiguity exists ($\Delta \le 20\%$ or top confidence $< 65\%$); multi-layer blast radius incurs zero confidence penalty.
7. **RCA auto-closure.** Execute corrective actions immediately across all root-cause layers; never defer multi-file bugs.
8. **Guardian exemptions require rationale.** `# guardian: allow-<type> -- <specific justification>`.
9. **SVP Engineering rigor for architecture.** Operational simplicity, cohesive modular boundaries, clean inter-subsystem separation, zero-regression.
10. **External-contract refactor discipline.** After refactoring or deleting bloated modules, verify external caller contracts and unmocked regression coverage (`tools/testing_gaps_auditor.py`). Never preserve dead internal helpers or fighting post-LLM regex mutators (`INV-DELETE-BEFORE-DECOMPOSE`).
11. **Terminal process lifecycle.** All `run_command`/subprocess invocations must terminate cleanly and reap background tasks.
12. **No imports from `archives/` in production.**
13. **Non-blocking structural inspection fallback.** Prefer `adg_sqlite` MCP or `artifacts/adg/*.sqlite` when available; otherwise proceed immediately using direct AST/code search.
14. **Subprocess timeout required** (alias of §0).
15. **Precise exception handling.** Catch specific types; bare `except:` and `except Exception` without guardian comment forbidden.
16. **Progress reporting on long-running loops.** Emit progress indicators on heavy batch operations (>5s).
17. **Memory & session state.** Use live repo code, git state, and optional healthy graph queries; no deprecated session-start rituals.

### Process Discipline (§18–§37)

18. **Cohesive root-cause scope (zero blast-radius cap).** Expand freely across all connected producers, contracts, consumers, validators, and tests; avoid unrelated cosmetic churn only.
19. **Plan-only firewall respected.** Honor explicit `PLAN ONLY` / `NO IMPLEMENT` prompts; otherwise execute root-cause fixes, `/boost`, and `/swarm` end-to-end.
20. **Fact grading mandatory.** Classify claims as **DIRECTLY OBSERVED** / **DERIVED** / **UNRESOLVED**.
21. **Zero-loss overwrite discipline.** Preserve active constraints and script-relied references when editing governance files.
22. **ADG & AST structural analysis.** Use ADG views (`mv_*`, `v_p0_*`..`v_p3_*`) and AST/search inspection freely; missing ADG artifacts never block wave plans.
23. **ADG canonical invariants.** SQLite=truth, Redis=hot projection, MCP=read-only gateway (`adg-canonical-invariants.md`).
24. **Zero bug-deferral rule.** Fix discovered bugs immediately at their root cause regardless of file count or layer span.
25. *(Reserved slot.)*
26. **No interactive pagers in `run_command`.** `more`/`less`/`most` forbidden; redirect output or bound reads.
27. **Config schema purity.** `.agents/hooks.json` and `.mcp.json` must contain only supported schema fields (`tools/ssot_boundary_auditor.py`).
28. **Combined ADG, AST, and grep dependency analysis.** Combine `adg_sqlite`, AST analysis, and `grep_search` freely without degraded-fallback blocks.
29. **Closed-loop router evidence mandatory.** Routers emit `ROUTER_DECISION:` + `emit_ledger_event` on the same code path.
30. *(Retired slot — `ask_question` supersedes Author-Gate.)*
31. **SSOT folder routing for new files.** Governance/gate/hook scripts under `tools/`, smoke runners under `ops_scripts/`, serving scripts under `scripts/`, domain code inside its owning package root (`ssot-folder-enforcement.md`).
32. *(Retired slot — see §37.)*
33. **Concise governance context budget.** Root `AGENTS.md <= 200` lines, always-on rules `<= 36,000` bytes, and `.agents/skills/*/SKILL.md` descriptions `<= 4,000` tokens (`tools/validate_turn_gates.py`, `tools/audit_governance_harmonization.py`).
34. **Full-ripple inspection & telemetry.** No per-turn read/grep caps; trace all connected upstream producers, shared schemas, sibling lanes, and downstream validators (`scope-containment.md`).
35. *(Retired slot.)*
36. **Disk-only plans.** Plans live at `plans/<name>-<6hex>.md`, validated by `tools/validate_implementation_plan.py` (Notion plan enforcement retired).
37. **Root-cause diagnosis on runtime failure.** Never claim `PASS` over a failing test, traceback, or `X3_BLOCK`; trace and fix the owning layer end-to-end and keep chat summaries within `output-brevity-governance.md` (`<= 450` words).

## Scope & Execution Posture

| Surface | Scope Ceiling | Verification Requirement |
|------|-------|----------------|
| **Questions / Read-Only** | Zero code changes | Direct evidence from repo files / ADG |
| **Bug Fixes (`BUG_ROOT_CAUSE`), `/boost`, & `/swarm`** | **Unbounded** (1 to N files across any layers/packages) | Root-cause tests + `verify_commit.py` (directional inter-subsystem & storage boundary linters) |
| **Cohesive Refactoring (`REFACTOR_COHESIVE`)** | **Unbounded** (as many files, submodules, or waves as needed) | Full-ripple producer+contract+validator alignment + impacted test suites |

Delete and replace bloated legacy spaghetti (`> 1,500` LOC or `> 10` private modules for a bounded output) behind its external boundary contract rather than slicing it into micro-files (`INV-DELETE-BEFORE-DECOMPOSE`). Use ADG (`adg_sqlite`), AST inspection, and `rg`/`grep_search` freely together across the repository without tool-call or file-count caps.

## Quick Gates

- Plan SSOT: `plans/<name>-<6hex>.md` (disk-only; Notion plan registration retired)
- Python file I/O: `encoding="utf-8"`
- Zero artificial blast-radius, file-count, file-size, or `/boost` / `/swarm` caps (`INV-BUDGET-FILE-LINES = 0`, `INV-ZERO-BUGFIX-BLAST-RADIUS-CAP` via `tools/zero_bugfix_constraint_gate.py`)

## Extended Doctrine (model_decision rules — load on demand)

`adg-canonical-invariants.md` · `plan-first-enforcement.md` · `wave-progression.md` · `unified-agent-architecture.md` · `conformance-map.md`
