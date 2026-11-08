"""Deterministic formatting and channel constraint repair engine for outreach drafts."""

from __future__ import annotations

import re
from typing import Optional

from apps_lic.domain.models import (
    AudiencePersona,
    ChannelType,
    OutreachMessageDraft,
)
from apps_lic.domain.validators import _CHANNEL_MAX_CHARS


class DeterministicDraftRepairer:
    """Repairs syntax, channel lengths, formatting, and tone deterministically before final judge evaluation."""

    _MD_LINK_PAT = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
    _SUBORDINATE_REPLACEMENTS = [
        (re.compile(r"\bwould love to learn more\b", re.IGNORECASE), "open to exchanging perspectives"),
        (re.compile(r"\bthink I(?:'d| would) be a (?:great|perfect) fit\b", re.IGNORECASE), "see strong strategic alignment"),
        (re.compile(r"\bhoping for an? (?:opportunity|interview|chance)\b", re.IGNORECASE), "exploring potential alignment"),
        (re.compile(r"\bgive me a (?:chance|shot)\b", re.IGNORECASE), "open to a conversation"),
        (re.compile(r"\bplease consider my (?:application|resume|c\.?v\.?)\b", re.IGNORECASE), "sharing my background"),
        (re.compile(r"\bseeking a (?:role|job|position)\b", re.IGNORECASE), "targeting leadership opportunities"),
        (re.compile(r"\bgrateful for any (?:role|job|position|opportunity)\b", re.IGNORECASE), "open to exploratory discussion"),
    ]

    @classmethod
    def repair_text(
        cls,
        body: Optional[str],
        subject: str = "",
        channel: Optional[ChannelType] = None,
        persona: Optional[AudiencePersona] = None,
    ) -> tuple[str, str]:
        """Performs deterministic repairs on body and subject text."""
        repaired_body = str(body or "")
        repaired_subject = str(subject or "")

        # 1. Neutralize em dashes
        repaired_body = repaired_body.replace("—", ", ").replace("\u2014", ", ")
        repaired_body = re.sub(r"\s*--\s*", ", ", repaired_body)
        repaired_subject = repaired_subject.replace("—", "-").replace("\u2014", "-")
        repaired_subject = re.sub(r"\s*--\s*", " - ", repaired_subject)

        # 2. Neutralize markdown links to plain URLs
        repaired_body = cls._MD_LINK_PAT.sub(r"\1 (\2)", repaired_body)

        # 3. Normalize subordinate or deferential phrasing
        for pat, repl in cls._SUBORDINATE_REPLACEMENTS:
            repaired_body = pat.sub(repl, repaired_body)

        # 4. Clean consecutive blank lines and trailing spaces
        repaired_body = re.sub(r"[ \t]+$", "", repaired_body, flags=re.MULTILINE)
        repaired_body = re.sub(r"\n{3,}", "\n\n", repaired_body).strip()

        # 5. Channel length bounding
        eff_channel = channel or ChannelType.LINKEDIN_INMAIL
        ceiling = _CHANNEL_MAX_CHARS.get(eff_channel, 2000)
        inquiry_reserve = 80 if not repaired_body.strip().endswith("?") else 0
        target_len = max(50, ceiling - 10 - inquiry_reserve)

        if eff_channel == ChannelType.LINKEDIN_CONNECTION and len(repaired_body) > 300:
            repaired_body = cls._trim_connection_note(repaired_body, max_len=295)
        elif len(repaired_body) > target_len:
            repaired_body = cls._trim_generic_body(repaired_body, max_len=target_len)

        # 6. Ensure low-friction question ending
        repaired_body = cls._ensure_question_ending(repaired_body, eff_channel, persona)

        # Re-check channel length after question ending for ALL channels
        if eff_channel == ChannelType.LINKEDIN_CONNECTION and len(repaired_body) > 300:
            repaired_body = cls._trim_connection_note(repaired_body, max_len=295)
        elif len(repaired_body) > ceiling:
            repaired_body = cls._trim_generic_body(repaired_body, max_len=ceiling - 10)
            if not repaired_body.strip().endswith("?"):
                repaired_body = cls._ensure_question_ending(repaired_body, eff_channel, persona)
                if len(repaired_body) > ceiling:
                    short_ask = "Open to connecting?" if eff_channel == ChannelType.LINKEDIN_CONNECTION else "Open to discussing?"
                    repaired_body = repaired_body[: ceiling - len(short_ask) - 5].rstrip(".,;:\n ") + f"...\n\n{short_ask}"

        return repaired_body, repaired_subject

    @classmethod
    def _ensure_question_ending(
        cls,
        body: str,
        channel: ChannelType,
        persona: Optional[AudiencePersona] = None,
    ) -> str:
        """Guarantee message concludes with a low-friction question mark."""
        stripped = body.strip()
        if not stripped:
            return "Open to connecting?"

        # Separate signature block if present
        explicit_sig_starts = ("regards", "best,", "sincerely", "best regards", "--", "__", "cheers")
        contact_tokens = ("linkedin.com", "github.com", "+1-", "+1 ", "tel:", "phone:", "email:", "@")
        lines = stripped.splitlines()
        main_lines: list[str] = []
        sig_lines: list[str] = []
        in_sig = False

        for i, line in enumerate(lines):
            l_strip = line.strip()
            l_lower = l_strip.lower()
            if not in_sig:
                if any(l_lower.startswith(tok) or tok in l_lower for tok in explicit_sig_starts):
                    in_sig = True
                    sig_lines.append(line)
                    continue
                if any(tok in l_lower for tok in contact_tokens) and i > 0 and len(l_strip) <= 50:
                    in_sig = True
                    sig_lines.append(line)
                    continue
                main_lines.append(line)
            else:
                sig_lines.append(line)

        main_text = "\n".join(main_lines).strip()
        if not main_text:
            main_text = stripped
            sig_lines = []

        if not main_text.endswith("?"):
            # Check if last sentence ends with a period on an inquiry
            if re.search(r"(?:open to|would you be open|connect|thoughts|feedback|perspective|touch base|catch up)[^.?!]*\.$", main_text, re.IGNORECASE):
                main_text = re.sub(r"\.\s*$", "?", main_text)
            else:
                # Append standard low-friction ask
                if channel == ChannelType.LINKEDIN_CONNECTION:
                    ask = "Open to connecting?"
                elif channel == ChannelType.FOLLOW_UP:
                    ask = "Would it be helpful to reconnect next quarter instead?"
                elif persona == AudiencePersona.EXECUTIVE_RECRUITER:
                    ask = "Would you be open to a brief conversation regarding current or upcoming mandates?"
                else:
                    ask = "Given your focus, would you be open to a brief conversation next week?"
                main_text = f"{main_text}\n\n{ask}"

        if sig_lines:
            return f"{main_text}\n\n" + "\n".join(sig_lines).strip()
        return main_text

    @classmethod
    def _trim_connection_note(cls, text: str, max_len: int = 295) -> str:
        """Trims a LinkedIn Connection note gracefully while preserving greeting, grounded metric, and question."""
        text = re.sub(r"\.{4,}", "...", text)
        if len(text) <= max_len:
            return text

        # Extract greeting
        greeting_match = re.match(r"^(Hi\s+[^,\n]+,\s*\n+)", text, re.IGNORECASE)
        greeting = greeting_match.group(1) if greeting_match else "Hi,\n\n"
        remainder = text[greeting_match.end() :] if greeting_match else text

        # Extract closing ask and middle content without dropping 2-paragraph notes
        rem_paras = [p.strip() for p in remainder.split("\n\n") if p.strip()]
        if len(rem_paras) > 1 and rem_paras[-1].endswith("?"):
            closing = rem_paras[-1]
            middle_paras = rem_paras[:-1]
        else:
            closing = "Open to connecting?"
            middle_paras = rem_paras
        middle_text = " ".join(middle_paras)

        # If a long "In my work as <long title>, " or "As <long title>, " clause pushes the metric out of budget, condense title first
        budget = max_len - len(greeting) - len(closing) - 4  # for \n\n separators
        if budget < 30:
            return f"{greeting}Open to connecting?"

        if len(middle_text) > budget:
            middle_text = re.sub(
                r"\b(?:In my (?:recent |executive leadership )?work as|As)\s+([^,]{35,}),\s+",
                lambda m: f"As {m.group(1)[:28].rsplit(' ', 1)[0].rstrip(',/-')}, ",
                middle_text,
            )

        if len(middle_text) <= budget:
            return f"{greeting}{middle_text}\n\n{closing}"

        words = middle_text.split()
        accum: list[str] = []
        cur_len = 0
        for w in words:
            if cur_len + len(w) + 1 > budget - 3:  # reserve 3 for "..."
                break
            accum.append(w)
            cur_len += len(w) + 1

        trimmed_middle = " ".join(accum).rstrip(".,;:") + "..."
        return f"{greeting}{trimmed_middle}\n\n{closing}"

    @classmethod
    def _trim_generic_body(cls, text: str, max_len: int) -> str:
        """Trims message body content before the terminal inquiry to adhere to channel ceilings."""
        text = re.sub(r"\.{4,}", "...", text)
        if len(text) <= max_len:
            return text

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return text[:max_len]

        if len(paragraphs) == 1:
            single = paragraphs[0]
            sentences = re.split(r"(?<=[.?!])\s+", single)
            if len(sentences) > 1 and sentences[-1].endswith("?"):
                closing = sentences[-1]
                other = " ".join(sentences[:-1])
                budget = max_len - len(closing) - 4
                if budget > 20:
                    words = other.split()
                    accum: list[str] = []
                    cur_len = 0
                    for w in words:
                        if cur_len + len(w) + 1 > budget - 3:
                            break
                        accum.append(w)
                        cur_len += len(w) + 1
                    return f"{' '.join(accum).rstrip('.,;:')}...\n\n{closing}"
            words = single.split()
            accum_single: list[str] = []
            cur_len = 0
            for w in words:
                if cur_len + len(w) + 1 > max_len - 3:
                    break
                accum_single.append(w)
                cur_len += len(w) + 1
            return " ".join(accum_single).rstrip(".,;:") + "..."

        closing = paragraphs[-1]
        other_paras = paragraphs[:-1]
        budget = max_len - len(closing) - 4

        words = " ".join(other_paras).split()
        accum = []
        cur_len = 0
        for w in words:
            if cur_len + len(w) + 1 > budget - 3:
                break
            accum.append(w)
            cur_len += len(w) + 1

        trimmed_other = " ".join(accum).rstrip(".,;:") + "..."
        res = f"{trimmed_other}\n\n{closing}"
        if len(res) <= max_len:
            return res

        words_all = res.split()
        accum_all: list[str] = []
        cur_len = 0
        for w in words_all:
            if cur_len + len(w) + 1 > max_len - 3:
                break
            accum_all.append(w)
            cur_len += len(w) + 1
        return " ".join(accum_all).rstrip(".,;:") + "..."

    @classmethod
    def repair_draft(
        cls,
        draft: OutreachMessageDraft,
        channel: Optional[ChannelType] = None,
    ) -> OutreachMessageDraft:
        """In-place repair of draft formatting and channel constraints."""
        eff_channel = channel or draft.channel
        repaired_body, repaired_subject = cls.repair_text(
            body=draft.body,
            subject=draft.subject,
            channel=eff_channel,
            persona=draft.audience_persona,
        )
        draft.body = repaired_body
        draft.subject = repaired_subject
        draft.character_count = len(repaired_body)
        draft.word_count = len(repaired_body.split())
        return draft


__all__ = ["DeterministicDraftRepairer"]
