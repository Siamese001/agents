# Architecture Proof Pack

> **Status:** Active executable proof pack; every command below runs deterministically against the current repository tree.  
> **Primary Verification Gate:** `python tools/validate_turn_gates.py --mode all && python tools/verify_commit.py --all`  
> **Control-Plane Spec:** [`docs/RUNTIME_CONTROL_PLANE.md`](../RUNTIME_CONTROL_PLANE.md)

---

## 1. Governed Runtime Control Loop

All platform substrates and reference workloads operate inside a deterministic, layered control loop:

```text
Incoming Request / CrossAppEnvelope
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  U0 / L1  Inbound Airlock & Bounded Query Decomposition      │
│           SHA-256 envelope verification + HITL margin gate   │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  L0       Contract-Bound Router                              │
│           Route authority + turn/token/timeout budget        │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  C0       Factual Assertion Graph (C0.3) & Hybrid RRF        │
│           Dense BGE-M3 + BM25 retrieval -> EvidenceBundle    │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  L2 / L3  Bounded Execution & Socratic Self-Correction       │
│           Hard-capped iterations + protocol-isolated state   │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  L5 / UWG Exit Gate & Universal Write Gateway                │
│           Multi-judge rubric + forbidden-claims lint -> L4   │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  L6       Out-of-Band OpenTelemetry & Offline Eval Surface   │
│           Zero in-flight mutation; shadow drift detection    │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Executable Proof Command Map

Run these commands from the repository root to verify each architectural guarantee independently:

| Proof ID | Command | What It Verifies |
| :--- | :--- | :--- |
| **P1: Turn & Contract Gates** | `python tools/validate_turn_gates.py --mode all` | Hooks presence (`.agents/hooks.json`), `AGENTS.md` memory bound (`<= 200` lines), runtime boundary, provider catalog, and wave plan compliance |
| **P2: Tier 1 Commit Gate** | `python tools/verify_commit.py --all` | Repository-wide AST compilation, `<= 600` line module budgets, `L0`–`L6` layer imports, model neutrality, production purity, and secrets scan |
| **P3: Storage & Boundary Isolation** | `python tools/lint_architecture_boundaries.py` | Zero concrete persistence imports (`sqlite3`, JSONL/SQLite stores) in domain services and zero `sys.path` mutations |
| **P4: Tokenomics & Caching ROI** | `python tools/cost_token_budget_auditor.py` | 8-pillar token budget architecture, multi-tier caching, and $\ge 2.5\times$ Pareto ROI verification |
| **P5: Sidecar & Worktree Hygiene** | `python tools/validate_sidecar_separation.py && python tools/storage_worktree_hygiene.py` | Cross-repo isolation for the 7 scheduled `agents-*` sidecars and 6-pillar SQLite WAL / worktree hygiene |
| **P6: Cross-Subsystem Contracts** | `pytest tests/unit/test_cross_subsystem_handoff_contracts.py tests/unit/test_testing_gaps_edge_cases.py -v --timeout=60` | Cryptographic `CrossAppEnvelope` roundtrip, tamper rejection, TTL expiry, and prompt-injection airlocks |
| **P7: Authoritative E2E Smoke** | `python ops_scripts/run_e2e_authoritative_smoke.py` | End-to-end governed execution smoke verification across core substrates |
