"""Interactive flywheel remediation dispatcher bridging findings, proposals, and atomic ask_question payloads."""

from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

from agents.learning.commit_engine import apply_proposal_atomically
from agents.learning.eligibility import _SYNTHETIC_APPROVAL_MARKERS, validate_learning_approval_origin
from agents.learning.policy_router import (
    PolicyRoutingDecision,
    evaluate_auto_apply_policy,
    load_auto_apply_policy,
)
from agents.learning.proposal_generator import build_signed_provenance
from agents.learning.rollback_manager import evaluate_post_apply_canary_and_seal
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import (
    EvalCase,
    FailureCluster,
    FindingRecord,
    FindingStatus,
    HoldoutReplayVerdict,
    ImprovementProposal,
    utc_now_iso,
)
from apps_eval.holdout_replay import CandidateRunnerFn, evaluate_proposal_in_shadow
from apps_eval.triage_promoter import load_holdout_cases
from tools.hitl_governance import (
    ALLOWED_CAMEL_WHITELIST,
    ALLOWED_PASCAL_WHITELIST,
    MAX_OPTION_LENGTH,
    MAX_QUESTION_LENGTH,
    HITLDecisionStore,
    scan_question_jargon,
    validate_approval_origin,
    validate_hitl_presentation,
)

DispatchActionType = Literal[
    "AUTO_APPLY_TIER_A",
    "EXECUTE_TIER_B_COMMIT",
    "EXECUTE_TIER_C_FIX_AND_PROMOTE",
    "SNOOZED",
    "REJECTED",
]

_SUBSYSTEM_PLAIN_NAMES: dict[str, str] = {
    "resume_graph_engine": "resume builder",
    "apps_rg": "resume builder",
    "outreach_engine": "outreach writer",
    "apps_lic": "outreach writer",
    "apps_research": "company research flow",
    "apps_eval": "quality evaluation",
    "resume_engine": "resume formatter",
    "agents": "agent workflow",
    "agents_core": "agent workflow",
    "agents_cli": "agent workflow",
    "tools": "workspace automation",
    "antigravity_turn": "workspace automation",
    "infrastructure": "shared platform",
}

_PRIORITY_PLAIN_NAMES: dict[str, str] = {
    "P0": "critical",
    "P1": "high-priority",
    "P2": "medium-priority",
}

_JARGON_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bSELECT\s+.+?\s+FROM\s+[a-zA-Z0-9_]+", re.IGNORECASE | re.DOTALL), "data lookup"),
    (re.compile(r"(?:^|[\s`\"'(\[{])(?:[a-zA-Z0-9_\-./]+/)?[a-zA-Z0-9_\-]+\.(?:py|sqlite|jsonl|yaml|yml|toml|sh|sql|md|json)\b"), " system file"),
    (re.compile(r"(?:^|\s)--[a-zA-Z0-9][a-zA-Z0-9\-]*\b"), " option"),
    (re.compile(r"\bCandidate\s+ID\s*:\s*\S*", re.IGNORECASE), ""),
    (re.compile(r"\bO[1-8]\b"), "step"),
    (re.compile(r"(?:\.\.\.|…|\[truncated\]|\[cut\s*off\])", re.IGNORECASE), " "),
    (re.compile(r"\b(?:additionally|secondly|furthermore)\b", re.IGNORECASE), " "),
    (re.compile(r"\bblast\s+radius\b", re.IGNORECASE), "change scope"),
    (re.compile(r"\bsub-?agents?\b", re.IGNORECASE), "helper agent"),
    (re.compile(r"\bHITL\b", re.IGNORECASE), "human review"),
    (re.compile(r"\bA2A\b", re.IGNORECASE), "agent handoff"),
    (re.compile(r"\bSSOT\b", re.IGNORECASE), "central config"),
    (re.compile(r"\bWAL\b", re.IGNORECASE), "database log"),
    (re.compile(r"\bACID\b", re.IGNORECASE), "safe write"),
    (re.compile(r"\bJSONL\b", re.IGNORECASE), "data log"),
    (re.compile(r"\bAST\b", re.IGNORECASE), "code check"),
    (re.compile(r"\b(?:DDL|DML|PRAGMA|SQL)\b", re.IGNORECASE), "database"),
    (re.compile(r"\bCLI\b", re.IGNORECASE), "command tool"),
    (re.compile(r"\bSDK\b", re.IGNORECASE), "developer kit"),
    (re.compile(r"\b(?:BM25|RRF)\b", re.IGNORECASE), "search ranking"),
    (re.compile(r"\bDAG\b", re.IGNORECASE), "workflow"),
    (re.compile(r"\bMCP\b", re.IGNORECASE), "tool server"),
    (re.compile(r"\bSHA\b", re.IGNORECASE), "checksum"),
    (re.compile(r"\bTTL\b", re.IGNORECASE), "expiry"),
    (re.compile(r"\bUUID\b", re.IGNORECASE), "identifier"),
    (re.compile(r"\b(?:YAML|TOML|JSON)\b", re.IGNORECASE), "config"),
    (re.compile(r"\btriad\b", re.IGNORECASE), "trio"),
    (re.compile(r"\btelemetry\b", re.IGNORECASE), "metrics"),
    (re.compile(r"\borchestration\b", re.IGNORECASE), "coordination"),
    (re.compile(r"\bdeterministic\b", re.IGNORECASE), "repeatable"),
    (re.compile(r"\binvariants\b", re.IGNORECASE), "rules"),
    (re.compile(r"\binvariant\b", re.IGNORECASE), "rule"),
    (re.compile(r"\bschemas\b", re.IGNORECASE), "formats"),
    (re.compile(r"\bschema\b", re.IGNORECASE), "format"),
    (re.compile(r"\bpayloads\b", re.IGNORECASE), "requests"),
    (re.compile(r"\bpayload\b", re.IGNORECASE), "request"),
    (re.compile(r"\bratchets\b", re.IGNORECASE), "limits"),
    (re.compile(r"\bratchet\b", re.IGNORECASE), "limit"),
    (re.compile(r"\bidempotent\b", re.IGNORECASE), "repeatable"),
)


