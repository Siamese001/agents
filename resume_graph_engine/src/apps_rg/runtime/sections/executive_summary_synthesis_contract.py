"""SSOT: SVP executive-summary synthesis arc (U0 targeting → L2 prompt → pre-X2 regen → judge remediation → L6 shadow).

JD/briefing themes are targeting-only (never proof). All prose claims remain bound to ALLOWED_SOURCE_FACT_IDS.
"""

from __future__ import annotations

from typing import Any

# Targeting emphasis themes (JD shapes ranking only — jd_used_as_proof=false).
QUANT_METRIC_DISPLAY_FACT_ID = "fact_quant_hpc_001"
FSA_CREDENTIAL_FACT_ID = "fact_quant_hpc_003"

# Approved S2–S5 transitions (max two stock bridges per paragraph — see I0).
APPROVED_NON_STOCK_OPENERS: tuple[str, ...] = (
    "Across enterprise programs,",
    "Within that ecosystem model,",
    "In parallel,",
    "That platform productization discipline",
    "The same platform discipline",
)

EXEC_SUMMARY_STOCK_BRIDGE_PREFIXES: tuple[str, ...] = (
    "from that",
    "against that",
    "complementing that",
    "building on that",
    "through that",
    "with that governance",
)

# Fact ID for dependency graph intelligence (RC-C: past-tense S6 issue).
DEPENDENCY_GRAPH_FACT_ID = "fact_engineering_platform_002"

# C0 display override for framing-sensitive facts (checked for 1-to-1 parity with judge packet).
FACT_C0_DISPLAY_OVERRIDES: dict[str, str] = {
    FSA_CREDENTIAL_FACT_ID: (
        "That regulatory foundation is grounded in quantitative rigor established through "
        "FSA-chartered actuarial work in capital modeling and portfolio stress analytics, "
        "informing data governance and AI strategy at scale."
    ),
}

SVP_JD_EMPHASIS_THEMES: tuple[str, ...] = (
    "enterprise architecture governance",
    "innovation programs and incubation",
    "multi-year IT strategy and roadmap",
    "federated / post-merger integration",
    "AI and data platform revenue generation",
)

SENTENCE_ARC_AI_PARTNERSHIPS: tuple[dict[str, str], ...] = (
    {
        "brushstroke_id": "B1_executive_identity",
        "arc_role": "partnerships_thesis",
        "guidance": (
            "S1: Sharp applied AI architecture and multi-ecosystem partnerships hook; "
            "lead with current cloud/AI partner co-sell and commercial platform adoption "
            "across hyperscaler and GSI channel ecosystems (never name employer brands or TARGET_COMPANY)."
        ),
    },
    {
        "brushstroke_id": "B2_governed_platform_system",
        "arc_role": "platform_and_partner_motion",
        "guidance": (
            "S2: Reusable multi-model agentic AI platform architecture and joint cloud/AI solution patterns "
            "from allowed facts; max two mechanism terms verbatim."
        ),
    },
    {
        "brushstroke_id": "B3_control_evidence_discipline",
        "arc_role": "commercial_and_enablement_outcomes",
        "guidance": (
            "S3: Weave reserved partner co-sell, IP-led platform revenue, seat-scaling, and production "
            "enablement outcomes from allowed facts into crisp prose; zero AI bridge crutches."
        ),
    },
    {
        "brushstroke_id": "B4_business_role_fit",
        "arc_role": "ecosystem_capstone",
        "guidance": (
            "S4 (optional if 3 crisp sentences land cleanly in 420-680 chars): forward-modal capstone grounded in "
            "cited source_fact_ids projecting how reusable AI platform productization and partner co-sell scale "
            "enterprise AI adoption; never name TARGET_COMPANY."
        ),
    },
)


