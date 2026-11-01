# Cost, Token Budget & Provider Routing Remediation Plan

## Executive Summary
This wave-based remediation plan resolves the 6-pillar cost, token budget, prompt prefix caching, and provider routing findings identified during the Stage IV-A (`agents-cost-token-budget`) audit of `/Users/amitayer/Git/agents`. Every planned remediation meets the mandatory $\text{ROI} \ge 2.5\times$ economic efficiency admission gate, eliminates all 13 hardcoded model literal violations reported by `tools/lint_model_neutral_naming.py`, enforces bounded embedding client timeouts and SHA-256 deduplication in `apps_research`, and elevates static consumer brief instructions into the system message prefix to maximize provider prompt caching hit rates.

## Wave 1: Provider Profile Conformance & Explicit Token Budget Caps

### Objective & Scope
Eliminate all 13 hardcoded model literals across `apps_research/engines/research_retrieval_engine.py` and `scripts/local_llm/`, resolve model identifiers dynamically from `config/model_catalog.json`, add explicit per-call timeout (`timeout=30.0`, `max_retries=2`) and SHA-256 content-digest embedding deduplication to `InMemoryResearchStore._mock_embed`, and reset `artifacts/governance/model_literal_baseline.json` to zero violations ($\text{ROI} = 3.13\times$).

### Milestones & Deliverables
- `[MODIFY]` `apps_research/engines/research_retrieval_engine.py`: Resolve embedding model identifier from `config/model_catalog.json` (`embedding.bge_m3` / `APPS_RESEARCH_EMBEDDING_MODEL`), configure `timeout=30.0` and `max_retries=2` on the OpenAI client, and add an in-memory SHA-256 digest cache (`_digest_embedding_cache`) to deduplicate repeated embedding calls on identical inputs within a run.
- `[MODIFY]` `scripts/local_llm/download_qwen_weights.py`: Resolve default local MLX repository identifier from `config/model_catalog.json` (`qwen.local_27b_mlx`) with neutral CLI help text.
- `[MODIFY]` `scripts/local_llm/test_client_call.py`: Resolve local inference model identifier from `config/model_catalog.json` (`qwen.local_model_id`) with neutral diagnostic notes.
- `[MODIFY]` `scripts/local_llm/serve_qwen_m5.py`: Resolve local server model identifiers and weights path from `config/model_catalog.json` (`qwen.local_model_id`, `qwen.local_27b_mlx`) so `tools/lint_model_neutral_naming.py` passes with 0 violations.
- `[MODIFY]` `artifacts/governance/model_literal_baseline.json`: Ratchet legacy model literal baseline down from 13 violations across 4 files to 0 violations.
- `[MODIFY]` `tests/test_research_retrieval_engine.py`: Add unit tests verifying SHA-256 embedding deduplication, bounded client timeout/retry parameters, and catalog-resolved model identity.

### Acceptance Criteria
- `python3 tools/lint_model_neutral_naming.py` exits `0` with `[PASS] Model-neutral naming clean` (0 violations, down from 13).
- `InMemoryResearchStore._mock_embed` caches embeddings by SHA-256 text digest and avoids duplicate live provider calls for identical inputs.
- Scoped unit tests in `tests/test_research_retrieval_engine.py` and `tests/test_model_neutral_naming.py` pass with `--timeout=60`.

### Runtime Receipt & Completion Gate
- **Run:** `python3 tools/lint_model_neutral_naming.py && /Users/amitayer/Git/agents/.venv/bin/pytest tests/test_research_retrieval_engine.py tests/test_model_neutral_naming.py -v --timeout=60`
- **Input:** Production Python modules in `apps_research/` and `scripts/local_llm/`, plus unit test suites.
- **Expected:** Exit code `0`; 0 model-neutral naming violations; 100% test pass rate.
- **Verify independently:** Inspect `artifacts/governance/model_literal_baseline.json` (`file_counts == {}`) and AST of `apps_research/engines/research_retrieval_engine.py`.
- **Fail if:** Any hardcoded model literal remains in production scope or any test fails.
- **Record:** `artifacts/sidecar_runs/agents_cost_token_budget/20261101T130343Z/wave_receipts.md`

## Wave 2: Research Payload Compaction & Prompt Prefix Cache Optimization

### Objective & Scope
Enforce deterministic character compaction (`max_chars=12000`) on raw job description payloads in `apps_research/prompt_assembly/consumer_briefs.py:extract_jd_text` to prevent unbounded JD dumps from exhausting synthesis input token budgets, and hoist static contract rules (`CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT`) into the system message of `CompanyBriefEngine._gemini_synthesize_plain` so static system instructions precede dynamic company/JD payloads for optimal OpenAI prefix caching ($\text{ROI} = 4.00\times$).

### Milestones & Deliverables
- `[MODIFY]` `apps_research/prompt_assembly/consumer_briefs.py`: Add `max_chars: int = 12000` compaction ceiling to `extract_jd_text` and define `CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT` containing the invariant grounding, exclusion, and formatting rules for downstream targeting and consumer briefs.
- `[MODIFY]` `apps_research/engines/company_brief_engine.py`: Update `_gemini_synthesize_plain` to pass `CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT` in the `system` role message ahead of the dynamic `user` prompt payload.
- `[MODIFY]` `resume_graph_engine/tests/unit/apps_research/test_apps_rg_targeting_brief_prompt.py`: Add unit tests verifying `extract_jd_text` compaction ceiling and static system prompt prefix ordering in `_gemini_synthesize_plain`.

### Acceptance Criteria
- `extract_jd_text` deterministically truncates oversized JD inputs above `max_chars=12000` with a `...` suffix while preserving normal JDs intact.
- `CompanyBriefEngine._gemini_synthesize_plain` places `CONSUMER_BRIEF_STATIC_SYSTEM_PROMPT` in `messages[0]` (`role="system"`) before the dynamic `messages[1]` (`role="user"`).
- Scoped unit tests in `resume_graph_engine/tests/unit/apps_research/test_apps_rg_targeting_brief_prompt.py` pass with `--timeout=60`.

### Runtime Receipt & Completion Gate
- **Run:** `/Users/amitayer/Git/agents/.venv/bin/pytest resume_graph_engine/tests/unit/apps_research/test_apps_rg_targeting_brief_prompt.py outreach_engine/tests/test_research_cost_optimization.py -v --timeout=60`
- **Input:** Oversized JD fixtures (>12,000 chars) and mocked OpenAI synthesis gateway calls.
- **Expected:** Exit code `0`; JD text bounded to `<= 12000` chars; system message prefix verified before user message.
- **Verify independently:** Inspect message ordering and `extract_jd_text` return length via Python one-liner inspection.
- **Fail if:** System prompt is missing static rules, user message precedes system message, or JD text exceeds `max_chars`.
- **Record:** `artifacts/sidecar_runs/agents_cost_token_budget/20261101T130343Z/wave_receipts.md`

## Wave Implementation & Completion Status Table

| Wave | Description / Scope | Status |
| :--- | :--- | :--- |
| **Wave 1** | Provider Profile Conformance, Embedding Deduplication & Explicit Timeouts (`ROI = 3.13x`) | `COMPLETE` |
| **Wave 2** | Research JD Payload Compaction & Prompt Prefix Cache Ordering (`ROI = 4.00x`) | `COMPLETE` |
