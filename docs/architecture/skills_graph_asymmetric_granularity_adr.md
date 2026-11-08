# ADR: Asymmetric Granularity Architecture for Skills Graph Database

**Document Type**: Architecture Decision Record (ADR)  
**Status**: Accepted  
**Date**: 11/08/2026  
**Context**: Cross-Repository Comparison (`agents` vs. `decision-intelligence-engine`)  
**SSOT Invariant**: `INV-PROJECTION-PURITY`, `INV-MANIFEST-FRESHNESS`  

---

## 1. Context & Problem Statement

The `agents` repository maintains a skills and competency knowledge graph database (`augmented_skills_graph.sqlite`) utilized by `resume_graph_engine` (Apps RG), outreach routing, and cross-agent execution. Concurrently, the sibling `decision-intelligence-engine` (DIE) repository maintains a daily meeting knowledge graph (`graph.sqlite`) capturing spoken claims, stakeholders, decisions, and temporal commitments from continuous meeting transcripts.

The architectural question was raised: **Should the agent repository skills graph database exhibit the same level of granularity in how nodes, assertions, confidence, evidence, and lineage are generated and updated as the Decision Intelligence Engine (DIE) graph?**

Because updates in the `agents` repository are milestone-driven and curated rather than daily unconstrained audio streams, applying symmetric operational machinery would introduce severe maintenance churn, latency, and fragility.

---

## 2. Decision: Asymmetric Granularity

We adopt an **Asymmetric Granularity** standard:
1. **Semantic Representation Granularity (Data Model)**: **Full Parity with DIE.** The skills graph maintains strict, granular semantic identity for typed nodes, structured assertions, discrete calibrated confidence tiers, and cryptographic multi-point evidence bindings.
2. **Operational Machinery Granularity (Lifecycle & Updates)**: **Complete Divergence from DIE.** The skills graph rejects DIE's daily background maintenance swarms, continuous ten-agent freshness panels, runtime `BEFORE UPDATE` SQL triggers, time-travel history tables, and dynamic alias redirect resolvers.

```
+---------------------------------------------------------------------------------------------------+
|                                 ARCHITECTURAL DEFENSE MATRIX                                      |
+-------------------+-----------------------------+-------------------------------+-----------------+
| Dimension         | DIE Approach (Daily Stream) | Agents Approach (Milestone)   | Decision        |
+-------------------+-----------------------------+-------------------------------+-----------------+
| 1. Nodes          | Dynamic entities + Aliases  | Curated typed vocabulary      | Match Schema;   |
|                   | + Runtime entity_redirect   | Git SSOT; Zero redirects      | Omit Redirects  |
+-------------------+-----------------------------+-------------------------------+-----------------+
| 2. Assertions     | First-class table with      | Edge assertions with basis    | Match Semantics;|
|                   | SUPERSEDED/RETRACTED rows   | Purely active clean snapshot  | Omit Dead Rows  |
+-------------------+-----------------------------+-------------------------------+-----------------+
| 3. Confidence     | Continuous float (0.0–1.0)  | Calibrated discrete tiers     | Reject Float;   |
|                   | Dynamic speech drift        | (HIGH, MEDIUM, LOW, UNSCORED) | Enforce Tiers   |
+-------------------+-----------------------------+-------------------------------+-----------------+
| 4. Evidence       | Multi-point quote binding   | Multi-point quote binding     | Strict Parity   |
|                   | Text span + audio link      | Source doc + SHA-256 digest   | (Non-Negotiable)|
+-------------------+-----------------------------+-------------------------------+-----------------+
| 5. Lineage        | SQL BEFORE UPDATE triggers  | Git revision SHA + SHA-256    | Reject Triggers;|
|                   | Database history tables     | input_manifest_digest         | Git-Native SSOT |
+-------------------+-----------------------------+-------------------------------+-----------------+
| 6. Maintenance    | 10-Agent Freshness Swarm    | Delta Proposal Ingestion Lane | Reject Swarms;  |
|                   | Daily harm-ranked planner   | Deterministic Materializer    | One-Shot Build  |
+-------------------+-----------------------------+-------------------------------+-----------------+
```

---

## 3. Detailed Architectural Principles

### 3.1 Node Identity & Controlled Vocabulary
- Entity types are strictly typed: `skill`, `fact`, `metric`, `role_episode`, `career_epoch`.
- Identifiers are canonical and immutable (e.g. `skill_governed_agentic_systems_architecture`, `fact_slalom_001`).
- All deduplication occurs upstream in source JSON ledgers under Git review. Runtime alias redirect tables (`entity_redirect`) are prohibited to eliminate recursive lookup overhead during graph traversal.

### 3.2 Assertion Semantics & Active-Only Snapshots
- Edge assertions explicitly declare `assertion_type` (`STRUCTURAL_CONTAINMENT`, `TAXONOMIC_ATTRIBUTION`, `EVIDENTIAL_SUPPORT`, `POLICY_ELIGIBILITY`, `METRIC_BINDING`) and `assertion_basis` (`evidence_reference`, `taxonomy_rule`, `policy_predicate`).
- The compiled SQLite database stores **strictly active, confirmed assertions**. Historical supersession is governed by Git revision history, avoiding runtime `WHERE status = 'CONFIRMED'` filtering overhead and eliminating obsolete claim retrieval.

### 3.3 Calibrated Discrete Confidence Tiers
- Rather than continuous decimal scores (e.g. `0.81` vs `0.82`) that introduce prompt fluttering and ranking instability, the skills graph enforces discrete tiers:
  - `HIGH` (>= 85%): Primary direct production proof, signed Git commits, or confirmed client engagements.
  - `MEDIUM` (50%–84%): Secondary domain transferability or pattern similarity.
  - `LOW` (< 50%): Exploratory claims requiring human-in-the-loop confirmation.

### 3.4 Cryptographic Evidence Grounding (Non-Negotiable Parity)
- Every edge asserting evidential support must join to `edge_evidence` specifying:
  - `evidence_ref`: Canonical fact or metric identifier.
  - `source_doc`: Exact repository file path.
  - `span`: Line and byte range.
  - `quote_sha256`: Cryptographic SHA-256 digest of the exact quoted text.

### 3.5 Lineage & Compilation Invariants
- Lineage is tracked cryptographically via `graph_build_runs` and `graph_metadata`:
  - `input_manifest_digest`: SHA-256 digest across all source JSON ledgers and bundles.
  - `builder_git_commit`: The exact Git commit SHA used to compile the projection.
- In-database version history tables and `BEFORE UPDATE` SQL triggers are prohibited.

---

## 4. Governance Invariants

1. **`INV-PROJECTION-PURITY`**: `augmented_skills_graph.sqlite` is strictly a derived, disposable compiled projection. It is read-only during agent traversal. Direct out-of-band writes or runtime mutations are blocked.
2. **`INV-MANIFEST-FRESHNESS`**: Graph runtime loaders must verify `input_manifest_digest` before query execution. If any underlying ledger file changes without compilation, the system fails closed.
3. **`INV-NO-AUTONOMOUS-MUTATION`**: Background daemon threads, automated freshness swarms, or continuous heuristic healers must not mutate graph tables outside a Git pull request.
