"""Draft composition and persona-tournament fact selection for PromptCompiler."""

from __future__ import annotations

import re
from typing import Any, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.compiler_pkg.signatures_and_context import PromptContextAssembler


class PromptCompiler(PromptContextAssembler):
    """Compiles prompt context slots and enforces forbidden behavior rules."""

    def _format_strategic_hook(self, raw_hook: str, company_name: Optional[str] = None) -> str:
        """Format and condense a raw priority or JD bullet into a clean conversational phrase."""
        clean = (raw_hook or "").strip().rstrip(".!?:;")
        abbrevs = {"dr", "mr", "ms", "mrs", "prof", "sr", "jr", "vs", "u.s", "inc", "corp", "ltd", "co", "e.g", "i.e"}
        for m in re.finditer(r"\.\s+", clean):
            preceding = clean[:m.start()].split()
            last_word = preceding[-1].lower() if preceding else ""
            if last_word not in abbrevs:
                clean = clean[:m.start()].strip()
                break
        for sep in ("; ", " - "):
            if sep in clean:
                clean = clean.split(sep)[0].strip()
        clean = re.sub(r"^(?:\d+[\.\)]\s*|[-*•]\s*|signal:\s*|focus:\s*)", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[A-Za-z\s]+(?:’s|\x27s)\s+immediate mandate is to\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^[A-Za-z\s]+(?:’s|\x27s)\s+organizational priorities revolve around\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^(?:A\s+)?core priority will be\s*", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"^From an architectural standpoint,\s*(?:he|she|they) (?:is|are) focused on\s*", "", clean, flags=re.IGNORECASE).strip()

        verb_map = {
            "translate": "translating", "modernize": "modernizing", "transform": "transforming",
            "optimize": "optimizing", "execute": "executing", "deliver": "delivering",
            "drive": "driving", "accelerate": "accelerating", "architect": "architecting",
            "deploy": "deploying", "migrate": "migrating", "consolidate": "consolidating",
            "streamline": "streamlining", "navigate": "navigating", "build": "building",
            "scale": "scaling", "lead": "leading", "integrate": "integrating",
            "standardize": "standardizing", "move": "moving", "generate": "generating",
            "expand": "expanding", "advance": "advancing", "establish": "establishing",
        }
        for v, g in verb_map.items():
            if re.match(rf"^{v}\b", clean, flags=re.IGNORECASE):
                clean = re.sub(rf"^{v}\b", g, clean, count=1, flags=re.IGNORECASE)
                break

        if clean and clean[0].isupper() and (len(clean) == 1 or clean[1].islower()):
            first_word = clean.split()[0].lower()
            preserved_terms = {"aws", "azure", "gcp", "ai", "ml", "the"}
            if company_name:
                for tok in re.findall(r"\b[A-Za-z]{3,}\b", company_name.lower()):
                    preserved_terms.add(tok)
            if first_word not in preserved_terms:
                clean = clean[0].lower() + clean[1:]

        if len(clean) > 90:
            words = clean.split()
            truncated = ""
            for w in words:
                if len(truncated) + len(w) + 1 > 85:
                    break
                truncated = f"{truncated} {w}" if truncated else w
            clean = truncated if truncated else " ".join(words[:10])

        return clean.strip().rstrip(".!?:;")

    def _format_fact_phrase(self, statement: str) -> str:
        """Format candidate verified fact statement into a natural lowercased clause."""
        clean = (statement or "").strip().rstrip(".!?:;")
        if not clean:
            return ""
        first_word = clean.split()[0]
        if len(first_word) > 1 and first_word.isupper():
            return clean
        if clean and clean[0].isupper() and (len(clean) == 1 or clean[1].islower()):
            clean = clean[0].lower() + clean[1:]
        return clean

    def _compose_connection_note(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        template_id: str,
        hook: str,
        fact_statement: str,
    ) -> str:
        """Compose a LinkedIn connection note strictly bounded under 300 characters."""
        fact_phrase = self._format_fact_phrase(fact_statement)
        title_short = (candidate.target_title or "").strip()
        if len(title_short) > 40:
            title_short = title_short[:38].rsplit(" ", 1)[0].rstrip(",/-")
        as_title = f"As {title_short}, " if title_short else "In leadership, "
        work_as_title = f"In my work as {title_short}, " if title_short else "In my leadership work, "
        greeting = f"Hi {opportunity.recipient_name}," if (opportunity.recipient_name or "").strip() else "Hi,"

        def _slice_fact(phrase: str, max_chars: int = 85) -> str:
            clean_p = phrase.rstrip(".")
            if len(clean_p) <= max_chars:
                return clean_p
            metric_match = re.search(r"(\$\d[\d,.]*\s*(?:[kmbKMB]|million|billion|thousand)?|\b\d+(?:\.\d+)?%)", clean_p)
            limit = max_chars - 3
            if metric_match and metric_match.end() <= max_chars + 30:
                limit = max(limit, metric_match.end() + 2)
            words = clean_p.split()
            accum = ""
            for w in words:
                if len(accum) + len(w) + 1 > limit:
                    break
                accum = f"{accum} {w}" if accum else w
            base = (accum or " ".join(words[:6])).rstrip(".,;:")
            return base if base.endswith("...") else f"{base}..."

        fact_short = _slice_fact(fact_phrase, 85)
        hook_short = hook[:45].rsplit(" ", 1)[0] if len(hook) > 48 else hook

        if template_id == "compact_recruiter_arc":
            role_s = opportunity.role_title[:35].rsplit(" ", 1)[0] if len(opportunity.role_title) > 38 else opportunity.role_title
            search_clause = f"{opportunity.company_name}'s {role_s} search in {hook_short}" if hook_short else f"{opportunity.company_name}'s {role_s} search"
            if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                body = (
                    f"{greeting}\n\n"
                    f"Great seeing your work at {opportunity.company_name}. "
                    f"Following your {role_s} search" + (f" in {hook_short}." if hook_short else ".") + " "
                    f"{as_title}{fact_short}.\n\n"
                    f"Open to connecting?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
                body = (
                    f"{greeting}\n\n"
                    f"Reaching out via mutual connection regarding {search_clause}. "
                    f"{as_title}{fact_short}.\n\n"
                    f"Open to connecting?"
                )
            else:
                body = (
                    f"{greeting}\n\n"
                    f"Following {search_clause}. "
                    f"{as_title}{fact_short}.\n\n"
                    f"Open to connecting?"
                )
        else:
            if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                work_clause = f"Following your work in {hook_short}." if hook_short else f"Following your work at {opportunity.company_name}."
                body = (
                    f"{greeting}\n\n"
                    f"Great seeing your momentum at {opportunity.company_name}. "
                    f"{work_clause} "
                    f"{work_as_title}{fact_short}.\n\n"
                    f"Open to catching up?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
                focus_clause = f"focus on {hook_short}" if hook_short else f"work in {opportunity.industry}"
                body = (
                    f"{greeting}\n\n"
                    f"Reaching out from our shared network regarding {opportunity.company_name}'s {focus_clause}. "
                    f"{work_as_title}{fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )
            elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
                focus_clause = f"focus on {hook_short}" if hook_short else f"work in {opportunity.industry}"
                body = (
                    f"{greeting}\n\n"
                    f"Following {opportunity.company_name}'s {focus_clause} from our shared circles. "
                    f"{work_as_title}{fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )
            else:
                focus_clause = f"Noticed {opportunity.company_name}'s focus on {hook_short}." if hook_short else f"Following {opportunity.company_name}'s leadership in {opportunity.industry}."
                body = (
                    f"{greeting}\n\n"
                    f"{focus_clause} "
                    f"{work_as_title}{fact_short}.\n\n"
                    f"Open to exchanging perspectives?"
                )

        body = body.replace("....", "...")
        if len(body) > 295:
            compact_fact = _slice_fact(fact_phrase, 72)
            prefix = f"Following {opportunity.company_name}'s focus on {hook_short}." if hook_short else f"Following {opportunity.company_name}'s work in {opportunity.industry}."
            body = (
                f"{greeting}\n\n"
                f"{prefix} "
                f"{as_title}{compact_fact}\n\n"
                f"Open to connecting?"
            ).replace("....", "...")
        return body

    def _compose_recruiter_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose compact 2-paragraph draft aligned with compact_recruiter_arc.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)

        if channel == ChannelType.EMAIL:
            subject = f"{candidate.full_name} / {opportunity.company_name} {opportunity.role_title} search"
        elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            subject = f"Reconnecting: {candidate.full_name} -> {opportunity.company_name} ({opportunity.role_title})"
        else:
            subject = f"{candidate.full_name} -> {opportunity.company_name} ({opportunity.role_title})"

        cand_title = (candidate.target_title or "").strip()
        as_clause = f"As {cand_title}, " if cand_title else "In my leadership work, "
        greeting = f"Hi {opportunity.recipient_name}," if (opportunity.recipient_name or "").strip() else "Hi,"

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            search_clause = f"{opportunity.company_name}'s {opportunity.role_title} search in {hook}" if hook else f"{opportunity.company_name}'s {opportunity.role_title} search"
            p1 = (
                f"Reaching out following our previous collaboration regarding {search_clause}. "
                f"{as_clause}{fact_phrase}."
            )
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            search_clause = f"{opportunity.company_name}'s {opportunity.role_title} search in {hook}" if hook else f"{opportunity.company_name}'s {opportunity.role_title} search"
            p1 = (
                f"Reaching out via mutual connection regarding {search_clause}. "
                f"{as_clause}{fact_phrase}."
            )
        else:
            priority_clause = f"regarding {opportunity.company_name}'s priorities in {hook}" if hook else f"regarding {opportunity.company_name}'s {opportunity.role_title} role"
            p1 = (
                f"Reaching out {priority_clause}. "
                f"{as_clause}{fact_phrase}."
            )

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            p2 = "Would you be open to connecting briefly to discuss the mandate?"
        else:
            p2 = "Would you be open to connecting on this role?"

        body = f"{greeting}\n\n{p1}\n\n{p2}"
        return subject, body

    def _compose_executive_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose 4-part executive arc aligned with exec_positioning.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)
        cand_title = (candidate.target_title or "").strip()
        greeting = f"Hi {opportunity.recipient_name}," if (opportunity.recipient_name or "").strip() else "Hi,"

        if channel == ChannelType.EMAIL:
            if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
                subject = f"{opportunity.company_name} {opportunity.role_title} - Strategic Governance Perspective"
            elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                subject = f"Catching up: {opportunity.company_name} / {candidate.full_name}"
            else:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"
        else:
            if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Board & Governance Alignment"
            elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
                subject = f"Catching up / {opportunity.company_name} {opportunity.role_title} perspective"
            else:
                subject = f"{opportunity.company_name} / {opportunity.role_title} - Executive Alignment"

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            opener = f"Great to see your continued momentum at {opportunity.company_name}."
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            opener = f"Reaching out following recommendations from our shared network regarding {opportunity.company_name}'s work in {hook}." if hook else f"Reaching out following recommendations from our shared network regarding {opportunity.company_name}'s {opportunity.role_title} search."
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            opener = f"Reaching out from our shared network, following {opportunity.company_name}'s focus on {hook}." if hook else f"Reaching out from our shared network, following {opportunity.company_name}'s work in {opportunity.industry}."
        elif opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            opener = f"Following {opportunity.company_name}'s strategic mandate and governance focus on {hook}." if hook else f"Following {opportunity.company_name}'s strategic mandate and leadership in {opportunity.industry}."
        else:
            opener = f"I have been following {opportunity.company_name}'s focus on {hook}." if hook else f"I have been following {opportunity.company_name}'s work in {opportunity.industry}."

        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            fit = f"In my executive leadership work as {cand_title}, {fact_phrase}." if cand_title else f"In my executive leadership work, {fact_phrase}."
        else:
            fit = f"In my recent work as {cand_title}, {fact_phrase}." if cand_title else f"In my recent leadership work, {fact_phrase}."

        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            reciprocity = "Happy to share architectural lessons and governance benchmarks from similar scale transformations."
        elif opportunity.recipient_class == RecipientClass.HIRING_MANAGER:
            reciprocity = "Happy to share our operational scaling framework and metrics if useful for your roadmap."
        elif opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            reciprocity = "Happy to compare notes and share operational lessons from similar architecture transitions."
        else:
            reciprocity = "Happy to share our operational playbook and architectural benchmarks if helpful for your roadmap."

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            ask = "Open to catching up for a brief conversation sometime next week?"
        elif opportunity.recipient_class == RecipientClass.BOARD_MEMBER:
            ask = "Given your focus, would you be open to a brief high-level conversation next week?"
        else:
            ask = "Given your focus, would you be open to a brief conversation next week?"

        p1 = f"{opener} {fit}"
        p2 = f"{reciprocity} {ask}"
        body = f"{greeting}\n\n{p1}\n\n{p2}"
        return subject, body

    def _compose_general_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType,
        hook: str,
        fact_statement: str,
    ) -> tuple[str, str]:
        """Compose general/hiring-manager draft aligned with outreach_draft_v2.yaml."""
        fact_phrase = self._format_fact_phrase(fact_statement)
        cand_title = (candidate.target_title or "").strip()
        greeting = f"Hi {opportunity.recipient_name}," if (opportunity.recipient_name or "").strip() else "Hi,"
        subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            opener = f"Great to reconnect as {opportunity.company_name} expands its focus on {hook}." if hook else f"Great to reconnect as {opportunity.company_name} expands its {opportunity.role_title} team."
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            opener = f"Reaching out via our shared network regarding {opportunity.company_name}'s work in {hook}." if hook else f"Reaching out via our shared network regarding {opportunity.company_name}'s {opportunity.role_title} role."
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            opener = f"Following {opportunity.company_name}'s work in {hook} from our shared circles." if hook else f"Following {opportunity.company_name}'s work in {opportunity.industry} from our shared circles."
        else:
            opener = f"I have been following {opportunity.company_name}'s focus on {hook}." if hook else f"I have been following {opportunity.company_name}'s work in {opportunity.industry}."

        fit = f"In my recent work as {cand_title}, {fact_phrase}." if cand_title else f"In my recent leadership work, {fact_phrase}."
        reciprocity = "Happy to share our operational scaling framework and metrics if useful for your roadmap."
        ask = "Given your focus, would you be open to a brief conversation next week?"

        p1 = f"{opener} {fit}"
        p2 = f"{reciprocity} {ask}"
        body = f"{greeting}\n\n{p1}\n\n{p2}"
        return subject, body

    def _compose_follow_up(self, candidate: CandidateProfile, opportunity: TargetOpportunity, hook: str, fact_statement: str) -> tuple[str, str]:
        fact_phrase = self._format_fact_phrase(fact_statement)
        cand_title = (candidate.target_title or "").strip()
        greeting = f"Hi {opportunity.recipient_name}," if (opportunity.recipient_name or "").strip() else "Hi,"
        subject = f"Following up: {opportunity.company_name} / {opportunity.role_title}"
        focus_clause = f"Following up on my earlier note regarding {opportunity.company_name}'s focus on {hook}." if hook else f"Following up on my earlier note regarding {opportunity.company_name}'s {opportunity.role_title} work in {opportunity.industry}."
        fit = f"In my work as {cand_title}, {fact_phrase}." if cand_title else f"In my leadership work, {fact_phrase}."
        ask = "If timing is tight right now, would it be helpful to reconnect next quarter instead?"
        return subject, f"{greeting}\n\n{focus_clause} {fit}\n\n{ask}"

    def _select_persona_tournament_lead_fact(self, candidate: CandidateProfile, opportunity: TargetOpportunity, audience_persona: Optional[AudiencePersona] = None) -> Optional[Any]:
        grounded = candidate.grounded_facts
        if not grounded or len(grounded) == 1:
            return grounded[0] if grounded else None
        priority_tokens = {tok.lower() for p in (opportunity.strategic_priorities or []) for tok in re.findall(r"\b[A-Za-z0-9]{3,}\b", str(p))}
        persona = audience_persona or AudiencePersona.EXECUTIVE_CONTACT
        best_fact, best_score = grounded[0], -1.0
        for idx, fact in enumerate(grounded):
            stmt_lower, cat_lower = str(fact.statement or "").lower(), str(getattr(fact, "category", "") or "").lower()
            score = 0.50 - (idx * 0.01) + min(sum(1 for tok in priority_tokens if tok in stmt_lower) * 0.15, 0.30) + (0.10 if getattr(fact, "metric", None) else 0.0)
            if (persona == AudiencePersona.EXECUTIVE_RECRUITER and cat_lower in {"leadership", "scale"}) or (persona == AudiencePersona.EXECUTIVE_CONTACT and cat_lower in {"governance", "scale", "strategy"}):
                score += 0.10
            if score > best_score:
                best_score, best_fact = score, fact
        return best_fact

    def render_draft_message(self, candidate: CandidateProfile, opportunity: TargetOpportunity, channel: ChannelType, audience_persona: Optional[AudiencePersona] = None) -> tuple[str, str, list[str]]:
        context = self.assemble_context(candidate, opportunity, channel, audience_persona)
        template_id = context["template_id"]
        lead_fact = self._select_persona_tournament_lead_fact(candidate, opportunity, audience_persona)
        fact_statement = lead_fact.statement if lead_fact else candidate.executive_summary
        fact_ids = [lead_fact.fact_id] if lead_fact else []

        sealed = getattr(opportunity, "sealed_resolution", None) or {}
        is_verified = bool(sealed.get("is_verified", True))
        if sealed.get("resolution_source") == "HERMETIC_FALLBACK":
            is_verified = False
        brief_text = getattr(opportunity, "briefing_text", "") or ""
        if "UNVERIFIED OFFLINE FALLBACK" in brief_text:
            is_verified = False

        has_verified_priorities = bool(is_verified and opportunity.strategic_priorities)
        raw_hook = opportunity.strategic_priorities[0] if has_verified_priorities else ""
        hook = self._format_strategic_hook(raw_hook, company_name=opportunity.company_name) if raw_hook else ""

        if channel == ChannelType.LINKEDIN_CONNECTION:
            body = self._compose_connection_note(candidate, opportunity, template_id, hook, fact_statement)
            if len(body) > 300:
                from apps_lic.domain.repair import DeterministicDraftRepairer
                body = DeterministicDraftRepairer._trim_connection_note(body, max_len=295)
            return "", body, fact_ids
        elif channel == ChannelType.FOLLOW_UP:
            subject, body = self._compose_follow_up(candidate, opportunity, hook, fact_statement)
        elif template_id == "compact_recruiter_arc":
            subject, body = self._compose_recruiter_draft(candidate, opportunity, channel, hook, fact_statement)
        elif template_id == "exec_positioning":
            subject, body = self._compose_executive_draft(candidate, opportunity, channel, hook, fact_statement)
        else:
            subject, body = self._compose_general_draft(candidate, opportunity, channel, hook, fact_statement)

        from apps_lic.domain.repair import DeterministicDraftRepairer
        body, subject = DeterministicDraftRepairer.repair_text(
            body=body,
            subject=subject,
            channel=channel,
            persona=audience_persona,
        )

        return subject, body, fact_ids

    @staticmethod
    def build_templated_system_instructions(context: Dict[str, Any]) -> Any:
        """Build Antigravity SDK TemplatedSystemInstructions from compiled prompt context."""
        from tools.unified_agent_architecture import TemplatedSystemInstructions

        forbidden = "\n".join(context.get("forbidden_behaviors") or [])
        return TemplatedSystemInstructions(
            identity=f"{context.get('candidate_name', 'Executive')} ({context.get('candidate_title', 'Leader')})",
            guidelines=forbidden,
            communication_style=str(context.get("tone", "professional")),
        )


__all__ = ["PromptCompiler"]
