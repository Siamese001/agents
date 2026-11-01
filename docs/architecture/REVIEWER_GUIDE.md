# Reviewer Guide — Governed Control-Plane Architecture

> **Start here.** This is the technical entry point for auditing the governed agentic control plane.  
> Read time: five minutes.  
> One-command structural & turn-gate verification: `python tools/validate_turn_gates.py --mode all && python tools/verify_commit.py --all`

---

## 1. What Was Built

This repository provides a deterministic control-plane substrate (`agents/`, `infrastructure/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`) and two high-constraint reference workloads (`resume_graph_engine` for verified document synthesis and `outreach_engine` for policy-gated external communications).

```text
U0 Airlock -> L1 Plan -> L0 Route -> C0 Factual Graph / Prompt Assembly -> L2 or L3/L2 -> Exit Gate -> UWG -> L4 State
                                                                                                         |
                                                                                                         `-> L6 Shadow Telemetry
```

---

## 2. Recommended Inspection Order

| Step | Artifact or Command | What It Proves |
| :--- | :--- | :--- |
| **1** | [`../../README.md`](../../README.md) | Platform invariants, subsystem separation, and benchmark economics |
| **2** | [`../RUNTIME_CONTROL_PLANE.md`](../RUNTIME_CONTROL_PLANE.md) | Authority boundaries across `U0`–`L6`, `Exit`, and `UWG` |
| **3** | [`architecture-proof-pack.md`](architecture-proof-pack.md) | Executable proof command map across compile-time and runtime gates |
| **4** | `python tools/validate_turn_gates.py --mode all` | Pre-turn & post-turn governance contract integrity |
| **5** | `python tools/verify_commit.py --all` | AST layer imports, 600-line file budgets, model neutrality, production purity, secrets |
| **6** | `python tools/lint_architecture_boundaries.py` | Domain storage isolation and `sys.path` purity |

---

## 3. Engineer Quickstart Commands

Run all commands from the repository root:

```bash
# 1. Mechanical turn-gate and governance contract verification
python tools/validate_turn_gates.py --mode all

# 2. Tier 1 repository-wide static verification (AST, layers, budgets, purity, secrets)
python tools/verify_commit.py --all

# 3. Domain storage isolation and sys.path purity
python tools/lint_architecture_boundaries.py

# 4. Tokenomics, multi-tier caching, and >= 2.5x Pareto ROI audit
python tools/cost_token_budget_auditor.py

# 5. Authoritative cross-subsystem end-to-end smoke verification
python ops_scripts/run_e2e_authoritative_smoke.py
```

---

## 4. What to Inspect

### Structural & Compile-Time Integrity
- Unidirectional layer imports (`L0`–`L6`) enforced via `tools/lint_layer_imports.py`.
- Zero direct database or filesystem driver imports (`sqlite3`, `SqliteStateRepository`, `JsonlEventStore`) in domain services (`tools/lint_architecture_boundaries.py`).
- Strict `<= 600` line ceiling across production Python modules (`tools/lint_file_budgets.py`).
- Zero hardcoded proprietary model identifiers outside `config/provider_profiles.yaml` (`tools/lint_model_neutral_naming.py`).

### Runtime & Cross-Subsystem Safety
- Inbound query validation and outbound briefing sanitization airlocks prevent prompt injection across `apps_research` -> `outreach_engine` and `resume_graph_engine`.
- Cryptographic SHA-256 and TTL-bounded `CrossAppEnvelope` / `ResearchBriefEnvelope` handoffs reject tampered or expired upstream context.
- 38-cluster Factual Assertion Graph (`C0.3`) and forbidden-claims linters block uncorroborated claims before `Exit` clearance.

### Governance & Operational Hygiene
- `.agents/` and `.antigravity/` house active rules, skills, lifecycle hooks (`.agents/hooks.json`), and runtime boundary declarations.
- Serialized FIFO merge queue (`tools/pr_governance.py`) prevents direct commits to `main` and enforces two-parent `--no-ff` merges with automated worktree cleanup.
