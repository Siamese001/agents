
<!-- Converted from `.codex/rules/constitutional.md`. Original legacy editor trigger: `always_on`. -->

> See `AGENTS.md` for shared retrieval / enforcement guidance.

# Constitutional Floor

> ⛔ Applies every task, every tier, every session. No exceptions.

## Hard Constraints

0. **Subprocess timeout required.** `subprocess.run(argv, shell=False, timeout=30)`. PowerShell is permitted (primary Windows shell); the legacy legacy editor-era PowerShell ban is lifted. (Slot §14 retained for stable numbering.)
1. **No test skipping.** No `pytest.mark.skip`, no `xfail` without `strict=True`.
2. **Root-cause bug resolution without artificial barriers.** Trace and fix discovered bugs across all impacted files, contracts, and tests immediately without file-count or blast-radius caps (keeping `<= 600`-line file budgets and inter-subsystem import boundaries intact).
3. **Clean dead-code retirement.** Dead or superseded modules/agents with zero live callers may be retired or consolidated cleanly during refactoring once full reference checks pass.
4. **Tier 1 & Tier 2 verification.** `python tools/verify_commit.py` and `python tools/verify_main_readiness.py`.
5. **Structural dependency tracing.** Use ADG (`adg_sqlite`), AST analysis, and unconstrained file/text search to inspect full upstream/downstream ripple impact across the repository.
6. **Ambiguity-gated HITL (`ask_question`).** Surface one atomic plain-English question via `ask_question` only when genuine ambiguity exists ($\Delta \le 20\%$ or top confidence $< 65\%$); multi-layer blast radius incurs zero confidence penalty.
7. **RCA auto-closure.** Execute corrective actions immediately across all root-cause layers. Never leave RCA unresolved or defer multi-file bugs.
8. **Guardian exemptions require rationale.** `# guardian: allow-<type> -- <specific justification>`. Generic words forbidden.
9. **SVP Engineering rigor for architecture.** Operational simplicity, `<= 600`-line modular files, clean inter-subsystem boundaries, zero-regression.
10. **Zero-loss refactor.** After refactoring or decomposing monoliths, verify public facade exports and module/symbol test coverage (`tools/testing_gaps_auditor.py`).
11. **Terminal process lifecycle.** All `run_command`/subprocess invocations must terminate cleanly and reap background tasks.
12. **No imports from `archives/` in production.**
13. **Non-blocking structural inspection fallback.** Prefer `adg_sqlite` MCP or `artifacts/adg/*.sqlite` when available; if unavailable or closed, proceed immediately using direct AST/code search without blocking root-cause edits or `/boost` / `/swarm` workers.
14. **Subprocess timeout required** — reserved alias of §0, kept for stable numbering (sibling rules `query-progress-bar.md` and `python-dash-c-quote-hazard.md` cite "§14"; do not renumber to dedupe). See §0.
15. **Precise exception handling.** Catch specific types. Bare `except:` and `except Exception` without guardian comment FORBIDDEN.
16. **Progress reporting on long-running loops.** Emit clear progress indicators on heavy batch operations (>5s). See `query-progress-bar.md`.
17. **Memory lifecycle (native file memory).** Recall project memory at session start and write back significant decisions/patterns. SSOT is native file memory (`memory/MEMORY.md` + per-fact files); the knowledge-graph MCP is optional for genuine graph queries. W3 supersession (ADR-095) retired the mandatory `mem_recall_session_start` first-call ritual and the purge/staleness gates.

### Process Discipline (§18–§21)

18. **Cohesive root-cause scope (zero blast-radius cap).** Expand freely across all connected producers, contracts, consumers, validators, and tests needed to fix a bug or complete a refactor; avoid unrelated cosmetic churn only.
19. **Plan-only firewall respected.** Honor explicit `PLAN ONLY` / `NO IMPLEMENT` prompts; otherwise execute root-cause fixes, `/boost`, and `/swarm` end-to-end.
20. **Fact grading mandatory.** Classify claims as **DIRECTLY OBSERVED** / **DERIVED** / **UNRESOLVED**. Don't present unresolved as fact.
21. **Zero-loss overwrite discipline.** When overwriting rule/skill/workflow: preserve active constraints + script-relied references; remove obsolete caps.