def classify_exec_summary_role_archetype(
    *,
    target_role: str = "",
    jd_text: str = "",
    briefing_text: str = "",
) -> str:
    """Classify executive summary role archetype for prompt and sentence-arc adaptation."""
    title_low = str(target_role or "").lower()
    blob = f"{target_role} {jd_text} {briefing_text}".lower()
    is_partner_title = any(
        k in title_low
        for k in ("partnership", "alliances", "ecosystem", "partner", "channel", "co-sell", "cosell")
    )
    if not is_partner_title and any(
        k in title_low
        for k in (
            "forward deployed",
            "forward-deployed",
            "forward deployment",
            "field engineering",
            "deployment engineering",
        )
    ):
        return "agentic_platform"
    if is_partner_title or (
        any(
            k in blob
            for k in (
                "co-sell",
                "cosell",
                "channel partner",
                "hyperscaler alliance",
                "joint go-to-market",
                "gsi",
                "system integrator",
            )
        )
        and any(k in blob for k in ("applied ai", "solution architecture", "gsi", "hyperscaler", "co-sell", "cosell"))
    ):
        return "ai_partnerships"
    if any(k in title_low for k in ("it strategy", "strategy & innovation", "strategy and innovation", "chief information", "cio", "cito")):
        return "it_strategy_regulated"
    if any(k in title_low for k in ("transformation", "advisory", "consulting")):
        return "enterprise_transformation"
    return "agentic_platform"

SENTENCE_ARC_SVP_STRATEGY: tuple[dict[str, str], ...] = (
    {
        "brushstroke_id": "B1_executive_identity",
        "arc_role": "strategy_thesis",
        "guidance": (
            "S1: Sharp technology strategy / enterprise technology executive thesis; frame enterprise IT direction "
            "and innovation-program leadership for regulated enterprises (targeting vocabulary only — never JD-as-proof)."
        ),
    },
    {
        "brushstroke_id": "B2_governed_platform_system",
        "arc_role": "platform_and_scale_proof",
        "guidance": (
            "S2: Flagship governed AI platform architecture, team scale, and IP-led revenue/margin outcomes from allowed "
            "facts; max two mechanism terms verbatim; zero AI bridge crutches."
        ),
    },
    {
        "brushstroke_id": "B3_control_evidence_discipline",
        "arc_role": "governance_and_quant_proof",
        "guidance": (
            "S3: Distinct regulatory lineage, risk governance, or quantitative HPC stress-testing outcome with allowed "
            "percentage metrics woven naturally into prose (never list derivatives or cert-label stacks)."
        ),
    },
    {
        "brushstroke_id": "B4_business_role_fit",
        "arc_role": "enterprise_capstone",
        "guidance": (
            "S4 (optional if 3 crisp sentences land cleanly in 420-680 chars): forward-looking mandate fit grounded in "
            "cited source_fact_ids projecting how this rare combination scales federated innovation; never recap S1-S3, "
            "never name TARGET_COMPANY, never open with 'Looking ahead,'."
        ),
    },
)


def format_s6_briefing_forward_targeting_anchor(
    *,
    briefing_text: str = "",
    jd_text: str = "",
) -> str:
    """Targeting-only S6 forward themes from JD/briefing (never proof)."""
    blob = f"{briefing_text} {jd_text}".lower()
    themes: list[str] = []
    has_fde_signal = any(
        tok in blob
        for tok in (
            "forward deployed",
            "forward-deployed",
            "rapid prototyping",
            "prototype to production",
            "production activation",
            "embedded engineering",
        )
    )
    has_explicit_partner_channel = any(
        tok in blob
        for tok in (
            "co-sell",
            "cosell",
            "gsi",
            "system integrator",
            "hyperscaler alliance",
            "channel partner",
            "joint go-to-market",
            "partner-led",
        )
    )
    if has_fde_signal and not has_explicit_partner_channel:
        themes.append(
            "forward-deployed AI engineering execution, rapid prototyping-to-production activation, and business-line engineering alignment"
        )
    elif has_explicit_partner_channel or (
        "partnership" in blob and any(tok in blob for tok in ("hyperscaler", "co-sell", "cosell", "gsi"))
    ):
        themes.append("partner-facing applied AI solution architecture and joint go-to-market execution")
    if any(tok in blob for tok in ("deployment", "commercial adoption", "production rollout", "reusable")):
        themes.append("enterprise AI deployment velocity and commercial platform adoption")
    if any(tok in blob for tok in ("decentral", "autonomous unit", "federated", "operating unit")):
        themes.append("decentralized operating units")
    if "innovation" in blob and not has_fde_signal:
        themes.append("innovation incubation and architecture standards")
    if ("enterprise architecture" in blob or " ea " in f" {blob} ") and len(themes) < 2:
        themes.append("enterprise architecture governance")
    if ("multi-year" in blob or "roadmap" in blob) and len(themes) < 2:
        themes.append("multi-year IT strategy roadmap")
    if not themes:
        themes.append("enterprise AI platform direction, production engineering execution, and governed business adoption")
    joined = "; ".join(themes)
    return (
        f"TARGETING_FORWARD_ANCHOR (targeting only — jd_used_as_proof=false): {joined}."
    )


