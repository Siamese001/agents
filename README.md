# Agentic Intelligence Engine

[![Status](https://img.shields.io/badge/Status-Production-success.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-Governed%20Agentic-blue.svg)](#)
[![Integrity](https://img.shields.io/badge/Integrity-Zero%20Drift-purple.svg)](#)

> **Building AI that behaves like enterprise software—deterministic, auditable, and resilient.**

This repository contains the core Agentic Intelligence Engine, a suite of cleanly decoupled, production-ready AI services. The platform is designed from the ground up for **SVP-level risk management**, prioritizing factual grounding, strict execution bounds, and architectural governance over raw stochastic output.

---

## 🏛️ Enterprise Engineering Invariants

Engineering leadership demands **guarantees**, not promises. This codebase enforces four strict architectural invariants across both compile time and runtime:

### 1. Factual Assertion Knowledge Graph (Zero Hallucination)
- **Graph-Led Authority**: The engine evaluates candidate claims against deeply curated, multi-node factual evidence clusters.
- **Forbidden Claims Guard**: Output generators pass through strict assertion checkers that reject unverified metrics, unearned titles, or fabricated achievements *before* any data reaches the write gateway.

### 2. Bounded Socratic Iteration (Cost & Latency Ceilings)
- **Deterministic Step Caps**: Agent-to-agent self-correction loops are hard-capped at bounded iterations to prevent runaway execution costs.
- **Fail-Closed Convergence**: If an agent fails to meet rubric thresholds within its allocated turn quota, the system falls back to a deterministic, pre-certified safe output rather than returning unverified model emissions.

### 3. Universal Write Gateway (UWG)
- **Single-Door Commit**: No agent or tool can directly mutate filesystem storage, caches, or external databases. 
- **Atomic Admission**: State mutations must be proposed as typed payloads, evaluated by runtime exit gates, and committed through the Universal Write Gateway with cryptographic provenance seals.

### 4. Strict Layer Separation
- **Compile-Time Drift Elimination**: A custom dependency graph maps every module import, function fanout, and cross-layer call to prevent architectural decay.
- **Clean Boundaries**: Strict separation between Reasoning, Routing, Execution, and Verification ensures the system scales predictably across engineering teams.

---

## ⚙️ Production Subsystems

The repository is organized into independent, highly cohesive engines:

| Subsystem | Mission & Architecture | Key Technical Primitives | Status |
| :--- | :--- | :--- | :---: |
| [`resume_graph_engine/`](resume_graph_engine/) | **Autonomous Career & Skill Intelligence Engine**<br>Constructs mathematically grounded, hallucination-proof executive resumes matching target job descriptions. | • Factual Assertion Graph<br>• Dense + BM25 Reciprocal Rank Fusion<br>• Multi-Judge Proof Panels | **Production** |
| [`outreach_engine/`](outreach_engine/) | **Autonomous Lifecycle & Outbound Intelligence**<br>Orchestrates hyper-personalized executive engagement, briefing airlocks, and multi-touch cadence sequencing. | • Adversarial Briefing Injection Airlock<br>• Forbidden-Claims Linting<br>• Multi-Touch State Machine | **Production** |
| [`apps_research/`](apps_research/) | **Grounded Deep Research Substrate**<br>Autonomous company profiling, competitive intelligence, and executive dossier synthesis. | • Local Search Integration<br>• Autonomous Dossier Extractor<br>• Grounded Evidence Collector | **Active** |
| [`apps_eval/`](apps_eval/) | **Evaluation Lab & Model Benchmark Surface**<br>Rigorous offline grading, metric delta ratcheting, and multi-dimensional LLM judge calibration. | • Automated LLM Graders & Rubrics<br>• Regression & Mutation Test Suites<br>• CI Ratcheting | **Active** |
| [`apps_exec/`](apps_exec/) | **Executive Brief & Narrative Synthesizer**<br>Condenses multi-source organizational signals into Board-level strategic summaries. | • Structural Blueprint Schemas<br>• Context Compression | **Active** |
| [`apps_architect/`](apps_architect/) | **Architecture Governance Engine**<br>Enforces compile-time architectural integrity across all platform code. | • Static Dependency Graph<br>• Anti-Pattern Burndown<br>• Write Bypass Detectors | **Core Gate** |

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11+ (tested on 3.11 and 3.12)
- Git

### 1. Clone & Environment Setup
```bash
git clone https://github.com/Siamese001/agents.git
cd agents

# Initialize virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1   # On POSIX: source .venv/bin/activate

# Install dependencies in editable mode
pip install -e .
```

### 2. Run the Resume Graph Engine (`resume_graph_engine`)
```bash
cd resume_graph_engine

# Run the canonical product pipeline (Anthropic JD + Base Resume)
python -m apps_rg run

# Execute the offline evaluation suite
pytest tests/unit/apps_rg/evals/test_c03_owner_solo_qrel.py
```

### 3. Run the Outreach Engine (`outreach_engine`)
```bash
cd outreach_engine

# Run live executive outreach synthesis
python -m outreach_engine --demo
```

### 4. Verify Architectural Gates
```bash
# Run the platform deterministic validation suite
pytest tests/
```

---

## 📖 Executive & Leadership Reading Guide

For technical hiring executives, hiring managers, and architecture evaluators:

- 🧭 [**Executive Overview**](docs/EXECUTIVE_OVERVIEW.md) - Strategic positioning on route authority, write controls, and board-level risk management.
- 🎯 [**Recruiter & Hiring Manager Guide**](docs/RECRUITER_GUIDE.md) - Mapping of codebase architecture to SVP Engineering, Head of AI Platform, and Principal AI Architect competencies.
- 🔐 [**Runtime Control Plane Specification**](docs/RUNTIME_CONTROL_PLANE.md) - Detailed breakdown of the control plane and Universal Write Gateway.
- 🛡️ [**SVP Engineering Governance Guide**](docs/SVP_ENGINEERING_GOVERNANCE_README.md) - Concrete proof points on AST graph analysis, zero-drift shadow learning, and compliance auditing.

---

## 👤 Author & Leadership Profile

**Amit Ayer**  
*SVP-Level AI Engineering Leader | Platform Architect for Governed Enterprise AI*  
[GitHub Profile](https://github.com/Siamese001)

> *"Building AI that behaves like enterprise software - deterministic, auditable, and resilient."*
