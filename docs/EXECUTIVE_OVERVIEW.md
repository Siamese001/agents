# Executive Overview

## Bottom Line

The agent is not the product. The **governed runtime control plane around the agent** is the product.

This repository is a production-hardened reference architecture for a deterministic AI control plane: typed route contracts, graph-grounded context (`C0`), bounded Socratic execution (`L2`), mandatory exit gates (`L5`), single-door write admission (`UWG`), deterministic replay, and out-of-band shadow learning (`L6`).

---

## Why This Matters at Organizational Scale

Most enterprise AI initiatives stall after the initial prototype: a model demo succeeds in isolation, but the surrounding engineering system lacks route authority, factual provenance guarantees, bounded retry ceilings, write isolation, and compile-time layer enforcement. The result is non-reproducible behavior, unpredictable token spend, and unverified state mutations.

This platform addresses those failure modes as **machine-enforced invariants** rather than aspirational guidelines:

- **Route Authority (`L0`)** — Runtime paths are dispatched through typed routing contracts with explicit turn, token, and latency budgets.
- **Graph-Grounded Context (`C0`)** — Candidate claims are validated against a 38-cluster Factual Assertion Graph (`C0.3`) using hybrid dense BGE-M3 + BM25 Reciprocal Rank Fusion before prompt compilation.
- **Prompt Assembly as an Engineering Control (`PA`)** — Prompts are compiled from authority-ordered slots with strict instruction/data separation and inbound prompt-injection airlocks.
- **Bounded Socratic Execution (`L2`)** — Self-correction loops are hard-capped (default 3 turns); failure to clear multi-judge rubric thresholds triggers a deterministic, pre-certified safe abstention.
- **Universal Write Gateway (`UWG`)** — Domain services are mechanically blocked at compile time (`tools/lint_architecture_boundaries.py`) from importing concrete persistence drivers; all state mutations pass through atomic exit and write gates.
- **Tokenomics & Caching ROI** — Multi-tier caching and prompt compression are continuously audited (`tools/cost_token_budget_auditor.py`) to maintain a $\ge 2.5\times$ Pareto return on investment.
- **Shadow Learning (`L6`)** — OpenTelemetry exhaust and offline evaluation suites (`apps_eval`) operate strictly after the run boundary, preventing live in-flight drift.

---

## Runtime Control Model

```text
U0 Airlock -> L1 Plan -> L0 Route -> C0 Grounding -> L2 Execute -> Exit Clears -> UWG Commits -> L4 State
                                                                                      ↓
                                                                           L6 Observes (Shadow)
```

The foundational operating law:
> **`L2` proposes -> `Exit` clears -> `UWG` commits -> `L4` stores.**

---

## Suggested Reading Path

1. [`README.md`](../README.md) — System guarantees, benchmark economics, and subsystem architecture
2. [`docs/RECRUITER_GUIDE.md`](RECRUITER_GUIDE.md) — Operating model, organizational scaling, and reliability economics
3. [`docs/RUNTIME_CONTROL_PLANE.md`](RUNTIME_CONTROL_PLANE.md) — Technical specification for the `U0`–`L6` control plane
4. [`docs/architecture/REVIEWER_GUIDE.md`](architecture/REVIEWER_GUIDE.md) — Five-minute technical audit and executable proof commands
5. [`docs/SVP_ENGINEERING_GOVERNANCE_README.md`](SVP_ENGINEERING_GOVERNANCE_README.md) — Compile-time AST gates, turn validators, and PR queue governance
