# Word Document OpenXML Repair & Sub-7-Minute Runtime Optimization Plan

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Repair Word `.docx` ECMA-376 OpenXML schema ordering and package completeness | COMPLETE |
| Wave 2 | Eliminate self-consistency and X1D judge output-token truncation cascades | COMPLETE |
| Wave 3 | Enable compacted-prompt prefix caching, patch-run boundary parity, and parallel Wave-2 scheduling | COMPLETE |
| Wave 4 | Preserve claim-binding text in coherence compaction and author SVP-rich competency surfaces | COMPLETE |
| Wave 5 | Harden coherence judge negative-assertion filter and dimension-gated blocker promotion | COMPLETE |
| Wave 6 | Remove literal HEADLINE label, update GitHub URL, and de-clunk executive summary synthesis | COMPLETE |

## Wave 1: Word Document OpenXML Schema & Package Repair

### Objective & Scope
Fix `.docx` corruption in `final_resume_docx.py` so Word and OpenXML readers open `resume.docx` cleanly.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/final_resume_docx.py`: Order `<w:pPr>` child elements per ECMA-376 `CT_PPrBase` inside a 10-part `.docx` package.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_final_resume_outputs.py`: Assert `docx.Document` loads cleanly and `<w:pPr>` obeys ECMA-376 ordering.

### Acceptance Criteria
- `docx.Document` loads `resume.docx` cleanly and all `<w:pPr>` elements satisfy `CT_PPrBase` order.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_final_resume_outputs.py -v --timeout=60`
- **Input:** Finalized spine JSON in `final_resume.json`.
- **Expected:** Exit code `0` and valid `.docx` package.
- **Verify independently:** Inspect `zipfile.ZipFile` namelist and `<w:pPr>` child order.
- **Fail if:** Any `<w:pPr>` violates `CT_PPrBase` order or `docx.Document` raises.
- **Record:** `artifacts/governance/wave1_docx_repair_receipt.json`

## Wave 2: Self-Consistency & Judge Output-Token Headroom

### Objective & Scope
Eliminate first-attempt `max_tokens` truncation cascades in `competencies` SC generation and X1D proof judges.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/sections/competencies_lane_defaults.py`: Raise `DEFAULT_COMPETENCIES_SC_OUTPUT_TOKENS` and `COMPETENCIES_MAX_OUTPUT_TOKENS` to `8192`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml`: Raise `max_output_tokens` to `8192` for `standard_reasoning` and `bullet_rewrite_quality`.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_competencies_transport_orchestration_w1_w6.py`: Update SC output token assertions to `8192`.

### Acceptance Criteria
- `competencies_self_consistency_output_tokens()` and `standard_reasoning` / `bullet_rewrite_quality` judge caps resolve to `8192`.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_competencies_transport_orchestration_w1_w6.py resume_graph_engine/tests/unit/apps_rg/test_section_judges_and_gates_consistency_redteam.py -v --timeout=60`
- **Input:** `provider_profiles.yaml` and `competencies_lane_defaults.py`.
- **Expected:** Exit code `0` with all assertions passing.
- **Verify independently:** Query `get_section_judge_policy("competencies").judge_runtime_profile.resolved_max_output_tokens(attempt=1) == 8192`.
- **Fail if:** Judge tier monotonicity fails or SC cap is below `8192`.
- **Record:** `artifacts/governance/wave2_token_headroom_receipt.json`

## Wave 3: Prefix Caching, Patch-Run Boundary Parity & Parallel Wave Scheduling

### Objective & Scope
Enable ephemeral prefix caching on compacted `competencies` SC prompts, enforce runtime boundary bootstrap in `execute_patch_run`, and co-schedule `executive_summary` + `headline` in Wave 2.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/providers/anthropic_section_cache_payload.py`: Recognize `COMPETENCIES_SC_COMPACT_SYSTEM_MARKER` for `CACHE_TTL_5M` caching.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/orchestration/patch_run.py`: Call `configure_apps_rg_runtime_boundary(repo_root=plan.repo)` in `execute_patch_run`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/section_execution_plan.py`: Schedule `executive_summary` and `headline` concurrently in Wave 2.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/runtime/providers/test_section_provider_anthropic_cache.py`: Assert compacted SC prompts emit `cache_marker_count == 1`.

### Acceptance Criteria
- Compacted `competencies` SC prompts emit `cache_marker_count == 1` and `execution_waves_for_lanes` co-schedules `executive_summary` and `headline`.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/runtime/providers/test_section_provider_anthropic_cache.py resume_graph_engine/tests/unit/apps_rg/test_perf_waves_sync.py -v --timeout=60`
- **Input:** Compacted SC messages and `GENERATED_CONTENT_LANES`.
- **Expected:** Exit code `0`, cache markers enabled, and parallel Wave-2 schedule verified.
- **Verify independently:** Verify `execution_waves_for_lanes(GENERATED_CONTENT_LANES)[-1] == ("executive_summary", "headline")`.
- **Fail if:** Compacted SC prompt is uncached or `headline` blocks on `executive_summary`.
- **Record:** `artifacts/governance/wave3_caching_parallelism_receipt.json`

