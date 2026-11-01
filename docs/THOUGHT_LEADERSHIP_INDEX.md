# Thought Leadership & Architectural Thesis Index

An index connecting the engineering primitives in this repository to the architectural principles required for production-grade enterprise agentic AI.

---

## Core Thesis

> **Enterprise agentic AI requires a deterministic runtime control plane.**

Models are probabilistic; production systems must be deterministic. Autonomous AI becomes enterprise-ready only when wrapped in governed software engineering primitives: typed route contracts, graph-grounded context, bounded execution loops, mandatory exit gates, single-door write admission, and out-of-band shadow learning.

---

## Architectural Reference Series

1. **The Agent Is Not the Product; The Runtime Control Plane Is** — Why enterprise AI fails at the system boundary rather than the model boundary ([`docs/EXECUTIVE_OVERVIEW.md`](EXECUTIVE_OVERVIEW.md)).
2. **Operating Model & Reliability Economics at Scale** — Scaling from a single AI squad to a multi-team organization using compile-time AST enforcement and bounded tokenomics ([`docs/RECRUITER_GUIDE.md`](RECRUITER_GUIDE.md)).
3. **Separation of Duties in Agentic Systems (`U0`–`L6`)** — Enforcing strict boundaries between planning, routing, grounding, execution, exit evaluation, and durable state ([`docs/RUNTIME_CONTROL_PLANE.md`](RUNTIME_CONTROL_PLANE.md)).
4. **Factual Assertion Graphs vs. Unverified Generation** — Eliminating hallucinated attributions using 38-cluster graph authority and hybrid dense + lexical Reciprocal Rank Fusion ([`resume_graph_engine/README.md`](../resume_graph_engine/README.md)).
5. **Inbound Airlocks & Policy-Gated External Communications** — Defending multi-touch agent state machines against indirect prompt injection and forbidden claims ([`outreach_engine/README.md`](../outreach_engine/README.md)).
6. **Compile-Time Governance for AI-Assisted Engineering** — Turning architectural boundaries, file budgets, model neutrality, and PR merge queues into `< 5s` mechanical gates ([`docs/SVP_ENGINEERING_GOVERNANCE_README.md`](SVP_ENGINEERING_GOVERNANCE_README.md)).

---

## Primary Technical Inspection Path

1. [`README.md`](../README.md) — Platform guarantees, benchmark economics, and quickstart commands.
2. [`docs/EXECUTIVE_OVERVIEW.md`](EXECUTIVE_OVERVIEW.md) — Executive control-plane thesis.
3. [`docs/RECRUITER_GUIDE.md`](RECRUITER_GUIDE.md) — Organizational scaling and unit economics.
4. [`docs/RUNTIME_CONTROL_PLANE.md`](RUNTIME_CONTROL_PLANE.md) — Control-point specification (`U0`–`L6`).
5. [`docs/architecture/REVIEWER_GUIDE.md`](architecture/REVIEWER_GUIDE.md) & [`docs/architecture/architecture-proof-pack.md`](architecture/architecture-proof-pack.md) — Executable verification commands.
