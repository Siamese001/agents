"""Live behavioral probes for Pillars 5, 6, and 7 of the Cost & Token Budget Auditor.

Covers surgical prompt trimming, evidence/shape contract preservation, lane-calibrated
judge retries, zero-LLM qualification guard checks, token budget reservations,
model pricing rollups, research spend caps, and HITL decision store learning.
"""

from __future__ import annotations

import contextlib
import io
import socket
import tempfile
from pathlib import Path
from typing import Any

from tools.cost_token_budget_probes import load_repo_module, load_yaml_strict


def run_pillar_5_live_probes(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    """Execute live optional trim, protected evidence/shape contract checks, and word repair builder."""
    gaps: list[str] = []
    metrics: dict[str, Any] = {"trim_tokens_saved": 0, "quality_preserved": False}

    estb, e1 = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_token_budget.py",
    )
    wbr, e2 = load_repo_module(
        repo_root,
        "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary/word_budget_repair.py",
    )
    if e1 or estb is None:
        gaps.append(e1 or "Missing executive_summary_token_budget.py")
    if e2 or wbr is None:
        gaps.append(e2 or "Missing executive_summary/word_budget_repair.py")
    if gaps:
        return gaps, metrics

    try:
        protected_ids = {"fact_high_01", "fact_high_02"}
        sample_prompt = (
            "<!-- SLOT: S0 -->\nNO FABRICATION. Use proof substrate only.\n"
            "<!-- SLOT: I0 -->\n"
            "<authority_boundary>SOVEREIGN_AUTH</authority_boundary>\n"
            "<evidence_law>STRICT_EVIDENCE_LAW</evidence_law>\n"
            "<output_contract>SIX_SENTENCES</output_contract>\n"
            "<!-- SLOT: C0 -->\n"
            "INPUT_AUTHORITY:\n"
            'ALLOWED_SOURCE_FACT_IDS: ["fact_high_01","fact_high_02"]\n'
            "- fact_high_01: Led $50M AI platform transformation.\n"
            "- fact_high_02: Reduced latency 42% across 18 services.\n"
            "- fact_opt_99: Optional low-priority historical note.\n"
            "JD_TEXT (targeting only; non-proof): " + ("Enterprise AI transformation role. " * 90) + "\n"
            "BRIEFING (targeting only; non-proof): " + ("Strategic cloud modernization mandate. " * 110) + "\n"
            "<!-- SLOT: E0 -->\n" + ("Style example paragraph for optional compression.\n" * 80) + "\n"
            "<!-- SLOT: Y0 -->\n" + ("Optional tone and cadence guidance block.\n" * 60) + "\n"
            "<!-- SLOT: U0 -->\nGenerate executive summary JSON.\n"
            '<!-- SLOT: R0 -->\n{"type":"object","required":["resume_display_text","claim_ledger"]}\n'
        )
        before_tokens = int(estb.estimate_tokens_approximate(sample_prompt))
        trimmed, trimmed_components, trim_applied = estb.trim_executive_summary_prompt_content(
            sample_prompt,
            protected_ids=protected_ids,
            available_input_tokens=max(400, int(before_tokens * 0.55)),
        )
        after_tokens = int(estb.estimate_tokens_approximate(trimmed))
        if not trim_applied or not trimmed_components or after_tokens >= before_tokens:
            gaps.append("trim_executive_summary_prompt_content failed to reduce optional prompt bloat")

        ev_violations = estb.verify_evidence_contract_unchanged(sample_prompt, trimmed, protected_ids)
        sh_violations = estb.verify_prompt_shape_preserved(sample_prompt, trimmed, srfs_mode=False)
        if ev_violations:
            gaps.append(f"Optional trim corrupted protected evidence contract: {ev_violations}")
        if sh_violations:
            gaps.append(f"Optional trim corrupted prompt shape: {sh_violations}")

        # Negative probe: tampering with protected fact or I0 evidence_law MUST report violations
        tampered = trimmed.replace("fact_high_01", "fact_DROPPED").replace("STRICT_EVIDENCE_LAW", "WEAKENED")
        neg_ev = estb.verify_evidence_contract_unchanged(sample_prompt, tampered, protected_ids)
        if not neg_ev:
            gaps.append("verify_evidence_contract_unchanged failed to detect tampered protected fact/evidence_law")

        # Regen budget check
        regen_check = estb.regen_dispatch_allowed(
            [{"role": "user", "content": "x " * 200}],
            max_output_tokens=600,
            provider_context_window=32000,
        )
        if not regen_check.dispatch_allowed or regen_check.available_input_tokens <= 0:
            gaps.append("regen_dispatch_allowed rejected small valid repair thread")

        repair_prompt = wbr._build_word_budget_repair_user(148, word_ceiling=130)
        if "148" not in repair_prompt or "130" not in repair_prompt:
            gaps.append("word_budget_repair._build_word_budget_repair_user failed dynamic word-ceiling binding")

        # Outreach prompt_templates/*.yaml + DeterministicDraftRepairer zero-token repair probes
        tmpl_dir = repo_root / "outreach_engine" / "config" / "prompt_templates"
        tmpl_files = sorted(tmpl_dir.glob("*.yaml")) if tmpl_dir.is_dir() else []
        if len(tmpl_files) < 8:
            gaps.append(f"Expected >= 8 outreach prompt templates in outreach_engine/config/prompt_templates, got {len(tmpl_files)}")
        for tf in tmpl_files:
            tdoc, terr = load_yaml_strict(tf)
            if terr or not isinstance(tdoc, dict) or not tdoc.get("template_id") or not tdoc.get("input_contract"):
                gaps.append(f"Invalid outreach prompt template {tf.relative_to(repo_root)}: {terr or 'missing template_id/input_contract'}")

        lic_repair, e_lr = load_repo_module(repo_root, "outreach_engine/src/apps_lic/domain/repair.py")
        outreach_repair_ok = False
        if e_lr or lic_repair is None:
            gaps.append(e_lr or "Missing outreach_engine DeterministicDraftRepairer")
        else:
            raw_conn = (
                "Hi Sarah,\n\n"
                + ("Noticed your enterprise platform architecture mandate — would love to learn more about current priorities. " * 4)
            )
            rep_body, rep_subj = lic_repair.DeterministicDraftRepairer.repair_text(
                body=raw_conn,
                subject="Platform alignment — quick note",
                channel=lic_repair.ChannelType.LINKEDIN_CONNECTION,
            )
            outreach_repair_ok = (
                "\u2014" not in rep_body
                and "\u2014" not in rep_subj
                and "would love to learn more" not in rep_body.lower()
                and "open to exchanging perspectives" in rep_body.lower()
                and len(rep_body) <= 300
                and rep_body.endswith("?")
            )
            if not outreach_repair_ok:
                gaps.append("DeterministicDraftRepairer.repair_text failed zero-token outreach formatting/length repair")

        metrics = {
            "trim_tokens_saved": max(0, before_tokens - after_tokens),
            "outreach_prompt_templates_verified": len(tmpl_files),
            "outreach_repair_verified": outreach_repair_ok,
            "quality_preserved": (not ev_violations and not sh_violations and bool(neg_ev) and outreach_repair_ok),
        }
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 5 execution failure: {type(exc).__name__}: {exc}")

    return gaps, metrics