## Wave 4: Coherence Evidence Binding & Competency Surface Recovery

### Objective & Scope
Preserve `visible_claim_text` and `claim_source_fact_ids` in `compact_evidence_packet_for_prompt` and register SVP-rich compositions in `_ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS`.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/assembly/coherence_prompt_compact.py`: Retain `visible_claim_text` and `claim_source_fact_ids` in `bindings_compact`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/c0/competencies_graph_authority.py`: Register source-bound 6-word compositions for five Brown & Brown allocation pairs.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py`: Assert `visible_claim_text` retention in `bindings_compact`.

### Acceptance Criteria
- `compact_evidence_packet_for_prompt` preserves `visible_claim_text` on `graph_claim_bindings` and all Brown & Brown competency terms pass SVP richness.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py -v --timeout=60`
- **Input:** `full_resume_11773d943c97` competency allocation plan and evidence packet.
- **Expected:** Exit code `0` and `factual_support.pass == True` across both coherence judges.
- **Verify independently:** Inspect `x1d_full_resume_judge_outputs.json` (`factual_support.pass == True`).
- **Fail if:** Any allocation phrase falls back to token-soup synthesis.
- **Record:** `artifacts/governance/wave4_coherence_surface_receipt.json`

## Wave 5: Coherence Judge Negative-Assertion Blocker Guard

### Objective & Scope
Prevent positive judge findings containing `"with no unsupported..."` from falsely triggering `unsupported_jd_proof` blockers during mean-quorum coherence aggregation.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/assembly/full_resume_llm_coherence.py`: Gate `unsupported_jd_proof` blockers on `factual_support.pass is False` or non-empty `unsupported_claims`.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py`: Assert `aggregate_full_resume_coherence` passes mean quorum when a judge finding states `"with no unsupported JD-only proof"`.

### Acceptance Criteria
- `_finding_is_negative_assertion` returns `True` for `"with no unsupported JD-only proof"` and `aggregate_full_resume_coherence` achieves `full_resume_coherence_pass=True`.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_wave4_judge_repair_and_recovery.py -v --timeout=60`
- **Input:** `full_resume_11773d943c97` coherence judge outputs.
- **Expected:** Exit code `0` and `full_resume_coherence_pass=True`.
- **Verify independently:** Inspect `patch_run_receipt.json` (`decisive_status == "PASS"`).
- **Fail if:** Genuine `factual_support` failures are ignored.
- **Record:** `artifacts/governance/wave5_coherence_blocker_guard_receipt.json`

## Wave 6: Headline Banner Cleanup, GitHub Link Fix & Executive Summary De-Clunking

### Objective & Scope
Remove the literal `"HEADLINE"` label in rendered `.txt` and `.docx` outputs, update the GitHub link to `https://github.com/Siamese001/`, and remove forced verbatim S4 dependency-graph canned sentence injection so the executive summary flows naturally.

### Milestones & Deliverables
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/assembly/full_resume_text.py` & `final_resume_docx.py`: Omit `"HEADLINE"` label and style the headline line as `RoleHeader`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/evals/owner_solo/final_resume_output_review.py`: Slice top-of-resume without requiring `"HEADLINE"`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/resume/base/candidate_static_profile.json` & `amit_ayer_base_resume_v1.json`: Update GitHub URL to `https://github.com/Siamese001/`.
- `[MODIFY]` `resume_graph_engine/src/apps_rg/runtime/validators/executive_summary_x2.py`, `executive_summary_voice_repair.py`, & `executive_summary_synthesis_contract.py`: Relax `fact_engineering_platform_002` required substring to `"dependency graph"` and prevent overwriting natural LLM prose when the fact is only a linked ancestor.

### Acceptance Criteria
- Rendered resume text and `.docx` omit `"HEADLINE"`, show `https://github.com/Siamese001/`, and produce a natural 6-sentence executive summary.

### Runtime Receipt & Completion Gate
- **Run:** `.venv/bin/python -m pytest resume_graph_engine/tests/unit/apps_rg/test_final_resume_outputs.py resume_graph_engine/tests/apps_rg/test_csuite_five_section_e2e_jds.py -v --timeout=60`
- **Input:** `full_resume_11773d943c97` run directory and unit test fixtures.
- **Expected:** Exit code `0`, `"HEADLINE"` absent from `FINAL_RESUME_OUTPUT.txt`, and `https://github.com/Siamese001/` present.
- **Verify independently:** Inspect `FINAL_RESUME_OUTPUT.txt`, `outputs/resume.docx`, and `x1d_llm_judge_outputs.json`.
- **Fail if:** `"HEADLINE"` appears in rendered output, old GitHub link persists, or canned S4 overwrite clobbers natural synthesis.
- **Record:** `artifacts/governance/wave6_exec_summary_and_header_polish_receipt.json`