def format_svp_jd_emphasis_line() -> str:
    themes = "; ".join(SVP_JD_EMPHASIS_THEMES)
    return (
        f"- JD/briefing may tilt emphasis among evidenced themes only ({themes}) — leadership stays primary, "
        "role family cannot reorder the arc, and JD never becomes proof.\n"
    )


def format_leadership_first_exec_summary_block(*, target_title: str = "") -> str:
    """Universal exec-summary targeting note: leadership first, JD only tunes emphasis."""
    role = (target_title or "the target role").strip()
    return (
        "LEADERSHIP_FIRST_EXEC_SUMMARY (targeting only - NOT PROOF):\n"
        "- Regardless of JD or role family, lead the executive summary with a commanding executive role-identity "
        "phrase (e.g. 'Engineering executive...', 'Enterprise technology and AI platform executive...'), "
        "organizational leadership scope, decision-making, and operating model before domain-specific keywords; "
        "never open with robotic third-person subjects like 'Executive leadership architects...' or 'Executive leadership identity...'.\n"
        "- Synthesize a crisp 3-to-4 sentence spoken executive arc (420 to 680 characters, max 210 chars/sentence) across "
        "the allowed C0 facts without AI bridge crutches or dumping internal codebase package, readiness-gate, or MCP server counts.\n"
        "- JD and briefing only tune emphasis among proven facts; they do not reorder the arc or replace "
        "graph-backed evidence.\n"
        f"- Write for {role} as a leadership story first, then weave role-specific evidence and graph skills.\n"
    )


_INTEROP_PROOF_MARKERS = (
    "interop",
    "federated",
    "accession",
    "brokerage",
    "enterprise_architecture",
    "ea_",
)

_UNSUPPORTED_INDUSTRY_REGEN_PHRASES = (
    "insurance brokerage",
    "insurance-sector",
    "insurance sector",
    "federated insurance",
    "insurance operations",
    "insurance-brokerage",
)


def has_svp_targeting_proof_gap(*, allowed_fact_ids: set[str] | frozenset[str]) -> bool:
    """True when allowlist lacks EA/interop/federated proof IDs (Brown SVP lane)."""
    allowed = {str(x).lower() for x in allowed_fact_ids}
    has_interop_proof = any(any(m in fid for m in _INTEROP_PROOF_MARKERS) for fid in allowed)
    return not has_interop_proof


def format_judge_regen_proof_boundary_guard() -> str:
    """Regen-turn guard when TARGETING_GAP is active — blocks X2 industry-claim failures."""
    return (
        "PROOF_BOUNDARY_REGEN: JD/briefing are targeting-only (jd_used_as_proof=false). "
        "Do NOT introduce insurance brokerage, insurance operations, federated insurance, or other "
        "industry-sector nouns in resume_display_text unless an ALLOWED_SOURCE_FACT_ID claim_text "
        "explicitly supports that domain."
    )


