---
name: agents-domain-assurance
description: Consolidated E2E pipeline and hybrid retrieval assurance across outreach_engine, resume_engine, resume_graph_engine, and apps_research.
---

# Agents Domain, Retrieval & Rubric Surface Assurance (On-Demand)

Consolidates `agents-outreach-resume-functionality`, `agents-research-retrieval-surface`, and `agents-evals-judge-assurance` into a single behavioral, fail-closed on-demand workflow (zero daily background schedules).

## Execution Protocol

1. **Preflight Behavioral Auditors & Full Dual-Engine Sweep (11 Roots / 5 Config Roots / 314 Data Files)**:
   Never fast-exit on `verify_commit.py` alone or skip resume tailoring (`run_e2e_authoritative_smoke.py` executes both Outreach and deterministic 11-stage Resume by default). Run every dedicated domain auditor in read-only mode so tracked `reports/` remain clean:
   ```bash
   .venv/bin/python tools/e2e_functionality_auditor.py --read-only --json
   .venv/bin/python tools/retrieval_surface_auditor.py --read-only --json
   .venv/bin/python tools/validate_eval_rubrics.py --json
   .venv/bin/python ops_scripts/run_e2e_authoritative_smoke.py --read-only
   .venv/bin/python tools/verify_graph_integrity_and_embeddings.py
   .venv/bin/python tools/run_resume_graph_traversal_probe.py --max-paths 200
   .venv/bin/python tools/verify_pipeline_latency_caching.py
   .venv/bin/python tools/verify_release_gate.py --no-write --json
   .venv/bin/pytest tests/unit/test_e2e_and_retrieval_full_parity.py tests/unit/test_evals_and_budget_full_parity.py outreach_engine/tests -q --timeout=60
   ```
   If all 8 behavioral gates exit `0` (`B_total == 0`), exit immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating empty branches or synthetic wave plans.

2. **Interactive Remediation Quota (`INV-REMEDIATION-QUOTA-FLOOR`)**:
   When `B_total > 0`, provision an isolated worktree via `.venv/bin/python tools/pr_governance.py start`, remediate at least `Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` production defects, and include the 7-column Before/After Defect Accounting Table.

3. **Executive Summary 6-Sentence Synthesis Calibration (`executive_summary_synthesis_calibration`)**:
   Interactive IDE (`ide_argon4_routing_policy`) and C-suite generation must strictly match the external 8-slot prompt assembly (`compile_executive_summary_prompt` + `executive_summary.generate_scratch_v1.yaml`):
   - **Thesis-First 6-Sentence Arc (`110–148` words, hard cap `150`)**: `S1` present-tense leadership thesis (`<=1` mechanism) -> `S2` governed platform architecture (`<=2` mechanisms) -> `S3–S4` connective bridges (`<=2` stock openers) weaving verified scale/governance metrics -> `S5` woven `FSA-chartered` quantitative rigor -> `S6` forward-modal capstone.
   - **Zero Backward-Looking Title Stacking or Mail-Merge**: Never emit `"former CTO"`, `"former SVP"`, `"Big-4 Principal"`, `"past principal"`, `"past CTO"`, or target-company mail-merge in the summary paragraph; verify all 7 `executive_summary_x2` gates before output.
   - **Header Portfolio & Domain-Routed Graph Competencies**: The top contact bar must always include `github.com/Siamese001/agents` (`phone | email | linkedin | github`) and omit city/state (`Boca Raton, FL`) to avoid geographic screening bias on national mandates. Section 2 (`CORE COMPETENCIES`) must route `ccb_insurance_domain_erm` (`FSA`, `Solvency II`, `AG43`, carrier/brokerage modernization) for insurance/strategy JDs (`Brown & Brown`, `AIG`) instead of emitting a domain-blind agentic plumbing dump.
   - **Single Canonical Pipeline & 5-Role Structure (`INV-SINGLE-CANONICAL-PIPELINE`)**: Execute all resume generation, whole-resume graph allocation (`build_whole_resume_graph_allocation` with `DEFAULT_MAX_CANDIDATES_PER_SLOT = 256` and `executive_summary` `metric_outcome` retention in `compute_career_band_filter`), flattening (`flatten_final_resume_to_text`), and styled OpenXML `.docx` rendering (`final_resume_docx.export`) strictly through `emit_final_resume_product_outputs`. Enforce standard executive headings (`EXECUTIVE SUMMARY`, `CORE COMPETENCIES`, `PROFESSIONAL EXPERIENCE`, `EDUCATION`, `CERTIFICATIONS`), 2 `InsurTech` bullets (`bul_insurtech_001`, `bul_insurtech_002`), and consolidated `Ernst & Young / Early Career Roles` (`exp_early_career_001`, 0 EY bullets).

