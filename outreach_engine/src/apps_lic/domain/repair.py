"""Deterministic formatting, channel constraint, and C0 reserve-pool repair engine for outreach drafts."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    ChannelType,
    OutreachMessageDraft,
)
from apps_lic.domain.validators import PCTCertificate, _CHANNEL_MAX_CHARS
from infrastructure.types.metric_lexical_primitives import (
    METRIC_DOLLAR_PAT,
    METRIC_PERCENT_PAT,
    METRIC_SCALE_PAT,
)


@dataclass(frozen=True)
class ReservePoolRepairResult:
    """Result of repairing an ungrounded or colliding touch claim using the C0 reserve pool."""

    repaired_touch: Any
    certificate: PCTCertificate
    repaired_body: str
    replacement_fact_id: str
    repaired: bool = True

    @property
    def pct_certificate(self) -> PCTCertificate:
        """Alias for certificate."""
        return self.certificate

    @property
    def body(self) -> str:
        """Alias for repaired_body."""
        return self.repaired_body

    @property
    def fact_id(self) -> str:
        """Alias for replacement_fact_id."""
        return self.replacement_fact_id

    @property
    def draft(self) -> Any:
        """Return underlying draft object if touch is a TouchPoint."""
        return getattr(self.repaired_touch, "draft", self.repaired_touch)

    def __iter__(self) -> Iterator[Any]:
        yield self.repaired_touch
        yield self.certificate

    def to_dict(self) -> dict[str, Any]:
        """Serialize repair result to a JSON-compatible dictionary."""
        return {
            "repaired": self.repaired,
            "repaired_body": self.repaired_body,
            "replacement_fact_id": self.replacement_fact_id,
            "certificate": self.certificate.to_dict(),
        }


def _extract_reserve_candidates(
    allocation_plan: Any | None,
    reserve_facts: Sequence[Any] | None,
    candidate_facts: Sequence[Any] | Any | None,
) -> list[tuple[str, str, str, str]]:
    """Extract ordered (fact_id, source_chunk_id, verbatim_span, primary_metric) from reserve pool."""
    pool_ids: list[str] = []
    raw_items: list[Any] = []
    if allocation_plan is not None:
        r_ids = getattr(allocation_plan, "reserve_repair_pool_fact_ids", None) or (
            allocation_plan.get("reserve_repair_pool_fact_ids") if isinstance(allocation_plan, Mapping) else ()
        )
        pool_ids.extend(str(x) for x in (r_ids or ()) if str(x).strip())
        r_facts = getattr(allocation_plan, "reserve_repair_pool_facts", None) or (
            allocation_plan.get("reserve_repair_pool_facts") if isinstance(allocation_plan, Mapping) else ()
        )
        raw_items.extend(r_facts or ())
    if reserve_facts is not None:
        raw_items.extend(reserve_facts)
    if candidate_facts is not None:
        if hasattr(candidate_facts, "verified_facts"):
            raw_items.extend(getattr(candidate_facts, "verified_facts") or ())
        elif hasattr(candidate_facts, "chunks"):
            raw_items.extend(getattr(candidate_facts, "chunks") or ())
        elif isinstance(candidate_facts, Sequence) and not isinstance(candidate_facts, (str, bytes)):
            raw_items.extend(candidate_facts)

    by_id: dict[str, tuple[str, str, str, str]] = {}
    ordered: list[tuple[str, str, str, str]] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            fid = str(item.get("fact_id") or "").strip()
            src = str(item.get("source_chunk_id") or item.get("source_reference") or "reserve_chunk").strip()
            span = str(item.get("verbatim_span") or item.get("statement") or "").strip()
            mtoks = item.get("metric_tokens") or ([item["metric"]] if item.get("metric") else ())
        else:
            fid = str(getattr(item, "fact_id", "") or "").strip()
            src = str(getattr(item, "source_chunk_id", None) or getattr(item, "source_reference", None) or "reserve_chunk").strip()
            span = str(getattr(item, "verbatim_span", None) or getattr(item, "statement", None) or "").strip()
            mtoks = getattr(item, "metric_tokens", None) or ([getattr(item, "metric")] if getattr(item, "metric", None) else ())
        if not fid or not span:
            continue
        p_met = str(mtoks[0]).strip() if mtoks else ""
        if not p_met:
            for pat in (METRIC_DOLLAR_PAT, METRIC_PERCENT_PAT, METRIC_SCALE_PAT):
                if m := pat.search(span):
                    p_met = m.group(0)
                    break
        rec = (fid, src, span, p_met)
        if fid not in by_id:
            by_id[fid] = rec
            ordered.append(rec)

    if pool_ids:
        prioritized = [by_id[fid] for fid in pool_ids if fid in by_id]
        if prioritized:
            return prioritized
    return ordered


def repair_touch_with_reserve_pool(
    touch_or_draft: Any,
    allocation_plan: Any | None = None,
    *,
    reserve_facts: Sequence[Any] | None = None,
    candidate_facts: Sequence[Any] | Any | None = None,
    touch_number: int | None = None,
    ungrounded_span: str | None = None,
    colliding_metric: str | None = None,
    colliding_fact_id: str | None = None,
    used_reserve_fact_ids: set[str] | Sequence[str] | None = None,
) -> ReservePoolRepairResult:
    """Swap an ungrounded or colliding claim/metric with a verified C0 reserve-pool fact and emit a PCTCertificate."""
    candidates = _extract_reserve_candidates(allocation_plan, reserve_facts, candidate_facts)
    used_set = {str(x) for x in (used_reserve_fact_ids or ())}
    chosen = next((c for c in candidates if c[0] not in used_set), None)
    if chosen is None:
        raise ValueError("Reserve repair pool is empty or exhausted; cannot repair touch.")

    r_fid, r_src, r_span, r_met = chosen
    eff_touch_num = int(touch_number or getattr(touch_or_draft, "touch_number", 0) or 1)
    draft_obj = getattr(touch_or_draft, "draft", touch_or_draft)

    if isinstance(draft_obj, str):
        raw_body = draft_obj
    elif isinstance(draft_obj, Mapping):
        eff_touch_num = int(draft_obj.get("touch_number", eff_touch_num) or eff_touch_num)
        raw_body = str(draft_obj.get("body") or "")
    else:
        raw_body = str(getattr(draft_obj, "body", "") or "")

    clean_span = r_span.strip().rstrip(".")
    replacement_sentence = f"In my recent work, {clean_span[0].lower() + clean_span[1:] if len(clean_span) > 1 and clean_span[1].islower() else clean_span}."
    repaired_body = raw_body

    if ungrounded_span and ungrounded_span in repaired_body:
        repaired_body = repaired_body.replace(ungrounded_span, clean_span, 1)
    elif colliding_metric and colliding_metric in repaired_body:
        repaired_body = re.sub(
            r"[^.!?\n]*" + re.escape(colliding_metric) + r"[^.!?\n]*\.?",
            f" {replacement_sentence}",
            repaired_body,
            count=1,
        ).strip()
    else:
        replaced = False
        for pat in (METRIC_DOLLAR_PAT, METRIC_PERCENT_PAT, METRIC_SCALE_PAT):
            if m := pat.search(repaired_body):
                repaired_body = re.sub(
                    r"[^.!?\n]*" + re.escape(m.group(0)) + r"[^.!?\n]*\.?",
                    f" {replacement_sentence}",
                    repaired_body,
                    count=1,
                ).strip()
                replaced = True
                break
        if not replaced:
            repaired_body = f"{repaired_body.rstrip()}\n\n{replacement_sentence}".strip()

    if r_met and r_met not in repaired_body:
        repaired_body = f"{repaired_body.rstrip()}\n\n{replacement_sentence}".strip()

    cert = PCTCertificate(
        touch_number=eff_touch_num,
        claim_span=replacement_sentence,
        metric_token=r_met,
        fact_id=r_fid,
        source_chunk_id=r_src,
        verbatim_span=r_span,
        in_cand=True,
        in_opp=False,
        verified=True,
    )

    if isinstance(draft_obj, dict):
        draft_obj["body"] = repaired_body
        draft_obj["grounded_facts_used"] = [r_fid]
        draft_obj["cited_fact_ids"] = [r_fid]
        draft_obj["repaired_from_reserve_pool"] = True
        meta = draft_obj.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta["repaired_from_reserve_pool"] = True
            meta["reserve_fact_id"] = r_fid
            meta["pct_certificate"] = cert.to_dict()
        out_touch = touch_or_draft
    elif not isinstance(draft_obj, str) and hasattr(draft_obj, "body"):
        draft_obj.body = repaired_body
        draft_obj.grounded_facts_used = [r_fid]
        draft_obj.character_count = len(repaired_body)
        draft_obj.word_count = len(repaired_body.split())
        if hasattr(draft_obj, "metadata") and isinstance(draft_obj.metadata, dict):
            draft_obj.metadata["repaired_from_reserve_pool"] = True
            draft_obj.metadata["reserve_fact_id"] = r_fid
            draft_obj.metadata["pct_certificate"] = cert.to_dict()
        out_touch = touch_or_draft
    else:
        out_touch = repaired_body

    return ReservePoolRepairResult(
        repaired_touch=out_touch,
        certificate=cert,
        repaired_body=repaired_body,
        replacement_fact_id=r_fid,
        repaired=True,
    )


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
    def repair_touch_with_reserve_pool(cls, touch_or_draft: Any, allocation_plan: Any | None = None, **kwargs: Any) -> ReservePoolRepairResult:
        """Delegate reserve-pool touch repair to repair_touch_with_reserve_pool."""
        return repair_touch_with_reserve_pool(touch_or_draft, allocation_plan, **kwargs)

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

        repaired_body = re.sub(r"\s*--\s*", ", ", repaired_body.replace("—", ", ").replace("\u2014", ", "))
        repaired_subject = re.sub(r"\s*--\s*", " - ", repaired_subject.replace("—", "-").replace("\u2014", "-"))
        repaired_body = cls._MD_LINK_PAT.sub(r"\1 (\2)", repaired_body)

        for pat, repl in cls._SUBORDINATE_REPLACEMENTS:
            repaired_body = pat.sub(repl, repaired_body)

        repaired_body = re.sub(r"[ \t]+$", "", repaired_body, flags=re.MULTILINE)
        repaired_body = re.sub(r"\n{3,}", "\n\n", repaired_body).strip()

        eff_channel = channel or ChannelType.LINKEDIN_INMAIL
        ceiling = _CHANNEL_MAX_CHARS.get(eff_channel, 2000)
        inquiry_reserve = 80 if not repaired_body.strip().endswith("?") else 0
        target_len = max(50, ceiling - 10 - inquiry_reserve)

        if eff_channel == ChannelType.LINKEDIN_CONNECTION and len(repaired_body) > 300:
            repaired_body = cls._trim_connection_note(repaired_body, max_len=295)
        elif len(repaired_body) > target_len:
            repaired_body = cls._trim_generic_body(repaired_body, max_len=target_len)

        repaired_body = cls._ensure_question_ending(repaired_body, eff_channel, persona)

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
    def _ensure_question_ending(cls, body: str, channel: ChannelType, persona: Optional[AudiencePersona] = None) -> str:
        """Guarantee message concludes with a low-friction question mark."""
        stripped = body.strip()
        if not stripped:
            return "Open to connecting?"

        explicit_sig_starts = ("regards", "best,", "sincerely", "best regards", "--", "__", "cheers")
        contact_tokens = ("linkedin.com", "github.com", "+1-", "+1 ", "tel:", "phone:", "email:", "@")
        lines = stripped.splitlines()
        main_lines: list[str] = []
        sig_lines: list[str] = []
        in_sig = False

        for i, line in enumerate(lines):
            l_strip, l_lower = line.strip(), line.strip().lower()
            if not in_sig:
                if any(l_lower.startswith(tok) or tok in l_lower for tok in explicit_sig_starts) or (
                    any(tok in l_lower for tok in contact_tokens) and i > 0 and len(l_strip) <= 50
                ):
                    in_sig = True
                    sig_lines.append(line)
                    continue
                main_lines.append(line)
            else:
                sig_lines.append(line)

        main_text = "\n".join(main_lines).strip() or stripped
        if not main_lines:
            sig_lines = []

        if not main_text.endswith("?"):
            if re.search(r"(?:open to|would you be open|connect|thoughts|feedback|perspective|touch base|catch up)[^.?!]*\.$", main_text, re.IGNORECASE):
                main_text = re.sub(r"\.\s*$", "?", main_text)
            else:
                if channel == ChannelType.LINKEDIN_CONNECTION:
                    ask = "Open to connecting?"
                elif channel == ChannelType.FOLLOW_UP:
                    ask = "Would it be helpful to reconnect next quarter instead?"
                elif persona == AudiencePersona.EXECUTIVE_RECRUITER:
                    ask = "Would you be open to a brief conversation regarding current or upcoming mandates?"
                else:
                    ask = "Given your focus, would you be open to a brief conversation next week?"
                main_text = f"{main_text}\n\n{ask}"

        return f"{main_text}\n\n" + "\n".join(sig_lines).strip() if sig_lines else main_text

    @classmethod
    def _trim_connection_note(cls, text: str, max_len: int = 295) -> str:
        """Trims a LinkedIn Connection note gracefully while preserving greeting, grounded metric, and question."""
        text = re.sub(r"\.{4,}", "...", text)
        if len(text) <= max_len:
            return text

        greeting_match = re.match(r"^(Hi\s+[^,\n]+,\s*\n+)", text, re.IGNORECASE)
        greeting = greeting_match.group(1) if greeting_match else "Hi,\n\n"
        remainder = text[greeting_match.end() :] if greeting_match else text

        rem_paras = [p.strip() for p in remainder.split("\n\n") if p.strip()]
        if len(rem_paras) > 1 and rem_paras[-1].endswith("?"):
            closing, middle_paras = rem_paras[-1], rem_paras[:-1]
        else:
            closing, middle_paras = "Open to connecting?", rem_paras
        middle_text = " ".join(middle_paras)

        budget = max_len - len(greeting) - len(closing) - 4
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

        accum, cur_len = [], 0
        for w in middle_text.split():
            if cur_len + len(w) + 1 > budget - 3:
                break
            accum.append(w)
            cur_len += len(w) + 1
        return f"{greeting}{' '.join(accum).rstrip('.,;:')}...\n\n{closing}"

    @classmethod
    def _trim_generic_body(cls, text: str, max_len: int) -> str:
        """Trims message body content before the terminal inquiry to adhere to channel ceilings."""
        text = re.sub(r"\.{4,}", "...", text)
        if len(text) <= max_len:
            return text

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return text[:max_len]

        def _fit_words(words: list[str], limit: int) -> str:
            acc: list[str] = []
            c_len = 0
            for w in words:
                if c_len + len(w) + 1 > limit - 3:
                    break
                acc.append(w)
                c_len += len(w) + 1
            return " ".join(acc).rstrip(".,;:") + "..."

        if len(paragraphs) == 1:
            single = paragraphs[0]
            sentences = re.split(r"(?<=[.?!])\s+", single)
            if len(sentences) > 1 and sentences[-1].endswith("?"):
                closing = sentences[-1]
                budget = max_len - len(closing) - 4
                if budget > 20:
                    return f"{_fit_words(' '.join(sentences[:-1]).split(), budget)}\n\n{closing}"
            return _fit_words(single.split(), max_len)

        closing = paragraphs[-1]
        budget = max_len - len(closing) - 4
        res = f"{_fit_words(' '.join(paragraphs[:-1]).split(), budget)}\n\n{closing}"
        return res if len(res) <= max_len else _fit_words(res.split(), max_len)

    @classmethod
    def repair_draft(cls, draft: OutreachMessageDraft, channel: Optional[ChannelType] = None) -> OutreachMessageDraft:
        """In-place repair of draft formatting and channel constraints."""
        eff_channel = channel or draft.channel
        repaired_body, repaired_subject = cls.repair_text(
            body=draft.body, subject=draft.subject, channel=eff_channel, persona=draft.audience_persona
        )
        draft.body, draft.subject = repaired_body, repaired_subject
        draft.character_count, draft.word_count = len(repaired_body), len(repaired_body.split())
        return draft


__all__ = ["DeterministicDraftRepairer", "ReservePoolRepairResult", "repair_touch_with_reserve_pool"]