def format_judge_regen_proof_gap_reframe_line() -> str:
    """Replacement guidance when verbatim judge feedback asks for unsupported industry framing."""
    return (
        "- PROOF_GAP_REFRAME: Sharpen S1/S6 with targeting vocabulary only (decentralized operating units, "
        "federated operating-model posture, innovation-program mandate) — never add insurance-sector "
        "nouns unless ALLOWED_SOURCE_FACT_IDS support them."
    )


def filter_judge_remediation_feedback_for_proof_gap(
    lines: list[str],
    *,
    allowed_fact_ids: set[str] | frozenset[str],
) -> tuple[list[str], dict[str, Any]]:
    """Drop/reframe judge delta lines that instruct unsupported industry claims."""
    if not has_svp_targeting_proof_gap(allowed_fact_ids=allowed_fact_ids):
        return list(lines), {"proof_gap_filter": "inactive", "dropped_count": 0}

    kept: list[str] = []
    dropped: list[str] = []
    for line in lines:
        low = str(line).lower()
        if any(phrase in low for phrase in _UNSUPPORTED_INDUSTRY_REGEN_PHRASES):
            dropped.append(line)
            continue
        if "insurance" in low and any(
            tok in low
            for tok in (
                "brokerage context",
                "insurance-sector",
                "insurance sector",
                "federated insurance",
                "insurance operations",
            )
        ):
            dropped.append(line)
            continue
        kept.append(line)

    meta: dict[str, Any] = {
        "proof_gap_filter": "active",
        "dropped_count": len(dropped),
        "dropped_preview": [d[:120] for d in dropped[:4]],
    }
    if dropped:
        reframe = format_judge_regen_proof_gap_reframe_line()
        if reframe not in kept:
            kept.insert(0, reframe)
        meta["reframe_inserted"] = True
    return kept, meta


def format_strategy_targeting_gap_note(*, allowed_fact_ids: set[str] | frozenset[str]) -> str:
    """When JD themes lack proof IDs, require gap_notes + concept translation (not JD-as-proof)."""
    allowed = {str(x).lower() for x in allowed_fact_ids}
    has_interop_proof = any(any(m in fid for m in _INTEROP_PROOF_MARKERS) for fid in allowed)
    concept_block = (
        "TARGETING_CONCEPT_MAP (targeting only — NOT PROOF):\n"
        "- Translate allowed platform/governance/commercial/regulated-delivery facts into executive concepts: "
        "enterprise IT strategy, architecture modernization, innovation incubation, lineage-ready operating models, "
        "and regulated enterprise scale — without claiming insurance brokerage, federated M&A integration, or "
        "interoperability product experience unless matching ALLOWED_SOURCE_FACT_IDs exist.\n"
        "- Do not keyword-stuff JD phrases; use causal synthesis so an SVP IT Strategy reader sees strategic fit.\n"
    )
    if has_interop_proof:
        return concept_block
    return (
        concept_block
        + "TARGETING_GAP: No EA/interop/federated proof IDs in allowlist — set "
        "gap_notes.svp_targeting_theme_gap_explained=true; emphasize platform/governance/commercial facts only "
        "(jd_used_as_proof=false).\n"
    )


def format_strategy_executive_u0_block(*, target_title: str = "") -> str:
    """U0 targeting appendix for SVP IT strategy / innovation lanes (injected at PA compile)."""
    role = (target_title or "SVP IT strategy").strip()
    return (
        "STRATEGY_EXECUTIVE_SYNTHESIS (targeting only — NOT PROOF):\n"
        "- Required JSON field `executive_strategy_thesis` before `resume_display_text` (one ledger-backed sentence).\n"
        "- Open S1 with a sharp, boardroom-spoken executive hook; zero generic filler and zero repetitive 'That...' or AI transition crutches ('In parallel,', 'Building on that', 'Across enterprise programs,', 'From that commercial base').\n"
        "- Visual layout band: 3 to 4 crisp sentences totaling 420 to 680 characters (max 210 chars/sentence, 110-word overflow safety cap, zero word minimum) with varied sentence lengths (spread >= 4 words) and distinct sentence openers.\n"
        "- Foreground measurable commercial, scale, and regulated governance impact early in display prose (never hide metrics only in claim_ledger).\n"
        "- Final sentence (when using 4 sentences): crisp forward-looking mandate fit grounded in source_fact_ids projecting how this rare combination advances the "
        f"{role} mandate; forbidden: 'Looking ahead,', 'extend that arc toward', 'this leadership profile', 'can translate into'.\n"
        f"{format_svp_jd_emphasis_line()}"
        f"- Target role framing: {role} (positioning only). NEVER name TARGET_COMPANY in resume_display_text.\n"
    )


