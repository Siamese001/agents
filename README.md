# Agentic Workflow — A Deterministic AI Control Plane

> **A governed runtime around the agent — not another agent framework.**  
> Route authority, verified context, bounded execution, runtime gates, single-door writes, exact replay, and shadow learning. Built as an enterprise-grade reference design for governed AI systems.

**Author:** [Amit Ayer](https://github.com/Siamese001) — SVP-level Agentic Engineer | Platform Architecture for Governed Enterprise AI.

---

## The Thesis

Most public discourse about "agents" focuses on **frameworks, prompts, and playground demos**. That framing is the exact reason enterprise AI initiatives stall the moment they confront real-world compliance, security, and runtime boundaries.

The argument this repository makes — and demonstrates in production-grade code — is the opposite:

> **The agent is not the product. The governed runtime around the agent is the product.**

Enterprise AI in mission-critical environments consistently fails on five predictable architectural fault lines:

1. **No route authority** — The model hallucinates what tool or action to invoke next, instead of dispatching through typed, contract-bound state machines.
2. **No context guarantees** — Retrieval quietly injects stale or unverified text, instead of strictly grounding every generated claim against authoritative canonical evidence.
3. **No exit evaluation** — Outputs commit to storage or external channels without an automated, multi-dimensional gate (allow / deny / repair / escalate).
4. **No write controls** — State mutates through ad-hoc database calls across arbitrary worker threads rather than a single-door, auditable gateway.
5. **No replayability** — Failure states cannot be deterministically reconstructed from logs, making regressions impossible to debug, audit, or prevent safely.

These failure modes are **system engineering problems**, not prompt-engineering problems. This repository is the engineering substrate behind the philosophy: **AI that behaves like software, not experiments.**

---

## What This Is *Not*

- **Not an agent framework:** Not another CrewAI, LangGraph, or AutoGen clone.
- **Not a prompt library:** Prompts are versioned, typed configuration assets, not unbounded instructions.
- **Not an unbounded autonomous sandbox:** Every agent operation executes within hard contract boundaries, token quotas, and automated veto gates.
- **Not a prototype:** It is a **public reference design** written so that an SVP of Engineering, CISO, or Head of Platform can evaluate architectural rigor without relying on superficial screenshots.

---

## Why This Matters for Engineering Leadership

For a CTO, VP of Engineering, or Head of Platform, the hiring signal demonstrated here is not merely "can build an LLM wrapper." The signal is:

> **Can architect the governance operating system, execution boundaries, and evaluation infrastructure required for AI teams and autonomous runtimes to scale safely in enterprise environments.**

This repository demonstrates:
- **Contract-first engineering:** Strict schema enforcement via Pydantic and typed interfaces.
- **Structural governance:** Static AST dependency graphs (ADG), forbidden-claims guardrails, and deterministic exit gates.
- **Dual deployment flexibility:** Monorepo coherence alongside fully decoupled, standalone micro-subsystems.
- **Audit-ready provenance:** Compiler-only signed evidence and reproducible evaluation benchmarks.

---

## High-Level Architecture

```
                          User / Mission Brief
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │       Target Context & Evidence Layer     │
             │   (Candidate Profiles, Dossiers, Grounding)│
             └─────────────────────┬─────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
        ┌───────────────────────┐     ┌───────────────────────┐
        │      apps_rg_v2       │     │    outreach_engine    │
        │   Autonomous Resume   │     │ Lifecycle Intelligence│
        │   Generation Engine   │     │  & Outbound Synthesis │
        └───────────┬───────────┘     └───────────┬───────────┘
                    │                             │
                    ├──────────────┬──────────────┤
                    ▼              ▼              ▼
        ┌────────────────┐ ┌──────────────┐ ┌────────────────┐
        │  Prompt/Graph  │ │ Bounded A2A  │ │   Multi-Touch  │
        │    Compiler    │ │ Loops & SMT  │ │    Sequencer   │
        └───────────┬────┘ └───────┬──────┘ └───────────┬────┘
                    └──────────────┼────────────────────┘
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │       Automated Rubric & Safety Gates     │
             │   (Forbidden Claims, Grounding, Length)   │
             └─────────────────────┬─────────────────────┘
                                   │ [Pass / Repair / Veto]
                                   ▼
             ┌───────────────────────────────────────────┐
             │        Verified Runtime Outputs           │
             │  (LaTeX Resumes, Outreach Briefs, Audits) │
             └───────────────────────────────────────────┘
```

---

## Core Application Subsystems

Following a comprehensive forensic audit, legacy monolithic framework layers (`agentic_core`, `apps_shared`, legacy `apps_rg`, `apps_lic`, `apps_qna`, `apps_underwriting_ai`) have been retired. The platform is anchored by decoupled, autonomous v2 subsystems designed for high velocity, clean isolation, and standalone portability:

| Application | Subsystem Focus | Key Architectural Patterns | Status / Links |
| :--- | :--- | :--- | :--- |
| [`apps_rg_v2`](apps_rg_v2/) | **Autonomous Executive Resume Engine** | Offline BGE-M3 vector qualification, Slalom-activated graph orchestration, bounded Agent-to-Agent loops, deterministic LaTeX compilation. | **Production Ready**<br>[README](apps_rg_v2/README.md) • [Docs](apps_rg_v2/docs/) |
| [`outreach_engine`](outreach_engine/) | **Lifecycle Intelligence & Communication** | Grounded executive outbound authoring, dynamic YAML prompt resolution, forbidden claims assertions, mission fixture ingestion, multi-touch cadence planner. | **Production Ready**<br>[README](outreach_engine/README.md) |
| [`apps_exec`](apps_exec/) | **Executive Brief Generator** | High-level executive synthesis, strategic narrative condensation, and portfolio briefs. | Governed Subsystem |
| [`apps_research`](apps_research/) | **Autonomous Research Substrate** | Structured target company profiling, executive dossier extraction, and deep topic synthesis. | [README](apps_research/README.md) |
| [`apps_eval`](apps_eval/) | **Evaluation Lab & Model Benchmarks** | Multi-hop rubric judges, automated LLM graders, regression suites, and calibration harnesses. | [README](apps_eval/README.md) |
| [`apps_architect`](apps_architect/) | **Architecture Governance & Pattern Collector** | Deterministic pattern scanning, AST dependency auditing, and architectural drift defense. | Governed Subsystem |

> [!NOTE]
> **Dual Deployment Parity**: Both [`apps_rg_v2`](apps_rg_v2/) and [`outreach_engine`](outreach_engine/) maintain complete standalone independence. They can be executed directly within this monorepo or deployed as fully autonomous, standalone repositories:
> - [`apps_rg_v2` Standalone](https://github.com/Siamese001/apps_rg_v2)
> - [`apps_lic_v2` / `outreach_engine` Standalone](https://github.com/Siamese001/apps_lic_v2)

---

## Architectural Principles & Enforced Invariants

### 1. Grounded Context & Zero Hallucination Invariants
- **Indisputable Facts Only:** Output generators are strictly forbidden from fabricating metrics, unverified company achievements, or unsupported executive claims.
- **Assertion Gates:** Every generated text artifact passes through an automated validation layer that cross-references candidate dossiers before dispatch.

### 2. Bounded Autonomous Loops
- **Strict Iteration Caps:** Agent-to-agent refinement cycles (e.g. Writer ↔ Critic) are bounded by deterministic step ceilings (max 2–3 iterations) to eliminate infinite latency loops and runaway token expenditure.
- **Fail-Closed Escalation:** When a repair loop fails to converge, the subsystem defaults to safe fallback templates rather than unvalidated model output.

### 3. Programmatic Tool & Model Isolation
- **Typed Input/Output Contracts:** Actions communicate via Pydantic domain models with runtime schema validation.
- **Runtime Boundary Defender:** Local process execution, virtual environment scope, and tool execution boundaries are isolated from ambient machine contamination.

### 4. AST Dependency Graph (ADG) Governance
- **Source of Truth for Code Structure:** An AST-based dependency graph monitors imports, call hierarchies, and cross-subsystem boundaries.
- **Zero Monolithic Drift:** Hard architectural boundaries prevent rogue dependencies from sneaking between decoupled subsystems.

---

## Repository Directory Layout

```
Agentic-Workflow/
├── apps_rg_v2/           # Standalone Executive Resume Engine (Slalom graph, BGE-M3, LaTeX)
├── outreach_engine/      # Standalone Lifecycle Intelligence (Grounded Outreach & Cadences)
├── apps_exec/            # Executive Brief Generation & Portfolio Synthesis
├── apps_research/        # Deep Research Substrate & Target Company Profiling
├── apps_eval/            # Autonomous Evaluation Lab & Rubric Graders
├── apps_architect/       # Architecture Governance & Pattern Collection Engine
├── artifacts/            # Evaluation benchmarks, ADG graph snapshots, and runtime traces
├── config/               # Platform policies, exit rubrics, and telemetry definitions
├── data/                 # Golden fixtures, candidate dossiers, and calibration test sets
├── docs/                 # Architecture Decision Records (ADRs), specs, and reviewer guides
├── infrastructure/       # Core SDK wrappers, reasoning helpers, and base typings
├── memory/               # Semantic memory stores and persistent runtime states
├── ops_scripts/          # CI/CD verification, lint enforcement, and automation tooling
├── scripts/              # Governance verification and diagnostic runners
├── tests/                # Consolidated test suite for platform and active subsystems
└── tools/                # Diagnostic CLIs, cache utilities, and audit tools
```

---

## Quickstart

### Prerequisites
- Python 3.11 or 3.12
- Git

### 1. Clone & Setup
```bash
git clone https://github.com/Siamese001/Agentic-Workflow.git
cd Agentic-Workflow

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\Activate.ps1

# Install repository in editable mode
pip install -e .
```

### 2. Run the Autonomous Resume Engine (`apps_rg_v2`)
```bash
cd apps_rg_v2

# Run resume generation pipeline with candidate brief
python -m apps_rg.entrypoints.cli --profile data/fixtures/executive_candidate.json

# Execute unit and integration tests
pytest tests/
```

### 3. Run the Outreach Engine (`outreach_engine`)
```bash
cd outreach_engine

# Run the live executive outreach demo
python -m outreach_engine --demo

# Ingest a real-world mission fixture (e.g. Truist executive outreach)
python -m outreach_engine --brief data/fixtures/charles_truist_mission.json

# Execute unit and validation tests
pytest tests/
```

### 4. Run the Evaluation Lab (`apps_eval`)
```bash
# Run model and rubric benchmarks across scenarios
python -m apps_eval --suite smoke
```

---

## The Monolith Retirement & Modernization Notice

In September 2026, this repository underwent an extensive forensic audit to eliminate technical debt and over-engineered abstractions:

- **Eradicated Legacy Monolith:** The legacy `agentic_core/` (3,711 files) and `apps_shared/` (284 files) frameworks were permanently decommissioned, along with ~2,700 obsolete tests.
- **Retired Prototypes:** Legacy `apps_rg/`, `apps_lic/`, `apps_qna/`, and `apps_underwriting_ai/` were purged.
- **Embraced Modern Subsystems:** All capabilities were refactored into high-velocity, modular v2 engines (`apps_rg_v2`, `outreach_engine`) with self-contained dependencies, pristine type contracts, and zero framework overhead.

---

## Public Positioning Index

- [Executive Overview](docs/EXECUTIVE_OVERVIEW.md) — Strategic positioning for CTOs, CISOs, and SVPs of Engineering.
- [Recruiter & Hiring Guide](docs/RECRUITER_GUIDE.md) — Plain-English explanation of technical leadership competencies demonstrated.
- [Runtime Control Plane Narrative](docs/RUNTIME_CONTROL_PLANE.md) — In-depth breakdown of route authority, write gateways, and replayability.
- [SVP Engineering Review](docs/SVP_ENGINEERING_GOVERNANCE_README.md) — Multi-tier governance, AST graph analysis, and compliance proof commands.

---

## Summary

This repository is **not** a collection of toy prompts or unconstrained chatbots. It is an **architectural statement and working reference design** demonstrating that the future of enterprise AI lies in **rigorous systems engineering, deterministic control planes, and verified software execution**.

**AI that behaves like software, not experiments.**

— **[Amit Ayer](https://github.com/Siamese001)**, SVP-level Agentic Engineer
