"""Grounding, PCTCertificate, forbidden claims, personalization, and outbound privacy validators for apps_lic."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, List, Optional

from infrastructure.types.metric_lexical_primitives import (
    METRIC_DOLLAR_PAT, METRIC_PERCENT_PAT, METRIC_SCALE_PAT, extract_normalized_dollars, normalize_dollar_token,
)

_METRIC_DOLLAR_PAT, _METRIC_PERCENT_PAT, _METRIC_SCALE_PAT = METRIC_DOLLAR_PAT, METRIC_PERCENT_PAT, METRIC_SCALE_PAT
_normalize_dollar_token, _extract_normalized_dollars = normalize_dollar_token, extract_normalized_dollars

METRIC_LAUNDERED_FROM_OPPORTUNITY: Final[str] = "METRIC_LAUNDERED_FROM_OPPORTUNITY"
UNGROUNDED_CANDIDATE_METRIC: Final[str] = "UNGROUNDED_CANDIDATE_METRIC"

_TARGET_FOCUS_CLAUSE_PAT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:following|noticed|regarding|given)\b[^.!?\n]{0,90}\b"
    r"(?:focus\s+on|priorities\s+in|work\s+in|search\s+in|mandate\s+in|modernization|initiative|expansion)\b",
    re.IGNORECASE,
)
_CANDIDATE_ATTR_PAT: Final[re.Pattern[str]] = re.compile(
    r"\b(?:my|we|our|track\s+record|i\s+(?!(?:have\s+been\s+|am\s+)?(?:following|noticing|reaching|writing)\b|(?:noticed|saw|read|wanted)\b))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PCTCertificate:
    """Proof-Carrying Text (PCT) certificate binding a candidate metric claim to a C0 fact."""

    certificate_id: str = ""
    touch_number: int = 1
    claim_span: str = ""
    metric_token: str = ""
    fact_id: str = ""
    source_chunk_id: str = ""
    verbatim_span: str = ""
    in_cand: bool = False
    in_opp: bool = False
    verified: bool = False

    def __post_init__(self) -> None:
        if not self.certificate_id:
            seed = f"{self.touch_number}|{self.metric_token}|{self.fact_id}|{self.source_chunk_id}|{self.claim_span}"
            object.__setattr__(self, "certificate_id", f"pct_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "certificate_id": self.certificate_id, "touch_number": int(self.touch_number), "claim_span": self.claim_span,
            "metric_token": self.metric_token, "fact_id": self.fact_id, "source_chunk_id": self.source_chunk_id,
            "verbatim_span": self.verbatim_span, "in_cand": bool(self.in_cand), "in_opp": bool(self.in_opp), "verified": bool(self.verified),
        }


@dataclass(frozen=True)
class MetricGroundingVerificationResult:
    """Structured result of candidate metric grounding and PCTCertificate verification."""

    passed: bool
    certificates: tuple[PCTCertificate, ...] = ()
    violations: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.passed

    @property
    def pct_certificates(self) -> tuple[PCTCertificate, ...]:
        return self.certificates

    def __iter__(self) -> Iterator[Any]:
        return iter((self.passed, list(self.certificates), list(self.violations)))

    def __bool__(self) -> bool:
        return self.passed

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "certificates": [c.to_dict() for c in self.certificates], "violations": list(self.violations)}


def _extract_clause_for_span(text: str, start: int, end: int) -> str:
    sent_start = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start), text.rfind("\n", 0, start))
    sent_start = 0 if sent_start == -1 else sent_start + 1
    next_bounds = [p for p in (text.find(".", end), text.find("!", end), text.find("?", end), text.find("\n", end)) if p != -1]
    sentence = text[sent_start : (min(next_bounds) if next_bounds else len(text))].strip()
    rel_pos, cursor = max(0, start - sent_start), 0
    for cl in re.split(r",\s+(?=(?:i|my|we|our|in\s+my|as\s+|would\s+you|open\s+to|happy\s+to)\b)", sentence, flags=re.IGNORECASE):
        if cursor + len(cl) + 2 >= rel_pos:
            return cl.strip()
        cursor += len(cl) + 2
    return sentence


def _is_target_context_clause(text: str, start: int, end: int) -> bool:
    clause = _extract_clause_for_span(text, start, end)
    return bool(_TARGET_FOCUS_CLAUSE_PAT.search(clause)) and not bool(_CANDIDATE_ATTR_PAT.search(clause))


def _unpack_fact_record(f: Any) -> tuple[str, str, str, str, bool]:
    if isinstance(f, Mapping):
        fid, src = str(f.get("fact_id") or "").strip(), str(f.get("source_chunk_id") or f.get("source_reference") or "").strip()
        span = str(f.get("verbatim_span") or f.get("statement") or "").strip()
        met = " ".join(str(x) for x in (f.get("metric_tokens") or ())) or str(f.get("metric") or "")
        has_prov = bool(f.get("has_provenance", bool(src))) and bool(src)
    else:
        fid = str(getattr(f, "fact_id", "") or "").strip()
        src = str(getattr(f, "source_chunk_id", None) or getattr(f, "source_reference", None) or "").strip()
        span = str(getattr(f, "verbatim_span", None) or getattr(f, "statement", None) or "").strip()
        mtoks = getattr(f, "metric_tokens", None)
        met = " ".join(str(x) for x in mtoks) if mtoks else str(getattr(f, "metric", "") or "")
        has_prov = bool(getattr(f, "has_provenance", bool(src))) and bool(src)
    return fid, src, span, f"{span} {met}".strip().lower(), has_prov


def _metric_matches_text(raw_metric: str, kind: str, target_text_lower: str, target_dollars: set[str]) -> bool:
    matched = raw_metric.strip().lower()
    if not matched or not target_text_lower:
        return False
    if kind == "dollar":
        return (matched in target_text_lower) or (normalize_dollar_token(raw_metric) in target_dollars)
    if kind == "percent":
        return bool(re.search(r"(?<!\d)" + re.escape(matched), target_text_lower))
    return matched in target_text_lower


def verify_candidate_metric_grounding(
    body_or_draft: str | Any = "", candidate_facts: Sequence[Any] | Any = (),
    opportunity_context: str | Any | None = None, allowed_fact_ids: set[str] | Sequence[str] | None = None,
    *, body: str | None = None, draft: Any | None = None, claim_span: str | None = None,
    metric_token: str | None = None, declared_fact_ids: Sequence[str] | None = None,
    allocation_plan: Any | None = None, touch_number: int = 1,
    strict_candidate_attribution: bool = True, never_treated_as_candidate_proof: bool = True,
) -> MetricGroundingVerificationResult:
    """Verify candidate-attributed metrics have `in_cand == True` and a bound C0 `PCTCertificate`."""
    if isinstance(body_or_draft, PCTCertificate):
        cert, viols = body_or_draft, []
        if cert.in_opp and not cert.in_cand:
            viols.append(f"{METRIC_LAUNDERED_FROM_OPPORTUNITY}: Metric '{cert.metric_token}' originates from opportunity research.")
        elif not cert.in_cand or not cert.fact_id or not cert.source_chunk_id or not cert.verified:
            viols.append(f"{UNGROUNDED_CANDIDATE_METRIC}: Metric '{cert.metric_token}' lacks verified candidate provenance.")
        return MetricGroundingVerificationResult(passed=len(viols) == 0, certificates=(cert,), violations=tuple(viols))

    target_obj = draft if draft is not None else body_or_draft
    if hasattr(target_obj, "draft"):
        touch_number, target_obj = int(getattr(target_obj, "touch_number", touch_number) or touch_number), getattr(target_obj, "draft")
    if isinstance(target_obj, str):
        text = body if body is not None else target_obj
    elif isinstance(target_obj, Mapping):
        touch_number = int(target_obj.get("touch_number", touch_number) or touch_number)
        text = str(body if body is not None else (target_obj.get("body") or claim_span or ""))
        if declared_fact_ids is None and ("grounded_facts_used" in target_obj or "cited_fact_ids" in target_obj):
            declared_fact_ids = list(target_obj.get("grounded_facts_used") or target_obj.get("cited_fact_ids") or ())
    else:
        text = str(body if body is not None else (getattr(target_obj, "body", None) or claim_span or ""))
        if declared_fact_ids is None and hasattr(target_obj, "grounded_facts_used"):
            declared_fact_ids = list(getattr(target_obj, "grounded_facts_used") or ())

    raw_facts: list[Any] = list(
        getattr(candidate_facts, "verified_facts", None) or getattr(candidate_facts, "chunks", None)
        or (candidate_facts if isinstance(candidate_facts, Sequence) and not isinstance(candidate_facts, (str, bytes)) else ())
    )
    alloc_touch_ids: set[str] | None = None
    if allocation_plan is not None:
        by_touch = getattr(allocation_plan, "allocated_fact_ids_by_touch", None) or (allocation_plan.get("allocated_fact_ids_by_touch") if isinstance(allocation_plan, Mapping) else None)
        if isinstance(by_touch, Mapping):
            alloc_touch_ids = {str(x) for x in (by_touch.get(touch_number) or by_touch.get(str(touch_number)) or ()) if str(x).strip()}
        res_ids = getattr(allocation_plan, "reserve_repair_pool_fact_ids", None) or (allocation_plan.get("reserve_repair_pool_fact_ids") if isinstance(allocation_plan, Mapping) else ())
        t_meta = target_obj.get("metadata", {}) if isinstance(target_obj, Mapping) else (getattr(target_obj, "metadata", None) or {})
        if alloc_touch_ids is not None and isinstance(t_meta, Mapping) and t_meta.get("repaired_from_reserve_pool"):
            alloc_touch_ids |= {str(x) for x in (res_ids or ()) if str(x).strip()}
        for a in (getattr(allocation_plan, "assignments", None) or (allocation_plan.get("assignments") if isinstance(allocation_plan, Mapping) else ()) or ()):
            raw_facts.extend((getattr(a, "allocated_facts", None) or (a.get("allocated_facts") if isinstance(a, Mapping) else ())) or ())
        raw_facts.extend((getattr(allocation_plan, "reserve_repair_pool_facts", None) or (allocation_plan.get("reserve_repair_pool_facts") if isinstance(allocation_plan, Mapping) else ())) or ())

    fact_records: dict[str, tuple[str, str, str, str, set[str]]] = {}
    for item in raw_facts:
        fid, src, span, comb_lower, has_prov = _unpack_fact_record(item)
        if fid and has_prov and fid not in fact_records:
            fact_records[fid] = (fid, src, span, comb_lower, extract_normalized_dollars(comb_lower))

    allowed_set = set(fact_records.keys())
    if allowed_fact_ids is not None:
        allowed_set &= {str(x) for x in allowed_fact_ids}
    if alloc_touch_ids is not None:
        allowed_set &= alloc_touch_ids

    violations: list[str] = []
    active_fact_ids = set(allowed_set)
    if declared_fact_ids is not None:
        decl_list = [str(x) for x in declared_fact_ids if str(x).strip()]
        violations.extend(f"Ungrounded or unallocated fact_id '{fid}' referenced in touch {touch_number}." for fid in decl_list if fid not in allowed_set)
        active_fact_ids = {fid for fid in decl_list if fid in allowed_set}

    opp_str = ""
    if isinstance(opportunity_context, str):
        opp_str = opportunity_context
    elif isinstance(opportunity_context, Mapping):
        opp_str = " ".join(str(opportunity_context.get(k) or "") for k in ("briefing_text", "company_name", "strategic_priorities"))
        never_treated_as_candidate_proof = bool(opportunity_context.get("never_treated_as_candidate_proof", never_treated_as_candidate_proof))
    elif opportunity_context is not None:
        prios = " ".join(str(x) for x in (getattr(opportunity_context, "strategic_priorities", None) or ()))
        opp_str = f"{prios} {getattr(opportunity_context, 'briefing_text', '') or ''} {getattr(opportunity_context, 'company_name', '') or ''}".strip()
        sealed = getattr(opportunity_context, "sealed_resolution", None)
        if isinstance(sealed, Mapping) and "never_treated_as_candidate_proof" in sealed:
            never_treated_as_candidate_proof = bool(sealed["never_treated_as_candidate_proof"])

    opp_lower, opp_dollars = opp_str.lower(), extract_normalized_dollars(opp_str.lower())
    matches: list[tuple[int, int, str, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for kind, pat in (("dollar", _METRIC_DOLLAR_PAT), ("percent", _METRIC_PERCENT_PAT), ("scale", _METRIC_SCALE_PAT)):
        for m in pat.finditer(text):
            if (m.start(), m.end()) not in seen_spans:
                seen_spans.add((m.start(), m.end()))
                matches.append((m.start(), m.end(), m.group(0), kind))
    if metric_token and all(metric_token.lower() != m[2].lower() for m in matches):
        s_idx = max(0, text.lower().find(metric_token.lower()))
        matches.append((s_idx, s_idx + len(metric_token), metric_token, "dollar" if "$" in metric_token else ("percent" if "%" in metric_token else "scale")))
    matches.sort(key=lambda item: item[0])

    certificates: list[PCTCertificate] = []
    for s_idx, e_idx, raw_tok, kind in matches:
        c_span = _extract_clause_for_span(text, s_idx, e_idx)
        is_target_only = _is_target_context_clause(text, s_idx, e_idx) and not strict_candidate_attribution
        matched_fid = matched_src = matched_verbatim = ""
        for fid in sorted(active_fact_ids):
            if (rec := fact_records.get(fid)) and _metric_matches_text(raw_tok, kind, rec[3], rec[4]):
                matched_fid, matched_src, matched_verbatim = rec[0], rec[1], rec[2]
                break
        in_cand, in_opp = bool(matched_fid and matched_src), _metric_matches_text(raw_tok, kind, opp_lower, opp_dollars)
        if is_target_only:
            verified = in_cand or in_opp
            if not verified:
                violations.append(f"{UNGROUNDED_CANDIDATE_METRIC}: Metric '{raw_tok}' in touch {touch_number} is ungrounded.")
        elif in_cand and matched_fid in allowed_set:
            verified = True
        elif in_opp and (not in_cand or never_treated_as_candidate_proof):
            verified = False
            violations.append(f"{METRIC_LAUNDERED_FROM_OPPORTUNITY}: Candidate-attributed metric '{raw_tok}' in touch {touch_number} originates only from target opportunity research (in_opp=True, in_cand=False).")
        else:
            verified = False
            violations.append(f"{UNGROUNDED_CANDIDATE_METRIC}: Candidate-attributed metric '{raw_tok}' in touch {touch_number} is not backed by any allocated C0 candidate fact with source evidence.")
        certificates.append(PCTCertificate(touch_number=touch_number, claim_span=c_span, metric_token=raw_tok, fact_id=matched_fid, source_chunk_id=matched_src, verbatim_span=matched_verbatim, in_cand=in_cand, in_opp=in_opp, verified=verified))

    return MetricGroundingVerificationResult(passed=len(violations) == 0, certificates=tuple(certificates), violations=tuple(violations))


class GroundingValidator:
    """Ensures drafts do not fabricate claims outside allowed candidate facts and blocks opportunity metric laundering."""

    _METRIC_DOLLAR_PAT, _METRIC_PERCENT_PAT, _METRIC_SCALE_PAT = METRIC_DOLLAR_PAT, METRIC_PERCENT_PAT, METRIC_SCALE_PAT
    _UNGROUNDED_ASSERTION_PAT: Final[re.Pattern[str]] = re.compile(
        r"\b(?:personally invented|co-invented|patented the|invented the|won an? (?:olympic|nobel|pulitzer))\b", re.IGNORECASE
    )

    @staticmethod
    def _normalize_dollar_token(raw: str) -> str:
        return normalize_dollar_token(raw)

    def _extract_normalized_dollars(self, text: str) -> set[str]:
        return extract_normalized_dollars(text)

    def validate(
        self, draft_facts_used: List[str], allowed_fact_ids: set[str],
        body: Optional[str] = None, candidate_facts: Optional[List[Any]] = None,
        opportunity_context: Optional[str] = None, *, strict_candidate_metrics: bool = False,
    ) -> tuple[bool, List[str]]:
        violations: List[str] = []
        cf_by_id: dict[str, Any] = {getattr(f, "fact_id"): f for f in (candidate_facts or ()) if getattr(f, "fact_id", None)}

        for fid in draft_facts_used:
            if fid not in allowed_fact_ids:
                violations.append(f"Ungrounded fact referenced: '{fid}'")
            elif cf_by_id:
                f_obj = cf_by_id.get(fid)
                if f_obj is None:
                    violations.append(f"Referenced fact ID '{fid}' not found in candidate facts.")
                elif not str(getattr(f_obj, "source_reference", None) or getattr(f_obj, "source_chunk_id", None) or "").strip():
                    violations.append(f"Fact '{fid}' has missing provenance (source_reference is missing); failing closed.")

        if body and body.strip():
            declared_texts = [
                f"{getattr(f_obj, 'statement', '') or getattr(f_obj, 'verbatim_span', '') or ''} {getattr(f_obj, 'metric', '') or ''}".lower()
                for fid in (draft_facts_used if cf_by_id else ())
                if (f_obj := cf_by_id.get(fid)) and (getattr(f_obj, "has_provenance", False) or getattr(f_obj, "source_reference", None) or getattr(f_obj, "source_chunk_id", None))
            ]
            declared_facts_text, opp_text = " ".join(declared_texts), str(opportunity_context or "").lower()
            declared_dollars, opp_dollars = self._extract_normalized_dollars(declared_facts_text), self._extract_normalized_dollars(opp_text)

            for kind, pat in (("dollar", self._METRIC_DOLLAR_PAT), ("percentage", self._METRIC_PERCENT_PAT), ("scale", self._METRIC_SCALE_PAT)):
                for m in pat.finditer(body):
                    raw_m, m_kind = m.group(0), ("percent" if kind == "percentage" else kind)
                    in_declared = _metric_matches_text(raw_m, m_kind, declared_facts_text, declared_dollars)
                    in_opp = _metric_matches_text(raw_m, m_kind, opp_text, opp_dollars)
                    is_target_ctx = _is_target_context_clause(body, m.start(), m.end()) and not strict_candidate_metrics
                    if not in_declared and in_opp and not is_target_ctx:
                        violations.append(f"{METRIC_LAUNDERED_FROM_OPPORTUNITY}: Candidate-attributed {kind} metric '{raw_m}' originates only from target opportunity context (in_opp=True, in_cand=False).")
                    elif not in_declared and not (in_opp and is_target_ctx):
                        msg = (
                            f"Message body cites metric '{raw_m}' without declaring any grounded fact ID backed by source evidence."
                            if kind == "dollar" and not draft_facts_used
                            else f"Unsupported {kind} metric claim in message body: '{raw_m}'. Not supported by declared candidate facts with source evidence."
                        )
                        violations.append(msg)

            for m in self._UNGROUNDED_ASSERTION_PAT.finditer(body):
                if m.group(0).lower() not in declared_facts_text:
                    violations.append(f"Unsupported factual assertion in message body: '{m.group(0)}'. Not grounded in candidate verified facts with source evidence.")

        return len(violations) == 0, violations


class ForbiddenClaimsValidator:
    """Hard assertion gate rejecting ungrounded compensation, unverifiable tenure claims, and policy-forbidden phrasing."""

    _COMPENSATION_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:salary|compensation|base\s+pay|annual\s+pay|equity\s+grant|stock\s+options|signing\s+bonus|hourly\s+rate|expected\s+rate|pay\s+rate|target\s+comp|comp\s+package|retainer|ote)\b", re.IGNORECASE),
        re.compile(r"[\$€£]\s*\d{1,4}(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|million|billion|thousand|/yr|/year|per\s+year|/hr|/hour|per\s+hour|ote)?(?:\s*[-–—]\s*[\$€£]?\s*\d{1,4}(?:,\d{3})*(?:\.\d+)?\s*(?:k|m|b|million|billion|thousand)?)?\b", re.IGNORECASE),
        re.compile(r"\b\d{1,4}\s*k\s*(?:ote|salary|base|comp|retainer|bonus)\b", re.IGNORECASE),
    ]
    _TENURE_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:over\s+)?(\d+|ten|fifteen|twenty|twenty-five|thirty)\+?\s+years?\s+(?:of\s+)?(?:experience|leading|leadership|in|track\s+record)\b", re.IGNORECASE),
        re.compile(r"\b((?:two|three|four)\s+decades?)\s+(?:of\s+)?(?:experience|leadership|in)\b", re.IGNORECASE),
        re.compile(r"\b(\d+)\s*(?:\+|-)\s*year\s+(?:veteran|career|leader)\b", re.IGNORECASE),
    ]
    _POLICY_FORBIDDEN_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\b(?:visa\s+sponsorship|require\s+sponsorship|sponsorship\s+required|h-?1b|opt\s+stem|green\s*card\s+sponsorship)\b", re.IGNORECASE),
        re.compile(r"\b(?:relocation\s+(?:package|assistance|allowance|bonus)|paid\s+relocation)\b", re.IGNORECASE),
        re.compile(r"\b(?:status\s+of\s+my\s+application|following\s+up\s+on\s+my\s+(?:job\s+)?application|submitted\s+my\s+resume|check\s+on\s+my\s+interview\s+status|pending\s+application)\b", re.IGNORECASE),
    ]
    _BIZ_KWS: Final[tuple[str, ...]] = (
        "arr", "revenue", "volume", "budget", "valuation", "pipeline", "spend", "deal", "portfolio", "gmv", "assets", "sales",
        "program", "transformation", "modernization", "initiative", "infrastructure", "platform", "savings", "saved", "cost",
        "costs", "reduction", "reduced", "efficiency", "opex", "capex", "roi", "run-rate",
    )

    def validate(self, body: Optional[str], verified_facts: Optional[List[Any]] = None, opportunity_context: Optional[str] = None) -> tuple[bool, List[str]]:
        body_str, violations, opp_text = str(body or ""), [], str(opportunity_context or "").lower()
        norm_fn, g_val = GroundingValidator._normalize_dollar_token, GroundingValidator()
        opp_dollars = g_val._extract_normalized_dollars(opp_text)

        for pat in (self._COMPENSATION_PATTERNS[0], self._COMPENSATION_PATTERNS[2]):
            for match in pat.finditer(body_str):
                violations.append(f"Forbidden compensation claim detected: '{match.group(0)}'. Compensation discussions are strictly prohibited in cold outreach before first reply.")

        for match in self._COMPENSATION_PATTERNS[1].finditer(body_str):
            matched_str = match.group(0)
            norm_matched = norm_fn(re.sub(r"^[€£]", "$", matched_str.strip()))
            comp_window = body_str[max(0, match.start() - 30) : min(len(body_str), match.end() + 30)].lower()
            biz_window = body_str[max(0, match.start() - 60) : min(len(body_str), match.end() + 60)].lower()

            if re.search(r"\b(?:salary|compensation|base\s+pay|base\s+salary|annual\s+pay|pay\s+rate|pay\s+package|signing\s+bonus|bonus|equity|stock|ote|hourly|rate|target\s+comp|comp\s+package|retainer|per\s+hour|per\s+year)\b|/(?:hr|hour|yr|year)\b", comp_window, re.IGNORECASE):
                violations.append(f"Forbidden compensation claim detected: '{matched_str}'. Compensation discussions are strictly prohibited in cold outreach before first reply.")
                continue
            if verified_facts and any(
                (getattr(f, "has_provenance", False) or bool(getattr(f, "source_reference", None) and str(getattr(f, "source_reference")).strip()))
                and (matched_str.lower() in (ft := f"{getattr(f, 'statement', '') or ''} {getattr(f, 'metric', '') or ''}".lower()) or norm_matched in g_val._extract_normalized_dollars(ft))
                for f in verified_facts
            ):
                continue
            if (opportunity_context and (matched_str.lower() in opp_text or norm_matched in opp_dollars)) or any(w in biz_window for w in self._BIZ_KWS):
                continue
            violations.append(f"Forbidden compensation claim detected: '{matched_str}'. Compensation discussions are strictly prohibited in cold outreach before first reply.")

        for pat in self._POLICY_FORBIDDEN_PATTERNS:
            if match := pat.search(body_str):
                violations.append(f"Policy-forbidden claim detected: '{match.group(0)}'.")

        verified_text = " ".join(
            f"{getattr(f, 'statement', f)} {getattr(f, 'metric', '')}"
            for f in (verified_facts or ())
            if getattr(f, "has_provenance", False) or bool(getattr(f, "source_reference", None) and str(getattr(f, "source_reference")).strip())
        ).lower()
        for pat in self._TENURE_PATTERNS:
            if (match := pat.search(body_str)) and match.group(1).lower() not in verified_text:
                violations.append(f"Unverifiable tenure claim detected: '{match.group(0).lower()}'. Claimed duration '{match.group(1).lower()}' is not backed by candidate verified facts with source evidence.")
        return len(violations) == 0, violations


class UnsupportedPersonalizationValidator:
    """Detects and blocks unsupported personalization claiming company strategic priorities without verified briefing evidence."""

    _PERSONALIZATION_PATTERNS = [
        re.compile(r"\b(?:following|noticed)\s+[^,\n]+(?:'s|’s)\s+(?:focus\s+on|priorities\s+in)\s+([^.,\n\?]+)", re.IGNORECASE),
        re.compile(r"\b(?:focus\s+on|priorities\s+in|strategic\s+mandate\s+in)\s+([^.,\n\?]+)", re.IGNORECASE),
    ]

    def validate(self, body: Optional[str], opportunity: Optional[Any] = None) -> tuple[bool, List[str]]:
        body_str, violations = str(body or ""), []
        if opportunity is None:
            return True, violations
        sealed = getattr(opportunity, "sealed_resolution", None)
        is_verified = (bool(sealed.get("is_verified", False)) and sealed.get("resolution_source") != "HERMETIC_FALLBACK") if isinstance(sealed, dict) else not (getattr(opportunity, "_explicit_unsealed", False) or sealed is not None)
        if "UNVERIFIED OFFLINE FALLBACK" in (getattr(opportunity, "briefing_text", "") or ""):
            is_verified = False

        verified_priorities = [p.lower() for p in getattr(opportunity, "strategic_priorities", [])]
        for pat in self._PERSONALIZATION_PATTERNS:
            if match := pat.search(body_str):
                claimed_focus = match.group(1).strip()
                if not is_verified:
                    violations.append(f"Unsupported personalization detected: draft claims company strategic focus '{claimed_focus}' under an unverified briefing resolution.")
                    break
                if not verified_priorities:
                    violations.append(f"Unsupported personalization detected: draft claims company strategic focus '{claimed_focus}' but opportunity has no verified strategic priorities.")
                    break
                focus_tokens = [tok for tok in re.findall(r"\b[A-Za-z]{4,}\b", claimed_focus.lower())]
                if focus_tokens and not any(any(tok in p for tok in focus_tokens) for p in verified_priorities):
                    violations.append(f"Unsupported personalization detected: claimed focus '{claimed_focus}' does not match verified strategic priorities.")
                    break
        return len(violations) == 0, violations


class OutboundPrivacyValidator:
    """Blocks outbound messages containing API secrets, private strategy notes, or personal billing rates."""

    _SECRET_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ]
    _PRIVATE_STRATEGY_PATTERNS: Final[List[re.Pattern[str]]] = [
        re.compile(r"\bINTERNAL_ADVISORY\b"), re.compile(r"\[INTERNAL[^\]]*\]", re.IGNORECASE),
        re.compile(r"\bstealth_score\b", re.IGNORECASE), re.compile(r"\bcareer\s+leverage\b", re.IGNORECASE),
    ]
    _RATE_FLOOR_PATTERNS: Final[List[re.Pattern[str]]] = [re.compile(r"\$\s*\d{2,4}(?:\.\d{2})?\s*/\s*(?:hr|hour)\b", re.IGNORECASE)]

    def validate(self, body: Optional[str]) -> tuple[bool, List[str]]:
        body_str, violations = str(body or ""), []
        if any(pat.search(body_str) for pat in self._SECRET_PATTERNS):
            violations.append("Outbound privacy block: detected API credential or private key pattern.")
        if any(pat.search(body_str) for pat in self._PRIVATE_STRATEGY_PATTERNS):
            violations.append("Outbound privacy block: detected internal advisory or private career strategy marker.")
        if any(pat.search(body_str) for pat in self._RATE_FLOOR_PATTERNS):
            violations.append("Outbound privacy block: detected hourly billing rate disclosure.")
        return len(violations) == 0, violations


__all__ = [
    "ForbiddenClaimsValidator", "GroundingValidator", "METRIC_LAUNDERED_FROM_OPPORTUNITY", "MetricGroundingVerificationResult",
    "OutboundPrivacyValidator", "PCTCertificate", "UNGROUNDED_CANDIDATE_METRIC", "UnsupportedPersonalizationValidator",
    "_METRIC_DOLLAR_PAT", "_METRIC_PERCENT_PAT", "_METRIC_SCALE_PAT", "_extract_normalized_dollars", "_normalize_dollar_token",
    "verify_candidate_metric_grounding",
]