22. **ADG & AST structural analysis.** Use ADG views (`mv_*`, semantic edges, `v_p0_*`..`v_p3_*`) and AST/search inspection to trace full transitive dependencies during refactoring; missing optional ADG sections never block valid wave plans.
23. **ADG canonical invariants.** SQLite=truth, Redis=hot projection, MCP=read-only gateway. Detail: `adg-canonical-invariants.md`.
24. **Zero bug-deferral rule.** Fix discovered bugs immediately at their root cause regardless of file count or layer span; reserve `spawn_task` / backlog items strictly for optional future feature ideas unrelated to active bugs.
25. *(Reserved — no rule occupies §25. Slot intentionally vacant; numbering held stable because `§`-citations are load-bearing across rules. Do not renumber to close the gap.)*
26. **No interactive pagers in `run_command`.** `more`/`less`/`most`/`more.com` (pipe or bare) FORBIDDEN; redirect to file (`> out.txt`) + `read_file` and use bounded `WaitMsBeforeAsync`.
27. **Config schema purity.** `.agents/hooks.json` and `.mcp.json` MUST contain only supported schema fields (`tools/ssot_boundary_auditor.py`).
28. **Combined ADG, AST, and grep dependency analysis.** Use `adg_sqlite` MCP, `artifacts/adg/*.sqlite`, AST analysis, and `grep_search` freely together across all structural and literal lookups without degraded-fallback blocks.
29. **Closed-loop router evidence mandatory.** Routers emit `ROUTER_DECISION:` + `emit_ledger_event` on the same code path (`L6/promo` promote: Wilson>=0.60, z>=1.96, uplift>0, n>=30; `L6/regret`: non-empty `by_layer_json`). Detail: `closed-loop-router-enforcement.md`.
30. **Author-Gate capture health — RETIRED** (ADR-093; `ask_question` supersedes the old marker-ledger pipeline). Slot retained for stable numbering.
31. **SSOT folder routing for new files.** Place governance/gate/hook scripts under `tools/` (wired via `.agents/hooks.json` -> `tools/hook_dispatch.py`), smoke runners under `ops_scripts/`, serving scripts under `scripts/`, and domain code inside its owning package root. Detail: `ssot-folder-enforcement.md`.
32. **Fort Knox certification integrity — RETIRED (2026-06-14).** Integrity principle lives in §37 + `002-pass-blocked-proof-contract.md`. Slot retained for stable numbering.
33. **Concise governance context budget.** Root `AGENTS.md <= 200` lines (`INV-AGENTS-MD-MAX-LINES`) and `.agents/skills/*/SKILL.md` descriptions `<= 4,000` tokens (`INV-SKILLS-BUDGET-MAX-TOKENS`), enforced by `tools/validate_turn_gates.py`.
34. **Full-ripple inspection & telemetry (per-turn read/grep caps retired).** Artificial per-response caps on `grep_search`/`code_search` and file reads are retired: agents MUST read and trace all connected upstream producers, shared schemas, sibling lanes, and downstream validators when analyzing or implementing a change. Detail: `scope-containment.md` and `.agents/skills/scope-containment/SKILL.md`.
35. **Author-Gate queue drain — RETIRED** (ADR-093). Slot retained for stable numbering.
36. **Plan–Notion registration — RETIRED (notion-wave-enforcement-removal).** **Plans are disk-only** (`plans/<name>-<6hex>.md`), validated by `tools/validate_implementation_plan.py` + `plan-location.md`. Slot retained for stable numbering.
37. **Root-cause diagnosis on runtime failure.** Never claim `PASS` over a failing test, traceback, or `X3_BLOCK` signal; trace every runtime failure down its causal chain to the owning layer, fix it end-to-end (§7), and keep user-facing chat summaries within `output-brevity-governance.md` (`<= 450` words, plain-English clarity).

## Scope & Execution Posture

| Surface | Scope Ceiling | Verification Requirement |
|------|-------|----------------|
| **Questions / Read-Only** | Zero code changes | Direct evidence from repo files / ADG |
| **Bug Fixes, `/boost`, & `/swarm`** | **Unbounded** (1 to N files across any layers/packages) | Root-cause tests + `verify_commit.py` (`<= 600`-line file budget & boundary linters) |
| **Cohesive Refactoring** | **Unbounded** (as many files, submodules, or waves as needed) | Full-ripple producer+contract+validator alignment + impacted test suites |

Use ADG (`adg_sqlite`), AST inspection, and `rg`/`grep_search` freely together to trace imports, callers, schemas, and literals across the entire repository without tool-call or file-count caps.

## Quick Gates

- Plan SSOT: `plans/<name>-<6hex>.md` — never `docs/reports/plans/` for plans
- Python file I/O: `encoding="utf-8"`
- Zero artificial blast-radius, file-count, or `/boost` / `/swarm` caps (`INV-ZERO-BUGFIX-BLAST-RADIUS-CAP` via `tools/zero_bugfix_constraint_gate.py`)

## Extended Doctrine (model_decision rules — load on demand)

`adg-analysis-procedures.md` · `adg-canonical-invariants.md` · `plan-first-enforcement.md` · `memory-management.md`

> Deprecated ADG/Author-Gate/deferred-scope/notion-plan stubs and the Notion plan-status/wave/registration rules were removed (never functioned; plans are disk-only). Signal lives at canonical targets (constitutional §6/§24/§36, `plan-location.md`); full map: `docs/reports/governance/retired-rules-index.md`.
