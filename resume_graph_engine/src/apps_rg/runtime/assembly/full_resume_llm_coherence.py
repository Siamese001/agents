"""Full-resume LLM coherence review + X2 aggregation gate (apps_rg assembly)."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.runtime.assembly.full_resume_text import flatten_final_resume_to_text
from apps_rg.runtime.judges.executive_summary_x1d import (
    DEFAULT_THRESHOLD,
    JUDGE_COMPACT_OUTPUT,
    PROVIDERS,
    JudgeOutput,
    _call_gemini,
    _call_openai,
    _invoke_judge_with_bounded_retries,
    _make_blocked_output,
    resolve_x1d_provider_credentials,
)
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.section_judge_policy import REQUIRED_JUDGE_PROVIDER_KEYS
from apps_rg.runtime.sections.competencies_certification_contract import (
    check_competencies_no_reserved_certification_category,
)

FULL_RESUME_COHERENCE_RUBRIC_VERSION = "full_resume_llm_coherence_v2"
# Judge panel SSOT = section_judge_policy.REQUIRED_JUDGE_PROVIDER_KEYS (the recalibrated cross-provider
# dual panel gemini_pro + openai_chatgpt; anthropic_claude dropped as a self-judge since Claude is the
# generator). Sourced from the SSOT — NOT a separate hardcoded roster that can silently diverge.
DEFAULT_JUDGE_ROSTER: tuple[str, ...] = REQUIRED_JUDGE_PROVIDER_KEYS
DEFAULT_QUORUM = int(os.environ.get("APPS_RG_FULL_RESUME_COHERENCE_QUORUM", "2"))
DEFAULT_PASS_THRESHOLD = DEFAULT_THRESHOLD

FULL_RESUME_COHERENCE_RUBRIC = """
You are evaluating a COMPLETE assembled executive resume (all sections) for release coherence.
Deterministic X2 gates are authoritative for hard proof; your verdict informs full_resume_coherence_pass only when aggregated with quorum.

Return JSON only with: score_scale, score, threshold, pass, decisive_failure, findings, cited_sentence_indexes, remediation_suggestions.

Evaluate:
1. narrative_coherence: headline → executive summary → experience → competencies tell one SVP/platform story.
2. section_ownership: certifications/credentials appear ONLY under CERTIFICATIONS & CREDENTIALS — never duplicated inside competencies.
3. redundancy: competencies do not restate bullets or executive summary as keyword laundry.
4. seniority_tone: executive-grade; no junior/generic filler.
5. role_fit: alignment to target role without JD/briefing-as-proof (JD is targeting context only).
6. unsupported_claims: flag JD-only or briefing-only phrasing presented as candidate proof.
7. readability_density: scannable, not stuffed.
8. cross_section_consistency: titles, dates, metrics, claims consistent across sections.
9. competencies_quality: executive capability clusters (3–6 items per category), not credential relisting or bare metrics-as-skills; preserve high-signal C0.3 graph-skills evidence without repeating EY/IBM/summary bullets.
10. cross_section_overlap: minimize redundancy between executive summary, experience bullets, and competencies while keeping locked verbatim blocks (EY, InsurTech, early career, education, certifications) intact.

CANDIDATE_EVIDENCE_PACKET is candidate proof, not targeting context. Graph IDs and source-fact IDs in that packet are the claim-authority spine. A globally unique metric or skill may be intentionally allocated to one rendered section; do not call it unsupported merely because the same wording is not duplicated in professional experience. Still flag a claim when the packet provides no candidate-evidence binding or when the rendered claim conflicts with its evidence.

AUTHORITATIVE CANDIDATE PROFILE & TARGETING BAR:
- The candidate is an executive technology leader (SVP Engineering / CTO / Partner).
- When targeting technical, platform, or applied research roles (such as "Applied AI Research Engineer" at Anthropic or similar frontier labs), the candidate's executive platform posture (platform architecture, GTM alliance co-sell, runtime governance telemetry, model eval frameworks, and enterprise portfolio expansion) is authoritative, intentional, and required.
- The Anthropic Applied AI role explicitly specifies owning the technical<>GTM handshake, enterprise reference architectures, and translating customer adoption into research/product feedback.
- For dimension `ats_alignment_without_keyword_stuffing` and `role_fit`: Do NOT mark TARGET_ROLE_MISMATCH or penalize the resume for maintaining executive SVP engineering leadership rather than an individual contributor (IC) junior researcher persona. Downward title/scope distortion or asking for an IC hands-on research downgrade is explicitly forbidden by the `seniority_downgrade` blocker. Evaluate role fit on how well executive platform/GTM leadership meets the enterprise scale, governance, and adoption scope of the role.
- For dimension `resume_voice`: Technical platform terminology (e.g., runtime governance telemetry, control planes, model evaluation frameworks) is expected at the SVP Engineering bar; do not cite it as negative jargon density unless genuinely vacuous buzzwords.