4. **Cross-Repo Graph Retrieval & SQLite Write Custody Invariants**:
   - **Native SQLite FTS5 Keyword Index**: `augmented_skills_graph.sqlite` materializes `graph_nodes_fts` (`fts5(node_id UNINDEXED, node_type UNINDEXED, label, description)`) paired with `sqlite_fts5_bm25_rank()` for sub-millisecond sparse ranking before RRF fusion (`fuse_dense_bm25`).
   - **1024-d L2-Normalized Research Embeddings**: `InMemoryResearchStore` in `apps_research/engines/research_retrieval_engine.py` must emit `1024`-dimensional L2-normalized (`norm == 1.0 ± 1e-4`) vectors grounded in the local `360`-vector BGE-M3 `unit_vectors` corpus rather than 10-element hash slices.
   - **Five-Check Physical SQLite Write Proof & Non-Mock E2E Gate**: `_replace_sqlite_projection_if_unchanged()` and `_open_c03_graph_sqlite_read_snapshot()` enforce `verify_sqlite_physical_write_proof()` (file size/SHA-256, `SQLite format 3\x00` header magic, isolated `PRAGMA integrity_check == ok`, isolated `mode=ro` `PRAGMA query_only=ON`, and positive `graph_nodes`/`graph_edges` row counts), verified end-to-end by `ops_scripts/run_e2e_authoritative_smoke.py --read-only`, `tools/e2e_functionality_auditor.py --read-only --json`, and `tools/retrieval_surface_auditor.py --read-only --json`.

5. **Outreach Engine (`apps_lic`) Non-Mock E2E Edge-Case Invariants**:
   - **Research Bridge & Canonical Sidecar Persistence**: Always exercise `GovernedBriefingResolver.resolve` and `execute_managed_research` with a real `artifact_runs_root` directory and the production `AppsResearchBridge` (never `MockAppsResearchBridge` alone) to verify `CANONICAL_FIXTURE` (`is_verified=True`), `x2_judge_receipt` exit gates (`G21`/`G26`/`X2`), standalone fallback receipts (`G5`/`G6`/`G7`), and `trace_id` parity.
   - **Channel Routing, Follow-Up Grounding & Connection-Note Trimming**: Verify that `BOARD_MEMBER` connection notes auto-upgrade to `inmail` in both `TouchSequencePlanner` and `generate_single_draft`, `FOLLOW_UP` single drafts weave `strategic_priorities` to pass Lens 2 (`>= 0.70`), and connection-note trimming preserves grounded metric tokens without double ellipsis (`"......"`).
   - **Validator & CLI Parity**: Verify that `OutreachOrchestrator.validate_draft` enforces `OutboundPrivacyValidator`, `ForbiddenClaimsValidator` normalizes grounded dollar tokens (`$10M` == `$10,000,000`) while blocking 1-digit/4-digit bonus/retainer demands, and CLI `cmd_run --brief --role` preserves `candidate.target_title`.
   - **Red-Team Adversarial Boundary Hardening (59 Breakages / 70 Non-Mock Tests)**: Verify null-safe CLI/validator coercion (`None`/empty inputs), symlink/path-traversal containment in `MissionLoader` and `persist_standalone_outreach_research_bundle`, `NaN`/`Inf` numeric sanitization in `ExecutiveOutreachJudgePanel` and `ModelRegistry`, fail-closed `u0_receipt_sha256` verification in `managed_research_delegation`, and explicit unsealed resolution blocking in `UnsupportedPersonalizationValidator`.

6. **Live Non-Mocked Resume Engine Pre-Run Checklist**:
   - Verify all 11 canonical resume sections (`headline`, `executive_summary`, `competencies`, `slalom_bullets`, `slalom_narrative`, `unify_bullets`, `unify_narrative`, `ibm_bullets`, `ibm_narrative`, `insurtech_bullets`, `insurtech_narrative`) are registered in both `section_retrieval_profile.yaml` and `provider_profiles.yaml`.
   - Verify `configure_apps_rg_runtime_boundary(repo_root=Path("resume_graph_engine").resolve())` resolves shared-data symlinks (`artifacts/models/BAAI/bge-m3`) via `is_within_trusted_checkout`.
   - Before launching an 11-lane live run, execute a 1-token live probe against all proof-eligible X1D judge providers (`gemini_pro` and `openai_chatgpt`) to detect account-level monthly spend caps (`HTTP 429 RESOURCE_EXHAUSTED`) early.

7. **Local MacBook (Apple Silicon MPS / Metal) Runtime & Zero-CUDA Assurance**:
   - Verify zero CUDA dependencies or configurations exist in manifests or lockfiles (`uv lock --check`).
   - Run dedicated standalone MacBook runtime tests: `PYTHONPATH="resume_graph_engine/src:." .venv/bin/pytest tests/macbook_runtime/ -v --timeout=60`.
   - Run local operational benchmark harness asserting zero memory leaks and temporal drift: `PYTHONPATH="resume_graph_engine/src:." .venv/bin/python tools/benchmark_macbook_runtime.py --iterations 10 --assert-gates`.
