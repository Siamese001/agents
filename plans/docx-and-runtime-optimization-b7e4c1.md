# Word Document OpenXML Repair & Sub-7-Minute Runtime Optimization Plan

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Repair Word `.docx` ECMA-376 OpenXML schema ordering and package completeness | COMPLETE |
| Wave 2 | Eliminate self-consistency and X1D judge output-token truncation cascades | COMPLETE |
| Wave 3 | Enable compacted-prompt prefix caching, patch-run boundary parity, and parallel Wave-2 scheduling | COMPLETE |
| Wave 4 | Preserve claim-binding text in coherence evidence compaction and author SVP-rich allocation surface phrases | COMPLETE |

## Wave 1: Word Document OpenXML Schema & Package Repair

### Objective & Scope
Fix the `.docx` corruption in `resume_graph_engine/src/apps_rg/runtime/final_resume_docx.py` so Microsoft Word, Apple Pages, and OpenXML readers open `resume.docx` cleanly, and regenerate `resume.docx` for `full_resume_a4ada2b8be99`.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/final_resume_docx.py`: Order `<w:pPr>` child elements strictly per ECMA-376 `CT_PPrBase` (`w:pStyle` -> `w:keepNext` -> `w:pBdr` -> `w:spacing` -> `w:ind` -> `w:jc`) in `_STYLES_XML` and package the document inside a complete `python-docx` OpenXML container (`docProps/core.xml`, `docProps/app.xml`, `word/settings.xml`, `word/webSettings.xml`, `word/fontTable.xml`, `word/styles.xml`, `word/document.xml`).
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_final_resume_outputs.py`: Add unit tests asserting `docx.Document(docx_path)` opens without error, all required OpenXML package parts exist, and every `<w:pPr>` in `word/styles.xml` and `word/document.xml` obeys ECMA-376 child ordering.
- `[MODIFY]` `resume_graph_engine/artifacts/apps_rg/runtime_proofs/full_resume_a4ada2b8be99/outputs/resume.docx`: Re-export valid `.docx` from the finalized spine JSON.

### Acceptance Criteria
- `docx.Document` loads `resume.docx` and parses all paragraphs and styles without exception.
- Every `<w:pPr>` element in `word/styles.xml` and `word/document.xml` satisfies strict `CT_PPrBase` sequence order.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_final_resume_outputs.py -v --timeout=60`
- **Input:** Finalized spine JSON in `resume_graph_engine/artifacts/apps_rg/runtime_proofs/full_resume_a4ada2b8be99/modular_r4/final_resume_assembly/final_resume.json`.
- **Expected:** Exit code `0`, all tests pass, and `outputs/resume.docx` opens cleanly via `docx.Document`.
- **Verify independently:** Inspect `zipfile.ZipFile` namelist and XML child order of `<w:pPr>` nodes in `outputs/resume.docx`.
- **Fail if:** Any `<w:pPr>` places `w:jc` or `w:ind` before `w:spacing`, or `docx.Document` raises an exception.
- **Record:** `artifacts/governance/wave1_docx_repair_receipt.json`

## Wave 2: Self-Consistency & Judge Output-Token Headroom

### Objective & Scope
Eliminate the 30–36s first-attempt `max_tokens` truncation cascades in `competencies` self-consistency generation and in `standard_reasoning` / `bullet_rewrite_quality` X1D proof judges.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/sections/competencies_lane_defaults.py`: Raise `DEFAULT_COMPETENCIES_SC_OUTPUT_TOKENS` from `4096` to `8192` and `COMPETENCIES_MAX_OUTPUT_TOKENS` from `6000` to `8192` to match `section_l2_authority.py` (`8192`).
- `[MODIFY]` `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml`: Raise `max_output_tokens` from `4096` to `8192` for `standard_reasoning` and `bullet_rewrite_quality` under `runtime_limits.judge.runtime_profiles` so high-thinking proof judges do not truncate at ~4,080 tokens on Attempt 1.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_competencies_transport_orchestration_w1_w6.py`: Update token budget assertions for `8192` SC output headroom.

### Acceptance Criteria
- `competencies_self_consistency_output_tokens()` resolves to `8192` by default.
- `standard_reasoning` and `bullet_rewrite_quality` judge runtime profiles resolve `max_output_tokens == 8192` on Attempt 1 while preserving tier monotonicity.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_competencies_transport_orchestration_w1_w6.py resume_graph_engine/tests/unit/apps_rg/test_section_judges_and_gates_consistency_redteam.py -v --timeout=60`
- **Input:** `provider_profiles.yaml` and `competencies_lane_defaults.py`.
- **Expected:** Exit code `0` with all unit and red-team consistency assertions passing.
- **Verify independently:** Query `get_section_judge_policy("competencies").judge_runtime_profile.resolved_max_output_tokens(attempt=1) == 8192`.
- **Fail if:** Any judge tier monotonicity test fails or `competencies` SC default remains below `8192`.
- **Record:** `artifacts/governance/wave2_token_headroom_receipt.json`

