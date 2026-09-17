"""Causal allocation engine for mandatory run outputs."""
from __future__ import annotations

from typing import Any

from .constants import *
from .helpers import *
from .judge_parsers import *
from .section_lane_tables import *
from .causal_plan import *

__all__ = ['_causal_allocation']

def _causal_allocation(section: dict[str, Any]) -> dict[str, Any]:
    classification = str(section.get("failure_classification") or "").lower()
    section_id = str(section.get("section") or "")
    gate_ids = _failed_gate_ids(section)
    if "output contract" in classification:
        bullet_gate = _gate_reason(section, "bullet_count")
        ledger_gate = _gate_reason(section, "claim_ledger")
        source_gate = _gate_reason(section, "source_fact")
        return {
            "dominant_cause": "The runtime accepted provider output but the parser/schema/ledger contract emitted an empty product artifact.",
            "retry_recoverability": "LOW",
            "retry_recoverability_reason": "Additional model attempts cannot repair a parser and claim-ledger path that converts generated bullets into zero product bullets and zero claims.",
            "allocation": [
                _allocation_row(
                    domain="Parser / normalization contract",
                    causal_role="PRIMARY",
                    root_cause_link=bullet_gate or "The bullet-count gate observed an empty parsed bullet artifact.",
                    work_share="40%",
                    evidence_refs=["x2_insurtech_bullets_bullet_count_3"],
                    required_work="Normalize provider JSON into the canonical bullet schema before X2 and fail closed before display when parsing yields zero bullets.",
                ),
                _allocation_row(
                    domain="Claim ledger / provenance contract",
                    causal_role="CONTRIBUTING",
                    root_cause_link=ledger_gate or source_gate or "The claim ledger lacked claim_text and supported source_fact_ids for generated claims.",
                    work_share="30%",
                    evidence_refs=[
                        "x2_claim_ledger_claim_text_non_empty",
                        "x2_insurtech_bullets_source_fact_ids_supported",
                    ],
                    required_work="Emit claim_text and source_fact_ids during parsing so every bullet is provenance-bound before judge or gate review.",
                ),
                _allocation_row(
                    domain="Validation / gate precision",
                    causal_role="DETECTION",
                    root_cause_link="X2 detected empty bullets and ledger rows, but the RCA must preserve which parser/schema contract produced the empty artifact.",
                    work_share="15%",
                    evidence_refs=gate_ids,
                    required_work="Attach parser input/output references and failed field names to the gate evidence.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="LOW_RECOVERY",
                    root_cause_link="Retries target the model, while the observed failure is an empty parsed artifact after generation.",
                    work_share="15%",
                    evidence_refs=["self_consistency_paths.json", "parsed_output.json"],
                    required_work="Allow retry only after parser and claim-ledger contracts prove they can preserve a valid generated payload.",
                ),
            ],
        }
    if "specificity" in classification:
        specificity_gate = _gate_reason(section, "technical_specificity")
        return {
            "dominant_cause": "The generated narrative was not constrained to include an evidence-backed mechanism token before deterministic specificity validation.",
            "retry_recoverability": "HIGH",
            "retry_recoverability_reason": "A targeted repair can add a source-backed mechanism or technology token without changing the underlying evidence set.",
            "allocation": [
                _allocation_row(
                    domain="Generation instruction / output control",
                    causal_role="PRIMARY",
                    root_cause_link=specificity_gate or "The specificity gate found no named mechanism or technology token in display text.",
                    work_share="45%",
                    evidence_refs=["x2_narrative_technical_specificity_floor"],
                    required_work="Bind the narrative prompt and repair step to accepted source-backed mechanism vocabulary.",
                ),
                _allocation_row(
                    domain="Claim ledger / provenance contract",
                    causal_role="CONTRIBUTING",
                    root_cause_link="The accepted mechanism must be present in both display text and the claim ledger, not only in hidden evidence.",
                    work_share="20%",
                    evidence_refs=["claim_ledger.json", "text_claim_coverage.json"],
                    required_work="Expose the mechanism token in claim text and source_fact_ids before the specificity gate runs.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="HIGH_RECOVERY",
                    root_cause_link="The lane had supported content but missed a deterministic token, so gate-aware text repair is the correct retry shape.",
                    work_share="25%",
                    evidence_refs=["x2_narrative_technical_specificity_floor", "section_repair_ledger.json"],
                    required_work="Trigger a targeted rewrite that only inserts an evidence-backed mechanism token.",
                ),
                _allocation_row(
                    domain="Validation / gate precision",
                    causal_role="DETECTION",
                    root_cause_link="The gate names the missing token class but should also emit the accepted vocabulary and evidence source used for repair.",
                    work_share="10%",
                    evidence_refs=["x2_gate_outputs.json"],
                    required_work="Include accepted mechanism vocabulary and source-fact anchors in the gate receipt.",
                ),
            ],
        }
    if "executive summary synthesis contract" in classification:
        utilization_gate = _gate_reason(section, "allowed_fact_utilization")
        synthesis_gate = _gate_reason(section, "synthesis_quality")
        transition_gate = _gate_reason(section, "robotic_transition")
        conflation_gate = _gate_reason(section, "cross_fact_conflation")
        return {
            "dominant_cause": "The executive-summary repair path let a word-budget candidate become final without re-closing brushstroke utilization and transition-shape gates.",
            "retry_recoverability": "MEDIUM",
            "retry_recoverability_reason": "Blind retry can recreate the same bridge stack, but producer-side rebinding and transition repair can recover without changing the evidence substrate.",
            "allocation": [
                _allocation_row(
                    domain="Producer finalization / repair ordering",
                    causal_role="PRIMARY",
                    root_cause_link=synthesis_gate
                    or transition_gate
                    or "The final producer accepted text that still carried robotic S2-S5 transition openers.",
                    work_share="35%",
                    evidence_refs=[
                        "x2_executive_summary_synthesis_quality",
                        "x2_exec_summary_robotic_transition_stack_zero",
                    ],
                    required_work="Apply bridge-density repair after all final polish and word-budget rewrites, then re-run the same synthesis-shape predicate X2 uses.",
                ),
                _allocation_row(
                    domain="Composition-plan brushstroke coverage",
                    causal_role="CONTRIBUTING",
                    root_cause_link=utilization_gate
                    or "The claim ledger dropped the B4 commercialization-leadership fact required by the composition plan.",
                    work_share="30%",
                    evidence_refs=["x2_exec_summary_allowed_fact_utilization"],
                    required_work="Preserve at least one cited source fact for every required B1-B4 brushstroke group after display-ledger reconciliation.",
                ),
                _allocation_row(
                    domain="Claim attribution density",
                    causal_role="CONTRIBUTING",
                    root_cause_link=conflation_gate
                    or "Density repair must choose direct supporting facts instead of carrying every adjacent source_fact_id.",
                    work_share="20%",
                    evidence_refs=["x2_exec_summary_cross_fact_conflation_zero", "claim_ledger.json"],
                    required_work="Cap each sentence row to the direct proof facts while preferring composition-required facts when multiple facts compete.",
                ),
                _allocation_row(
                    domain="Validation / RCA reporting",
                    causal_role="DETECTION",
                    root_cause_link="The mandatory output must allocate deterministic executive-summary gate failures to the producer contract instead of generic validation precision.",
                    work_share="15%",
                    evidence_refs=gate_ids or ["x2_gate_outputs.json"],
                    required_work="Classify executive-summary deterministic gate families with sentence-shape, brushstroke, and attribution-density RCA rows.",
                ),
            ],
        }
    if "headline executive positioning contract" in classification:
        abstraction_gate = _gate_reason(section, "executive_abstraction_floor")
        vendor_gate = _gate_reason(section, "vendor_terms_proof_only")
        return {
            "dominant_cause": "The headline producer let a vendor-specific migration phrase remain in display position instead of projecting it to a proof-backed executive operating abstraction.",
            "retry_recoverability": "HIGH_AFTER_NORMALIZATION_FIX",
            "retry_recoverability_reason": "The selected proof was valid and judges passed; deterministic normalization can recover by rewriting the display segment and ledger before X2.",
            "allocation": [
                _allocation_row(
                    domain="Headline normalization / display policy",
                    causal_role="PRIMARY",
                    root_cause_link=abstraction_gate
                    or vendor_gate
                    or "X2 observed a headline segment missing executive abstraction while carrying a vendor/tool term.",
                    work_share="45%",
                    evidence_refs=[
                        "x2_headline_executive_abstraction_floor",
                        "x2_headline_vendor_terms_proof_only",
                    ],
                    required_work="Rewrite vendor-specific migration phrases to allowed executive headline abstractions before display validation.",
                ),
                _allocation_row(
                    domain="Claim ledger segment rebinding",
                    causal_role="CONTRIBUTING",
                    root_cause_link="Headline segment rewrites must also update claim_text rows so visible X/Y/Z phrases remain the ledger authority.",
                    work_share="25%",
                    evidence_refs=["claim_ledger.json", "parsed_output.json"],
                    required_work="Rebuild the three segment claim-ledger rows after deterministic headline phrase repair.",
                ),
                _allocation_row(
                    domain="Validation / gate precision",
                    causal_role="DETECTION",
                    root_cause_link="The deterministic headline gates correctly blocked a proof-only vendor term in display despite model-backed judge passes.",
                    work_share="20%",
                    evidence_refs=["x2_gate_outputs.json"],
                    required_work="Keep display-policy X2 gates authoritative over X1D judge approval for headline formatting and abstraction constraints.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="HIGH_RECOVERY",
                    root_cause_link="The failure is a deterministic phrase-normalization gap, so a targeted repair fixture should recover without changing research or section evidence.",
                    work_share="10%",
                    evidence_refs=["headline_output.txt"],
                    required_work="Rerun after the live failed headline fixture proves X2 clears with the repaired segment.",
                ),
            ],
        }
    if "x1d decisive judge failure" in classification:
        judge_evidence = _judge_failure_evidence(section)
        return {
            "dominant_cause": "The section was generated, parsed, and X2-clean, but the published claim ledger lost source-fact bindings that X1D required for judge-visible material claims.",
            "retry_recoverability": "LOW_UNTIL_LEDGER_FIX",
            "retry_recoverability_reason": "Blind regeneration can return a valid parsed claim ledger again, but the same lossy normalization path will keep dropping support before X1D.",
            "allocation": [
                _allocation_row(
                    domain="Claim ledger normalization",
                    causal_role="PRIMARY",
                    root_cause_link=judge_evidence
                    or "The decisive judge rejected a material claim because the published claim ledger omitted its supporting source_fact_id.",
                    work_share="45%",
                    evidence_refs=["parsed_output.json", "claim_ledger.json", "x1d_llm_judge_outputs.json"],
                    required_work="Preserve valid source_fact_ids from parsed narrative claim_ledger rows when publishing the single-sentence role-episode ledger.",
                ),
                _allocation_row(
                    domain="Narrative source binding",
                    causal_role="CONTRIBUTING",
                    root_cause_link="Narrative material phrases such as insurance operations, model risk, and traceable controls must bind to selected role-episode facts before judge review.",
                    work_share="25%",
                    evidence_refs=["selected_fact_plan.json", "role_episode_lane.py"],
                    required_work="Add deterministic phrase-to-fact reconciliation for EY narrative material claims within the allowed graph packet.",
                ),
                _allocation_row(
                    domain="X1D authorization policy",
                    causal_role="DETECTION",
                    root_cause_link="X2 PASS and product PASS were not enough because the model-backed judge rejected factual support.",
                    work_share="20%",
                    evidence_refs=["x3_disposition.json", "x1d_llm_judge_outputs.json"],
                    required_work="Keep X3 blocked on decisive factual-support judge failures and surface the judge finding as the primary RCA.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="LOW_RECOVERY",
                    root_cause_link="The fix belongs at the parser/ledger boundary, not in downstream rerun scheduling or final assembly.",
                    work_share="10%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Rerun only after the narrative ledger preservation fixture and mandatory-RCA fixture pass.",
                ),
            ],
        }
    if "evidence mapping" in classification:
        if str(section.get("section") or "") == "executive_summary":
            paragraph_gate = _gate_reason(section, "paragraph_max_words")
            mechanism_gate = _gate_reason(section, "no_mechanism_inventory")
            conflation_gate = _gate_reason(section, "cross_fact_conflation")
            return {
                "dominant_cause": "The executive summary can over-compress platform, modernization, governance, and alliance facts into dense sentences before X2 attribution gates run.",
                "retry_recoverability": "MEDIUM",
                "retry_recoverability_reason": "Blind retries can repeat the density pattern, but gate-aware synthesis repair plus deterministic density trimming can recover without changing the research substrate.",
                "allocation": [
                    _allocation_row(
                        domain="Synthesis density / prose shaping",
                        causal_role="PRIMARY",
                        root_cause_link=paragraph_gate or mechanism_gate or "Failed gates show over-budget prose or mechanism-inventory wording in the executive summary.",
                        work_share="40%",
                        evidence_refs=[
                            "x2_exec_summary_paragraph_max_words",
                            "x2_exec_summary_no_mechanism_inventory",
                        ],
                        required_work="Constrain the repair prompt and deterministic polish chain to produce six sentences under the word ceiling without mechanism inventories.",
                    ),
                    _allocation_row(
                        domain="Claim attribution density",
                        causal_role="CONTRIBUTING",
                        root_cause_link=conflation_gate or "A claim-ledger row carried too many distinct source_fact_ids for a single displayed sentence.",
                        work_share="30%",
                        evidence_refs=["x2_exec_summary_cross_fact_conflation_zero"],
                        required_work="Keep each claim-ledger row bound to the directly supporting facts for that sentence and split or compact overloaded proof themes.",
                    ),
                    _allocation_row(
                        domain="Validation / gate precision",
                        causal_role="DETECTION",
                        root_cause_link="X2 identified the exact failed executive-summary gates, but the run RCA must preserve sentence-level failure details.",
                        work_share="20%",
                        evidence_refs=gate_ids,
                        required_work="Emit sentence index, word count, mechanism hits, and source_fact_id counts in executive-summary gate evidence.",
                    ),
                    _allocation_row(
                        domain="Retry / repair policy",
                        causal_role="RECOVERY",
                        root_cause_link="Repair must be allowed to reduce source-fact density when the failing gate is over-compression, not treat fact-count reduction as a substance regression.",
                        work_share="10%",
                        evidence_refs=["synthesis_regen_receipt.json", "exec_summary_word_budget_repair_receipt.json"],
                        required_work="Let density-specific repairs reduce over-packed source_fact_ids while preserving six claim rows and required brushstroke coverage.",
                    ),
                ],
            }
        graph_gate = _gate_reason(section, "competencies_graph_granularity")
        term_gate = _gate_reason(section, "term_supported")
        ledger_gate = _gate_reason(section, "all_terms_source_fact_ids")
        confidence_gate = _gate_reason(section, "confidence")
        return {
            "dominant_cause": "The visible competency surface can be assembled before category, term, confidence, and graph lineage proof is complete.",
            "retry_recoverability": "LOW",
            "retry_recoverability_reason": "Blind retries regenerate text against the same incomplete proof contract; only gate-aware lineage repair can recover it.",
            "allocation": [
                _allocation_row(
                    domain="Evidence substrate / graph lineage",
                    causal_role="PRIMARY",
                    root_cause_link=graph_gate or term_gate or "Failed gates show missing category source facts or unsupported visible terms.",
                    work_share="45%",
                    evidence_refs=[
                        "x2_competencies_graph_granularity_gates",
                        "x2_competency_term_supported",
                    ],
                    required_work="Add category-level source-fact coverage and remove or bind unsupported visible terms before display.",
                ),
                _allocation_row(
                    domain="Artifact transformation contract",
                    causal_role="CONTRIBUTING",
                    root_cause_link=ledger_gate or confidence_gate or "Selected graph evidence was not preserved into per-term source_fact_ids and per-category confidence.",
                    work_share="25%",
                    evidence_refs=[
                        "x2_all_terms_source_fact_ids",
                        "x2_competencies_per_category_confidence_nonconstant",
                    ],
                    required_work="Make graph selection, claim ledger, category confidence, and display a lossless transformation contract.",
                ),
                _allocation_row(
                    domain="Validation / gate precision",
                    causal_role="DETECTION",
                    root_cause_link="The gates detected missing lineage, but the RCA must preserve the exact category, term, source fact, and owning producer.",
                    work_share="20%",
                    evidence_refs=gate_ids,
                    required_work="Emit a category-by-category repair matrix in the gate receipt and RCA.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="LOW_RECOVERY",
                    root_cause_link="More candidate generations cannot satisfy missing source_fact_ids or unsupported graph terms unless the repair step fills lineage first.",
                    work_share="10%",
                    evidence_refs=["self_consistency_paths.json", "section_repair_ledger.json"],
                    required_work="Replace blind retry with gate-aware lineage repair for missing facts, terms, and confidence.",
                ),
            ],
        }
    if "provider capability" in classification:
        pre_run = _pre_run_reason(section)
        return {
            "dominant_cause": "The selected Anthropic model rejected a request field that the transport still emitted unconditionally.",
            "retry_recoverability": "NONE",
            "retry_recoverability_reason": "Repeating the same request cannot recover while the serialized payload contains the deprecated temperature field.",
            "allocation": [
                _allocation_row(
                    domain="Provider capability contract",
                    causal_role="PRIMARY",
                    root_cause_link=pre_run or "Anthropic returned HTTP 400 for deprecated temperature.",
                    work_share="55%",
                    evidence_refs=["self_consistency_paths.json", "provider_request.json"],
                    required_work="Sanitize Anthropic payloads by model capability before sending HTTP requests.",
                ),
                _allocation_row(
                    domain="Model pin / provider profile",
                    causal_role="CONTRIBUTING",
                    root_cause_link="The generation model changed to Claude Sonnet 5 without updating transport capability rules.",
                    work_share="25%",
                    evidence_refs=["apps_rg/config/provider_profiles.yaml", "config/model_catalog.json"],
                    required_work="Keep provider profile model changes paired with transport capability tests.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="DETECTION",
                    root_cause_link="The no-candidate selector error must carry the first provider HTTP error.",
                    work_share="20%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON, "integrated_lane_pre_run_failure.json"],
                    required_work="Propagate first provider failure details into mandatory run RCA records.",
                ),
            ],
        }
    if "selector timeout" in classification:
        pre_run = _pre_run_reason(section)
        return {
            "dominant_cause": "The competencies selector provider request exceeded its configured wall-clock budget before a selection response was available.",
            "retry_recoverability": "MEDIUM",
            "retry_recoverability_reason": "A rerun can recover after increasing the bounded selector budget or reducing selector payload size; blind downstream retries cannot recover before competencies selects.",
            "allocation": [
                _allocation_row(
                    domain="Provider selector budget",
                    causal_role="PRIMARY",
                    root_cause_link=pre_run or "The selector timing receipt reported selector_timeout.",
                    work_share="55%",
                    evidence_refs=["integrated_lane_pre_run_failure.json", "bullet_pool_claude_selector_timing.json"],
                    required_work="Use a selector timeout budget sized for competencies graph-pool selection and keep it bounded by the shared provider ceiling.",
                ),
                _allocation_row(
                    domain="Selector payload / candidate pool",
                    causal_role="CONTRIBUTING",
                    root_cause_link="Competencies graph-pool selection ranks a larger structured candidate set than ordinary bullet selectors.",
                    work_share="20%",
                    evidence_refs=["bullet_pool_claude_selector_provider_request.json"],
                    required_work="Keep candidate payload compact and preserve request artifacts so slow selector paths can be inspected.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="MEDIUM_RECOVERY",
                    root_cause_link="The lane has no run directory until the selector returns, so retries must target selector execution before downstream lanes.",
                    work_share="15%",
                    evidence_refs=["full_run_section_status.json"],
                    required_work="Route retry to competencies selector execution, then schedule downstream lanes only after competencies product authorization.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="DETECTION",
                    root_cause_link="Mandatory outputs must distinguish provider selector timeout from PHASE1 dependency-token blockers.",
                    work_share="10%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Classify selector timeouts as provider-selector budget failures in BCG/RCA output.",
                ),
            ],
        }
    if "provider quorum" in classification:
        quorum_gate = _gate_reason(section, "full_resume_llm_coherence", "quorum")
        return {
            "dominant_cause": "The final aggregation judge panel could not count enough model-backed full-resume coherence verdicts to satisfy quorum.",
            "retry_recoverability": "HIGH_AFTER_ARTIFACT_FIX",
            "retry_recoverability_reason": "A rerun can recover after repairing the provider artifact path/transport blocker; blind reruns before that fix reproduce the same zero-quorum result.",
            "allocation": [
                _allocation_row(
                    domain="Provider artifact persistence",
                    causal_role="PRIMARY",
                    root_cause_link=quorum_gate or "Provider request artifact writes failed before Gemini/OpenAI could produce model-backed verdicts.",
                    work_share="45%",
                    evidence_refs=[
                        "coherence_judge_providers/*provider_request*.json",
                        "x1d_full_resume_judge_outputs.json",
                    ],
                    required_work="Make X1D provider request/response artifact paths compact and long-path safe before provider calls run.",
                ),
                _allocation_row(
                    domain="Judge panel quorum",
                    causal_role="CONTRIBUTING",
                    root_cause_link="The aggregation contract requires two model-backed pass verdicts; blocked providers do not count toward quorum.",
                    work_share="25%",
                    evidence_refs=["full_resume_llm_coherence_review.json"],
                    required_work="Preserve fail-closed quorum semantics and rerun the required Gemini/OpenAI full-resume judges after artifact persistence is repaired.",
                ),
                _allocation_row(
                    domain="Product authorization gate",
                    causal_role="DETECTION",
                    root_cause_link="Final resume output remained unauthorized because x2_full_resume_llm_coherence_aggregation did not pass.",
                    work_share="20%",
                    evidence_refs=gate_ids or ["final_resume_x2_gate_outputs.json"],
                    required_work="Continue withholding inline resume/DOCX authorization until final aggregation X2 and product gates pass in the same run root.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="REPORTING_GAP",
                    root_cause_link="Mandatory outputs must distinguish final judge provider quorum from missing upstream generated lanes.",
                    work_share="10%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Name provider_blocked_count, model_backed_pass_count, quorum_required, and failed aggregation gate IDs in RCA outputs.",
                ),
            ],
        }
    if "upstream certification" in classification:
        upstream_gate = _gate_reason(section, "latest_successful_real", "resolution not accepted")
        return {
            "dominant_cause": "Final aggregation refused a required section whose evidence was generated but not product-certified.",
            "retry_recoverability": "HIGH_AFTER_SECTION_REPAIR",
            "retry_recoverability_reason": "Aggregation can recover only after the blocking section repairs its judge-visible defect and returns X3_ALLOW in the same run root.",
            "allocation": [
                _allocation_row(
                    domain="Section certification / X3 authority",
                    causal_role="PRIMARY",
                    root_cause_link=upstream_gate or "A required section resolved to review-only/non-certified rather than latest-successful-real.",
                    work_share="50%",
                    evidence_refs=["final_resume_x2_gate_outputs.json", MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Surface the blocking section, X3 code, publish disposition, and blocking judge ids in final aggregation evidence.",
                ),
                _allocation_row(
                    domain="Section producer / deterministic gates",
                    causal_role="CONTRIBUTING",
                    root_cause_link="The blocking section passed deterministic X2 while still failing judge-visible certification quality.",
                    work_share="25%",
                    evidence_refs=["x2_gate_outputs.json", "x1d_llm_judge_outputs.json"],
                    required_work="Move the judge-observed defect into deterministic shape gates or same-authority regeneration before X1D.",
                ),
                _allocation_row(
                    domain="Product authorization gate",
                    causal_role="DETECTION",
                    root_cause_link="Final assembly correctly withheld authorization because X2 PASS without X1D certification is review-only.",
                    work_share="15%",
                    evidence_refs=["x3_disposition.json", "full_run_section_status.json"],
                    required_work="Keep latest-successful-real resolution tied to X3_ALLOW and product authorization, not merely runtime REAL_LLM.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="REPORTING_GAP",
                    root_cause_link="Mandatory outputs must distinguish non-certified upstream sections from provider quorum and missing-lane dependency failures.",
                    work_share="10%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Classify upstream section certification failures with their blocking section and judge evidence.",
                ),
            ],
        }
    if "pre-run" in classification:
        pre_run = _pre_run_reason(section)
        return {
            "dominant_cause": "A downstream lane was evaluated without an upstream product-authorization token.",
            "retry_recoverability": "NONE",
            "retry_recoverability_reason": "The dependent lane cannot recover through generation retries until the upstream lane is product-authorized.",
            "allocation": [
                _allocation_row(
                    domain="Orchestration / dependency control",
                    causal_role="PRIMARY",
                    root_cause_link=pre_run or "The pre-run receipt reports an upstream lane was not finalized.",
                    work_share="55%",
                    evidence_refs=["integrated_lane_pre_run_failure.json"],
                    required_work="Represent upstream lane product authorization as an explicit dependency token.",
                ),
                _allocation_row(
                    domain="Aggregation / product authorization",
                    causal_role="CONTRIBUTING",
                    root_cause_link="The dependent narrative must not schedule until its upstream bullets lane is certified.",
                    work_share="25%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Consume the upstream token before dependent-lane scheduling.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="NO_RECOVERY",
                    root_cause_link="No model retry can create the missing upstream authorization token.",
                    work_share="10%",
                    evidence_refs=["integrated_lane_pre_run_failure.json"],
                    required_work="Route retries to the upstream blocked lane, not the dependent lane.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="REPORTING_GAP",
                    root_cause_link="The operator output must name the upstream blocker, artifact, and lane token that is missing.",
                    work_share="10%",
                    evidence_refs=["integrated_lane_pre_run_failure.json"],
                    required_work="Surface upstream lane, missing token, and repair order in the RCA.",
                ),
            ],
        }
    if section_id == FINAL_AGGREGATION_LANE:
        return {
            "dominant_cause": "Final assembly depends on the required-lane authorization ledger and correctly remained blocked.",
            "retry_recoverability": "NONE",
            "retry_recoverability_reason": "Aggregation cannot recover until upstream blocked and not-run required lanes become product-authorized in the same run root.",
            "allocation": [
                _allocation_row(
                    domain="Aggregation / product authorization",
                    causal_role="PRIMARY",
                    root_cause_link="The mandatory section ledger contains blocked, pre-run-blocked, or not-run required lanes.",
                    work_share="60%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Compute final aggregation eligibility directly from the required-lane product-authorization ledger.",
                ),
                _allocation_row(
                    domain="Orchestration / dependency control",
                    causal_role="CONTRIBUTING",
                    root_cause_link="Final assembly must wait for upstream lane tokens rather than inferred run completion.",
                    work_share="20%",
                    evidence_refs=[FULL_RUN_SECTION_STATUS_JSON],
                    required_work="Require same-run product-authorization tokens for every required section.",
                ),
                _allocation_row(
                    domain="Retry / repair policy",
                    causal_role="NO_RECOVERY",
                    root_cause_link="Retrying aggregation cannot repair missing upstream product authorization.",
                    work_share="10%",
                    evidence_refs=[FULL_RUN_SECTION_STATUS_JSON],
                    required_work="Route repair to the blocking lanes before aggregation.",
                ),
                _allocation_row(
                    domain="Observability / RCA reporting",
                    causal_role="REPORTING_GAP",
                    root_cause_link="The output must name every non-authorized required lane that prevents assembly.",
                    work_share="10%",
                    evidence_refs=[MANDATORY_RUN_OUTPUT_JSON],
                    required_work="Emit a missing-lane manifest in the aggregation RCA.",
                ),
            ],
        }
    return {
        "dominant_cause": "The failed gate evidence has not been allocated to one owning runtime contract.",
        "retry_recoverability": "UNKNOWN",
        "retry_recoverability_reason": "Recoverability cannot be assessed until the owning contract is identified.",
        "allocation": [
            _allocation_row(
                domain="Validation / gate precision",
                causal_role="PRIMARY",
                root_cause_link="The available failed gates do not name a precise owning producer, parser, or validator contract.",
                work_share="100%",
                evidence_refs=gate_ids or ["x3_disposition.json"],
                required_work="Trace the failed evidence to the runtime contract that first allowed invalid state.",
            )
        ],
    }

