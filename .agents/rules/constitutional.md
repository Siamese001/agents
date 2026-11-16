
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
16. **Query progress bar mandatory.** Operations >5s, loops >10 lines, heavy-named functions (`scan_*`/`build_*`/`query_*`) >12 lines. Gate: `check_query_progress_bar.py`. See `query-progress-bar.md`.
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
26. **No interactive pagers in `run_command`.** `more`/`less`/`most`/`more.com` (pipe or bare) FORBIDDEN — Codex cannot answer pager prompts; pagers hang the turn. Pattern: redirect to file (`> out.txt`) + `read_file`. Long-running: `Blocking=false` + `WaitMsBeforeAsync`. Gate: `pre_run_gate.py`.
27. **Config schema purity.** `.agents/hooks.json` (only `command`+`working_directory`+`show_output`) and `.mcp.json` (only `command`+`args`+`env`+`disabled`) MUST contain ONLY official-schema fields. Unknown keys silently disable subsystem. Gate: config schema verification.
28. **SQLite-direct fallback supersedes grep for dependency analysis.** Hierarchy: (1) `adg_sqlite` MCP → (2) direct `sqlite3` of latest `artifacts/adg/adg_indexed_<ts>.sqlite` → (3) grep ONLY if BOTH fail AND `DEGRADED_FALLBACK: reason=<mcp_err>+<sqlite_err>` emitted. MCP unavailability is NEVER an excuse for grep — only for SQLite. Audit: `post_agent_adg_audit.py`. Bypass: `ADG_SQLITE_FALLBACK_BYPASS=1`.
29. **Closed-loop router evidence mandatory.** All 10 routers (L0/bandit, L0/r5, L1/c0, L2/cascade, L3/shape, L3/reroute, L4/uwg, L5/hitl, L6/promo, L6/regret) MUST emit `ROUTER_DECISION:` + `emit_ledger_event` same code path. `L6/promo` promote: Wilson≥0.60, z≥1.96, uplift>0, n≥30. `L6/regret`: non-empty `by_layer_json`. Detail: `closed-loop-router-enforcement.md`. Audit (CI): `ops_scripts/ci/check_router_calibration_evidence.py` (the post-agent response-scan audit was retired — it was unwired and a chat response carries no `ROUTER_DECISION:` markers; the in-code marker+ledger requirement and the CI gate are the real enforcement). Bypass: `ROUTER_ENFORCEMENT_BYPASS=1`.
30. **Author-Gate capture health — RETIRED** (ADR-093; Codex `request_user_input` supersedes the old marker-ledger pipeline). Slot retained for stable numbering.
31. **SSOT folder routing for new files.** `check_*`/`*_gate.py` → `ops_scripts/ci/`; calibration/binder/poller → `ops_scripts/calibration/`; `purge_*`/`cleanup_*` → `ops_scripts/maintenance/`; `pre_*`/`post_*` hooks → `.codex/governance/scripts/`; else → `tools/<domain>/`. Pre-existing files exempt. Detail: `ssot-folder-enforcement.md`. Hook: `pre_write_gate.py`. Bypass: `SSOT_FOLDER_BYPASS=1`.
32. **Fort Knox certification integrity — RETIRED (2026-06-14).** The bottom-up requirements-certification arm (`RTC-REQ-*` → `compile_requirement_signoff.py` → Merkle/signature) is decommissioned; its integrity principle (claims emerge from a compiler, no green theater) lives in §37 + `002-pass-blocked-proof-contract`. Runtime teardown (`agentic_core/L7_auditability/**`, `tools/cert/**`) deferred — tracked in git history / ADR. Slot retained for stable numbering.
33. **Two-tier compliance (Anthropic).** The real always-on surface (root `AGENTS.md` + ALL `.agents/rules/*.md`, which the native loader injects every session) MUST sum ≤86,016 bytes (84 KiB) — re-baselined from the legacy 51,200 (set for the retired 4-file `.mdc` design) by plan `always-on-rule-surface-cut-c7f3a1`. Procedural detail → skills; invariants → rules (thin pointer stubs); deterministic enforcement → hooks. Gate: `check_always_on_token_budget.py` (T7r — now measures + enforces the real surface). Bypass: `ALWAYS_ON_BUDGET_BYPASS=1`.
34. **Full-ripple inspection & telemetry (per-turn read/grep caps retired).** Artificial per-response caps on `grep_search`/`code_search` (formerly ≤3) and file reads (formerly ≤10) are retired: agents MUST read and trace all connected upstream producers, shared schemas, sibling lanes, and downstream validators when analyzing or implementing a change. Token-burn telemetry remains observational (`post_agent_token_telemetry.py` → `artifacts/governance/turn_budget.jsonl`). Detail: `scope-containment.md` and `.agents/skills/scope-containment/SKILL.md`.
35. **Author-Gate queue drain — RETIRED** (ADR-093; superseded by Codex `request_user_input` at the point of decision). Slot retained for stable numbering.
36. **Plan–Notion registration — RETIRED (notion-wave-enforcement-removal).** The plan→Notion registration pipeline never functioned and is removed. **Plans are disk-only.** The only plan gates are the disk-side format lints (`check_plan_format_compliance`, `check_plan_wave_summary_top`, `check_plan_definition_of_done`) + `plan-location.md`. Slot retained for stable numbering.
37. **RCA mandatory on runtime failure.** Any repo-work response that sets `STATUS: FAIL` or surfaces a runtime-failure signal (`X3_BLOCK`, traceback, non-zero exit, pytest `N failed`, `PRE_RUN_BLOCKED`, `BLOCKED_*`/`MISSING_GRAPH_PATH`) MUST carry an `RCA:` block — symptom · root_cause (graded §20) · evidence · fix_or_next (§7) · recurrence_guard. A green/PASS status over a body failure-signal is forbidden (an exit code or X3 label alone is not a runtime outcome). **On refactoring turns (T2/T3 code changes) the response MUST use the Outcome frame on EVERY turn (pass or fail) — Did it run? + verdict source + provenance · What worked · Failure · Next (the PASS/FAIL verdict is the `STATUS:` line; the frame proves it, it does not re-vote); omitting it is `missing_refactor_outcome`. On a failure the frame MUST carry the deep Layered RCA: Immediate symptom → Failing layer (isolated from the surfacing layer) → Why-chain (apply "but why?" and dig until the true root, even across many levels; ≥2 descent levels) → Root cause (DISTINCT from the symptom) → Evidence → Confidence. Stopping at a symptom, a single-hop cause, or root==symptom is `shallow_rca`.** Detail: `001-runtime-seam-execution.md` § Runtime failure ⇒ RCA mandatory. Audit: `post_agent_runtime_rca_audit.py` → `artifacts/governance/runtime_rca_violations.jsonl` (kinds `missing_refactor_outcome`/`missing_rca`/`incomplete_rca`/`status_signal_mismatch`/`shallow_rca`). Bypass: `RUNTIME_RCA_AUDIT_BYPASS=1`.