def run_pillar_6_live_probes(repo_root: Path, profiles_data: dict[str, Any]) -> list[str]:
    """Execute judge retry profile verification, Gemini transport retry classifier, and W5 zero-LLM guard."""
    gaps: list[str] = []
    judge_cfg = ((profiles_data.get("runtime_limits") or {}).get("judge")) or {}
    r_profiles = judge_cfg.get("runtime_profiles") or {}

    expected_attempts = {
        "optional_advisory_taxonomy_only": 1,
        "standard_reasoning": 2,
        "bullet_rewrite_quality": 2,
        "enhanced_reasoning": 3,
    }
    for prof_name, max_att in expected_attempts.items():
        prof = r_profiles.get(prof_name) or {}
        if prof.get("max_attempts") != max_att:
            gaps.append(f"judge.runtime_profiles.{prof_name}.max_attempts != {max_att}")

    pg, e1 = load_repo_module(repo_root, "apps_research/integrations/provider_gateway.py")
    zlq, e2 = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/runtime/zero_llm_qualification.py")
    if e1 or pg is None:
        gaps.append(e1 or "Missing apps_research/integrations/provider_gateway.py")
    if e2 or zlq is None:
        gaps.append(e2 or "Missing zero_llm_qualification.py")
    if gaps:
        return gaps

    try:
        err_cls = pg.AppsResearchProviderGatewayError
        transient_err = err_cls(
            "header timeout",
            receipt={"validation_reason": "WAIT_RESPONSE_HEADERS", "lifecycle": {"response_headers_received": False}},
            cause=socket.timeout("timed out"),
        )
        schema_err = err_cls(
            "bad schema",
            receipt={"validation_reason": "RESPONSE_SCHEMA_VALIDATION", "lifecycle": {"response_headers_received": True}},
            cause=ValueError("invalid json"),
        )
        if not pg._is_retryable_gemini_transport_error(transient_err):
            gaps.append("_is_retryable_gemini_transport_error rejected transient pre-header timeout")
        if pg._is_retryable_gemini_transport_error(schema_err):
            gaps.append("_is_retryable_gemini_transport_error falsely retried non-retryable schema error")

        delay = pg._gemini_retry_delay_seconds(
            transport_attempt=2,
            base_seconds=0.5,
            max_seconds=4.0,
            uniform=lambda _a, _b: 0.0,
        )
        if abs(delay - 1.0) > 1e-6:
            gaps.append(f"_gemini_retry_delay_seconds expected 1.0s on attempt 2, got {delay}")

        # Live zero-provider guard verification across all 6 ZERO_COUNTER_KEYS
        counter_keys = tuple(getattr(zlq, "ZERO_COUNTER_KEYS", ()))
        if len(counter_keys) < 6:
            gaps.append(f"ZERO_COUNTER_KEYS incomplete: {counter_keys}")
        else:
            zero_map = {k: 0 for k in counter_keys}
            guard_doc: dict[str, Any] = {
                "schema_version": zlq.ZERO_PROVIDER_GUARD_SCHEMA,
                "status": "PASS",
                "attempt_counters": dict(zero_map),
                **zero_map,
                "uwg_operation_attempted": False,
                "source_unchanged": True,
            }
            guard_doc["semantic_digest"] = zlq._canonical_digest(guard_doc)
            if not zlq._guard_zero(guard_doc, status="PASS"):
                gaps.append("zero_llm_qualification._guard_zero rejected valid zero-call replay guard")

            leaked_doc = dict(guard_doc)
            leaked_doc.pop("semantic_digest", None)
            leaked_doc["provider_calls"] = 1
            leaked_doc["semantic_digest"] = zlq._canonical_digest(leaked_doc)
            if zlq._guard_zero(leaked_doc, status="PASS"):
                gaps.append("zero_llm_qualification._guard_zero failed to reject non-zero provider_calls=1")
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 6 execution failure: {type(exc).__name__}: {exc}")

    return gaps


