# Runtime Control Plane Specification

A technical specification for principal architects and engineering leaders detailing the authority boundaries, handoff contracts, and executable verification surfaces of the governed runtime.

---

## Core Thesis

Enterprise agentic AI fails at the runtime boundary, not at the model boundary. Production-grade reliability requires a deterministic control plane that owns:

1. Request validity, identity binding, and inbound prompt-injection sanitization (`U0`);
2. Bounded decomposition and ambiguity scoring without route authority (`L1`);
3. Route selection under a typed contract (`L0`);
4. Verified context hydration and factual graph grounding (`C0`);
5. Authority-ordered prompt compilation (`PA`);
6. Bounded model, tool, and action execution (`L2` / `L3`);
7. Current-run exit evaluation and rubric verification (`L5` / `Exit`);
8. Single-door durable write admission (`UWG` -> `L4`);
9. Out-of-band telemetry, replay digests, and shadow learning (`L6`).

---

## Control-Point Topology

```text
U0 Intake & Airlock
  -> L1 Plan & Ambiguity Gate
    -> L0 Route Contract
       |-> Terminal cache / pre-certified abstention -> Exit
       |-> C0 Factual Graph Grounding -> Prompt Assembly -> L2 Bounded Execution
       `-> L3 Orchestrated Workflow -> Bounded L2 Steps

L2 Sealed Result -> Exit X3 Disposition
  |-> ALLOW_OR_FINISH / SAFE_ABSTAIN / ESCALATE_HITL
  `-> COMMIT_REQUEST_TO_UWG -> UWG Atomic Validation -> L4 Durable State

Completed Runtime Exhaust -> L6 Shadow Telemetry & Offline Evaluation
```

---

## Responsibility Matrix

| Surface | Owns | Strictly Prohibited From |
| :--- | :--- | :--- |
| **`U0` Intake** | Envelope validation, SHA-256 integrity, TTL checks, prompt-injection airlock | Semantic planning, routing, retrieval, or state mutation |
| **`L1` Plan** | Goal decomposition, calibrated confidence margin ($\Delta \le 20\%$ HITL gate), bounded plan | Route authority, direct tool execution, or unverified retrieval |
| **`L0` Route** | Selecting one typed route contract and execution budget | Prompt string concatenation or direct model invocation |
| **`C0` Context** | Factual Assertion Graph (`C0.3`) retrieval, dense + BM25 RRF ranking, provenance binding | Answering user queries, altering routes, or overriding system instructions |
| **`Prompt Assembly`** | Canonical slot ordering, instruction/data separation, provider-neutral rendering | Ad-hoc retrieval, route mutation, or side-effecting execution |
| **`L3` Orchestration** | Multi-step readiness ledger, 10-field sub-agent delegation contracts, cross-app envelopes | Direct database writes (`sqlite3`) or unbudgeted sub-agent spawning |
| **`L2` Execute** | Frozen capability envelope, bounded Socratic repair loop, sealed output proposal | Route expansion, opportunistic retrieval, or direct durable commits |
| **`Exit` (`L5`)** | Rubric grading, forbidden-claims linting, and emitting one terminal disposition | Direct state storage or unbounded retry loops |
| **`UWG`** | Atomic write admission, schema verification, and provenance sealing | Model inference or ad-hoc business logic |
| **`L4` State** | Protocol-isolated durable state and immutable audit ledgers | Direct unvalidated mutations from domain services |
| **`L6` Shadow** | OpenTelemetry span emission, drift detection, and offline evaluation (`apps_eval`) | Mutating in-flight execution state |

---

## Separation of Duties Invariants

The runtime enforces two foundational separation-of-duty laws:

1. **Write-Path Sovereignty**:
   > **`L2` proposes -> `Exit` clears -> `UWG` commits -> `L4` stores.**
   Domain services (`resume_graph_engine/src/apps_rg`, `outreach_engine/src/apps_lic`, `agents/orchestration/services`) are mechanically blocked by [`tools/lint_architecture_boundaries.py`](../tools/lint_architecture_boundaries.py) from importing concrete persistence drivers (`sqlite3`, `SqliteStateRepository`, `JsonlEventStore`, `FilesystemArtifactStore`).

2. **Context vs. Instruction Authority**:
   > **`C0` grounds; `Prompt Assembly` compiles; neither surface executes.**
   Retrieved evidence remains untrusted data inside fenced slots and can never escalate into instruction authority.

---

## Platform Subsystem Mapping

| Package | Architectural Classification | Primary Control-Plane Surface |
| :--- | :--- | :--- |
| [`agents/`](../agents/) & [`infrastructure/`](../infrastructure/) | **Core Control-Plane Substrate** | `L0`–`L6` runtime protocols, persistence adapters, and cross-app handoff contracts |
| [`apps_eval/`](../apps_eval/) | **Evaluation & Calibration Substrate** | Multi-judge calibration, rubric grading, and regression ratcheting |
| [`apps_model_telemetry/`](../apps_model_telemetry/) | **Observability & Tokenomics Substrate** | `L6` OpenTelemetry instrumentation, latency profiling, and cache ROI tracking |
| [`apps_research/`](../apps_research/) | **Grounded Evidence Substrate** | `U0` query airlock and `C0` SHA-256 sealed `ResearchBriefEnvelope` generation |
| [`resume_graph_engine/`](../resume_graph_engine/) (`apps_rg`) | **Reference Workload: Verified Document Synthesis** | 38-cluster Factual Assertion Graph (`C0.3`), BGE-M3 + BM25 RRF, and `G1`–`G6` evals |
| [`outreach_engine/`](../outreach_engine/) (`apps_lic`) | **Reference Workload: Policy-Gated Messaging** | Inbound/outbound injection airlock, forbidden-claims linting, and multi-touch state machine |

---

## Executable Proof Obligations

Verify the control-plane contracts, layer boundaries, and end-to-end runtime behavior directly from the repository root:

```bash
# 1. Verify pre-turn and post-turn governance gates
python tools/validate_turn_gates.py --mode all

# 2. Verify AST layer imports (L0-L6), 600-line file budgets, production purity, and secrets
python tools/verify_commit.py --all

# 3. Verify domain storage isolation and sys.path purity
python tools/lint_architecture_boundaries.py

# 4. Run the authoritative cross-subsystem end-to-end smoke suite
python ops_scripts/run_e2e_authoritative_smoke.py
```

Additional reviewer entry points:
- [`architecture/REVIEWER_GUIDE.md`](architecture/REVIEWER_GUIDE.md)
- [`architecture/architecture-proof-pack.md`](architecture/architecture-proof-pack.md)
- [`SVP_ENGINEERING_GOVERNANCE_README.md`](SVP_ENGINEERING_GOVERNANCE_README.md)