Lines marked [NOT COMPLETED: <section> — <reason>] are intentional gaps — do not score as prose; judge flow/overlap only on completed sections.

Decisive failure (blockers):
- Credential names duplicated in ENGINEERING & PLATFORM COMPETENCIES
- JD/briefing language used as primary proof for unsupported skills
- Severe incoherence or seniority downgrade vs SVP engineering/platform bar
- Competencies section is keyword stuffing with no executive clusters
""".strip()


def full_resume_coherence_review_enabled() -> bool:
    if assembly_structural_only_mode():
        return False
    raw = os.environ.get("APPS_RG_FULL_RESUME_LLM_COHERENCE_REVIEW", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "disabled")


def assembly_structural_only_mode() -> bool:
    """Structural package: lane copy + deterministic X2 only — no aggregate LLM judge."""
    from apps_rg.runtime.product_output_policy import product_fail_closed_runtime

    if product_fail_closed_runtime():
        return False
    raw = os.environ.get("APPS_RG_ASSEMBLY_STRUCTURAL_ONLY", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def assembly_product_release_mode() -> bool:
    return full_resume_coherence_review_enabled()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [dict(row) for row in value.values() if isinstance(row, dict)]
    return []


def build_full_resume_evidence_packet(final_resume: dict[str, Any]) -> dict[str, Any]:
    """Compact candidate-proof context for the whole-resume coherence panel.

    This projection intentionally excludes traversal, ranking, and candidate-pool
    diagnostics. It carries only visible claims and their candidate fact/graph
    bindings, so the judge can distinguish proof from JD targeting without being
    asked to infer authority from repeated surface prose.
    """
    section_evidence: list[dict[str, Any]] = []
    for section in final_resume.get("sections") or []:
        if not isinstance(section, dict):
            continue
        snapshot = section.get("l2_output_snapshot")
        if not isinstance(snapshot, dict):
            continue
        claims = [
            {
                "claim_text": str(row.get("claim_text") or row.get("claim") or "").strip(),
                "source_fact_ids": _strings(row.get("source_fact_ids")),
                "claim_unit_id": str(row.get("claim_unit_id") or "").strip(),
            }
            for row in _mapping_rows(snapshot.get("claim_ledger"))
            if str(row.get("claim_text") or row.get("claim") or "").strip()
        ]
        plan = snapshot.get("selected_fact_plan")
        plan = plan if isinstance(plan, dict) else {}
        facts = [
            {
                "fact_id": str(row.get("fact_id") or row.get("candidate_fact_id") or "").strip(),
                "claim_text": str(row.get("claim_text") or "").strip(),
                "employer_lane": str(
                    row.get("employer_lane") or row.get("source_employment") or ""
                ).strip(),
                "source_fact_ids": _strings(
                    row.get("source_fact_ids") or row.get("linked_source_fact_ids")
                ),
                "graph_skill_node_ids": _strings(row.get("graph_skill_node_ids")),
                "metric_outcome_ids": _strings(
                    row.get("metric_outcome_ids") or row.get("selected_metric_ids")
                ),
                "metric_values": _strings(row.get("metric_values")),
                "allocation_claim_unit_ids": _strings(
                    row.get("allocation_claim_unit_ids")
                ),
                "verification_status": str(
                    row.get("verification_status") or row.get("support_level") or ""
                ).strip(),
            }
            for row in _mapping_rows(plan.get("facts"))
        ]
        bindings = [
            {
                "visible_claim_text": str(row.get("visible_claim_text") or "").strip(),
                "fact_ids": _strings(row.get("fact_ids")),
                "skill_ids": _strings(row.get("skill_ids")),
                "metric_outcome_id": str(row.get("metric_outcome_id") or "").strip(),
                "metric_value": str(row.get("metric_value") or "").strip(),
                "citation_refs": _strings(row.get("citation_refs")),
                "binding_status": str(row.get("binding_status") or "").strip(),
            }
            for row in _mapping_rows(snapshot.get("graph_claim_bindings"))
        ]
        if not claims and not facts and not bindings:
            continue
        section_evidence.append(
            {
                "section_id": str(section.get("section_id") or "").strip(),
                "allocation_plan_digest": str(
                    snapshot.get("resume_graph_allocation_plan_digest")
                    or plan.get("allocation_plan_digest")
                    or ""
                ).strip(),
                "claim_binding_pass": snapshot.get("resume_graph_claim_binding_pass"),
                "visible_claims": claims,
                "selected_candidate_facts": facts,
                "graph_claim_bindings": bindings,
            }
        )
    return {
        "schema": "apps_rg.full_resume_candidate_evidence_packet.v1",
        "authority_semantics": [
            "This packet is candidate proof; TARGETING_CONTEXT is not proof.",
            "Graph IDs and source-fact IDs are claim authority.",
            "Whole-resume allocation may place a fact or metric in exactly one rendered section; surface-text repetition is not required for support.",
        ],
        "sections": section_evidence,
    }


def _build_prompt(
    *,
    full_resume_text: str,
    target_company: str,
    target_role: str,
    jd_context: str,
    evidence_packet: dict[str, Any] | None = None,
) -> str:
    jd_block = f"\nTARGETING_CONTEXT (not proof):\ncompany={target_company}\nrole={target_role}\n{jd_context}\n"
    evidence_block = ""
    if evidence_packet:
        evidence_block = (
            "\nCANDIDATE_EVIDENCE_PACKET (candidate proof):\n"
            + json.dumps(
                evidence_packet,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    return (
        f"{FULL_RESUME_COHERENCE_RUBRIC}\n\n{JUDGE_COMPACT_OUTPUT}\n\n"
        f"ASSEMBLED_RESUME_TEXT:\n{full_resume_text}\n"
        f"{evidence_block}"
        f"{jd_block}"
    )


def _mocked(provider_key: str, input_hash: str) -> JudgeOutput:
    meta = PROVIDERS[provider_key]
    from apps_rg.runtime.judges.executive_summary_x1d import _policy_model_name

    model_name = _policy_model_name(provider_key, "full_resume_coherence")
    return JudgeOutput(
        judge_id=f"x1d_{provider_key}_full_resume_coherence",
        provider_name=meta["provider_name"],
        provider_key=provider_key,
        evaluator_mode="MOCKED",
        provider_status="MOCKED",
        model_name=model_name,
        provider_available=False,
        provider_blocked=False,
        exact_provider_error=None,
        rubric_version=FULL_RESUME_COHERENCE_RUBRIC_VERSION,
        input_hash=input_hash,
        output_hash="mocked-output",
        score=0.0,
        score_scale="0_to_1",
        normalized_score=0.0,
        threshold=DEFAULT_PASS_THRESHOLD,
        normalized_threshold=DEFAULT_PASS_THRESHOLD,
        pass_=False,
        decisive_failure=True,
        findings=["MOCKED judge — does not count toward quorum pass."],
        cited_sentence_indexes=[],
        remediation_suggestions=[],
    )


def run_full_resume_coherence_judges(
    *,
    full_resume_text: str,
    target_company: str,
    target_role: str,
    jd_context: str = "",
    evidence_packet: dict[str, Any] | None = None,
    judge_roster: list[str] | None = None,
    mode: str = "blocked_if_unavailable",
    artifact_base: Path | None = None,
) -> list[JudgeOutput]:
    roster = list(judge_roster or DEFAULT_JUDGE_ROSTER)
    input_payload = {
        "full_resume_text": full_resume_text[:12000],
        "target_company": target_company,
        "target_role": target_role,
        "rubric": FULL_RESUME_COHERENCE_RUBRIC,
        "evidence_packet": evidence_packet or {},
    }
    input_hash = hashlib.sha256(json.dumps(input_payload, sort_keys=True).encode()).hexdigest()[:16]
    prompt = _build_prompt(
        full_resume_text=full_resume_text,
        target_company=target_company,
        target_role=target_role,
        jd_context=jd_context,
        evidence_packet=evidence_packet,
    )

    outputs: list[JudgeOutput] = []
    for key in roster:
        if key not in PROVIDERS:
            out = _make_blocked_output(
                key,
                input_hash,
                "BLOCKED_PROVIDER_UNAVAILABLE",
                "BLOCKED_PROVIDER_UNAVAILABLE",
                f"Unknown judge provider key: {key}",
            )
            out.judge_id = f"x1d_{key}_full_resume_coherence"
            outputs.append(out)
            continue

        if mode == "mocked":
            outputs.append(_mocked(key, input_hash))
            continue

        meta = PROVIDERS[key]
        api_key, env_checked = resolve_x1d_provider_credentials(key, os.environ)
        if not api_key:
            detail = (
                f"No non-empty API credential in {env_checked}; "
                f"(Gemini: GOOGLE_API_KEY, then deprecated GEMINI_API_KEY alias)."
                if key == "gemini_pro"
                else f"{meta['env']} environment variable not set"
            )
            out = _make_blocked_output(
                key,
                input_hash,
                "BLOCKED_PROVIDER_UNAVAILABLE",
                "BLOCKED_PROVIDER_UNAVAILABLE",
                detail,
            )
            out.judge_id = f"x1d_{key}_full_resume_coherence"
            outputs.append(out)
            continue

        resolution = resolve_section_proof_judge_model("full_resume_coherence", key)
        if resolution.blocked:
            out = _make_blocked_output(
                key,
                input_hash,
                "BLOCKED_MODEL_CONFIG",
                "BLOCKED_MODEL_CONFIG",
                resolution.block_reason or "proof judge model unavailable",
                model_name=resolution.model_requested or "unconfigured",
            )
            out.judge_id = f"x1d_{key}_full_resume_coherence"
            out.section_id = "full_resume_coherence"
            out.model_tier = resolution.model_tier
            outputs.append(out)
            continue
        model = resolution.model_actual
        model_source = resolution.model_source
        model_requested = resolution.model_requested or model
        reasoning_effort = resolution.reasoning_effort

        try:
            def _dispatch(attempt_no: int) -> JudgeOutput:
                if key == "openai_chatgpt":
                    return _call_openai(
                        api_key,
                        prompt,
                        model,
                        input_hash,
                        key,
                        artifact_base=artifact_base,
                        reasoning_effort=reasoning_effort,
                        model_requested=model_requested,
                        model_env_source=model_source,
                        attempt=attempt_no,
                        section_id="full_resume_coherence",
                    )
                return _call_gemini(
                    api_key,
                    prompt,
                    model,
                    input_hash,
                    key,
                    model_source=model_source,
                    artifact_base=artifact_base,
                    model_requested=model_requested,
                    thinking_level=reasoning_effort,
                    attempt=attempt_no,
                    section_id="full_resume_coherence",
                )

            output = _invoke_judge_with_bounded_retries(
                _dispatch,
                provider_key=key,
                section_id="full_resume_coherence",
            )
            output.judge_id = f"x1d_{key}_full_resume_coherence"
            outputs.append(output)
        except Exception as exc:  # guardian: allow-broad-exception -- P2 burndown: full-resume judge must not crash assembly
            out = _make_blocked_output(
                key,
                input_hash,
                "BLOCKED_PROVIDER_ERROR",
                "BLOCKED_PROVIDER_ERROR",
                str(exc)[:500],
            )
            out.judge_id = f"x1d_{key}_full_resume_coherence"
            outputs.append(out)

    return outputs


def _deterministic_preflight_blockers(final_resume: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    sections = final_resume.get("sections") or []
    by_id = {s.get("section_id"): s for s in sections if isinstance(s, dict)}
    comp_snap = (by_id.get("competencies") or {}).get("l2_output_snapshot") or {}
    comps = comp_snap.get("competencies") or []
    ok, reason = check_competencies_no_reserved_certification_category(comps)
    if not ok:
        blockers.append(f"credential_duplication_in_competencies:{reason}")

    flat = flatten_final_resume_to_text(final_resume)
    comp_heading = "ENGINEERING & PLATFORM COMPETENCIES"
    if comp_heading in flat:
        comp_block = _block_after_heading(
            flat,
            comp_heading,
            stop_headings=(
                "PROFESSIONAL EXPERIENCE",
                "EDUCATION",
                "CERTIFICATIONS",
            ),
        )
        for needle in ("AWS Certified", "Databricks Lakehouse Fundamentals", "Fellow of the Society"):
            if needle in comp_block:
                blockers.append(f"credential_name_in_competencies_block:{needle}")
    certification_heading = "CERTIFICATIONS & CREDENTIALS"
    if certification_heading in flat:
        before_certifications, certification_block = flat.split(
            certification_heading,
            1,
        )
        for needle in (
            "AWS Certified",
            "Databricks Lakehouse Fundamentals",
            "Fellow of the Society of Actuaries",
        ):
            if needle in certification_block and needle in before_certifications:
                blockers.append(
                    f"credential_section_ownership_duplicate:{needle}"
                )
    return blockers


def _block_after_heading(text: str, heading: str, *, stop_headings: tuple[str, ...]) -> str:
    """Return text under one rendered heading without swallowing later resume sections."""
    if heading not in text:
        return ""
    block = text.split(heading, 1)[-1]
    block_upper = block.upper()
    cut = len(block)
    for stop in stop_headings:
        idx = block_upper.find(stop.upper())
        if idx >= 0:
            cut = min(cut, idx)
    return block[:cut]


def aggregate_full_resume_coherence(
    judge_outputs: list[JudgeOutput],
    *,
    deterministic_blockers: list[str],
    quorum_required: int = DEFAULT_QUORUM,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> dict[str, Any]:
    model_backed = [
        o
        for o in judge_outputs
        if o.evaluator_mode != "MOCKED"
        and not o.provider_blocked
        and o.provider_available
        and o.provider_status not in ("MOCKED", "BLOCKED_PROVIDER_UNAVAILABLE", "BLOCKED_PROVIDER_ERROR")
    ]
    blocked = [
        o
        for o in judge_outputs
        if o.provider_blocked
        or not o.provider_available
        or o.provider_status.startswith("BLOCKED")
    ]
    passing = [
        o
        for o in model_backed
        if o.pass_
        and not o.decisive_failure
        and (o.normalized_score or 0.0) >= pass_threshold
    ]

    criteria_scores: dict[str, float] = {}
    if model_backed:
        criteria_scores["mean_normalized_score"] = round(
            sum(o.normalized_score or 0.0 for o in model_backed) / len(model_backed),
            4,
        )
    criteria_scores["model_backed_pass_count"] = float(len(passing))
    criteria_scores["model_backed_total"] = float(len(model_backed))

    quorum_met = len(passing) >= quorum_required if len(model_backed) >= quorum_required else False
    allow_mean_quorum = (
        os.environ.get("APPS_RG_FULL_RESUME_COHERENCE_ALLOW_MEAN_QUORUM", "1")
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )
    if not quorum_met and allow_mean_quorum and len(model_backed) >= 2:
        if (
            len(passing) >= 1
            and criteria_scores.get("mean_normalized_score", 0.0) >= pass_threshold
            and not any(o.decisive_failure for o in model_backed)
        ):
            quorum_met = True

    blockers = list(deterministic_blockers)
    from apps_rg.runtime.product_output_policy import product_fail_closed_runtime

    if product_fail_closed_runtime() and len(model_backed) < quorum_required:
        blockers.append(
            f"judge_quorum_insufficient:model_backed={len(model_backed)} required={quorum_required}"
        )
    warnings: list[str] = []
    for o in model_backed:
        if o.pass_ and not o.decisive_failure:
            # A passing judge's findings are commentary, not failure evidence. The
            # keyword scan below is polarity-blind: anthropic's PRAISE "No credential
            # names are duplicated inside ... COMPETENCIES" matched the cert/competency
            # heuristic and blocked a 3/3-pass resume (patch_run_17, 2026-06-11). The
            # authoritative cert-duplication detector is the deterministic preflight
            # (check_competencies_no_reserved_certification_category + needle scan),
            # which feeds deterministic_blockers above and is unaffected here.
            continue
        warnings.append(f"judge_dissent:{o.judge_id}")
        for f in o.findings or []:
            low = f.lower()
            if "jd" in low and "proof" in low:
                blockers.append(f"unsupported_jd_proof:{o.judge_id}")
            elif "briefing" in low and "proof" in low:
                blockers.append(f"unsupported_briefing_proof:{o.judge_id}")
            elif "certification" in low and "competenc" in low:
                blockers.append(f"cert_duplication_judge:{o.judge_id}")

    if blocked:
        warnings.append(f"provider_blocked_count={len(blocked)}")
    if not quorum_met and model_backed:
        for o in model_backed:
            if not o.pass_ or o.decisive_failure:
                blockers.append(f"judge_fail:{o.judge_id}")

    full_pass = quorum_met and not blockers

    decisive_reason = (
        "quorum_pass_no_blockers"
        if full_pass
        else (
            "deterministic_blocker"
            if deterministic_blockers
            else ("quorum_not_met" if not quorum_met else "judge_blockers")
        )
    )

    return {
        "criteria_scores": criteria_scores,
        "judge_verdicts": [o.to_dict() for o in judge_outputs],
        "aggregation_method": "quorum_majority_model_backed",
        "pass_threshold": pass_threshold,
        "quorum_required": quorum_required,
        "model_backed_pass_count": len(passing),
        "model_backed_total": len(model_backed),
        "provider_blocked_count": len(blocked),
        "blockers": blockers,
        "warnings": warnings,
        "decisive_reason": decisive_reason,
        "full_resume_coherence_pass": full_pass,
    }


def emit_full_resume_llm_coherence_review(
    *,
    final_resume: dict[str, Any],
    final_resume_path: Path,
    output_dir: Path,
    target_company: str = "",
    target_role: str = "",
    jd_context: str = "",
    judge_roster: list[str] | None = None,
    mode: str = "blocked_if_unavailable",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    full_text = flatten_final_resume_to_text(final_resume)
    final_hash = str(final_resume.get("final_resume_hash") or "")
    if not final_hash:
        final_hash = hashlib.sha256(
            json.dumps(final_resume, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    provider_artifact_base = output_dir / "coherence_judge_providers"
    provider_artifact_base.mkdir(parents=True, exist_ok=True)
    evidence_packet = build_full_resume_evidence_packet(final_resume)
    evidence_packet_digest = hashlib.sha256(
        json.dumps(
            evidence_packet,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    judges = run_full_resume_coherence_judges(
        full_resume_text=full_text,
        target_company=target_company,
        target_role=target_role,
        jd_context=jd_context,
        evidence_packet=evidence_packet,
        judge_roster=judge_roster,
        mode=mode,
        # Raw provider request/response artifacts go in a subdir: the structural
        # assembly X2 scan (final_resume_x2) iterates only top-level files of the
        # assembly dir, whose allowed set is the declared assembly artifacts plus
        # the two aggregate-judge summaries written below — not per-provider raws.
        artifact_base=provider_artifact_base,
    )
    det_blockers = _deterministic_preflight_blockers(final_resume)
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=det_blockers)

    roster = list(judge_roster or DEFAULT_JUDGE_ROSTER)
    review = {
        "schema": "apps_rg.full_resume_llm_coherence_review.v1",
        "emitted_at_utc": datetime.now(timezone.utc).isoformat(),
        "judge_roster": roster,
        "full_resume_ref": str(final_resume_path),
        "final_resume_hash": final_hash,
        "target_company": target_company,
        "target_role": target_role,
        "candidate_evidence_packet": {
            "schema": evidence_packet["schema"],
            "sha256": evidence_packet_digest,
            "section_count": len(evidence_packet["sections"]),
            "visible_claim_count": sum(
                len(section["visible_claims"])
                for section in evidence_packet["sections"]
            ),
            "selected_candidate_fact_count": sum(
                len(section["selected_candidate_facts"])
                for section in evidence_packet["sections"]
            ),
            "graph_claim_binding_count": sum(
                len(section["graph_claim_bindings"])
                for section in evidence_packet["sections"]
            ),
        },
        **agg,
        "explicit_non_claims": [
            "Section-level X2 PASS does not imply full_resume_coherence_pass.",
            "MOCKED or BLOCKED judges do not count toward quorum pass.",
            "UNKNOWN is not PASS.",
            "Targeting context is not candidate proof; the candidate evidence packet is.",
        ],
    }

    out_path = output_dir / "full_resume_llm_coherence_review.json"
    out_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review["artifact_path"] = str(out_path)

    x1d_path = output_dir / "x1d_full_resume_judge_outputs.json"
    x1d_blob = {
        "schema": "apps_rg.x1d_full_resume_judge_outputs.v1",
        "emitted_at_utc": review["emitted_at_utc"],
        "judge_roster": roster,
        "full_resume_ref": str(final_resume_path),
        "final_resume_hash": final_hash,
        "judges": review.get("judge_verdicts") or [],
        "aggregation": {
            "aggregation_method": review.get("aggregation_method"),
            "pass_threshold": review.get("pass_threshold"),
            "quorum_required": review.get("quorum_required"),
            "full_resume_coherence_pass": review.get("full_resume_coherence_pass"),
            "decisive_reason": review.get("decisive_reason"),
            "blockers": review.get("blockers"),
            "warnings": review.get("warnings"),
        },
        "explicit_non_claims": review.get("explicit_non_claims") or [],
    }
    x1d_path.write_text(json.dumps(x1d_blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review["x1d_full_resume_judge_outputs_json"] = str(x1d_path)
    return review