def run_pillar_7_live_probes(repo_root: Path, profiles_data: dict[str, Any], priced_model: str) -> list[str]:
    """Execute token governor reservations, pricing rollups, context budgeting, spend cap, and HITL store."""
    gaps: list[str] = []
    gov_cfg = ((profiles_data.get("runtime_limits") or {}).get("model_token_governor")) or {}
    if gov_cfg.get("max_input_tokens_per_attempt") != 48000:
        gaps.append("model_token_governor.max_input_tokens_per_attempt != 48000")
    if gov_cfg.get("max_reserved_tokens_per_run") != 300000:
        gaps.append("model_token_governor.max_reserved_tokens_per_run != 300000")

    tbg, e1 = load_repo_module(repo_root, "apps_model_telemetry/token_budget_governor.py")
    mtg, e2 = load_repo_module(repo_root, "resume_graph_engine/src/apps_rg/runtime/model_token_governor.py")
    prc, e3 = load_repo_module(repo_root, "apps_model_telemetry/pricing.py")
    rbp, e4 = load_repo_module(repo_root, "outreach_engine/src/apps_lic/integrations/research_boundary_policy.py")
    bdg, e5 = load_repo_module(repo_root, "agents/context/budgeting.py")
    prv, e6 = load_repo_module(repo_root, "agents/context/provenance.py")
    hitl, e7 = load_repo_module(repo_root, "tools/hitl_governance.py")

    for mod, msg in ((tbg, e1), (mtg, e2), (prc, e3), (rbp, e4), (bdg, e5), (prv, e6), (hitl, e7)):
        if msg or mod is None:
            gaps.append(msg or "Missing Pillar 7 governor/telemetry module")
    if gaps:
        return gaps

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # 1. Live TokenBudgetPolicy + reserve_token_budget attempt & run-cap enforcement
            rg_pol = mtg.apps_rg_model_token_budget_policy()
            rg_pol.validate()
            if rg_pol.max_input_tokens_per_attempt != 48000 or rg_pol.max_reserved_tokens_per_run != 300000:
                gaps.append("apps_rg_model_token_budget_policy diverged from 48k/300k SSOT caps")

            tight_pol = tbg.TokenBudgetPolicy(
                chars_per_token_estimate=3,
                safety_multiplier=1.0,
                max_input_tokens_per_attempt=200,
                max_reserved_tokens_per_run=350,
            )
            r1 = tbg.reserve_token_budget(
                artifact_dir=tmp_dir,
                provider="external_openai",
                model=priced_model,
                request_digest="req_a",
                prompt_text="x" * 300,  # ~100 tokens + 100 out = 200 reserved
                max_output_tokens=100,
                policy=tight_pol,
                stage="L2",
                section_id="exec",
                run_id="run_gov",
            )
            r_over_attempt = tbg.reserve_token_budget(
                artifact_dir=tmp_dir / "attempt_cap_only",
                provider="external_openai",
                model=priced_model,
                request_digest="req_b",
                prompt_text="x" * 900,  # ~300 input tokens > 200 max_input_tokens_per_attempt, but 320 < 350 run cap
                max_output_tokens=20,
                policy=tight_pol,
                stage="L2",
                section_id="exec",
                run_id="run_attempt_cap",
            )
            r_over_run = tbg.reserve_token_budget(
                artifact_dir=tmp_dir,
                provider="external_openai",
                model=priced_model,
                request_digest="req_c",
                prompt_text="x" * 360,  # ~120 + 100 = 220 + prior 200 = 420 > 350 run cap
                max_output_tokens=100,
                policy=tight_pol,
                stage="L2",
                section_id="exec",
                run_id="run_gov",
            )
            if not r1.allowed:
                gaps.append(f"reserve_token_budget blocked within-budget call: {r1.reason}")
            if r_over_attempt.allowed or r_over_attempt.reason != "INPUT_ATTEMPT_CAP_EXCEEDED":
                gaps.append("reserve_token_budget failed to block input attempt exceeding max_input_tokens_per_attempt")
            if r_over_run.allowed or r_over_run.reason != "RUN_RESERVED_TOKEN_CAP_EXCEEDED":
                gaps.append("reserve_token_budget failed to block cumulative run exceeding max_reserved_tokens_per_run")

            # 2. Pricing + unpriced fail-closed detection
            cost_ok, _, breakdown = prc.price_usage(
                priced_model,
                {"prompt_tokens": 10000, "cached_tokens": 8000, "output_tokens": 500},
                provider="external_openai",
            )
            cost_unpriced, ver_unpriced, _ = prc.price_usage("nonexistent-model-xyz", {"prompt_tokens": 100})
            if cost_ok is None or cost_ok <= 0 or breakdown.get("uncached_input_tokens") != 2000:
                gaps.append(f"price_usage miscomputed cached OpenAI usage for {priced_model}: {breakdown}")
            if cost_unpriced is not None or ver_unpriced != "unpriced":
                gaps.append("price_usage must return None for unpriced models rather than $0.00")

            rollup = prc.compute_run_cost_rollup(
                [{"model": priced_model, "provider": "external_openai", "prompt_tokens": 10000, "cached_tokens": 8000, "output_tokens": 500}]
            )
            if rollup.get("has_unpriced_models") is not False or float(rollup.get("total_cost_usd") or 0.0) <= 0.0:
                gaps.append(f"compute_run_cost_rollup failed priced rollup: {rollup}")

            # 3. Context TokenBudget priority-preserving trim
            budget = bdg.TokenBudget(max_total_tokens=300, reserved_output_tokens=100)  # max_context_tokens = 200
            low_item = prv.ContextItem(
                source_id="scratch_1",
                source_type=prv.ContextSourceType.EPHEMERAL_SCRATCH,
                content="ephemeral " * 60,
                estimated_tokens=140,
                relevance_score=0.9,
            )
            high_item = prv.ContextItem(
                source_id="doc_1",
                source_type=prv.ContextSourceType.USER_DOCUMENT,
                content="authoritative " * 50,
                estimated_tokens=150,
                relevance_score=0.8,
            )
            fitted = budget.fit_items_to_budget([low_item, high_item])
            kept_ids = [it.source_id for it in fitted.items]
            if kept_ids != ["doc_1"] or fitted.total_estimated_tokens > 200:
                gaps.append(f"TokenBudget.fit_items_to_budget failed priority preservation: kept={kept_ids}")

            # 4. ResearchBoundaryPolicy spend cap block
            pol = rbp.ResearchBoundaryPolicy(cost_limit_usd=0.10, cost_per_call_usd=0.05)
            blocked = rbp.build_cost_limit_exceeded_result(
                run_id="r_cost",
                trace_id="t_cost",
                request_id="req_cost",
                cumulative_cost_usd=0.10,
                cost_per_call_usd=pol.cost_per_call_usd,
                cost_limit_usd=pol.cost_limit_usd,
            )
            if not blocked.is_blocked or "COST_LIMIT_EXCEEDED" not in str(blocked.block_reason):
                gaps.append("ResearchBoundaryPolicy failed to emit blocked COST_LIMIT_EXCEEDED result")

            # 5. HITLDecisionStore SQLite execution outcome learning
            store = hitl.HITLDecisionStore(db_path=tmp_dir / "hitl_probe.sqlite")
            try:
                rec = store.record_decision(
                    decision_id="probe_dec_1",
                    task_id="probe_task_1",
                    category="cost_budget_probe",
                    options=[{"label": "Option A", "score": 0.85}, {"label": "Option B", "score": 0.60}],
                    selected_option="Option A",
                    operator_action="APPROVED",
                    margin=0.25,
                    calibrated_confidence=0.85,
                    context_summary="Probe decision",
                    outcome="PENDING",
                )
                updated = store.record_execution_outcome("probe_dec_1", "SUCCESS")
                if not rec or not updated:
                    gaps.append("HITLDecisionStore failed to persist and update execution outcome")
            finally:
                store.close()

            # 6. Infrastructure LiveTokenGovernor + LiveTelemetryLock fail-closed probes
            lgov, e_lg = load_repo_module(repo_root, "infrastructure/live_governor.py")
            if e_lg or lgov is None:
                gaps.append(e_lg or "Missing infrastructure/live_governor.py")
            else:
                gov_budget = lgov.TokenBudget(
                    max_prompt_tokens=200,
                    max_completion_tokens=100,
                    max_total_tokens=250,
                    max_run_tokens=400,
                )
                gov = lgov.LiveTokenGovernor(default_budget=gov_budget)
                res_ok = gov.reserve(
                    provider="external_openai",
                    model=priced_model,
                    estimated_prompt_tokens=150,
                    requested_completion_tokens=80,
                )
                gov.reconcile(res_ok, actual_prompt_tokens=140, actual_completion_tokens=70)
                if gov.cumulative_tokens_consumed != 210:
                    gaps.append(f"LiveTokenGovernor reconcile miscomputed cumulative_tokens_consumed={gov.cumulative_tokens_consumed}")

                exceeded_cases = (
                    (250, 50, "REQUEST_PROMPT_BUDGET_EXCEEDED"),
                    (100, 120, "REQUEST_COMPLETION_BUDGET_EXCEEDED"),
                    (180, 90, "REQUEST_TOTAL_BUDGET_EXCEEDED"),
                    (150, 80, "RUN_TOTAL_BUDGET_EXCEEDED"),
                )
                for est_p, req_c, expected_code in exceeded_cases:
                    try:
                        gov.reserve(
                            provider="external_openai",
                            model=priced_model,
                            estimated_prompt_tokens=est_p,
                            requested_completion_tokens=req_c,
                        )
                        gaps.append(f"LiveTokenGovernor failed to raise {expected_code}")
                    except lgov.TokenBudgetExceededError as exc_b:
                        if expected_code not in str(exc_b):
                            gaps.append(f"LiveTokenGovernor raised unexpected message for {expected_code}: {exc_b}")

                try:
                    lgov.LiveTelemetryLock.record_receipt(
                        provider="external_openai",
                        model=priced_model,
                        usage=None,
                        production_enforce=True,
                    )
                    gaps.append("LiveTelemetryLock failed to reject missing usage in production_enforce=True")
                except lgov.TelemetryMissingUsageError:
                    pass

            # 7. Inline deterministic secret & model-neutral naming enforcement
            sec_mod, e_sec = load_repo_module(repo_root, "tools/lint_secrets.py")
            mn_mod, e_mn = load_repo_module(repo_root, "tools/lint_model_neutral_naming.py")
            if e_sec or sec_mod is None:
                gaps.append(e_sec or "Missing tools/lint_secrets.py")
            else:
                buf_s = io.StringIO()
                with contextlib.redirect_stdout(buf_s), contextlib.redirect_stderr(buf_s):
                    sec_rc = sec_mod.main(["--all", "--repo-root", str(repo_root)])
                if sec_rc != 0:
                    gaps.append(f"lint_secrets failed inline check: {buf_s.getvalue().strip()}")
            if e_mn or mn_mod is None:
                gaps.append(e_mn or "Missing tools/lint_model_neutral_naming.py")
            else:
                buf_m = io.StringIO()
                with contextlib.redirect_stdout(buf_m), contextlib.redirect_stderr(buf_m):
                    mn_rc = mn_mod.main(["--all", "--repo-root", str(repo_root)])
                if mn_rc != 0:
                    gaps.append(f"lint_model_neutral_naming failed inline check: {buf_m.getvalue().strip()}")
    except Exception as exc:  # guardian: allow-broad-exception -- record runtime failure in pillar gaps
        gaps.append(f"Pillar 7 execution failure: {type(exc).__name__}: {exc}")

    return gaps