## Wave 3: Prefix Caching, Patch-Run Boundary Parity & Parallel Wave Scheduling

### Objective & Scope
Enable ephemeral prefix caching on compacted `competencies` SC prompts, enforce runtime boundary environment bootstrap in `execute_patch_run`, and align `section_execution_plan.py` with `workflow_manifest.resume_sections.v1.yaml` so `executive_summary` and `headline` execute concurrently in Wave 2.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/providers/anthropic_section_cache_payload.py`: Recognize `COMPETENCIES_SC_COMPACT_SYSTEM_MARKER` as a valid compacted `tier1_stable` system block when `compiled_prompt_artifact` slots are uncompacted.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/orchestration/patch_run.py`: Call `configure_apps_rg_runtime_boundary(repo_root=plan.repo)` in `execute_patch_run` so `APPS_RG_ANTHROPIC_PROMPT_CACHE=1` and parallel flags are active during patch runs.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/section_execution_plan.py`: Align `headline` dependencies with `workflow_manifest.resume_sections.v1.yaml` (depend on Wave 0/1 upstream sections rather than `executive_summary`) so `executive_summary` and `headline` run in parallel in Wave 2.
- `[MODIFY]` `.agents/skills/agents-domain-assurance/SKILL.md`: Codify the `/learn` guardrails for OpenXML `CT_PPrBase` ordering and reasoning token headroom.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/runtime/providers/test_section_provider_anthropic_cache.py`: Add unit test verifying compacted `competencies` SC messages emit `cache_marker_count >= 1` and `cache_enabled is True`.

### Acceptance Criteria
- `build_anthropic_section_cache_payload` marks compacted `competencies` SC system prompts with ephemeral cache control (`cache_marker_count == 1`).
- `execution_waves_for_lanes(GENERATED_CONTENT_LANES)` schedules `executive_summary` and `headline` together in the final wave.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/runtime/providers/test_section_provider_anthropic_cache.py resume_graph_engine/tests/unit/apps_rg/test_perf_waves_sync.py -v --timeout=60`
- **Input:** Compacted `competencies` SC messages and `GENERATED_CONTENT_LANES` schedule.
- **Expected:** Exit code `0`, cache markers enabled on compacted SC prompts, and Wave 2 co-schedules `executive_summary` + `headline`.
- **Verify independently:** Verify `execution_waves_for_lanes(GENERATED_CONTENT_LANES)[-1] == ("executive_summary", "headline")` and `validate_turn_gates.py --mode all` passes.
- **Fail if:** Compacted `competencies` SC prompt falls back to `pa_compiled_system_fallback_uncached_v1` or `headline` blocks on `executive_summary`.
- **Record:** `artifacts/governance/wave3_caching_parallelism_receipt.json`

## Wave 4: Whole-Resume Coherence Evidence Binding & Competency Surface Recovery

### Objective & Scope
Preserve truncated `visible_claim_text` and `claim_source_fact_ids` inside `compact_evidence_packet_for_prompt` so whole-resume coherence judges can verify child-fact claim bindings in `executive_summary`, and register graph-bound SVP-rich surface compositions for the five Brown & Brown competency allocation pairs in `_ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS`.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/assembly/coherence_prompt_compact.py`: Retain truncated `visible_claim_text` and `claim_source_fact_ids` in `bindings_compact` so `DISPLAY_OVERRIDE` and child-fact bindings remain visible to the coherence judge panel.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/c0/competencies_graph_authority.py`: Add/update source-bound 6-word compositions in `_ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS` for `skill_risk_data_aggregation_bcbs239`, `skill_credit_adjudication_default_risk`, `skill_p2_gtm_solution_mapping`, `skill_p2_tech_ibm_cloud_portfolio_anchor`, and `skill_p2_tech_reference_architecture`.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py`: Assert `compact_evidence_packet_for_prompt` retains `visible_claim_text` on `graph_claim_bindings` and all Brown & Brown allocation pairs resolve to SVP-rich phrases.

### Acceptance Criteria
- `compact_evidence_packet_for_prompt` preserves `visible_claim_text` and `claim_source_fact_ids` on `graph_claim_bindings`.
- All 8 Brown & Brown competency allocation assignments resolve to clean, human-readable 6-word SVP phrases without fallback token-soup concatenation.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py -v --timeout=60`
- **Input:** `full_resume_11773d943c97` competency allocation plan and coherence evidence packet.
- **Expected:** Exit code `0`, all unit tests pass, and `patch_run` on `full_resume_11773d943c97` achieves `full_resume_coherence_pass=true` (`decisive_status=PASS`).
- **Verify independently:** Inspect `x1d_full_resume_judge_outputs.json` (`quorum_pass == True`, `mean_normalized_score >= 0.80`) and `outputs/resume.docx`.
- **Fail if:** Any allocation surface phrase falls back to token-soup synthesis or whole-resume coherence quorum fails.
- **Record:** `artifacts/governance/wave4_coherence_surface_receipt.json`