## Scope & Execution Posture

| Surface | Scope Ceiling | Verification Requirement |
|------|-------|----------------|
| **Questions / Read-Only** | Zero code changes | Direct evidence from repo files / ADG |
| **Bug Fixes, `/boost`, & `/swarm`** | **Unbounded** (1 to N files across any layers/packages) | Root-cause tests + `verify_commit.py` (`<= 600`-line file budget & boundary linters) |
| **Cohesive Refactoring** | **Unbounded** (as many files, submodules, or waves as needed) | Full-ripple producer+contract+validator alignment + impacted test suites |

Use ADG (`adg_sqlite`), AST inspection, and `rg`/`grep_search` freely together to trace imports, callers, schemas, and literals across the entire repository without tool-call or file-count caps.

## Quick Gates

- Plan SSOT: `plans/<name>-<6hex>.md` (legacy `.codex/plans/` still valid) — never `docs/reports/plans/` for plans
- Python file I/O: `encoding="utf-8"`
- `grep_search` permitted only to confirm literals, never for dependency tracing

## Extended Doctrine (model_decision rules — load on demand)

`adg-analysis-procedures.md` · `adg-canonical-invariants.md` · `plan-first-enforcement.md` · `memory-management.md`

> Deprecated ADG/Author-Gate/deferred-scope/notion-plan stubs and the Notion plan-status/wave/registration rules were removed (never functioned; plans are disk-only). Signal lives at canonical targets (constitutional §6/§24/§36, `plan-location.md`); full map: `docs/reports/governance/retired-rules-index.md`.