def format_synthesis_repair_directive(*, strategy_executive: bool) -> str:
    """Pre-X2 same-authority regen addendum (L2 repair path)."""
    if not strategy_executive:
        return ""
    return (
        "SVP_SYNTHESIS_ARC: Write 3 to 4 crisp, spoken boardroom sentences (420 to 680 chars, zero AI bridge crutches): "
        "S1 sharp executive hook; S2 flagship platform/scale proof with concrete metrics; S3 distinct commercial/governance "
        "outcome; optional S4 forward mandate fit grounded in allowed facts only (jd_used_as_proof=false). "
    )


def format_judge_regen_mechanical_opener_guard() -> str:
    """X2 mechanical-opener stack guard for judge regen (max 2 sentences with bullet-style openers)."""
    from apps_rg.runtime.validators.executive_summary_x2 import EXEC_SUMMARY_MECHANICAL_OPENERS

    openers = ", ".join(EXEC_SUMMARY_MECHANICAL_OPENERS)
    return (
        f"MECHANICAL_OPENER_GUARD: at most 2 sentences may start with ({openers}); "
        "vary sentence openers for executive synthesis (not a resume bullet chain).\n"
    )


def format_judge_regen_soft_material_preservation(
    *,
    prior_word_count: int,
    prior_ledger_rows: int,
) -> str:
    """Soft regen guidance — visual layout band (3-4 sentences, 420-680 chars, zero word minimum)."""
    return (
        "MATERIAL_PRESERVATION (soft — not a word-count floor; hard X2 gates still apply):\n"
        "- Preserve material claims and ledger-backed support unless removal is required to satisfy "
        "X2 or judge feedback.\n"
        "- Stay within the SSOT visual layout band (3 to 4 sentences, 420 to 680 characters, max 210 chars/sentence, "
        "max 110 words overflow cap); do not pad or bloat to match prior length.\n"
        f"- Prior draft reference only: ~{max(0, prior_word_count)} words, "
        f"{max(0, prior_ledger_rows)} claim_ledger rows (zero minimum word count).\n"
        "- Weave unused allowed facts into prose and claim_ledger when grounded proof is missing; "
        "do not drop cited source_fact_ids without cause.\n"
        "- 3 to 4 sentences in resume_display_text; claim_ledger row count matches sentence count (1-to-1).\n"
    )


def format_judge_regen_x2_floor(*, prior_word_count: int, prior_ledger_rows: int) -> str:
    """Backward-compatible alias — delegates to soft material preservation (no word minimum)."""
    return format_judge_regen_soft_material_preservation(
        prior_word_count=prior_word_count,
        prior_ledger_rows=prior_ledger_rows,
    )


def failed_x2_gate_ids(failed_gates: list[dict[str, Any]]) -> frozenset[str]:
    """Gate IDs that failed in an X2 gate row list."""
    out: set[str] = set()
    for row in failed_gates:
        if not isinstance(row, dict) or row.get("pass"):
            continue
        gid = str(row.get("gate_id") or "").strip()
        if gid.startswith("x2_"):
            out.add(gid)
    return frozenset(out)


