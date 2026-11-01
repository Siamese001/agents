# Verified Document & Dossier Synthesis Engine (`resume_graph_engine` · `apps_rg`)

> **Reference Enterprise Workload: Graph-Grounded Document Synthesis & Multi-Judge Proof Panels**  
> Demonstrates zero-hallucination structured document generation using a 38-cluster Factual Assertion Graph (`C0.3`), hybrid dense BGE-M3 + BM25 Reciprocal Rank Fusion, and a 6-wave offline evaluation surface (`G1`–`G6`).

---

## Architectural Role in the Platform

Structured executive and technical dossier synthesis requires strict factual attribution: every quantitative claim, scope statement, and capability assertion must trace to an authoritative evidence node before emission.

This reference workload exercises five core control-plane primitives:

- **Factual Assertion Knowledge Graph (`C0.3`)**: Every synthesized claim is validated against 38 curated multi-node evidence clusters, mechanically preventing ungrounded generative assertions.
- **Hybrid Neural & Lexical Retrieval (`RRF`)**: Fuses dense BGE-M3 vector embeddings with deterministic BM25 lexical rankings via Reciprocal Rank Fusion, rehydrating assertion identifiers through graph authority constraints before section allocation.
- **Layered Control-Plane Pipeline (`U0 → L1 → L0 → C0 → PA → L2 → Exit`)**: Executes bounded planning capsules, section-level synthesis, multi-judge proof panels, and cryptographic execution receipts.
- **Six-Wave Offline Evaluation Surface (`G1`–`G6`)**: Enforces modular graph grounding metrics, whole-document rubric grading, stored-run repeatability, and critical-grader mutation testing under `src/apps_rg/evals`.
- **Protocol-Driven Storage Isolation**: Domain synthesis and pipeline services operate on pure protocol abstractions with zero direct database or filesystem driver imports.

---

## Canonical Execution Surface

The sole public module command is:

```bash
python -m apps_rg run
```

It executes the full governed flow, including evaluation gates, `L6` shadow evidence emission, and terminal execution receipt sealing. The `eval` action verifies a completed run without a provider call, and `show` prints a stored verified output. See [`docs/APPS_RG_V2_CANONICAL_ENTRYPOINTS.md`](docs/APPS_RG_V2_CANONICAL_ENTRYPOINTS.md) for contract details.

### Running the Offline Evaluation & Contract Suites

```bash
# Execute the G1-G6 offline evaluation suite
pytest resume_graph_engine/tests/unit/apps_rg/evals/ -v --timeout=60

# Verify public CLI surface and fail-closed entrypoint guards
pytest resume_graph_engine/tests/unit/apps_rg/test_public_cli_surface.py -v --timeout=60
```

---

##Provenance & Audit Artifacts

- [`C03_EMBEDDING_PRODUCTION_PROMOTION.md`](C03_EMBEDDING_PRODUCTION_PROMOTION.md) — Production promotion runbook and cluster-embedding retirement audit context.
- [`MIGRATION_PROVENANCE.md`](MIGRATION_PROVENANCE.md) & [`SOURCE_SYNC_RECEIPT.json`](SOURCE_SYNC_RECEIPT.json) — Cryptographic source synchronization provenance records.