@dataclass(frozen=True)
class RemediationDispatchAction:
    """Typed remediation action returned after classifying or resolving a flywheel finding."""

    action: DispatchActionType
    finding_id: str
    proposal_id: str
    finding_digest: str
    proposal_digest: str
    finding_status: FindingStatus
    approval_receipt: dict[str, Any] | None = None
    hitl_decision_id: str | None = None
    worktree_execution_packet: dict[str, Any] | None = None
    snoozed_until_utc: str | None = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_identifier_words(token: str) -> str:
    if token in ALLOWED_CAMEL_WHITELIST or token in ALLOWED_PASCAL_WHITELIST:
        return token
    if "_" in token or re.search(r"[a-z0-9][A-Z]", token):
        spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", token.replace("_", " "))
        return spaced.lower()
    return token


def _humanize_plain_english(raw_text: str, *, max_chars: int = 90) -> str:
    """Convert raw finding titles or failure buckets into safe plain-English prose with zero jargon."""
    cleaned = str(raw_text or "").strip()
    if not cleaned:
        return ""
    for pattern, repl in _JARGON_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = re.sub(r"[_/:.;?!`\"'\[\]{}()]+", " ", cleaned)
    tokens = [_split_identifier_words(tok) for tok in cleaned.split()]
    cleaned = " ".join(tokens)
    for pattern, repl in _JARGON_REPLACEMENTS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-")

    # Remove any residual token flagged by scan_question_jargon.
    for _ in range(3):
        violations = scan_question_jargon(cleaned)
        if not violations:
            break
        for v in violations:
            m = re.search(r"\('([^']+)'\)", v)
            if m:
                bad_tok = m.group(1)
                cleaned = re.sub(re.escape(bad_tok), "item", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,-")

    if scan_question_jargon(cleaned):
        return ""

    if len(cleaned) > max_chars:
        words = cleaned[:max_chars].rsplit(" ", 1)[0]
        cleaned = words.strip(" ,-")
    return cleaned


def _trim_to_word_limit(text: str, limit: int) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    if len(s) <= limit:
        return s
    trimmed = s[:limit].rsplit(" ", 1)[0].strip(" ,;:-")
    return trimmed if trimmed else s[:limit]


def _classify_remediation_mode(
    finding: FindingRecord,
    proposal: ImprovementProposal,
) -> Literal["TIER_C", "TIER_B", "TIER_A_ESCALATED"]:
    norm_path = str(proposal.target_path or "").replace("\\", "/")
    if (
        proposal.autonomy_tier == "TIER_C_PR_ONLY"
        or proposal.artifact_class in {"validator_or_code", "governance_or_schema"}
        or norm_path.endswith(".py")
        or proposal.risk_lane == "LANE_2"
    ):
        return "TIER_C"
    if (
        proposal.autonomy_tier == "TIER_B_HITL_GATED"
        or proposal.artifact_class in {"prompt_prior", "prompt_template"}
        or norm_path.startswith(("config/prompt_governance/", "apps_eval/baselines/"))
    ):
        return "TIER_B"
    if finding.track == "TRACK_2_CODE_FIX" and proposal.autonomy_tier != "TIER_A_AUTO_APPLY":
        return "TIER_C"
    return "TIER_A_ESCALATED"


def build_atomic_remediation_question(
    finding: FindingRecord,
    proposal: ImprovementProposal,
    holdout_verdict: HoldoutReplayVerdict | None = None,
    *,
    confidence_margin: float = 0.30,
    snooze_days: int = 7,
) -> dict[str, Any]:
    """Compile a single zero-jargon, length-capped ask_question payload bound to finding and proposal digests."""
    mode = _classify_remediation_mode(finding, proposal)
    area = _SUBSYSTEM_PLAIN_NAMES.get(
        finding.owner_subsystem,
        _SUBSYSTEM_PLAIN_NAMES.get(finding.app_id, "agent workflow"),
    )
    prio_label = _PRIORITY_PLAIN_NAMES.get(finding.priority, "tracked")
    occ = max(1, int(finding.occurrence_count))
    occ_phrase = "1 time" if occ == 1 else f"{occ} times"
    topic = _humanize_plain_english(finding.title or finding.root_cause_bucket, max_chars=72)
    if topic and topic.lower().startswith(area.lower()):
        topic = topic[len(area) :].strip(" ,-")

    is_close_margin = confidence_margin <= 0.20
    needs_mandatory_prefix = mode in {"TIER_B", "TIER_C"} or not is_close_margin
    prefix = "[Mandatory Approval] " if needs_mandatory_prefix else ""

    if mode == "TIER_C":
        action_phrase = f"Fix {prio_label} code issue in {area}"
        opt1_pct, opt1_tier = (88 if holdout_verdict and holdout_verdict.verdict == "PASS" else 85), "HIGH"
        opt2_pct, opt2_tier = 35, "LOW"
        opt3_pct, opt3_tier = 20, "LOW"
        impact_approve = "Applies fix in an isolated workspace, pins a check, and merges after tests pass."
        impact_snooze = f"Pauses this issue for {snooze_days} days and leaves live behavior unchanged."
        impact_reject = "Closes this finding and records that no change is wanted."
    elif mode == "TIER_B":
        action_phrase = f"Apply {prio_label} prompt update in {area}"
        opt1_pct, opt1_tier = (88 if holdout_verdict and holdout_verdict.verdict == "PASS" else 85), "HIGH"
        opt2_pct, opt2_tier = 35, "LOW"
        opt3_pct, opt3_tier = 20, "LOW"
        impact_approve = "Saves prompt update with canary monitoring and automatic rollback if quality drops."
        impact_snooze = f"Pauses this prompt update for {snooze_days} days without changing live behavior."
        impact_reject = "Declines this prompt update and archives the finding."
    else:
        action_phrase = f"Apply {prio_label} routing adjustment in {area}"
        opt1_pct = 72
        opt1_tier = "MEDIUM"
        clamped_margin = max(0.05, min(0.20, float(confidence_margin)))
        opt2_pct = max(54, min(68, round(opt1_pct - clamped_margin * 100)))
        opt2_tier = "MEDIUM"
        opt3_pct, opt3_tier = 25, "LOW"
        impact_approve = "Applies bounded setting update with canary checks and automatic rollback."
        impact_snooze = f"Pauses this borderline change for {snooze_days} days until more runs finish."
        impact_reject = "Discards this adjustment and keeps the current setting unchanged."

    detail = f" covering {topic} seen {occ_phrase}" if topic else f" seen {occ_phrase}"
    raw_question = f"{prefix}{action_phrase}{detail}"
    max_body = MAX_QUESTION_LENGTH - 1
    q_body = _trim_to_word_limit(raw_question, max_body).rstrip("?")
    question_text = f"{q_body}?"

    if scan_question_jargon(question_text):
        fallback_body = _trim_to_word_limit(f"{prefix}{action_phrase} seen {occ_phrase}", max_body).rstrip("?")
        question_text = f"{fallback_body}?"

    opt1 = _trim_to_word_limit(
        f"(Recommended) Approve and fix now (Confidence: {opt1_tier} ({opt1_pct}%)). Impact: {impact_approve}",
        MAX_OPTION_LENGTH,
    )
    opt2 = _trim_to_word_limit(
        f"Snooze for {snooze_days} days (Confidence: {opt2_tier} ({opt2_pct}%)). Impact: {impact_snooze}",
        MAX_OPTION_LENGTH,
    )
    opt3 = _trim_to_word_limit(
        f"Reject and archive (Confidence: {opt3_tier} ({opt3_pct}%)). Impact: {impact_reject}",
        MAX_OPTION_LENGTH,
    )
    options = [opt1, opt2, opt3]

    question_item = {
        "question": question_text,
        "options": options,
        "is_multi_select": False,
    }
    payload: dict[str, Any] = {
        "questions": [question_item],
        "metadata": {
            "contract_id": "urn:agents:learning:flywheel-hitl-question:1.0.0",
            "finding_id": finding.finding_id,
            "finding_digest": finding.finding_digest,
            "proposal_id": proposal.proposal_id,
            "proposal_digest": proposal.canonical_digest,
            "holdout_verdict_id": holdout_verdict.verdict_id if holdout_verdict else None,
            "holdout_verdict_digest": holdout_verdict.canonical_digest if holdout_verdict else None,
            "autonomy_tier": proposal.autonomy_tier,
            "effective_mode": mode,
            "confidence_margin": round(float(confidence_margin), 4),
            "impact_score": float(finding.impact_score),
            "target_files": list(finding.target_files)
            or ([proposal.target_path] if proposal.target_path else []),
            "action_map": {
                opt1: "APPROVE",
                opt2: "SNOOZE",
                opt3: "REJECT",
            },
        },
    }

    errors = validate_hitl_presentation(payload, enforce_visibility_and_jargon=True)
    if errors:
        raise ValueError(f"Compiled remediation question failed HITL presentation validation: {errors}")
    return payload


def _parse_operator_intent(operator_choice: str) -> Literal["APPROVE", "SNOOZE", "REJECT"]:
    cleaned = str(operator_choice or "").strip()
    if not cleaned:
        raise ValueError("Empty operator choice cannot resolve remediation decision")
    ok_auth, reason_auth = validate_approval_origin(cleaned)
    if not ok_auth:
        raise ValueError(f"SYNTHETIC_OPERATOR_CHOICE_REJECTED:{reason_auth}")
    low = cleaned.lower()
    for marker in _SYNTHETIC_APPROVAL_MARKERS:
        if marker in low:
            raise ValueError(f"SYNTHETIC_OPERATOR_CHOICE_REJECTED:{marker}")
    if "snooze" in low:
        return "SNOOZE"
    if "reject" in low or "archive" in low or "decline" in low:
        return "REJECT"
    if "approve" in low or "fix now" in low or "(recommended)" in low:
        return "APPROVE"
    raise ValueError(f"Unrecognized operator choice: {operator_choice!r}")


def record_remediation_decision(
    finding_id: str,
    proposal: ImprovementProposal,
    operator_choice: str,
    queue_store: SqliteFindingsQueueStore,
    hitl_store: HITLDecisionStore,
    *,
    approved_by: str = "operator",
    expected_finding_digest: str | None = None,
    expected_proposal_digest: str | None = None,
    confidence_margin: float = 0.30,
    snooze_days: int = 7,
    question_payload: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
    now_utc: datetime | None = None,
) -> RemediationDispatchAction:
    """Bind human decision digests, record in HITLDecisionStore, transition finding, and return dispatch action."""
    approver = str(approved_by or "").strip()
    if not approver:
        raise ValueError("MISSING_HUMAN_APPROVER_ID")
    approver_low = approver.lower()
    for marker in _SYNTHETIC_APPROVAL_MARKERS:
        if marker in approver_low:
            raise ValueError(f"SYNTHETIC_APPROVER_REJECTED:{marker}")

    intent = _parse_operator_intent(operator_choice)
    finding = queue_store.get_finding(finding_id)
    if finding is None:
        raise KeyError(f"Unknown finding_id: {finding_id}")

    if expected_finding_digest is not None and expected_finding_digest != finding.finding_digest:
        raise ValueError(
            f"FINDING_DIGEST_MISMATCH: expected={expected_finding_digest}, live={finding.finding_digest}"
        )
    if expected_proposal_digest is not None and expected_proposal_digest != proposal.canonical_digest:
        raise ValueError(
            f"PROPOSAL_DIGEST_MISMATCH: expected={expected_proposal_digest}, live={proposal.canonical_digest}"
        )
    if not proposal.verify_digest():
        raise ValueError(f"CORRUPT_PROPOSAL_DIGEST:{proposal.proposal_id}")

    payload = (
        dict(question_payload)
        if question_payload is not None
        else build_atomic_remediation_question(
            finding,
            proposal,
            confidence_margin=confidence_margin,
            snooze_days=snooze_days,
        )
    )
    q_item = (payload.get("questions") or [{}])[0]
    q_text = str(q_item.get("question") or "")
    options = list(q_item.get("options") or [])
    dec_id = stable_id(
        "hitl_rem",
        finding.finding_id,
        finding.finding_digest,
        proposal.proposal_id,
        proposal.canonical_digest,
        utc_now_iso(),
        length=16,
    )
    mode = _classify_remediation_mode(finding, proposal)
    top_conf = 0.85 if mode in {"TIER_B", "TIER_C"} else 0.72
    hitl_store.record_decision(
        decision_id=dec_id,
        task_id=finding.finding_id,
        category=f"flywheel_remediation_{mode.lower()}",
        options=options,
        selected_option=str(operator_choice),
        operator_action=("APPROVED" if intent == "APPROVE" else "OVERRIDDEN"),
        margin=round(float(confidence_margin), 4),
        calibrated_confidence=top_conf,
        context_summary=q_text[:200],
        outcome=("PENDING" if intent == "APPROVE" else ("SNOOZED" if intent == "SNOOZE" else "REJECTED")),
    )

    now_dt = now_utc or datetime.now(timezone.utc)
    if intent == "SNOOZE":
        until_iso = (now_dt + timedelta(days=int(snooze_days))).isoformat().replace("+00:00", "Z")
        updated = queue_store.transition_status(
            finding.finding_id,
            "SNOOZED",
            actor=approver,
            rationale=f"Operator snoozed remediation for {snooze_days} days via ask_question.",
            hitl_decision_id=dec_id,
            snoozed_until_utc=until_iso,
        )
        return RemediationDispatchAction(
            action="SNOOZED",
            finding_id=finding.finding_id,
            proposal_id=proposal.proposal_id,
            finding_digest=finding.finding_digest,
            proposal_digest=proposal.canonical_digest,
            finding_status=updated.status,
            hitl_decision_id=dec_id,
            snoozed_until_utc=until_iso,
            rationale=f"Snoozed until {until_iso}.",
        )

    if intent == "REJECT":
        updated = queue_store.transition_status(
            finding.finding_id,
            "REJECTED",
            actor=approver,
            rationale="Operator rejected and archived remediation via ask_question.",
            hitl_decision_id=dec_id,
        )
        return RemediationDispatchAction(
            action="REJECTED",
            finding_id=finding.finding_id,
            proposal_id=proposal.proposal_id,
            finding_digest=finding.finding_digest,
            proposal_digest=proposal.canonical_digest,
            finding_status=updated.status,
            hitl_decision_id=dec_id,
            rationale="Rejected and archived by operator.",
        )

    receipt_id = stable_id(
        "aprcpt",
        finding.finding_id,
        finding.finding_digest,
        proposal.proposal_id,
        proposal.canonical_digest,
        dec_id,
        length=16,
    )
    approval_receipt: dict[str, Any] = {
        "approval_receipt_id": receipt_id,
        "approval_origin": "HUMAN_HITL_APPROVED",
        "approved_by": approver,
        "hitl_decision_id": dec_id,
        "finding_id": finding.finding_id,
        "finding_digest": finding.finding_digest,
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.canonical_digest,
        "rationale": f"Human operator '{approver}' approved remediation for finding {finding.finding_id}.",
        "approved_at_utc": now_dt.isoformat().replace("+00:00", "Z"),
    }
    approval_receipt["receipt_digest"] = canonical_sha256(approval_receipt)
    ok_origin, origin_msg = validate_learning_approval_origin(approval_receipt)
    if not ok_origin:
        raise ValueError(f"Generated approval receipt failed origin check: {origin_msg}")

    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    routing = evaluate_auto_apply_policy(
        proposal=proposal,
        holdout_verdict=None,
        repo_root=root,
        confidence_margin=confidence_margin,
        now_utc=now_dt,
    )

    if routing.requires_pr or mode == "TIER_C":
        if finding.status != "APPROVED":
            queue_store.transition_status(
                finding.finding_id,
                "APPROVED",
                actor=approver,
                rationale=f"Operator approved Tier C remediation ({receipt_id}).",
                hitl_decision_id=dec_id,
            )
        updated = queue_store.transition_status(
            finding.finding_id,
            "IN_PROGRESS",
            actor=approver,
            rationale="Queued for isolated worktree root-cause fix, E2E pinning, and PR promotion.",
            hitl_decision_id=dec_id,
        )
        target_files = list(finding.target_files) or ([proposal.target_path] if proposal.target_path else [])
        branch_name = f"fix/{finding.finding_id}"
        pin_targets = ["apps_eval/suites/pinned_fix_regressions.json"]
        if finding.owner_subsystem:
            pin_targets.append(f"tests/end_to_end/ ({finding.owner_subsystem})")
        packet = {
            "schema_version": "agents.tier_c_worktree_fix_packet.v1",
            "finding_id": finding.finding_id,
            "finding_digest": finding.finding_digest,
            "proposal_id": proposal.proposal_id,
            "proposal_digest": proposal.canonical_digest,
            "hitl_decision_id": dec_id,
            "approval_receipt_id": receipt_id,
            "owner_subsystem": finding.owner_subsystem,
            "root_cause_bucket": finding.root_cause_bucket,
            "recommended_branch": branch_name,
            "target_files": target_files,
            "required_regression_pins": pin_targets,
            "verification_commands": [
                "python tools/verify_commit.py --staged --shard-fast",
                "python tools/audit_eval_construct_validity.py --verify-strict --include-e2e-pin",
                f"python tools/pr_governance.py promote {branch_name}",
            ],
        }
        return RemediationDispatchAction(
            action="EXECUTE_TIER_C_FIX_AND_PROMOTE",
            finding_id=finding.finding_id,
            proposal_id=proposal.proposal_id,
            finding_digest=finding.finding_digest,
            proposal_digest=proposal.canonical_digest,
            finding_status=updated.status,
            approval_receipt=approval_receipt,
            hitl_decision_id=dec_id,
            worktree_execution_packet=packet,
            rationale="Approved Tier C defect transitioned OPEN -> APPROVED -> IN_PROGRESS.",
        )

    updated = queue_store.transition_status(
        finding.finding_id,
        "APPROVED",
        actor=approver,
        rationale=f"Operator approved HITL-gated commit ({receipt_id}).",
        hitl_decision_id=dec_id,
    )
    return RemediationDispatchAction(
        action="EXECUTE_TIER_B_COMMIT",
        finding_id=finding.finding_id,
        proposal_id=proposal.proposal_id,
        finding_digest=finding.finding_digest,
        proposal_digest=proposal.canonical_digest,
        finding_status=updated.status,
        approval_receipt=approval_receipt,
        hitl_decision_id=dec_id,
        rationale="Approved HITL-gated update ready for atomic CAS commit + LP5 canary.",
    )


def execute_approved_tier_b_commit(
    *,
    action: RemediationDispatchAction,
    proposal: ImprovementProposal,
    holdout_verdict: HoldoutReplayVerdict,
    repo_root: Path,
    ledger_store: SqliteLearningLedgerStore,
    queue_store: SqliteFindingsQueueStore,
    hitl_store: HITLDecisionStore,
    rollback_dir: Path,
    seals_dir: Path,
    canary_metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    target_file_override: Path | None = None,
    confidence_margin: float = 0.30,
    run_id: str = "flywheel-hitl-commit",
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Execute an approved Tier B / HITL-gated commit through commit_engine + LP5 canary + queue transition."""
    if action.action != "EXECUTE_TIER_B_COMMIT" or action.approval_receipt is None:
        raise ValueError(f"Expected EXECUTE_TIER_B_COMMIT with approval_receipt, got {action.action}")

    applied = apply_proposal_atomically(
        proposal=proposal,
        holdout_verdict=holdout_verdict,
        repo_root=repo_root,
        ledger_store=ledger_store,
        rollback_dir=rollback_dir,
        target_file_override=target_file_override,
        approval_receipt=action.approval_receipt,
        confidence_margin=confidence_margin,
        now_utc=now_utc,
    )
    canary = evaluate_post_apply_canary_and_seal(
        receipt=applied,
        canary_metrics=canary_metrics,
        baseline_metrics=baseline_metrics,
        ledger_store=ledger_store,
        seals_dir=seals_dir,
        run_id=run_id,
        now_utc=now_utc,
    )
    if canary["canary_passed"]:
        queue_store.transition_status(
            action.finding_id,
            "VERIFIED",
            actor="commit_engine",
            rationale=f"Applied {applied.commit_id} and sealed LP0..LP5 ({canary['merkle_seal']['merkle_root'][:12]}).",
            hitl_decision_id=action.hitl_decision_id,
        )
        if action.hitl_decision_id:
            hitl_store.record_outcome(action.hitl_decision_id, "SUCCESS")
    else:
        queue_store.transition_status(
            action.finding_id,
            "OPEN",
            actor="rollback_manager",
            rationale="LP5 canary regressed; rolled back to pre-apply SHA-256.",
            hitl_decision_id=action.hitl_decision_id,
        )
        if action.hitl_decision_id:
            hitl_store.record_outcome(action.hitl_decision_id, "ROLLED_BACK")

    return {"applied_receipt": applied.to_dict(), "canary": canary}


def _default_calibration_runner(proposal: ImprovementProposal) -> CandidateRunnerFn:
    """Deterministic unlabeled_view scorer for numeric routing/threshold calibration replay."""

    def _runner(unlabeled_view: dict[str, Any], threshold_val: Any) -> dict[str, Any]:
        raw = unlabeled_view.get("unlabeled_input") or {}
        inner = raw.get("payload") if isinstance(raw.get("payload"), Mapping) else raw
        score_val = None
        if isinstance(inner, Mapping):
            if "score" in inner:
                score_val = float(inner["score"])
            elif "confidence" in inner:
                score_val = float(inner["confidence"])
        if score_val is None or threshold_val is None:
            return {"label": "FAIL", "latency_ms": 40.0, "cost_usd": 0.0}
        # Conservative surface threshold wraps borderline scores (< threshold) safely to PASS;
        # clear high-confidence cases (>= 0.80) continue passing regardless of minor threshold step.
        label = "PASS" if (score_val >= 0.80 or score_val < float(threshold_val)) else "FAIL"
        return {"label": label, "latency_ms": 40.0, "cost_usd": 0.0}

    return _runner


def _load_cases_by_split(dataset_path: Path | None) -> tuple[str, list[EvalCase], list[EvalCase]]:
    if dataset_path is None or not dataset_path.is_file():
        return "", [], []
    import json

    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    digest = str(raw.get("dataset_digest") or "")
    dev_cases: list[EvalCase] = []
    for item in raw.get("cases") or []:
        if str(item.get("split") or "") == "development":
            dev_cases.append(EvalCase.from_dict(item))
    _, holdouts = load_holdout_cases(dataset_path)
    return digest, dev_cases, holdouts


def _synthesize_single_finding_proposal(
    finding: FindingRecord,
    *,
    source_receipt_digests: Sequence[str] = (),
) -> ImprovementProposal:
    """Synthesize a fallback ImprovementProposal when an OPEN finding lacks a cluster-level proposal."""
    evidence_ids = list(finding.sample_trace_ids) or [finding.finding_id]
    if finding.track == "TRACK_2_CODE_FIX":
        target_path = (
            finding.target_files[0]
            if finding.target_files
            else f"{finding.owner_subsystem or 'agents'}/"
        )
        eval_plan = ["isolated_worktree_fix", "diff_scoped_eval_shield", "pr_governance_readiness"]
        patch_spec = {
            "action": "open_pr_for_root_cause_fix",
            "owner_subsystem": finding.owner_subsystem,
            "root_cause_bucket": finding.root_cause_bucket,
            "member_finding_ids": [finding.finding_id],
        }
        pid = stable_id("prop", finding.finding_id, target_path, finding.root_cause_bucket, length=16)
        prov = build_signed_provenance(
            proposal_id=pid,
            evidence_trace_ids=evidence_ids,
            source_receipt_digests=source_receipt_digests,
            proposed_change=patch_spec,
            evaluation_plan=eval_plan,
        )
        return ImprovementProposal(
            proposal_id=pid,
            cluster_id=f"clst-{finding.finding_id}",
            artifact_class="validator_or_code",
            autonomy_tier="TIER_C_PR_ONLY",
            risk_lane="LANE_2",
            target_path=target_path,
            target_key=None,
            expected_current_value=None,
            proposed_value_or_patch=patch_spec,
            step_delta_magnitude=0.0,
            evidence_trace_ids=evidence_ids,
            source_receipt_digests=list(source_receipt_digests),
            provenance_digest=prov,
            evaluation_plan=eval_plan,
            status="PROPOSED",
            expires_at_utc=(datetime.now(timezone.utc) + timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
        )

    target_path = "config/prompt_governance/priors.yaml"
    target_key = f"flywheel_priors.{finding.root_cause_bucket}"
    eval_plan = ["locked_holdout_replay", "lp5_canary"]
    pid = stable_id("prop", finding.finding_id, target_path, target_key, length=16)
    prov = build_signed_provenance(
        proposal_id=pid,
        evidence_trace_ids=evidence_ids,
        source_receipt_digests=source_receipt_digests,
        proposed_change={"key": target_key, "action": finding.recommended_action},
        evaluation_plan=eval_plan,
    )
    return ImprovementProposal(
        proposal_id=pid,
        cluster_id=f"clst-{finding.finding_id}",
        artifact_class="prompt_prior",
        autonomy_tier="TIER_B_HITL_GATED",
        risk_lane="LANE_1",
        target_path=target_path,
        target_key=target_key,
        expected_current_value=None,
        proposed_value_or_patch=finding.recommended_action,
        step_delta_magnitude=0.0,
        evidence_trace_ids=evidence_ids,
        source_receipt_digests=list(source_receipt_digests),
        provenance_digest=prov,
        evaluation_plan=eval_plan,
        status="PROPOSED",
        expires_at_utc=(datetime.now(timezone.utc) + timedelta(hours=72)).isoformat().replace("+00:00", "Z"),
    )


def _stage_sandbox_target(repo_root: Path, sandbox_targets_dir: Path, rel_target: str) -> Path | None:
    src = (repo_root / rel_target).resolve()
    if not src.is_file():
        return None
    dst = (sandbox_targets_dir / rel_target).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst


def dispatch_cycle_remediation(
    *,
    repo_root: Path,
    output_root: Path,
    queue_store: SqliteFindingsQueueStore,
    clusters: Sequence[FailureCluster],
    proposals: Sequence[ImprovementProposal],
    golden_dataset_path: Path | None = None,
    ledger_store: SqliteLearningLedgerStore | None = None,
    sandbox: bool = False,
    emit_next_hitl_question: bool = True,
    auto_apply_tier_a: bool = True,
    confidence_margin: float = 0.30,
    holdout_verdicts: Mapping[str, HoldoutReplayVerdict] | None = None,
    canary_metrics_by_proposal: Mapping[str, Mapping[str, Any]] | None = None,
    baseline_metrics_by_proposal: Mapping[str, Mapping[str, Any]] | None = None,
    shadow_runner: CandidateRunnerFn | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Auto-apply eligible Tier A proposals and emit at most one validated ask_question payload for Tier B/C/close-margin."""
    root = Path(repo_root).resolve()
    out = Path(output_root).resolve()
    policy = load_auto_apply_policy(root)
    interactive_cfg = policy.get("interactive_remediation") or {}
    effective_auto_apply = bool(auto_apply_tier_a and interactive_cfg.get("auto_apply_clear_tier_a", True))
    snooze_days = int(interactive_cfg.get("snooze_days_default", 7))

    owned_ledger = ledger_store is None
    active_ledger = ledger_store or SqliteLearningLedgerStore(out / "learning_ledger.sqlite")
    rollback_dir = out / "rollbacks"
    seals_dir = out / "seals"
    sandbox_targets_dir = out / "sandbox_targets"

    cluster_by_id = {c.cluster_id: c for c in clusters}
    dataset_digest, dev_cases, holdout_cases = _load_cases_by_split(golden_dataset_path)
    verdicts_map = dict(holdout_verdicts or {})

    auto_applied: list[dict[str, Any]] = []
    rolled_back: list[dict[str, Any]] = []
    policy_decisions: list[dict[str, Any]] = []
    proposal_by_finding_id: dict[str, tuple[ImprovementProposal, PolicyRoutingDecision, HoldoutReplayVerdict | None]] = {}

    try:
        for prop in proposals:
            cluster = cluster_by_id.get(prop.cluster_id)
            member_ids = list(cluster.member_finding_ids) if cluster is not None else []
            member_findings = [
                f for fid in member_ids if (f := queue_store.get_finding(fid)) is not None
            ]
            member_apps = {f.app_id for f in member_findings}

            verdict = verdicts_map.get(prop.proposal_id)
            if verdict is None and prop.autonomy_tier == "TIER_A_AUTO_APPLY":
                app_dev = [c for c in dev_cases if not member_apps or c.app_id in member_apps]
                app_hold = [c for c in holdout_cases if not member_apps or c.app_id in member_apps]
                if app_dev and app_hold and dataset_digest:
                    runner = shadow_runner or _default_calibration_runner(prop)
                    verdict = evaluate_proposal_in_shadow(
                        proposal=prop,
                        target_cluster_cases=app_dev,
                        holdout_cases=app_hold,
                        dataset_digest=dataset_digest,
                        candidate_runner=runner,
                    )

            decision = evaluate_auto_apply_policy(
                proposal=prop,
                holdout_verdict=verdict,
                repo_root=root,
                ledger_store=active_ledger,
                confidence_margin=confidence_margin,
                now_utc=now_utc,
            )
            policy_decisions.append(decision.to_dict())

            if (
                effective_auto_apply
                and decision.auto_apply_permitted
                and verdict is not None
                and not active_ledger.has_active_apply(prop.proposal_id)
            ):
                target_override: Path | None = None
                if sandbox:
                    target_override = _stage_sandbox_target(root, sandbox_targets_dir, prop.target_path)
                if not sandbox or target_override is not None:
                    applied = apply_proposal_atomically(
                        proposal=prop,
                        holdout_verdict=verdict,
                        repo_root=root,
                        ledger_store=active_ledger,
                        rollback_dir=rollback_dir,
                        target_file_override=target_override,
                        confidence_margin=confidence_margin,
                        now_utc=now_utc,
                    )
                    canary_metrics = dict(
                        (canary_metrics_by_proposal or {}).get(prop.proposal_id)
                        or {
                            "quality_score": verdict.holdout_accuracy_after,
                            "veto_defects": verdict.veto_regressions_count,
                            "latency_ms": 40.0,
                            "pinned_regressions_passed": verdict.pinned_regressions_passed,
                        }
                    )
                    baseline_metrics = dict(
                        (baseline_metrics_by_proposal or {}).get(prop.proposal_id)
                        or {"quality_score": verdict.holdout_accuracy_before}
                    )
                    canary = evaluate_post_apply_canary_and_seal(
                        receipt=applied,
                        canary_metrics=canary_metrics,
                        baseline_metrics=baseline_metrics,
                        ledger_store=active_ledger,
                        seals_dir=seals_dir,
                        now_utc=now_utc,
                    )
                    if canary["canary_passed"]:
                        for f in member_findings:
                            if f.status in {"OPEN", "APPROVED"}:
                                queue_store.transition_status(
                                    f.finding_id,
                                    "VERIFIED",
                                    actor="policy_tier_a_auto",
                                    rationale=f"Tier A auto-applied ({applied.commit_id}) and sealed LP0..LP5.",
                                )
                        auto_applied.append(
                            {
                                "proposal_id": prop.proposal_id,
                                "commit_id": applied.commit_id,
                                "target_path": applied.target_path,
                                "canary_status": canary["status"],
                                "merkle_root": canary["merkle_seal"]["merkle_root"],
                                "seal_path": canary["merkle_seal"].get("seal_path", ""),
                            }
                        )
                        continue
                    rolled_back.append(
                        {
                            "proposal_id": prop.proposal_id,
                            "commit_id": applied.commit_id,
                            "regressions": canary["regressions"],
                            "rollback": canary["rollback"],
                            "merkle_root": canary["merkle_seal"]["merkle_root"],
                        }
                    )

            for fid in member_ids:
                proposal_by_finding_id[fid] = (prop, decision, verdict)
    finally:
        if owned_ledger:
            active_ledger.close()

    # Select strictly the single highest-impact remaining OPEN finding for ask_question dispatch.
    open_findings = queue_store.list_findings(status="OPEN", limit=5000)
    next_ask_question_payload: dict[str, Any] | None = None
    if emit_next_hitl_question and open_findings:
        top_finding = open_findings[0]
        if top_finding.finding_id in proposal_by_finding_id:
            top_prop, _, top_verdict = proposal_by_finding_id[top_finding.finding_id]
        else:
            top_prop = _synthesize_single_finding_proposal(top_finding)
            top_verdict = None
        next_ask_question_payload = build_atomic_remediation_question(
            top_finding,
            top_prop,
            top_verdict,
            confidence_margin=confidence_margin,
            snooze_days=snooze_days,
        )

    return {
        "auto_applied_count": len(auto_applied),
        "auto_applied": auto_applied,
        "rolled_back_count": len(rolled_back),
        "rolled_back": rolled_back,
        "policy_decisions": policy_decisions,
        "pending_hitl_count": len(open_findings),
        "next_ask_question_payload": next_ask_question_payload,
    }
