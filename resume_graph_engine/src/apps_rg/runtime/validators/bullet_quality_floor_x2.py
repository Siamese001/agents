"""Quality floor X2 gate helpers for bullet generation (W4: Bullet Proof Bundle Redesign).

Implements deterministic proxy gates (no LLM required):
- x2_bullet_seniority_floor: strong action verb + scale signal required
- x2_bullet_technical_specificity_floor: named mechanism, technology, or domain term required
- x2_no_generic_consulting_substitution: extended GENERIC_FILLER blocklist for consulting-speak
- x2_experience_bullet_evidence_density_required: concrete delivery detail plus a
  business, adoption, efficiency, risk, or delivery result required

These gates catch low-quality bullets that passed structural gates but lack the depth
of an SVP Engineering-level candidate narrative.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Seniority floor: strong action verbs and organizational scale signals
# ---------------------------------------------------------------------------

STRONG_ACTION_VERBS: frozenset[str] = frozenset({
    "architected", "architect", "engineered", "engineer", "operationalized", "operationalize",
    "directed", "direct", "structured", "converted", "convert", "deployed", "designed",
    "established", "establish", "led", "lead", "built", "build", "launched", "launch",
    "modernized", "modernize", "forged", "forge", "drove", "drive", "productized",
    "productize", "standardized", "standardize", "unified", "unify", "accelerated",
    "accelerate", "cut", "scaled", "scale", "transformed", "transform", "generated",
    "generate", "delivered", "deliver", "created", "create", "implemented", "implement",
    "developed", "develop", "oversaw", "oversee", "managed", "manage", "steered", "steer",
    "instituted", "institute", "commercialized", "commercialize", "pioneered", "pioneer",
    "defined", "define", "spearheaded", "spearhead", "owned", "own", "headed", "head",
    "championed", "champion", "governed", "govern",
    "embedded", "embed", "ran", "run",
    "re-architected", "rearchitected", "re-engineered", "reengineered",
    "re-platformed", "replatformed",
})

def _is_strong_action_verb(word: str) -> bool:
    w = word.lower().strip()
    if w in STRONG_ACTION_VERBS:
        return True
    if w.startswith("re-") and w[3:] in STRONG_ACTION_VERBS:
        return True
    if w.startswith("re") and len(w) > 4 and w[2:] in STRONG_ACTION_VERBS:
        return True
    w_unhyphenated = w.replace("-", "")
    if w_unhyphenated in STRONG_ACTION_VERBS:
        return True
    return False

WEAK_ACTION_VERBS: frozenset[str] = frozenset({
    "supported", "helped", "assisted", "worked on", "participated", "contributed",
    "involved in", "part of", "utilized",
})

SCALE_SIGNALS: frozenset[str] = frozenset({
    "fortune 500", "enterprise", "financial institutions", "regulated", "global",
    "large-scale", "enterprise-scale", "multi-year", "hyperscaler", "cross-functional",
    "regulated financial", "fortune", "billion", "multi-million",
})

_NUMERIC_SIGNAL_PATTERN = re.compile(
    r"\$\d+[mk]?\b|\b\d+[\.,]\d+%|\b\d+%|\b\d+x\b|\b\d+\s+to\s+\d+\b|"
    r"\b\d+\s*(?:percent|million|billion)\b",
    re.IGNORECASE,
)
_FIRST_WORD_RE = re.compile(r"^\s*([a-zA-Z]+(?:-[a-zA-Z]+)?)")

# A result does not have to be a number.  Production, adoption, control,
# reliability, and delivery results are legitimate résumé outcomes when the
# graph-backed source does not contain a numeric metric.  Generic capability
# nouns are deliberately excluded.
_OUTCOME_SIGNAL_PATTERN = re.compile(
    r"\b(?:generated|increased|grew|improved|reduced|cut|compress(?:ed|ing|ion)|accelerated|"
    r"expanded|scal(?:ed|ing)|converted|standardized|operationalized|"
    r"establish(?:ed|ing|ment)|enabl(?:ed|ing)|deliver(?:ed|ing|y)|"
    r"deployed|launched|adopt(?:ed|ion|ing)|moderni[sz](?:ed|ing|ation)|"
    r"migrat(?:ed|ing|ion)|replatform(?:ed|ing)|remediat(?:ed|ing|ion)|"
    r"(?:high\s+)?availability|production|uptime|reliability|coverage|audit(?:able|-ready|-grade)?|"
    r"validat(?:e|ed|ing|ion|ions)?|"
    r"risk\s+(?:reduction|remediation|control|visibility)|"
    r"compliance\s+(?:readiness|evidence|coverage)|renewal|revenue|margin|pipeline|"
    r"cycle\s+time|latency|throughput|sponsorship|opportunity\s+progression)\b",
    re.IGNORECASE,
)
_CONCRETE_DELIVERY_PATTERN = re.compile(
    r"\b(?:aws|azure|gcp|databricks|kafka|kubernetes|api|microservices|"
    r"route[- ]policy|control plane|runtime|observability|lineage|retrieval|"
    r"solution architecture|reference architecture|account planning|"
    r"subscription forecasting|proof bundle|policy[- ]gated|soc ?2|"
    r"shared responsibility|financial-services|financial services|"
    r"insur(?:ance|tech|er|ers)?|"
    r"value[- ]realization|expansion\s+readiness|adoption\s+progress|"
    r"regulated|enterprise|production|deployment|integration)\b",
    re.IGNORECASE,
)
_CAPABILITY_ONLY_PATTERN = re.compile(
    r"^\s*(?:built|developed|forged|created|delivered)\s+(?:a\s+|an\s+)?"
    r"(?:(?:[\w/-]+)\s+){0,3}"
    r"(?:framework|frameworks|asset|assets|capability|capabilities|service|services|solution|solutions)\b",
    re.IGNORECASE,
)

SENIORITY_FLOOR_SCORE = 1  # Minimum score to pass the seniority gate


def _score_bullet_seniority(bullet_text: str) -> tuple[int, list[str]]:
    """Compute a deterministic seniority proxy score for a bullet.

    Returns (score, reasons) where:
    - +1 for strong action verb at start
    - +1 for organizational scale signal present
    - +1 for numeric metric present ($XM, XX%, etc.)
    - -1 for weak action verb at start
    """
    text_lower = bullet_text.lower().strip()
    score = 0
    signals: list[str] = []

    first_match = _FIRST_WORD_RE.match(text_lower)
    first_word = first_match.group(1) if first_match else ""

    if _is_strong_action_verb(first_word):
        score += 1
        signals.append(f"strong_verb:{first_word}")
    elif first_word in WEAK_ACTION_VERBS:
        score -= 1
        signals.append(f"weak_verb:{first_word}")
    elif any(text_lower.startswith(wv) for wv in WEAK_ACTION_VERBS):
        score -= 1
        signals.append("weak_verb_phrase")

    for sig in SCALE_SIGNALS:
        if sig in text_lower:
            score += 1
            signals.append(f"scale_signal:{sig}")
            break

    if _NUMERIC_SIGNAL_PATTERN.search(bullet_text):
        score += 1
        signals.append("numeric_metric")

    return score, signals


# ---------------------------------------------------------------------------
# Technical specificity floor: named mechanism, technology, or domain term
# ---------------------------------------------------------------------------

# Consulting-speak substitution patterns that replace specific technical mechanisms
GENERIC_CONSULTING_SUBSTITUTIONS: frozenset[str] = frozenset({
    # Plan-spec blocklist
    "drive strategic value",
    "ensure alignment",
    "stakeholder management",
    "delivered solutions",
    "managed the relationship",
    "worked closely with",
    "collaborated to deliver",
    "ensured the platform",
    "leveraged best practices",
    # Additional consulting filler
    "best-in-class solutions",
    "value-added solutions",
    "end-to-end solutions",
    "key stakeholders",
    "thought leadership",
    "strategic alignment",
    "holistic approach",
    "synergies",
    "robust framework",
    "go-to-market strategy",
    "driving growth",
    "enabling innovation",
    "key deliverables",
    "seamless integration",
    "best practices",
    "actionable insights",
})

_TECH_TOKEN_PATTERN = re.compile(
    r"\b(?:"
    r"aws|azure|gcp|databricks|kafka|kubernetes|docker|terraform|"
    r"python|scala|spark|sql|api|rest|graphql|hpc|microservices|"
    r"llm|gpt|claude|ai|ml|nlp|rag|graphrag|vector|embedding|"
    r"lineage|observability|telemetry|latency|throughput|sla|uptime|"
    r"runtime|control.plane|route.policy|deterministic|policy.gate|"
    r"policy.gating|execution.trace|traceability|sandbox|"
    r"cloud.native|cloud|platform|architecture|infrastructure|pipelines?|devsecops|ci/cd|cicd|"
    r"bi|dashboard|dashboards|data.model|data.models|semantic.view|semantic.views|"
    r"regulatory|compliance|basel|ccar|sox|iso|"
    r"saas|paas|iaas|serverless|lambda|"
    r"consumption.based\s+licensing|renewal.signal\s+instrumentation|"
    r"usage.based\s+subscription\s+forecasting|subscription\s+forecasting|"
    r"value[- ]realization|expansion\s+readiness|adoption\s+progress|"
    r"kubernetes|etl|data.lake|lakehouse|warehouse"
    r")\b",
    re.IGNORECASE,
)


def _has_technical_specificity(bullet_text: str, mechanism_vocab: list[str] | None = None) -> bool:
    """True if bullet contains at least one named mechanism, technology, or domain term.

    Accepts:
    - Known technology tokens (AWS, Databricks, Kafka, etc.)
    - Mechanism vocabulary tokens from the proof bundle for this bullet slot
    """
    if _TECH_TOKEN_PATTERN.search(bullet_text):
        return True
    if mechanism_vocab:
        text_lower = bullet_text.lower()
        return any(str(v).lower() in text_lower for v in mechanism_vocab if v)
    return False


def _has_consulting_substitution(bullet_text: str) -> list[str]:
    """Return list of consulting-speak substitution phrases found in bullet_text."""
    text_lower = bullet_text.lower()
    return [phrase for phrase in GENERIC_CONSULTING_SUBSTITUTIONS if phrase in text_lower]


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------

@dataclass
class QualityFloorResult:
    gate_id: str
    passed: bool
    bullet_id: str
    score: int
    signals: list[str]
    failure_reason: str | None


def check_bullet_seniority_floor(
    bullet_id: str,
    bullet_text: str,
    *,
    floor: int = SENIORITY_FLOOR_SCORE,
) -> QualityFloorResult:
    score, signals = _score_bullet_seniority(bullet_text)
    passed = score >= floor
    return QualityFloorResult(
        gate_id="x2_bullet_seniority_floor",
        passed=passed,
        bullet_id=bullet_id,
        score=score,
        signals=signals,
        failure_reason=(
            f"{bullet_id}: seniority score {score} < floor {floor} (signals={signals})"
            if not passed
            else None
        ),
    )


def check_bullet_technical_specificity_floor(
    bullet_id: str,
    bullet_text: str,
    *,
    mechanism_vocab: list[str] | None = None,
) -> QualityFloorResult:
    has_tech = _has_technical_specificity(bullet_text, mechanism_vocab=mechanism_vocab)
    return QualityFloorResult(
        gate_id="x2_bullet_technical_specificity_floor",
        passed=has_tech,
        bullet_id=bullet_id,
        score=1 if has_tech else 0,
        signals=["tech_token_found"] if has_tech else [],
        failure_reason=(
            f"{bullet_id}: no named mechanism/technology in bullet text"
            if not has_tech
            else None
        ),
    )


def check_bullet_no_generic_consulting_substitution(
    bullet_id: str,
    bullet_text: str,
) -> QualityFloorResult:
    hits = _has_consulting_substitution(bullet_text)
    return QualityFloorResult(
        gate_id="x2_no_generic_consulting_substitution",
        passed=not hits,
        bullet_id=bullet_id,
        score=0 if hits else 1,
        signals=hits,
        failure_reason=(
            f"{bullet_id}: consulting-speak substitution phrases: {hits}"
            if hits
            else None
        ),
    )


def check_experience_bullet_evidence_density(
    bullet_id: str,
    bullet_text: str,
    *,
    mechanism_vocab: list[str] | None = None,
) -> QualityFloorResult:
    """Reject capability-only experience bullets that lack detail or a result.

    This is intentionally content-only.  The lane's existing proof-pool and
    metric-lineage gates remain responsible for proving that any asserted
    outcome belongs to the cited graph path.
    """

    text = str(bullet_text or "").strip()
    first_match = _FIRST_WORD_RE.match(text.lower())
    action = first_match.group(1) if first_match else ""
    has_action = _is_strong_action_verb(action)
    has_delivery_detail = bool(_CONCRETE_DELIVERY_PATTERN.search(text)) or _has_technical_specificity(
        text,
        mechanism_vocab=mechanism_vocab,
    )
    has_outcome = bool(_NUMERIC_SIGNAL_PATTERN.search(text) or _OUTCOME_SIGNAL_PATTERN.search(text))
    capability_only = bool(_CAPABILITY_ONLY_PATTERN.search(text)) and not has_outcome
    signals = [
        signal
        for signal, present in (
            (f"strong_verb:{action}", has_action),
            ("concrete_delivery_detail", has_delivery_detail),
            ("outcome_signal", has_outcome),
            ("capability_only", capability_only),
        )
        if present
    ]
    passed = has_action and has_delivery_detail and has_outcome and not capability_only
    missing = [
        label
        for label, present in (
            ("specific_action", has_action),
            ("concrete_delivery_detail", has_delivery_detail),
            ("business_or_delivery_outcome", has_outcome),
        )
        if not present
    ]
    if capability_only:
        missing.append("capability_only_statement")
    return QualityFloorResult(
        gate_id="x2_experience_bullet_evidence_density_required",
        passed=passed,
        bullet_id=bullet_id,
        score=int(has_action) + int(has_delivery_detail) + int(has_outcome) - int(capability_only),
        signals=signals,
        failure_reason=(
            f"{bullet_id}: insufficient experience-bullet evidence density; missing={missing}"
            if not passed
            else None
        ),
    )


def run_bullet_quality_floor_gates(
    bullets: list[dict[str, Any]],
    *,
    section_id: str,
    mechanism_vocab_by_slot: dict[str, list[str]] | None = None,
    seniority_floor: int = SENIORITY_FLOOR_SCORE,
) -> tuple[
    bool,  # seniority gate overall pass
    list[QualityFloorResult],  # per bullet seniority results
    bool,  # technical specificity gate overall pass
    list[QualityFloorResult],  # per bullet tech results
    bool,  # no-generic-consulting gate overall pass
    list[QualityFloorResult],  # per bullet consulting results
]:
    """Run all three quality floor gates across all bullets in a section."""
    bullet_id_prefix = "bul_ibm_" if section_id == "ibm_bullets" else "bul_unify_"
    seniority_results: list[QualityFloorResult] = []
    tech_results: list[QualityFloorResult] = []
    consulting_results: list[QualityFloorResult] = []

    for b in bullets:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("bullet_id") or "")
        if not bid.startswith(bullet_id_prefix):
            continue
        text = str(b.get("bullet_text") or "").strip()
        if not text:
            continue

        seniority_results.append(
            check_bullet_seniority_floor(bid, text, floor=seniority_floor)
        )
        vocab = (mechanism_vocab_by_slot or {}).get(bid)
        tech_results.append(
            check_bullet_technical_specificity_floor(bid, text, mechanism_vocab=vocab)
        )
        consulting_results.append(
            check_bullet_no_generic_consulting_substitution(bid, text)
        )

    seniority_pass = all(r.passed for r in seniority_results) if seniority_results else True
    tech_pass = all(r.passed for r in tech_results) if tech_results else True
    consulting_pass = all(r.passed for r in consulting_results) if consulting_results else True
    return seniority_pass, seniority_results, tech_pass, tech_results, consulting_pass, consulting_results


__all__ = [
    "GENERIC_CONSULTING_SUBSTITUTIONS",
    "SCALE_SIGNALS",
    "SENIORITY_FLOOR_SCORE",
    "STRONG_ACTION_VERBS",
    "WEAK_ACTION_VERBS",
    "QualityFloorResult",
    "check_bullet_no_generic_consulting_substitution",
    "check_bullet_seniority_floor",
    "check_bullet_technical_specificity_floor",
    "check_experience_bullet_evidence_density",
    "run_bullet_quality_floor_gates",
]
