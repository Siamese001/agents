# Wave 0: stub inventory and callers (read-only findings)

Generated during plan execution. All claims below were observed in files or command output on 2026-11-19.

## Stub 1: judge stub
- File: `resume_graph_engine/src/apps_rg/runtime/judges/inprocess_proof_judge.py` (added by commit `baa6e5de60`, 2026-11-17, merged as `66a9c46d1b`).
- `evaluate_argon_x1d_judge` returns constants: score 4.85 (High pin) or 4.80, canned findings, every dimension pass (3.5 if a gate failed), invented token counts, `responseId` starting `argon-`.
- Caller: `executive_summary_x1d.py:1571` (`if is_argon_model(model)` inside `_call_gemini`).
- Blast radius in the artifacts on disk: 13 judge rows, all in one run (`truist_judge_verify_20261118`), scores exactly 4.8 (12 rows) or 4.85 (1 row). See `inventory.json`.
- `evaluate_argon_handoff_payload` (same file) has a LIVE caller: `apps_research/integrations/provider_gateway.py:463-478`. For any pin whose model name contains "argon" it returns a fixed 0.95 verdict unless a regex matches, instead of calling a model. The file therefore cannot simply be deleted.

## Stub 2: generator stub (found while executing Wave 0; outside the approved plan scope)
- File: `resume_graph_engine/src/apps_rg/runtime/providers/inprocess_ide_provider.py` (1047 lines, added by commit `d90e9751fc`, 2026-11-17, "migrate Anthropic roles to in-process IDE Sonnet 5.5 High and Medium with zero API calls").
- Trigger: `external_provider.py:408-415`: if the model id contains `5-5-` and `urllib.request.urlopen` is the stdlib one, return canned content from `_synthesize_executive_summary`, `_synthesize_headline`, `_synthesize_competencies`, `_synthesize_*_bullets` instead of calling the model.
- Evidence in the Truist run `truist_judge_verify_20261118` (generator pin `claude-sonnet-5-5-high`):
  - executive_summary: raw model output is IDENTICAL to the canned dict (7 of 7 shared keys; 6 of 6 sentences verbatim).
  - headline: the headline line is verbatim the canned line (`SVP Engineering | Multi Agent Systems | Regulated AI Governance | Agentic Control Infrastructure`).
  - competencies, unify_bullets, ibm_bullets: some keys identical to canned output (3 of 10, 3 of 7, 5 of 7); whether the remaining content was model-written is NOT yet resolved.
  - The provider records for these lanes say `runtime_generation_status: REAL_LLM`, `provider_attempted: true` and carry a `prompt_cache_receipt` with token counts, so the labels and receipts do not reveal the stub.
- Consequence: the "keyed Claude baseline" text used in the earlier parity experiments was this canned text, not a model output.

## Commit timeline (all 2026-11-17)
1. `3c6888c089`: last commit before any stub (parent of `baa6e5de60`). Real keyed generation and real keyed judges.
2. `baa6e5de60` (merged `66a9c46d1b`): judge stub.
3. `d90e9751fc`: generator stub.
The `d90e9751fc` checkout used earlier as the "prior commit with external API keys" already contains the generator stub.

## Integration code read for Wave 2
- `x1d_panel_adapters.py` dispatches by provider key to `_call_openai` / `_call_gemini`.
- Credentials are demanded in two places: `x1d_panel_bridge.py:182-198` and `executive_summary_x1d.py:1873-1886`.
- Model resolution: `section_judge_profile.resolve_section_proof_judge_model` (reads `judge_models` in `provider_profiles.yaml`, then the capability catalog `config/model_catalog.json`). Models absent from the catalog are not proof-eligible.
- `config/provider_profiles.yaml` and `resume_graph_engine/src/apps_rg/config/provider_profiles.yaml` are two identical files and must be edited together.
- `x1d_panel_harness.py` (555 lines) and `executive_summary_judge_packet.py` were not read in full.