def gate_ids_from_x2_reject_reason(reject_reason: str) -> frozenset[str]:
    """Parse ``gate_id: detail`` segments from ``format_x2_gate_failures_reject_reason`` output."""
    out: set[str] = set()
    for part in str(reject_reason or "").split(";"):
        chunk = part.strip()
        if not chunk or ":" not in chunk:
            continue
        gid = chunk.split(":", 1)[0].strip()
        if gid.startswith("x2_"):
            out.add(gid)
    return frozenset(out)


def format_x2_gate_failures_reject_reason(failed_gates: list[dict[str, Any]]) -> str:
    """Map post-regen X2 gate rows into synthesis-repair reject_reason vocabulary."""
    parts: list[str] = []
    for row in failed_gates:
        if not isinstance(row, dict) or row.get("pass"):
            continue
        gid = str(row.get("gate_id") or "x2_gate")
        reason = str(row.get("reason") or row.get("message") or "fail")
        parts.append(f"{gid}: {reason}")
    return "; ".join(parts) if parts else "x2_regen_failed"


def format_judge_remediation_synthesis_default() -> str:
    """Default synthesis line when judge feedback is sparse (post-X1D regen)."""
    return (
        "elevate hiring-committee conviction and spoken executive authenticity across 3 to 4 crisp sentences "
        "(420 to 680 characters total, zero AI bridge crutches or abstract noun soup): "
        "S1 sharp executive hook with scale and rare differentiator; "
        "S2 flagship technical/platform proof with concrete metrics; "
        "S3 distinct commercial or regulated governance outcome with allowed numbers; "
        "optional S4 crisp forward mandate fit from allowed facts only (no vendor cert laundry list; "
        "no cover-letter meta phrasing such as 'this leadership profile' or 'can translate into'; "
        "optional single FSA rigor clause only when fact_quant_hpc supports it); "
        "tilt emphasis toward enterprise architecture, federated integration, innovation incubation, "
        "multi-year IT strategy from JD (targeting only; jd_used_as_proof=false)"
    )


def format_judge_regen_connective_tissue_guard() -> str:
    """Require causal links between sentences for certification-grade synthesis."""
    return (
        "CONNECTIVE_TISSUE: S2 must bridge from S1 thesis (e.g. 'This platform foundation…', "
        "'Building on that direction…'); S3–S5 each open with a causal link to the prior sentence, "
        "not a bare Led/Built/Implemented/Re-architected resume bullet. "
        "Avoid one-fact-per-sentence inventory; read as one executive paragraph.\n"
    )


def format_l6_judge_soft_fail_recommendation(*, soft_judges: list[str]) -> str:
    judges = ", ".join(soft_judges) if soft_judges else "soft-fail judge"
    return (
        f"Executive summary judge soft-fail ({judges}): regenerate with SVP synthesis contract — "
        "connective S3–S4 (platform + innovation + operating model), ≤1 metric in S5, "
        "integrative S6 capstone with no cover-letter meta phrasing; JD themes for emphasis only "
        "(enterprise architecture, innovation, IT strategy); "
        "enable APPS_RG_EXEC_SUMMARY_JUDGE_REGEN=1 when X2 is green and one judge fails on synthesis."
    )


__all__ = [
    "DEPENDENCY_GRAPH_FACT_ID",
    "FSA_CREDENTIAL_FACT_ID",
    "format_leadership_first_exec_summary_block",
    "QUANT_METRIC_DISPLAY_FACT_ID",
    "SENTENCE_ARC_AI_PARTNERSHIPS",
    "SENTENCE_ARC_SVP_STRATEGY",
    "SVP_JD_EMPHASIS_THEMES",
    "classify_exec_summary_role_archetype",
    "format_s6_briefing_forward_targeting_anchor",
    "failed_x2_gate_ids",
    "gate_ids_from_x2_reject_reason",
    "format_judge_regen_x2_floor",
    "format_x2_gate_failures_reject_reason",
    "format_judge_regen_connective_tissue_guard",
    "format_judge_remediation_synthesis_default",
    "format_l6_judge_soft_fail_recommendation",
    "format_strategy_executive_u0_block",
    "format_synthesis_repair_directive",
    "format_svp_jd_emphasis_line",
]
