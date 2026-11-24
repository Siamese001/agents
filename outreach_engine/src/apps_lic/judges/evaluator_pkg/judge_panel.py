"""Authoritative 6-lens judge panel execution for ExecutiveOutreachJudgePanel."""

from __future__ import annotations

import math
import re
from typing import List

from apps_lic.domain.models import (
    AuthoritativeVerdict,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
)
from apps_lic.judges.evaluator_pkg.report_and_rubrics import (
    EvaluationReport,
    RubricConfigAndTournamentBase,
)


class ExecutiveOutreachJudgePanel(RubricConfigAndTournamentBase):
    """Authoritative 6-lens judge panel adapting apps_rg Rubric v3 to executive outreach."""

    def evaluate_authoritative(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> AuthoritativeVerdict:
        feedback: List[str] = []
        hints: List[str] = []

        # 1. Tone
        tone_valid, tone_viols = self._tone_validator.validate(draft.body)

        # 2. Grounding
        allowed_facts = {
            f.fact_id
            for f in candidate.verified_facts
            if getattr(f, "has_provenance", False) or bool(getattr(f, "source_reference", None) and str(getattr(f, "source_reference")).strip())
        }
        opp_context = f"{' '.join(opportunity.strategic_priorities)} {opportunity.briefing_text} {opportunity.company_name}"
        g_valid, g_viols = self._grounding_validator.validate(
            draft.grounded_facts_used,
            allowed_facts,
            body=draft.body,
            candidate_facts=candidate.verified_facts,
            opportunity_context=opp_context,
        )

        # 3. Forbidden claims
        fc_valid, fc_viols = self._forbidden_validator.validate(
            draft.body, candidate.verified_facts, opportunity_context=opp_context
        )

        # 4. Question ending
        q_valid, q_err = self._question_validator.validate(draft.body)

        # 5. Spam triggers
        spam_valid, spam_viols, spam_warns = self._spam_validator.validate(draft.body)

        # 6. Em dash
        dash_valid, dash_err = self._dash_validator.validate(draft.body)

        # 7. Channel length
        len_valid, len_err = self._length_validator.validate(draft.channel, draft.body)

        # 8. Markdown links
        link_valid, link_err = self._link_validator.validate(draft.body)

        # 9. Outbound privacy & unsupported personalization
        priv_valid, priv_viols = self._privacy_validator.validate(draft.body)
        up_valid, up_viols = self._unsupported_personalization_validator.validate(draft.body, opportunity)

        violations: List[str] = list(tone_viols)
        violations.extend(g_viols)
        violations.extend(fc_viols)
        if not q_valid and q_err:
            violations.append(q_err)
        violations.extend(spam_viols)
        if not dash_valid and dash_err:
            violations.append(dash_err)
        if not len_valid and len_err:
            violations.append(len_err)
        if not link_valid and link_err:
            violations.append(link_err)
        violations.extend(priv_viols)
        violations.extend(up_viols)

        warnings: List[str] = list(spam_warns)
        hard_gate_passed = len(violations) == 0

        # Lens 1: Altitude, Persona & Peer Framing (Rubric v3 Lens 5)
        lens1_score = 1.0
        if not tone_valid:
            lens1_score = 0.3
            feedback.append(f"Lens 1 (Altitude) Failure: {', '.join(tone_viols)}")
            hints.append("Adopt peer-to-peer executive framing; eliminate subordinate job-seeking phrases.")

        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER and draft.channel == ChannelType.LINKEDIN_CONNECTION:
            lens1_score = min(lens1_score, 0.5)
            feedback.append("Lens 1 (Altitude) Warning: Board member outreach should prefer InMail or Executive Email.")
            hints.append("Upgrade channel to InMail or Executive Email for Board Member tier.")

        # Lens 2: Zero-Hallucination Grounding & Fact Binding (Rubric v3 Lens 2)
        lens2_score = 1.0
        if not g_valid:
            lens2_score = 0.0
            feedback.append(f"Lens 2 (Grounding) Failure: {', '.join(g_viols)}")
            hints.append("All claims must map directly to verified candidate facts with source evidence.")

        if not fc_valid:
            lens2_score = min(lens2_score, 0.2)
            feedback.append(f"Lens 2 (Forbidden Claims) Failure: {', '.join(fc_viols)}")
            hints.append("Remove ungrounded compensation, unverifiable tenure claims, or policy-forbidden phrasing.")

        if not priv_valid:
            lens2_score = 0.0
            feedback.append(f"Lens 2 (Outbound Privacy) Failure: {', '.join(priv_viols)}")
            hints.append("Remove API credentials, private strategy markers, and billing rate disclosures.")

        if not up_valid:
            lens2_score = min(lens2_score, 0.2)
            feedback.append(f"Lens 2 (Grounding - Unsupported Personalization) Failure: {', '.join(up_viols)}")
            hints.append("Do not assert company strategic focus or initiatives without verified research backing.")

        # Lens 3: Strategic Briefing Resonance (Rubric v3 Lens 3)
        lens3_score = 1.0
        if not up_valid:
            lens3_score = min(lens3_score, 0.2)
            feedback.append(f"Lens 3 (Resonance - Unsupported Personalization) Failure: {', '.join(up_viols)}")
            hints.append("Omit claims of specific company focus when operating under an unverified briefing.")

        company_lower = opportunity.company_name.lower()
        body_lower = draft.body.lower()
        subject_lower = draft.subject.lower()

        has_company_ref = company_lower in body_lower or company_lower in subject_lower
        if not has_company_ref:
            clean_company = re.sub(r"[,.\(\)\'\"\-\/]", " ", company_lower)
            legal_suffixes = {
                "inc", "incorporated", "corp", "corporation", "co", "company",
                "llc", "ltd", "limited", "technologies", "technology", "enterprise",
                "group", "holdings", "financial", "services", "the", "and",
            }
            brand_tokens = [tok for tok in clean_company.split() if tok and tok not in legal_suffixes and len(tok) >= 3]
            if any(tok in body_lower or tok in subject_lower for tok in brand_tokens):
                has_company_ref = True

        has_priority_ref = False
        for p in opportunity.strategic_priorities:
            tokens = [t.lower() for t in re.findall(r"\b[A-Za-z]{4,}\b", p)]
            if any(tok in body_lower for tok in tokens[:4]):
                has_priority_ref = True
                break

        if not has_company_ref and not has_priority_ref:
            lens3_score = 0.4
            feedback.append("Lens 3 (Resonance) Failure: Outreach lacks reference to company priorities or mandate.")
            hints.append("Anchor message to verified strategic priorities from company briefing.")

        # Lens 4: Friction & CTA Calibration (Rubric v3 Lens 4)
        lens4_score = 1.0
        if not q_valid and q_err:
            lens4_score = 0.4
            feedback.append(f"Lens 4 (CTA) Failure: {q_err}")
            hints.append("Conclude message with a low-friction inquiry ending with a question mark.")

        if any(w in body_lower for w in ("you must", "my demands", "give me a job", "need a response today")):
            lens4_score = min(lens4_score, 0.2)
            feedback.append("Lens 4 (CTA) Failure: High-friction or demanding call-to-action detected.")
            hints.append("Reframe call to action as a low-friction value exchange.")

        # Lens 5: Anti-Spam, Anti-Cliche & Tone Guardrails (Rubric v3 Lens 1)
        lens5_score = 1.0
        if not spam_valid:
            lens5_score = 0.2
            feedback.append(f"Lens 5 (Anti-Spam) Failure: {', '.join(spam_viols)}")
            hints.append("Eliminate sales urgency and aggressive pitching language.")
        elif spam_warns:
            lens5_score = 0.8
            feedback.append(f"Lens 5 (Anti-Spam) Warning: {', '.join(spam_warns)}")
            hints.append("Avoid corporate cliches and formulaic generic openers.")

        if not dash_valid and dash_err:
            lens5_score = min(lens5_score, 0.6)
            feedback.append(f"Lens 5 (Style) Warning: {dash_err}")
            hints.append("Replace em dashes with commas or hyphens per writing preferences.")

        comp_viols = [v for v in fc_viols if "compensation" in v.lower()]
        if comp_viols:
            lens5_score = min(lens5_score, 0.2)
            feedback.append(f"Lens 5 (Cold Outreach Guardrail) Failure: {', '.join(comp_viols)}")
            hints.append("Eliminate compensation/salary discussions prior to first reply.")

        # Lens 6: Channel & Constraint Compliance (Rubric v3 Lens 6)
        lens6_score = 1.0
        if not len_valid and len_err:
            lens6_score = 0.0
            feedback.append(f"Lens 6 (Constraints) Failure: {len_err}")
            hints.append("Trim message to stay within strict channel character ceilings.")

        if not link_valid and link_err:
            lens6_score = min(lens6_score, 0.5)
            feedback.append(f"Lens 6 (Constraints) Failure: {link_err}")
            hints.append("Use plain-text URLs instead of markdown link syntax.")

        t_lens1, t_lens2, t_lens3 = self.get_threshold("lens1_altitude", 0.70), self.get_threshold("lens2_grounding", 0.99), self.get_threshold("lens3_resonance", 0.70)
        t_lens4, t_lens5, t_lens6 = self.get_threshold("lens4_cta", 0.70), self.get_threshold("lens5_anti_spam", 0.70), self.get_threshold("lens6_constraints", 0.70)

        w_lens1, w_lens2, w_lens3 = self.get_lens_weight("lens1_altitude", 0.15), self.get_lens_weight("lens2_grounding", 0.25), self.get_lens_weight("lens3_resonance", 0.20)
        w_lens4, w_lens5, w_lens6 = self.get_lens_weight("lens4_cta", 0.15), self.get_lens_weight("lens5_anti_spam", 0.15), self.get_lens_weight("lens6_constraints", 0.10)

        composite_score = round(
            lens1_score * w_lens1 + lens2_score * w_lens2 + lens3_score * w_lens3
            + lens4_score * w_lens4 + lens5_score * w_lens5 + lens6_score * w_lens6, 4
        )
        if math.isnan(composite_score) or math.isinf(composite_score):
            composite_score = 0.0
        min_composite = self.get_min_composite_score(0.75)

        all_lenses_passed = (
            lens1_score >= t_lens1 and lens2_score >= t_lens2 and lens3_score >= t_lens3
            and lens4_score >= t_lens4 and lens5_score >= t_lens5 and lens6_score >= t_lens6
        )
        judge_passed = all_lenses_passed and (composite_score >= min_composite)

        if not (composite_score >= min_composite):
            feedback.append(f"Composite Score Failure: {composite_score:.2f} is below minimum threshold {min_composite:.2f}.")

        score_band = "EXEMPLARY" if composite_score >= 0.85 else ("ACCEPTABLE" if composite_score >= 0.70 else "FAIL")
        passed = hard_gate_passed and judge_passed
        status = "PASSED" if passed else "BLOCKED"

        failure_reasons: List[str] = []
        for v in violations:
            if v not in failure_reasons:
                failure_reasons.append(v)
        if not passed:
            for fb in feedback:
                if fb not in failure_reasons:
                    failure_reasons.append(fb)
        else:
            for fb in feedback:
                if ("Failure" in fb or "below minimum threshold" in fb) and fb not in failure_reasons:
                    failure_reasons.append(fb)

        scores = {
            "spam_score": 1.0 if spam_valid else 0.0, "length_score": 1.0 if len_valid else 0.0,
            "question_score": 1.0 if q_valid else 0.0, "grounding_score": 1.0 if g_valid else 0.0,
            "dash_score": 1.0 if dash_valid else 0.0, "link_score": 1.0 if link_valid else 0.0,
            "tone_score": 1.0 if tone_valid else 0.0, "forbidden_claims_score": 1.0 if fc_valid else 0.0,
            "privacy_score": 1.0 if priv_valid else 0.0, "unsupported_personalization_score": 1.0 if up_valid else 0.0,
        }

        lens_scores = {
            "lens1_altitude": lens1_score, "lens2_grounding": lens2_score,
            "lens3_resonance": lens3_score, "lens4_cta": lens4_score,
            "lens5_anti_spam": lens5_score, "lens6_constraints": lens6_score,
        }

        return AuthoritativeVerdict(
            passed=passed,
            status=status,
            composite_score=composite_score,
            score_band=score_band,
            hard_gate_passed=hard_gate_passed,
            judge_passed=judge_passed,
            violations=violations,
            warnings=warnings,
            failure_reasons=failure_reasons,
            lens_scores=lens_scores,
            feedback=feedback,
            remediation_hints=hints,
            scores=scores,
        )

    def report_from_verdict(self, verdict: AuthoritativeVerdict) -> EvaluationReport:
        """Derive an EvaluationReport directly from an AuthoritativeVerdict without re-evaluating."""
        def _safe_lens_score(lens_key: str, default: float = 1.0) -> float:
            val = verdict.lens_scores.get(lens_key)
            if val is None:
                return default
            try:
                fval = float(val)
                return default if (math.isnan(fval) or math.isinf(fval)) else fval
            except (ValueError, TypeError):
                return default

        l1 = _safe_lens_score("lens1_altitude")
        l2 = _safe_lens_score("lens2_grounding")
        l3 = _safe_lens_score("lens3_resonance")
        l4 = _safe_lens_score("lens4_cta")
        l5 = _safe_lens_score("lens5_anti_spam")
        l6 = _safe_lens_score("lens6_constraints")

        hop1 = min(l1, l6)
        hop2 = l2
        hop6 = min(l3, l5)
        hop8 = l4

        return EvaluationReport(
            passed=verdict.passed, status=verdict.status, judge_passed=verdict.judge_passed,
            hard_gate_passed=verdict.hard_gate_passed, lens1_altitude_score=l1, lens2_grounding_score=l2,
            lens3_resonance_score=l3, lens4_cta_score=l4, lens5_anti_spam_score=l5, lens6_constraints_score=l6,
            composite_score=verdict.composite_score, score_band=verdict.score_band,
            hop1_classifier_score=hop1, hop2_grounding_score=hop2, hop6_alignment_score=hop6, hop8_narrative_score=hop8,
            feedback=list(verdict.feedback), remediation_hints=list(verdict.remediation_hints),
            lens_scores={k: (v if v is not None else 1.0) for k, v in verdict.lens_scores.items()},
        )

    def evaluate(self, draft: OutreachMessageDraft, candidate: CandidateProfile, opportunity: TargetOpportunity) -> EvaluationReport:
        return self.report_from_verdict(self.evaluate_authoritative(draft, candidate, opportunity))

    def evaluate_ide_cli(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        *,
        agy_bin: str | None = None,
    ) -> dict[str, object]:
        """Two-stage evaluation: Stage A deterministic preflight first, Stage B Judge v3 IDE CLI second."""
        from apps_lic.judges.ide_cli_judge import call_outreach_panel_ide_cli_judge

        det_verdict = self.evaluate_authoritative(draft, candidate, opportunity)
        if not det_verdict.hard_gate_passed:
            return {
                "passed": False,
                "status": "STAGE_A_BLOCKED",
                "hard_gate_passed": False,
                "evaluator_kind": "deterministic_gate",
                "llm_judge_executed": False,
                "normalized_unit_score": None,
                "deterministic_violations": list(det_verdict.violations),
                "ide_cli_judge": None,
            }
        fact_summaries = [
            f"{f.fact_id}: {getattr(f, 'statement', getattr(f, 'claim_text', getattr(f, 'text', '')))}"
            for f in candidate.verified_facts
        ]
        cli_res = call_outreach_panel_ide_cli_judge(
            subject=draft.subject,
            body=draft.body,
            channel=str(getattr(draft.channel, "value", draft.channel)),
            recipient_class=str(getattr(opportunity.recipient_class, "value", opportunity.recipient_class)),
            verified_facts=fact_summaries,
            company_name=opportunity.company_name,
            rubric=self._active_rubric,
            pass_threshold=self.get_min_composite_score(0.80),
            agy_bin=agy_bin,
        )
        combined_passed = bool(cli_res.passed and not cli_res.provider_blocked)
        return {
            "passed": combined_passed,
            "status": "PASSED" if combined_passed else "BLOCKED",
            "hard_gate_passed": True,
            "evaluator_kind": "llm_judge" if cli_res.llm_judge_executed else "skipped",
            "llm_judge_executed": cli_res.llm_judge_executed,
            "normalized_unit_score": cli_res.normalized_unit_score,
            "deterministic_violations": [],
            "ide_cli_judge": cli_res.to_dict(),
        }


RubricJudgeEvaluator = ExecutiveOutreachJudgePanel

__all__ = [
    "ExecutiveOutreachJudgePanel",
    "RubricJudgeEvaluator",
]
